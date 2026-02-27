"""Testes para backtests de DistinctCount, AllowedValues, PrimaryKey e Uniqueness CustomSql.

Cobre as 4 novas funcoes de backtest em core/backtest.py e o novo
RuleType.UNIQUENESS_CUSTOM_SQL (gerador, scoring, explainer).
"""

import math

import pytest

from core.backtest import (
    backtest_allowed_values,
    backtest_distinct_count_exact,
    backtest_distinct_count_range,
    backtest_primary_key,
)
from core.gdq_rule_generator import GDQRuleGenerator
from core.models.enums import ConfidenceLevel, RuleType, RULE_TYPE_LABELS, get_rule_label
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.rule_explainer import explain_rule, explain_rule_detail
from core.rule_scoring import score_proposal


# ===========================================================================
# backtest_distinct_count_exact
# ===========================================================================

class TestBacktestDistinctCountExact:

    def test_empty_input(self):
        bt = backtest_distinct_count_exact([], [], expected_count=3)
        assert bt.total_periods == 0
        assert bt.coverage_pct == 0.0
        assert bt.has_drift is False

    def test_all_match(self):
        counts = [3.0] * 20
        dates = [f"d{i}" for i in range(20)]
        bt = backtest_distinct_count_exact(counts, dates, expected_count=3)
        assert bt.total_periods == 20
        assert bt.periods_pass == 20
        assert bt.periods_fail == 0
        assert bt.coverage_pct == 100.0
        assert bt.stability_score == 1.0
        assert bt.band_width_ratio == 0.0
        assert bt.outlier_periods == []

    def test_some_mismatches(self):
        counts = [3.0] * 15 + [4.0] * 5
        dates = [f"d{i}" for i in range(20)]
        bt = backtest_distinct_count_exact(counts, dates, expected_count=3)
        assert bt.periods_pass == 15
        assert bt.periods_fail == 5
        assert bt.coverage_pct == 75.0
        assert len(bt.outlier_periods) == 5

    def test_false_positive_proxy_borderline(self):
        """Periods where count differs by exactly 1 are FP proxy."""
        counts = [3.0] * 10 + [4.0] * 3 + [6.0] * 2
        dates = [f"d{i}" for i in range(15)]
        bt = backtest_distinct_count_exact(counts, dates, expected_count=3)
        # 4 differs by 1 -> FP proxy, 6 differs by 3 -> not FP
        assert bt.false_positive_proxy == 3
        assert bt.periods_fail == 5

    def test_nan_values_skipped(self):
        counts = [3.0, float("nan"), 3.0, float("nan"), 3.0]
        dates = [f"d{i}" for i in range(5)]
        bt = backtest_distinct_count_exact(counts, dates, expected_count=3)
        assert bt.total_periods == 3
        assert bt.periods_pass == 3

    def test_none_values_skipped(self):
        counts = [3.0, None, 3.0]
        dates = ["d0", "d1", "d2"]
        bt = backtest_distinct_count_exact(counts, dates, expected_count=3)
        assert bt.total_periods == 2
        assert bt.periods_pass == 2

    def test_drift_detected_increasing(self):
        """Monotonically increasing distinct counts should flag drift."""
        counts = [float(i) for i in range(3, 23)]  # 3, 4, 5, ..., 22
        dates = [f"d{i}" for i in range(20)]
        bt = backtest_distinct_count_exact(counts, dates, expected_count=3)
        assert bt.has_drift is True

    def test_no_drift_stable(self):
        counts = [3.0] * 20
        dates = [f"d{i}" for i in range(20)]
        bt = backtest_distinct_count_exact(counts, dates, expected_count=3)
        assert bt.has_drift is False

    def test_rounding_float_counts(self):
        """Float counts should be rounded to nearest int."""
        counts = [3.0, 2.9, 3.1, 2.5, 3.4]
        dates = [f"d{i}" for i in range(5)]
        bt = backtest_distinct_count_exact(counts, dates, expected_count=3)
        # 3.0 -> 3 (pass), 2.9 -> 3 (pass), 3.1 -> 3 (pass), 2.5 -> 2 (fail), 3.4 -> 3 (pass)
        assert bt.periods_pass == 4
        assert bt.periods_fail == 1


