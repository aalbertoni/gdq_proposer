"""Gerador de regras GDQ com filtro WHERE via CustomSql.

Converte regras built-in (Mean, StdDev, RowCount, Completeness, etc.)
para CustomSql equivalentes com clausula WHERE.

Suporta dois cenarios:
- Filtro de data: WHERE filtrando por data de negocio (has_date_filter)
- Subpopulacao: WHERE filtrando por segmento do dado (ex: TIPO_PRODUTO = 'X')

A conversao preserva o dual guard (sigma OR margem%) no between,
mantendo compatibilidade com avg(last(N)) e std(last(N)).

Validado via Thundera na Fatia 0 (2026-03-26).
"""

from core.gdq_renderer import DualGuardRenderer
from core.models.dual_guard import DualGuardSpec, CUSTOM_SQL_PROFILE
from core.models.enums import MetricRef, RuleType
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import UserOverride
from infra.query_safety import validate_identifier


def _safe_col(proposal_target_column: str | None) -> str:
    """Valida e normaliza nome de coluna para uso em CustomSql."""
    col = proposal_target_column or ""
    if col:
        validate_identifier(col)
    return col.upper()


# Mapeamento: RuleType → função SQL agregada no SELECT
_RULE_TYPE_SQL_FUNC = {
    RuleType.MEAN_DUAL_GUARD: 'avg(cast({col} as double))',
    RuleType.STDDEV_DUAL_GUARD: 'stddev(cast({col} as double))',
    RuleType.ROW_COUNT_DUAL_GUARD: 'cast(count(*) as double)',
}


def generate_filtered_rule(
    proposal: RuleProposal,
    date_filter_where: str,
    overrides: UserOverride | None = None,
) -> str | None:
    """Gera regra GDQ com filtro de data via CustomSql.

    Converte regras built-in para CustomSql com WHERE. Se o tipo de regra
    não suporta conversão (ex: IsPrimaryKey), retorna None.

    Args:
        proposal: Proposta de regra original.
        date_filter_where: Expressão WHERE Spark (sem keyword WHERE).
            Ex: "ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')"
        overrides: Ajustes manuais do usuário.

    Returns:
        String GDQ com CustomSql + WHERE, ou None se não aplicável.
    """
    rt = proposal.rule_type

    if rt in _RULE_TYPE_SQL_FUNC:
        return _convert_dual_guard(proposal, date_filter_where, overrides)
    elif rt == RuleType.COMPLETENESS:
        return _convert_completeness(proposal, date_filter_where, overrides)
    elif rt == RuleType.ALLOWED_VALUES:
        return _convert_allowed_values(proposal, date_filter_where, overrides)
    elif rt == RuleType.DISTINCT_COUNT_EXACT:
        return _convert_distinct_count(proposal, date_filter_where, overrides)
    elif rt == RuleType.DISTINCT_COUNT_RANGE:
        return _convert_distinct_count_range(proposal, date_filter_where, overrides)
    elif rt in (
        RuleType.CATEGORY_FREQUENCY_STATIC,
        RuleType.CATEGORY_FREQUENCY_DYNAMIC,
        RuleType.CATEGORY_FREQUENCY_HYBRID,
    ):
        return _convert_category_frequency(proposal, date_filter_where, overrides)
    elif rt == RuleType.IS_PRIMARY_KEY:
        return None  # IsPrimaryKey avalia tabela inteira — sem filtro
    elif rt == RuleType.UNIQUENESS_CUSTOM_SQL:
        return None  # Unicidade avalia tabela inteira
    elif rt == RuleType.NUMERIC_PERCENTILE_BAND:
        return _convert_percentile(proposal, date_filter_where, overrides)
    else:
        return None


def generate_rule_with_where(
    proposal: RuleProposal,
    where_clause: str,
    overrides: UserOverride | None = None,
) -> str | None:
    """Gera regra GDQ com clausula WHERE arbitraria via CustomSql.

    Generaliza generate_filtered_rule para qualquer WHERE — filtro de data,
    subpopulacao, ou combinacao de ambos.

    Args:
        proposal: Proposta de regra original.
        where_clause: Expressao WHERE (sem keyword WHERE).
            Ex: "TIPO_PRODUTO = 'CONSIGNADO'"
            Ex: "REGIAO = 'SUL' AND STATUS = 'ATIVO'"
        overrides: Ajustes manuais do usuario.

    Returns:
        String GDQ com CustomSql + WHERE, ou None se nao aplicavel.
    """
    return generate_filtered_rule(proposal, where_clause, overrides)


