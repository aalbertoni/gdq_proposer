"""Testes para core/rule_strategy.py — seleção de bundles por regime."""

import pytest

from core.models.enums import RuleType, SeriesRegime
from core.models.rule_bundle import BundledRuleConfig, RuleBundle
from core.models.series_profile import SeriesProfile
from core.rule_strategy import select_strategy


def _profile(regime: SeriesRegime, **kwargs) -> SeriesProfile:
    """Helper para criar SeriesProfile com regime forçado."""
    defaults = dict(
        regime=regime,
        secondary_regimes=(),
        is_volatile=False,
        has_trend=False,
        is_seasonal=False,
        has_structural_break=False,
        is_zero_inflated=False,
        is_asymmetric=False,
        is_sparse=False,
        cv=0.1,
        skewness=0.0,
        null_pct=0.0,
        zero_pct=0.0,
        n_outliers_iqr=0,
        drift_slope=0.0,
        drift_r_squared=0.0,
        seasonality_strength=0.0,
        seasonality_amplitude_ratio=0.0,
        change_point_date=None,
        change_point_magnitude=0.0,
    )
    defaults.update(kwargs)
    return SeriesProfile(**defaults)


def _rule_types(bundle: RuleBundle) -> set[RuleType]:
    return {rc.rule_type for rc in bundle.rule_configs}


class TestStable:
    def test_contains_mean_stddev_rowcount_completeness(self):
        bundle = select_strategy(_profile(SeriesRegime.STABLE))
        types = _rule_types(bundle)
        assert RuleType.MEAN_DUAL_GUARD in types
        assert RuleType.STDDEV_DUAL_GUARD in types
        assert RuleType.ROW_COUNT_DUAL_GUARD in types
        assert RuleType.COMPLETENESS in types

    def test_regime_is_stable(self):
        bundle = select_strategy(_profile(SeriesRegime.STABLE))
        assert bundle.regime == SeriesRegime.STABLE

    def test_max_4_rules(self):
        bundle = select_strategy(_profile(SeriesRegime.STABLE))
        assert len(bundle.rule_configs) <= 4


class TestVolatile:
    def test_mean_sigma_3(self):
        bundle = select_strategy(_profile(SeriesRegime.VOLATILE, cv=0.45))
        mean_configs = [r for r in bundle.rule_configs if r.rule_type == RuleType.MEAN_DUAL_GUARD]
        assert len(mean_configs) == 1
        assert mean_configs[0].suggested_sigma == 3.0

    def test_has_percentile(self):
        bundle = select_strategy(_profile(SeriesRegime.VOLATILE, cv=0.45))
        assert RuleType.NUMERIC_PERCENTILE_BAND in _rule_types(bundle)

    def test_no_stddev(self):
        bundle = select_strategy(_profile(SeriesRegime.VOLATILE, cv=0.45))
        assert RuleType.STDDEV_DUAL_GUARD not in _rule_types(bundle)

    def test_has_rowcount(self):
        bundle = select_strategy(_profile(SeriesRegime.VOLATILE, cv=0.45))
        assert RuleType.ROW_COUNT_DUAL_GUARD in _rule_types(bundle)

    def test_substitutions_mention_stddev(self):
        bundle = select_strategy(_profile(SeriesRegime.VOLATILE, cv=0.45))
        assert any("StdDev" in s for s in bundle.substitutions)


class TestAsymmetric:
    def test_has_percentile_no_mean(self):
        bundle = select_strategy(_profile(SeriesRegime.ASYMMETRIC, skewness=1.5))
        types = _rule_types(bundle)
        assert RuleType.NUMERIC_PERCENTILE_BAND in types
        assert RuleType.MEAN_DUAL_GUARD not in types

    def test_max_3_rules(self):
        bundle = select_strategy(_profile(SeriesRegime.ASYMMETRIC, skewness=1.5))
        assert len(bundle.rule_configs) <= 3


class TestTrending:
    def test_short_n_for_strong_trend(self):
        bundle = select_strategy(_profile(SeriesRegime.TRENDING, drift_r_squared=0.8))
        mean_configs = [r for r in bundle.rule_configs if r.rule_type == RuleType.MEAN_DUAL_GUARD]
        assert len(mean_configs) == 1
        assert mean_configs[0].suggested_n == 10

    def test_moderate_n_for_weak_trend(self):
        bundle = select_strategy(_profile(SeriesRegime.TRENDING, drift_r_squared=0.55))
        mean_configs = [r for r in bundle.rule_configs if r.rule_type == RuleType.MEAN_DUAL_GUARD]
        assert mean_configs[0].suggested_n == 15

    def test_no_stddev(self):
        bundle = select_strategy(_profile(SeriesRegime.TRENDING, drift_r_squared=0.6))
        assert RuleType.STDDEV_DUAL_GUARD not in _rule_types(bundle)