# ===========================================================================
# backtest_distinct_count_range
# ===========================================================================

class TestBacktestDistinctCountRange:

    def test_empty_input(self):
        bt = backtest_distinct_count_range([], [], lower=3, upper=5)
        assert bt.total_periods == 0
        assert bt.coverage_pct == 0.0

    def test_all_in_range(self):
        counts = [3.0, 4.0, 5.0, 4.0, 3.0] * 4
        dates = [f"d{i}" for i in range(20)]
        bt = backtest_distinct_count_range(counts, dates, lower=3, upper=5)
        assert bt.total_periods == 20
        assert bt.periods_pass == 20
        assert bt.coverage_pct == 100.0

    def test_out_of_range(self):
        counts = [3.0, 4.0, 6.0, 2.0, 5.0]
        dates = [f"d{i}" for i in range(5)]
        bt = backtest_distinct_count_range(counts, dates, lower=3, upper=5)
        # 3 (pass), 4 (pass), 6 (fail), 2 (fail), 5 (pass)
        assert bt.periods_pass == 3
        assert bt.periods_fail == 2
        assert bt.coverage_pct == 60.0

    def test_false_positive_proxy_just_outside(self):
        """Count just 1 outside range is FP proxy."""
        counts = [3.0, 4.0, 6.0, 2.0, 7.0]
        dates = [f"d{i}" for i in range(5)]
        bt = backtest_distinct_count_range(counts, dates, lower=3, upper=5)
        # 6 = upper+1 -> FP, 2 = lower-1 -> FP, 7 = upper+2 -> not FP
        assert bt.false_positive_proxy == 2

    def test_band_width_ratio(self):
        counts = [4.0] * 10
        dates = [f"d{i}" for i in range(10)]
        bt = backtest_distinct_count_range(counts, dates, lower=2, upper=6)
        # center = 4, width = 4, ratio = 4/4 = 1.0
        assert abs(bt.band_width_ratio - 1.0) < 0.01

    def test_nan_skipped(self):
        counts = [4.0, float("nan"), 4.0]
        dates = ["d0", "d1", "d2"]
        bt = backtest_distinct_count_range(counts, dates, lower=3, upper=5)
        assert bt.total_periods == 2

    def test_drift_detected(self):
        counts = [float(i) for i in range(3, 23)]
        dates = [f"d{i}" for i in range(20)]
        bt = backtest_distinct_count_range(counts, dates, lower=3, upper=5)
        assert bt.has_drift is True

    def test_stability_reflects_coverage(self):
        counts = [4.0] * 10
        dates = [f"d{i}" for i in range(10)]
        bt = backtest_distinct_count_range(counts, dates, lower=3, upper=5)
        assert bt.stability_score == 1.0


# ===========================================================================
# backtest_allowed_values
# ===========================================================================

