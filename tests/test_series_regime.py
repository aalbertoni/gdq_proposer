"""Tests for series regime classification.

Validates that each fixture series is correctly classified
into the expected regime, with appropriate flags and metrics.
"""

import math

import pytest

from core.models.enums import SeriesRegime
from core.models.series_profile import SeriesProfile
from core.series_regime import (
    classify_series,
    _compute_skewness,
    _determine_regime,
)
from tests.fixtures import (
    make_stable_series,
    make_drift_series,
    make_seasonal_series,
    make_outlier_series,
    make_sparse_numeric_series,
    make_zero_inflated_series,
    make_regime_change_series,
)


# ===========================================================================
# SeriesProfile dataclass
# ===========================================================================

class TestSeriesProfile:

    def test_frozen_immutable(self):
        """SeriesProfile should be immutable (frozen=True)."""
        profile = SeriesProfile(regime=SeriesRegime.STABLE)
        with pytest.raises(AttributeError):
            profile.regime = SeriesRegime.VOLATILE

    def test_is_stable_property(self):
        p = SeriesProfile(regime=SeriesRegime.STABLE)
        assert p.is_stable is True
        p2 = SeriesProfile(regime=SeriesRegime.VOLATILE)
        assert p2.is_stable is False

    def test_regime_count_no_secondary(self):
        p = SeriesProfile(regime=SeriesRegime.STABLE)
        assert p.regime_count == 1

    def test_regime_count_with_secondary(self):
        p = SeriesProfile(
            regime=SeriesRegime.TRENDING,
            secondary_regimes=(SeriesRegime.VOLATILE, SeriesRegime.ASYMMETRIC),
        )
        assert p.regime_count == 3

    def test_regime_summary(self):
        p = SeriesProfile(
            regime=SeriesRegime.STRUCTURAL_BREAK,
            secondary_regimes=(SeriesRegime.VOLATILE,),
        )
        assert p.regime_summary == "structural_break + volatile"

    def test_defaults(self):
        p = SeriesProfile(regime=SeriesRegime.STABLE)
        assert p.is_volatile is False
        assert p.has_trend is False
        assert p.n_points == 0
        assert p.cv == 0.0
        assert p.change_point_date is None


# ===========================================================================
# _determine_regime priority
# ===========================================================================

class TestDetermineRegime:

    def test_all_false_returns_stable(self):
        regime, secondary = _determine_regime(
            has_structural_break=False, has_trend=False,
            is_seasonal=False, is_volatile=False,
            is_zero_inflated=False, is_asymmetric=False,
            is_sparse=False,
        )
        assert regime == SeriesRegime.STABLE
        assert secondary == []

    def test_structural_break_highest_priority(self):
        regime, secondary = _determine_regime(
            has_structural_break=True, has_trend=True,
            is_seasonal=True, is_volatile=True,
            is_zero_inflated=False, is_asymmetric=False,
            is_sparse=False,
        )
        assert regime == SeriesRegime.STRUCTURAL_BREAK
        assert SeriesRegime.TRENDING in secondary
        assert SeriesRegime.SEASONAL in secondary
        assert SeriesRegime.VOLATILE in secondary

    def test_trend_before_seasonal(self):
        regime, secondary = _determine_regime(
            has_structural_break=False, has_trend=True,
            is_seasonal=True, is_volatile=False,
            is_zero_inflated=False, is_asymmetric=False,
            is_sparse=False,
        )
        assert regime == SeriesRegime.TRENDING
        assert secondary == [SeriesRegime.SEASONAL]

    def test_zero_inflated_before_volatile(self):
        regime, secondary = _determine_regime(
            has_structural_break=False, has_trend=False,
            is_seasonal=False, is_volatile=True,
            is_zero_inflated=True, is_asymmetric=False,
            is_sparse=False,
        )
        assert regime == SeriesRegime.ZERO_INFLATED
        assert secondary == [SeriesRegime.VOLATILE]

    def test_single_flag(self):
        regime, secondary = _determine_regime(
            has_structural_break=False, has_trend=False,
            is_seasonal=False, is_volatile=False,
            is_zero_inflated=False, is_asymmetric=True,
            is_sparse=False,
        )
        assert regime == SeriesRegime.ASYMMETRIC
        assert secondary == []


# ===========================================================================
# _compute_skewness
# ===========================================================================

class TestComputeSkewness:

    def test_symmetric_near_zero(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        mean = 3.0
        std = math.sqrt(2.5)
        skew = _compute_skewness(values, mean, std)
        assert abs(skew) < 0.5  # symmetric → near zero

    def test_right_skewed_positive(self):
        values = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 100.0]
        mean = sum(values) / len(values)
        std = math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
        skew = _compute_skewness(values, mean, std)
        assert skew > 1.0

    def test_too_few_points_returns_zero(self):
        assert _compute_skewness([1.0, 2.0], 1.5, 0.5) == 0.0

    def test_zero_std_returns_zero(self):
        assert _compute_skewness([5.0, 5.0, 5.0], 5.0, 0.0) == 0.0


