"""Testes para os modelos do dominio (core/models/)."""

import pytest
from core.models.enums import (
    BaselineMethod,
    ConfidenceLevel,
    MetricRef,
    RuleType,
    SemanticType,
)
from core.models.column_profile import ColumnProfile
from core.models.baseline import BaselineStrategy
from core.models.dual_guard import (
    DualGuardSpec,
    FormattingProfile,
    MEAN_PROFILE,
    STDDEV_PROFILE,
    ROWCOUNT_PROFILE,
)
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.rule_selection import RuleSelection, UserOverride


# ---------------------------------------------------------------------------
# ColumnProfile
# ---------------------------------------------------------------------------

class TestColumnProfile:
    def test_basic_creation(self):
        cp = ColumnProfile(
            column_name="VLR_SALDO",
            athena_type="double",
            inferred_semantic_type=SemanticType.NUMERIC,
        )
        assert cp.column_name == "VLR_SALDO"
        assert cp.athena_type == "double"
        assert cp.inferred_semantic_type == SemanticType.NUMERIC

    def test_effective_type_without_override(self):
        cp = ColumnProfile(
            column_name="COD_SEG",
            athena_type="string",
            inferred_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY,
        )
        assert cp.effective_type == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_effective_type_with_override(self):
        cp = ColumnProfile(
            column_name="COD_PROD",
            athena_type="string",
            inferred_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY,
            user_override_type=SemanticType.NUMERIC,
        )
        assert cp.effective_type == SemanticType.NUMERIC

    def test_is_numeric(self):
        cp = ColumnProfile(
            column_name="VLR",
            athena_type="double",
            inferred_semantic_type=SemanticType.NUMERIC,
        )
        assert cp.is_numeric is True
        assert cp.is_categorical is False

    def test_is_categorical(self):
        for sem_type in [
            SemanticType.CATEGORICAL_LOW_CARDINALITY,
            SemanticType.CATEGORICAL_MID_CARDINALITY,
            SemanticType.CATEGORICAL_HIGH_CARDINALITY,
        ]:
            cp = ColumnProfile(
                column_name="COL",
                athena_type="string",
                inferred_semantic_type=sem_type,
            )
            assert cp.is_categorical is True
            assert cp.is_numeric is False

    def test_default_lists(self):
        cp = ColumnProfile(
            column_name="COL",
            athena_type="string",
            inferred_semantic_type=SemanticType.UNKNOWN,
        )
        assert cp.sample_values == []
        assert cp.warnings == []


# ---------------------------------------------------------------------------
# BaselineStrategy
# ---------------------------------------------------------------------------

class TestBaselineStrategy:
    def test_defaults(self):
        bs = BaselineStrategy()
        assert bs.method == BaselineMethod.LAST_N_PERIODS
        assert bs.n_periods == 20
        assert bs.n_sigma == 2.0
        assert bs.margin_pct == 0.10
        assert bs.percentile_lower == 0.05
        assert bs.percentile_upper == 0.95
        assert bs.min_history_points == 7

    def test_custom_values(self):
        bs = BaselineStrategy(
            method=BaselineMethod.ROLLING_WINDOW_EXCLUDE_CURRENT,
            n_periods=10,
            n_sigma=3.0,
            margin_pct=0.15,
            min_history_points=5,
        )
        assert bs.method == BaselineMethod.ROLLING_WINDOW_EXCLUDE_CURRENT
        assert bs.n_periods == 10
        assert bs.n_sigma == 3.0


# ---------------------------------------------------------------------------
# DualGuardSpec / FormattingProfile
# ---------------------------------------------------------------------------

class TestFormattingProfile:
    def test_mean_profile(self):
        assert MEAN_PROFILE.k_as_float is False
        assert MEAN_PROFILE.include_buffer is True
        assert MEAN_PROFILE.avg_multiply_one is False
        assert MEAN_PROFILE.margin_format == "factor"

    def test_stddev_profile(self):
        assert STDDEV_PROFILE.k_as_float is False
        assert STDDEV_PROFILE.include_buffer is True
        assert STDDEV_PROFILE.avg_multiply_one is False
        assert STDDEV_PROFILE.margin_format == "factor"

    def test_rowcount_profile(self):
        assert ROWCOUNT_PROFILE.k_as_float is True
        assert ROWCOUNT_PROFILE.include_buffer is False
        assert ROWCOUNT_PROFILE.avg_multiply_one is True
        assert ROWCOUNT_PROFILE.margin_format == "delta"


