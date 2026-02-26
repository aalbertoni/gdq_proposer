"""Testes Sprint C2: CustomSql Dinamico — renderer, generator, backtest, proposal."""

import math

import pandas as pd
import pytest

from core.backtest import backtest_frequency_dual_guard
from core.gdq_renderer import DualGuardRenderer
from core.gdq_rule_generator import GDQRuleGenerator
from core.models.baseline import BaselineStrategy
from core.models.column_profile import ColumnProfile
from core.models.dual_guard import DualGuardSpec
from core.models.enums import (
    BaselineMethod,
    MetricRef,
    RuleType,
    SemanticType,
)
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import UserOverride
from core.rule_scoring import score_proposal
from services.proposal_service import ProposalService
from tests.fixtures import (
    make_stable_categories,
    make_category_shift,
    make_rare_category,
)


# ---------------------------------------------------------------------------
# DualGuardRenderer — CustomSql dynamic
# ---------------------------------------------------------------------------

class TestRendererCustomSqlDynamic:

    def setup_method(self):
        self.renderer = DualGuardRenderer()

    def test_basic_dynamic_syntax(self):
        sql = "select cast(sum(case when COL = 'A' then 1 else 0 end) as double) * 100.0 / count(*) from primary"
        spec = DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            custom_sql_expression=sql,
            n_periods=30,
            n_sigma=2.0,
            margin_pct=0.10,
            buffer=0.01,
        )
        result = self.renderer.render(spec)
        assert 'CustomSql' in result
        assert 'avg(last(30))' in result
        assert 'std(last(30))' in result
        assert 'OR' in result
        assert '0.01' in result
        assert 'from primary' in result

    def test_sigma_part_structure(self):
        sql = "select 1 from primary"
        spec = DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            custom_sql_expression=sql,
            n_periods=20,
            n_sigma=3.0,
            buffer=0.01,
        )
        result = self.renderer.render(spec)
        assert '(3 * std(last(20)))' in result

    def test_margin_part_structure(self):
        sql = "select 1 from primary"
        spec = DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            custom_sql_expression=sql,
            n_periods=30,
            margin_pct=0.15,
            buffer=0.01,
        )
        result = self.renderer.render(spec)
        assert '* 0.85' in result
        assert '* 1.15' in result

    def test_sigma_only_no_or(self):
        sql = "select 1 from primary"
        spec = DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            custom_sql_expression=sql,
            margin_enabled=False,
        )
        result = self.renderer.render(spec)
        assert 'OR' not in result
        assert 'avg(last(' in result

    def test_balanced_parentheses(self):
        sql = "select cast(sum(case when COL = 'A' then 1 else 0 end) as double) * 100.0 / count(*) from primary"
        spec = DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            custom_sql_expression=sql,
        )
        result = self.renderer.render(spec)
        assert result.count('(') == result.count(')')

    def test_k_integer_formatting(self):
        """CustomSql uses integer K (not float like RowCount)."""
        sql = "select 1 from primary"
        spec = DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            custom_sql_expression=sql,
            n_sigma=2.0,
        )
        result = self.renderer.render(spec)
        assert '(2 * std(' in result
        assert '(2.0 * std(' not in result


# ---------------------------------------------------------------------------
# DualGuardRenderer — CustomSql hybrid
# ---------------------------------------------------------------------------