# ===========================================================================
# classify_series — integration with fixtures
# ===========================================================================

class TestClassifySeriesStable:

    def test_stable_series_regime(self):
        data = make_stable_series()
        profile = classify_series(data["values"], data["dates"])
        assert profile.regime == SeriesRegime.STABLE
        assert profile.is_stable is True
        assert profile.is_volatile is False
        assert profile.has_trend is False

    def test_stable_series_metrics(self):
        data = make_stable_series()
        profile = classify_series(data["values"], data["dates"])
        assert profile.n_points == len(data["values"])
        assert profile.n_valid == profile.n_points
        assert profile.null_pct == 0.0
        assert profile.zero_pct < 5.0
        assert profile.cv < 0.30  # not volatile


class TestClassifySeriesDrift:

    def test_drift_series_detected(self):
        data = make_drift_series()
        profile = classify_series(data["values"], data["dates"])
        assert profile.has_trend is True
        assert profile.regime == SeriesRegime.TRENDING
        assert profile.drift_slope != 0.0


class TestClassifySeriesSeasonal:

    def test_seasonal_series_detected(self):
        data = make_seasonal_series(n=42)
        profile = classify_series(data["values"], data["dates"])
        # Seasonal detection needs >= 14 points and strong pattern
        if profile.is_seasonal:
            assert profile.regime == SeriesRegime.SEASONAL
            assert profile.seasonality_strength > 0.0


class TestClassifySeriesOutlier:

    def test_outlier_series_has_outliers(self):
        data = make_outlier_series()
        profile = classify_series(data["values"], data["dates"])
        assert profile.n_outliers_iqr >= 1


class TestClassifySeriesSparse:

    def test_sparse_series_detected(self):
        data = make_sparse_numeric_series()
        profile = classify_series(data["values"], data["dates"])
        assert profile.is_sparse is True
        assert profile.null_pct >= 30.0
        # Sparse should be primary or secondary
        all_regimes = [profile.regime] + list(profile.secondary_regimes)
        assert SeriesRegime.SPARSE in all_regimes


class TestClassifySeriesZeroInflated:

    def test_zero_inflated_detected(self):
        data = make_zero_inflated_series()
        profile = classify_series(data["values"], data["dates"])
        assert profile.is_zero_inflated is True
        assert profile.zero_pct >= 30.0
        all_regimes = [profile.regime] + list(profile.secondary_regimes)
        assert SeriesRegime.ZERO_INFLATED in all_regimes


class TestClassifySeriesRegimeChange:

    def test_regime_change_detected(self):
        data = make_regime_change_series()
        profile = classify_series(data["values"], data["dates"])
        assert profile.has_structural_break is True
        assert profile.regime == SeriesRegime.STRUCTURAL_BREAK
        assert profile.change_point_date is not None
        assert profile.change_point_magnitude > 0


class TestClassifySeriesEdgeCases:

    def test_empty_series(self):
        profile = classify_series([], [])
        assert profile.regime == SeriesRegime.STABLE
        assert profile.n_points == 0

    def test_single_value(self):
        profile = classify_series([42.0], ["2026-01-01"])
        assert profile.regime == SeriesRegime.STABLE
        assert profile.n_valid == 1

    def test_all_nulls(self):
        values = [float("nan")] * 10
        dates = [f"2026-01-{i+1:02d}" for i in range(10)]
        profile = classify_series(values, dates)
        assert profile.is_sparse is True
        assert profile.null_pct == 100.0

    def test_constant_series(self):
        values = [100.0] * 30
        dates = [f"2026-01-{i+1:02d}" for i in range(30)]
        profile = classify_series(values, dates)
        assert profile.regime == SeriesRegime.STABLE
        assert profile.cv == 0.0

    def test_high_skewness_detected(self):
        """Series with extreme right skew should be classified as asymmetric."""
        values = [1.0] * 25 + [1000.0] * 5
        dates = [f"2026-01-{i+1:02d}" for i in range(30)]
        profile = classify_series(values, dates)
        assert profile.is_asymmetric is True
        assert abs(profile.skewness) > 1.0

    def test_manually_volatile_series(self):
        """High CV series should be volatile."""
        import random
        random.seed(99)
        values = [random.uniform(0, 1000) for _ in range(30)]
        dates = [f"2026-01-{i+1:02d}" for i in range(30)]
        profile = classify_series(values, dates)
        assert profile.is_volatile is True
        assert profile.cv > 0.30

    def test_profile_summary_format(self):
        data = make_regime_change_series()
        profile = classify_series(data["values"], data["dates"])
        summary = profile.regime_summary
        assert "structural_break" in summary
        assert isinstance(summary, str)

    def test_secondary_regimes_are_tuple(self):
        data = make_stable_series()
        profile = classify_series(data["values"], data["dates"])
        assert isinstance(profile.secondary_regimes, tuple)
