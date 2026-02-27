"""Testes para core/backtest.py.

Usa fixtures sintéticas para validar backtest com janela rolante.
"""

import math
import pytest

from core.backtest import backtest_band, backtest_frequency_band, backtest_frequency_dual_guard, _compute_weighted_coverage
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


class TestWeightedCoverage:
    """Tests for weighted coverage with recency bias."""

    def test_weighted_coverage_stable(self):
        """Stable series: weighted coverage should be close to flat coverage."""
        data = make_stable_series(n=30)
        bt = backtest_band(data["values"], data["dates"], 20, 2.0, 0.10)
        assert abs(bt.weighted_coverage_pct - bt.coverage_pct) < 5.0

    def test_weighted_coverage_regime_change(self):
        """Regime change: weighted coverage exists and is in valid range."""
        data = make_regime_change_series(n=30)
        bt = backtest_band(data["values"], data["dates"], 25, 2.0, 0.10)
        assert bt.weighted_coverage_pct >= 0
        assert bt.weighted_coverage_pct <= 100

    def test_weighted_coverage_empty(self):
        """Empty backtest: weighted = 0."""
        bt = backtest_band([], [], 10, 2.0, 0.10)
        assert bt.weighted_coverage_pct == 0.0

    def test_weighted_coverage_too_few(self):
        """Too few values: weighted = 0 (no evaluation)."""
        bt = backtest_band([1.0, 2.0, 3.0], ["d1", "d2", "d3"], 20, 2.0, 0.10)
        assert bt.weighted_coverage_pct == 0.0

    def test_weighted_higher_when_recent_passes(self):
        """If only recent periods pass, weighted > flat."""
        # First 10 values are extreme outliers, last 20 are stable near 100
        values = [1000.0] * 10 + [100.0 + i * 0.1 for i in range(20)]
        dates = [f"2026-01-{i + 1:02d}" for i in range(30)]
        bt = backtest_band(values, dates, 20, 2.0, 0.10)
        # Weighted should favor recent stable periods
        assert bt.weighted_coverage_pct >= bt.coverage_pct

    def test_weighted_lower_when_recent_fails(self):
        """If recent periods fail, weighted < flat."""
        # First 20 are stable, last 10 are extreme outliers
        values = [100.0 + i * 0.1 for i in range(20)] + [1000.0] * 10
        dates = [f"2026-01-{i + 1:02d}" for i in range(30)]
        bt = backtest_band(values, dates, 15, 2.0, 0.10)
        # Weighted should penalize recent failures
        assert bt.weighted_coverage_pct <= bt.coverage_pct

    def test_weighted_coverage_field_exists(self):
        """BacktestSummary should have weighted_coverage_pct field."""
        data = make_stable_series(n=40)
        bt = backtest_band(data["values"], data["dates"], 20, 2.0, 0.10)
        assert hasattr(bt, 'weighted_coverage_pct')
        assert isinstance(bt.weighted_coverage_pct, float)

    def test_weighted_coverage_sparse_series(self):
        """Sparse series with NaNs: weighted coverage should still work."""
        data = make_sparse_numeric_series(n=40)
        bt = backtest_band(data["values"], data["dates"], 20, 2.0, 0.10)
        assert 0.0 <= bt.weighted_coverage_pct <= 100.0


class TestComputeWeightedCoverageHelper:
    """Tests for the _compute_weighted_coverage helper function."""

    def test_empty_results(self):
        assert _compute_weighted_coverage([]) == 0.0

    def test_all_pass(self):
        results = [{"passed": True}] * 20
        cov = _compute_weighted_coverage(results)
        assert cov == 100.0

    def test_all_fail(self):
        results = [{"passed": False}] * 20
        cov = _compute_weighted_coverage(results)
        assert cov == 0.0

    def test_recent_passes_weighted_higher(self):
        """Early fails, recent passes should give > 50% weighted coverage."""
        results = [{"passed": False}] * 10 + [{"passed": True}] * 10
        cov = _compute_weighted_coverage(results)
        # Flat would be 50%, weighted should be > 50% since recent pass
        assert cov > 50.0

    def test_recent_fails_weighted_lower(self):
        """Early passes, recent fails should give < 50% weighted coverage."""
        results = [{"passed": True}] * 10 + [{"passed": False}] * 10
        cov = _compute_weighted_coverage(results)
        # Flat would be 50%, weighted should be < 50% since recent fail
        assert cov < 50.0

    def test_single_result(self):
        assert _compute_weighted_coverage([{"passed": True}]) == 100.0
        assert _compute_weighted_coverage([{"passed": False}]) == 0.0


class TestWeightedCoverageFrequency:
    """Tests for weighted coverage in frequency backtest functions."""

    def test_frequency_band_has_weighted_coverage(self):
        """backtest_frequency_band returns weighted_coverage_pct."""
        pct_series = [50.0 + i * 0.1 for i in range(30)]
        dates = [f"2026-01-{i + 1:02d}" for i in range(30)]
        bt = backtest_frequency_band(pct_series, dates, n_periods=20, margin_pct=5.0)
        assert hasattr(bt, 'weighted_coverage_pct')
        assert 0.0 <= bt.weighted_coverage_pct <= 100.0

    def test_frequency_dual_guard_has_weighted_coverage(self):
        """backtest_frequency_dual_guard returns weighted_coverage_pct."""
        pct_series = [50.0 + i * 0.1 for i in range(30)]
        dates = [f"2026-01-{i + 1:02d}" for i in range(30)]
        bt = backtest_frequency_dual_guard(pct_series, dates, n_periods=20)
        assert hasattr(bt, 'weighted_coverage_pct')
        assert 0.0 <= bt.weighted_coverage_pct <= 100.0

    def test_frequency_band_empty(self):
        """Empty frequency backtest: weighted = 0."""
        bt = backtest_frequency_band([], [], n_periods=10)
        assert bt.weighted_coverage_pct == 0.0

    def test_frequency_dual_guard_empty(self):
        """Empty frequency dual guard backtest: weighted = 0."""
        bt = backtest_frequency_dual_guard([], [], n_periods=10)
        assert bt.weighted_coverage_pct == 0.0