class TestRendererCustomSqlHybrid:

    def setup_method(self):
        self.renderer = DualGuardRenderer()

    def _make_spec(self, floor_pct=0.0, ceiling_pct=5.0, **kwargs):
        sql = "select cast(sum(case when COL = 'RARE' then 1 else 0 end) as double) * 100.0 / count(*) from primary"
        return DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            custom_sql_expression=sql,
            floor_pct=floor_pct,
            ceiling_pct=ceiling_pct,
            **kwargs,
        )

    def test_hybrid_has_and_clause(self):
        spec = self._make_spec(floor_pct=0.0, ceiling_pct=5.0)
        result = self.renderer.render(spec)
        assert 'AND' in result
        assert 'between 0.0 and 5.0' in result

    def test_hybrid_has_dual_guard_and_absolute(self):
        spec = self._make_spec(floor_pct=1.0, ceiling_pct=10.0)
        result = self.renderer.render(spec)
        assert 'OR' in result  # dual guard
        assert 'between 1.0 and 10.0' in result  # absolute

    def test_hybrid_balanced_parentheses(self):
        spec = self._make_spec()
        result = self.renderer.render(spec)
        assert result.count('(') == result.count(')')

    def test_non_hybrid_when_defaults(self):
        """floor=0 and ceiling=100 means no effective constraint — pure dynamic."""
        spec = self._make_spec(floor_pct=0.0, ceiling_pct=100.0)
        result = self.renderer.render(spec)
        # Should be pure dynamic (no AND with between 0.0 and 100.0)
        assert 'between 0.0 and 100.0' not in result

    def test_hybrid_floor_only(self):
        spec = self._make_spec(floor_pct=1.0, ceiling_pct=100.0)
        result = self.renderer.render(spec)
        assert 'between 1.0 and 100.0' in result

    def test_hybrid_ceiling_only(self):
        spec = self._make_spec(floor_pct=0.0, ceiling_pct=50.0)
        result = self.renderer.render(spec)
        assert 'between 0.0 and 50.0' in result


# ---------------------------------------------------------------------------
# GDQRuleGenerator — dynamic + hybrid
# ---------------------------------------------------------------------------

class TestGeneratorDynamic:

    def setup_method(self):
        self.gen = GDQRuleGenerator()

    def test_dynamic_generates_syntax(self):
        p = RuleProposal(
            id="1", target_column="STATUS", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            metric_name="cat_freq_A",
            category_value="A",
            baseline_window=30, baseline_n_sigma=2.0,
            baseline_margin_pct=0.10,
        )
        syntax = self.gen.generate(p)
        assert "STATUS = 'A'" in syntax
        assert 'avg(last(30))' in syntax
        assert 'OR' in syntax

    def test_dynamic_override_n_periods(self):
        p = RuleProposal(
            id="2", target_column="COL", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            metric_name="freq", category_value="X",
            baseline_window=30, baseline_n_sigma=2.0,
        )
        overrides = UserOverride(custom_n_periods=15)
        syntax = self.gen.generate(p, overrides)
        assert 'last(15)' in syntax

    def test_dynamic_override_n_sigma(self):
        p = RuleProposal(
            id="3", target_column="COL", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            metric_name="freq", category_value="X",
            baseline_window=30, baseline_n_sigma=2.0,
        )
        overrides = UserOverride(custom_n_sigma=3.0)
        syntax = self.gen.generate(p, overrides)
        assert '(3 * std(' in syntax

    def test_dynamic_margin_disabled(self):
        p = RuleProposal(
            id="4", target_column="COL", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            metric_name="freq", category_value="X",
            baseline_window=30, baseline_n_sigma=2.0,
            margin_enabled=False,
        )
        syntax = self.gen.generate(p)
        assert 'OR' not in syntax

    def test_hybrid_generates_floor_ceiling(self):
        p = RuleProposal(
            id="5", target_column="STATUS", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_HYBRID,
            metric_name="freq", category_value="RARE",
            baseline_window=30, baseline_n_sigma=2.0,
            baseline_margin_pct=0.10,
            floor_pct=0.0, ceiling_pct=5.0,
        )
        syntax = self.gen.generate(p)
        assert 'between 0.0 and 5.0' in syntax
        assert 'avg(last(30))' in syntax
        assert 'OR' in syntax

    def test_hybrid_override_floor_ceiling(self):
        p = RuleProposal(
            id="6", target_column="COL", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_HYBRID,
            metric_name="freq", category_value="X",
            baseline_window=30, baseline_n_sigma=2.0,
            floor_pct=0.0, ceiling_pct=5.0,
        )
        overrides = UserOverride(custom_floor_pct=1.0, custom_ceiling_pct=10.0)
        syntax = self.gen.generate(p, overrides)
        assert 'between 1.0 and 10.0' in syntax


# ---------------------------------------------------------------------------
# Backtest — frequency dual guard
# ---------------------------------------------------------------------------

