"""Testes para core/statistical_engine.py.

Usa as 8 fixtures sintéticas para validar bandas, margens e drift.
"""

import math
import random
import pytest

from core.statistical_engine import (
    compute_dynamic_band,
    compute_iqr_band,
    compute_mad_band,
    compute_margin_band,
    compute_percentile_band,
    compute_frequency_band,
    detect_change_points,
    detect_drift,
    detect_outliers,
    detect_seasonality,
    _filter_valid,
    _last_n,
    _median,
    _percentile,
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


# ---------------------------------------------------------------------------
# detect_seasonality
# ---------------------------------------------------------------------------

class TestDetectSeasonality:
    def test_seasonal_series_detected(self):
        """make_seasonal_series has clear weekly pattern."""
        data = make_seasonal_series(n=30)
        result = detect_seasonality(data["values"], data["dates"])
        assert result["has_seasonality"] is True
        assert result["seasonality_strength"] > 0.15
        assert result["amplitude_ratio"] > 0.10
        assert len(result["day_of_week_means"]) == 7

    def test_stable_series_no_seasonality(self):
        """Stable series has no seasonal pattern."""
        data = make_stable_series(n=30)
        result = detect_seasonality(data["values"], data["dates"])
        assert result["has_seasonality"] is False
        # Amplitude ratio is the key discriminator for random noise
        assert result["amplitude_ratio"] < 0.10

    def test_drift_series_no_seasonality(self):
        """Drift series has trend but no weekly pattern."""
        data = make_drift_series(n=30)
        result = detect_seasonality(data["values"], data["dates"])
        # Drift is linear, not seasonal
        assert result["has_seasonality"] is False

    def test_insufficient_data(self):
        """Less than min_periods returns no seasonality."""
        result = detect_seasonality(
            [1.0, 2.0, 3.0],
            ["2026-01-01", "2026-01-02", "2026-01-03"],
        )
        assert result["has_seasonality"] is False
        assert "insuficientes" in result["message"].lower()

    def test_all_same_values(self):
        """Constant series has no seasonality."""
        values = [100.0] * 30
        dates = [f"2026-01-{i + 1:02d}" for i in range(30)]
        result = detect_seasonality(values, dates)
        assert result["has_seasonality"] is False

    def test_empty_series(self):
        result = detect_seasonality([], [])
        assert result["has_seasonality"] is False

    def test_message_contains_day_names_when_seasonal(self):
        """When seasonality detected, message mentions peak/valley days."""
        data = make_seasonal_series(n=30)
        result = detect_seasonality(data["values"], data["dates"])
        if result["has_seasonality"]:
            # Message should contain Portuguese day names
            day_names = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"]
            assert any(name in result["message"] for name in day_names)

    def test_amplitude_and_ratio_positive_for_seasonal(self):
        """Seasonal series should have positive amplitude and ratio."""
        data = make_seasonal_series(n=30)
        result = detect_seasonality(data["values"], data["dates"])
        assert result["amplitude"] > 0
        assert result["amplitude_ratio"] > 0

    def test_nan_values_filtered(self):
        """NaN values should be filtered out before analysis."""
        data = make_seasonal_series(n=30)
        # Insert some NaN values
        values = data["values"][:]
        values[5] = float("nan")
        values[10] = None
        result = detect_seasonality(values, data["dates"])
        # Should still detect seasonality with enough valid data
        assert result["has_seasonality"] is True


# ---------------------------------------------------------------------------
# Robust Statistics: IQR, MAD, detect_outliers
# ---------------------------------------------------------------------------

class TestRobustStatistics:
    def test_iqr_band_stable(self):
        """Stable series: IQR band similar to sigma band."""
        data = make_stable_series(n=30)
        iqr = compute_iqr_band(data["values"], 30)
        sigma = compute_dynamic_band(data["values"], 30, 2.0)
        assert iqr["lower"] < iqr["upper"]
        assert iqr["q1"] < iqr["q3"]
        assert iqr["iqr"] > 0
        # For normal data, IQR and sigma should be reasonably close
        assert abs(iqr["center"] - sigma["center"]) < 10

    def test_iqr_band_outlier_resistant(self):
        """Outlier series: IQR band narrower than sigma band."""
        data = make_outlier_series(n=30)
        iqr = compute_iqr_band(data["values"], 30)
        sigma = compute_dynamic_band(data["values"], 30, 2.0)
        # IQR should be narrower because it ignores outliers
        iqr_width = iqr["upper"] - iqr["lower"]
        sigma_width = sigma["upper"] - sigma["lower"]
        assert iqr_width < sigma_width

    def test_mad_band_stable(self):
        """Stable series: MAD band reasonable."""
        data = make_stable_series(n=30)
        mad = compute_mad_band(data["values"], 30)
        assert mad["lower"] < mad["upper"]
        assert mad["mad_raw"] > 0
        assert mad["mad_scaled"] > mad["mad_raw"]  # scale factor > 1

    def test_mad_band_outlier_resistant(self):
        """Outlier series: MAD band much narrower than sigma."""
        data = make_outlier_series(n=30)
        mad = compute_mad_band(data["values"], 30, n_mad=3.0)
        sigma = compute_dynamic_band(data["values"], 30, 2.0)
        mad_width = mad["upper"] - mad["lower"]
        sigma_width = sigma["upper"] - sigma["lower"]
        assert mad_width < sigma_width

    def test_detect_outliers_iqr(self):
        """Detect outliers in outlier series."""
        data = make_outlier_series(n=30)
        result = detect_outliers(data["values"], method="iqr")
        assert result["n_outliers"] >= 1
        assert result["method"] == "iqr"
        assert len(result["outlier_indices"]) == result["n_outliers"]

    def test_detect_outliers_mad(self):
        """Detect outliers via MAD method."""
        data = make_outlier_series(n=30)
        result = detect_outliers(data["values"], method="mad")
        assert result["n_outliers"] >= 1
        assert result["method"] == "mad"

    def test_detect_outliers_stable_none(self):
        """Stable series should have few or no outliers."""
        data = make_stable_series(n=30)
        result = detect_outliers(data["values"], method="iqr")
        # Stable normal data: at most a couple statistical outliers
        assert result["pct_outliers"] < 0.15

    def test_iqr_band_few_values(self):
        """Fewer than 3 values: degenerate band."""
        result = compute_iqr_band([5.0, 10.0], 2)
        assert result["iqr"] == 0.0
        assert result["n_periods_used"] == 2

    def test_mad_band_few_values(self):
        """Fewer than 3 values: degenerate band."""
        result = compute_mad_band([5.0], 1)
        assert result["mad_raw"] == 0.0
        assert result["n_periods_used"] == 1

    def test_iqr_band_empty(self):
        result = compute_iqr_band([], 10)
        assert result["center"] == 0.0
        assert result["n_periods_used"] == 0

    def test_percentile_function(self):
        """Basic percentile computation."""
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(vals, 50.0) == 3.0
        assert _percentile(vals, 0.0) == 1.0
        assert _percentile(vals, 100.0) == 5.0

    def test_median_function(self):
        assert _median([1.0, 2.0, 3.0]) == 2.0
        assert _median([1.0, 2.0, 3.0, 4.0]) == 2.5
        assert _median([]) == 0.0


# ---------------------------------------------------------------------------
# detect_change_points (CUSUM)
# ---------------------------------------------------------------------------

class TestChangePointDetection:
    def test_regime_change_detected(self):
        """Regime change series should detect change point."""
        data = make_regime_change_series(n=30)
        result = detect_change_points(data["values"], data["dates"])
        assert result["has_change_point"] is True
        assert result["change_index"] is not None
        assert len(result["post_change_values"]) >= 5
        assert len(result["segments"]) >= 2

    def test_stable_no_change(self):
        """Stable series has no change point."""
        data = make_stable_series(n=30)
        result = detect_change_points(data["values"], data["dates"])
        assert result["has_change_point"] is False

    def test_drift_may_or_may_not_detect(self):
        """Drift series: gradual change, not abrupt."""
        data = make_drift_series(n=30)
        result = detect_change_points(data["values"], data["dates"])
        # Drift is gradual, CUSUM may or may not detect depending on threshold
        # Just verify it returns valid structure
        assert "has_change_point" in result
        assert "segments" in result

    def test_insufficient_data(self):
        """Too few points returns no change."""
        result = detect_change_points([1.0, 2.0, 3.0])
        assert result["has_change_point"] is False

    def test_constant_series(self):
        """All same values: no change point."""
        values = [100.0] * 30
        result = detect_change_points(values)
        assert result["has_change_point"] is False

    def test_empty_series(self):
        result = detect_change_points([])
        assert result["has_change_point"] is False

    def test_post_change_values_correct(self):
        """Verify post_change_values are from after the change."""
        data = make_regime_change_series(n=30)
        result = detect_change_points(data["values"], data["dates"])
        if result["has_change_point"]:
            idx = result["change_index"]
            assert result["post_change_values"] == data["values"][idx:]

    def test_segments_cover_full_series(self):
        """Segments should cover all values."""
        data = make_regime_change_series(n=30)
        result = detect_change_points(data["values"], data["dates"])
        total_in_segments = sum(s["end"] - s["start"] for s in result["segments"])
        valid_count = len([v for v in data["values"] if v is not None and v == v])
        assert total_in_segments == valid_count

    def test_change_date_populated(self):
        """When dates provided, change_date should be set."""
        data = make_regime_change_series(n=30)
        result = detect_change_points(data["values"], data["dates"])
        if result["has_change_point"]:
            assert result["change_date"] is not None
            assert result["change_date"] in data["dates"]

    def test_no_dates_still_works(self):
        """Without dates, detection still works but change_date is from indices."""
        data = make_regime_change_series(n=30)
        result = detect_change_points(data["values"])
        assert result["has_change_point"] is True
        assert result["change_date"] is None
        assert result["post_change_dates"] == []

    def test_message_present(self):
        """Result always has a message."""
        data = make_regime_change_series(n=30)
        result = detect_change_points(data["values"], data["dates"])
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 0

    def test_nan_values_handled(self):
        """NaN values should be filtered before detection."""
        data = make_regime_change_series(n=30)
        values = data["values"][:]
        values[3] = float("nan")
        values[7] = None
        result = detect_change_points(values, data["dates"])
        # Should still detect the regime change
        assert result["has_change_point"] is True

    def test_high_threshold_fewer_detections(self):
        """Higher threshold means fewer change points detected."""
        data = make_regime_change_series(n=30)
        result_low = detect_change_points(data["values"], data["dates"], threshold=2.0)
        result_high = detect_change_points(data["values"], data["dates"], threshold=8.0)
        assert result_low["n_change_points"] >= result_high["n_change_points"]

    def test_small_fluctuation_not_detected(self):
        """Small natural variation should NOT trigger change-point.

        A series with mean ~100 and std ~5 that shifts to ~103 (< 1.5 * within_std)
        should not be considered a regime change.
        """
        rng = random.Random(99)
        # First half: mean 100, std ~5
        values = [100.0 + rng.gauss(0, 5) for _ in range(20)]
        # Second half: mean 103, std ~5 (small shift < 1.5 * 5 = 7.5)
        values += [103.0 + rng.gauss(0, 5) for _ in range(20)]
        dates = [f"2026-01-{i+1:02d}" for i in range(40)]
        result = detect_change_points(values, dates)
        assert result["has_change_point"] is False

    def test_large_shift_still_detected(self):
        """Large regime shift (100 -> 200) should still be detected after filter."""
        data = make_regime_change_series(n=30)
        result = detect_change_points(data["values"], data["dates"])
        assert result["has_change_point"] is True
        # Message should contain the percentage
        assert "%" in result["message"]

    def test_message_includes_relative_magnitude(self):
        """When change detected, message should show relative magnitude."""
        data = make_regime_change_series(n=30)
        result = detect_change_points(data["values"], data["dates"])
        if result["has_change_point"]:
            assert "diferenca de" in result["message"]
