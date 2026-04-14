"""Configuração de amostragem estatística para análise exploratória.

Quando habilitada, queries de análise (numeric_history, categorical_distribution,
profiling) usam TABLESAMPLE BERNOULLI para reduzir volumetria.
Queries de contagem (row_count, distinct_count) e metadados NÃO são amostradas.
Regras GDQ finais operam sobre dados completos.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SamplingConfig:
    """Configuração de amostragem estatística.

    Attributes:
        enabled: Se amostragem está habilitada.
        confidence_level: Nível de confiança (0.90, 0.95, 0.99).
        margin_of_error: Margem de erro (0.01 a 0.10).
        population_size: Tamanho da população estimada (preenchido após Step 5).
        sample_size: Tamanho amostral teórico (Cochran).
        sample_pct: Porcentagem efetiva para TABLESAMPLE (após floor/ceiling).
    """

    enabled: bool = False
    confidence_level: float = 0.95
    margin_of_error: float = 0.05
    population_size: Optional[int] = None
    sample_size: Optional[int] = None
    sample_pct: Optional[float] = None
