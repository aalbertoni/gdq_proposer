"""Testes para services/proposal_service.py."""

import math

import pandas as pd
import pytest

from core.models.baseline import BaselineStrategy
from core.models.enums import BaselineMethod, ConfidenceLevel, RuleType
from core.models.rule_proposal import RuleProposal
from services.proposal_service import ProposalService
from tests.fixtures import make_stable_series


@pytest.fixture
def service():
    return ProposalService()


@pytest.fixture
def stable_history():
    """DataFrame simulando saída do get_numeric_history com dados estáveis."""
    data = make_stable_series(n=30)
    return pd.DataFrame({
        "period": data["dates"],
        "mean": data["values"],
        "stddev": [5.0 + i * 0.01 for i in range(30)],
        "min": [v - 10 for v in data["values"]],
        "max": [v + 10 for v in data["values"]],
        "p01": [v - 12 for v in data["values"]],
        "p05": [v - 10 for v in data["values"]],
        "p25": [v - 3 for v in data["values"]],
        "p50": data["values"],
        "p75": [v + 3 for v in data["values"]],
        "p95": [v + 10 for v in data["values"]],
        "p99": [v + 12 for v in data["values"]],
        "non_null_count": [1000] * 30,
        "null_count": [0] * 30,
        "total_count": [1000] * 30,
    })


@pytest.fixture
def baseline():
    return BaselineStrategy(
        method=BaselineMethod.LAST_N_PERIODS,
        n_periods=20,
        n_sigma=2.0,
        margin_pct=0.10,
        min_history_points=7,
    )


class TestProposeNumericRules:
    def test_returns_three_proposals(self, service, stable_history, baseline):
        proposals = service.propose_numeric_rules(
            stable_history, "VLR_SALDO", "tb_test", baseline,
        )
        # Mean + StdDev + Completeness
        types = [p.rule_type for p in proposals]
        assert RuleType.MEAN_DUAL_GUARD in types
        assert RuleType.STDDEV_DUAL_GUARD in types
        assert RuleType.COMPLETENESS in types

    def test_mean_proposal_has_syntax(self, service, stable_history, baseline):
        proposals = service.propose_numeric_rules(
            stable_history, "VLR_SALDO", "tb_test", baseline,
        )
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert "Mean VLR_SALDO" in mean_p.gdq_syntax_preview
        assert "avg(last(" in mean_p.gdq_syntax_preview

    def test_mean_proposal_has_backtest(self, service, stable_history, baseline):
        proposals = service.propose_numeric_rules(
            stable_history, "VLR_SALDO", "tb_test", baseline,
        )
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert mean_p.backtest is not None
        assert mean_p.backtest.total_periods > 0

    def test_mean_proposal_has_score(self, service, stable_history, baseline):
        proposals = service.propose_numeric_rules(
            stable_history, "VLR_SALDO", "tb_test", baseline,
        )
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert mean_p.confidence in (
            ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW,
        )

    def test_completeness_threshold_100(self, service, stable_history, baseline):
        proposals = service.propose_numeric_rules(
            stable_history, "VLR_SALDO", "tb_test", baseline,
        )
        comp_p = next(p for p in proposals if p.rule_type == RuleType.COMPLETENESS)
        assert comp_p.suggested_lower == 1.0
        assert "Completeness VLR_SALDO >= 1.00" == comp_p.gdq_syntax_preview

    def test_empty_history_returns_empty(self, service, baseline):
        empty_df = pd.DataFrame()
        proposals = service.propose_numeric_rules(
            empty_df, "VLR_SALDO", "tb_test", baseline,
        )
        assert proposals == []

    def test_unique_ids(self, service, stable_history, baseline):
        proposals = service.propose_numeric_rules(
            stable_history, "VLR_SALDO", "tb_test", baseline,
        )
        ids = [p.id for p in proposals]
        assert len(ids) == len(set(ids))


class TestRecalculateProposal:
    def test_recalculate_changes_window(self, service, stable_history, baseline):
        proposals = service.propose_numeric_rules(
            stable_history, "VLR_SALDO", "tb_test", baseline,
        )
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        original_syntax = mean_p.gdq_syntax_preview

        new_baseline = BaselineStrategy(n_periods=10, n_sigma=3.0)
        updated = service.recalculate_proposal(mean_p, new_baseline)
        assert updated.baseline_window == 10
        assert "last(10)" in updated.gdq_syntax_preview
        assert "3 *" in updated.gdq_syntax_preview

    def test_recalculate_updates_backtest(self, service, stable_history, baseline):
        proposals = service.propose_numeric_rules(
            stable_history, "VLR_SALDO", "tb_test", baseline,
        )
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        original_bt = mean_p.backtest.total_periods

        new_baseline = BaselineStrategy(n_periods=10, n_sigma=1.0)
        updated = service.recalculate_proposal(mean_p, new_baseline)
        assert updated.backtest is not None

    def test_recalculate_empty_history_noop(self, service):
        proposal = RuleProposal(
            id="test", target_column="COL", target_table="TBL",
            rule_type=RuleType.MEAN_DUAL_GUARD, metric_name="mean",
        )
        new_baseline = BaselineStrategy(n_periods=10)
        result = service.recalculate_proposal(proposal, new_baseline)
        assert result.backtest is None  # unchanged
