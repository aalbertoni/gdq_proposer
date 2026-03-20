"""Testes unitarios para core/rule_recommender.py."""

import pytest

from core.models.enums import (
    ConfidenceLevel,
    ProposalCategory,
    RecommendationTier,
    RuleType,
    SemanticType,
    SeriesRegime,
)
from core.models.column_profile import ColumnProfile
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.series_profile import SeriesProfile
from core.rule_recommender import (
    ColumnExclusion,
    classify_proposal,
    detect_redundancies,
    explain_column_exclusions,
    select_minimal_set,
    compute_priority_score,
    prioritize_proposals,
    recommend_tier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bt(
    coverage: float = 95.0,
    fp: int = 0,
    stability: float = 0.9,
    total_periods: int = 30,
    drift: bool = False,
) -> BacktestSummary:
    return BacktestSummary(
        total_periods=total_periods,
        periods_pass=int(total_periods * coverage / 100),
        periods_fail=total_periods - int(total_periods * coverage / 100),
        coverage_pct=coverage,
        false_positive_proxy=fp,
        band_width_ratio=0.05,
        stability_score=stability,
        has_drift=drift,
    )


def _proposal(
    rule_type: RuleType = RuleType.MEAN_DUAL_GUARD,
    backtest: BacktestSummary | None = None,
    suggested_lower: float | None = None,
    **kwargs,
) -> RuleProposal:
    return RuleProposal(
        id="test",
        target_column="VLR_SALDO",
        target_table="tb_test",
        rule_type=rule_type,
        metric_name=rule_type.value,
        backtest=backtest,
        suggested_lower=suggested_lower,
        **kwargs,
    )


def _stable_profile() -> SeriesProfile:
    return SeriesProfile(
        regime=SeriesRegime.STABLE,
        n_points=45, n_valid=45,
        cv=0.05, skewness=0.1, zero_pct=0.0, null_pct=0.0,
        n_outliers_iqr=0,
        drift_slope=0.0, drift_r_squared=0.0,
        seasonality_strength=0.0, seasonality_amplitude_ratio=0.0,
        change_point_magnitude=0.0,
    )


def _profile(regime: SeriesRegime, **kwargs) -> SeriesProfile:
    defaults = dict(
        regime=regime,
        n_points=45, n_valid=45,
        cv=0.05, skewness=0.1, zero_pct=0.0, null_pct=0.0,
        n_outliers_iqr=0,
        drift_slope=0.0, drift_r_squared=0.0,
        seasonality_strength=0.0, seasonality_amplitude_ratio=0.0,
        change_point_magnitude=0.0,
    )
    defaults.update(kwargs)
    return SeriesProfile(**defaults)


# ---------------------------------------------------------------------------
# RECOMMENDED: serie estavel, boa cobertura, poucos FPs
# ---------------------------------------------------------------------------

class TestRecommended:
    def test_stable_high_coverage(self):
        p = _proposal(backtest=_bt(coverage=95, fp=0, stability=0.9))
        tier, reasons = recommend_tier(p, _stable_profile())
        assert tier == RecommendationTier.RECOMMENDED
        assert len(reasons) == 0

    def test_completeness_non_trivial(self):
        p = _proposal(
            rule_type=RuleType.COMPLETENESS,
            backtest=_bt(coverage=95, fp=1),
            suggested_lower=0.95,
        )
        tier, _ = recommend_tier(p, _stable_profile())
        assert tier == RecommendationTier.RECOMMENDED

    def test_allowed_values_good(self):
        p = _proposal(
            rule_type=RuleType.ALLOWED_VALUES,
            backtest=_bt(coverage=100, fp=0),
        )
        tier, _ = recommend_tier(p)
        assert tier == RecommendationTier.RECOMMENDED


# ---------------------------------------------------------------------------
# POSSIBLE: metricas moderadas ou regime cauteloso
# ---------------------------------------------------------------------------

class TestPossible:
    def test_moderate_coverage(self):
        p = _proposal(backtest=_bt(coverage=70, fp=1))
        tier, reasons = recommend_tier(p, _stable_profile())
        assert tier == RecommendationTier.POSSIBLE
        assert any("Cobertura moderada" in r for r in reasons)

    def test_moderate_fp(self):
        p = _proposal(backtest=_bt(coverage=90, fp=4))
        tier, reasons = recommend_tier(p)
        assert tier == RecommendationTier.POSSIBLE
        assert any("falso positivo" in r.lower() for r in reasons)

    def test_volatile_regime(self):
        p = _proposal(backtest=_bt(coverage=95, fp=0))
        prof = _profile(SeriesRegime.VOLATILE, cv=0.40)
        tier, reasons = recommend_tier(p, prof)
        assert tier == RecommendationTier.POSSIBLE
        assert any("volatile" in r for r in reasons)

    def test_sparse_regime(self):
        p = _proposal(backtest=_bt(coverage=90, fp=0))
        prof = _profile(SeriesRegime.SPARSE, null_pct=0.35)
        tier, reasons = recommend_tier(p, prof)
        assert tier == RecommendationTier.POSSIBLE
        assert any("sparse" in r for r in reasons)

    def test_zero_inflated_regime(self):
        p = _proposal(backtest=_bt(coverage=90, fp=0))
        prof = _profile(SeriesRegime.ZERO_INFLATED, zero_pct=0.40)
        tier, reasons = recommend_tier(p, prof)
        assert tier == RecommendationTier.POSSIBLE
        assert any("zero_inflated" in r for r in reasons)

    def test_secondary_hostile_regime(self):
        """Regime secundario hostil rebaixa para POSSIBLE (nao NOT_RECOMMENDED)."""
        p = _proposal(backtest=_bt(coverage=95, fp=0))
        prof = _profile(
            SeriesRegime.TRENDING,
            secondary_regimes=(SeriesRegime.STRUCTURAL_BREAK,),
        )
        tier, reasons = recommend_tier(p, prof)
        assert tier == RecommendationTier.POSSIBLE
        assert any("secundario" in r for r in reasons)


# ---------------------------------------------------------------------------
# NOT_RECOMMENDED: falhas graves ou contexto hostil
# ---------------------------------------------------------------------------

class TestNotRecommended:
    def test_no_backtest(self):
        p = _proposal(backtest=None)
        tier, reasons = recommend_tier(p)
        assert tier == RecommendationTier.NOT_RECOMMENDED
        assert any("backtest" in r.lower() for r in reasons)

    def test_low_coverage(self):
        p = _proposal(backtest=_bt(coverage=40))
        tier, reasons = recommend_tier(p)
        assert tier == RecommendationTier.NOT_RECOMMENDED
        assert any("Cobertura insuficiente" in r for r in reasons)

    def test_high_fp(self):
        p = _proposal(backtest=_bt(coverage=90, fp=8))
        tier, reasons = recommend_tier(p)
        assert tier == RecommendationTier.NOT_RECOMMENDED
        assert any("falso positivo" in r for r in reasons)

    def test_structural_break_mean(self):
        p = _proposal(backtest=_bt(coverage=95, fp=0))
        prof = _profile(SeriesRegime.STRUCTURAL_BREAK)
        tier, reasons = recommend_tier(p, prof)
        assert tier == RecommendationTier.NOT_RECOMMENDED
        assert any("structural_break" in r for r in reasons)

    def test_structural_break_stddev(self):
        p = _proposal(
            rule_type=RuleType.STDDEV_DUAL_GUARD,
            backtest=_bt(coverage=95, fp=0),
        )
        prof = _profile(SeriesRegime.STRUCTURAL_BREAK)
        tier, reasons = recommend_tier(p, prof)
        assert tier == RecommendationTier.NOT_RECOMMENDED

    def test_completeness_trivial(self):
        """Completeness 1.0 com 100% coverage e 0 FPs = trivial."""
        p = _proposal(
            rule_type=RuleType.COMPLETENESS,
            backtest=_bt(coverage=100, fp=0),
            suggested_lower=1.0,
        )
        tier, reasons = recommend_tier(p)
        assert tier == RecommendationTier.NOT_RECOMMENDED
        assert any("trivial" in r.lower() for r in reasons)

    def test_dynamic_insufficient_history(self):
        """Below min_periods_possible (default 5) → NOT_RECOMMENDED."""
        p = _proposal(backtest=_bt(coverage=90, total_periods=3))
        tier, reasons = recommend_tier(p)
        assert tier == RecommendationTier.NOT_RECOMMENDED
        assert any("insuficiente" in r.lower() for r in reasons)

    def test_dynamic_limited_history_is_possible(self):
        """Between min_periods_possible (5) and min_periods_dynamic (10) → POSSIBLE."""
        p = _proposal(backtest=_bt(coverage=95, total_periods=7))
        tier, reasons = recommend_tier(p)
        assert tier == RecommendationTier.POSSIBLE
        assert any("limitado" in r.lower() for r in reasons)

    def test_low_score_with_hostile_profile(self):
        """Score cai abaixo do minimo com regime hostil + metricas ruins."""
        p = _proposal(
            rule_type=RuleType.ALLOWED_VALUES,  # nao dinamica, evita filtro de historico
            backtest=_bt(coverage=52, fp=0, stability=0.0),
        )
        # Profile hostil reduz regime_fit e robustness
        prof = _profile(
            SeriesRegime.STRUCTURAL_BREAK,
            n_valid=5, null_pct=0.50, n_outliers_iqr=10,
        )
        tier, reasons = recommend_tier(p, prof)
        # Structural break nao afeta AllowedValues, mas score baixo sim
        assert tier in (RecommendationTier.POSSIBLE, RecommendationTier.NOT_RECOMMENDED)


# ---------------------------------------------------------------------------
# Regras nao-dinamicas: sem filtro de historico minimo
# ---------------------------------------------------------------------------

class TestNonDynamicRules:
    def test_allowed_values_short_history_ok(self):
        """AllowedValues nao e dinamica — 7 periodos e suficiente."""
        p = _proposal(
            rule_type=RuleType.ALLOWED_VALUES,
            backtest=_bt(coverage=100, fp=0, total_periods=7),
        )
        tier, _ = recommend_tier(p)
        assert tier == RecommendationTier.RECOMMENDED

    def test_completeness_short_history_ok(self):
        """Completeness nao e dinamica — historico curto nao e bloqueante."""
        p = _proposal(
            rule_type=RuleType.COMPLETENESS,
            backtest=_bt(coverage=95, fp=1, total_periods=5),
            suggested_lower=0.90,
        )
        tier, _ = recommend_tier(p)
        assert tier in (RecommendationTier.RECOMMENDED, RecommendationTier.POSSIBLE)


# ---------------------------------------------------------------------------
# Integracao com RuleProposal
# ---------------------------------------------------------------------------

class TestProposalIntegration:
    def test_tier_stored_on_proposal(self):
        """RuleProposal tem campos de tier."""
        p = _proposal(backtest=_bt())
        tier, reasons = recommend_tier(p)
        p.recommendation_tier = tier
        p.recommendation_reasons = reasons
        assert p.recommendation_tier == RecommendationTier.RECOMMENDED
        assert isinstance(p.recommendation_reasons, list)

    def test_default_tier_is_recommended(self):
        """Novo RuleProposal tem tier RECOMMENDED por padrao."""
        p = _proposal()
        assert p.recommendation_tier == RecommendationTier.RECOMMENDED

    def test_reasons_always_list(self):
        """Reasons e sempre uma lista (vazia para RECOMMENDED)."""
        p = _proposal(backtest=_bt(coverage=95, fp=0))
        _, reasons = recommend_tier(p, _stable_profile())
        assert isinstance(reasons, list)

    def test_default_priority_score_is_zero(self):
        p = _proposal()
        assert p.priority_score == 0.0


# ---------------------------------------------------------------------------
# Priorizacao (ordenacao)
# ---------------------------------------------------------------------------

class TestPrioritizeProposals:
    def test_recommended_before_possible(self):
        rec = _proposal(backtest=_bt(coverage=95, fp=0))
        rec.recommendation_tier = RecommendationTier.RECOMMENDED
        rec.priority_score = 0.85

        pos = _proposal(backtest=_bt(coverage=70, fp=2))
        pos.recommendation_tier = RecommendationTier.POSSIBLE
        pos.priority_score = 0.60

        result = prioritize_proposals([pos, rec])
        assert result[0] is rec
        assert result[1] is pos

    def test_possible_before_not_recommended(self):
        pos = _proposal(backtest=_bt(coverage=70))
        pos.recommendation_tier = RecommendationTier.POSSIBLE
        pos.priority_score = 0.55

        nr = _proposal(backtest=_bt(coverage=40))
        nr.recommendation_tier = RecommendationTier.NOT_RECOMMENDED
        nr.priority_score = 0.30

        result = prioritize_proposals([nr, pos])
        assert result[0] is pos
        assert result[1] is nr

    def test_same_tier_higher_score_first(self):
        high = _proposal(backtest=_bt(coverage=95, fp=0))
        high.recommendation_tier = RecommendationTier.RECOMMENDED
        high.priority_score = 0.90

        low = _proposal(backtest=_bt(coverage=85, fp=1))
        low.recommendation_tier = RecommendationTier.RECOMMENDED
        low.priority_score = 0.75

        result = prioritize_proposals([low, high])
        assert result[0] is high
        assert result[1] is low

    def test_same_tier_same_score_higher_coverage_first(self):
        a = _proposal(backtest=_bt(coverage=95))
        a.recommendation_tier = RecommendationTier.RECOMMENDED
        a.priority_score = 0.85

        b = _proposal(backtest=_bt(coverage=80))
        b.recommendation_tier = RecommendationTier.RECOMMENDED
        b.priority_score = 0.85

        result = prioritize_proposals([b, a])
        assert result[0] is a

    def test_same_everything_fewer_fp_first(self):
        a = _proposal(backtest=_bt(coverage=90, fp=0))
        a.recommendation_tier = RecommendationTier.RECOMMENDED
        a.priority_score = 0.85

        b = _proposal(backtest=_bt(coverage=90, fp=2))
        b.recommendation_tier = RecommendationTier.RECOMMENDED
        b.priority_score = 0.85

        result = prioritize_proposals([b, a])
        assert result[0] is a

    def test_empty_list(self):
        assert prioritize_proposals([]) == []

    def test_single_proposal(self):
        p = _proposal(backtest=_bt())
        result = prioritize_proposals([p])
        assert result == [p]

    def test_does_not_mutate_original(self):
        a = _proposal(backtest=_bt(coverage=90))
        a.recommendation_tier = RecommendationTier.RECOMMENDED
        a.priority_score = 0.85

        b = _proposal(backtest=_bt(coverage=50))
        b.recommendation_tier = RecommendationTier.NOT_RECOMMENDED
        b.priority_score = 0.30

        original = [b, a]
        result = prioritize_proposals(original)
        assert original[0] is b  # original nao muda
        assert result[0] is a  # resultado reordenado


class TestComputePriorityScore:
    def test_good_backtest_high_score(self):
        p = _proposal(backtest=_bt(coverage=95, fp=0, stability=0.9))
        score = compute_priority_score(p)
        assert score >= 0.80

    def test_no_backtest_zero(self):
        p = _proposal(backtest=None)
        assert compute_priority_score(p) == 0.0

    def test_low_coverage_low_score(self):
        p = _proposal(backtest=_bt(coverage=50, fp=0, stability=0.3))
        score = compute_priority_score(p)
        assert score < 0.75

    def test_fp_penalty_reduces_score(self):
        no_fp = _proposal(backtest=_bt(coverage=90, fp=0, stability=0.8))
        with_fp = _proposal(backtest=_bt(coverage=90, fp=3, stability=0.8))
        assert compute_priority_score(no_fp) > compute_priority_score(with_fp)

    def test_score_in_range(self):
        p = _proposal(backtest=_bt(coverage=50, fp=5, stability=0.1))
        score = compute_priority_score(p)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Categorias de proposta
# ---------------------------------------------------------------------------

class TestClassifyProposal:
    def test_mean_recommended_validated_is_strong(self):
        p = _proposal(
            rule_type=RuleType.MEAN_DUAL_GUARD,
            backtest=_bt(coverage=95, fp=0),
        )
        p.recommendation_tier = RecommendationTier.RECOMMENDED
        assert classify_proposal(p) == ProposalCategory.STRONG

    def test_completeness_recommended_is_conservative(self):
        p = _proposal(
            rule_type=RuleType.COMPLETENESS,
            backtest=_bt(coverage=95, fp=0),
        )
        p.recommendation_tier = RecommendationTier.RECOMMENDED
        assert classify_proposal(p) == ProposalCategory.CONSERVATIVE

    def test_allowed_values_recommended_is_conservative(self):
        p = _proposal(
            rule_type=RuleType.ALLOWED_VALUES,
            backtest=_bt(coverage=100, fp=0),
        )
        p.recommendation_tier = RecommendationTier.RECOMMENDED
        assert classify_proposal(p) == ProposalCategory.CONSERVATIVE

    def test_dynamic_frequency_is_experimental(self):
        """CustomSql dynamic frequency = EXPERIMENTAL capability."""
        p = _proposal(
            rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            backtest=_bt(coverage=90, fp=0),
        )
        p.recommendation_tier = RecommendationTier.RECOMMENDED
        assert classify_proposal(p) == ProposalCategory.EXPERIMENTAL

    def test_hybrid_frequency_is_experimental(self):
        p = _proposal(
            rule_type=RuleType.CATEGORY_FREQUENCY_HYBRID,
            backtest=_bt(coverage=85, fp=1),
        )
        p.recommendation_tier = RecommendationTier.POSSIBLE
        assert classify_proposal(p) == ProposalCategory.EXPERIMENTAL

    def test_percentile_is_experimental(self):
        p = _proposal(
            rule_type=RuleType.NUMERIC_PERCENTILE_BAND,
            backtest=_bt(coverage=90, fp=0),
        )
        p.recommendation_tier = RecommendationTier.RECOMMENDED
        assert classify_proposal(p) == ProposalCategory.EXPERIMENTAL

    def test_possible_validated_is_needs_review(self):
        p = _proposal(
            rule_type=RuleType.MEAN_DUAL_GUARD,
            backtest=_bt(coverage=70, fp=2),
        )
        p.recommendation_tier = RecommendationTier.POSSIBLE
        assert classify_proposal(p) == ProposalCategory.NEEDS_REVIEW

    def test_not_recommended_always_not_recommended(self):
        p = _proposal(backtest=_bt(coverage=40))
        p.recommendation_tier = RecommendationTier.NOT_RECOMMENDED
        assert classify_proposal(p) == ProposalCategory.NOT_RECOMMENDED

    def test_not_recommended_even_if_experimental(self):
        """NOT_RECOMMENDED domina sobre EXPERIMENTAL capability."""
        p = _proposal(
            rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            backtest=_bt(coverage=30),
        )
        p.recommendation_tier = RecommendationTier.NOT_RECOMMENDED
        assert classify_proposal(p) == ProposalCategory.NOT_RECOMMENDED

    def test_rowcount_recommended_is_strong(self):
        p = _proposal(
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            backtest=_bt(coverage=95, fp=0),
        )
        p.recommendation_tier = RecommendationTier.RECOMMENDED
        assert classify_proposal(p) == ProposalCategory.STRONG

    def test_default_category_on_new_proposal(self):
        p = _proposal()
        assert p.proposal_category == ProposalCategory.STRONG


# ---------------------------------------------------------------------------
# Deteccao de redundancia
# ---------------------------------------------------------------------------

class TestDetectRedundancies:
    def test_allowed_values_plus_distinct_count(self):
        """DistinctCountExact rebaixado quando AllowedValues presente."""
        av = _proposal(
            rule_type=RuleType.ALLOWED_VALUES,
            backtest=_bt(coverage=100),
        )
        av.recommendation_tier = RecommendationTier.RECOMMENDED
        dc = _proposal(
            rule_type=RuleType.DISTINCT_COUNT_EXACT,
            backtest=_bt(coverage=100),
        )
        dc.recommendation_tier = RecommendationTier.RECOMMENDED

        detect_redundancies([av, dc])
        assert av.recommendation_tier == RecommendationTier.RECOMMENDED
        assert dc.recommendation_tier == RecommendationTier.NOT_RECOMMENDED
        assert any("Redundante" in r for r in dc.recommendation_reasons)
        assert any("AllowedValues" in r for r in dc.recommendation_reasons)

    def test_different_columns_not_redundant(self):
        """AllowedValues col_A + DistinctCount col_B = nao redundante."""
        av = _proposal(rule_type=RuleType.ALLOWED_VALUES, backtest=_bt())
        av.target_column = "COL_A"
        av.recommendation_tier = RecommendationTier.RECOMMENDED
        dc = _proposal(rule_type=RuleType.DISTINCT_COUNT_EXACT, backtest=_bt())
        dc.target_column = "COL_B"
        dc.recommendation_tier = RecommendationTier.RECOMMENDED

        detect_redundancies([av, dc])
        assert dc.recommendation_tier == RecommendationTier.RECOMMENDED

    def test_pk_plus_completeness(self):
        """Completeness 1.0 rebaixada quando IsPrimaryKey cobre a coluna."""
        pk = _proposal(
            rule_type=RuleType.IS_PRIMARY_KEY,
            backtest=_bt(coverage=100),
        )
        pk.target_column = None
        pk.suggested_values = ["COL_PK"]
        pk.recommendation_tier = RecommendationTier.RECOMMENDED

        comp = _proposal(
            rule_type=RuleType.COMPLETENESS,
            backtest=_bt(coverage=100),
            suggested_lower=1.0,
        )
        comp.target_column = "COL_PK"
        comp.recommendation_tier = RecommendationTier.RECOMMENDED

        detect_redundancies([pk, comp])
        assert comp.recommendation_tier == RecommendationTier.NOT_RECOMMENDED
        assert any("IsPrimaryKey" in r for r in comp.recommendation_reasons)

    def test_mean_plus_p50(self):
        """P50 rebaixado quando Mean presente na mesma coluna."""
        mean = _proposal(
            rule_type=RuleType.MEAN_DUAL_GUARD,
            backtest=_bt(coverage=95),
        )
        mean.recommendation_tier = RecommendationTier.RECOMMENDED

        p50 = _proposal(
            rule_type=RuleType.NUMERIC_PERCENTILE_BAND,
            backtest=_bt(coverage=90),
        )
        p50.metric_name = "p50"
        p50.suggested_values = ["0.50"]
        p50.recommendation_tier = RecommendationTier.RECOMMENDED

        detect_redundancies([mean, p50])
        assert mean.recommendation_tier == RecommendationTier.RECOMMENDED
        assert p50.recommendation_tier == RecommendationTier.NOT_RECOMMENDED

    def test_mean_plus_p10_p90_not_redundant(self):
        """P10 e P90 nao sao redundantes com Mean."""
        mean = _proposal(rule_type=RuleType.MEAN_DUAL_GUARD, backtest=_bt())
        mean.recommendation_tier = RecommendationTier.RECOMMENDED

        p10 = _proposal(rule_type=RuleType.NUMERIC_PERCENTILE_BAND, backtest=_bt())
        p10.metric_name = "p10"
        p10.suggested_values = ["0.10"]
        p10.recommendation_tier = RecommendationTier.RECOMMENDED

        p90 = _proposal(rule_type=RuleType.NUMERIC_PERCENTILE_BAND, backtest=_bt())
        p90.metric_name = "p90"
        p90.suggested_values = ["0.90"]
        p90.recommendation_tier = RecommendationTier.RECOMMENDED

        detect_redundancies([mean, p10, p90])
        assert p10.recommendation_tier == RecommendationTier.RECOMMENDED
        assert p90.recommendation_tier == RecommendationTier.RECOMMENDED

    def test_empty_list(self):
        assert detect_redundancies([]) == []

    def test_single_proposal_unchanged(self):
        p = _proposal(rule_type=RuleType.MEAN_DUAL_GUARD, backtest=_bt())
        p.recommendation_tier = RecommendationTier.RECOMMENDED
        detect_redundancies([p])
        assert p.recommendation_tier == RecommendationTier.RECOMMENDED


# ---------------------------------------------------------------------------
# Modo minimo (select_minimal_set)
# ---------------------------------------------------------------------------

class TestSelectMinimalSet:
    def _make(self, rule_type, tier=RecommendationTier.RECOMMENDED,
              category=ProposalCategory.STRONG, **kw):
        p = _proposal(rule_type=rule_type, backtest=_bt(), **kw)
        p.recommendation_tier = tier
        p.proposal_category = category
        return p

    def test_rowcount_included(self):
        p = self._make(RuleType.ROW_COUNT_DUAL_GUARD)
        assert p in select_minimal_set([p])

    def test_isprimarykey_included(self):
        p = self._make(RuleType.IS_PRIMARY_KEY, category=ProposalCategory.CONSERVATIVE)
        assert p in select_minimal_set([p])

    def test_mean_strong_included(self):
        p = self._make(RuleType.MEAN_DUAL_GUARD, category=ProposalCategory.STRONG)
        assert p in select_minimal_set([p])

    def test_completeness_conservative_included(self):
        p = self._make(RuleType.COMPLETENESS, category=ProposalCategory.CONSERVATIVE)
        assert p in select_minimal_set([p])

    def test_allowed_values_conservative_included(self):
        p = self._make(RuleType.ALLOWED_VALUES, category=ProposalCategory.CONSERVATIVE)
        assert p in select_minimal_set([p])

    def test_stddev_excluded(self):
        """StdDev excluido do minimo (nao esta em _MINIMAL_RULE_TYPES)."""
        p = self._make(RuleType.STDDEV_DUAL_GUARD)
        assert p not in select_minimal_set([p])

    def test_frequency_excluded(self):
        p = self._make(RuleType.CATEGORY_FREQUENCY_STATIC)
        assert p not in select_minimal_set([p])

    def test_percentile_excluded(self):
        p = self._make(RuleType.NUMERIC_PERCENTILE_BAND)
        assert p not in select_minimal_set([p])

    def test_distinct_count_excluded(self):
        p = self._make(RuleType.DISTINCT_COUNT_EXACT)
        assert p not in select_minimal_set([p])

    def test_not_recommended_excluded(self):
        p = self._make(
            RuleType.MEAN_DUAL_GUARD,
            tier=RecommendationTier.NOT_RECOMMENDED,
            category=ProposalCategory.NOT_RECOMMENDED,
        )
        assert p not in select_minimal_set([p])

    def test_possible_excluded(self):
        p = self._make(
            RuleType.MEAN_DUAL_GUARD,
            tier=RecommendationTier.POSSIBLE,
            category=ProposalCategory.NEEDS_REVIEW,
        )
        assert p not in select_minimal_set([p])

    def test_experimental_excluded(self):
        p = self._make(
            RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            category=ProposalCategory.EXPERIMENTAL,
        )
        assert p not in select_minimal_set([p])

    def test_empty_input(self):
        assert select_minimal_set([]) == []

    def test_mixed_keeps_only_eligible(self):
        """De um conjunto misto, so as elegiveis passam."""
        mean = self._make(RuleType.MEAN_DUAL_GUARD, category=ProposalCategory.STRONG)
        stddev = self._make(RuleType.STDDEV_DUAL_GUARD, category=ProposalCategory.STRONG)
        comp = self._make(RuleType.COMPLETENESS, category=ProposalCategory.CONSERVATIVE)
        freq = self._make(RuleType.CATEGORY_FREQUENCY_STATIC, category=ProposalCategory.CONSERVATIVE)
        not_rec = self._make(
            RuleType.COMPLETENESS,
            tier=RecommendationTier.NOT_RECOMMENDED,
            category=ProposalCategory.NOT_RECOMMENDED,
        )

        result = select_minimal_set([mean, stddev, comp, freq, not_rec])
        assert mean in result
        assert comp in result
        assert stddev not in result
        assert freq not in result
        assert not_rec not in result
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Explicacao de exclusoes de colunas
# ---------------------------------------------------------------------------

def _col_profile(name: str, stype: SemanticType, null_ratio: float = 0.0) -> ColumnProfile:
    return ColumnProfile(
        column_name=name,
        athena_type="varchar",
        inferred_semantic_type=stype,
        null_ratio=null_ratio,
    )


class TestExplainColumnExclusions:
    def test_datetime_excluded(self):
        p = _col_profile("DT_REF", SemanticType.DATETIME)
        result = explain_column_exclusions([p])
        assert len(result) == 1
        assert result[0].column_name == "DT_REF"
        assert "temporal" in result[0].reason

    def test_identifier_excluded(self):
        p = _col_profile("NUM_CPF", SemanticType.IDENTIFIER)
        result = explain_column_exclusions([p])
        assert len(result) == 1
        assert "identificadora" in result[0].reason

    def test_unknown_excluded(self):
        p = _col_profile("COL_VAZIA", SemanticType.UNKNOWN)
        result = explain_column_exclusions([p])
        assert len(result) == 1
        assert "nula" in result[0].reason.lower()

    def test_cat_high_excluded(self):
        p = _col_profile("NOME_CLIENTE", SemanticType.CATEGORICAL_HIGH_CARDINALITY)
        result = explain_column_exclusions([p])
        assert len(result) == 1
        assert "cardinalidade" in result[0].reason.lower()

    def test_numeric_not_excluded(self):
        p = _col_profile("VLR_SALDO", SemanticType.NUMERIC)
        result = explain_column_exclusions([p])
        assert len(result) == 0

    def test_cat_low_not_excluded(self):
        p = _col_profile("COD_SITU", SemanticType.CATEGORICAL_LOW_CARDINALITY)
        result = explain_column_exclusions([p])
        assert len(result) == 0

    def test_cat_mid_not_excluded(self):
        p = _col_profile("CIDADE", SemanticType.CATEGORICAL_MID_CARDINALITY)
        result = explain_column_exclusions([p])
        assert len(result) == 0

    def test_high_null_ratio(self):
        p = _col_profile("VLR_PARCIAL", SemanticType.NUMERIC, null_ratio=0.35)
        result = explain_column_exclusions([p])
        assert len(result) == 1
        assert "Nulidade" in result[0].reason

    def test_low_null_ratio_no_exclusion(self):
        p = _col_profile("VLR_OK", SemanticType.NUMERIC, null_ratio=0.05)
        result = explain_column_exclusions([p])
        assert len(result) == 0

    def test_mixed_profiles(self):
        profiles = [
            _col_profile("VLR_SALDO", SemanticType.NUMERIC),
            _col_profile("DT_REF", SemanticType.DATETIME),
            _col_profile("NUM_CPF", SemanticType.IDENTIFIER),
            _col_profile("COD_SITU", SemanticType.CATEGORICAL_LOW_CARDINALITY),
        ]
        result = explain_column_exclusions(profiles)
        names = {e.column_name for e in result}
        assert "DT_REF" in names
        assert "NUM_CPF" in names
        assert "VLR_SALDO" not in names
        assert "COD_SITU" not in names
        assert len(result) == 2

    def test_empty_input(self):
        assert explain_column_exclusions([]) == []

    def test_exclusion_is_frozen(self):
        p = _col_profile("DT_REF", SemanticType.DATETIME)
        result = explain_column_exclusions([p])
        with pytest.raises(AttributeError):
            result[0].reason = "changed"
