"""Cálculo de tamanho amostral via fórmula de Cochran.

Usado para determinar a porcentagem de TABLESAMPLE BERNOULLI
que garante confiança e margem de erro configuráveis.
"""

import math
from typing import Optional

# Z-scores para níveis de confiança padrão
CONFIDENCE_Z: dict[float, float] = {
    0.90: 1.645,
    0.95: 1.960,
    0.99: 2.576,
}

# Limites operacionais
MIN_SAMPLE_PCT = 0.1        # Floor: 0.1% (evita amostra vazia)
MAX_USEFUL_PCT = 50.0       # Acima disso, amostragem ineficiente
MAX_SAMPLE_ROWS = 500_000   # Teto absoluto de rows na amostra
MIN_POPULATION = 50_000     # Abaixo disso, amostragem desnecessária


def compute_sample_size(
    population: int,
    confidence: float = 0.95,
    margin: float = 0.05,
) -> int:
    """Calcula tamanho amostral via Cochran com correção para população finita.

    Fórmula: n = (Z² × p × (1-p)) / E²
    Correção: n_adj = n / (1 + (n-1)/N)

    Usa p=0.5 (máxima variância) para estimativa conservadora.

    Args:
        population: Tamanho da população (N).
        confidence: Nível de confiança (0.90, 0.95, 0.99).
        margin: Margem de erro (0.01 a 0.10).

    Returns:
        Tamanho amostral ajustado (n_adj), mínimo 1.

    Raises:
        ValueError: Se parâmetros inválidos.
    """
    if population <= 0:
        raise ValueError(f"population deve ser positivo, recebido: {population}")
    if confidence not in CONFIDENCE_Z:
        raise ValueError(
            f"confidence deve ser um de {list(CONFIDENCE_Z.keys())}, "
            f"recebido: {confidence}"
        )
    if not (0.001 <= margin <= 0.50):
        raise ValueError(f"margin deve estar entre 0.001 e 0.50, recebido: {margin}")

    z = CONFIDENCE_Z[confidence]
    p = 0.5  # Máxima variância

    # Cochran (população infinita)
    n0 = (z ** 2 * p * (1 - p)) / (margin ** 2)

    # Correção para população finita
    n_adj = n0 / (1 + (n0 - 1) / population)

    return max(1, math.ceil(n_adj))


def compute_sample_pct(
    population: int,
    confidence: float = 0.95,
    margin: float = 0.05,
) -> Optional[float]:
    """Calcula porcentagem para TABLESAMPLE BERNOULLI.

    Retorna None se amostragem não é útil:
    - População < MIN_POPULATION (tabela pequena)
    - Porcentagem calculada > MAX_USEFUL_PCT (amostra ineficiente)

    Aplica limites operacionais:
    - Floor: MIN_SAMPLE_PCT (evita amostra vazia)
    - Teto: MAX_SAMPLE_ROWS (limita rows absolutas)

    Args:
        population: Tamanho da população (N).
        confidence: Nível de confiança (0.90, 0.95, 0.99).
        margin: Margem de erro (0.01 a 0.10).

    Returns:
        Porcentagem para TABLESAMPLE (0 < pct <= 100), ou None.
    """
    if population < MIN_POPULATION:
        return None

    n_adj = compute_sample_size(population, confidence, margin)
    pct = (n_adj / population) * 100

    if pct > MAX_USEFUL_PCT:
        return None

    # Floor (evita amostra vazia)
    pct = max(pct, MIN_SAMPLE_PCT)

    # Teto de rows absolutas (aplicado depois do floor)
    if population * pct / 100 > MAX_SAMPLE_ROWS:
        pct = (MAX_SAMPLE_ROWS / population) * 100

    return round(pct, 4)
