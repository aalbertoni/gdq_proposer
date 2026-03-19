"""Tests for core/backtest_analysis.py."""

import pytest

from core.backtest_analysis import (
    analyze_backtest,
    summarize_backtest_analysis,
    BacktestAnalysis,
)
from core.models.rule_proposal import BacktestSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bt(results: list[dict]) -> BacktestSummary:
    """Create BacktestSummary with given point_results."""
    n_pass = sum(1 for r in results if r["passed"])
    n_fail = len(results) - n_pass
    coverage = (n_pass / len(results) * 100) if results else 0.0
    return BacktestSummary(
        total_periods=len(results),
        periods_pass=n_pass,
        periods_fail=n_fail,
        coverage_pct=coverage,
        false_positive_proxy=0,
        band_width_ratio=0.15,
        stability_score=0.8,
        has_drift=False,
        point_results=results,
    )


def _pass(i: int, val: float = 100.0) -> dict:
    return {"index": i, "value": val, "passed": True}


def _fail(i: int, val: float = 200.0) -> dict:
    return {"index": i, "value": val, "passed": False}


# ===========================================================================
# analyze_backtest
# ===========================================================================

class TestAnalyzeBacktest:

    def test_empty_results(self):
        bt = _make_bt([])
        a = analyze_backtest(bt)
        assert a.max_fail_streak == 0
        assert a.violation_rate == 0.0

    def test_all_pass(self):
        results = [_pass(i) for i in range(20)]
        a = analyze_backtest(_make_bt(results))
        assert a.max_fail_streak == 0
        assert a.max_pass_streak == 20
        assert a.violation_rate == 0.0
        assert a.current_streak_type == "pass"
        assert a.current_streak_length == 20

    def test_all_fail(self):
        results = [_fail(i) for i in range(10)]
        a = analyze_backtest(_make_bt(results))
        assert a.max_fail_streak == 10
        assert a.max_pass_streak == 0
        assert a.violation_rate == 1.0
        assert a.current_streak_type == "fail"

    def test_alternating(self):
        results = [
            _pass(0), _fail(1), _pass(2), _fail(3), _pass(4),
        ]
        a = analyze_backtest(_make_bt(results))
        assert a.max_fail_streak == 1
        assert a.max_pass_streak == 1

    def test_fail_streak_in_middle(self):
        results = (
            [_pass(i) for i in range(5)]
            + [_fail(i) for i in range(5, 9)]
            + [_pass(i) for i in range(9, 15)]
        )
        a = analyze_backtest(_make_bt(results))
        assert a.max_fail_streak == 4
        assert a.first_fail_index == 5
        assert a.last_fail_index == 8

    def test_recent_violation_rate(self):
        # 20 passes then 5 fails
        results = [_pass(i) for i in range(20)] + [_fail(i) for i in range(20, 25)]
        a = analyze_backtest(_make_bt(results))
        # Recent 7: 2 pass + 5 fail
        assert a.recent_violation_rate > a.violation_rate

    def test_tail_risk(self):
        # 20 passes then 5 fails (last 20% = last 5)
        results = [_pass(i) for i in range(20)] + [_fail(i) for i in range(20, 25)]
        a = analyze_backtest(_make_bt(results))
        assert a.tail_risk == 1.0  # all 5 tail points failed

    def test_current_streak_fail(self):
        results = [_pass(0), _pass(1), _fail(2), _fail(3)]
        a = analyze_backtest(_make_bt(results))
        assert a.current_streak_type == "fail"
        assert a.current_streak_length == 2

    def test_first_last_fail_none_when_all_pass(self):
        results = [_pass(i) for i in range(10)]
        a = analyze_backtest(_make_bt(results))
        assert a.first_fail_index is None
        assert a.last_fail_index is None


# ===========================================================================
# summarize_backtest_analysis
# ===========================================================================

class TestSummarizeBacktestAnalysis:

    def test_perfect_coverage(self):
        a = BacktestAnalysis(
            max_pass_streak=20, violation_rate=0.0,
        )
        text = summarize_backtest_analysis(a)
        assert "perfeita" in text.lower()

    def test_long_fail_streak_flagged(self):
        a = BacktestAnalysis(max_fail_streak=5, violation_rate=0.2)
        text = summarize_backtest_analysis(a)
        assert "5" in text
        assert "consecutivos" in text

    def test_recent_degradation_flagged(self):
        a = BacktestAnalysis(
            violation_rate=0.10,
            recent_violation_rate=0.40,
        )
        text = summarize_backtest_analysis(a)
        assert "degradacao" in text.lower()

    def test_high_tail_risk_flagged(self):
        a = BacktestAnalysis(tail_risk=0.50, violation_rate=0.20)
        text = summarize_backtest_analysis(a)
        assert "cauda" in text.lower()

    def test_good_result_empty(self):
        a = BacktestAnalysis(
            max_fail_streak=1, max_pass_streak=15,
            violation_rate=0.05, recent_violation_rate=0.05,
            tail_risk=0.05,
        )
        text = summarize_backtest_analysis(a)
        assert text == ""
