"""Tests for enriched rule scoring with regime awareness.

Tests _compute_regime_fit, _compute_fp_risk, _compute_robustness,
_regime_warnings, and evaluate_proposal.
"""

import pytest

from core.models.enums import ConfidenceLevel, RuleType, SeriesRegime
from core.models.rule_evaluation import RuleEvaluation
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.series_profile import SeriesProfile
from core.rule_scoring import (
    _compute_regime_fit,
    _compute_fp_risk,
    _compute_robustness,
    _regime_warnings,
    evaluate_proposal,
    score_proposal,
)
from tests.fixtures import make_stable_series


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proposal(
    backtest: BacktestSummary | None = None,
    rule_type: RuleType = RuleType.MEAN_DUAL_GUARD,
    warnings: list[str] | None = None,
    history_values: list[float] | None = None,
) -> RuleProposal:
    return RuleProposal(
        id="test-001",
        target_column="VLR_SALDO",
        target_table="tb_test",
        rule_type=rule_type,
        metric_name="mean",
        backtest=backtest,
        warnings=warnings or [],
        history_values=history_values or [],
    )


def _make_good_backtest() -> BacktestSummary:
    return BacktestSummary(
        total_periods=30,
        periods_pass=29,
        periods_fail=1,
        coverage_pct=96.67,
        false_positive_proxy=0,
        band_width_ratio=0.15,
        stability_score=0.9,
        has_drift=False,
    )


def _stable_profile() -> SeriesProfile:
    return SeriesProfile(
        regime=SeriesRegime.STABLE,
        n_points=30, n_valid=30, cv=0.10,
    )


def _volatile_profile() -> SeriesProfile:
    return SeriesProfile(
        regime=SeriesRegime.VOLATILE,
        is_volatile=True,
        n_points=30, n_valid=30, cv=0.55,
    )


def _trending_profile() -> SeriesProfile:
    return SeriesProfile(
        regime=SeriesRegime.TRENDING,
        has_trend=True,
        n_points=30, n_valid=30, cv=0.15,
        drift_slope=0.05,
    )


def _structural_break_profile() -> SeriesProfile:
    return SeriesProfile(
        regime=SeriesRegime.STRUCTURAL_BREAK,
        has_structural_break=True,
        n_points=30, n_valid=30,
        change_point_date="2026-02-15",
        change_point_magnitude=50.0,
    )


def _asymmetric_profile() -> SeriesProfile:
    return SeriesProfile(
        regime=SeriesRegime.ASYMMETRIC,
        is_asymmetric=True,
        n_points=30, n_valid=30,
        skewness=2.5, cv=0.25,
    )


def _sparse_profile() -> SeriesProfile:
    return SeriesProfile(
        regime=SeriesRegime.SPARSE,
        is_sparse=True,
        n_points=30, n_valid=10,
        null_pct=66.67,
    )


# ===========================================================================
# _compute_regime_fit
# ===========================================================================

class TestComputeRegimeFit:

    def test_stable_always_1(self):
        fit = _compute_regime_fit(SeriesRegime.STABLE, (), RuleType.MEAN_DUAL_GUARD)
        assert fit == 1.0

    def test_volatile_mean_lower_than_rowcount(self):
        fit_mean = _compute_regime_fit(
            SeriesRegime.VOLATILE, (), RuleType.MEAN_DUAL_GUARD,
        )
        fit_rc = _compute_regime_fit(
            SeriesRegime.VOLATILE, (), RuleType.ROW_COUNT_DUAL_GUARD,
        )
        assert fit_mean < fit_rc

    def test_structural_break_mean_very_low(self):
        fit = _compute_regime_fit(
            SeriesRegime.STRUCTURAL_BREAK, (), RuleType.MEAN_DUAL_GUARD,
        )
        assert fit <= 0.3

    def test_secondary_regime_applies_penalty(self):
        fit_no_sec = _compute_regime_fit(
            SeriesRegime.VOLATILE, (), RuleType.MEAN_DUAL_GUARD,
        )
        fit_with_sec = _compute_regime_fit(
            SeriesRegime.VOLATILE, (SeriesRegime.ASYMMETRIC,), RuleType.MEAN_DUAL_GUARD,
        )
        assert fit_with_sec < fit_no_sec

    def test_completeness_resilient_to_regime(self):
        """Completeness should stay high even in adverse regimes."""
        for regime in [SeriesRegime.VOLATILE, SeriesRegime.SPARSE, SeriesRegime.TRENDING]:
            fit = _compute_regime_fit(regime, (), RuleType.COMPLETENESS)
            assert fit >= 0.8, f"Completeness fit too low for {regime}"

    def test_fit_never_negative(self):
        fit = _compute_regime_fit(
            SeriesRegime.STRUCTURAL_BREAK,
            (SeriesRegime.VOLATILE, SeriesRegime.ASYMMETRIC, SeriesRegime.SPARSE),
            RuleType.MEAN_DUAL_GUARD,
        )
        assert fit >= 0.0


# ===========================================================================
# _compute_fp_risk
# ===========================================================================

