"""
Scoring composto de regras propostas.

Avalia qualidade da proposta com base em cobertura, estabilidade,
interpretabilidade, eficiência de custo, adequação ao regime,
risco de FP e robustez dos dados.

Definido conforme docs/technical_spec_v1.md seção 6.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.models.enums import ConfidenceLevel, RuleType, SeriesRegime
from core.models.rule_evaluation import RuleEvaluation
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.series_profile import SeriesProfile
from core.statistical_engine import detect_drift, _filter_valid


@dataclass
class RuleScore:
    """Avaliação composta da regra proposta."""

    coverage: float          # 0-1 (do backtest)
    stability: float         # 0-1 (do backtest)
    interpretability: float  # 0-1 (hardcoded por rule_type)
    cost_efficiency: float   # 0-1 (hardcoded por rule_type)
    false_positive_count: int
    sensitivity: float       # band_width / center
    score_total: float       # weighted sum
    confidence: ConfidenceLevel
    recommendation: str
    warnings: list[str] = field(default_factory=list)


# Pesos da pontuação composta (clássicos)
WEIGHT_COVERAGE = 0.30
WEIGHT_STABILITY = 0.20
WEIGHT_INTERPRETABILITY = 0.10
WEIGHT_COST_EFFICIENCY = 0.10
WEIGHT_REGIME_FIT = 0.15
WEIGHT_ROBUSTNESS = 0.15

# Interpretability por tipo de regra
_INTERPRETABILITY = {
    RuleType.MEAN_DUAL_GUARD: 1.0,
    RuleType.STDDEV_DUAL_GUARD: 1.0,
    RuleType.ROW_COUNT_DUAL_GUARD: 1.0,
    RuleType.COMPLETENESS: 1.0,
    RuleType.ALLOWED_VALUES: 0.9,
    RuleType.DISTINCT_COUNT_EXACT: 0.9,
    RuleType.DISTINCT_COUNT_RANGE: 0.9,
    RuleType.CATEGORY_FREQUENCY_STATIC: 0.8,
    RuleType.CATEGORY_FREQUENCY_DYNAMIC: 0.7,
    RuleType.CATEGORY_FREQUENCY_HYBRID: 0.7,
    RuleType.NUMERIC_PERCENTILE_BAND: 0.8,
    RuleType.IS_PRIMARY_KEY: 1.0,
    RuleType.UNIQUENESS_CUSTOM_SQL: 0.8,
    RuleType.CUSTOM_SQL: 0.6,
}

# Cost efficiency por tipo de regra (built-in = 1.0, CustomSql = 0.7)
_COST_EFFICIENCY = {
    RuleType.MEAN_DUAL_GUARD: 1.0,
    RuleType.STDDEV_DUAL_GUARD: 1.0,
    RuleType.ROW_COUNT_DUAL_GUARD: 1.0,
    RuleType.COMPLETENESS: 1.0,
    RuleType.ALLOWED_VALUES: 1.0,
    RuleType.DISTINCT_COUNT_EXACT: 1.0,
    RuleType.DISTINCT_COUNT_RANGE: 1.0,
    RuleType.CATEGORY_FREQUENCY_STATIC: 0.7,
    RuleType.CATEGORY_FREQUENCY_DYNAMIC: 0.7,
    RuleType.CATEGORY_FREQUENCY_HYBRID: 0.7,
    RuleType.NUMERIC_PERCENTILE_BAND: 0.7,
    RuleType.IS_PRIMARY_KEY: 1.0,
    RuleType.UNIQUENESS_CUSTOM_SQL: 0.7,
    RuleType.CUSTOM_SQL: 0.6,
}

# Regime fit por (regime, rule_type) — valores padrão por regime
_REGIME_FIT_DEFAULTS: dict[SeriesRegime, float] = {
    SeriesRegime.STABLE: 1.0,
    SeriesRegime.VOLATILE: 0.7,
    SeriesRegime.TRENDING: 0.6,
    SeriesRegime.SEASONAL: 0.7,
    SeriesRegime.STRUCTURAL_BREAK: 0.4,
    SeriesRegime.ZERO_INFLATED: 0.6,
    SeriesRegime.ASYMMETRIC: 0.7,
    SeriesRegime.SPARSE: 0.5,
}

# Overrides específicos por (regime, rule_type)
_REGIME_FIT_OVERRIDES: dict[tuple[SeriesRegime, RuleType], float] = {
    # Volatile: RowCount still works well, Mean/StdDev less so
    (SeriesRegime.VOLATILE, RuleType.ROW_COUNT_DUAL_GUARD): 0.9,
    (SeriesRegime.VOLATILE, RuleType.COMPLETENESS): 0.9,
    (SeriesRegime.VOLATILE, RuleType.MEAN_DUAL_GUARD): 0.6,
    (SeriesRegime.VOLATILE, RuleType.STDDEV_DUAL_GUARD): 0.6,
    # Trending: Mean misleading, RowCount less affected
    (SeriesRegime.TRENDING, RuleType.MEAN_DUAL_GUARD): 0.5,
    (SeriesRegime.TRENDING, RuleType.ROW_COUNT_DUAL_GUARD): 0.8,
    (SeriesRegime.TRENDING, RuleType.COMPLETENESS): 0.9,
    # Structural break: full-history rules unreliable
    (SeriesRegime.STRUCTURAL_BREAK, RuleType.MEAN_DUAL_GUARD): 0.3,
    (SeriesRegime.STRUCTURAL_BREAK, RuleType.STDDEV_DUAL_GUARD): 0.3,
    (SeriesRegime.STRUCTURAL_BREAK, RuleType.ROW_COUNT_DUAL_GUARD): 0.5,
    (SeriesRegime.STRUCTURAL_BREAK, RuleType.COMPLETENESS): 0.8,
    # Zero-inflated: Mean skewed by zeros
    (SeriesRegime.ZERO_INFLATED, RuleType.MEAN_DUAL_GUARD): 0.4,
    (SeriesRegime.ZERO_INFLATED, RuleType.COMPLETENESS): 1.0,
    (SeriesRegime.ZERO_INFLATED, RuleType.ROW_COUNT_DUAL_GUARD): 0.8,
    # Sparse: everything less reliable, Completeness still relevant
    (SeriesRegime.SPARSE, RuleType.COMPLETENESS): 0.9,
    # Asymmetric: symmetric bands suboptimal for Mean
    (SeriesRegime.ASYMMETRIC, RuleType.MEAN_DUAL_GUARD): 0.5,
}


def _compute_regime_fit(
    regime: SeriesRegime,
    secondary: tuple[SeriesRegime, ...],
    rule_type: RuleType,
) -> float:
    """Calcula adequacao da regra ao regime da serie.

    Usa override especifico (regime, rule_type) se existir,
    senao usa default do regime. Para regimes secundarios,
    aplica penalidade proporcional (30% do impacto do secundario).
    """
    # Primary regime fit
    fit = _REGIME_FIT_OVERRIDES.get(
        (regime, rule_type),
        _REGIME_FIT_DEFAULTS.get(regime, 0.8),
    )

    # Secondary regime penalty (30% of each secondary's impact)
    for sec_regime in secondary:
        sec_fit = _REGIME_FIT_OVERRIDES.get(
            (sec_regime, rule_type),
            _REGIME_FIT_DEFAULTS.get(sec_regime, 0.8),
        )
        penalty = (1.0 - sec_fit) * 0.30
        fit = max(0.0, fit - penalty)

    return round(fit, 4)


def _compute_fp_risk(
    profile: Optional[SeriesProfile],
    bt: Optional[BacktestSummary],
) -> float:
    """Calcula risco de falsos positivos (0=baixo, 1=alto).

    Fatores: CV alto, banda estreita, outliers frequentes, assimetria.
    """
    risk = 0.0

    if bt is not None:
        # FPs reais no backtest
        if bt.false_positive_proxy > 0:
            risk += min(bt.false_positive_proxy * 0.10, 0.40)
        # Banda muito estreita com serie volatil
        if bt.band_width_ratio < 0.10:
            risk += 0.15

    if profile is not None:
        # CV alto → mais chance de violações espúrias
        if profile.cv > 0.50:
            risk += 0.20
        elif profile.cv > 0.30:
            risk += 0.10
        # Assimetria → bandas simétricas geram FP em um lado
        if profile.is_asymmetric:
            risk += 0.15
        # Muitos outliers IQR → boundary entre normal e outlier difusa
        if profile.n_outliers_iqr > 3:
            risk += 0.10

    return min(round(risk, 4), 1.0)


_DEFAULT_ROBUSTNESS_TIERS = ((7, -0.30), (15, -0.15), (30, -0.05))


def _compute_robustness(
    profile: Optional[SeriesProfile],
    valid_count: int,
    robustness_tiers: tuple[tuple[int, float], ...] = _DEFAULT_ROBUSTNESS_TIERS,
) -> float:
    """Calcula robustez/confiabilidade da avaliacao (0-1).

    Baseado em: quantidade de dados, % nulos, % zeros, outliers.
    robustness_tiers define (threshold, penalty) adaptativos por grain.
    """
    score = 1.0

    # Penalidade por poucos dados (adaptativa)
    for threshold, penalty in sorted(robustness_tiers, key=lambda t: t[0]):
        if valid_count < threshold:
            score += penalty  # penalty e negativo
            break

    if profile is not None:
        # Penalidade por nulos
        if profile.null_pct > 50:
            score -= 0.25
        elif profile.null_pct > 30:
            score -= 0.15
        elif profile.null_pct > 10:
            score -= 0.05

        # Penalidade por muitos zeros
        if profile.is_zero_inflated:
            score -= 0.10

        # Penalidade por muitos outliers (dados ruidosos)
        if profile.n_outliers_iqr > 5:
            score -= 0.10

    return max(round(score, 4), 0.0)


def _regime_warnings(profile: SeriesProfile) -> list[str]:
    """Gera warnings especificos do regime detectado."""
    warns: list[str] = []

    if profile.regime == SeriesRegime.STRUCTURAL_BREAK:
        date_str = f" em {profile.change_point_date}" if profile.change_point_date else ""
        warns.append(
            f"Mudanca de regime detectada{date_str} — "
            "baseline pode nao refletir o padrao atual. "
            "Considere usar N menor (apenas pos-mudanca)."
        )

    if profile.regime == SeriesRegime.TRENDING or profile.has_trend:
        warns.append(
            f"Tendencia detectada (slope={profile.drift_slope:.4f}) — "
            "banda pode ficar defasada. Considere N menor para acompanhar."
        )

    if profile.is_seasonal:
        warns.append(
            f"Sazonalidade detectada (forca={profile.seasonality_strength:.2f}) — "
            "use N multiplo de 7 para suavizar efeito semanal."
        )

    if profile.is_volatile:
        warns.append(
            f"Serie volatil (CV={profile.cv:.2f}) — "
            "banda larga necessaria, risco de falsos positivos."
        )

    if profile.is_asymmetric:
        warns.append(
            f"Distribuicao assimetrica (skewness={profile.skewness:.2f}) — "
            "bandas simetricas podem gerar alertas em apenas um lado."
        )

    if profile.is_zero_inflated:
        warns.append(
            f"Serie zero-inflated ({profile.zero_pct:.0f}% zeros) — "
            "media distorcida, considere regra de completude ao inves de media."
        )

    if profile.is_sparse:
        warns.append(
            f"Dados esparsos ({profile.null_pct:.0f}% nulos) — "
            "confiabilidade reduzida, monitore com cautela."
        )

    return warns


def score_proposal(
    proposal: RuleProposal,
    history_values: list[float] | None = None,
    profile: SeriesProfile | None = None,
    robustness_tiers: tuple[tuple[int, float], ...] | None = None,
) -> RuleScore:
    """Avalia qualidade da regra proposta.

    Args:
        proposal: Proposta com thresholds e backtest.
        history_values: Série histórica para drift detection.
        profile: Perfil de regime da série (opcional, enriquece scoring).

    Returns:
        RuleScore com avaliação composta.
    """
    warnings = list(proposal.warnings)

    # --- Extrair métricas do backtest ---
    bt = proposal.backtest
    if bt is None:
        return RuleScore(
            coverage=0.0,
            stability=0.0,
            interpretability=_INTERPRETABILITY.get(proposal.rule_type, 0.5),
            cost_efficiency=_COST_EFFICIENCY.get(proposal.rule_type, 0.5),
            false_positive_count=0,
            sensitivity=0.0,
            score_total=0.0,
            confidence=ConfidenceLevel.LOW,
            recommendation="Sem backtest disponível",
            warnings=warnings + ["Backtest não executado"],
        )

    coverage = bt.coverage_pct / 100.0  # normalize to 0-1
    stability = bt.stability_score
    interpretability = _INTERPRETABILITY.get(proposal.rule_type, 0.5)
    cost_efficiency = _COST_EFFICIENCY.get(proposal.rule_type, 0.5)

    # --- Regime-aware dimensions ---
    if profile is not None:
        regime_fit = _compute_regime_fit(
            profile.regime, profile.secondary_regimes, proposal.rule_type,
        )
        fp_risk = _compute_fp_risk(profile, bt)
        regime_warns = _regime_warnings(profile)
        warnings.extend(regime_warns)
    else:
        regime_fit = 1.0
        fp_risk = _compute_fp_risk(None, bt)

    # --- Data quality warnings ---
    values = history_values or proposal.history_values
    valid_count = len(_filter_valid(values)) if values else 0

    _rt = robustness_tiers or _DEFAULT_ROBUSTNESS_TIERS
    robustness = _compute_robustness(profile, valid_count, robustness_tiers=_rt)

    _min_tier = min(t for t, _ in _rt) if _rt else 7
    if valid_count < _min_tier:
        warnings.append(f"Pouco historico: menos de {_min_tier} periodos validos")
    if valid_count < 3:
        warnings.append("Dados insuficientes: menos de 3 periodos")

    if bt.has_drift:
        warnings.append("Tendência detectada no histórico")

    if bt.false_positive_proxy > 0:
        warnings.append(f"~{bt.false_positive_proxy} possíveis falsos positivos")

    if bt.band_width_ratio > 1.0:
        warnings.append("Banda muito larga — regra pouco seletiva")

    # --- Score total (6 dimensões) ---
    score_total = (
        WEIGHT_COVERAGE * coverage
        + WEIGHT_STABILITY * stability
        + WEIGHT_INTERPRETABILITY * interpretability
        + WEIGHT_COST_EFFICIENCY * cost_efficiency
        + WEIGHT_REGIME_FIT * regime_fit
        + WEIGHT_ROBUSTNESS * robustness
        - fp_risk * 0.10  # FP risk como penalidade
    )
    score_total = max(0.0, min(1.0, score_total))

    # Force LOW if insufficient data
    if valid_count < 3:
        confidence = ConfidenceLevel.LOW
    elif score_total >= 0.80:
        confidence = ConfidenceLevel.HIGH
    elif score_total >= 0.55:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.LOW

    # --- Recommendation ---
    if confidence == ConfidenceLevel.HIGH:
        recommendation = "Regra recomendada para produção"
    elif confidence == ConfidenceLevel.MEDIUM:
        recommendation = "Regra aceitável — revisar parâmetros"
    else:
        recommendation = "Regra instável — não recomendada sem ajuste"

    # Enrich recommendation with regime info
    if profile is not None and profile.regime != SeriesRegime.STABLE:
        recommendation += f" [regime: {profile.regime_summary}]"

    return RuleScore(
        coverage=coverage,
        stability=stability,
        interpretability=interpretability,
        cost_efficiency=cost_efficiency,
        false_positive_count=bt.false_positive_proxy,
        sensitivity=bt.band_width_ratio,
        score_total=round(score_total, 4),
        confidence=confidence,
        recommendation=recommendation,
        warnings=warnings,
    )


def evaluate_proposal(
    proposal: RuleProposal,
    profile: SeriesProfile | None = None,
    history_values: list[float] | None = None,
    robustness_tiers: tuple[tuple[int, float], ...] | None = None,
) -> RuleEvaluation:
    """Avaliacao enriquecida com todas as dimensoes.

    Wrapper que combina score_proposal com dimensoes de regime
    em um RuleEvaluation completo.

    Args:
        proposal: Proposta com thresholds e backtest.
        profile: Perfil de regime da série.
        history_values: Série histórica.

    Returns:
        RuleEvaluation com 7 dimensões + contexto de regime.
    """
    bt = proposal.backtest
    values = history_values or proposal.history_values
    valid_count = len(_filter_valid(values)) if values else 0

    # Classic dimensions
    coverage = (bt.coverage_pct / 100.0) if bt else 0.0
    stability = bt.stability_score if bt else 0.0
    interpretability = _INTERPRETABILITY.get(proposal.rule_type, 0.5)
    cost_efficiency = _COST_EFFICIENCY.get(proposal.rule_type, 0.5)

    # Regime-aware dimensions
    if profile is not None:
        regime_fit = _compute_regime_fit(
            profile.regime, profile.secondary_regimes, proposal.rule_type,
        )
        fp_risk = _compute_fp_risk(profile, bt)
        regime_warns = _regime_warnings(profile)
        regime_summary = profile.regime_summary
    else:
        regime_fit = 1.0
        fp_risk = _compute_fp_risk(None, bt)
        regime_warns = []
        regime_summary = None

    _rt_ev = robustness_tiers or _DEFAULT_ROBUSTNESS_TIERS
    robustness = _compute_robustness(profile, valid_count, robustness_tiers=_rt_ev)

    # Score total
    score_total = (
        WEIGHT_COVERAGE * coverage
        + WEIGHT_STABILITY * stability
        + WEIGHT_INTERPRETABILITY * interpretability
        + WEIGHT_COST_EFFICIENCY * cost_efficiency
        + WEIGHT_REGIME_FIT * regime_fit
        + WEIGHT_ROBUSTNESS * robustness
        - fp_risk * 0.10
    )
    score_total = max(0.0, min(1.0, round(score_total, 4)))

    # Confidence
    if bt is None or valid_count < 3:
        confidence = ConfidenceLevel.LOW
    elif score_total >= 0.80:
        confidence = ConfidenceLevel.HIGH
    elif score_total >= 0.55:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.LOW

    # Recommendation
    if confidence == ConfidenceLevel.HIGH:
        recommendation = "Regra recomendada para produção"
    elif confidence == ConfidenceLevel.MEDIUM:
        recommendation = "Regra aceitável — revisar parâmetros"
    else:
        recommendation = "Regra instável — não recomendada sem ajuste"

    if profile is not None and profile.regime != SeriesRegime.STABLE:
        recommendation += f" [regime: {profile.regime_summary}]"

    # Warnings
    warnings: list[str] = list(proposal.warnings)
    if bt is None:
        warnings.append("Backtest não executado")
    else:
        if bt.has_drift:
            warnings.append("Tendência detectada no histórico")
        if bt.false_positive_proxy > 0:
            warnings.append(f"~{bt.false_positive_proxy} possíveis falsos positivos")
        if bt.band_width_ratio > 1.0:
            warnings.append("Banda muito larga — regra pouco seletiva")

    _min_tier_ev = min(t for t, _ in _rt_ev) if _rt_ev else 7
    if valid_count < _min_tier_ev:
        warnings.append("Pouco histórico: menos de 7 períodos válidos")
    if valid_count < 3:
        warnings.append("Dados insuficientes: menos de 3 períodos")

    return RuleEvaluation(
        coverage=coverage,
        stability=stability,
        interpretability=interpretability,
        cost_efficiency=cost_efficiency,
        regime_fit=regime_fit,
        fp_risk=fp_risk,
        robustness=robustness,
        false_positive_count=bt.false_positive_proxy if bt else 0,
        sensitivity=bt.band_width_ratio if bt else 0.0,
        score_total=score_total,
        confidence=confidence,
        recommendation=recommendation,
        regime_summary=regime_summary,
        regime_warnings=regime_warns,
        warnings=warnings,
    )
