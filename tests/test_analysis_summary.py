"""Testes unitarios para core/analysis_summary.py."""

import pytest

from core.analysis_summary import (
    AnalysisSummary,
    _extract_column_from_key,
    build_analysis_summary,
)
from core.models.column_profile import ColumnProfile
from core.models.enums import (
    ConfidenceLevel,
    ProposalCategory,
    RecommendationTier,
    RuleType,
    SemanticType,
    SeriesRegime,
)
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.rule_selection import RuleSelection
from core.rule_recommender import ColumnExclusion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(name: str, stype: SemanticType = SemanticType.NUMERIC, null_ratio: float = 0.0) -> ColumnProfile:
    return ColumnProfile(
        column_name=name,
        athena_type="double",
        inferred_semantic_type=stype,
        total_count=1000,
        non_null_count=int(1000 * (1 - null_ratio)),
        distinct_count=100,
        null_ratio=null_ratio,
        distinct_ratio=0.1,
    )


def _make_proposal(
    col: str = "COL_A",
    rule_type: RuleType = RuleType.MEAN_DUAL_GUARD,
    coverage: float = 95.0,
    fp: int = 0,
    stability: float = 0.9,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    tier: RecommendationTier = RecommendationTier.RECOMMENDED,
    category: ProposalCategory = ProposalCategory.STRONG,
    target_column: str | None = None,
) -> RuleProposal:
    """Cria proposta minima para testes."""
    return RuleProposal(
        id=f"test-{col}-{rule_type.value}",
        target_column=target_column if target_column is not None else col,
        target_table="test_table",
        rule_type=rule_type,
        metric_name=rule_type.value,
        backtest=BacktestSummary(
            total_periods=30,
            periods_pass=int(30 * coverage / 100),
            periods_fail=30 - int(30 * coverage / 100),
            coverage_pct=coverage,
            false_positive_proxy=fp,
            band_width_ratio=0.1,
            stability_score=stability,
            has_drift=False,
        ),
        confidence=confidence,
        recommendation_tier=tier,
        proposal_category=category,
        priority_score=0.85,
    )


def _make_selection(proposal: RuleProposal) -> RuleSelection:
    return RuleSelection(
        proposal_id=proposal.id,
        proposal=proposal,
        final_gdq_syntax=proposal.gdq_syntax_preview,
    )


class _FakeSeriesProfile:
    """Stub minimo de SeriesProfile para testes."""
    def __init__(self, regime: SeriesRegime):
        self.regime = regime


# ---------------------------------------------------------------------------
# Tests: empty inputs
# ---------------------------------------------------------------------------

class TestEmptyInputs:
    def test_no_profiles_no_proposals(self):
        s = build_analysis_summary([], [], [])
        assert s.total_columns == 0
        assert s.columns_with_proposals == 0
        assert s.columns_in_cart == 0
        assert s.total_proposals == 0
        assert s.rules_in_cart == 0
        assert s.avg_coverage == 0.0
        assert s.avg_confidence_score == 0.0
        assert s.by_semantic_type == {}
        assert s.by_proposal_category == {}

    def test_profiles_only(self):
        profiles = [_make_profile("A"), _make_profile("B")]
        s = build_analysis_summary(profiles, [], [])
        assert s.total_columns == 2
        assert s.columns_with_proposals == 0
        assert s.total_proposals == 0


# ---------------------------------------------------------------------------
# Tests: semantic type distribution
# ---------------------------------------------------------------------------

class TestSemanticTypeDistribution:
    def test_single_type(self):
        profiles = [_make_profile("A"), _make_profile("B")]
        s = build_analysis_summary(profiles, [], [])
        assert s.by_semantic_type == {"numeric": 2}

    def test_mixed_types(self):
        profiles = [
            _make_profile("A", SemanticType.NUMERIC),
            _make_profile("B", SemanticType.CATEGORICAL_LOW_CARDINALITY),
            _make_profile("C", SemanticType.CATEGORICAL_LOW_CARDINALITY),
            _make_profile("D", SemanticType.DATETIME),
        ]
        s = build_analysis_summary(profiles, [], [])
        assert s.by_semantic_type == {
            "numeric": 1,
            "categorical_low": 2,
            "datetime": 1,
        }


# ---------------------------------------------------------------------------
# Tests: proposal category distribution
# ---------------------------------------------------------------------------