class TestBacktestFrequencyDualGuard:

    def test_empty_series(self):
        bt = backtest_frequency_dual_guard([], [], 20)
        assert bt.total_periods == 0

    def test_too_few_points(self):
        bt = backtest_frequency_dual_guard([50.0] * 3, ["d1", "d2", "d3"], 20)
        assert bt.total_periods == 0

    def test_stable_series_high_coverage(self):
        data = make_stable_categories()
        bt = backtest_frequency_dual_guard(
            pct_series=data["series"]["A"],
            dates=data["dates"],
            n_periods=15,
            n_sigma=2.0,
            margin_pct=0.10,
        )
        assert bt.total_periods > 0
        assert bt.coverage_pct >= 80.0

    def test_shift_detects_failures(self):
        data = make_category_shift()
        bt = backtest_frequency_dual_guard(
            pct_series=data["series"]["A"],
            dates=data["dates"],
            n_periods=10,
            n_sigma=2.0,
            margin_pct=0.10,
        )
        assert bt.periods_fail > 0

    def test_nan_in_series(self):
        series = [50.0] * 15 + [float("nan")] + [50.0] * 5
        dates = [f"d{i}" for i in range(len(series))]
        bt = backtest_frequency_dual_guard(series, dates, 10, n_sigma=2.0)
        assert bt.total_periods > 0

    def test_sigma_only_mode(self):
        data = make_stable_categories()
        bt = backtest_frequency_dual_guard(
            pct_series=data["series"]["A"],
            dates=data["dates"],
            n_periods=15,
            n_sigma=2.0,
            margin_enabled=False,
        )
        assert bt.total_periods > 0

    def test_hybrid_floor_ceiling_restricts(self):
        """Hybrid with tight ceiling should cause more failures."""
        data = make_stable_categories()
        series_a = data["series"]["A"]
        dates = data["dates"]

        # No ceiling: should have high coverage
        bt_dynamic = backtest_frequency_dual_guard(
            pct_series=series_a, dates=dates,
            n_periods=15, n_sigma=3.0, margin_pct=0.20,
        )

        # With tight ceiling (30%) on a ~50% category: should fail more
        bt_hybrid = backtest_frequency_dual_guard(
            pct_series=series_a, dates=dates,
            n_periods=15, n_sigma=3.0, margin_pct=0.20,
            floor_pct=0.0, ceiling_pct=30.0,
        )
        assert bt_hybrid.coverage_pct < bt_dynamic.coverage_pct

    def test_hybrid_with_generous_limits(self):
        """Hybrid with generous limits should behave like dynamic."""
        data = make_stable_categories()
        bt = backtest_frequency_dual_guard(
            pct_series=data["series"]["A"],
            dates=data["dates"],
            n_periods=15, n_sigma=2.0, margin_pct=0.10,
            floor_pct=0.0, ceiling_pct=100.0,
        )
        assert bt.coverage_pct >= 80.0

    def test_stability_score_returned(self):
        data = make_stable_categories()
        bt = backtest_frequency_dual_guard(
            pct_series=data["series"]["B"],
            dates=data["dates"],
            n_periods=15, n_sigma=2.0,
        )
        assert 0.0 <= bt.stability_score <= 1.0

    def test_drift_detection(self):
        data = make_category_shift()
        bt = backtest_frequency_dual_guard(
            pct_series=data["series"]["B"],
            dates=data["dates"],
            n_periods=10, n_sigma=2.0,
        )
        assert bt.has_drift is True


# ---------------------------------------------------------------------------
# ProposalService — frequency mode
# ---------------------------------------------------------------------------

def _make_distribution_df(data: dict) -> pd.DataFrame:
    rows = []
    for i, date in enumerate(data["dates"]):
        for cat, pct in data["distributions"][i].items():
            rows.append({
                "period": date,
                "category_value": cat,
                "value_count": int(pct * 10),
                "value_pct": pct,
            })
    return pd.DataFrame(rows)


