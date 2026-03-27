"""Builder de expressões de filtro de data para regras GDQ (Spark SQL).

Gera a cláusula WHERE usada em regras CustomSql quando a coluna de data
de negócio é diferente da partição (cenário FULL_SNAPSHOT).

O engine GDQ roda sobre Spark, então as expressões usam sintaxe Spark SQL:
- date_format(current_date(), 'yyyyMM')
- add_months(current_date(), -N)
- cast(... as int)
"""

from core.models.enums import (
    DateFilterGranularity,
    DateReferenceStrategy,
)


# Mapeamento: (granularidade, tipo_coluna) → formato Spark para date_format()
_SPARK_DATE_FORMATS: dict[DateFilterGranularity, str] = {
    DateFilterGranularity.DAY: "yyyyMMdd",
    DateFilterGranularity.MONTH: "yyyyMM",
    DateFilterGranularity.YEAR: "yyyy",
}

# Mapeamento: granularidade → formato display para o usuário
GRANULARITY_LABELS: dict[DateFilterGranularity, str] = {
    DateFilterGranularity.NONE: "Sem filtro (snapshot inteiro)",
    DateFilterGranularity.DAY: "Dia (YYYYMMDD)",
    DateFilterGranularity.MONTH: "Mes (YYYYMM)",
    DateFilterGranularity.YEAR: "Ano (YYYY)",
}

STRATEGY_LABELS: dict[DateReferenceStrategy, str] = {
    DateReferenceStrategy.CURRENT: "Periodo corrente",
    DateReferenceStrategy.LAG_N: "Defasagem fixa (N periodos atras)",
    DateReferenceStrategy.MAX_VALUE: "Ultimo valor disponivel (max)",
}


def build_gdq_date_filter_expr(
    column: str,
    granularity: DateFilterGranularity,
    strategy: DateReferenceStrategy,
    lag: int = 0,
    column_is_integer: bool = False,
    custom_spark_format: str | None = None,
) -> str | None:
    """Constrói a expressão WHERE Spark para filtro de data nas regras GDQ.

    Args:
        column: Nome da coluna de data (ex: ANO_MES_RFRC_CRED).
        granularity: Granularidade do filtro (DAY, MONTH, YEAR, NONE).
        strategy: Estratégia de referência temporal.
        lag: Defasagem em períodos (usado quando strategy=LAG_N).
        column_is_integer: True se a coluna é inteira (ex: 202603 int).
        custom_spark_format: Formato Spark customizado (override do default).

    Returns:
        Expressão WHERE completa (sem a keyword WHERE), ou None se NONE.
    """
    if granularity == DateFilterGranularity.NONE:
        return None

    if strategy == DateReferenceStrategy.MAX_VALUE:
        return f"{column} = (select max({column}) from primary)"

    spark_fmt = custom_spark_format or _SPARK_DATE_FORMATS[granularity]
    date_ref = _build_date_reference(granularity, strategy, lag, spark_fmt)

    if column_is_integer:
        return f"{column} = cast({date_ref} as int)"
    return f"{column} = {date_ref}"


def _build_date_reference(
    granularity: DateFilterGranularity,
    strategy: DateReferenceStrategy,
    lag: int,
    spark_fmt: str,
) -> str:
    """Constrói a expressão Spark que gera o valor de referência temporal.

    Returns:
        Expressão Spark (ex: "date_format(current_date(), 'yyyyMM')").
    """
    if strategy == DateReferenceStrategy.CURRENT:
        return f"date_format(current_date(), '{spark_fmt}')"

    if strategy == DateReferenceStrategy.LAG_N:
        if granularity == DateFilterGranularity.MONTH:
            return f"date_format(add_months(current_date(), -{lag}), '{spark_fmt}')"
        elif granularity == DateFilterGranularity.YEAR:
            # Subtract N years via add_months(-N*12)
            return f"date_format(add_months(current_date(), -{lag * 12}), '{spark_fmt}')"
        else:  # DAY
            return f"date_format(date_sub(current_date(), {lag}), '{spark_fmt}')"

    # Fallback
    return f"date_format(current_date(), '{spark_fmt}')"


def explain_date_filter(
    column: str,
    granularity: DateFilterGranularity,
    strategy: DateReferenceStrategy,
    lag: int = 0,
) -> str:
    """Gera explicação em pt-BR do filtro de data configurado.

    Útil para exibição na UI e warnings sobre frequência de execução.
    """
    if granularity == DateFilterGranularity.NONE:
        return "Sem filtro de data — regras avaliam o snapshot inteiro."

    gran_label = {
        DateFilterGranularity.DAY: "dia",
        DateFilterGranularity.MONTH: "mes",
        DateFilterGranularity.YEAR: "ano",
    }[granularity]

    if strategy == DateReferenceStrategy.MAX_VALUE:
        return (
            f"Regras filtram por `{column}` = ultimo valor disponivel (max). "
            f"O GDQ avalia apenas os registros do {gran_label} mais recente na tabela."
        )

    if strategy == DateReferenceStrategy.CURRENT:
        return (
            f"Regras filtram por `{column}` = {gran_label} corrente. "
            f"O GDQ avalia apenas os registros do {gran_label} atual (baseado em current_date)."
        )

    if strategy == DateReferenceStrategy.LAG_N:
        return (
            f"Regras filtram por `{column}` = {lag} {gran_label}(s) atras. "
            f"O GDQ avalia registros com defasagem de {lag} {gran_label}(s) em relacao a hoje."
        )

    return ""


def explain_execution_frequency_warning(
    granularity: DateFilterGranularity,
) -> str:
    """Gera warning sobre a frequência de execução do GDQ vs granularidade dos dados.

    Importante: se o GDQ roda mais frequentemente que os dados mudam,
    avg(last(N)) acumula valores idênticos e std→0.
    """
    if granularity == DateFilterGranularity.NONE:
        return ""

    gran_label = {
        DateFilterGranularity.DAY: "diaria",
        DateFilterGranularity.MONTH: "mensal",
        DateFilterGranularity.YEAR: "anual",
    }[granularity]

    freq_match = {
        DateFilterGranularity.DAY: "diariamente",
        DateFilterGranularity.MONTH: "mensalmente (ou a cada atualizacao mensal)",
        DateFilterGranularity.YEAR: "anualmente",
    }[granularity]

    return (
        f"**Frequencia de execucao:** A granularidade do filtro e {gran_label}. "
        f"Para que `avg(last(N))` e `std(last(N))` capturem variacao real entre periodos, "
        f"o GDQ deve executar **{freq_match}**. "
        f"Se o GDQ rodar mais frequentemente que os dados mudam, "
        f"o historico acumula valores identicos (std≈0) e a banda fica super apertada, "
        f"causando falsos positivos na proxima atualizacao.\n\n"
        f"**`last(N)` recomendado:** N deve corresponder a quantidade de periodos "
        f"distintos que voce quer comparar. Ex: para dados mensais com 2 anos de "
        f"historico, use `last(24)` (24 meses). Para dados diarios, `last(30)` (30 dias)."
    )