def _build_select_with_where(sql_select: str, date_filter_where: str) -> str:
    """Monta a expressão SQL interna do CustomSql com WHERE."""
    return f"{sql_select} from primary where {date_filter_where}"


def _convert_dual_guard(
    proposal: RuleProposal,
    date_filter_where: str,
    overrides: UserOverride | None,
) -> str:
    """Converte Mean/StdDev/RowCount dual guard para CustomSql com WHERE."""
    col = _safe_col(proposal.target_column)
    rt = proposal.rule_type

    # Build SELECT expression
    if rt == RuleType.ROW_COUNT_DUAL_GUARD:
        sql_select = "select cast(count(*) as double)"
    else:
        template = _RULE_TYPE_SQL_FUNC[rt]
        sql_select = f"select {template.format(col=col)}"

    sql_inner = _build_select_with_where(sql_select, date_filter_where)

    # Resolve parameters
    n_periods = proposal.baseline_window or 30
    n_sigma = proposal.baseline_n_sigma or 2.0
    margin_pct = proposal.baseline_margin_pct or 0.10
    margin_enabled = proposal.margin_enabled
    buffer = 0.01

    if overrides:
        if overrides.custom_n_periods is not None:
            n_periods = overrides.custom_n_periods
        if overrides.custom_n_sigma is not None:
            n_sigma = overrides.custom_n_sigma
        if overrides.custom_margin_pct is not None:
            margin_pct = overrides.custom_margin_pct
        if overrides.margin_enabled is not None:
            margin_enabled = overrides.margin_enabled

    # RowCount: no buffer, K as float
    if rt == RuleType.ROW_COUNT_DUAL_GUARD:
        buffer = 0

    spec = DualGuardSpec(
        metric=MetricRef.CUSTOM_SQL,
        target="",
        n_periods=n_periods,
        n_sigma=n_sigma,
        margin_pct=margin_pct,
        margin_enabled=margin_enabled,
        buffer=buffer,
        custom_sql_expression=sql_inner,
    )
    renderer = DualGuardRenderer()
    return renderer.render(spec)


def _convert_completeness(
    proposal: RuleProposal,
    date_filter_where: str,
    overrides: UserOverride | None,
) -> str:
    """Converte Completeness para CustomSql count(col)/count(*) com WHERE."""
    col = _safe_col(proposal.target_column)
    threshold = proposal.suggested_lower or 1.0
    if overrides and overrides.custom_lower is not None:
        threshold = overrides.custom_lower

    sql_inner = _build_select_with_where(
        f'select cast(count({col}) as double) / nullif(count(*), 0)',
        date_filter_where,
    )
    return f'CustomSql "{sql_inner}" >= {threshold:.2f}'


def _convert_allowed_values(
    proposal: RuleProposal,
    date_filter_where: str,
    overrides: UserOverride | None,
) -> str:
    """Converte AllowedValues para CustomSql count de valores fora do domínio com WHERE."""
    col = _safe_col(proposal.target_column)
    values = proposal.suggested_values or []
    if overrides and overrides.custom_values is not None:
        values = overrides.custom_values

    # Build IN list
    formatted = []
    for v in values:
        s = str(v)
        if s.upper() == "NULL":
            formatted.append("NULL")
        else:
            try:
                float(s)
                formatted.append(s)
            except (ValueError, TypeError):
                formatted.append(f"'{s}'")

    in_list = ", ".join(formatted)
    # Count rows outside allowed values — should be 0
    sql_inner = _build_select_with_where(
        f'select cast(count(case when cast({col} as varchar) not in ({in_list}) then 1 end) as double)',
        date_filter_where,
    )
    return f'CustomSql "{sql_inner}" = 0'


def _convert_distinct_count(
    proposal: RuleProposal,
    date_filter_where: str,
    overrides: UserOverride | None,
) -> str:
    """Converte DistinctValuesCount exato para CustomSql com WHERE."""
    col = _safe_col(proposal.target_column)
    count = int(proposal.suggested_lower) if proposal.suggested_lower else 0
    if overrides and overrides.custom_lower is not None:
        count = int(overrides.custom_lower)

    sql_inner = _build_select_with_where(
        f'select cast(count(distinct {col}) as double)',
        date_filter_where,
    )
    return f'CustomSql "{sql_inner}" = {count}'


def _convert_distinct_count_range(
    proposal: RuleProposal,
    date_filter_where: str,
    overrides: UserOverride | None,
) -> str:
    """Converte DistinctValuesCount range para CustomSql com WHERE."""
    col = _safe_col(proposal.target_column)
    lower = proposal.suggested_lower or 0
    upper = proposal.suggested_upper or 999999
    if overrides:
        if overrides.custom_lower is not None:
            lower = overrides.custom_lower
        if overrides.custom_upper is not None:
            upper = overrides.custom_upper

    sql_inner = _build_select_with_where(
        f'select cast(count(distinct {col}) as double)',
        date_filter_where,
    )
    return (
        f'(CustomSql "{sql_inner}" >= {int(lower)}) AND '
        f'(CustomSql "{sql_inner}" <= {int(upper)})'
    )


