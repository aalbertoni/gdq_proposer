"""Geracao de predicados de partition pruning fisico.

Separa completamente o pruning fisico (custo) da expressao de data
analitica (corretude temporal). O predicado gerado NUNCA aplica funcao
sobre a coluna de particao — usa comparacao direta com literal formatado.

Suporta:
- Particoes string lexicograficas: %Y-%m-%d, %Y%m%d, %Y%m, %Y.%m.%d
- Particoes com tipo nativo (date/timestamp): comparacao com DATE literal
- DuckDB (testes): usa literal de string com TRY_CAST
"""

from datetime import date, timedelta

from infra.sql_dialect import SQLDialect


def compute_cutoff_date(reference_date: str | None, lookback_days: int) -> date:
    """Calcula a data de corte para pruning.

    Args:
        reference_date: Data ancora no formato YYYY-MM-DD, ou None para hoje.
        lookback_days: Dias de lookback a subtrair.

    Returns:
        Data de corte (reference - lookback).
    """
    if reference_date:
        ref = date.fromisoformat(reference_date)
    else:
        ref = date.today()
    return ref - timedelta(days=lookback_days)


def build_partition_predicate(
    partition_column: str,
    partition_format: str | None,
    cutoff: date,
    dialect: SQLDialect = SQLDialect.ATHENA,
    is_integer: bool = False,
) -> str:
    """Gera predicado SQL de pruning fisico sem funcao sobre a coluna.

    Args:
        partition_column: Nome da coluna de particao.
        partition_format: strftime format da coluna string/integer, ou None se tipo nativo.
        cutoff: Data de corte calculada.
        dialect: Dialeto SQL (Athena ou DuckDB).
        is_integer: Se True, gera literal numerico sem aspas.

    Returns:
        Predicado SQL como string. Ex: "dt_ref" >= '2026-02-18' ou "dt_ref" >= 20260218
    """
    col = f'"{partition_column}"'

    if partition_format is None:
        # Tipo nativo (date/timestamp) — comparacao com DATE literal
        if dialect == SQLDialect.DUCKDB:
            return f"{col} >= TRY_CAST('{cutoff.isoformat()}' AS DATE)"
        return f"{col} >= DATE '{cutoff.isoformat()}'"

    # Formatar cutoff no layout fisico da particao
    formatted = cutoff.strftime(partition_format)

    if is_integer:
        # Integer — literal numerico sem aspas
        return f"{col} >= {formatted}"

    # String — literal com aspas
    return f"{col} >= '{formatted}'"


def build_multi_column_predicate(
    partition_columns: list[str],
    partition_formats: dict[str, str | None],
    partition_is_integer_map: dict[str, bool],
    cutoff: date,
    dialect: SQLDialect = SQLDialect.ATHENA,
) -> str:
    """Gera predicado AND combinando multiplas colunas de particao.

    Cada coluna gera um predicado individual via build_partition_predicate().
    Predicados sao combinados com AND.

    Args:
        partition_columns: Lista de colunas de particao.
        partition_formats: Formato por coluna (chave=coluna, valor=strftime ou None).
        partition_is_integer_map: Tipo por coluna (chave=coluna, valor=True se inteiro).
        cutoff: Data de corte calculada.
        dialect: Dialeto SQL (Athena ou DuckDB).

    Returns:
        Predicado SQL combinado, ou "" se lista vazia.
    """
    if not partition_columns:
        return ""

    predicates = []
    for col in partition_columns:
        fmt = partition_formats.get(col)
        is_int = partition_is_integer_map.get(col, False)
        pred = build_partition_predicate(col, fmt, cutoff, dialect=dialect, is_integer=is_int)
        predicates.append(pred)

    return " AND ".join(predicates)