class TestComputeFpRisk:

    def test_no_profile_no_bt_zero_risk(self):
        assert _compute_fp_risk(None, None) == 0.0

    def test_high_cv_increases_risk(self):
        risk = _compute_fp_risk(_volatile_profile(), None)
        assert risk > 0.0

    def test_asymmetric_increases_risk(self):
        risk = _compute_fp_risk(_asymmetric_profile(), None)
        assert risk >= 0.15

    def test_backtest_fps_increase_risk(self):
        bt = _make_good_backtest()
        bt.false_positive_proxy = 3
        risk = _compute_fp_risk(None, bt)
        assert risk >= 0.20

    def test_risk_capped_at_1(self):
        profile = SeriesProfile(
            regime=SeriesRegime.VOLATILE,
            is_volatile=True, is_asymmetric=True,
            n_points=30, n_valid=30,
            cv=0.60, skewness=3.0, n_outliers_iqr=10,
        )
        bt = _make_good_backtest()
        bt.false_positive_proxy = 10
        bt.band_width_ratio = 0.05
        risk = _compute_fp_risk(profile, bt)
        assert risk <= 1.0


# ===========================================================================
# _compute_robustness
# ===========================================================================

class TestComputeRobustness:

    def test_good_data_high_robustness(self):
        rob = _compute_robustness(_stable_profile(), 30)
        assert rob >= 0.9

    def test_few_points_reduces_robustness(self):
        rob_many = _compute_robustness(None, 30)
        rob_few = _compute_robustness(None, 5)
        assert rob_few < rob_many

    def test_sparse_reduces_robustness(self):
        rob = _compute_robustness(_sparse_profile(), 10)
        assert rob < 0.8

    def test_never_negative(self):
        profile = SeriesProfile(
            regime=SeriesRegime.SPARSE,
            is_sparse=True, is_zero_inflated=True,
            n_points=30, n_valid=5,
            null_pct=83.0, n_outliers_iqr=10,
        )
        rob = _compute_robustness(profile, 2)
        assert rob >= 0.0


# ===========================================================================
# _regime_warnings
# ===========================================================================

class TestRegimeWarnings:

    def test_stable_no_warnings(self):
        warns = _regime_warnings(_stable_profile())
        assert warns == []

    def test_structural_break_warning_includes_date(self):
        warns = _regime_warnings(_structural_break_profile())
        assert any("2026-02-15" in w for w in warns)

    def test_trending_warning(self):
        warns = _regime_warnings(_trending_profile())
        assert any("tendencia" in w.lower() for w in warns)

    def test_volatile_warning_mentions_cv(self):
        warns = _regime_warnings(_volatile_profile())
        assert any("cv=" in w.lower() for w in warns)

    def test_asymmetric_warning(self):
        warns = _regime_warnings(_asymmetric_profile())
        assert any("assimetrica" in w.lower() for w in warns)


# ===========================================================================
# score_proposal with profile
# ===========================================================================

class TestScoreProposalWithProfile:

    def test_stable_profile_same_as_no_profile(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        history = make_stable_series(n=30)["values"]
        score_no = score_proposal(proposal, history, profile=None)
        score_stable = score_proposal(proposal, history, profile=_stable_profile())
        # Stable profile: regime_fit=1.0, fp_risk~0.0, robustness~1.0
        # Should be very close to no-profile score
        assert abs(score_no.score_total - score_stable.score_total) < 0.15

    def test_volatile_profile_lowers_score(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt, rule_type=RuleType.MEAN_DUAL_GUARD)
        history = make_stable_series(n=30)["values"]
        score_stable = score_proposal(proposal, history, profile=_stable_profile())
        score_volatile = score_proposal(proposal, history, profile=_volatile_profile())
        assert score_volatile.score_total < score_stable.score_total

    def test_structural_break_adds_warning(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        history = make_stable_series(n=30)["values"]
        score = score_proposal(proposal, history, profile=_structural_break_profile())
        assert any("mudanca" in w.lower() for w in score.warnings)

    def test_recommendation_includes_regime(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        history = make_stable_series(n=30)["values"]
        score = score_proposal(proposal, history, profile=_volatile_profile())
        assert "regime:" in score.recommendation.lower()

    def test_backward_compatible_no_profile(self):
        """score_proposal without profile should still work."""
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        history = make_stable_series(n=30)["values"]
        score = score_proposal(proposal, history)
        assert score.score_total > 0
        assert score.confidence in list(ConfidenceLevel)


# ===========================================================================
# evaluate_proposal
# ===========================================================================

class TestEvaluateProposal:

    def test_returns_rule_evaluation(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        ev = evaluate_proposal(proposal, profile=_stable_profile())
        assert isinstance(ev, RuleEvaluation)

    def test_all_dimensions_populated(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(
            backtest=bt,
            history_values=make_stable_series(n=30)["values"],
        )
        ev = evaluate_proposal(proposal, profile=_stable_profile())
        assert ev.coverage > 0
        assert ev.stability > 0
        assert ev.interpretability > 0
        assert ev.cost_efficiency > 0
        assert ev.regime_fit > 0
        assert ev.robustness > 0
        assert ev.fp_risk >= 0

    def test_regime_summary_populated(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        ev = evaluate_proposal(proposal, profile=_volatile_profile())
        assert ev.regime_summary == "volatile"

    def test_no_backtest_low_confidence(self):
        proposal = _make_proposal(backtest=None)
        ev = evaluate_proposal(proposal)
        assert ev.confidence == ConfidenceLevel.LOW

    def test_regime_warnings_in_evaluation(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        ev = evaluate_proposal(proposal, profile=_structural_break_profile())
        assert len(ev.regime_warnings) > 0
        assert any("mudanca" in w.lower() for w in ev.regime_warnings)

    def test_score_total_bounded(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        for profile in [
            _stable_profile(), _volatile_profile(),
            _trending_profile(), _structural_break_profile(),
            _asymmetric_profile(), _sparse_profile(),
        ]:
            ev = evaluate_proposal(proposal, profile=profile)
            assert 0.0 <= ev.score_total <= 1.0, f"Score out of bounds for {profile.regime}"