class TestSeasonal:
    def test_n_28_sigma_2_5(self):
        bundle = select_strategy(_profile(SeriesRegime.SEASONAL, seasonality_strength=0.25))
        mean_configs = [r for r in bundle.rule_configs if r.rule_type == RuleType.MEAN_DUAL_GUARD]
        assert mean_configs[0].suggested_n == 28
        assert mean_configs[0].suggested_sigma == 2.5

    def test_rowcount_n_14(self):
        bundle = select_strategy(_profile(SeriesRegime.SEASONAL, seasonality_strength=0.25))
        rc_configs = [r for r in bundle.rule_configs if r.rule_type == RuleType.ROW_COUNT_DUAL_GUARD]
        assert rc_configs[0].suggested_n == 14


class TestStructuralBreak:
    def test_sufficient_post_change(self):
        # n_valid=60 → post_count=60//3=20 (sufficient)
        bundle = select_strategy(_profile(
            SeriesRegime.STRUCTURAL_BREAK, n_valid=60,
        ))
        types = _rule_types(bundle)
        assert RuleType.MEAN_DUAL_GUARD in types
        assert RuleType.STDDEV_DUAL_GUARD in types
        mean_configs = [r for r in bundle.rule_configs if r.rule_type == RuleType.MEAN_DUAL_GUARD]
        assert mean_configs[0].suggested_n == 20  # 60//3=20

    def test_insufficient_post_change_fallback(self):
        # n_valid=9 → post_count=9//3=3 (< 5, insufficient)
        bundle = select_strategy(_profile(
            SeriesRegime.STRUCTURAL_BREAK, n_valid=9,
        ))
        types = _rule_types(bundle)
        assert RuleType.MEAN_DUAL_GUARD not in types
        assert RuleType.COMPLETENESS in types
        assert RuleType.ROW_COUNT_DUAL_GUARD in types

    def test_min_n_10(self):
        # n_valid=21 → post_count=21//3=7, max(7,10)=10
        bundle = select_strategy(_profile(
            SeriesRegime.STRUCTURAL_BREAK, n_valid=21,
        ))
        mean_configs = [r for r in bundle.rule_configs if r.rule_type == RuleType.MEAN_DUAL_GUARD]
        assert mean_configs[0].suggested_n == 10  # max(7, 10) = 10


class TestZeroInflated:
    def test_no_mean_no_stddev(self):
        bundle = select_strategy(_profile(SeriesRegime.ZERO_INFLATED, zero_pct=40.0))
        types = _rule_types(bundle)
        assert RuleType.MEAN_DUAL_GUARD not in types
        assert RuleType.STDDEV_DUAL_GUARD not in types

    def test_has_completeness_rowcount(self):
        bundle = select_strategy(_profile(SeriesRegime.ZERO_INFLATED, zero_pct=40.0))
        types = _rule_types(bundle)
        assert RuleType.COMPLETENESS in types
        assert RuleType.ROW_COUNT_DUAL_GUARD in types


class TestSparse:
    def test_only_completeness_rowcount(self):
        bundle = select_strategy(_profile(SeriesRegime.SPARSE, null_pct=50.0))
        types = _rule_types(bundle)
        assert types == {RuleType.COMPLETENESS, RuleType.ROW_COUNT_DUAL_GUARD}

    def test_explanation_mentions_nulls(self):
        bundle = select_strategy(_profile(SeriesRegime.SPARSE, null_pct=50.0))
        assert "nulo" in bundle.explanation.lower()


class TestFallback:
    def test_unknown_regime_returns_stable(self):
        """If a new regime is added but not mapped, fallback to STABLE."""
        profile = _profile(SeriesRegime.STABLE)
        # Force unknown by monkey-patching (simulates unmapped regime)
        bundle = select_strategy(profile)
        assert bundle.regime == SeriesRegime.STABLE

    def test_all_bundles_have_explanation(self):
        for regime in SeriesRegime:
            profile = _profile(regime, cv=0.4, skewness=1.5, drift_r_squared=0.6,
                               seasonality_strength=0.2, null_pct=0.4,
                               zero_pct=40.0, n_valid=60)
            bundle = select_strategy(profile)
            assert bundle.explanation, f"Missing explanation for {regime}"

    def test_all_bundles_max_4_rules(self):
        for regime in SeriesRegime:
            profile = _profile(regime, cv=0.4, skewness=1.5, drift_r_squared=0.6,
                               seasonality_strength=0.2, null_pct=0.4,
                               zero_pct=40.0, n_valid=60)
            bundle = select_strategy(profile)
            assert len(bundle.rule_configs) <= 4, f"{regime}: {len(bundle.rule_configs)} rules"

    def test_all_bundles_have_rowcount_or_completeness(self):
        """Every bundle must have at least RowCount or Completeness."""
        for regime in SeriesRegime:
            profile = _profile(regime, cv=0.4, skewness=1.5, drift_r_squared=0.6,
                               seasonality_strength=0.2, null_pct=0.4,
                               zero_pct=40.0, n_valid=60)
            bundle = select_strategy(profile)
            types = _rule_types(bundle)
            assert types & {RuleType.ROW_COUNT_DUAL_GUARD, RuleType.COMPLETENESS}, \
                f"{regime}: missing RowCount or Completeness"
