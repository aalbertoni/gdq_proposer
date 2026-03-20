"""Testes end-to-end para series curtas (mensais).

Valida que o pipeline (backtest → scoring → recommendation) funciona
corretamente com a GrainPolicy mensal para series de 4-8 periodos.
Tambem garante nao-regressao para series diarias.
"""

import pytest

from core.backtest import backtest_band
from core.models.enums import (
    ConfidenceLevel,
    GrainType,
    RecommendationTier,
    RuleType,
    SeriesRegime,
)
from core.models.grain_policy import get_grain_policy
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.rule_recommender import recommend_tier
from core.rule_scoring import score_proposal
from core.series_regime import classify_series
from core.statistical_engine import compute_dynamic_band


# ---------------------------------------------------------------------------
# Fixtures: series sinteticas
# ---------------------------------------------------------------------------

def _stable_series(n: int, base: float = 100.0, noise: float = 2.0) -> tuple[list[float], list[str]]:
    """Serie estavel com baixa variancia."""
    import random
    random.seed(42)
    values = [base + random.uniform(-noise, noise) for _ in range(n)]
    dates = [f"2024-{i+1:02d}-01" for i in range(n)]
    return values, dates


def _volatile_series(n: int) -> tuple[list[float], list[str]]:
    """Serie volatil (CV > 30%)."""
    import random
    random.seed(42)
    values = [100 + random.uniform(-50, 50) for _ in range(n)]
    dates = [f"2024-{i+1:02d}-01" for i in range(n)]
    return values, dates


def _make_proposal(
    bt: BacktestSummary,
    rule_type: RuleType = RuleType.MEAN_DUAL_GUARD,
) -> RuleProposal:
    return RuleProposal(
        id="test",
        target_column="VLR_SALDO",
        target_table="test_table",
        rule_type=rule_type,
        metric_name="mean",
        backtest=bt,
    )


# ---------------------------------------------------------------------------
# Backtest com min_history adaptativo
# ---------------------------------------------------------------------------

class TestBacktestShortSeries:
    def test_6_periods_min_history_3(self):
        """6 periodos com min_history=3 → 3 pontos avaliados."""
        values, dates = _stable_series(6)
        bt = backtest_band(values, dates, n_periods=3, n_sigma=2.0,
                           margin_pct=0.10, min_history=3)
        assert bt.total_periods == 3
        assert bt.coverage_pct > 0

    def test_5_periods_min_history_3(self):
        """5 periodos com min_history=3 → 2 pontos avaliados."""
        values, dates = _stable_series(5)
        bt = backtest_band(values, dates, n_periods=3, n_sigma=2.0,
                           margin_pct=0.10, min_history=3)
        assert bt.total_periods == 2

    def test_4_periods_min_history_3(self):
        """4 periodos com min_history=3 → 1 ponto avaliado."""
        values, dates = _stable_series(4)
        bt = backtest_band(values, dates, n_periods=3, n_sigma=2.0,
                           margin_pct=0.10, min_history=3)
        assert bt.total_periods == 1

    def test_3_periods_min_history_3(self):
        """3 periodos com min_history=3 → 0 pontos (precisa de min+1)."""
        values, dates = _stable_series(3)
        bt = backtest_band(values, dates, n_periods=3, n_sigma=2.0,
                           margin_pct=0.10, min_history=3)
        assert bt.total_periods == 0

    def test_8_periods_min_history_7_daily_default(self):
        """8 periodos com min_history=7 (daily default) → 1 ponto."""
        values, dates = _stable_series(8)
        bt = backtest_band(values, dates, n_periods=7, n_sigma=2.0,
                           margin_pct=0.10, min_history=7)
        assert bt.total_periods == 1


# ---------------------------------------------------------------------------
# Recommendation tier com monthly policy
# ---------------------------------------------------------------------------

