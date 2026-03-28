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
    """Gera predicado hierarquico OR/AND para particoes multi-coluna.

    Para colunas hierarquicas (ano/mes/dia), um predicado AND simples
    como '"ano" >= 2026 AND "mes" >= 2 AND "dia" >= 23' e incorreto
    porque exclui 2026-03-01 (dia=1 < 23).

    O predicado correto usa OR de clausulas com prefixo de igualdade:
      ("ano" > 2026)
      OR ("ano" = 2026 AND "mes" > 2)
      OR ("ano" = 2026 AND "mes" = 2 AND "dia" >= 23)

    Para uma unica coluna, retorna predicado simples (sem OR).

    Args:
        partition_columns: Lista de colunas de particao (ordem hierarquica).
        partition_formats: Formato por coluna (chave=coluna, valor=strftime ou None).
        partition_is_integer_map: Tipo por coluna (chave=coluna, valor=True se inteiro).
        cutoff: Data de corte calculada.
        dialect: Dialeto SQL (Athena ou DuckDB).

    Returns:
        Predicado SQL combinado, ou "" se lista vazia.
    """
    if not partition_columns:
        return ""

    # Single column: simple predicate (no OR needed)
    if len(partition_columns) == 1:
        col = partition_columns[0]
        return build_partition_predicate(
            col, partition_formats.get(col), cutoff,
            dialect=dialect, is_integer=partition_is_integer_map.get(col, False),
        )

    # Multi-column: build value literals for each column
    col_literals = []
    for col in partition_columns:
        fmt = partition_formats.get(col)
        is_int = partition_is_integer_map.get(col, False)
        quoted_col = f'"{col}"'
        if fmt is None:
            # Native date — use DATE literal
            if dialect == SQLDialect.DUCKDB:
                literal = f"TRY_CAST('{cutoff.isoformat()}' AS DATE)"
            else:
                literal = f"DATE '{cutoff.isoformat()}'"
        else:
            formatted = cutoff.strftime(fmt)
            literal = formatted if is_int else f"'{formatted}'"
        col_literals.append((quoted_col, literal))

    # Build hierarchical OR/AND predicate:
    # For N columns, generate N clauses:
    #   clause_0: col_0 > val_0                          (strictly greater on first)
    #   clause_1: col_0 = val_0 AND col_1 > val_1        (equal prefix, then strictly greater)
    #   ...
    #   clause_N-1: col_0 = val_0 AND ... AND col_N-1 >= val_N-1  (equal prefix, then >=)
    clauses = []
    n = len(col_literals)
    for i in range(n):
        parts = []
        # Equality prefix for columns before i
        for j in range(i):
            col_q, lit = col_literals[j]
            parts.append(f"{col_q} = {lit}")
        # Current column: strict > for all except last (which uses >=)
        col_q, lit = col_literals[i]
        if i < n - 1:
            parts.append(f"{col_q} > {lit}")
        else:
            parts.append(f"{col_q} >= {lit}")
        clauses.append("(" + " AND ".join(parts) + ")")

    return "(" + " OR ".join(clauses) + ")"
