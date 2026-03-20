"""Testes Sprint B2: categóricas — fixtures, backtest, generator, proposal."""

import math

import pandas as pd
import pytest

from core.backtest import backtest_frequency_band
from core.gdq_rule_generator import GDQRuleGenerator
from core.models.baseline import BaselineStrategy
from core.models.column_profile import ColumnProfile
from core.models.enums import (
    BaselineMethod,
    ConfidenceLevel,
    RuleType,
    SemanticType,
)
from core.models.rule_proposal import RuleProposal
from core.rule_explainer import explain_rule, explain_rule_detail
from core.rule_scoring import score_proposal
from core.statistical_engine import compute_frequency_band
from services.proposal_service import ProposalService
from tests.fixtures import (
    make_category_shift,
    make_stable_categories,
    make_rare_category,
    make_emerging_category,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class TestCategoryFixtures:

    def test_category_shift_structure(self):
        data = make_category_shift()
        assert "dates" in data
        assert "distributions" in data
        assert "series" in data
        assert "domain" in data
        assert "distinct_counts" in data
        assert len(data["dates"]) == 30
        assert len(data["distributions"]) == 30
        assert set(data["domain"]) == {"A", "B", "C"}

    def test_category_shift_values_sum_to_100(self):
        data = make_category_shift()
        for dist in data["distributions"]:
            total = sum(dist.values())
            assert abs(total - 100.0) < 0.1

    def test_category_shift_series_match_distributions(self):
        data = make_category_shift()
        for cat in data["domain"]:
            assert len(data["series"][cat]) == 30

    def test_category_shift_has_shift(self):
        data = make_category_shift()
        series_a = data["series"]["A"]
        first_half_mean = sum(series_a[:15]) / 15
        second_half_mean = sum(series_a[15:]) / 15
        assert first_half_mean > 60  # ~70%
        assert second_half_mean < 40  # ~30%

    def test_stable_categories(self):
        data = make_stable_categories()
        assert set(data["domain"]) == {"A", "B", "C", "D"}
        series_a = data["series"]["A"]
        mean_a = sum(series_a) / len(series_a)
        assert 45 < mean_a < 55  # ~50%

    def test_rare_category(self):
        data = make_rare_category()
        assert "RARE" in data["domain"]
        series_rare = data["series"]["RARE"]
        mean_rare = sum(series_rare) / len(series_rare)
        assert mean_rare < 5  # ~2%

    def test_emerging_category(self):
        data = make_emerging_category()
        series_d = data["series"].get("D", [])
        # D should be 0 in first 2/3, >0 in last 1/3
        first_part = series_d[:20]
        last_part = series_d[20:]
        # First 2/3 should be 0 (D doesn't exist in those periods)
        assert all(v == 0 for v in first_part)
        assert any(v > 10 for v in last_part)


# ---------------------------------------------------------------------------
# compute_frequency_band with n_sigma
# ---------------------------------------------------------------------------

class TestFrequencyBandNSigma:

    def test_n_sigma_parameter(self):
        data = make_stable_categories()
        series_a = data["series"]["A"]
        band_2 = compute_frequency_band(series_a, 20, margin_pct=5.0, n_sigma=2.0)
        band_3 = compute_frequency_band(series_a, 20, margin_pct=5.0, n_sigma=3.0)
        assert band_3["upper"] > band_2["upper"]
        assert band_3["lower"] < band_2["lower"]

    def test_returns_std(self):
        data = make_stable_categories()
        band = compute_frequency_band(data["series"]["A"], 20, margin_pct=5.0)
        assert "std" in band
        assert band["std"] > 0

    def test_returns_n_sigma(self):
        band = compute_frequency_band([50.0] * 10, 10, n_sigma=3.0)
        assert band["n_sigma"] == 3.0

    def test_rare_category_clamps_lower(self):
        data = make_rare_category()
        band = compute_frequency_band(data["series"]["RARE"], 20, margin_pct=2.0)
        assert band["lower"] >= -0.01

    def test_dominant_category_clamps_upper(self):
        data = make_rare_category()
        band = compute_frequency_band(data["series"]["DOM"], 20, margin_pct=2.0)
        assert band["upper"] <= 100.01


# ---------------------------------------------------------------------------
# backtest_frequency_band
# ---------------------------------------------------------------------------

class TestBacktestFrequencyBand:

    def test_empty_series(self):
        bt = backtest_frequency_band([], [], 20)
        assert bt.total_periods == 0

    def test_too_few_points(self):
        bt = backtest_frequency_band([50.0, 50.0], ["d1", "d2"], 20)
        assert bt.total_periods == 0

    def test_stable_series_high_coverage(self):
        data = make_stable_categories()
        bt = backtest_frequency_band(
            pct_series=data["series"]["A"],
            dates=data["dates"],
            n_periods=15,
            margin_pct=5.0,
            n_sigma=2.0,
        )
        assert bt.total_periods > 0
        assert bt.coverage_pct >= 80.0

    def test_shift_detects_failures(self):
        data = make_category_shift()
        bt = backtest_frequency_band(
            pct_series=data["series"]["A"],
            dates=data["dates"],
            n_periods=10,
            margin_pct=3.0,
            n_sigma=2.0,
        )
        assert bt.periods_fail > 0

    def test_stability_returned(self):
        data = make_stable_categories()
        bt = backtest_frequency_band(
            pct_series=data["series"]["B"],
            dates=data["dates"],
            n_periods=15,
            margin_pct=5.0,
        )
        assert 0.0 <= bt.stability_score <= 1.0

    def test_drift_detection_on_shift(self):
        data = make_category_shift()
        bt = backtest_frequency_band(
            pct_series=data["series"]["B"],
            dates=data["dates"],
            n_periods=10,
            margin_pct=3.0,
        )
        # B shifts from ~20% to ~50%, should detect drift
        assert bt.has_drift is True

    def test_nan_in_series(self):
        series = [50.0] * 10 + [float("nan")] + [50.0] * 10
        dates = [f"d{i}" for i in range(len(series))]
        bt = backtest_frequency_band(series, dates, 10, margin_pct=5.0)
        assert bt.total_periods > 0


# ---------------------------------------------------------------------------
# GDQ Generator — category frequency + distinct count range
# ---------------------------------------------------------------------------

class TestGDQGeneratorCategorical:

    def setup_method(self):
        self.gen = GDQRuleGenerator()

    def test_category_frequency_static(self):
        p = RuleProposal(
            id="1", target_column="STATUS", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            metric_name="cat_freq_A",
            category_value="A",
            suggested_lower=25.0, suggested_upper=35.0,
        )
        syntax = self.gen.generate(p)
        assert 'CustomSql' in syntax
        assert 'STATUS' in syntax and "'A'" in syntax
        assert '"STATUS"' not in syntax  # sem aspas no nome da coluna
        assert 'between 25.00 and 35.00' in syntax
        assert 'from primary' in syntax

    def test_distinct_count_range(self):
        p = RuleProposal(
            id="2", target_column="TIPO", target_table="t",
            rule_type=RuleType.DISTINCT_COUNT_RANGE,
            metric_name="distinct_count_range",
            suggested_lower=10.0, suggested_upper=15.0,
        )
        syntax = self.gen.generate(p)
        assert "(DistinctValuesCount TIPO >= 10)" in syntax
        assert "(DistinctValuesCount TIPO <= 15)" in syntax
        assert "AND" in syntax

    def test_category_frequency_dynamic_generates_syntax(self):
        """DYNAMIC generates CustomSql with avg(last(N))."""
        p = RuleProposal(
            id="3", target_column="STATUS", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            metric_name="cat_freq",
            category_value="A",
            baseline_window=30,
            baseline_n_sigma=2.0,
            baseline_margin_pct=0.10,
        )
        syntax = self.gen.generate(p)
        assert 'CustomSql' in syntax
        assert 'STATUS' in syntax and "'A'" in syntax
        assert '"STATUS"' not in syntax  # sem aspas no nome da coluna
        assert 'avg(last(30))' in syntax
        assert 'std(last(30))' in syntax
        assert 'from primary' in syntax
        assert 'OR' in syntax

    def test_allowed_values_still_works(self):
        p = RuleProposal(
            id="4", target_column="UF", target_table="t",
            rule_type=RuleType.ALLOWED_VALUES,
            metric_name="allowed_values",
            suggested_values=["SP", "RJ", "MG"],
        )
        syntax = self.gen.generate(p)
        assert "ColumnValues UF in ['SP', 'RJ', 'MG']" == syntax


# ---------------------------------------------------------------------------
# ProposalService.propose_categorical_rules
# ---------------------------------------------------------------------------

def _make_distribution_df(data: dict, cat_value: str) -> pd.DataFrame:
    """Build distribution DataFrame from fixture data."""
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
    """Build domain DataFrame from fixture data."""
    rows = []
    for cat in data["domain"]:
        total_pct = sum(d.get(cat, 0) for d in data["distributions"]) / len(data["distributions"])
        rows.append({
            "category_value": cat,
            "value_count": int(total_pct * 100),
            "value_pct": total_pct,
        })
    return pd.DataFrame(rows).sort_values("value_count", ascending=False).reset_index(drop=True)


class TestProposalServiceCategorical:

    def setup_method(self):
        self.svc = ProposalService()
        self.baseline = BaselineStrategy(
            method=BaselineMethod.LAST_N_PERIODS,
            n_periods=15,
            n_sigma=2.0,
            margin_pct=0.10,
        )

    def _make_profile(self, col: str, sem_type: SemanticType, n_distinct: int = 3):
        return ColumnProfile(
            column_name=col,
            athena_type="string",
            inferred_semantic_type=sem_type,
            distinct_count=n_distinct,
            null_ratio=0.02,
        )

    def test_cat_low_generates_all_rule_types(self):
        data = make_stable_categories()
        dist_df = _make_distribution_df(data, "A")
        domain_df = _make_domain_df(data)
        profile = self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY, 4)

        proposals = self.svc.propose_categorical_rules(
            dist_df, domain_df, "COL", "t", profile, self.baseline,
        )

        rule_types = {p.rule_type for p in proposals}
        assert RuleType.ALLOWED_VALUES in rule_types
        assert RuleType.DISTINCT_COUNT_EXACT in rule_types
        assert RuleType.CATEGORY_FREQUENCY_STATIC in rule_types
        assert RuleType.COMPLETENESS in rule_types

    def test_cat_mid_generates_range_and_topk(self):
        data = make_stable_categories()
        dist_df = _make_distribution_df(data, "A")
        domain_df = _make_domain_df(data)
        profile = self._make_profile("COL", SemanticType.CATEGORICAL_MID_CARDINALITY, 100)

        proposals = self.svc.propose_categorical_rules(
            dist_df, domain_df, "COL", "t", profile, self.baseline,
        )

        rule_types = {p.rule_type for p in proposals}
        # No AllowedValues for mid
        assert RuleType.ALLOWED_VALUES not in rule_types
        # Has range instead of exact
        assert RuleType.DISTINCT_COUNT_RANGE in rule_types
        assert RuleType.CATEGORY_FREQUENCY_STATIC in rule_types

    def test_cat_high_only_completeness(self):
        data = make_stable_categories()
        dist_df = _make_distribution_df(data, "A")
        domain_df = _make_domain_df(data)
        profile = self._make_profile("COL", SemanticType.CATEGORICAL_HIGH_CARDINALITY, 1000)

        proposals = self.svc.propose_categorical_rules(
            dist_df, domain_df, "COL", "t", profile, self.baseline,
        )

        rule_types = {p.rule_type for p in proposals}
        assert RuleType.ALLOWED_VALUES not in rule_types
        assert RuleType.CATEGORY_FREQUENCY_STATIC not in rule_types
        assert RuleType.COMPLETENESS in rule_types

    def test_frequency_proposal_has_category_value(self):
        data = make_stable_categories()
        dist_df = _make_distribution_df(data, "A")
        domain_df = _make_domain_df(data)
        profile = self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY, 4)

        proposals = self.svc.propose_categorical_rules(
            dist_df, domain_df, "COL", "t", profile, self.baseline,
        )

        freq_proposals = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_STATIC]
        assert len(freq_proposals) == 4  # one per category
        for p in freq_proposals:
            assert p.category_value is not None
            assert p.gdq_syntax_preview != ""
            assert "CustomSql" in p.gdq_syntax_preview

    def test_frequency_proposals_have_backtest(self):
        data = make_stable_categories()
        dist_df = _make_distribution_df(data, "A")
        domain_df = _make_domain_df(data)
        profile = self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY, 4)

        proposals = self.svc.propose_categorical_rules(
            dist_df, domain_df, "COL", "t", profile, self.baseline,
        )

        freq_proposals = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_STATIC]
        for p in freq_proposals:
            assert p.backtest is not None
            assert p.backtest.total_periods > 0

    def test_empty_domain(self):
        proposals = self.svc.propose_categorical_rules(
            pd.DataFrame(), pd.DataFrame(), "COL", "t",
            self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY),
            self.baseline,
        )
        assert proposals == []

    def test_allowed_values_syntax(self):
        data = make_stable_categories()
        dist_df = _make_distribution_df(data, "A")
        domain_df = _make_domain_df(data)
        profile = self._make_profile("COL", SemanticType.CATEGORICAL_LOW_CARDINALITY, 4)

        proposals = self.svc.propose_categorical_rules(
            dist_df, domain_df, "COL", "t", profile, self.baseline,
        )

        av_proposals = [p for p in proposals if p.rule_type == RuleType.ALLOWED_VALUES]
        assert len(av_proposals) == 1
        assert "ColumnValues COL in [" in av_proposals[0].gdq_syntax_preview