class TestRecommendTierMonthly:
    def _bt(self, total: int, coverage: float = 95.0) -> BacktestSummary:
        return BacktestSummary(
            total_periods=total,
            periods_pass=int(total * coverage / 100),
            periods_fail=total - int(total * coverage / 100),
            coverage_pct=coverage,
            false_positive_proxy=0,
            band_width_ratio=0.1,
            stability_score=0.5,
            has_drift=False,
        )

    def test_3_evaluated_is_recommended_with_monthly_policy(self):
        """3 avaliados com policy mensal (min_dynamic=3) → pode ser RECOMMENDED."""
        policy = get_grain_policy(GrainType.MONTHLY)
        p = _make_proposal(self._bt(total=3, coverage=100.0))
        tier, _ = recommend_tier(
            p,
            min_periods_dynamic=policy.min_valid_periods_dynamic,
            min_periods_possible=policy.min_valid_periods_possible,
        )
        # Com 100% coverage e 3 periodos >= min_dynamic=3, pode ser RECOMMENDED
        assert tier in (RecommendationTier.RECOMMENDED, RecommendationTier.POSSIBLE)

    def test_2_evaluated_is_possible_with_monthly_policy(self):
        """2 avaliados com policy mensal (min_possible=2) → POSSIBLE."""
        policy = get_grain_policy(GrainType.MONTHLY)
        p = _make_proposal(self._bt(total=2, coverage=100.0))
        tier, reasons = recommend_tier(
            p,
            min_periods_dynamic=policy.min_valid_periods_dynamic,
            min_periods_possible=policy.min_valid_periods_possible,
        )
        assert tier == RecommendationTier.POSSIBLE
        assert any("limitado" in r.lower() for r in reasons)

    def test_1_evaluated_is_not_recommended_with_monthly_policy(self):
        """1 avaliado com policy mensal (min_possible=2) → NOT_RECOMMENDED."""
        policy = get_grain_policy(GrainType.MONTHLY)
        p = _make_proposal(self._bt(total=1, coverage=100.0))
        tier, _ = recommend_tier(
            p,
            min_periods_dynamic=policy.min_valid_periods_dynamic,
            min_periods_possible=policy.min_valid_periods_possible,
        )
        assert tier == RecommendationTier.NOT_RECOMMENDED

    def test_5_evaluated_is_recommended_with_monthly_policy(self):
        """5 avaliados com policy mensal → RECOMMENDED se metricas boas."""
        policy = get_grain_policy(GrainType.MONTHLY)
        p = _make_proposal(self._bt(total=5, coverage=95.0))
        tier, _ = recommend_tier(
            p,
            min_periods_dynamic=policy.min_valid_periods_dynamic,
            min_periods_possible=policy.min_valid_periods_possible,
        )
        assert tier == RecommendationTier.RECOMMENDED


# ---------------------------------------------------------------------------
# Scoring com robustness tiers mensais
# ---------------------------------------------------------------------------

class TestScoringMonthly:
    def test_6_valid_monthly_no_heavy_penalty(self):
        """6 periodos validos com tiers mensais → sem penalty -0.30."""
        policy = get_grain_policy(GrainType.MONTHLY)
        bt = BacktestSummary(
            total_periods=3, periods_pass=3, periods_fail=0,
            coverage_pct=100.0, false_positive_proxy=0,
            band_width_ratio=0.1, stability_score=0.5, has_drift=False,
        )
        p = _make_proposal(bt)
        p.history_values = [100.0] * 6
        result = score_proposal(p, robustness_tiers=policy.robustness_tiers)
        # Score nao deve ter penalty -0.30 (6 >= 5 no tier mensal)
        assert result.score_total > 0.50

    def test_6_valid_daily_penalized_more_than_monthly(self):
        """6 periodos validos: daily penaliza mais que monthly."""
        daily_policy = get_grain_policy(GrainType.DAILY)
        monthly_policy = get_grain_policy(GrainType.MONTHLY)
        bt = BacktestSummary(
            total_periods=3, periods_pass=3, periods_fail=0,
            coverage_pct=100.0, false_positive_proxy=0,
            band_width_ratio=0.1, stability_score=0.5, has_drift=False,
        )
        p_daily = _make_proposal(bt)
        p_daily.history_values = [100.0] * 6
        p_monthly = _make_proposal(bt)
        p_monthly.history_values = [100.0] * 6
        daily_score = score_proposal(p_daily, robustness_tiers=daily_policy.robustness_tiers)
        monthly_score = score_proposal(p_monthly, robustness_tiers=monthly_policy.robustness_tiers)
        # Daily penalty -0.30 (6 < 7), monthly penalty -0.05 (5 <= 6 < 8)
        assert monthly_score.score_total > daily_score.score_total


