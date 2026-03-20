"""Policy de thresholds adaptativos por granularidade temporal.

Centraliza todos os valores que mudam entre grain_type (daily, monthly, etc.)
para evitar espalhar `if grain == monthly` pelo codigo.

Modulos de core/ recebem valores individuais via parametros.
A resolucao grain_type -> valores acontece exclusivamente aqui.
"""

from dataclasses import dataclass, field

from core.models.enums import GrainType


@dataclass(frozen=True)
class GrainPolicy:
    """Thresholds adaptativos por granularidade temporal."""

    # Backtest
    min_history: int = 7

    # Auto-tune grid search
    n_range: tuple[int, ...] = (10, 15, 20, 30, 45)
    n_penalty_threshold: int = 15

    # Scoring — robustness tiers: (min_valid_count, penalty)
    # Aplicadas em ordem: primeira que match (valid_count < threshold) aplica a penalty
    robustness_tiers: tuple[tuple[int, float], ...] = (
        (7, -0.30),
        (15, -0.15),
        (30, -0.05),
    )

    # Recommender
    min_valid_periods_dynamic: int = 10
    min_valid_periods_possible: int = 5

    # Seasonality
    seasonality_enabled: bool = True

    # UI slider defaults
    slider_n_min: int = 5
    slider_n_max: int = 90
    slider_n_default: int = 20

    # Batch calibrate minimum
    batch_min_periods: int = 5


_DAILY_POLICY = GrainPolicy()

_MONTHLY_POLICY = GrainPolicy(
    min_history=3,
    n_range=(3, 4, 5, 6, 8, 10, 12),
    n_penalty_threshold=5,
    robustness_tiers=(
        (3, -0.30),
        (5, -0.15),
        (8, -0.05),
    ),
    min_valid_periods_dynamic=3,
    min_valid_periods_possible=2,
    seasonality_enabled=False,
    slider_n_min=3,
    slider_n_max=24,
    slider_n_default=6,
    batch_min_periods=3,
)

_POLICIES: dict[GrainType, GrainPolicy] = {
    GrainType.DAILY: _DAILY_POLICY,
    GrainType.MONTHLY: _MONTHLY_POLICY,
}


def get_grain_policy(grain_type: GrainType) -> GrainPolicy:
    """Retorna policy de thresholds para a granularidade dada.

    GrainTypes nao mapeados (TIMESTAMP, CUSTOM) usam policy daily como default.
    """
    return _POLICIES.get(grain_type, _DAILY_POLICY)