class TestBacktestAllowedValues:

    def test_empty_input(self):
        bt = backtest_allowed_values({}, {"A", "B"})
        assert bt.total_periods == 0
        assert bt.coverage_pct == 0.0

    def test_all_within_allowed(self):
        period_map = {
            f"d{i}": {"A", "B"} for i in range(10)
        }
        bt = backtest_allowed_values(period_map, {"A", "B", "C"})
        assert bt.total_periods == 10
        assert bt.periods_pass == 10
        assert bt.coverage_pct == 100.0
        assert bt.outlier_periods == []

    def test_some_unexpected_values(self):
        period_map = {
            "d0": {"A", "B"},
            "d1": {"A", "B", "X"},  # X is unexpected
            "d2": {"A", "B"},
            "d3": {"A", "B", "Y"},  # Y is unexpected
            "d4": {"A", "B"},
        }
        bt = backtest_allowed_values(period_map, {"A", "B"})
        assert bt.periods_pass == 3
        assert bt.periods_fail == 2
        assert bt.coverage_pct == 60.0
        assert len(bt.outlier_periods) == 2

    def test_false_positive_single_unexpected(self):
        """Period with exactly 1 unexpected value is FP proxy (borderline)."""
        period_map = {
            "d0": {"A", "B", "X"},       # 1 unexpected -> FP
            "d1": {"A", "B", "X", "Y"},  # 2 unexpected -> not FP
        }
        bt = backtest_allowed_values(period_map, {"A", "B"})
        assert bt.false_positive_proxy == 1

    def test_empty_allowed_set(self):
        period_map = {"d0": {"A"}, "d1": set()}
        bt = backtest_allowed_values(period_map, set())
        # d0: {"A"} - set() = {"A"} -> fail; d1: set() - set() = set() -> pass
        assert bt.periods_pass == 1
        assert bt.periods_fail == 1

    def test_band_width_ratio_zero(self):
        """AllowedValues is a binary check, band_width_ratio should be 0."""
        period_map = {"d0": {"A"}}
        bt = backtest_allowed_values(period_map, {"A"})
        assert bt.band_width_ratio == 0.0

    def test_stability_reflects_coverage(self):
        period_map = {f"d{i}": {"A"} for i in range(10)}
        bt = backtest_allowed_values(period_map, {"A"})
        assert bt.stability_score == 1.0

    def test_drift_increasing_unexpected(self):
        """When unexpected values increase over time, should detect drift."""
        period_map = {}
        for i in range(10):
            # First 5 periods: no unexpected, last 5: increasing unexpected
            if i < 5:
                period_map[f"d{i:02d}"] = {"A", "B"}
            else:
                extras = {f"X{j}" for j in range(i - 4)}
                period_map[f"d{i:02d}"] = {"A", "B"} | extras
        bt = backtest_allowed_values(period_map, {"A", "B"})
        assert bt.periods_fail == 5

    def test_sorted_dates_in_outliers(self):
        """Outlier periods should be in sorted date order."""
        period_map = {
            "d03": {"A", "X"},
            "d01": {"A", "X"},
            "d02": {"A"},
            "d04": {"A"},
        }
        bt = backtest_allowed_values(period_map, {"A"})
        assert bt.outlier_periods == ["d01", "d03"]


# ===========================================================================
# backtest_primary_key
# ===========================================================================

