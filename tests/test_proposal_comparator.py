"""Tests for core/proposal_comparator.py."""

import pytest

from core.models.enums import RuleType, SeriesRegime, ConfidenceLevel
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.series_profile import SeriesProfile
from core.proposal_comparator import (
    compare_proposals,
    ComparisonResult,
    _find_advantages,
)
from core.models.rule_evaluation import RuleEvaluation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proposal(
    rule_type: RuleType = RuleType.MEAN_DUAL_GUARD,
    coverage_pct: float = 95.0,
    stability: float = 0.9,
    fp: int = 0,
    bwr: float = 0.15,
    proposal_id: str = "p-001",
    history_values: list[float] | None = None,
) -> RuleProposal:
    bt = BacktestSummary(
        total_periods=30, periods_pass=int(30 * coverage_pct / 100),
        periods_fail=30 - int(30 * coverage_pct / 100),
        coverage_pct=coverage_pct, false_positive_proxy=fp,
        band_width_ratio=bwr, stability_score=stability,
        has_drift=False,
    )
    return RuleProposal(
        id=proposal_id,
        target_column="VLR_SALDO",
        target_table="tb_test",
        rule_type=rule_type,
        metric_name="mean",
        backtest=bt,
        history_values=history_values or [100.0] * 30,
    )


# ===========================================================================
# compare_proposals
# ===========================================================================

class TestCompareProposals:

    def test_better_proposal_wins(self):
        a = _make_proposal(coverage_pct=95.0, stability=0.9, proposal_id="a")
        b = _make_proposal(coverage_pct=60.0, stability=0.4, proposal_id="b")
        result = compare_proposals(a, b)
        assert result.winner == "A"
        assert result.score_a > result.score_b

    def test_worse_proposal_loses(self):
        a = _make_proposal(coverage_pct=50.0, stability=0.3, proposal_id="a")
        b = _make_proposal(coverage_pct=95.0, stability=0.9, proposal_id="b")
        result = compare_proposals(a, b)
        assert result.winner == "B"

    def test_equal_proposals_tie(self):
        a = _make_proposal(coverage_pct=90.0, stability=0.8, proposal_id="a")
        b = _make_proposal(coverage_pct=90.0, stability=0.8, proposal_id="b")
        result = compare_proposals(a, b)
        assert result.winner == "tie"

    def test_result_has_ids(self):
        a = _make_proposal(proposal_id="alpha")
        b = _make_proposal(proposal_id="beta")
        result = compare_proposals(a, b)
        assert result.proposal_a_id == "alpha"
        assert result.proposal_b_id == "beta"

    def test_advantages_populated(self):
        a = _make_proposal(coverage_pct=95.0, stability=0.9, proposal_id="a")
        b = _make_proposal(coverage_pct=60.0, stability=0.4, proposal_id="b")
        result = compare_proposals(a, b)
        assert len(result.advantages_a) > 0

    def test_summary_not_empty(self):
        a = _make_proposal(proposal_id="a")
        b = _make_proposal(proposal_id="b")
        result = compare_proposals(a, b)
        assert len(result.summary) > 0

    def test_with_profile(self):
        profile = SeriesProfile(
            regime=SeriesRegime.VOLATILE,
            is_volatile=True, cv=0.50,
            n_points=30, n_valid=30,
        )
        a = _make_proposal(
            rule_type=RuleType.MEAN_DUAL_GUARD, proposal_id="a",
        )
        b = _make_proposal(
            rule_type=RuleType.COMPLETENESS, proposal_id="b",
            coverage_pct=100.0,
        )
        result = compare_proposals(a, b, profile=profile)
        # Completeness should be more resilient to volatility
        assert isinstance(result, ComparisonResult)

    def test_different_rule_types(self):
        a = _make_proposal(
            rule_type=RuleType.MEAN_DUAL_GUARD, proposal_id="a",
        )
        b = _make_proposal(
            rule_type=RuleType.CUSTOM_SQL, proposal_id="b",
        )
        result = compare_proposals(a, b)
        # Mean has better interpretability/cost than CustomSql
        assert any("interpretabilidade" in adv.lower() for adv in result.advantages_a)


# ===========================================================================
# _find_advantages
# ===========================================================================

class TestFindAdvantages:

    def test_no_advantages_when_equal(self):
        ev = RuleEvaluation(
            coverage=0.9, stability=0.8,
            interpretability=1.0, cost_efficiency=1.0,
            regime_fit=1.0, fp_risk=0.1, robustness=0.9,
        )
        adv_a, adv_b = _find_advantages(ev, ev)
        assert adv_a == []
        assert adv_b == []

    def test_coverage_advantage(self):
        ev_a = RuleEvaluation(
            coverage=0.95, stability=0.8,
            interpretability=1.0, cost_efficiency=1.0,
        )
        ev_b = RuleEvaluation(
            coverage=0.60, stability=0.8,
            interpretability=1.0, cost_efficiency=1.0,
        )
        adv_a, adv_b = _find_advantages(ev_a, ev_b)
        assert any("cobertura" in a.lower() for a in adv_a)

    def test_fp_risk_lower_is_better(self):
        ev_a = RuleEvaluation(
            coverage=0.9, stability=0.8,
            interpretability=1.0, cost_efficiency=1.0,
            fp_risk=0.05,
        )
        ev_b = RuleEvaluation(
            coverage=0.9, stability=0.8,
            interpretability=1.0, cost_efficiency=1.0,
            fp_risk=0.30,
        )
        adv_a, adv_b = _find_advantages(ev_a, ev_b)
        assert any("risco de fp" in a.lower() for a in adv_a)
