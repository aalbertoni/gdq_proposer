"""
Scoring composto de regras propostas.

Avalia qualidade da proposta com base em cobertura, estabilidade,
interpretabilidade e eficiência de custo. Retorna RuleScore.

Definido conforme docs/technical_spec_v1.md seção 6.
"""

from dataclasses import dataclass, field

from core.models.enums import ConfidenceLevel, RuleType
from core.models.rule_proposal import BacktestSummary, RuleProposal
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


# Pesos da pontuação composta
WEIGHT_COVERAGE = 0.35
WEIGHT_STABILITY = 0.25
WEIGHT_INTERPRETABILITY = 0.20
WEIGHT_COST_EFFICIENCY = 0.20

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
    RuleType.IS_PRIMARY_KEY: 1.0,
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
    RuleType.IS_PRIMARY_KEY: 1.0,
    RuleType.CUSTOM_SQL: 0.6,
}


def score_proposal(
    proposal: RuleProposal,
    history_values: list[float] | None = None,
) -> RuleScore:
    """Avalia qualidade da regra proposta.

    Args:
        proposal: Proposta com thresholds e backtest.
        history_values: Série histórica para drift detection.

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

    # --- Warnings ---
    values = history_values or proposal.history_values
    valid_count = len(_filter_valid(values)) if values else 0

    if valid_count < 7:
        warnings.append("Pouco histórico: menos de 7 períodos válidos")
    if valid_count < 3:
        warnings.append("Dados insuficientes: menos de 3 períodos")

    if bt.has_drift:
        warnings.append("Tendência detectada no histórico")

    if bt.false_positive_proxy > 0:
        warnings.append(f"~{bt.false_positive_proxy} possíveis falsos positivos")

    if bt.band_width_ratio > 1.0:
        warnings.append("Banda muito larga — regra pouco seletiva")

    # --- Score total ---
    score_total = (
        WEIGHT_COVERAGE * coverage
        + WEIGHT_STABILITY * stability
        + WEIGHT_INTERPRETABILITY * interpretability
        + WEIGHT_COST_EFFICIENCY * cost_efficiency
    )

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

    return RuleScore(
        coverage=coverage,
        stability=stability,
        interpretability=interpretability,
        cost_efficiency=cost_efficiency,
        false_positive_count=bt.false_positive_proxy,
        sensitivity=bt.band_width_ratio,
        score_total=score_total,
        confidence=confidence,
        recommendation=recommendation,
        warnings=warnings,
    )
