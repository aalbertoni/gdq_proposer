"""
Gerador de explicacoes em linguagem natural para regras GDQ.

Converte RuleProposal em texto legivel para analistas/engenheiros de dados
que nao precisam conhecer a sintaxe GDQ para entender o que a regra faz.

Inclui explicacoes enriquecidas com contexto de regime e trade-offs.
"""

from typing import Optional

from core.models.enums import ConfidenceLevel, RuleType, SeriesRegime
from core.models.rule_evaluation import RuleEvaluation
from core.models.rule_proposal import RuleProposal
from core.models.series_profile import SeriesProfile


def explain_rule(proposal: RuleProposal) -> str:
    """Gera explicacao em linguagem natural para uma proposta de regra.

    Args:
        proposal: Proposta de regra com parametros e backtest.

    Returns:
        Texto em pt-BR explicando o que a regra faz.
    """
    rt = proposal.rule_type

    if rt == RuleType.MEAN_DUAL_GUARD:
        return _explain_mean(proposal)
    elif rt == RuleType.STDDEV_DUAL_GUARD:
        return _explain_stddev(proposal)
    elif rt == RuleType.ROW_COUNT_DUAL_GUARD:
        return _explain_rowcount(proposal)
    elif rt == RuleType.COMPLETENESS:
        return _explain_completeness(proposal)
    elif rt == RuleType.ALLOWED_VALUES:
        return _explain_allowed_values(proposal)
    elif rt == RuleType.DISTINCT_COUNT_EXACT:
        return _explain_distinct_count(proposal)
    elif rt == RuleType.DISTINCT_COUNT_RANGE:
        return _explain_distinct_count_range(proposal)
    elif rt == RuleType.IS_PRIMARY_KEY:
        return _explain_primary_key(proposal)
    elif rt == RuleType.UNIQUENESS_CUSTOM_SQL:
        return _explain_uniqueness_custom_sql(proposal)
    elif rt in (
        RuleType.CATEGORY_FREQUENCY_STATIC,
        RuleType.CATEGORY_FREQUENCY_DYNAMIC,
        RuleType.CATEGORY_FREQUENCY_HYBRID,
    ):
        return _explain_category_frequency(proposal)
    elif rt == RuleType.NUMERIC_PERCENTILE_BAND:
        return _explain_percentile(proposal)
    else:
        return f"Regra customizada para `{proposal.target_column or proposal.target_table}`."


def explain_rule_detail(proposal: RuleProposal) -> str:
    """Gera explicacao detalhada incluindo parametros e resultado do backtest.

    Args:
        proposal: Proposta de regra com parametros e backtest.

    Returns:
        Texto em pt-BR com explicacao + parametros + evidencia.
    """
    parts = []

    # Parametros
    params = _explain_params(proposal)
    if params:
        parts.append("**Parametros:**")
        parts.append(params)

    # Evidencia do backtest
    evidence = _explain_backtest(proposal)
    if evidence:
        if parts:
            parts.append("")
        parts.append("**Evidencia:**")
        parts.append(evidence)

    return "\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Explicacoes por tipo de regra
# ---------------------------------------------------------------------------

def _explain_mean(p: RuleProposal) -> str:
    col = p.target_column
    n = p.baseline_window or 30
    k = p.baseline_n_sigma or 2.0

    base = (
        f"Verifica se a **media** da coluna `{col}` esta dentro do esperado. "
        f"A regra calcula a media dos ultimos **{n} periodos** e aceita o valor se estiver "
        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica"
    )

    if p.margin_enabled:
        margin = (p.baseline_margin_pct or 0.10) * 100
        return (
            f"{base}, "
            f"**ou** dentro de **{margin:.0f}%** da media historica. "
            f"Se qualquer uma das duas bandas for atendida, a regra passa."
        )

    return f"{base}."


def _explain_stddev(p: RuleProposal) -> str:
    col = p.target_column
    n = p.baseline_window or 30
    k = p.baseline_n_sigma or 2.0

    base = (
        f"Verifica se o **desvio padrao** da coluna `{col}` esta dentro do esperado. "
        f"A regra calcula o desvio padrao medio dos ultimos **{n} periodos** e aceita se estiver "
        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica"
    )

    if p.margin_enabled:
        margin = (p.baseline_margin_pct or 0.10) * 100
        return (
            f"{base}, "
            f"**ou** dentro de **{margin:.0f}%** da media historica. "
            f"Detecta se a dispersao dos dados mudou significativamente."
        )

    return f"{base}. Detecta se a dispersao dos dados mudou significativamente."