class TestProposalCategoryDistribution:
    def test_counts_all_categories(self):
        proposals = [
            _make_proposal("A", category=ProposalCategory.STRONG),
            _make_proposal("B", category=ProposalCategory.STRONG),
            _make_proposal("C", category=ProposalCategory.NEEDS_REVIEW),
            _make_proposal("D", category=ProposalCategory.NOT_RECOMMENDED,
                           tier=RecommendationTier.NOT_RECOMMENDED),
        ]
        s = build_analysis_summary([], proposals, [])
        assert s.by_proposal_category["strong"] == 2
        assert s.by_proposal_category["needs_review"] == 1
        assert s.by_proposal_category["not_recommended"] == 1


# ---------------------------------------------------------------------------
# Tests: columns with proposals
# ---------------------------------------------------------------------------

class TestColumnsWithProposals:
    def test_counts_distinct_columns(self):
        proposals = [
            _make_proposal("A"),
            _make_proposal("A", rule_type=RuleType.COMPLETENESS,
                           category=ProposalCategory.CONSERVATIVE),
            _make_proposal("B"),
        ]
        s = build_analysis_summary([], proposals, [])
        assert s.columns_with_proposals == 2

    def test_excludes_not_recommended(self):
        proposals = [
            _make_proposal("A", tier=RecommendationTier.NOT_RECOMMENDED,
                           category=ProposalCategory.NOT_RECOMMENDED),
        ]
        s = build_analysis_summary([], proposals, [])
        assert s.columns_with_proposals == 0

    def test_includes_possible(self):
        proposals = [
            _make_proposal("A", tier=RecommendationTier.POSSIBLE,
                           category=ProposalCategory.NEEDS_REVIEW),
        ]
        s = build_analysis_summary([], proposals, [])
        assert s.columns_with_proposals == 1

    def test_table_proposals_counted(self):
        p = _make_proposal("TABLE", rule_type=RuleType.ROW_COUNT_DUAL_GUARD)
        p.target_column = None  # table-level rule
        s = build_analysis_summary([], [p], [])
        assert s.columns_with_proposals == 1


# ---------------------------------------------------------------------------
# Tests: cart metrics
# ---------------------------------------------------------------------------

class TestCartMetrics:
    def test_columns_in_cart(self):
        p1 = _make_proposal("A")
        p2 = _make_proposal("A", rule_type=RuleType.COMPLETENESS,
                            category=ProposalCategory.CONSERVATIVE)
        p3 = _make_proposal("B")
        cart = [_make_selection(p1), _make_selection(p2), _make_selection(p3)]
        s = build_analysis_summary([], [], cart)
        assert s.columns_in_cart == 2
        assert s.rules_in_cart == 3

    def test_empty_cart(self):
        s = build_analysis_summary([], [], [])
        assert s.columns_in_cart == 0
        assert s.rules_in_cart == 0


# ---------------------------------------------------------------------------
# Tests: excluded columns
# ---------------------------------------------------------------------------

class TestExcludedColumns:
    def test_passthrough_exclusions(self):
        exclusions = [
            ColumnExclusion("DT_REF", SemanticType.DATETIME,
                            "Coluna temporal"),
        ]
        s = build_analysis_summary([], [], [], exclusions=exclusions)
        assert len(s.excluded_columns) == 1
        assert s.excluded_columns[0].column_name == "DT_REF"

    def test_auto_generates_exclusions(self):
        profiles = [_make_profile("DT_REF", SemanticType.DATETIME)]
        s = build_analysis_summary(profiles, [], [])
        assert len(s.excluded_columns) == 1


# ---------------------------------------------------------------------------
# Tests: experimental in cart (legacy field, always 0 now)
# ---------------------------------------------------------------------------

class TestExperimentalInCart:
    def test_zero_with_validated_rules(self):
        """No proposals are classified as EXPERIMENTAL anymore."""
        p1 = _make_proposal("A", category=ProposalCategory.STRONG)
        p2 = _make_proposal("B", category=ProposalCategory.STRONG)
        cart = [_make_selection(p1), _make_selection(p2)]
        s = build_analysis_summary([], [], cart)
        assert s.experimental_in_cart == 0

    def test_zero_if_none(self):
        p1 = _make_proposal("A", category=ProposalCategory.STRONG)
        cart = [_make_selection(p1)]
        s = build_analysis_summary([], [], cart)
        assert s.experimental_in_cart == 0


