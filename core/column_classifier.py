"""
Classificação semântica de colunas em camadas.

Camada 1: tipo físico Athena (int/bigint/double → numérica, date → datetime)
Camada 2: heurística de conteúdo (strings castáveis para número → numérica)
Camada 3: cardinalidade para subclassificar categóricas (low/mid/high)

Definido conforme docs/technical_spec_v1.md seção 7.
"""

from core.models.enums import SemanticType


# ---------------------------------------------------------------------------
# Thresholds de classificação (configuráveis)
# ---------------------------------------------------------------------------

NUMERIC_CAST_THRESHOLD = 0.95
LOW_CARDINALITY_MAX_DISTINCT = 50
LOW_CARDINALITY_MAX_RATIO = 0.005
MID_CARDINALITY_MAX_DISTINCT = 500
MID_CARDINALITY_MAX_RATIO = 0.05

# ---------------------------------------------------------------------------
# Tipos Athena nativos
# ---------------------------------------------------------------------------

ATHENA_NUMERIC_TYPES = {
    "tinyint", "smallint", "int", "integer", "bigint",
    "float", "double", "decimal", "real",
}

ATHENA_DATE_TYPES = {"date", "timestamp", "timestamp with time zone"}

# Tipos string/binários que passam para heurística de conteúdo
ATHENA_STRING_TYPES = {"string", "varchar", "char", "binary", "varbinary"}


def classify_column(
    athena_type: str,
    distinct_count: int,
    total_count: int,
    non_null_count: int,
    numeric_cast_count: int = 0,
) -> SemanticType:
    """Classificação em camadas.

    Camada 1 — tipo Athena nativo:
        - Tipos numéricos (int, double, etc.) → NUMERIC
        - Tipos data (date, timestamp) → DATETIME

    Camada 2 — heurística de conteúdo (para strings):
        - Se numeric_cast_ratio > 0.95 → NUMERIC

    Camada 3 — cardinalidade (para strings não-numéricas):
        - distinct_ratio < 0.005 E distinct_count <= 50 → CATEGORICAL_LOW
        - distinct_ratio < 0.05 E distinct_count <= 500 → CATEGORICAL_MID
        - Senão → CATEGORICAL_HIGH

    Args:
        athena_type: Tipo físico Athena (ex: "int", "string", "double").
        distinct_count: Número de valores distintos não-nulos.
        total_count: Total de linhas na amostra.
        non_null_count: Total de linhas não-nulas.
        numeric_cast_count: Quantas linhas string são castáveis para número.

    Returns:
        SemanticType inferido.
    """
    base_type = _normalize_athena_type(athena_type)

    # Camada 1: tipo nativo
    if base_type in ATHENA_NUMERIC_TYPES:
        return SemanticType.NUMERIC

    if base_type in ATHENA_DATE_TYPES:
        return SemanticType.DATETIME

    # Camada 2: heurística de conteúdo (strings)
    if non_null_count > 0 and numeric_cast_count > 0:
        numeric_cast_ratio = numeric_cast_count / non_null_count
        if numeric_cast_ratio >= NUMERIC_CAST_THRESHOLD:
            return SemanticType.NUMERIC

    # Camada 3: cardinalidade
    if non_null_count == 0:
        return SemanticType.UNKNOWN

    distinct_ratio = distinct_count / non_null_count if non_null_count > 0 else 0.0

    if distinct_count <= LOW_CARDINALITY_MAX_DISTINCT and distinct_ratio < LOW_CARDINALITY_MAX_RATIO:
        return SemanticType.CATEGORICAL_LOW_CARDINALITY

    if distinct_count <= MID_CARDINALITY_MAX_DISTINCT and distinct_ratio < MID_CARDINALITY_MAX_RATIO:
        return SemanticType.CATEGORICAL_MID_CARDINALITY

    return SemanticType.CATEGORICAL_HIGH_CARDINALITY


def _normalize_athena_type(athena_type: str) -> str:
    """Normaliza tipo Athena para comparação.

    Trata tipos parametrizados como decimal(10,2) → decimal,
    varchar(100) → varchar, etc.
    """
    normalized = athena_type.strip().lower()
    # Remove parâmetros: decimal(10,2) → decimal
    paren_idx = normalized.find("(")
    if paren_idx != -1:
        normalized = normalized[:paren_idx]
    return normalized.strip()