def _explain_rowcount(p: RuleProposal) -> str:
    table = p.target_table
    n = p.baseline_window or 30
    k = p.baseline_n_sigma or 2.0

    base = (
        f"Verifica se o **volume de linhas** da tabela `{table}` esta dentro do esperado. "
        f"A regra calcula a quantidade media de linhas dos ultimos **{n} periodos** e aceita se estiver "
        f"dentro de **{_fmt_k(k)} desvios padrao** do volume historico"
    )

    if p.margin_enabled:
        margin = (p.baseline_margin_pct or 0.10) * 100
        return (
            f"{base}, "
            f"**ou** dentro de **{margin:.0f}%** do volume historico. "
            f"Detecta cargas com volume anomalo (muito acima ou abaixo)."
        )

    return f"{base}. Detecta cargas com volume anomalo (muito acima ou abaixo)."


def _explain_completeness(p: RuleProposal) -> str:
    col = p.target_column
    threshold = (p.suggested_lower or 1.0) * 100

    return (
        f"Verifica se a coluna `{col}` tem pelo menos **{threshold:.0f}%** dos valores preenchidos "
        f"(nao nulos). Se a porcentagem de valores nao-nulos cair abaixo desse limite, "
        f"a regra falha."
    )


def _explain_allowed_values(p: RuleProposal) -> str:
    col = p.target_column
    values = p.suggested_values or []
    n_values = len(values)
    if n_values <= 10:
        values_str = ", ".join(f"`{v}`" for v in values)
        return (
            f"Verifica se todos os valores da coluna `{col}` estao entre: {values_str}. "
            f"Qualquer valor fora dessa lista faz a regra falhar."
        )
    return (
        f"Verifica se todos os valores da coluna `{col}` estao dentro "
        f"de um dominio de **{n_values} valores** permitidos."
    )


def _explain_distinct_count(p: RuleProposal) -> str:
    col = p.target_column
    count = int(p.suggested_lower) if p.suggested_lower else 0
    return (
        f"Verifica se a coluna `{col}` tem exatamente **{count} valores distintos**. "
        f"Se o numero de distintos mudar (ex: novo codigo, valor removido), a regra falha."
    )


def _explain_primary_key(p: RuleProposal) -> str:
    cols = p.suggested_values or []
    cols_str = ", ".join(f"`{c}`" for c in cols)
    return (
        f"Verifica se a combinacao de colunas ({cols_str}) forma uma **chave primaria** "
        f"(sem duplicatas). Se houver linhas duplicadas, a regra falha."
    )


def _explain_uniqueness_custom_sql(p: RuleProposal) -> str:
    cols = p.suggested_values or []
    if len(cols) == 1:
        cols_str = f"coluna `{cols[0]}`"
    else:
        cols_str = "combinacao de colunas (" + ", ".join(f"`{c}`" for c in cols) + ")"

    return (
        f"Verifica que a {cols_str} e unica (sem duplicatas), "
        f"usando CustomSql. Diferente de IsPrimaryKey, nao exige completude "
        f"(permite nulls)."
    )


def _explain_distinct_count_range(p: RuleProposal) -> str:
    col = p.target_column
    lower = int(p.suggested_lower) if p.suggested_lower else 0
    upper = int(p.suggested_upper) if p.suggested_upper else 0
    return (
        f"Verifica se a coluna `{col}` tem entre **{lower}** e **{upper} valores distintos**. "
        f"Permite variacao natural sem disparar alarme para cada novo valor."
    )


def _explain_percentile(p: RuleProposal) -> str:
    col = p.target_column
    pct_label = p.metric_name.upper() if p.metric_name else "P50"
    n = p.baseline_window or 30
    k = p.baseline_n_sigma or 2.0

    base = (
        f"Verifica se o **{pct_label}** da coluna `{col}` esta dentro do esperado. "
        f"A regra calcula o percentil historico dos ultimos **{n} periodos** e aceita se estiver "
        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica"
    )

    if p.margin_enabled:
        margin = (p.baseline_margin_pct or 0.10) * 100
        return (
            f"{base}, "
            f"**ou** dentro de **{margin:.0f}%** da media historica. "
            f"Detecta mudancas na distribuicao dos dados (caudas)."
        )

    return f"{base}. Detecta mudancas na distribuicao dos dados (caudas)."