class TestBacktestPrimaryKey:

    def test_empty_input(self):
        bt = backtest_primary_key([], [], {}, [])
        assert bt.total_periods == 0
        assert bt.coverage_pct == 0.0

    def test_perfect_pk(self):
        """No duplicates, no nulls -> 100% pass."""
        total_rows = [100, 100, 100]
        distinct_keys = [100, 100, 100]
        null_counts = {"col_a": [0, 0, 0], "col_b": [0, 0, 0]}
        dates = ["d0", "d1", "d2"]
        bt = backtest_primary_key(total_rows, distinct_keys, null_counts, dates)
        assert bt.total_periods == 3
        assert bt.periods_pass == 3
        assert bt.coverage_pct == 100.0
        assert bt.band_width_ratio == 0.0

    def test_duplicates_detected(self):
        """Some periods have duplicates."""
        total_rows = [100, 100, 100]
        distinct_keys = [100, 95, 100]  # period 1 has 5 duplicates
        null_counts = {"col_a": [0, 0, 0]}
        dates = ["d0", "d1", "d2"]
        bt = backtest_primary_key(total_rows, distinct_keys, null_counts, dates)
        assert bt.periods_pass == 2
        assert bt.periods_fail == 1
        assert "d1" in bt.outlier_periods

    def test_nulls_detected(self):
        """Periods with nulls in PK columns fail."""
        total_rows = [100, 100, 100]
        distinct_keys = [100, 100, 100]  # no duplicates
        null_counts = {"col_a": [0, 5, 0]}  # period 1 has 5 nulls
        dates = ["d0", "d1", "d2"]
        bt = backtest_primary_key(total_rows, distinct_keys, null_counts, dates)
        assert bt.periods_pass == 2
        assert bt.periods_fail == 1
        assert "d1" in bt.outlier_periods

    def test_both_duplicates_and_nulls(self):
        """Period with both duplicates and nulls still fails once."""
        total_rows = [100]
        distinct_keys = [95]
        null_counts = {"col_a": [3]}
        dates = ["d0"]
        bt = backtest_primary_key(total_rows, distinct_keys, null_counts, dates)
        assert bt.periods_fail == 1
        assert bt.total_periods == 1

    def test_false_positive_proxy_borderline(self):
        """1 duplicate or 1 null is borderline (FP proxy)."""
        total_rows = [100, 100, 100]
        distinct_keys = [99, 95, 100]  # 1 dup, 5 dups, 0 dups
        null_counts = {"col_a": [0, 0, 1]}  # last period has 1 null
        dates = ["d0", "d1", "d2"]
        bt = backtest_primary_key(total_rows, distinct_keys, null_counts, dates)
        # d0: 1 dup, 0 null -> FP proxy (dup<=1 and null<=1)
        # d1: 5 dups, 0 null -> not FP
        # d2: 0 dups, 1 null -> FP proxy (dup<=1 and null<=1)
        assert bt.false_positive_proxy == 2

    def test_multiple_pk_columns_nulls(self):
        """Nulls in any PK column cause failure."""
        total_rows = [100, 100]
        distinct_keys = [100, 100]
        null_counts = {
            "col_a": [0, 0],
            "col_b": [0, 2],  # col_b has nulls in period 1
        }
        dates = ["d0", "d1"]
        bt = backtest_primary_key(total_rows, distinct_keys, null_counts, dates)
        assert bt.periods_pass == 1
        assert bt.periods_fail == 1

    def test_drift_increasing_duplicates(self):
        """Increasing duplicate trend should flag drift."""
        n = 20
        total_rows = [100] * n
        distinct_keys = [100 - i for i in range(n)]  # 100, 99, 98, ..., 81
        null_counts = {"col_a": [0] * n}
        dates = [f"d{i}" for i in range(n)]
        bt = backtest_primary_key(total_rows, distinct_keys, null_counts, dates)
        assert bt.has_drift is True

    def test_no_drift_stable(self):
        total_rows = [100] * 10
        distinct_keys = [100] * 10
        null_counts = {"col_a": [0] * 10}
        dates = [f"d{i}" for i in range(10)]
        bt = backtest_primary_key(total_rows, distinct_keys, null_counts, dates)
        assert bt.has_drift is False

    def test_empty_null_counts(self):
        """Empty null_counts dict should still work (no null check)."""
        total_rows = [100, 100]
        distinct_keys = [100, 100]
        null_counts = {}
        dates = ["d0", "d1"]
        bt = backtest_primary_key(total_rows, distinct_keys, null_counts, dates)
        assert bt.periods_pass == 2


# ===========================================================================
# RuleType.UNIQUENESS_CUSTOM_SQL — enum + label
# ===========================================================================

class TestUniquenessRuleType:

    def test_enum_exists(self):
        assert RuleType.UNIQUENESS_CUSTOM_SQL.value == "uniqueness_custom_sql"

    def test_label(self):
        assert RULE_TYPE_LABELS[RuleType.UNIQUENESS_CUSTOM_SQL] == "Unicidade (CustomSql)"

    def test_get_rule_label(self):
        assert get_rule_label(RuleType.UNIQUENESS_CUSTOM_SQL) == "Unicidade (CustomSql)"


# ===========================================================================
# Scoring — UNIQUENESS_CUSTOM_SQL
# ===========================================================================

