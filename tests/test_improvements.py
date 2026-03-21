"""Tests for the 3 improvements: cardinality guardrails, margin toggle, FP clarity.

Tests:
1. suggest_reclassification: low-card numeric → suggest categorical,
   high-card numeric → suggest identifier, normal numeric → no suggestion
2. margin_enabled=False: renderer produces sigma-only syntax,
   backtest evaluates only sigma, proposal carries flag
3. FP proxy: verify the 4-sigma heuristic counts correctly
"""

import math
import uuid

import pytest

from core.column_classifier import suggest_reclassification
from core.models.dataset_config import DatasetConfig
from core.models.enums import GrainType, SemanticType, MetricRef, RuleType, BaselineMethod
from services.analysis_service import diagnose_history_gap
from core.models.dual_guard import DualGuardSpec
from core.gdq_renderer import DualGuardRenderer
from core.gdq_rule_generator import GDQRuleGenerator
from core.backtest import backtest_band
from core.models.baseline import BaselineStrategy
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import UserOverride


# =====================================================================
# 1. Cardinality guardrails
# =====================================================================

class TestSuggestReclassification:
    def test_low_card_numeric_suggests_categorical(self):
        """Numeric with <= 20 distinct values → suggest categorical."""
        suggested, msg = suggest_reclassification(
            athena_type="integer",
            distinct_count=5,
            total_count=100000,
            non_null_count=100000,
        )
        assert suggested == SemanticType.CATEGORICAL_LOW_CARDINALITY
        assert "categorica" in msg.lower()

    def test_boundary_20_suggests_categorical(self):
        """Exactly 20 distinct → suggest categorical."""
        suggested, msg = suggest_reclassification(
            athena_type="bigint",
            distinct_count=20,
            total_count=100000,
            non_null_count=100000,
        )
        assert suggested == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_21_distinct_no_suggestion(self):
        """21 distinct values → no suggestion (normal numeric)."""
        suggested, msg = suggest_reclassification(
            athena_type="double",
            distinct_count=21,
            total_count=100000,
            non_null_count=100000,
        )
        assert suggested is None

    def test_high_card_numeric_suggests_identifier(self):
        """Numeric with >= 10k distinct and >= 50% ratio → suggest identifier."""
        suggested, msg = suggest_reclassification(
            athena_type="bigint",
            distinct_count=50000,
            total_count=100000,
            non_null_count=100000,
        )
        assert suggested == SemanticType.IDENTIFIER
        assert "identificador" in msg.lower()

    def test_double_high_card_no_identifier_suggestion(self):
        """Double/decimal with high cardinality → NOT identifier (monetary values)."""
        for dtype in ("double", "decimal", "float", "real"):
            suggested, msg = suggest_reclassification(
                athena_type=dtype,
                distinct_count=50000,
                total_count=100000,
                non_null_count=100000,
            )
            assert suggested is None, f"{dtype} should not be suggested as identifier"

    def test_decimal_parametrized_no_identifier(self):
        """decimal(18,2) with high cardinality → NOT identifier."""
        suggested, msg = suggest_reclassification(
            athena_type="decimal(18,2)",
            distinct_count=80000,
            total_count=100000,
            non_null_count=100000,
        )
        assert suggested is None

    def test_high_distinct_low_ratio_no_suggestion(self):
        """High distinct but low ratio → no suggestion (valid numeric)."""
        suggested, msg = suggest_reclassification(
            athena_type="double",
            distinct_count=15000,
            total_count=100000,
            non_null_count=100000,
        )
        # ratio = 0.15, below 0.50 threshold
        assert suggested is None

    def test_string_type_no_suggestion(self):
        """Non-numeric type → no suggestion."""
        suggested, msg = suggest_reclassification(
            athena_type="string",
            distinct_count=5,
            total_count=100000,
            non_null_count=100000,
        )
        assert suggested is None

    def test_zero_non_null_no_suggestion(self):
        """All nulls → no suggestion."""
        suggested, msg = suggest_reclassification(
            athena_type="integer",
            distinct_count=0,
            total_count=100000,
            non_null_count=0,
        )
        assert suggested is None

    def test_normal_numeric_no_suggestion(self):
        """Normal numeric column → no suggestion."""
        suggested, msg = suggest_reclassification(
            athena_type="double",
            distinct_count=500,
            total_count=100000,
            non_null_count=100000,
        )
        assert suggested is None
        assert msg == ""

    def test_constant_column_has_specific_warning(self):
        """Column with exactly 1 distinct value → specific constant warning."""
        suggested, msg = suggest_reclassification(
            athena_type="double",
            distinct_count=1,
            total_count=100000,
            non_null_count=100000,
        )
        assert suggested == SemanticType.CATEGORICAL_LOW_CARDINALITY
        assert "constante" in msg.lower() or "unico" in msg.lower()
        assert "Mean" in msg or "StdDev" in msg

    def test_constant_int_has_specific_warning(self):
        """Integer with 1 distinct → same constant warning."""
        suggested, msg = suggest_reclassification(
            athena_type="integer",
            distinct_count=1,
            total_count=50000,
            non_null_count=50000,
        )
        assert suggested == SemanticType.CATEGORICAL_LOW_CARDINALITY
        assert "constante" in msg.lower() or "unico" in msg.lower()

    def test_few_distinct_has_generic_warning(self):
        """Column with 5 distinct → generic low-cardinality warning (not constant)."""
        _, msg = suggest_reclassification(
            athena_type="integer",
            distinct_count=5,
            total_count=100000,
            non_null_count=100000,
        )
        # Should mention code/flag/status, NOT constant
        assert "codigo" in msg.lower() or "flag" in msg.lower() or "status" in msg.lower()
        assert "constante" not in msg.lower()