def _explain_category_frequency(p: RuleProposal) -> str:
    col = p.target_column
    value = p.category_value
    lower = p.suggested_lower or 0.0
    upper = p.suggested_upper or 100.0
    rt = p.rule_type

    if not value:
        return (
            f"Verifica se a **frequencia relativa** dos valores da coluna `{col}` "
            f"esta dentro do esperado. Detecta mudancas na distribuicao "
            f"(ex: um valor que era 30% passou a ser 10%)."
        )

    if rt == RuleType.CATEGORY_FREQUENCY_DYNAMIC:
        n = p.baseline_window or 30
        k = p.baseline_n_sigma or 2.0
        margin = (p.baseline_margin_pct or 0.10) * 100
        return (
            f"Verifica se a **frequencia** do valor `{value}` na coluna `{col}` "
            f"esta dentro do esperado, usando **banda dinamica** baseada nos "
            f"ultimos **{n} periodos**. Aceita se estiver dentro de "
            f"**{_fmt_k(k)} desvios padrao** da frequencia media historica, "
            f"**ou** dentro de **{margin:.0f}%** da media. "
            f"A regra se adapta automaticamente a evolucao natural da distribuicao."
        )
    elif rt == RuleType.CATEGORY_FREQUENCY_HYBRID:
        n = p.baseline_window or 30
        k = p.baseline_n_sigma or 2.0
        margin = (p.baseline_margin_pct or 0.10) * 100
        floor = p.floor_pct if p.floor_pct is not None else 0.0
        ceiling = p.ceiling_pct if p.ceiling_pct is not None else 100.0
        return (
            f"Verifica se a **frequencia** do valor `{value}` na coluna `{col}` "
            f"esta dentro do esperado, usando **banda dinamica** (ultimos **{n} periodos**, "
            f"**{_fmt_k(k)} sigma** ou **{margin:.0f}%** de margem) "
            f"**com limites absolutos** de **{floor:.1f}%** (piso) a **{ceiling:.1f}%** (teto). "
            f"Combina adaptabilidade do modo dinamico com guardrails fixos de negocio."
        )
    else:
        # STATIC
        return (
            f"Verifica se a **frequencia** do valor `{value}` na coluna `{col}` "
            f"esta entre **{lower:.1f}%** e **{upper:.1f}%** das linhas (limites fixos). "
            f"Se a proporcao cair fora dessa faixa, a regra falha."
        )


# ---------------------------------------------------------------------------
# Parametros e evidencia
# ---------------------------------------------------------------------------

def _explain_params(p: RuleProposal) -> str:
    rt = p.rule_type

    if rt in (
        RuleType.MEAN_DUAL_GUARD,
        RuleType.STDDEV_DUAL_GUARD,
        RuleType.ROW_COUNT_DUAL_GUARD,
        RuleType.NUMERIC_PERCENTILE_BAND,
    ):
        n = p.baseline_window or 30
        k = p.baseline_n_sigma or 2.0
        margin = (p.baseline_margin_pct or 0.10) * 100

        lines = [
            f"- **Janela (N):** {n} periodos",
            f"- **Sigma (K):** {_fmt_k(k)} desvios padrao",
            f"- **Margem:** {margin:.0f}%",
        ]
        return "\n".join(lines)

    elif rt == RuleType.COMPLETENESS:
        threshold = (p.suggested_lower or 1.0) * 100
        return f"- **Limite minimo:** {threshold:.0f}% preenchido"

    elif rt == RuleType.ALLOWED_VALUES:
        values = p.suggested_values or []
        return f"- **Valores permitidos:** {len(values)}"

    elif rt == RuleType.DISTINCT_COUNT_EXACT:
        count = int(p.suggested_lower) if p.suggested_lower else 0
        return f"- **Contagem esperada:** {count} distintos"

    elif rt == RuleType.DISTINCT_COUNT_RANGE:
        lower = int(p.suggested_lower) if p.suggested_lower else 0
        upper = int(p.suggested_upper) if p.suggested_upper else 0
        return f"- **Faixa de distintos:** {lower} a {upper}"

    elif rt == RuleType.CATEGORY_FREQUENCY_STATIC:
        lower = p.suggested_lower or 0.0
        upper = p.suggested_upper or 100.0
        value_str = f" (`{p.category_value}`)" if p.category_value else ""
        return f"- **Faixa{value_str}:** {lower:.1f}% a {upper:.1f}% (limites fixos)"

    elif rt in (RuleType.CATEGORY_FREQUENCY_DYNAMIC, RuleType.CATEGORY_FREQUENCY_HYBRID):
        n = p.baseline_window or 30
        k = p.baseline_n_sigma or 2.0
        margin = (p.baseline_margin_pct or 0.10) * 100
        value_str = f" (`{p.category_value}`)" if p.category_value else ""
        lines = [
            f"- **Valor{value_str}**",
            f"- **Janela (N):** {n} periodos",
            f"- **Sigma (K):** {_fmt_k(k)} desvios padrao",
            f"- **Margem:** {margin:.0f}%",
        ]
        if rt == RuleType.CATEGORY_FREQUENCY_HYBRID:
            floor = p.floor_pct if p.floor_pct is not None else 0.0
            ceiling = p.ceiling_pct if p.ceiling_pct is not None else 100.0
            lines.append(f"- **Piso:** {floor:.1f}%")
            lines.append(f"- **Teto:** {ceiling:.1f}%")
        return "\n".join(lines)

    elif rt == RuleType.IS_PRIMARY_KEY:
        cols = p.suggested_values or []
        return f"- **Colunas:** {', '.join(cols)}"

    elif rt == RuleType.UNIQUENESS_CUSTOM_SQL:
        cols = p.suggested_values or []
        return f"- **Colunas:** {', '.join(cols)}\n- **Tipo:** CustomSql (permite nulls)"

    return ""


