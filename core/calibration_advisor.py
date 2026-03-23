"""
Assistente de Calibracao: substituicao explicavel do auto-tune grid search.

Logica sequencial em 5 etapas, onde cada decisao e justificada:
1. Escolher N (janela) baseado no grao e dados disponiveis
2. Testar sigma sozinho — se >=98% cobertura normal, nao usar margem
3. Adicionar margem somente se sigma insuficiente
4. Validar com backtest e ajustar se FPs recentes
5. Gerar relatorio de justificativa

Funcoes puras — sem I/O, sem Athena, sem UI.

Dependencias: core/backtest, core/statistical_engine, core/series_regime.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

from core.backtest import backtest_band, backtest_frequency_dual_guard
from core.models.enums import ConfidenceLevel, GrainType, SeriesRegime
from core.models.series_profile import SeriesProfile
from core.series_regime import classify_series
from core.statistical_engine import _filter_valid, detect_change_points


# ---------------------------------------------------------------------------
# Resultado da calibracao
# ---------------------------------------------------------------------------

@dataclass
class CalibrationStep:
    """Uma etapa do processo de calibracao com sua justificativa."""

    step: int
    name: str
    decision: str
    justification: str
    data: dict = field(default_factory=dict)


@dataclass
class CalibrationResult:
    """Resultado completo da calibracao com parametros e justificativas.

    Attrs:
        n_periods: Janela escolhida.
        n_sigma: Multiplicador de sigma escolhido.
        margin_pct: Margem percentual (0 se nao necessaria).
        margin_enabled: Se a margem esta ativa.
        coverage_pct: Cobertura do backtest final.
        weighted_coverage_pct: Cobertura ponderada por recencia.
        false_positives: FPs estimados do backtest final.
        confidence: Nivel de confianca final.
        viable: Se a calibracao encontrou parametros aceitaveis.
        steps: Lista de etapas com justificativas.
        recommendation: Texto final de recomendacao.
        profile: Perfil de regime da serie (se disponivel).
    """

    n_periods: int
    n_sigma: float
    margin_pct: float
    margin_enabled: bool
    coverage_pct: float
    weighted_coverage_pct: float
    false_positives: int
    stability: float
    confidence: ConfidenceLevel
    viable: bool
    steps: list[CalibrationStep] = field(default_factory=list)
    recommendation: str = ""
    profile: Optional[SeriesProfile] = None


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Cobertura minima de pontos normais para aceitar sigma sozinho
SIGMA_SUFFICIENT_THRESHOLD = 0.98

# Cobertura minima com margem para aceitar
MARGIN_SUFFICIENT_THRESHOLD = 0.98

# Sigmas testados em ordem de preferencia (menor = mais restritivo)
SIGMA_CANDIDATES = [2.0, 2.5, 3.0, 3.5]

# Margens testadas em ordem de preferencia (menor = mais restritivo)
MARGIN_CANDIDATES = [0.05, 0.10, 0.15, 0.20]

# N defaults por grao
N_DEFAULTS = {
    GrainType.DAILY: 30,
    GrainType.MONTHLY: 12,
}

# Minimo de pontos avaliados para considerar valido
MIN_EVALUATED_POINTS = 5

# FP maximo nos ultimos 7 periodos antes de relaxar
MAX_RECENT_FP = 0


# ---------------------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------------------

def _compute_outlier_mask(values: list[float]) -> set[int]:
    """Detecta outliers via IQR 2.5x e retorna indices."""
    valid = [(i, v) for i, v in enumerate(values)
             if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(valid) < 4:
        return set()

    sorted_vals = sorted(v for _, v in valid)
    q1_idx = len(sorted_vals) // 4
    q3_idx = 3 * len(sorted_vals) // 4
    q1 = sorted_vals[q1_idx]
    q3 = sorted_vals[q3_idx]
    iqr = q3 - q1
    fence_lower = q1 - 2.5 * iqr
    fence_upper = q3 + 2.5 * iqr

    return {i for i, v in valid if v < fence_lower or v > fence_upper}


def _normal_coverage(backtest_result, outlier_indices: set[int]) -> float:
    """Calcula cobertura de pontos normais (excluindo outliers)."""
    normal_pass = 0
    normal_total = 0
    for pr in backtest_result.point_results:
        if pr["index"] not in outlier_indices:
            normal_total += 1
            if pr["passed"]:
                normal_pass += 1
    if normal_total == 0:
        return backtest_result.coverage_pct / 100.0
    return normal_pass / normal_total


def _recent_fps(backtest_result, n_recent: int = 7) -> int:
    """Conta falsos positivos nos ultimos N periodos."""
    results = backtest_result.point_results
    if not results:
        return 0
    recent = results[-n_recent:]
    return sum(1 for r in recent if not r["passed"])


# ---------------------------------------------------------------------------
# Etapa 1: Escolher N
# ---------------------------------------------------------------------------

def choose_n(
    values: list[float],
    dates: list[str],
    grain: GrainType = GrainType.DAILY,
    profile: Optional[SeriesProfile] = None,
) -> CalibrationStep:
    """Escolhe a janela N baseada no grao e dados disponiveis.

    Regras:
    - Default: 30 (daily), 12 (monthly)
    - Se structural_break: usar apenas dados pos-mudanca
    - Se serie curta (< 2*N_default): reduzir proporcionalmente
    - Seasonal: preferir multiplo de 7 (daily)
    """
    valid = _filter_valid(values)
    n_valid = len(valid)
    n_default = N_DEFAULTS.get(grain, 30)
    reasons: list[str] = []

    n_chosen = n_default
    reasons.append(f"default para grao {grain.value}: N={n_default}")

    # Structural break: limitar N aos dados pos-mudanca
    post_change_len = None
    if profile and profile.has_structural_break:
        change_result = detect_change_points(values, dates)
        if change_result.get("has_change_point"):
            post_change_len = len(change_result.get("post_change_values", []))
            if post_change_len >= 5:
                n_chosen = min(n_chosen, max(post_change_len - 2, 5))
                reasons.append(
                    f"mudanca de regime em {profile.change_point_date}: "
                    f"limitado a {post_change_len} pontos pos-mudanca → N={n_chosen}"
                )

    # Serie curta: reduzir proporcionalmente
    if n_valid < 2 * n_chosen:
        n_chosen = max(n_valid // 2, 5)
        reasons.append(f"serie curta ({n_valid} pontos): reduzido para N={n_chosen}")

    # Seasonal (daily): preferir multiplo de 7
    if profile and profile.is_seasonal and grain == GrainType.DAILY:
        # Encontrar o multiplo de 7 mais proximo de n_chosen
        candidates_7 = [7, 14, 21, 28, 35, 42]
        best_7 = min(candidates_7, key=lambda x: abs(x - n_chosen))
        if best_7 <= n_valid // 2:
            n_chosen = best_7
            reasons.append(
                f"sazonalidade semanal detectada: ajustado para multiplo de 7 → N={n_chosen}"
            )

    justification = ". ".join(reasons) + "."

    return CalibrationStep(
        step=1,
        name="Escolha de N (janela)",
        decision=f"N = {n_chosen}",
        justification=f"N={n_chosen} porque {justification}",
        data={"n_periods": n_chosen, "n_valid": n_valid, "post_change_len": post_change_len},
    )


# ---------------------------------------------------------------------------
# Etapa 2: Testar sigma sozinho
# ---------------------------------------------------------------------------

def find_best_sigma(
    values: list[float],
    dates: list[str],
    n_periods: int,
    outlier_indices: set[int],
    metric_kind: str = "numeric",
) -> CalibrationStep:
    """Testa sigmas em ordem crescente sem margem.

    Se algum sigma atinge >= 98% cobertura normal, retorna-o.
    Sempre retorna o melhor sigma encontrado.
    """
    best_sigma = SIGMA_CANDIDATES[0]
    best_coverage = 0.0
    sigma_sufficient = False
    results_by_sigma: dict[float, float] = {}

    for sigma in SIGMA_CANDIDATES:
        try:
            if metric_kind == "frequency":
                bt = backtest_frequency_dual_guard(
                    pct_series=values, dates=dates,
                    n_periods=n_periods, n_sigma=sigma,
                    margin_pct=0.0, buffer=0.01,
                    margin_enabled=False,
                )
            else:
                bt = backtest_band(
                    values=values, dates=dates,
                    n_periods=n_periods, n_sigma=sigma,
                    margin_pct=0.0, margin_enabled=False,
                )
        except Exception:
            continue

        if bt.total_periods < MIN_EVALUATED_POINTS:
            continue

        cov = _normal_coverage(bt, outlier_indices)
        results_by_sigma[sigma] = cov

        if cov > best_coverage:
            best_coverage = cov
            best_sigma = sigma

        if cov >= SIGMA_SUFFICIENT_THRESHOLD and not sigma_sufficient:
            sigma_sufficient = True
            best_sigma = sigma
            best_coverage = cov
            break  # Menor sigma que atinge threshold — parar

    if sigma_sufficient:
        decision = f"sigma = {best_sigma} (suficiente sem margem)"
        justification = (
            f"sigma={best_sigma} cobre {best_coverage:.1%} dos pontos normais "
            f"(>= {SIGMA_SUFFICIENT_THRESHOLD:.0%}). Margem desnecessaria."
        )
    else:
        decision = f"sigma = {best_sigma} (melhor disponivel, margem necessaria)"
        justification = (
            f"Nenhum sigma atinge {SIGMA_SUFFICIENT_THRESHOLD:.0%} de cobertura normal. "
            f"Melhor: sigma={best_sigma} com {best_coverage:.1%}. Margem sera adicionada."
        )

    return CalibrationStep(
        step=2,
        name="Teste de sigma (sem margem)",
        decision=decision,
        justification=justification,
        data={
            "sigma": best_sigma,
            "coverage": best_coverage,
            "sigma_sufficient": sigma_sufficient,
            "results_by_sigma": results_by_sigma,
        },
    )


# ---------------------------------------------------------------------------
# Etapa 3: Adicionar margem se necessario
# ---------------------------------------------------------------------------

def add_margin_if_needed(
    values: list[float],
    dates: list[str],
    n_periods: int,
    sigma: float,
    sigma_sufficient: bool,
    outlier_indices: set[int],
    metric_kind: str = "numeric",
) -> CalibrationStep:
    """Adiciona margem somente se sigma nao foi suficiente.

    Testa margens em ordem crescente e escolhe a menor que atinge
    >= 98% cobertura normal com o sigma escolhido.
    """
    if sigma_sufficient:
        return CalibrationStep(
            step=3,
            name="Margem percentual",
            decision="margem desativada",
            justification="Sigma sozinho ja atinge cobertura suficiente. Margem nao necessaria.",
            data={"margin_pct": 0.0, "margin_enabled": False},
        )

    best_margin = MARGIN_CANDIDATES[0]
    best_coverage = 0.0
    margin_found = False
    results_by_margin: dict[float, float] = {}

    for margin in MARGIN_CANDIDATES:
        try:
            if metric_kind == "frequency":
                bt = backtest_frequency_dual_guard(
                    pct_series=values, dates=dates,
                    n_periods=n_periods, n_sigma=sigma,
                    margin_pct=margin, buffer=0.01,
                    margin_enabled=True,
                )
            else:
                bt = backtest_band(
                    values=values, dates=dates,
                    n_periods=n_periods, n_sigma=sigma,
                    margin_pct=margin, margin_enabled=True,
                )
        except Exception:
            continue

        if bt.total_periods < MIN_EVALUATED_POINTS:
            continue

        cov = _normal_coverage(bt, outlier_indices)
        results_by_margin[margin] = cov

        if cov > best_coverage:
            best_coverage = cov
            best_margin = margin

        if cov >= MARGIN_SUFFICIENT_THRESHOLD and not margin_found:
            margin_found = True
            best_margin = margin
            best_coverage = cov
            break

    if margin_found:
        justification = (
            f"Sigma={sigma} sozinho insuficiente. "
            f"Com margem {best_margin:.0%}, cobertura normal atinge {best_coverage:.1%}."
        )
    else:
        justification = (
            f"Sigma={sigma} sozinho insuficiente. "
            f"Melhor margem testada: {best_margin:.0%} com cobertura {best_coverage:.1%}. "
            f"A serie pode ser muito volatil para regra automatica."
        )

    return CalibrationStep(
        step=3,
        name="Margem percentual",
        decision=f"margem = {best_margin*100:.0f}% ({'ativada' if True else 'desativada'})",
        justification=justification,
        data={
            "margin_pct": best_margin,
            "margin_enabled": True,
            "coverage_with_margin": best_coverage,
            "results_by_margin": results_by_margin,
        },
    )


# ---------------------------------------------------------------------------
# Etapa 4: Validar com backtest
# ---------------------------------------------------------------------------

def validate_with_backtest(
    values: list[float],
    dates: list[str],
    n_periods: int,
    sigma: float,
    margin_pct: float,
    margin_enabled: bool,
    outlier_indices: set[int],
    metric_kind: str = "numeric",
) -> CalibrationStep:
    """Executa backtest final e verifica FPs recentes.

    Se ha FPs nos ultimos 7 periodos, tenta relaxar:
    1. Se margem desativada, ativa com menor margem viavel
    2. Se margem ativa, incrementa sigma em 0.5
    """
    try:
        if metric_kind == "frequency":
            bt = backtest_frequency_dual_guard(
                pct_series=values, dates=dates,
                n_periods=n_periods, n_sigma=sigma,
                margin_pct=margin_pct, buffer=0.01,
                margin_enabled=margin_enabled,
            )
        else:
            bt = backtest_band(
                values=values, dates=dates,
                n_periods=n_periods, n_sigma=sigma,
                margin_pct=margin_pct, margin_enabled=margin_enabled,
            )
    except Exception as e:
        return CalibrationStep(
            step=4,
            name="Validacao por backtest",
            decision="falha no backtest",
            justification=f"Backtest falhou: {e}. Dados insuficientes ou invalidos.",
            data={
                "backtest": None,
                "adjusted": False,
                "final_sigma": sigma,
                "final_margin_pct": margin_pct,
                "final_margin_enabled": margin_enabled,
            },
        )

    recent_fp = _recent_fps(bt, n_recent=7)
    adjusted = False
    adjust_reason = ""

    # Tentar relaxar se FPs recentes
    if recent_fp > MAX_RECENT_FP:
        if not margin_enabled:
            # Tentar ativar margem minima
            for try_margin in MARGIN_CANDIDATES:
                try:
                    if metric_kind == "frequency":
                        bt2 = backtest_frequency_dual_guard(
                            pct_series=values, dates=dates,
                            n_periods=n_periods, n_sigma=sigma,
                            margin_pct=try_margin, buffer=0.01,
                            margin_enabled=True,
                        )
                    else:
                        bt2 = backtest_band(
                            values=values, dates=dates,
                            n_periods=n_periods, n_sigma=sigma,
                            margin_pct=try_margin, margin_enabled=True,
                        )
                    if _recent_fps(bt2, 7) == 0:
                        bt = bt2
                        margin_pct = try_margin
                        margin_enabled = True
                        adjusted = True
                        adjust_reason = (
                            f"FP recente detectado: ativada margem {try_margin:.0%} para eliminar."
                        )
                        break
                except Exception:
                    continue
        else:
            # Tentar aumentar sigma
            for try_sigma in [sigma + 0.5, sigma + 1.0]:
                if try_sigma > 4.0:
                    break
                try:
                    if metric_kind == "frequency":
                        bt2 = backtest_frequency_dual_guard(
                            pct_series=values, dates=dates,
                            n_periods=n_periods, n_sigma=try_sigma,
                            margin_pct=margin_pct, buffer=0.01,
                            margin_enabled=True,
                        )
                    else:
                        bt2 = backtest_band(
                            values=values, dates=dates,
                            n_periods=n_periods, n_sigma=try_sigma,
                            margin_pct=margin_pct, margin_enabled=True,
                        )
                    if _recent_fps(bt2, 7) == 0:
                        bt = bt2
                        sigma = try_sigma
                        adjusted = True
                        adjust_reason = (
                            f"FP recente detectado: sigma aumentado para {try_sigma} para eliminar."
                        )
                        break
                except Exception:
                    continue

    normal_cov = _normal_coverage(bt, outlier_indices)

    if adjusted:
        justification = (
            f"Backtest: {bt.coverage_pct:.1f}% cobertura geral, "
            f"{bt.false_positive_proxy} FP(s). {adjust_reason}"
        )
    elif recent_fp > 0:
        justification = (
            f"Backtest: {bt.coverage_pct:.1f}% cobertura geral, "
            f"{bt.false_positive_proxy} FP(s). "
            f"{recent_fp} FP(s) nos ultimos 7 periodos — nao foi possivel eliminar completamente."
        )
    else:
        justification = (
            f"Backtest: {bt.coverage_pct:.1f}% cobertura geral, "
            f"0 FPs nos ultimos 7 periodos. Parametros validados."
        )

    return CalibrationStep(
        step=4,
        name="Validacao por backtest",
        decision=f"cobertura {bt.coverage_pct:.1f}%, {bt.false_positive_proxy} FP(s)",
        justification=justification,
        data={
            "backtest": bt,
            "adjusted": adjusted,
            "final_sigma": sigma,
            "final_margin_pct": margin_pct,
            "final_margin_enabled": margin_enabled,
            "normal_coverage": normal_cov,
            "recent_fps": _recent_fps(bt, 7),
        },
    )


# ---------------------------------------------------------------------------
# Etapa 5: Gerar relatorio
# ---------------------------------------------------------------------------

def generate_report(
    steps: list[CalibrationStep],
    profile: Optional[SeriesProfile] = None,
) -> CalibrationStep:
    """Gera relatorio consolidado da calibracao."""
    parts: list[str] = []

    if profile:
        parts.append(f"Regime: {profile.regime_summary}")
        if profile.has_structural_break and profile.change_point_date:
            parts.append(f"Mudanca de regime em {profile.change_point_date}")
        if profile.is_seasonal:
            parts.append(f"Sazonalidade detectada (eta²={profile.seasonality_strength:.2f})")
        if profile.is_volatile:
            parts.append(f"Serie volatil (CV={profile.cv:.2f})")
        if profile.is_asymmetric:
            parts.append(f"Distribuicao assimetrica (skew={profile.skewness:.2f})")

    for step in steps:
        parts.append(f"Etapa {step.step} ({step.name}): {step.decision}")

    return CalibrationStep(
        step=5,
        name="Relatorio",
        decision="calibracao concluida",
        justification="\n".join(parts),
        data={"summary_parts": parts},
    )


# ---------------------------------------------------------------------------
# Orquestrador principal
# ---------------------------------------------------------------------------

def calibrate(
    values: list[float],
    dates: list[str],
    grain: GrainType = GrainType.DAILY,
    metric_kind: str = "numeric",
    seasonality_enabled: bool = True,
    profile: Optional[SeriesProfile] = None,
) -> CalibrationResult:
    """Executa calibracao completa em 5 etapas sequenciais.

    Args:
        values: Serie temporal de valores.
        dates: Datas correspondentes.
        grain: Granularidade temporal (daily, monthly).
        metric_kind: "numeric" ou "frequency".
        seasonality_enabled: Se deve considerar sazonalidade semanal.
        profile: Perfil de regime pre-computado (opcional, sera calculado se None).

    Returns:
        CalibrationResult com parametros, justificativas e backtest.
    """
    valid = _filter_valid(values)
    if len(valid) < 5:
        return CalibrationResult(
            n_periods=N_DEFAULTS.get(grain, 30),
            n_sigma=2.0,
            margin_pct=0.0,
            margin_enabled=False,
            coverage_pct=0.0,
            weighted_coverage_pct=0.0,
            false_positives=0,
            stability=0.0,
            confidence=ConfidenceLevel.LOW,
            viable=False,
            recommendation="Dados insuficientes para calibracao (minimo 5 pontos validos).",
        )

    # Classificar regime se nao fornecido
    if profile is None:
        profile = classify_series(values, dates, seasonality_enabled=seasonality_enabled)

    # Mascara de outliers (calculada uma vez)
    outlier_indices = _compute_outlier_mask(values)

    steps: list[CalibrationStep] = []

    # Etapa 1: Escolher N
    step1 = choose_n(values, dates, grain=grain, profile=profile)
    steps.append(step1)
    n_periods = step1.data["n_periods"]

    # Etapa 2: Testar sigma sozinho
    step2 = find_best_sigma(
        values, dates, n_periods, outlier_indices, metric_kind=metric_kind,
    )
    steps.append(step2)
    sigma = step2.data["sigma"]
    sigma_sufficient = step2.data["sigma_sufficient"]

    # Etapa 3: Margem se necessario
    step3 = add_margin_if_needed(
        values, dates, n_periods, sigma, sigma_sufficient, outlier_indices,
        metric_kind=metric_kind,
    )
    steps.append(step3)
    margin_pct = step3.data["margin_pct"]
    margin_enabled = step3.data["margin_enabled"]

    # Etapa 4: Validar com backtest
    step4 = validate_with_backtest(
        values, dates, n_periods, sigma, margin_pct, margin_enabled,
        outlier_indices, metric_kind=metric_kind,
    )
    steps.append(step4)

    # Parametros finais (podem ter sido ajustados na etapa 4)
    final_sigma = step4.data.get("final_sigma", sigma)
    final_margin_pct = step4.data.get("final_margin_pct", margin_pct)
    final_margin_enabled = step4.data.get("final_margin_enabled", margin_enabled)
    bt = step4.data.get("backtest")

    # Etapa 5: Relatorio
    step5 = generate_report(steps, profile=profile)
    steps.append(step5)

    # Extrair metricas do backtest final
    coverage_pct = bt.coverage_pct if bt else 0.0
    weighted_coverage_pct = bt.weighted_coverage_pct if bt else 0.0
    false_positives = bt.false_positive_proxy if bt else 0
    stability = bt.stability_score if bt else 0.0

    # Determinar confianca
    if coverage_pct >= 90.0 and false_positives == 0:
        confidence = ConfidenceLevel.HIGH
    elif coverage_pct >= 70.0:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.LOW

    viable = coverage_pct >= 70.0

    # Construir recomendacao
    recommendation = _build_recommendation(
        n_periods, final_sigma, final_margin_pct, final_margin_enabled,
        coverage_pct, false_positives, confidence, profile, steps,
    )

    return CalibrationResult(
        n_periods=n_periods,
        n_sigma=final_sigma,
        margin_pct=final_margin_pct,
        margin_enabled=final_margin_enabled,
        coverage_pct=coverage_pct,
        weighted_coverage_pct=weighted_coverage_pct,
        false_positives=false_positives,
        stability=stability,
        confidence=confidence,
        viable=viable,
        steps=steps,
        recommendation=recommendation,
        profile=profile,
    )


def _build_recommendation(
    n_periods: int,
    sigma: float,
    margin_pct: float,
    margin_enabled: bool,
    coverage_pct: float,
    false_positives: int,
    confidence: ConfidenceLevel,
    profile: Optional[SeriesProfile],
    steps: list[CalibrationStep],
) -> str:
    """Constroi texto de recomendacao consolidado."""
    parts: list[str] = []

    # Parametros escolhidos
    sigma_str = str(int(sigma)) if sigma == int(sigma) else f"{sigma:.1f}"
    if margin_enabled:
        params = (
            f"N={n_periods}, sigma={sigma_str}, margem={margin_pct*100:.0f}%"
        )
    else:
        params = f"N={n_periods}, sigma={sigma_str} (sem margem)"

    # Veredicto principal
    if confidence == ConfidenceLevel.HIGH:
        parts.append(f"Recomendado: {params}. Cobertura {coverage_pct:.1f}%, 0 falsos positivos.")
    elif confidence == ConfidenceLevel.MEDIUM:
        fp_text = f", {false_positives} FP(s)" if false_positives > 0 else ""
        parts.append(f"Aceitavel: {params}. Cobertura {coverage_pct:.1f}%{fp_text}. Revise os parametros.")
    else:
        parts.append(
            f"Nao recomendado: {params}. Cobertura {coverage_pct:.1f}% com {false_positives} FP(s). "
            f"A metrica pode ser instavel para regra automatica."
        )

    # Justificativa do sigma/margem
    if not margin_enabled:
        parts.append(
            f"Sigma {sigma_str} suficiente sozinho — distribuicao bem comportada."
        )
    else:
        parts.append(
            f"Margem {margin_pct*100:.0f}% necessaria — sigma sozinho nao cobria pontos normais suficientes."
        )

    # Contexto de regime
    if profile and profile.regime != SeriesRegime.STABLE:
        regime_texts = {
            SeriesRegime.STRUCTURAL_BREAK: "Mudanca de regime detectada — N limitado a dados pos-mudanca.",
            SeriesRegime.TRENDING: "Tendencia detectada — N reduzido para acompanhar.",
            SeriesRegime.SEASONAL: "Sazonalidade detectada — N ajustado para multiplo de 7.",
            SeriesRegime.VOLATILE: "Serie volatil — parametros podem precisar de revisao periodica.",
            SeriesRegime.ZERO_INFLATED: "Serie com muitos zeros — considere regra alternativa.",
            SeriesRegime.ASYMMETRIC: "Distribuicao assimetrica — margem complementa sigma.",
            SeriesRegime.SPARSE: "Serie esparsa — poucos dados reduzem confianca.",
        }
        regime_text = regime_texts.get(profile.regime)
        if regime_text:
            parts.append(regime_text)

    return " ".join(parts)