# =====================================================================
# 1b. History gap diagnostics
# =====================================================================

class TestDiagnoseHistoryGap:
    """diagnose_history_gap: warns when profiling finds data but history is empty/thin."""

    def _make_config(self, grain=GrainType.DAILY, lookback=30, reference_date="2026-01-30"):
        return DatasetConfig(
            schema="test", table="t",
            partition_column="dt_ref", date_column="dt_ref",
            grain_type=grain, lookback_value=lookback,
            reference_date=reference_date,
        )

    def test_zero_periods_emits_warning(self):
        """0 periods returned → at least 1 warning."""
        config = self._make_config()
        warnings = diagnose_history_gap(0, config)
        assert len(warnings) >= 1
        assert any("0 periodos" in w for w in warnings)

    def test_zero_periods_with_profiling_data_explains_gap(self):
        """0 periods but profiling had data → mentions the gap explicitly."""
        config = self._make_config()
        warnings = diagnose_history_gap(0, config, profiling_total_count=5000)
        assert any("Profiling encontrou dados" in w for w in warnings)

    def test_zero_periods_without_reference_date_suggests_it(self):
        """No reference_date → suggests setting it."""
        config = self._make_config(reference_date=None)
        warnings = diagnose_history_gap(0, config)
        assert any("reference_date" in w for w in warnings)

    def test_zero_periods_monthly_mentions_lookback(self):
        """Monthly grain with 0 periods → mentions lookback_value in days."""
        config = self._make_config(grain=GrainType.MONTHLY, lookback=30)
        warnings = diagnose_history_gap(0, config)
        assert any("MONTHLY" in w and "lookback_value" in w for w in warnings)

    def test_few_periods_daily_warns_below_min_history(self):
        """Daily with 3 periods (< min_history=7) → warns about insufficient backtest."""
        config = self._make_config()
        warnings = diagnose_history_gap(3, config)
        assert len(warnings) >= 1
        assert any("backtest" in w.lower() for w in warnings)

    def test_few_periods_monthly_suggests_larger_lookback(self):
        """Monthly with 2 periods and small lookback → suggests increasing."""
        config = self._make_config(grain=GrainType.MONTHLY, lookback=90)
        warnings = diagnose_history_gap(2, config)
        assert any("lookback_value" in w for w in warnings)

    def test_sufficient_periods_daily_no_warnings(self):
        """Daily with 30 periods → no warnings."""
        config = self._make_config()
        warnings = diagnose_history_gap(30, config)
        assert warnings == []

    def test_sufficient_periods_monthly_no_warnings(self):
        """Monthly with 6 periods (>= min_history=3) → no warnings."""
        config = self._make_config(grain=GrainType.MONTHLY, lookback=400)
        warnings = diagnose_history_gap(6, config)
        assert warnings == []

    def test_exactly_min_history_daily_no_warning(self):
        """Daily with exactly 7 periods (= min_history) → no warning."""
        config = self._make_config()
        warnings = diagnose_history_gap(7, config)
        assert warnings == []


# =====================================================================
# 2. Margin toggle
# =====================================================================

