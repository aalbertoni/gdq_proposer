"""Testes para core/statistical_engine.py.

Usa as 8 fixtures sintéticas para validar bandas, margens e drift.
"""

import math
import pytest

from core.statistical_engine import (
    compute_dynamic_band,
    compute_margin_band,
    compute_percentile_band,
    compute_frequency_band,
    detect_drift,
    _filter_valid,
    _last_n,
)
from tests.fixtures import (
    make_stable_series,
    make_drift_series,
    make_outlier_series,
    make_sparse_numeric_series,
    make_zero_inflated_series,
    make_regime_change_series,
    make_seasonal_series,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _in_band(value, band):
    return band["lower"] <= value <= band["upper"]


# ---------------------------------------------------------------------------
# _filter_valid / _last_n
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_filter_valid_removes_nan(self):
        assert _filter_valid([1.0, float("nan"), 3.0]) == [1.0, 3.0]

    def test_filter_valid_removes_none(self):
        assert _filter_valid([1.0, None, 3.0]) == [1.0, 3.0]

    def test_filter_valid_empty(self):
        assert _filter_valid([]) == []

    def test_last_n_returns_tail(self):
        assert _last_n([1.0, 2.0, 3.0, 4.0, 5.0], 3) == [3.0, 4.0, 5.0]

    def test_last_n_exceeds_length(self):
        assert _last_n([1.0, 2.0], 10) == [1.0, 2.0]

    def test_last_n_skips_nan(self):
        result = _last_n([1.0, float("nan"), 3.0, 4.0], 3)
        assert result == [1.0, 3.0, 4.0]


# ---------------------------------------------------------------------------
# compute_dynamic_band
# ---------------------------------------------------------------------------

class TestDynamicBand:
    def test_stable_series_covers_most_points(self):
        data = make_stable_series()
        band = compute_dynamic_band(data["values"], n_periods=30, n_sigma=2.0)
        in_count = sum(1 for v in data["values"] if _in_band(v, band))
        assert in_count / len(data["values"]) >= 0.90

    def test_stable_series_center_near_100(self):
        data = make_stable_series()
        band = compute_dynamic_band(data["values"], n_periods=30)
        assert abs(band["center"] - 100.0) < 5.0

    def test_stable_series_std_reasonable(self):
        data = make_stable_series()
        band = compute_dynamic_band(data["values"], n_periods=30)
        assert 1.0 < band["std"] < 15.0

    def test_drift_series_wider_band(self):
        data = make_drift_series()
        band = compute_dynamic_band(data["values"], n_periods=30, n_sigma=2.0)
        width = band["upper"] - band["lower"]
        assert width > 20  # banda larga por causa do drift

    def test_outlier_series_wider_than_stable(self):
        stable = make_stable_series()
        outlier = make_outlier_series()
        band_s = compute_dynamic_band(stable["values"], 30)
        band_o = compute_dynamic_band(outlier["values"], 30)
        assert (band_o["upper"] - band_o["lower"]) > (band_s["upper"] - band_s["lower"])

    def test_sparse_series_filters_nan(self):
        data = make_sparse_numeric_series()
        band = compute_dynamic_band(data["values"], n_periods=30)
        assert band["n_periods_used"] < 30  # some were NaN

    def test_zero_inflated_low_center(self):
        data = make_zero_inflated_series()
        band = compute_dynamic_band(data["values"], n_periods=30)
        assert band["center"] < 50  # many zeros pull center down

    def test_regime_change_wide_band(self):
        data = make_regime_change_series()
        band = compute_dynamic_band(data["values"], n_periods=30)
        assert band["std"] > 50  # huge spread between regimes

    def test_n_periods_used_correct(self):
        data = make_stable_series(n=50)
        band = compute_dynamic_band(data["values"], n_periods=20)
        assert band["n_periods_used"] == 20

    def test_too_few_values_raises(self):
        with pytest.raises(ValueError, match="Insuficiente"):
            compute_dynamic_band([1.0, 2.0], n_periods=10)

    def test_all_nan_raises(self):
        with pytest.raises(ValueError, match="Insuficiente"):
            compute_dynamic_band([float("nan")] * 10, n_periods=10)

    def test_three_values_minimum(self):
        band = compute_dynamic_band([10.0, 20.0, 30.0], n_periods=5)
        assert band["n_periods_used"] == 3

    def test_higher_sigma_wider_band(self):
        data = make_stable_series()
        band2 = compute_dynamic_band(data["values"], 30, n_sigma=2.0)
        band3 = compute_dynamic_band(data["values"], 30, n_sigma=3.0)
        assert (band3["upper"] - band3["lower"]) > (band2["upper"] - band2["lower"])


# ---------------------------------------------------------------------------
# compute_margin_band
# ---------------------------------------------------------------------------

class TestMarginBand:
    def test_stable_series_10pct(self):
        data = make_stable_series()
        band = compute_margin_band(data["values"], n_periods=30, margin_pct=0.10)
        assert band["lower"] == pytest.approx(band["center"] * 0.9, rel=1e-6)
        assert band["upper"] == pytest.approx(band["center"] * 1.1, rel=1e-6)

    def test_margin_pct_stored(self):
        data = make_stable_series()
        band = compute_margin_band(data["values"], n_periods=30, margin_pct=0.15)
        assert band["margin_pct"] == 0.15

    def test_too_few_raises(self):
        with pytest.raises(ValueError, match="Insuficiente"):
            compute_margin_band([1.0], n_periods=5)

    def test_zero_center_produces_zero_band(self):
        band = compute_margin_band([0.0, 0.0, 0.0, 0.0], n_periods=4, margin_pct=0.10)
        assert band["lower"] == 0.0
        assert band["upper"] == 0.0


# ---------------------------------------------------------------------------
# compute_percentile_band
# ---------------------------------------------------------------------------

class TestPercentileBand:
    def test_basic(self):
        p_lower = [10.0, 12.0, 11.0, 10.5, 11.5]
        p_upper = [90.0, 88.0, 91.0, 89.0, 90.5]
        band = compute_percentile_band(p_lower, p_upper, n_periods=5)
        assert band["lower"] < band["upper"]
        assert band["n_periods_used"] == 5

    def test_too_few_raises(self):
        with pytest.raises(ValueError, match="Insuficiente"):
            compute_percentile_band([1.0], [2.0], n_periods=5)


# ---------------------------------------------------------------------------
# compute_frequency_band
# ---------------------------------------------------------------------------

class TestFrequencyBand:
    def test_stable_frequency(self):
        pct = [30.0, 31.0, 29.5, 30.2, 30.8, 29.9, 30.1, 30.5, 29.7, 30.3]
        band = compute_frequency_band(pct, n_periods=10)
        assert 25.0 < band["lower"] < 35.0
        assert 25.0 < band["upper"] < 35.0

    def test_lower_clipped_to_negative(self):
        """Lower bound pode ser negativo (buffer para categorias raras)."""
        pct = [0.5, 0.3, 0.1, 0.2, 0.4]
        band = compute_frequency_band(pct, n_periods=5)
        assert band["lower"] >= -0.01

    def test_upper_capped_at_100(self):
        pct = [99.5, 99.8, 99.7, 99.9, 99.6]
        band = compute_frequency_band(pct, n_periods=5)
        assert band["upper"] <= 100.01


# ---------------------------------------------------------------------------
# detect_drift
# ---------------------------------------------------------------------------

class TestDetectDrift:
    def test_drift_series_detected(self):
        data = make_drift_series()
        result = detect_drift(data["values"])
        assert result["has_drift"] is True
        assert result["slope"] > 0
        assert result["r_squared"] > 0.5

    def test_stable_series_no_drift(self):
        data = make_stable_series()
        result = detect_drift(data["values"])
        assert result["has_drift"] is False

    def test_regime_change_detects_drift(self):
        data = make_regime_change_series()
        result = detect_drift(data["values"])
        # Regime change looks like a strong upward trend
        assert result["has_drift"] is True

    def test_too_few_points_no_drift(self):
        result = detect_drift([1.0, 2.0, 3.0])
        assert result["has_drift"] is False
        assert result["n_points"] == 3

    def test_window_parameter(self):
        data = make_drift_series(n=50)
        result_all = detect_drift(data["values"])
        result_10 = detect_drift(data["values"], window=10)
        assert result_all["n_points"] == 50
        assert result_10["n_points"] == 10

    def test_constant_series_no_drift(self):
        result = detect_drift([42.0] * 20)
        assert result["has_drift"] is False
        assert result["r_squared"] == 0.0

    def test_seasonal_low_drift(self):
        data = make_seasonal_series()
        result = detect_drift(data["values"])
        # Seasonal should not show strong linear drift
        assert result["r_squared"] < 0.5 or result["has_drift"] is False
