"""Testes para core/rule_scoring.py."""

import pytest

from core.rule_scoring import score_proposal, RuleScore
from core.models.enums import ConfidenceLevel, RuleType
from core.models.rule_proposal import BacktestSummary, RuleProposal
from tests.fixtures import make_stable_series, make_regime_change_series


def _make_proposal(
    backtest: BacktestSummary | None = None,
    rule_type: RuleType = RuleType.MEAN_DUAL_GUARD,
    warnings: list[str] | None = None,
) -> RuleProposal:
    return RuleProposal(
        id="test-001",
        target_column="VLR_SALDO",
        target_table="tb_test",
        rule_type=rule_type,
        metric_name="mean",
        backtest=backtest,
        warnings=warnings or [],
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


def _make_poor_backtest() -> BacktestSummary:
    return BacktestSummary(
        total_periods=30,
        periods_pass=15,
        periods_fail=15,
        coverage_pct=50.0,
        false_positive_proxy=5,
        band_width_ratio=1.5,
        stability_score=0.3,
        has_drift=True,
    )


class TestScoreProposal:
    def test_high_quality_gets_high_confidence(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        history = make_stable_series(n=30)["values"]
        score = score_proposal(proposal, history)
        assert score.confidence == ConfidenceLevel.HIGH
        assert score.score_total >= 0.80

    def test_poor_quality_gets_low_or_medium_confidence(self):
        bt = _make_poor_backtest()
        proposal = _make_proposal(backtest=bt)
        history = make_regime_change_series(n=30)["values"]
        score = score_proposal(proposal, history)
        # Coverage 50% + stability 0.3 = low data quality,
        # but interpretability/cost push total up. Should not be HIGH.
        assert score.confidence != ConfidenceLevel.HIGH
        assert score.score_total < 0.80

    def test_no_backtest_returns_low(self):
        proposal = _make_proposal(backtest=None)
        score = score_proposal(proposal)
        assert score.confidence == ConfidenceLevel.LOW
        assert "Backtest não executado" in score.warnings

    def test_insufficient_data_forces_low(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        history = [100.0, 101.0]  # only 2 points
        score = score_proposal(proposal, history)
        assert score.confidence == ConfidenceLevel.LOW
        assert any("insuficientes" in w.lower() for w in score.warnings)

    def test_drift_warning(self):
        bt = _make_good_backtest()
        bt.has_drift = True
        proposal = _make_proposal(backtest=bt)
        history = make_stable_series(n=30)["values"]
        score = score_proposal(proposal, history)
        assert any("tendência" in w.lower() for w in score.warnings)

    def test_false_positive_warning(self):
        bt = _make_good_backtest()
        bt.false_positive_proxy = 3
        proposal = _make_proposal(backtest=bt)
        score = score_proposal(proposal)
        assert any("falsos positivos" in w.lower() for w in score.warnings)

    def test_wide_band_warning(self):
        bt = _make_good_backtest()
        bt.band_width_ratio = 2.0
        proposal = _make_proposal(backtest=bt)
        score = score_proposal(proposal)
        assert any("larga" in w.lower() for w in score.warnings)

    def test_coverage_normalized(self):
        bt = _make_good_backtest()
        bt.coverage_pct = 96.67
        proposal = _make_proposal(backtest=bt)
        score = score_proposal(proposal)
        assert 0.96 < score.coverage < 0.97

    def test_interpretability_by_rule_type(self):
        bt = _make_good_backtest()
        mean_proposal = _make_proposal(backtest=bt, rule_type=RuleType.MEAN_DUAL_GUARD)
        custom_proposal = _make_proposal(backtest=bt, rule_type=RuleType.CUSTOM_SQL)
        score_mean = score_proposal(mean_proposal)
        score_custom = score_proposal(custom_proposal)
        assert score_mean.interpretability > score_custom.interpretability

    def test_recommendation_text(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        score = score_proposal(proposal, make_stable_series(n=30)["values"])
        assert "produção" in score.recommendation.lower()

    def test_medium_confidence_range(self):
        bt = BacktestSummary(
            total_periods=30, periods_pass=22, periods_fail=8,
            coverage_pct=73.0, false_positive_proxy=2,
            band_width_ratio=0.5, stability_score=0.5,
            has_drift=False,
        )
        proposal = _make_proposal(backtest=bt)
        history = make_stable_series(n=30)["values"]
        score = score_proposal(proposal, history)
        assert score.confidence == ConfidenceLevel.MEDIUM

    def test_existing_warnings_preserved(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt, warnings=["Teste existente"])
        score = score_proposal(proposal)
        assert "Teste existente" in score.warnings

    def test_score_total_range(self):
        bt = _make_good_backtest()
        proposal = _make_proposal(backtest=bt)
        score = score_proposal(proposal)
        assert 0.0 <= score.score_total <= 1.0