# ---------------------------------------------------------------------------
# Seasonality disabled for monthly
# ---------------------------------------------------------------------------

class TestSeasonalityMonthly:
    def test_classify_series_no_seasonality_monthly(self):
        """classify_series com seasonality_enabled=False nao detecta sazonalidade."""
        # Serie com 14+ pontos que teria sazonalidade semanal em daily
        values, dates = _stable_series(20)
        profile = classify_series(values, dates, seasonality_enabled=False)
        assert not profile.is_seasonal

    def test_classify_series_with_seasonality_daily(self):
        """classify_series com seasonality_enabled=True (default) funciona normal."""
        values, dates = _stable_series(20)
        # Pode ou nao detectar, o importante e que nao levanta erro
        profile = classify_series(values, dates, seasonality_enabled=True)
        assert profile is not None


# ---------------------------------------------------------------------------
# Statistical engine com series curtas
# ---------------------------------------------------------------------------

class TestStatisticalEngineShortSeries:
    def test_compute_band_3_values(self):
        """compute_dynamic_band com 3 valores funciona."""
        band = compute_dynamic_band([100.0, 102.0, 98.0], n_periods=3, n_sigma=2.0)
        assert "center" in band
        assert band["lower"] < band["center"] < band["upper"]

    def test_compute_band_2_values_raises(self):
        """compute_dynamic_band com 2 valores levanta ValueError."""
        with pytest.raises(ValueError):
            compute_dynamic_band([100.0, 102.0], n_periods=2, n_sigma=2.0)


# ---------------------------------------------------------------------------
# Non-regression: daily unchanged
# ---------------------------------------------------------------------------

class TestDailyNonRegression:
    def test_recommend_tier_daily_10_periods_recommended(self):
        """Daily: 10 periodos com boas metricas → RECOMMENDED (como antes)."""
        bt = BacktestSummary(
            total_periods=10, periods_pass=10, periods_fail=0,
            coverage_pct=100.0, false_positive_proxy=0,
            band_width_ratio=0.1, stability_score=0.9, has_drift=False,
        )
        p = _make_proposal(bt)
        tier, _ = recommend_tier(p)  # defaults = daily
        assert tier == RecommendationTier.RECOMMENDED

    def test_recommend_tier_daily_7_periods_possible(self):
        """Daily: 7 periodos → POSSIBLE (entre min_possible=5 e min_dynamic=10)."""
        bt = BacktestSummary(
            total_periods=7, periods_pass=7, periods_fail=0,
            coverage_pct=100.0, false_positive_proxy=0,
            band_width_ratio=0.1, stability_score=0.9, has_drift=False,
        )
        p = _make_proposal(bt)
        tier, _ = recommend_tier(p)
        assert tier == RecommendationTier.POSSIBLE

    def test_recommend_tier_daily_3_periods_not_recommended(self):
        """Daily: 3 periodos → NOT_RECOMMENDED (< min_possible=5)."""
        bt = BacktestSummary(
            total_periods=3, periods_pass=3, periods_fail=0,
            coverage_pct=100.0, false_positive_proxy=0,
            band_width_ratio=0.1, stability_score=0.9, has_drift=False,
        )
        p = _make_proposal(bt)
        tier, _ = recommend_tier(p)
        assert tier == RecommendationTier.NOT_RECOMMENDED