class TestScoringUniqueness:

    def test_interpretability(self):
        bt = BacktestSummary(
            total_periods=10, periods_pass=10, periods_fail=0,
            coverage_pct=100.0, false_positive_proxy=0,
            band_width_ratio=0.0, stability_score=1.0,
            has_drift=False, outlier_periods=[],
        )
        p = RuleProposal(
            id="1", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
            backtest=bt,
            suggested_values=["COL_A"],
        )
        score = score_proposal(p)
        assert score.interpretability == 0.8
        assert score.cost_efficiency == 0.7

    def test_without_backtest(self):
        p = RuleProposal(
            id="1", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
            suggested_values=["COL_A"],
        )
        score = score_proposal(p)
        assert score.confidence == ConfidenceLevel.LOW


# ===========================================================================
# Rule Explainer — UNIQUENESS_CUSTOM_SQL
# ===========================================================================

class TestRuleExplainerUniqueness:

    def test_explain_single_column(self):
        p = RuleProposal(
            id="1", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
            suggested_values=["NUM_CTRT"],
        )
        text = explain_rule(p)
        assert "unica" in text
        assert "`NUM_CTRT`" in text
        assert "IsPrimaryKey" in text
        assert "nulls" in text

    def test_explain_composite_key(self):
        p = RuleProposal(
            id="2", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
            suggested_values=["COL_A", "COL_B"],
        )
        text = explain_rule(p)
        assert "`COL_A`" in text
        assert "`COL_B`" in text
        assert "combinacao" in text

    def test_explain_params(self):
        p = RuleProposal(
            id="3", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
            suggested_values=["COL_A", "COL_B"],
        )
        detail = explain_rule_detail(p)
        assert "COL_A" in detail
        assert "COL_B" in detail
        assert "CustomSql" in detail
        assert "nulls" in detail


# ===========================================================================
# GDQ Generator — UNIQUENESS_CUSTOM_SQL
# ===========================================================================

class TestGDQGeneratorUniqueness:

    def setup_method(self):
        self.gen = GDQRuleGenerator()

    def test_single_column(self):
        p = RuleProposal(
            id="1", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
            suggested_values=["NUM_CTRT"],
        )
        syntax = self.gen.generate(p)
        assert syntax.startswith('CustomSql "')
        assert 'count(distinct' in syntax
        assert '\\"NUM_CTRT\\"' in syntax
        assert 'from primary' in syntax
        assert '>= 100.0' in syntax
        assert 'cast(' in syntax
        assert 'as varchar)' in syntax

    def test_composite_key(self):
        p = RuleProposal(
            id="2", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
            suggested_values=["COL_A", "COL_B"],
        )
        syntax = self.gen.generate(p)
        assert 'CustomSql "' in syntax
        assert 'concat(' in syntax
        assert '\\"COL_A\\"' in syntax
        assert '\\"COL_B\\"' in syntax
        assert "'||'" in syntax
        assert 'from primary' in syntax
        assert '>= 100.0' in syntax

    def test_three_columns(self):
        p = RuleProposal(
            id="3", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
            suggested_values=["C1", "C2", "C3"],
        )
        syntax = self.gen.generate(p)
        assert 'concat(' in syntax
        assert '\\"C1\\"' in syntax
        assert '\\"C2\\"' in syntax
        assert '\\"C3\\"' in syntax
        # Should have 2 '||' separators for 3 columns
        assert syntax.count("'||'") == 2

    def test_empty_columns_raises(self):
        p = RuleProposal(
            id="4", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
            suggested_values=[],
        )
        with pytest.raises(ValueError, match="suggested_values"):
            self.gen.generate(p)

    def test_no_columns_raises(self):
        p = RuleProposal(
            id="5", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
        )
        with pytest.raises(ValueError, match="suggested_values"):
            self.gen.generate(p)

    def test_syntax_structure_single(self):
        """Verify the exact structure of single-column uniqueness SQL."""
        p = RuleProposal(
            id="6", target_column=None, target_table="t",
            rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
            metric_name="uniqueness",
            suggested_values=["MY_COL"],
        )
        syntax = self.gen.generate(p)
        # Should be: CustomSql "select cast(count(distinct cast(\"MY_COL\" as varchar)) as double) * 100.0 / count(*) from primary" >= 100.0
        assert '* 100.0 / count(*)' in syntax
        assert 'as double)' in syntax
