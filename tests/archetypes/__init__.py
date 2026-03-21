"""Adversarial table archetypes for stress-testing the GDQ Proposer.

Cada archetype representa uma arquitetura de tabela real encontrada em
producao que desvia do caminho feliz. O objetivo e validar que o sistema
se comporta adequadamente (ou falha gracefully) em cada cenario.

Comportamentos esperados (AdversarialBehavior):
- SUPPORTED: sistema processa corretamente
- FAIL_FAST: sistema deve rejeitar com erro claro
- WARNING: sistema processa mas deve emitir warning
- KNOWN_LIMITATION: sistema produz resultado potencialmente enganoso
  (documentado, sem fix imediato)

Para adicionar um novo archetype:
1. Criar funcao `arch_<nome>()` em scenarios.py retornando Archetype
2. Adicionar na lista ALL_ARCHETYPES em scenarios.py
3. O teste parametrizado em test_archetypes.py roda automaticamente
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd

from core.models.dataset_config import DatasetConfig
from core.models.enums import SemanticType


class AdversarialBehavior(str, Enum):
    """Comportamento esperado do sistema para cenario adverso."""

    SUPPORTED = "supported"
    # Sistema processa corretamente. Teste valida resultado esperado.

    FAIL_FAST = "fail_fast"
    # Sistema deve rejeitar com erro claro (ValueError, empty result).

    WARNING = "warning"
    # Sistema processa mas deve emitir warning na UI ou nos profiles.

    KNOWN_LIMITATION = "known_limitation"
    # Sistema produz resultado potencialmente enganoso.
    # Documentado como limitacao, sem fix imediato.


@dataclass
class Archetype:
    """Um cenario adverso de tabela com dados, config e expectativas."""

    name: str
    description: str
    category: str  # "partitioning", "schema", "quality", "volume", "combo"
    behavior: AdversarialBehavior

    # Dados e configuracao
    df: pd.DataFrame
    config: DatasetConfig

    # Expectativas de profiling (opcionais)
    expected_types: dict[str, SemanticType] = field(default_factory=dict)
    # col_name -> SemanticType esperado apos profiling

    expected_warnings_contain: list[str] = field(default_factory=list)
    # Substrings que devem aparecer em algum warning

    expected_profiling_succeeds: bool = True
    # Se False, profiling deve retornar UNKNOWN ou falhar

    # Profiling override
    sample_periods: Optional[int] = None
    # Se definido, passa para profile_columns(sample_periods=).
    # Necessario para dados mensais onde default=10 (dias) e insuficiente.

    # Metadata
    notes: str = ""
    # Explicacao de por que este cenario e problemático
