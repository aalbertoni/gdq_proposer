"""
Estrategia de baseline para propor thresholds.

Definido conforme docs/technical_spec_v1.md secao 3.3.
"""

from dataclasses import dataclass

from core.models.enums import BaselineMethod


@dataclass
class BaselineStrategy:
    """Como calcular a baseline para propor thresholds.

    Attributes:
        method: Estrategia de calculo (last_n_periods, last_x_days, etc.).
        n_periods: Numero de periodos para lookback.
        n_sigma: Multiplicador de desvio padrao para bandas sigma.
        margin_pct: Margem percentual (alternativa a sigma).
        percentile_lower: Percentil inferior para banda de percentis.
        percentile_upper: Percentil superior para banda de percentis.
        min_history_points: Minimo de pontos para sugerir banda.
    """

    method: BaselineMethod = BaselineMethod.LAST_N_PERIODS
    n_periods: int = 20
    n_sigma: float = 2.0
    margin_pct: float = 0.10
    percentile_lower: float = 0.05
    percentile_upper: float = 0.95
    min_history_points: int = 7
