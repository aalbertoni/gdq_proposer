"""
Perfil de uma coluna apos classificacao.

Definido conforme docs/technical_spec_v1.md secao 3.2.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.models.enums import SemanticType


@dataclass
class ColumnProfile:
    """Perfil de uma coluna apos classificacao.

    Contem o tipo fisico Athena, o tipo semantico inferido, metricas
    de profiling e um possivel override manual do usuario.
    """

    # === Identificacao ===
    column_name: str
    athena_type: str  # tipo fisico Athena (int, string, etc.)
    inferred_semantic_type: SemanticType
    user_override_type: Optional[SemanticType] = None
    # Override manual sempre prevalece

    # === Metricas de profiling (calculadas com amostra) ===
    total_count: int = 0
    non_null_count: int = 0
    distinct_count: int = 0
    null_ratio: float = 0.0
    distinct_ratio: float = 0.0  # distinct / non_null
    numeric_cast_ratio: float = 0.0  # % castavel para numero
    sample_values: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def effective_type(self) -> SemanticType:
        """Tipo efetivo: override manual > inferencia."""
        return self.user_override_type or self.inferred_semantic_type

    @property
    def is_numeric(self) -> bool:
        return self.effective_type == SemanticType.NUMERIC

    @property
    def is_categorical(self) -> bool:
        return self.effective_type in (
            SemanticType.CATEGORICAL_LOW_CARDINALITY,
            SemanticType.CATEGORICAL_MID_CARDINALITY,
            SemanticType.CATEGORICAL_HIGH_CARDINALITY,
        )
