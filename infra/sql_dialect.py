"""
Adaptador de sintaxe SQL entre Athena (Presto/Trino) e DuckDB.

A maioria das queries é idêntica. Este módulo trata as poucas
funções que diferem, permitindo que os templates Jinja2 sejam
agnósticos ao backend.
"""

from enum import Enum


class SQLDialect(str, Enum):
    ATHENA = "athena"
    DUCKDB = "duckdb"


# Mapeamento de funções que diferem entre Athena e DuckDB
DIALECT_FUNCTIONS: dict[str, dict[SQLDialect, str]] = {
    "APPROX_PERCENTILE": {
        SQLDialect.ATHENA: "APPROX_PERCENTILE({col}, ARRAY[{quantiles}])",
        SQLDialect.DUCKDB: "QUANTILE_CONT({col}, [{quantiles}])",
    },
    "APPROX_DISTINCT": {
        SQLDialect.ATHENA: "APPROX_DISTINCT({col})",
        SQLDialect.DUCKDB: "APPROX_COUNT_DISTINCT({col})",
    },
    "STDDEV": {
        SQLDialect.ATHENA: "STDDEV({expr})",
        SQLDialect.DUCKDB: "STDDEV_SAMP({expr})",
    },
    "DATE_SUBTRACT_DAYS": {
        SQLDialect.ATHENA: "DATE_ADD('day', -{n}, CURRENT_DATE)",
        SQLDialect.DUCKDB: "CURRENT_DATE - INTERVAL '{n}' DAY",
    },
    "TABLE_REF": {
        SQLDialect.ATHENA: '"{schema}"."{table}"',
        SQLDialect.DUCKDB: '"{table}"',
    },
}


def adapt_function(func_name: str, dialect: SQLDialect, **kwargs) -> str:
    """Retorna a expressão SQL correta para o dialeto.

    Args:
        func_name: Nome da função no dicionário DIALECT_FUNCTIONS.
        dialect: Dialeto alvo (ATHENA ou DUCKDB).
        **kwargs: Parâmetros para interpolação no template.

    Returns:
        String SQL formatada para o dialeto.

    Raises:
        KeyError: Se func_name não existe em DIALECT_FUNCTIONS.
    """
    template = DIALECT_FUNCTIONS[func_name][dialect]
    return template.format(**kwargs)