class TestDualGuardSpec:
    def test_mean_auto_profile(self):
        spec = DualGuardSpec(metric=MetricRef.MEAN, target="VLR_SALDO")
        assert spec.profile is MEAN_PROFILE
        assert spec.buffer == 0.01

    def test_stddev_auto_profile(self):
        spec = DualGuardSpec(metric=MetricRef.STANDARD_DEVIATION, target="VLR_SALDO")
        assert spec.profile is STDDEV_PROFILE
        assert spec.buffer == 0.01

    def test_rowcount_auto_profile(self):
        spec = DualGuardSpec(metric=MetricRef.ROW_COUNT)
        assert spec.profile is ROWCOUNT_PROFILE
        assert spec.buffer == 0  # auto-set by __post_init__
        assert isinstance(spec.n_sigma, float)  # auto-cast by __post_init__

    def test_custom_profile_not_overridden(self):
        custom = FormattingProfile(k_as_float=True, include_buffer=True)
        spec = DualGuardSpec(
            metric=MetricRef.MEAN,
            target="COL",
            profile=custom,
        )
        assert spec.profile is custom

    def test_default_values(self):
        spec = DualGuardSpec(metric=MetricRef.MEAN, target="COL")
        assert spec.n_periods == 30
        assert spec.margin_pct == 0.10
        assert spec.target == "COL"


# ---------------------------------------------------------------------------
# RuleProposal / BacktestSummary
# ---------------------------------------------------------------------------

class TestBacktestSummary:
    def test_creation(self):
        bt = BacktestSummary(
            total_periods=30,
            periods_pass=28,
            periods_fail=2,
            coverage_pct=93.3,
            false_positive_proxy=1,
            band_width_ratio=0.15,
            stability_score=0.85,
            has_drift=False,
            outlier_periods=["2026-01-10", "2026-01-25"],
        )
        assert bt.total_periods == 30
        assert bt.periods_pass == 28
        assert bt.periods_fail == 2
        assert bt.coverage_pct == 93.3
        assert len(bt.outlier_periods) == 2

    def test_default_outliers(self):
        bt = BacktestSummary(
            total_periods=10,
            periods_pass=10,
            periods_fail=0,
            coverage_pct=100.0,
            false_positive_proxy=0,
            band_width_ratio=0.1,
            stability_score=0.9,
            has_drift=False,
        )
        assert bt.outlier_periods == []


class TestRuleProposal:
    def test_creation(self):
        rp = RuleProposal(
            id="test-uuid-001",
            target_column="VLR_SALDO",
            target_table="tb_operacoes",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            metric_name="mean",
        )
        assert rp.id == "test-uuid-001"
        assert rp.target_column == "VLR_SALDO"
        assert rp.rule_type == RuleType.MEAN_DUAL_GUARD
        assert rp.confidence == ConfidenceLevel.MEDIUM

    def test_defaults(self):
        rp = RuleProposal(
            id="x",
            target_column=None,
            target_table="tb",
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            metric_name="row_count",
        )
        assert rp.suggested_lower is None
        assert rp.suggested_upper is None
        assert rp.suggested_values is None
        assert rp.backtest is None
        assert rp.warnings == []
        assert rp.gdq_syntax_preview == ""
        assert rp.history_dates == []
        assert rp.history_values == []

    def test_table_level_rule(self):
        rp = RuleProposal(
            id="rc-001",
            target_column=None,
            target_table="tb_ops",
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            metric_name="row_count",
        )
        assert rp.target_column is None


# ---------------------------------------------------------------------------
# RuleSelection / UserOverride
# ---------------------------------------------------------------------------

class TestUserOverride:
    def test_defaults(self):
        uo = UserOverride()
        assert uo.custom_lower is None
        assert uo.custom_upper is None
        assert uo.custom_values is None
        assert uo.custom_n_periods is None
        assert uo.custom_n_sigma is None
        assert uo.notes == ""

    def test_custom_values(self):
        uo = UserOverride(
            custom_lower=100.0,
            custom_upper=500.0,
            custom_n_sigma=3.0,
            notes="Ajustado para tolerancia maior",
        )
        assert uo.custom_lower == 100.0
        assert uo.custom_n_sigma == 3.0


class TestRuleSelection:
    def test_creation(self):
        proposal = RuleProposal(
            id="p-001",
            target_column="VLR_SALDO",
            target_table="tb_ops",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            metric_name="mean",
        )
        sel = RuleSelection(
            proposal_id="p-001",
            proposal=proposal,
        )
        assert sel.proposal_id == "p-001"
        assert sel.proposal is proposal
        assert sel.enabled is True
        assert sel.user_overrides is None
        assert sel.final_gdq_syntax == ""

    def test_with_overrides(self):
        proposal = RuleProposal(
            id="p-002",
            target_column="COL",
            target_table="tb",
            rule_type=RuleType.STDDEV_DUAL_GUARD,
            metric_name="stddev",
        )
        override = UserOverride(custom_n_sigma=3.0)
        sel = RuleSelection(
            proposal_id="p-002",
            proposal=proposal,
            user_overrides=override,
            final_gdq_syntax="StandardDeviation COL ...",
        )
        assert sel.user_overrides.custom_n_sigma == 3.0
        assert sel.final_gdq_syntax != ""
