"""Test fixtures: séries sintéticas para testes do statistical_engine, backtest e scoring."""

from tests.fixtures.stable_series import make_stable_series
from tests.fixtures.drift_series import make_drift_series
from tests.fixtures.seasonal_series import make_seasonal_series
from tests.fixtures.outlier_series import make_outlier_series
from tests.fixtures.sparse_numeric_series import make_sparse_numeric_series
from tests.fixtures.zero_inflated_series import make_zero_inflated_series
from tests.fixtures.regime_change_series import make_regime_change_series
from tests.fixtures.category_shift import (
    make_category_shift,
    make_stable_categories,
    make_rare_category,
    make_emerging_category,
)

__all__ = [
    "make_stable_series",
    "make_drift_series",
    "make_seasonal_series",
    "make_outlier_series",
    "make_sparse_numeric_series",
    "make_zero_inflated_series",
    "make_regime_change_series",
    "make_category_shift",
    "make_stable_categories",
    "make_rare_category",
    "make_emerging_category",
]
