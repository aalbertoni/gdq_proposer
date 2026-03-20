"""Testes unitarios para core/rule_recommender.py."""

import pytest

from core.models.enums import (
    ConfidenceLevel,
    RecommendationTier,
    RuleType,
    SeriesRegime,
)
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.series_profile import SeriesProfile
from core.rule_recommender import compute_priority_score, prioritize_proposals, recommend_tier


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
        p = _proposal(backtest=_bt(coverage=90, total_periods=7))
        tier, reasons = recommend_tier(p)
        assert tier == RecommendationTier.NOT_RECOMMENDED
        assert any("Historico insuficiente" in r for r in reasons)

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
