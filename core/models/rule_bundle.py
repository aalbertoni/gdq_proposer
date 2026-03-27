"""Modelo de bundle de regras recomendadas por regime estatístico.

Puramente informativo — não gera SQL, não altera pipeline.
Contém apenas tipos de regra + parâmetros numéricos sugeridos.
"""

from dataclasses import dataclass, field

from core.models.enums import RuleType, SeriesRegime


@dataclass(frozen=True)
class BundledRuleConfig:
    """Configuração de uma regra individual dentro do bundle."""

    rule_type: RuleType
    suggested_n: int | None = None
    suggested_sigma: float | None = None
    note: str = ""


@dataclass(frozen=True)
class RuleBundle:
    """Conjunto de regras recomendadas para um regime estatístico.

    Puramente advisory — a UI exibe como sugestão, o usuário decide
    se ajusta os parâmetros nos controles existentes.
    """

    regime: SeriesRegime
    rule_configs: tuple[BundledRuleConfig, ...] = ()
    explanation: str = ""
    substitutions: tuple[str, ...] = ()