def _explain_backtest(p: RuleProposal) -> str:
    bt = p.backtest
    if not bt:
        return ""

    confidence_labels = {
        ConfidenceLevel.HIGH: "Alta — recomendada para producao",
        ConfidenceLevel.MEDIUM: "Media — revisar parametros",
        ConfidenceLevel.LOW: "Baixa — nao recomendada",
    }

    lines = [
        f"- **Cobertura:** {bt.coverage_pct:.1f}% dos periodos historicos passariam na regra",
        f"- **Falsos positivos:** ~{bt.false_positive_proxy} periodo(s) normal(is) seriam reprovado(s)",
        f"- **Estabilidade:** {bt.stability_score:.2f} (1.0 = muito estavel)",
        f"- **Confianca:** {confidence_labels.get(p.confidence, p.confidence.value)}",
    ]

    if bt.has_drift:
        lines.append("- **Atencao:** tendencia (drift) detectada no historico")

    if bt.outlier_periods:
        n_outliers = len(bt.outlier_periods)
        lines.append(f"- **Outliers:** {n_outliers} periodo(s) com valores atipicos")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Explicacoes enriquecidas com regime
# ---------------------------------------------------------------------------

def explain_regime_context(
    proposal: RuleProposal,
    profile: SeriesProfile,
) -> str:
    """Gera texto sobre como o regime da serie afeta esta regra.

    Args:
        proposal: Proposta de regra.
        profile: Perfil de regime da serie.

    Returns:
        Texto em pt-BR com contexto de regime, ou string vazia se STABLE.
    """
    if profile.regime == SeriesRegime.STABLE and not profile.secondary_regimes:
        return ""

    parts: list[str] = []
    parts.append(f"**Regime detectado:** {profile.regime_summary}")

    regime = profile.regime
    rt = proposal.rule_type

    # Contexto especifico por regime + tipo de regra
    if regime == SeriesRegime.STRUCTURAL_BREAK:
        date_str = f" em {profile.change_point_date}" if profile.change_point_date else ""
        parts.append(
            f"A serie apresenta **mudanca de patamar**{date_str}. "
            f"O historico antes da mudanca pode nao representar o padrao atual. "
        )
        if rt in (RuleType.MEAN_DUAL_GUARD, RuleType.STDDEV_DUAL_GUARD):
            parts.append(
                "**Recomendacao:** reduza N para usar apenas dados pos-mudanca, "
                "ou aumente o sigma para acomodar a transicao."
            )

    elif regime == SeriesRegime.TRENDING:
        parts.append(
            f"A serie apresenta **tendencia** (slope={profile.drift_slope:.4f}). "
            f"A media historica pode estar defasada em relacao ao valor atual."
        )
        if rt in (RuleType.MEAN_DUAL_GUARD, RuleType.STDDEV_DUAL_GUARD):
            parts.append(
                "**Recomendacao:** use N menor (10-15) para que a baseline "
                "acompanhe a tendencia, ou aumente a margem."
            )

    elif regime == SeriesRegime.SEASONAL:
        parts.append(
            f"A serie apresenta **sazonalidade** "
            f"(forca={profile.seasonality_strength:.2f}). "
            f"Valores variam ciclicamente ao longo da semana/mes."
        )
        if rt in (RuleType.MEAN_DUAL_GUARD, RuleType.ROW_COUNT_DUAL_GUARD):
            parts.append(
                "**Recomendacao:** use N multiplo de 7 para suavizar "
                "o efeito do dia da semana (ex: N=14, 21, 28)."
            )

    elif regime == SeriesRegime.VOLATILE:
        parts.append(
            f"A serie e **volatil** (CV={profile.cv:.2f}). "
            f"Variacao alta e natural, nao necessariamente anomala."
        )
        if rt in (RuleType.MEAN_DUAL_GUARD, RuleType.STDDEV_DUAL_GUARD):
            parts.append(
                "**Recomendacao:** aumente sigma (3+) ou margem para "
                "evitar falsos positivos. Considere se esta regra "
                "agrega valor para uma serie naturalmente dispersa."
            )

    elif regime == SeriesRegime.ZERO_INFLATED:
        parts.append(
            f"A serie tem **muitos zeros** ({profile.zero_pct:.0f}%). "
            f"A media e distorcida pela concentracao em zero."
        )
        if rt == RuleType.MEAN_DUAL_GUARD:
            parts.append(
                "**Recomendacao:** regra de Mean pode ser inadequada. "
                "Considere Completeness ou uma regra CustomSql que "
                "filtre os zeros antes de calcular."
            )

    elif regime == SeriesRegime.ASYMMETRIC:
        parts.append(
            f"A distribuicao e **assimetrica** (skewness={profile.skewness:.2f}). "
            f"Bandas simetricas podem gerar alertas em apenas um lado."
        )
        if rt == RuleType.MEAN_DUAL_GUARD:
            parts.append(
                "**Recomendacao:** bandas simetricas (sigma) podem ser "
                "demasiado restritivas em um lado e frouxas no outro. "
                "Considere a margem % como guarda complementar."
            )

    elif regime == SeriesRegime.SPARSE:
        parts.append(
            f"A serie tem **muitos valores nulos** ({profile.null_pct:.0f}%). "
            f"Poucas observacoes validas reduzem a confiabilidade."
        )
        parts.append(
            "**Recomendacao:** resultados podem ser imprecisos. "
            "Monitore com cautela e valide com mais dados."
        )

    # Secondary regimes
    for sec in profile.secondary_regimes:
        parts.append(f"- Regime secundario: **{sec.value}** (impacto menor)")

    return "\n".join(parts)


