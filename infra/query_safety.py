"""
Validação de segurança para queries SQL.

Garante que identificadores, lookback e filtros customizados
não introduzam SQL injection ou operações destrutivas.
"""

import re
from enum import Enum


# Whitelist de caracteres permitidos em identificadores SQL
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Limites padrão
MAX_LOOKBACK_DAYS = 365
MAX_LOOKBACK_PERIODS = 100

# Palavras-chave bloqueadas em filtros customizados (case-insensitive)
_BLOCKED_KEYWORDS = [
    "UNION", "INSERT", "DELETE", "DROP", "ALTER",
    "CREATE", "UPDATE", "EXEC", "TRUNCATE", "GRANT",
    "REVOKE", "MERGE",
]
_BLOCKED_KEYWORDS_PATTERN = re.compile(
    r"\b(" + "|".join(_BLOCKED_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Tokens perigosos (não precisam de word boundary)
_BLOCKED_TOKENS = [";", "--", "/*"]


class LookbackMode(str, Enum):
    DAYS = "days"
    PERIODS = "periods"


def validate_identifier(name: str) -> str:
    """Valida e retorna identificador seguro.

    Args:
        name: Nome de schema, tabela ou coluna.

    Returns:
        O próprio nome, se válido.

    Raises:
        ValueError: Se o identificador contém caracteres não permitidos.
    """
    if not name or not IDENTIFIER_PATTERN.match(name):
        raise ValueError(f"Identificador inválido: {name!r}")
    return name


def validate_lookback(value: int, mode: LookbackMode = LookbackMode.DAYS) -> int:
    """Garante que lookback está dentro dos limites.

    Args:
        value: Valor de lookback.
        mode: DAYS ou PERIODS.

    Returns:
        O próprio valor, se válido.

    Raises:
        ValueError: Se valor é negativo, zero ou excede o limite.
    """
    if value <= 0:
        raise ValueError(f"Lookback deve ser positivo, recebido: {value}")

    limit = MAX_LOOKBACK_DAYS if mode == LookbackMode.DAYS else MAX_LOOKBACK_PERIODS
    if value > limit:
        raise ValueError(
            f"Lookback {mode.value}={value} excede limite máximo de {limit}"
        )
    return value


# Padrão estrito para datas YYYY-MM-DD
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_reference_date(value: str) -> str:
    """Valida que reference_date esta no formato YYYY-MM-DD.

    Args:
        value: Data como string.

    Returns:
        O proprio valor, se valido.

    Raises:
        ValueError: Se formato invalido.
    """
    if not _DATE_PATTERN.match(value):
        raise ValueError(
            f"reference_date deve ser YYYY-MM-DD, recebido: {value!r}"
        )
    return value


def sanitize_expression(sql_expression: str) -> str:
    """Validação de expressões SQL como date_expression.

    Aceita expressões com parênteses, CAST, AS, DATE, VARCHAR etc.
    Bloqueia as mesmas keywords destrutivas e tokens perigosos que
    sanitize_filter.

    Args:
        sql_expression: Expressão SQL (ex: 'CAST("dt_ref" AS DATE)').

    Returns:
        A expressão sanitizada (stripped), se segura.

    Raises:
        ValueError: Se a expressão contém tokens ou keywords bloqueados.
    """
    stripped = sql_expression.strip()

    if not stripped:
        raise ValueError("Expressão não pode ser vazia")

    # Checar tokens perigosos
    for token in _BLOCKED_TOKENS:
        if token in stripped:
            raise ValueError(
                f"Expressão contém token bloqueado: {token!r}"
            )

    # Checar keywords bloqueadas
    match = _BLOCKED_KEYWORDS_PATTERN.search(stripped)
    if match:
        raise ValueError(
            f"Expressão contém keyword bloqueada: {match.group()!r}"
        )

    return stripped


def sanitize_filter(sql_fragment: str) -> str:
    """Validação básica de filtro custom do usuário.

    Bloqueia tokens e keywords perigosos. Para MVP, permite apenas
    expressões simples (col = 'val', col IN (...), col BETWEEN x AND y).

    Args:
        sql_fragment: Fragmento SQL fornecido pelo usuário.

    Returns:
        O fragmento sanitizado (stripped), se seguro.

    Raises:
        ValueError: Se o fragmento contém tokens ou keywords bloqueados.
    """
    stripped = sql_fragment.strip()

    if not stripped:
        raise ValueError("Filtro não pode ser vazio")

    # Checar tokens perigosos
    for token in _BLOCKED_TOKENS:
        if token in stripped:
            raise ValueError(
                f"Filtro contém token bloqueado: {token!r}"
            )

    # Checar keywords bloqueadas
    match = _BLOCKED_KEYWORDS_PATTERN.search(stripped)
    if match:
        raise ValueError(
            f"Filtro contém keyword bloqueada: {match.group()!r}"
        )

    return stripped
