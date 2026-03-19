"""
Sprint D.1b tests: Percentile rules via CustomSql dual guard.

Covers:
1. GDQRuleGenerator._generate_percentile_custom_sql: syntax, dual guard, overrides
2. ProposalService.propose_percentile_rules: default/custom levels, empty history, fields
3. Rule scoring: _INTERPRETABILITY and _COST_EFFICIENCY for NUMERIC_PERCENTILE_BAND
4. Rule explainer: explain_rule and explain_rule_detail for percentile proposals
5. Numeric history DataFrame with 9 percentile columns (p01..p99)
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from core.gdq_rule_generator import GDQRuleGenerator
from core.models.baseline import BaselineStrategy
from core.models.enums import (
    BaselineMethod,
    ConfidenceLevel,
    MetricRef,
    RuleType,
)
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.rule_selection import UserOverride
from core.rule_explainer import explain_rule, explain_rule_detail
from core.rule_scoring import _COST_EFFICIENCY, _INTERPRETABILITY
from services.proposal_service import ProposalService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_history(n: int = 30) -> pd.DataFrame:
    """Create a fake numeric history DataFrame with 9 percentile columns."""
    today = date.today()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(n)]
    np.random.seed(42)
    return pd.DataFrame({
        "period": dates,
        "mean": np.random.normal(100, 5, n),
        "stddev": np.random.normal(10, 1, n),
        "min": np.random.normal(50, 5, n),
        "max": np.random.normal(150, 5, n),
        "p01": np.random.normal(55, 2, n),
        "p05": np.random.normal(60, 2, n),
        "p10": np.random.normal(65, 2, n),
        "p25": np.random.normal(75, 3, n),
        "p50": np.random.normal(100, 4, n),
        "p75": np.random.normal(125, 3, n),
        "p90": np.random.normal(135, 2, n),
        "p95": np.random.normal(140, 2, n),
        "p99": np.random.normal(145, 2, n),
        "non_null_count": [100] * n,
        "null_count": [0] * n,
        "total_count": [100] * n,
    })


def _make_baseline(**kwargs) -> BaselineStrategy:
    """Create a BaselineStrategy with sensible defaults."""
    defaults = dict(
        method=BaselineMethod.LAST_N_PERIODS,
        n_periods=30,
        n_sigma=2.0,
        margin_pct=0.10,
    )
    defaults.update(kwargs)
    return BaselineStrategy(**defaults)


def _make_percentile_proposal(
    pct_col: str = "p10",
    pct_value: str = "0.10",
    target_column: str = "VLR_SALDO",
    **kwargs,
) -> RuleProposal:
    """Create a RuleProposal of type NUMERIC_PERCENTILE_BAND for testing."""
    defaults = dict(
        id="test-pct-001",
        target_column=target_column,
        target_table="tb_test",
        rule_type=RuleType.NUMERIC_PERCENTILE_BAND,
        metric_name=pct_col,
        suggested_values=[pct_value],
        baseline_window=30,
        baseline_n_sigma=2.0,
        baseline_margin_pct=0.10,
    )
    defaults.update(kwargs)
    return RuleProposal(**defaults)


# ===========================================================================
# 1. GDQ Generator: _generate_percentile_custom_sql
# ===========================================================================

class TestGDQGeneratorPercentile:
    """Tests for GDQRuleGenerator._generate_percentile_custom_sql."""

    def setup_method(self):
        self.generator = GDQRuleGenerator()

    def test_syntax_contains_approx_percentile_and_from_primary(self):
        """Generated syntax must contain approx_percentile and 'from primary'."""
        proposal = _make_percentile_proposal(
            pct_col="p10", pct_value="0.10", target_column="VLR_SALDO",
        )
        syntax = self.generator.generate(proposal)

        assert "approx_percentile" in syntax, (
            f"Expected 'approx_percentile' in syntax: {syntax}"
        )
        assert "from primary" in syntax, (
            f"Expected 'from primary' in syntax: {syntax}"
        )

    def test_syntax_contains_dual_guard_dynamic_functions(self):
        """Generated syntax must contain avg(last(N)) and std(last(N)) for dual guard."""
        proposal = _make_percentile_proposal(
            pct_col="p90", pct_value="0.90",
            baseline_window=20, baseline_n_sigma=3.0,
        )
        syntax = self.generator.generate(proposal)

        assert "avg(last(20))" in syntax, (
            f"Expected 'avg(last(20))' in syntax: {syntax}"
        )
        assert "std(last(20))" in syntax, (
            f"Expected 'std(last(20))' in syntax: {syntax}"
        )

    def test_overrides_custom_n_periods_and_n_sigma(self):
        """User overrides for n_periods and n_sigma must be reflected in syntax."""
        proposal = _make_percentile_proposal(
            pct_col="p50", pct_value="0.50",
            baseline_window=30, baseline_n_sigma=2.0,
        )
        overrides = UserOverride(custom_n_periods=15, custom_n_sigma=1.5)
        syntax = self.generator.generate(proposal, overrides)

        assert "avg(last(15))" in syntax, (
            f"Expected overridden 'avg(last(15))' in syntax: {syntax}"
        )
        assert "std(last(15))" in syntax, (
            f"Expected overridden 'std(last(15))' in syntax: {syntax}"
        )

    def test_syntax_uses_correct_column_name(self):
        """The SQL expression inside CustomSql must reference the correct column."""
        proposal = _make_percentile_proposal(
            pct_col="p25", pct_value="0.25", target_column="TAXA_JUROS",
        )
        syntax = self.generator.generate(proposal)

        assert "TAXA_JUROS" in syntax, (
            f"Expected column 'TAXA_JUROS' in syntax: {syntax}"
        )
        assert "0.25" in syntax, (
            f"Expected percentile value '0.25' in syntax: {syntax}"
        )

    def test_syntax_uses_correct_pct_value_from_suggested_values(self):
        """Percentile fraction comes from proposal.suggested_values[0]."""
        proposal = _make_percentile_proposal(
            pct_col="p99", pct_value="0.99",
        )
        syntax = self.generator.generate(proposal)

        assert "0.99" in syntax, (
            f"Expected '0.99' in syntax: {syntax}"
        )

    def test_syntax_is_customsql_dual_guard_format(self):
        """Syntax must follow CustomSql dual guard: ((...sigma...) OR (...margin...))."""
        proposal = _make_percentile_proposal()
        syntax = self.generator.generate(proposal)

        # CustomSql dual guard has OR between sigma and margin bands
        assert " OR " in syntax or " or " in syntax.lower(), (
            f"Expected 'OR' in dual guard syntax: {syntax}"
        )
        # Must start with CustomSql or contain it
        assert "CustomSql" in syntax, (
            f"Expected 'CustomSql' keyword in syntax: {syntax}"
        )

    def test_override_margin_pct(self):
        """Override for margin_pct must change the margin band."""
        proposal = _make_percentile_proposal()

        syntax_default = self.generator.generate(proposal)

        overrides = UserOverride(custom_margin_pct=0.20)
        syntax_override = self.generator.generate(proposal, overrides)

        # Different margin should produce different syntax
        assert syntax_default != syntax_override, (
            "Overriding margin_pct should produce different syntax"
        )


# ===========================================================================
# 2. ProposalService.propose_percentile_rules
# ===========================================================================

class TestProposalServicePercentileRules:
    """Tests for ProposalService.propose_percentile_rules."""

    def setup_method(self):
        self.service = ProposalService()
        self.baseline = _make_baseline()

    def test_default_levels_returns_two_proposals(self):
        """Default percentile_levels=['p10', 'p90'] should return 2 proposals."""
        history = _make_history(30)
        proposals = self.service.propose_percentile_rules(
            history=history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        assert len(proposals) == 2, (
            f"Expected 2 proposals (p10, p90), got {len(proposals)}"
        )

    def test_custom_levels_returns_correct_count(self):
        """Custom levels ['p05', 'p95', 'p99'] should return 3 proposals."""
        history = _make_history(30)
        proposals = self.service.propose_percentile_rules(
            history=history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
            percentile_levels=["p05", "p95", "p99"],
        )
        assert len(proposals) == 3, (
            f"Expected 3 proposals, got {len(proposals)}"
        )

    def test_empty_history_returns_empty_list(self):
        """Empty history DataFrame should return no proposals."""
        empty_df = pd.DataFrame()
        proposals = self.service.propose_percentile_rules(
            history=empty_df, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        assert proposals == [], (
            f"Expected empty list for empty history, got {len(proposals)} proposals"
        )

    def test_each_proposal_has_correct_rule_type(self):
        """Each proposal must have rule_type=NUMERIC_PERCENTILE_BAND."""
        history = _make_history(30)
        proposals = self.service.propose_percentile_rules(
            history=history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        for p in proposals:
            assert p.rule_type == RuleType.NUMERIC_PERCENTILE_BAND, (
                f"Expected NUMERIC_PERCENTILE_BAND, got {p.rule_type}"
            )

    def test_each_proposal_has_correct_metric_name(self):
        """Metric name should match the percentile level (e.g., 'p10', 'p90')."""
        history = _make_history(30)
        proposals = self.service.propose_percentile_rules(
            history=history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        metric_names = [p.metric_name for p in proposals]
        assert "p10" in metric_names, f"Expected 'p10' in {metric_names}"
        assert "p90" in metric_names, f"Expected 'p90' in {metric_names}"

    def test_each_proposal_has_valid_gdq_syntax_preview(self):
        """Each proposal must have a non-empty gdq_syntax_preview with CustomSql."""
        history = _make_history(30)
        proposals = self.service.propose_percentile_rules(
            history=history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        for p in proposals:
            assert p.gdq_syntax_preview, (
                f"Expected non-empty gdq_syntax_preview for {p.metric_name}"
            )
            assert "CustomSql" in p.gdq_syntax_preview, (
                f"Expected 'CustomSql' in syntax for {p.metric_name}: "
                f"{p.gdq_syntax_preview}"
            )

    def test_each_proposal_has_backtest(self):
        """Each proposal must have a BacktestSummary populated."""
        history = _make_history(30)
        proposals = self.service.propose_percentile_rules(
            history=history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        for p in proposals:
            assert p.backtest is not None, (
                f"Expected backtest for {p.metric_name}"
            )
            assert p.backtest.total_periods > 0, (
                f"Expected positive total_periods for {p.metric_name}"
            )

    def test_each_proposal_has_confidence_level(self):
        """Each proposal must have a valid ConfidenceLevel."""
        history = _make_history(30)
        proposals = self.service.propose_percentile_rules(
            history=history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        for p in proposals:
            assert p.confidence in (
                ConfidenceLevel.HIGH,
                ConfidenceLevel.MEDIUM,
                ConfidenceLevel.LOW,
            ), f"Unexpected confidence: {p.confidence}"

    def test_suggested_values_contains_pct_fraction(self):
        """suggested_values[0] should be the percentile fraction as string."""
        history = _make_history(30)
        proposals = self.service.propose_percentile_rules(
            history=history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
            percentile_levels=["p10", "p90"],
        )
        pct_map = {"p10": "0.1", "p90": "0.9"}
        for p in proposals:
            assert p.suggested_values is not None and len(p.suggested_values) > 0, (
                f"Expected suggested_values for {p.metric_name}"
            )
            expected = pct_map.get(p.metric_name)
            actual = float(p.suggested_values[0])
            assert abs(actual - float(expected)) < 1e-6, (
                f"Expected pct value ~{expected} for {p.metric_name}, got {actual}"
            )

    def test_missing_percentile_column_is_skipped(self):
        """If a requested percentile column is not in the history, it is skipped."""
        history = _make_history(30)
        proposals = self.service.propose_percentile_rules(
            history=history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
            percentile_levels=["p10", "p_nonexistent"],
        )
        # Only p10 should produce a proposal; p_nonexistent is silently skipped
        assert len(proposals) == 1, (
            f"Expected 1 proposal (p10 only), got {len(proposals)}"
        )
        assert proposals[0].metric_name == "p10"

    def test_all_nine_percentile_levels(self):
        """All 9 percentile levels (p01..p99) should produce 9 proposals."""
        history = _make_history(30)
        all_levels = ["p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99"]
        proposals = self.service.propose_percentile_rules(
            history=history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
            percentile_levels=all_levels,
        )
        assert len(proposals) == 9, (
            f"Expected 9 proposals for all levels, got {len(proposals)}"
        )
        metric_names = {p.metric_name for p in proposals}
        assert metric_names == set(all_levels), (
            f"Expected all 9 levels, got {metric_names}"
        )


# ===========================================================================
# 3. Numeric history DataFrame: 9 percentile columns
# ===========================================================================

class TestNumericHistoryPercentileColumns:
    """Verify that _make_history produces 9 percentile columns."""

    def test_history_has_all_nine_percentile_columns(self):
        """The numeric history DataFrame must have p01, p05, p10, p25, p50, p75, p90, p95, p99."""
        history = _make_history(30)
        expected_cols = ["p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99"]
        for col in expected_cols:
            assert col in history.columns, (
                f"Missing percentile column '{col}' in history DataFrame"
            )

    def test_history_percentile_columns_have_numeric_data(self):
        """All percentile columns should contain numeric (float) data."""
        history = _make_history(30)
        pct_cols = ["p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99"]
        for col in pct_cols:
            assert history[col].dtype in ("float64", "float32"), (
                f"Column {col} has dtype {history[col].dtype}, expected float"
            )

    def test_history_has_expected_row_count(self):
        """History should have the requested number of rows."""
        for n in [10, 30, 50]:
            history = _make_history(n)
            assert len(history) == n, f"Expected {n} rows, got {len(history)}"


# ===========================================================================
# 4. Rule Scoring: _INTERPRETABILITY and _COST_EFFICIENCY
# ===========================================================================

class TestPercentileBandScoring:
    """Tests for scoring weights of NUMERIC_PERCENTILE_BAND."""

    def test_interpretability_is_0_8(self):
        """_INTERPRETABILITY[NUMERIC_PERCENTILE_BAND] must be 0.8."""
        assert RuleType.NUMERIC_PERCENTILE_BAND in _INTERPRETABILITY, (
            "NUMERIC_PERCENTILE_BAND missing from _INTERPRETABILITY"
        )
        assert _INTERPRETABILITY[RuleType.NUMERIC_PERCENTILE_BAND] == 0.8, (
            f"Expected 0.8, got {_INTERPRETABILITY[RuleType.NUMERIC_PERCENTILE_BAND]}"
        )

    def test_cost_efficiency_is_0_7(self):
        """_COST_EFFICIENCY[NUMERIC_PERCENTILE_BAND] must be 0.7."""
        assert RuleType.NUMERIC_PERCENTILE_BAND in _COST_EFFICIENCY, (
            "NUMERIC_PERCENTILE_BAND missing from _COST_EFFICIENCY"
        )
        assert _COST_EFFICIENCY[RuleType.NUMERIC_PERCENTILE_BAND] == 0.7, (
            f"Expected 0.7, got {_COST_EFFICIENCY[RuleType.NUMERIC_PERCENTILE_BAND]}"
        )


# ===========================================================================
# 5. Rule Explainer: explain_rule and explain_rule_detail
# ===========================================================================

class TestPercentileRuleExplainer:
    """Tests for explain_rule and explain_rule_detail with percentile proposals."""

    def test_explain_rule_contains_percentile_label(self):
        """explain_rule for a percentile proposal should mention the percentile label."""
        proposal = _make_percentile_proposal(pct_col="p10", pct_value="0.10")
        text = explain_rule(proposal)

        assert "P10" in text, (
            f"Expected 'P10' in explanation: {text}"
        )

    def test_explain_rule_p90_contains_label(self):
        """explain_rule for p90 should mention P90."""
        proposal = _make_percentile_proposal(pct_col="p90", pct_value="0.90")
        text = explain_rule(proposal)

        assert "P90" in text, (
            f"Expected 'P90' in explanation: {text}"
        )

    def test_explain_rule_contains_percentil_keyword(self):
        """explain_rule for a percentile proposal should contain 'percentil'."""
        proposal = _make_percentile_proposal(pct_col="p50", pct_value="0.50")
        text = explain_rule(proposal)

        assert "percentil" in text.lower(), (
            f"Expected 'percentil' (pt-BR) in explanation: {text}"
        )

    def test_explain_rule_mentions_column_name(self):
        """explain_rule should mention the target column."""
        proposal = _make_percentile_proposal(
            pct_col="p25", pct_value="0.25", target_column="TAXA_JUROS",
        )
        text = explain_rule(proposal)

        assert "TAXA_JUROS" in text, (
            f"Expected column 'TAXA_JUROS' in explanation: {text}"
        )

    def test_explain_rule_mentions_n_periods(self):
        """explain_rule should mention the number of periods."""
        proposal = _make_percentile_proposal(baseline_window=20)
        text = explain_rule(proposal)

        assert "20" in text, (
            f"Expected '20' (n_periods) in explanation: {text}"
        )

    def test_explain_rule_detail_contains_parametros(self):
        """explain_rule_detail must contain a 'Parametros' section."""
        proposal = _make_percentile_proposal()
        text = explain_rule_detail(proposal)

        assert "Parametros" in text, (
            f"Expected 'Parametros' section in detail: {text}"
        )

    def test_explain_rule_detail_contains_evidencia_with_backtest(self):
        """explain_rule_detail with a backtest must contain an 'Evidencia' section."""
        proposal = _make_percentile_proposal()
        proposal.backtest = BacktestSummary(
            total_periods=30,
            periods_pass=28,
            periods_fail=2,
            coverage_pct=93.3,
            false_positive_proxy=1,
            band_width_ratio=0.15,
            stability_score=0.90,
            has_drift=False,
        )
        text = explain_rule_detail(proposal)

        assert "Evidencia" in text, (
            f"Expected 'Evidencia' section in detail: {text}"
        )

    def test_explain_rule_detail_no_backtest_no_evidencia(self):
        """explain_rule_detail without backtest should not have 'Evidencia' section."""
        proposal = _make_percentile_proposal()
        proposal.backtest = None
        text = explain_rule_detail(proposal)

        assert "Evidencia" not in text, (
            f"Did not expect 'Evidencia' section without backtest: {text}"
        )

    def test_explain_rule_detail_params_contain_janela_sigma_margem(self):
        """Parametros section should mention Janela, Sigma, and Margem."""
        proposal = _make_percentile_proposal(
            baseline_window=30, baseline_n_sigma=2.0, baseline_margin_pct=0.10,
        )
        text = explain_rule_detail(proposal)

        assert "Janela" in text, f"Expected 'Janela' in params: {text}"
        assert "Sigma" in text, f"Expected 'Sigma' in params: {text}"
        assert "Margem" in text, f"Expected 'Margem' in params: {text}"


# ===========================================================================
# 6. Integration: ProposalService end-to-end with scoring and syntax
# ===========================================================================

class TestPercentileEndToEnd:
    """End-to-end tests: propose -> score -> syntax -> explain."""

    def setup_method(self):
        self.service = ProposalService()
        self.baseline = _make_baseline()
        self.history = _make_history(30)

    def test_proposal_syntax_is_valid_customsql(self):
        """Generated proposals should have valid CustomSql dual guard syntax."""
        proposals = self.service.propose_percentile_rules(
            history=self.history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        for p in proposals:
            syntax = p.gdq_syntax_preview
            assert syntax.startswith("("), (
                f"Dual guard syntax should start with '(': {syntax[:80]}"
            )
            # Check balanced parentheses
            open_count = syntax.count("(")
            close_count = syntax.count(")")
            assert open_count == close_count, (
                f"Unbalanced parentheses ({open_count} open, {close_count} close) "
                f"in: {syntax[:100]}"
            )

    def test_proposal_history_values_populated(self):
        """Proposals should have history_values and history_dates populated."""
        proposals = self.service.propose_percentile_rules(
            history=self.history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        for p in proposals:
            assert len(p.history_values) == 30, (
                f"Expected 30 history values, got {len(p.history_values)}"
            )
            assert len(p.history_dates) == 30, (
                f"Expected 30 history dates, got {len(p.history_dates)}"
            )

    def test_proposal_suggested_bounds_are_numeric(self):
        """suggested_lower and suggested_upper should be numeric and non-None."""
        proposals = self.service.propose_percentile_rules(
            history=self.history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        for p in proposals:
            assert p.suggested_lower is not None, (
                f"Expected numeric suggested_lower for {p.metric_name}"
            )
            assert p.suggested_upper is not None, (
                f"Expected numeric suggested_upper for {p.metric_name}"
            )
            assert p.suggested_lower < p.suggested_upper, (
                f"Expected lower < upper for {p.metric_name}: "
                f"{p.suggested_lower} >= {p.suggested_upper}"
            )

    def test_explain_works_on_real_proposals(self):
        """explain_rule and explain_rule_detail should work on actual proposals."""
        proposals = self.service.propose_percentile_rules(
            history=self.history, column="VLR_SALDO", table="tb_test",
            baseline=self.baseline,
        )
        for p in proposals:
            text = explain_rule(p)
            assert len(text) > 20, (
                f"Explanation too short for {p.metric_name}: {text}"
            )
            detail = explain_rule_detail(p)
            assert len(detail) > 0, (
                f"Detail should not be empty for {p.metric_name}"
            )