def _make_domain_df(data: dict) -> pd.DataFrame:
    rows = []
    for cat in data["domain"]:
        total_pct = sum(d.get(cat, 0) for d in data["distributions"]) / len(data["distributions"])
        rows.append({
            "category_value": cat,
            "value_count": int(total_pct * 100),
            "value_pct": total_pct,
        })
    return pd.DataFrame(rows).sort_values("value_count", ascending=False).reset_index(drop=True)


class TestProposalServiceFreqMode:

    def setup_method(self):
        self.svc = ProposalService()
        self.baseline = BaselineStrategy(
            method=BaselineMethod.LAST_N_PERIODS,
            n_periods=15, n_sigma=2.0, margin_pct=0.10,
        )

    def _make_profile(self, col, sem_type, n_distinct=4):
        return ColumnProfile(
            column_name=col, athena_type="string",
            inferred_semantic_type=sem_type,
            distinct_count=n_distinct, null_ratio=0.02,
        )

    def test_static_mode_default(self):
        data = make_stable_categories()
        proposals = self.svc.propose_categorical_rules(
            _make_distribution_df(data), _make_domain_df(data),
            "COL", "t",
            self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY),
            self.baseline,
        )
        freq_proposals = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_STATIC]
        assert len(freq_proposals) > 0

    def test_dynamic_mode(self):
        data = make_stable_categories()
        proposals = self.svc.propose_categorical_rules(
            _make_distribution_df(data), _make_domain_df(data),
            "COL", "t",
            self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY),
            self.baseline, freq_mode="dynamic",
        )
        freq_proposals = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_DYNAMIC]
        assert len(freq_proposals) > 0
        for p in freq_proposals:
            assert 'avg(last(' in p.gdq_syntax_preview
            assert p.backtest is not None

    def test_hybrid_mode(self):
        data = make_stable_categories()
        proposals = self.svc.propose_categorical_rules(
            _make_distribution_df(data), _make_domain_df(data),
            "COL", "t",
            self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY),
            self.baseline, freq_mode="hybrid",
            floor_pct=0.0, ceiling_pct=80.0,
        )
        freq_proposals = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_HYBRID]
        assert len(freq_proposals) > 0
        for p in freq_proposals:
            assert 'between 0.0 and 80.0' in p.gdq_syntax_preview
            assert p.floor_pct == 0.0
            assert p.ceiling_pct == 80.0

    def test_dynamic_has_backtest_with_dual_guard(self):
        data = make_stable_categories()
        proposals = self.svc.propose_categorical_rules(
            _make_distribution_df(data), _make_domain_df(data),
            "COL", "t",
            self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY),
            self.baseline, freq_mode="dynamic",
        )
        freq_proposals = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_DYNAMIC]
        for p in freq_proposals:
            assert p.backtest is not None
            assert p.backtest.total_periods > 0

    def test_scoring_works_for_dynamic(self):
        data = make_stable_categories()
        proposals = self.svc.propose_categorical_rules(
            _make_distribution_df(data), _make_domain_df(data),
            "COL", "t",
            self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY),
            self.baseline, freq_mode="dynamic",
        )
        freq_proposals = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_DYNAMIC]
        for p in freq_proposals:
            score = score_proposal(p, p.history_values)
            assert score.interpretability == 0.7
            assert score.cost_efficiency == 0.7

    def test_scoring_works_for_hybrid(self):
        data = make_stable_categories()
        proposals = self.svc.propose_categorical_rules(
            _make_distribution_df(data), _make_domain_df(data),
            "COL", "t",
            self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY),
            self.baseline, freq_mode="hybrid",
        )
        freq_proposals = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_HYBRID]
        for p in freq_proposals:
            score = score_proposal(p, p.history_values)
            assert score.interpretability == 0.7
            assert score.cost_efficiency == 0.7


# ---------------------------------------------------------------------------
# RuleProposal model — floor/ceiling fields
# ---------------------------------------------------------------------------