# ---------------------------------------------------------------------------
# Tests: low coverage detection
# ---------------------------------------------------------------------------

class TestLowCoverage:
    def test_detects_low_coverage(self):
        proposals = [
            _make_proposal("A", coverage=95.0),
            _make_proposal("B", coverage=70.0),
            _make_proposal("C", coverage=60.0),
        ]
        s = build_analysis_summary([], proposals, [])
        assert s.low_coverage_rules == 2

    def test_excludes_not_recommended(self):
        proposals = [
            _make_proposal("A", coverage=50.0,
                           tier=RecommendationTier.NOT_RECOMMENDED,
                           category=ProposalCategory.NOT_RECOMMENDED),
        ]
        s = build_analysis_summary([], proposals, [])
        assert s.low_coverage_rules == 0

    def test_no_backtest(self):
        p = _make_proposal("A")
        p.backtest = None
        s = build_analysis_summary([], [p], [])
        assert s.low_coverage_rules == 0


# ---------------------------------------------------------------------------
# Tests: problematic regimes
# ---------------------------------------------------------------------------

class TestProblematicRegimes:
    def test_detects_structural_break(self):
        series = {"series_profile_COL_A_30": _FakeSeriesProfile(SeriesRegime.STRUCTURAL_BREAK)}
        s = build_analysis_summary([], [], [], series_profiles=series)
        assert "structural_break" in s.problematic_regimes
        assert "COL_A" in s.problematic_regimes["structural_break"]

    def test_ignores_stable(self):
        series = {"series_profile_COL_A_30": _FakeSeriesProfile(SeriesRegime.STABLE)}
        s = build_analysis_summary([], [], [], series_profiles=series)
        assert len(s.problematic_regimes) == 0

    def test_multiple_regimes(self):
        series = {
            "series_profile_COL_A_30": _FakeSeriesProfile(SeriesRegime.SPARSE),
            "series_profile_COL_B_30": _FakeSeriesProfile(SeriesRegime.VOLATILE),
        }
        s = build_analysis_summary([], [], [], series_profiles=series)
        assert "sparse" in s.problematic_regimes
        assert "volatile" in s.problematic_regimes


# ---------------------------------------------------------------------------
# Tests: averages
# ---------------------------------------------------------------------------

class TestAverages:
    def test_avg_coverage(self):
        proposals = [
            _make_proposal("A", coverage=90.0),
            _make_proposal("B", coverage=80.0),
        ]
        s = build_analysis_summary([], proposals, [])
        assert s.avg_coverage == 85.0

    def test_avg_coverage_excludes_not_recommended(self):
        proposals = [
            _make_proposal("A", coverage=90.0),
            _make_proposal("B", coverage=30.0,
                           tier=RecommendationTier.NOT_RECOMMENDED,
                           category=ProposalCategory.NOT_RECOMMENDED),
        ]
        s = build_analysis_summary([], proposals, [])
        assert s.avg_coverage == 90.0

    def test_avg_confidence_score(self):
        p1 = _make_proposal("A", confidence=ConfidenceLevel.HIGH)
        p2 = _make_proposal("B", confidence=ConfidenceLevel.MEDIUM)
        p3 = _make_proposal("C", confidence=ConfidenceLevel.LOW)
        cart = [_make_selection(p1), _make_selection(p2), _make_selection(p3)]
        s = build_analysis_summary([], [], cart)
        assert s.avg_confidence_score == 0.5  # (1.0 + 0.5 + 0.0) / 3

    def test_avg_confidence_empty_cart(self):
        s = build_analysis_summary([], [], [])
        assert s.avg_confidence_score == 0.0


# ---------------------------------------------------------------------------
# Tests: extract column from key
# ---------------------------------------------------------------------------

class TestExtractColumnFromKey:
    def test_standard_key(self):
        assert _extract_column_from_key("series_profile_VLR_SALDO_30") == "VLR_SALDO"

    def test_simple_col(self):
        assert _extract_column_from_key("series_profile_AMOUNT_45") == "AMOUNT"

    def test_non_matching_prefix(self):
        assert _extract_column_from_key("other_key") is None

    def test_no_underscore_after_prefix(self):
        assert _extract_column_from_key("series_profile_COL") == "COL"


# ---------------------------------------------------------------------------
# Tests: frozen dataclass
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_cannot_mutate(self):
        s = build_analysis_summary([], [], [])
        with pytest.raises(AttributeError):
            s.total_columns = 99
