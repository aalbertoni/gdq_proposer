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
) -> str:
    """Gera predicado SQL de pruning fisico sem funcao sobre a coluna.

    Args:
        partition_column: Nome da coluna de particao.
        partition_format: strftime format da coluna string, ou None se tipo nativo.
        cutoff: Data de corte calculada.
        dialect: Dialeto SQL (Athena ou DuckDB).

    Returns:
        Predicado SQL como string. Ex: "dt_ref" >= '2026-02-18'
    """
    col = f'"{partition_column}"'

    if partition_format is None:
        # Tipo nativo (date/timestamp) — comparacao com DATE literal
        if dialect == SQLDialect.DUCKDB:
            return f"{col} >= TRY_CAST('{cutoff.isoformat()}' AS DATE)"
        return f"{col} >= DATE '{cutoff.isoformat()}'"

    # String — formatar cutoff no layout fisico da particao
    formatted = cutoff.strftime(partition_format)
    return f"{col} >= '{formatted}'"
