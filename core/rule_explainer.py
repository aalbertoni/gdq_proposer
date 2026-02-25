"""
Gerador de explicacoes em linguagem natural para regras GDQ.

Converte RuleProposal em texto legivel para analistas/engenheiros de dados
que nao precisam conhecer a sintaxe GDQ para entender o que a regra faz.
"""

from core.models.enums import ConfidenceLevel, RuleType
from core.models.rule_proposal import RuleProposal


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
    elif rt in (
        RuleType.CATEGORY_FREQUENCY_STATIC,
        RuleType.CATEGORY_FREQUENCY_DYNAMIC,
        RuleType.CATEGORY_FREQUENCY_HYBRID,
    ):
        return _explain_category_frequency(proposal)
    else:
        return f"Regra customizada para `{proposal.target_column or proposal.target_table}`."


def explain_rule_detail(proposal: RuleProposal) -> str:
    """Gera explicacao detalhada incluindo parametros e resultado do backtest.

    Args:
        proposal: Proposta de regra com parametros e backtest.

    Returns:
        Texto em pt-BR com explicacao + parametros + evidencia.
    """
    parts = [explain_rule(proposal)]

    # Parametros
    params = _explain_params(proposal)
    if params:
        parts.append("")
        parts.append("**Parametros:**")
        parts.append(params)

    # Evidencia do backtest
    evidence = _explain_backtest(proposal)
    if evidence:
        parts.append("")
        parts.append("**Evidencia:**")
        parts.append(evidence)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Explicacoes por tipo de regra
# ---------------------------------------------------------------------------

def _explain_mean(p: RuleProposal) -> str:
    col = p.target_column
    n = p.baseline_window or 30
    k = p.baseline_n_sigma or 2.0
    margin = (p.baseline_margin_pct or 0.10) * 100

    return (
        f"Verifica se a **media** da coluna `{col}` esta dentro do esperado. "
        f"A regra calcula a media dos ultimos **{n} periodos** e aceita o valor se estiver "
        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica, "
        f"**ou** dentro de **{margin:.0f}%** da media historica. "
        f"Se qualquer uma das duas bandas for atendida, a regra passa."
    )


def _explain_stddev(p: RuleProposal) -> str:
    col = p.target_column
    n = p.baseline_window or 30
    k = p.baseline_n_sigma or 2.0
    margin = (p.baseline_margin_pct or 0.10) * 100

    return (
        f"Verifica se o **desvio padrao** da coluna `{col}` esta dentro do esperado. "
        f"A regra calcula o desvio padrao medio dos ultimos **{n} periodos** e aceita se estiver "
        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica, "
        f"**ou** dentro de **{margin:.0f}%** da media historica. "
        f"Detecta se a dispersao dos dados mudou significativamente."
    )


def _explain_rowcount(p: RuleProposal) -> str:
    table = p.target_table
    n = p.baseline_window or 30
    k = p.baseline_n_sigma or 2.0
    margin = (p.baseline_margin_pct or 0.10) * 100

    return (
        f"Verifica se o **volume de linhas** da tabela `{table}` esta dentro do esperado. "
        f"A regra calcula a quantidade media de linhas dos ultimos **{n} periodos** e aceita se estiver "
        f"dentro de **{_fmt_k(k)} desvios padrao** do volume historico, "
        f"**ou** dentro de **{margin:.0f}%** do volume historico. "
        f"Detecta cargas com volume anomalo (muito acima ou abaixo)."
    )


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


def _explain_distinct_count_range(p: RuleProposal) -> str:
    col = p.target_column
    lower = int(p.suggested_lower) if p.suggested_lower else 0
    upper = int(p.suggested_upper) if p.suggested_upper else 0
    return (
        f"Verifica se a coluna `{col}` tem entre **{lower}** e **{upper} valores distintos**. "
        f"Permite variacao natural sem disparar alarme para cada novo valor."
    )


def _explain_category_frequency(p: RuleProposal) -> str:
    col = p.target_column
    value = p.category_value
    lower = p.suggested_lower or 0.0
    upper = p.suggested_upper or 100.0
    if value:
        return (
            f"Verifica se a **frequencia** do valor `{value}` na coluna `{col}` "
            f"esta entre **{lower:.1f}%** e **{upper:.1f}%** das linhas. "
            f"Se a proporcao cair fora dessa faixa, a regra falha."
        )
    return (
        f"Verifica se a **frequencia relativa** dos valores da coluna `{col}` "
        f"esta dentro do esperado. Detecta mudancas na distribuicao "
        f"(ex: um valor que era 30% passou a ser 10%)."
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

    elif rt in (
        RuleType.CATEGORY_FREQUENCY_STATIC,
        RuleType.CATEGORY_FREQUENCY_DYNAMIC,
        RuleType.CATEGORY_FREQUENCY_HYBRID,
    ):
        lower = p.suggested_lower or 0.0
        upper = p.suggested_upper or 100.0
        value_str = f" (`{p.category_value}`)" if p.category_value else ""
        return f"- **Faixa{value_str}:** {lower:.1f}% a {upper:.1f}%"

    elif rt == RuleType.IS_PRIMARY_KEY:
        cols = p.suggested_values or []
        return f"- **Colunas:** {', '.join(cols)}"

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
# Helpers
# ---------------------------------------------------------------------------

def _fmt_k(k: float) -> str:
    """Formata K como inteiro quando possivel."""
    return str(int(k)) if k == int(k) else f"{k:.1f}"