def explain_trade_offs(
    proposal: RuleProposal,
    evaluation: RuleEvaluation,
) -> str:
    """Gera texto sobre trade-offs e riscos da regra.

    Args:
        proposal: Proposta de regra.
        evaluation: Avaliacao enriquecida com 7 dimensoes.

    Returns:
        Texto em pt-BR com analise de trade-offs.
    """
    parts: list[str] = []

    # Regime fit assessment
    if evaluation.regime_fit < 0.5:
        parts.append(
            f"**Adequacao ao regime:** Baixa ({evaluation.regime_fit:.0%}). "
            f"Este tipo de regra pode nao ser o mais indicado para o "
            f"comportamento observado na serie."
        )
    elif evaluation.regime_fit < 0.8:
        parts.append(
            f"**Adequacao ao regime:** Moderada ({evaluation.regime_fit:.0%}). "
            f"A regra pode funcionar, mas parametros precisam de ajuste cuidadoso."
        )

    # FP risk
    if evaluation.fp_risk > 0.30:
        parts.append(
            f"**Risco de falsos positivos:** Alto ({evaluation.fp_risk:.0%}). "
            f"A regra pode gerar alertas frequentes para variacao normal."
        )
    elif evaluation.fp_risk > 0.15:
        parts.append(
            f"**Risco de falsos positivos:** Moderado ({evaluation.fp_risk:.0%}). "
            f"Alguns alertas podem ser espurios."
        )

    # Robustness
    if evaluation.robustness < 0.6:
        parts.append(
            f"**Confiabilidade dos dados:** Baixa ({evaluation.robustness:.0%}). "
            f"Pouco historico ou muitos nulos reduzem a confianca na avaliacao."
        )

    # Coverage vs. band width trade-off
    if evaluation.coverage > 0.95 and evaluation.sensitivity > 0.50:
        parts.append(
            "**Trade-off:** cobertura alta, mas a banda e larga. "
            "A regra cobre quase tudo, incluindo possíveis anomalias."
        )
    elif evaluation.coverage < 0.80 and evaluation.sensitivity < 0.15:
        parts.append(
            "**Trade-off:** banda estreita, mas cobertura baixa. "
            "A regra pode ser muito restritiva para esta serie."
        )

    if not parts:
        return ""

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_k(k: float) -> str:
    """Formata K como inteiro quando possivel."""
    return str(int(k)) if k == int(k) else f"{k:.1f}"