def _convert_category_frequency(
    proposal: RuleProposal,
    date_filter_where: str,
    overrides: UserOverride | None,
) -> str:
    """Converte Category Frequency (static/dynamic/hybrid) para CustomSql com WHERE."""
    col = _safe_col(proposal.target_column)
    value = proposal.category_value or ""
    athena_type = proposal.target_column_type or "string"

    # Build the frequency SQL with WHERE
    if athena_type in ("bigint", "int", "integer", "smallint", "tinyint", "double", "float", "decimal"):
        cast_expr = f'cast({col} as varchar)'
        val_compare = f"'{value}'"
    else:
        cast_expr = col
        val_compare = f"'{value}'"

    freq_sql = (
        f"select cast(sum(case when {cast_expr} = {val_compare} then 1 else 0 end) as double) "
        f"* 100.0 / count(*)"
    )
    sql_inner = _build_select_with_where(freq_sql, date_filter_where)

    rt = proposal.rule_type

    if rt == RuleType.CATEGORY_FREQUENCY_STATIC:
        lower = proposal.suggested_lower or 0.0
        upper = proposal.suggested_upper or 100.0
        if overrides:
            if overrides.custom_lower is not None:
                lower = overrides.custom_lower
            if overrides.custom_upper is not None:
                upper = overrides.custom_upper
        return (
            f'(CustomSql "{sql_inner}" >= {lower:.4f}) AND '
            f'(CustomSql "{sql_inner}" <= {upper:.4f})'
        )
    else:
        # Dynamic / Hybrid — use dual guard renderer
        n_periods = proposal.baseline_window or 30
        n_sigma = proposal.baseline_n_sigma or 2.0
        margin_pct = proposal.baseline_margin_pct or 0.10
        margin_enabled = proposal.margin_enabled

        if overrides:
            if overrides.custom_n_periods is not None:
                n_periods = overrides.custom_n_periods
            if overrides.custom_n_sigma is not None:
                n_sigma = overrides.custom_n_sigma
            if overrides.custom_margin_pct is not None:
                margin_pct = overrides.custom_margin_pct
            if overrides.margin_enabled is not None:
                margin_enabled = overrides.margin_enabled

        spec = DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            target="",
            n_periods=n_periods,
            n_sigma=n_sigma,
            margin_pct=margin_pct,
            margin_enabled=margin_enabled,
            buffer=0.01,
            custom_sql_expression=sql_inner,
            floor_pct=getattr(proposal, "floor_pct", 0.0) or 0.0,
            ceiling_pct=getattr(proposal, "ceiling_pct", 100.0) or 100.0,
        )
        renderer = DualGuardRenderer()
        return renderer.render(spec)


def _convert_percentile(
    proposal: RuleProposal,
    date_filter_where: str,
    overrides: UserOverride | None,
) -> str:
    """Converte percentile band para CustomSql com WHERE."""
    col = _safe_col(proposal.target_column)
    # Use approx_percentile for the specific quantile
    quantile = getattr(proposal, "percentile_quantile", 0.99) or 0.99

    n_periods = proposal.baseline_window or 30
    n_sigma = proposal.baseline_n_sigma or 3.0
    margin_pct = proposal.baseline_margin_pct or 0.03
    margin_enabled = proposal.margin_enabled
    buffer = 0.01

    if overrides:
        if overrides.custom_n_periods is not None:
            n_periods = overrides.custom_n_periods
        if overrides.custom_n_sigma is not None:
            n_sigma = overrides.custom_n_sigma
        if overrides.custom_margin_pct is not None:
            margin_pct = overrides.custom_margin_pct
        if overrides.margin_enabled is not None:
            margin_enabled = overrides.margin_enabled

    sql_inner = _build_select_with_where(
        f'select approx_percentile(cast({col} as double), {quantile})',
        date_filter_where,
    )

    spec = DualGuardSpec(
        metric=MetricRef.CUSTOM_SQL,
        target="",
        n_periods=n_periods,
        n_sigma=n_sigma,
        margin_pct=margin_pct,
        margin_enabled=margin_enabled,
        buffer=buffer,
        custom_sql_expression=sql_inner,
    )
    renderer = DualGuardRenderer()
    return renderer.render(spec)