# ---------------------------------------------------------------------------
# Rule Explainer — categorical
# ---------------------------------------------------------------------------

class TestRuleExplainerCategorical:

    def test_explain_frequency_with_value(self):
        p = RuleProposal(
            id="1", target_column="STATUS", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            metric_name="cat_freq_A", category_value="A",
            suggested_lower=25.0, suggested_upper=35.0,
        )
        text = explain_rule(p)
        assert "frequencia" in text
        assert "`A`" in text
        assert "25.0%" in text
        assert "35.0%" in text

    def test_explain_distinct_count_range(self):
        p = RuleProposal(
            id="2", target_column="COL", target_table="t",
            rule_type=RuleType.DISTINCT_COUNT_RANGE,
            metric_name="dc_range",
            suggested_lower=10.0, suggested_upper=15.0,
        )
        text = explain_rule(p)
        assert "10" in text
        assert "15" in text

    def test_explain_params_frequency(self):
        p = RuleProposal(
            id="3", target_column="COL", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            metric_name="cat_freq_X", category_value="X",
            suggested_lower=10.0, suggested_upper=20.0,
        )
        detail = explain_rule_detail(p)
        assert "10.0%" in detail
        assert "20.0%" in detail

    def test_explain_params_primary_key(self):
        p = RuleProposal(
            id="4", target_column=None, target_table="t",
            rule_type=RuleType.IS_PRIMARY_KEY,
            metric_name="pk",
            suggested_values=["COL_A", "COL_B"],
        )
        detail = explain_rule_detail(p)
        assert "COL_A" in detail
        assert "COL_B" in detail


# ---------------------------------------------------------------------------
# Scoring for categorical rules
# ---------------------------------------------------------------------------

class TestScoringCategorical:

    def test_frequency_with_backtest(self):
        data = make_stable_categories()
        bt = backtest_frequency_band(
            data["series"]["A"], data["dates"], 15, margin_pct=5.0,
        )
        p = RuleProposal(
            id="1", target_column="COL", target_table="t",
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            metric_name="cat_freq_A",
            backtest=bt,
        )
        score = score_proposal(p, data["series"]["A"])
        assert score.coverage >= 0
        assert score.interpretability == 0.8
        assert score.cost_efficiency == 0.7

    def test_allowed_values_without_backtest(self):
        p = RuleProposal(
            id="2", target_column="COL", target_table="t",
            rule_type=RuleType.ALLOWED_VALUES,
            metric_name="av",
        )
        score = score_proposal(p)
        assert score.confidence == ConfidenceLevel.LOW
        assert score.interpretability == 0.9