class TestMarginToggle:
    def test_renderer_sigma_only(self):
        """margin_enabled=False → produces sigma-only syntax (no OR)."""
        spec = DualGuardSpec(
            metric=MetricRef.MEAN,
            target="VLR",
            n_periods=20,
            n_sigma=2.0,
            margin_pct=0.10,
            margin_enabled=False,
        )
        renderer = DualGuardRenderer()
        result = renderer.render(spec)
        assert "OR" not in result
        assert "Mean VLR >=" in result
        assert "Mean VLR <=" in result
        assert "std(last(20))" in result

    def test_renderer_dual_guard(self):
        """margin_enabled=True → produces full dual guard with OR."""
        spec = DualGuardSpec(
            metric=MetricRef.MEAN,
            target="VLR",
            n_periods=20,
            n_sigma=2.0,
            margin_pct=0.10,
            margin_enabled=True,
        )
        renderer = DualGuardRenderer()
        result = renderer.render(spec)
        assert "OR" in result
        assert "0.9" in result or "1.1" in result

    def test_generator_sigma_only(self):
        """GDQRuleGenerator respects margin_enabled=False on proposal."""
        proposal = RuleProposal(
            id=str(uuid.uuid4()),
            target_column="VLR",
            target_table="t",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            metric_name="mean",
            baseline_window=20,
            baseline_n_sigma=2.0,
            baseline_margin_pct=0.10,
            margin_enabled=False,
        )
        gen = GDQRuleGenerator()
        result = gen.generate(proposal)
        assert "OR" not in result

    def test_generator_override_margin_enabled(self):
        """UserOverride can toggle margin_enabled."""
        proposal = RuleProposal(
            id=str(uuid.uuid4()),
            target_column="VLR",
            target_table="t",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            metric_name="mean",
            baseline_window=20,
            baseline_n_sigma=2.0,
            baseline_margin_pct=0.10,
            margin_enabled=True,  # originally enabled
        )
        gen = GDQRuleGenerator()

        # Override to disable margin
        overrides = UserOverride(margin_enabled=False)
        result = gen.generate(proposal, overrides)
        assert "OR" not in result

    def test_backtest_sigma_only_stricter(self):
        """Sigma-only backtest should have equal or lower coverage than dual guard."""
        values = [100 + i * 0.5 for i in range(30)]
        dates = [f"2024-01-{i+1:02d}" for i in range(30)]

        dual = backtest_band(values, dates, 20, 2.0, 0.10, margin_enabled=True)
        sigma = backtest_band(values, dates, 20, 2.0, 0.10, margin_enabled=False)

        assert sigma.coverage_pct <= dual.coverage_pct

    def test_baseline_strategy_margin_enabled(self):
        """BaselineStrategy carries margin_enabled flag."""
        bs = BaselineStrategy(margin_enabled=False)
        assert bs.margin_enabled is False
        bs2 = BaselineStrategy()
        assert bs2.margin_enabled is True


# =====================================================================
# 3. FP proxy heuristic
# =====================================================================

class TestFalsePositiveProxy:
    def test_fp_proxy_counts_normal_violations(self):
        """Values within 4 sigma global but outside band → counted as FP."""
        # Series with natural variability; last value slightly outside tight band
        import random
        random.seed(42)
        values = [100.0 + random.gauss(0, 3) for _ in range(30)]
        # Add a value that's within global 4σ but outside a tight 0.5σ band
        values.append(100.0 + 5.0)
        dates = [f"2024-{(i//28)+1:02d}-{(i%28)+1:02d}" for i in range(31)]

        # Use very tight sigma (0.5) to force some failures
        result = backtest_band(values, dates, 15, 0.5, 0.01, min_history=5)

        # With tight band, some normal values should fail → FP proxy > 0
        if result.periods_fail > 0:
            assert result.false_positive_proxy > 0

    def test_fp_proxy_extreme_outlier_not_counted(self):
        """Values beyond 4 sigma global → NOT counted as FP."""
        # Stable series with extreme outlier
        values = [100.0] * 20 + [500.0]  # 500 is way beyond 4σ
        dates = [f"2024-01-{i+1:02d}" for i in range(21)]

        result = backtest_band(values, dates, 10, 2.0, 0.10, min_history=5)

        # 500 should fail and NOT be counted as FP (beyond 4σ)
        if result.periods_fail > 0:
            assert result.false_positive_proxy == 0

    def test_fp_proxy_zero_for_good_coverage(self):
        """Stable series with good coverage → 0 FPs."""
        values = [100.0 + i * 0.1 for i in range(30)]
        dates = [f"2024-01-{i+1:02d}" for i in range(30)]

        result = backtest_band(values, dates, 20, 3.0, 0.10, min_history=5)
        assert result.false_positive_proxy == 0