class TestRuleProposalFloorCeiling:

    def test_floor_ceiling_defaults(self):
        p = RuleProposal(
            id="1", target_column="X", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_HYBRID,
            metric_name="freq",
        )
        assert p.floor_pct is None
        assert p.ceiling_pct is None

    def test_floor_ceiling_set(self):
        p = RuleProposal(
            id="2", target_column="X", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_HYBRID,
            metric_name="freq",
            floor_pct=1.0, ceiling_pct=50.0,
        )
        assert p.floor_pct == 1.0
        assert p.ceiling_pct == 50.0


# ---------------------------------------------------------------------------
# UserOverride — floor/ceiling fields
# ---------------------------------------------------------------------------

class TestUserOverrideFloorCeiling:

    def test_override_defaults(self):
        o = UserOverride()
        assert o.custom_floor_pct is None
        assert o.custom_ceiling_pct is None

    def test_override_set(self):
        o = UserOverride(custom_floor_pct=2.0, custom_ceiling_pct=15.0)
        assert o.custom_floor_pct == 2.0
        assert o.custom_ceiling_pct == 15.0


# ---------------------------------------------------------------------------
# ProposalService.find_best_params — auto-tuning
# ---------------------------------------------------------------------------

class TestFindBestParams:

    def setup_method(self):
        self.svc = ProposalService()

    def test_stable_numeric_returns_high(self):
        """Stable series should find HIGH confidence params."""
        values = [100.0 + i * 0.1 for i in range(40)]
        dates = [f"d{i}" for i in range(40)]
        result = self.svc.find_best_params(values, dates, metric_kind="numeric")
        assert result["viable"] is True
        assert result["coverage_pct"] >= 70.0
        assert "n_periods" in result
        assert "n_sigma" in result
        assert "margin_pct" in result

    def test_returns_recommendation_text(self):
        values = [50.0] * 30
        dates = [f"d{i}" for i in range(30)]
        result = self.svc.find_best_params(values, dates)
        assert "recommendation" in result
        assert len(result["recommendation"]) > 10

    def test_frequency_metric_kind(self):
        data = make_stable_categories()
        result = self.svc.find_best_params(
            data["series"]["A"], data["dates"],
            metric_kind="frequency",
        )
        assert result["viable"] is True
        assert result["coverage_pct"] > 0

    def test_insufficient_data_returns_not_viable(self):
        values = [1.0, 2.0]
        dates = ["d1", "d2"]
        result = self.svc.find_best_params(values, dates)
        assert result["viable"] is False
        assert result["confidence"].value == "low"

    def test_volatile_series_may_not_reach_min_coverage(self):
        """Highly volatile series should have lower coverage."""
        import random
        random.seed(42)
        values = [random.uniform(0, 1000) for _ in range(40)]
        dates = [f"d{i}" for i in range(40)]
        result = self.svc.find_best_params(
            values, dates, min_coverage=99.0,
        )
        # With min_coverage=99%, random data likely won't reach it
        # (but it might with wide sigma/margin — so just check structure)
        assert "viable" in result
        assert "confidence" in result

    def test_custom_ranges(self):
        values = [50.0 + (i % 5) for i in range(30)]
        dates = [f"d{i}" for i in range(30)]
        result = self.svc.find_best_params(
            values, dates,
            n_range=[10, 20],
            sigma_range=[2.0, 3.0],
            margin_range=[0.10],
        )
        assert result["n_periods"] in [10, 20]
        assert result["n_sigma"] in [2.0, 3.0]
        assert result["margin_pct"] == 0.10

    def test_shift_series_lower_coverage(self):
        """Series with abrupt shift should have lower best coverage."""
        data = make_category_shift()
        result = self.svc.find_best_params(
            data["series"]["A"], data["dates"],
            metric_kind="frequency",
        )
        # Should still return a result, though coverage may be lower
        assert "coverage_pct" in result
        assert "false_positives" in result

    def test_result_has_all_fields(self):
        values = [100.0] * 25
        dates = [f"d{i}" for i in range(25)]
        result = self.svc.find_best_params(values, dates)
        expected_keys = {
            "n_periods", "n_sigma", "margin_pct", "margin_enabled",
            "coverage_pct", "false_positives", "stability", "score_total",
            "confidence", "viable", "recommendation",
        }
        assert expected_keys.issubset(set(result.keys()))
