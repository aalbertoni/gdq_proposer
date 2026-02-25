"""Testes para strategies/row_count_strategy.py."""

import math

import pytest

from core.models.baseline import BaselineStrategy
from core.models.enums import BaselineMethod, ConfidenceLevel, RuleType
from core.models.rule_proposal import RuleProposal
from strategies.row_count_strategy import (
    GenericBandRowCountStrategy,
    RowCountStrategy,
)
from tests.fixtures import make_stable_series, make_drift_series


@pytest.fixture
def strategy():
    return GenericBandRowCountStrategy()


@pytest.fixture
def baseline():
    return BaselineStrategy(
        method=BaselineMethod.LAST_N_PERIODS,
        n_periods=20,
        n_sigma=2.0,
        margin_pct=0.10,
        min_history_points=7,
    )


@pytest.fixture
def stable_row_counts():
    """Serie estavel simulando row counts ~1000."""
    data = make_stable_series(n=30, seed=42)
    # Escalar para parecer row counts (x10)
    return {
        "values": [v * 10 for v in data["values"]],
        "dates": data["dates"],
    }


@pytest.fixture
def drift_row_counts():
    """Serie com drift simulando row counts crescentes."""
    data = make_drift_series(n=30)
    return {
        "values": [v * 10 for v in data["values"]],
        "dates": data["dates"],
    }


class TestProtocolCompliance:
    def test_generic_strategy_is_protocol_compliant(self):
        strategy = GenericBandRowCountStrategy()
        assert isinstance(strategy, RowCountStrategy)


class TestGenericStrategyPropose:
    def test_stable_series_produces_proposal(
        self, strategy, stable_row_counts, baseline,
    ):
        proposal = strategy.propose(
            stable_row_counts["values"],
            stable_row_counts["dates"],
            "tb_test",
            baseline,
        )
        assert proposal is not None
        assert proposal.rule_type == RuleType.ROW_COUNT_DUAL_GUARD
        assert proposal.target_column is None
        assert proposal.target_table == "tb_test"

    def test_stable_series_high_confidence(
        self, strategy, stable_row_counts, baseline,
    ):
        proposal = strategy.propose(
            stable_row_counts["values"],
            stable_row_counts["dates"],
            "tb_test",
            baseline,
        )
        assert proposal is not None
        assert proposal.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)

    def test_produces_rowcount_syntax(
        self, strategy, stable_row_counts, baseline,
    ):
        proposal = strategy.propose(
            stable_row_counts["values"],
            stable_row_counts["dates"],
            "tb_test",
            baseline,
        )
        assert proposal is not None
        assert "RowCount" in proposal.gdq_syntax_preview
        assert "avg(last(" in proposal.gdq_syntax_preview
        assert "2.0 *" in proposal.gdq_syntax_preview

    def test_has_backtest(self, strategy, stable_row_counts, baseline):
        proposal = strategy.propose(
            stable_row_counts["values"],
            stable_row_counts["dates"],
            "tb_test",
            baseline,
        )
        assert proposal is not None
        assert proposal.backtest is not None
        assert proposal.backtest.total_periods > 0
        assert proposal.backtest.coverage_pct > 0

    def test_drift_series_has_warnings(
        self, strategy, drift_row_counts, baseline,
    ):
        proposal = strategy.propose(
            drift_row_counts["values"],
            drift_row_counts["dates"],
            "tb_test",
            baseline,
        )
        assert proposal is not None
        assert proposal.backtest is not None
        assert proposal.backtest.has_drift

    def test_insufficient_data_returns_none(self, strategy, baseline):
        proposal = strategy.propose(
            [100.0, 200.0],
            ["2026-01-01", "2026-01-02"],
            "tb_test",
            baseline,
        )
        assert proposal is None


class TestGenericStrategyRecalculate:
    def test_recalculate_changes_window(
        self, strategy, stable_row_counts, baseline,
    ):
        proposal = strategy.propose(
            stable_row_counts["values"],
            stable_row_counts["dates"],
            "tb_test",
            baseline,
        )
        assert proposal is not None
        original_syntax = proposal.gdq_syntax_preview

        new_baseline = BaselineStrategy(n_periods=10, n_sigma=3.0)
        updated = strategy.recalculate(proposal, new_baseline)
        assert updated.baseline_window == 10
        assert "last(10)" in updated.gdq_syntax_preview
        assert "3.0 *" in updated.gdq_syntax_preview

    def test_recalculate_updates_backtest(
        self, strategy, stable_row_counts, baseline,
    ):
        proposal = strategy.propose(
            stable_row_counts["values"],
            stable_row_counts["dates"],
            "tb_test",
            baseline,
        )
        assert proposal is not None

        new_baseline = BaselineStrategy(n_periods=10, n_sigma=1.0)
        updated = strategy.recalculate(proposal, new_baseline)
        assert updated.backtest is not None

    def test_recalculate_empty_history_noop(self, strategy):
        proposal = RuleProposal(
            id="test", target_column=None, target_table="tb_test",
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD, metric_name="row_count",
        )
        new_baseline = BaselineStrategy(n_periods=10)
        result = strategy.recalculate(proposal, new_baseline)
        assert result.backtest is None  # unchanged
