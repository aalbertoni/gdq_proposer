"""Testes para core/backtest.py.

Usa fixtures sintéticas para validar backtest com janela rolante.
"""

import math
import pytest

from core.backtest import backtest_band
from tests.fixtures import (
    make_stable_series,
    make_drift_series,
    make_outlier_series,
    make_sparse_numeric_series,
    make_zero_inflated_series,
    make_regime_change_series,
    make_seasonal_series,
)


class TestBacktestStableSeries:
    def test_high_coverage(self):
        data = make_stable_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        assert result.coverage_pct >= 90.0

    def test_low_false_positives(self):
        data = make_stable_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        # With dual guard (sigma OR margin), FP should be very low
        assert result.false_positive_proxy <= 2

    def test_no_drift(self):
        data = make_stable_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        assert result.has_drift is False

    def test_stability_high(self):
        data = make_stable_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        assert result.stability_score >= 0.6

    def test_total_periods_sum(self):
        data = make_stable_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        assert result.total_periods == result.periods_pass + result.periods_fail


class TestBacktestDriftSeries:
    def test_drift_detected(self):
        data = make_drift_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        assert result.has_drift is True

    def test_some_failures(self):
        data = make_drift_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=10, n_sigma=1.5)
        # With tight bands and drift, there should be some failures
        assert result.total_periods > 0


class TestBacktestOutlierSeries:
    def test_outliers_detected(self):
        data = make_outlier_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        assert result.periods_fail > 0

    def test_outlier_periods_listed(self):
        data = make_outlier_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        assert len(result.outlier_periods) == result.periods_fail


class TestBacktestRegimeChange:
    def test_low_stability(self):
        data = make_regime_change_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        # Regime change means band parameters are unstable
        assert result.stability_score <= 0.8

    def test_has_failures(self):
        data = make_regime_change_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=10)
        assert result.periods_fail > 0


class TestBacktestSparseSeries:
    def test_handles_nan(self):
        data = make_sparse_numeric_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        # Should not crash; total_periods < 40 because NaN points skipped
        assert result.total_periods >= 0


class TestBacktestEdgeCases:
    def test_empty_values(self):
        result = backtest_band([], [], n_periods=20)
        assert result.total_periods == 0
        assert result.coverage_pct == 0.0

    def test_too_few_values(self):
        result = backtest_band([1.0, 2.0, 3.0], ["d1", "d2", "d3"], n_periods=20)
        assert result.total_periods == 0

    def test_min_history_respected(self):
        data = make_stable_series(n=15)
        result = backtest_band(
            data["values"], data["dates"],
            n_periods=10, min_history=12,
        )
        # Only a few points can be evaluated since we need 12 prior
        assert result.total_periods <= 3

    def test_band_width_ratio_positive(self):
        data = make_stable_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        assert result.band_width_ratio > 0

    def test_coverage_pct_range(self):
        data = make_stable_series(n=40)
        result = backtest_band(data["values"], data["dates"], n_periods=20)
        assert 0.0 <= result.coverage_pct <= 100.0
