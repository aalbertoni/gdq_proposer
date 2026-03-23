"""
Gerador de explicacoes para o Assistente de Calibracao.

Converte CalibrationResult em texto legivel em pt-BR,
detalhando cada etapa e decisao do processo de calibracao.

Funcoes puras — sem I/O, sem Athena, sem UI.
"""

from core.calibration_advisor import CalibrationResult, CalibrationStep
from core.models.enums import ConfidenceLevel, SeriesRegime


def explain_calibration(result: CalibrationResult) -> str:
    """Gera texto explicativo completo da calibracao em pt-BR.

    Args:
        result: Resultado da calibracao com etapas.

    Returns:
        Markdown com explicacao passo a passo.
    """
    parts: list[str] = []

    parts.append("### Assistente de Calibracao")
    parts.append("")

    # Resumo do regime
    if result.profile:
        profile = result.profile
        if profile.regime == SeriesRegime.STABLE:
            parts.append("**Regime:** Estavel — serie sem anomalias detectadas.")
        else:
            parts.append(f"**Regime:** {profile.regime_summary}")
            _append_regime_detail(parts, profile)
        parts.append("")

    # Etapas
    for step in result.steps:
        if step.step == 5:
            continue  # Relatorio nao precisa ser repetido
        parts.append(f"**Etapa {step.step}: {step.name}**")
        parts.append(f"- Decisao: {step.decision}")
        parts.append(f"- Justificativa: {step.justification}")
        parts.append("")

    # Veredicto final
    parts.append("---")
    parts.append(f"**Resultado:** {result.recommendation}")

    return "\n".join(parts)


def explain_calibration_short(result: CalibrationResult) -> str:
    """Gera resumo curto (1-2 linhas) da calibracao.

    Args:
        result: Resultado da calibracao.

    Returns:
        Texto curto com parametros e justificativa principal.
    """
    sigma_str = _fmt_sigma(result.n_sigma)

    if result.margin_enabled:
        params = f"N={result.n_periods}, σ={sigma_str}, margem={result.margin_pct*100:.0f}%"
    else:
        params = f"N={result.n_periods}, σ={sigma_str} (sem margem)"

    if not result.margin_enabled:
        reason = "sigma suficiente"
    else:
        reason = "margem complementar necessaria"

    return f"{params} — {reason}, cobertura {result.coverage_pct:.0f}%"


def explain_step_detail(step: CalibrationStep) -> str:
    """Gera explicacao detalhada de uma etapa individual.

    Args:
        step: Etapa da calibracao.

    Returns:
        Texto em pt-BR com detalhes da etapa.
    """
    parts = [f"**{step.name}**", f"Decisao: {step.decision}", f"Justificativa: {step.justification}"]

    # Dados extras por tipo de etapa
    if step.step == 2 and "results_by_sigma" in step.data:
        results = step.data["results_by_sigma"]
        if results:
            parts.append("Cobertura por sigma:")
            for sigma, cov in sorted(results.items()):
                parts.append(f"  - σ={sigma}: {cov:.1%}")

    if step.step == 3 and "results_by_margin" in step.data:
        results = step.data["results_by_margin"]
        if results:
            parts.append("Cobertura por margem:")
            for margin, cov in sorted(results.items()):
                parts.append(f"  - margem={margin:.0%}: {cov:.1%}")

    return "\n".join(parts)


def _append_regime_detail(parts: list[str], profile) -> None:
    """Adiciona detalhes do regime ao texto."""
    if profile.has_structural_break and profile.change_point_date:
        parts.append(
            f"  - Mudanca de patamar em {profile.change_point_date} "
            f"(magnitude: {profile.change_point_magnitude:.2f})"
        )
    if profile.is_seasonal:
        parts.append(
            f"  - Sazonalidade (eta²={profile.seasonality_strength:.2f}, "
            f"amplitude={profile.seasonality_amplitude_ratio:.1%})"
        )
    if profile.is_volatile:
        parts.append(f"  - Volatil (CV={profile.cv:.2f})")
    if profile.has_trend:
        parts.append(
            f"  - Tendencia (slope={profile.drift_slope:.4f}, "
            f"R²={profile.drift_r_squared:.2f})"
        )
    if profile.is_asymmetric:
        parts.append(f"  - Assimetrica (skew={profile.skewness:.2f})")
    if profile.is_zero_inflated:
        parts.append(f"  - Zero-inflated ({profile.zero_pct:.0f}% zeros)")
    if profile.is_sparse:
        parts.append(f"  - Esparsa ({profile.null_pct:.0f}% nulos)")


def _fmt_sigma(sigma: float) -> str:
    """Formata sigma como inteiro quando possivel."""
    return str(int(sigma)) if sigma == int(sigma) else f"{sigma:.1f}"
