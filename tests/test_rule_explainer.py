"""Testes para core/rule_explainer.py."""

import pytest

from core.models.enums import (
    BaselineMethod,
    ConfidenceLevel,
    RuleType,
    SeriesRegime,
)
from core.models.rule_evaluation import RuleEvaluation
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.series_profile import SeriesProfile
from core.rule_explainer import (
    explain_rule,
    explain_rule_detail,
    explain_regime_context,
    explain_trade_offs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_proposal(
    rule_type: RuleType,
    column: str | None = "VLR_SALDO",
    table: str = "tb_operacoes",
    n: int = 30,
    k: float = 2.0,
    margin: float = 0.10,
    threshold: float | None = None,
    values: list[str] | None = None,
    backtest: BacktestSummary | None = None,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
) -> RuleProposal:
    return RuleProposal(
        id="test-id",
        target_column=column,
        target_table=table,
        rule_type=rule_type,
        metric_name=rule_type.value,
        baseline_method=BaselineMethod.LAST_N_PERIODS,
        baseline_window=n,
        baseline_n_sigma=k,
        baseline_margin_pct=margin,
        suggested_lower=threshold,
        suggested_values=values,
        backtest=backtest,
        confidence=confidence,
    )


def _make_backtest(**kwargs) -> BacktestSummary:
    defaults = dict(
        total_periods=30,
        periods_pass=29,
        periods_fail=1,
        coverage_pct=96.7,
        false_positive_proxy=1,
        band_width_ratio=0.15,
        stability_score=0.85,
        has_drift=False,
        outlier_periods=[],
    )
    defaults.update(kwargs)
    return BacktestSummary(**defaults)


# ---------------------------------------------------------------------------
# Tests: explain_rule
# ---------------------------------------------------------------------------

class TestExplainRule:
    def test_mean_dual_guard(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD, column="VLR_SALDO", n=20, k=2.0, margin=0.10)
        text = explain_rule(p)
        assert "media" in text
        assert "VLR_SALDO" in text
        assert "20 periodos" in text
        assert "2 desvios padrao" in text
        assert "10%" in text

    def test_stddev_dual_guard(self):
        p = _make_proposal(RuleType.STDDEV_DUAL_GUARD, column="VLR_PARC")
        text = explain_rule(p)
        assert "desvio padrao" in text
        assert "VLR_PARC" in text
        assert "dispersao" in text

    def test_rowcount_dual_guard(self):
        p = _make_proposal(RuleType.ROW_COUNT_DUAL_GUARD, column=None, table="tb_ops")
        text = explain_rule(p)
        assert "volume de linhas" in text
        assert "tb_ops" in text
        assert "volume anomalo" in text

    def test_completeness(self):
        p = _make_proposal(RuleType.COMPLETENESS, threshold=0.98)
        text = explain_rule(p)
        assert "98%" in text
        assert "preenchidos" in text

    def test_completeness_100(self):
        p = _make_proposal(RuleType.COMPLETENESS, threshold=1.0)
        text = explain_rule(p)
        assert "100%" in text

    def test_allowed_values_few(self):
        p = _make_proposal(RuleType.ALLOWED_VALUES, values=["A", "B", "C"])
        text = explain_rule(p)
        assert "`A`" in text
        assert "`B`" in text
        assert "`C`" in text

    def test_allowed_values_many(self):
        vals = [str(i) for i in range(20)]
        p = _make_proposal(RuleType.ALLOWED_VALUES, values=vals)
        text = explain_rule(p)
        assert "20 valores" in text

    def test_distinct_count(self):
        p = _make_proposal(RuleType.DISTINCT_COUNT_EXACT, threshold=5.0)
        text = explain_rule(p)
        assert "5 valores distintos" in text

    def test_primary_key(self):
        p = _make_proposal(RuleType.IS_PRIMARY_KEY, values=["COL_A", "COL_B"])
        text = explain_rule(p)
        assert "chave primaria" in text
        assert "`COL_A`" in text
        assert "`COL_B`" in text

    def test_category_frequency(self):
        p = _make_proposal(RuleType.CATEGORY_FREQUENCY_STATIC)
        text = explain_rule(p)
        assert "frequencia relativa" in text

    def test_unknown_type_fallback(self):
        p = _make_proposal(RuleType.CUSTOM_SQL)
        text = explain_rule(p)
        assert "Regra customizada" in text

    def test_sigma_fractional_k(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD, k=1.5)
        text = explain_rule(p)
        assert "1.5 desvios padrao" in text

    def test_margin_20pct(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD, margin=0.20)
        text = explain_rule(p)
        assert "20%" in text

    def test_mean_margin_disabled_no_margin_text(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        p.margin_enabled = False
        text = explain_rule(p)
        assert "**ou**" not in text
        assert "% da media" not in text
        assert "duas bandas" not in text

    def test_stddev_margin_disabled_no_margin_text(self):
        p = _make_proposal(RuleType.STDDEV_DUAL_GUARD)
        p.margin_enabled = False
        text = explain_rule(p)
        assert "**ou**" not in text
        assert "% da media" not in text
        assert "duas bandas" not in text

    def test_rowcount_margin_disabled_no_margin_text(self):
        p = _make_proposal(RuleType.ROW_COUNT_DUAL_GUARD, column=None, table="tb_ops")
        p.margin_enabled = False
        text = explain_rule(p)
        assert "**ou**" not in text
        assert "% do volume" not in text
        assert "duas bandas" not in text


# ---------------------------------------------------------------------------
# Tests: explain_rule_detail
# ---------------------------------------------------------------------------

class TestExplainRuleDetail:
    def test_includes_params(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD, n=25, k=3.0, margin=0.15)
        text = explain_rule_detail(p)
        assert "Parametros" in text
        assert "25 periodos" in text
        assert "3 desvios padrao" in text
        assert "15%" in text

    def test_includes_backtest_evidence(self):
        bt = _make_backtest(coverage_pct=97.5, false_positive_proxy=0, stability_score=0.92)
        p = _make_proposal(
            RuleType.MEAN_DUAL_GUARD,
            backtest=bt,
            confidence=ConfidenceLevel.HIGH,
        )
        text = explain_rule_detail(p)
        assert "Evidencia" in text
        assert "97.5%" in text
        assert "0 periodo" in text
        assert "0.92" in text
        assert "recomendada para producao" in text

    def test_backtest_with_drift(self):
        bt = _make_backtest(has_drift=True)
        p = _make_proposal(RuleType.STDDEV_DUAL_GUARD, backtest=bt)
        text = explain_rule_detail(p)
        assert "drift" in text

    def test_backtest_with_outliers(self):
        bt = _make_backtest(outlier_periods=["2026-01-01", "2026-01-15"])
        p = _make_proposal(RuleType.ROW_COUNT_DUAL_GUARD, column=None, backtest=bt)
        text = explain_rule_detail(p)
        assert "2 periodo" in text
        assert "atipicos" in text

    def test_completeness_params(self):
        p = _make_proposal(RuleType.COMPLETENESS, threshold=0.95)
        text = explain_rule_detail(p)
        assert "Parametros" in text
        assert "95%" in text

    def test_no_backtest_no_evidence(self):
        p = _make_proposal(RuleType.COMPLETENESS, threshold=1.0)
        text = explain_rule_detail(p)
        assert "Evidencia" not in text

    def test_low_confidence_label(self):
        bt = _make_backtest(coverage_pct=60.0)
        p = _make_proposal(
            RuleType.MEAN_DUAL_GUARD,
            backtest=bt,
            confidence=ConfidenceLevel.LOW,
        )
        text = explain_rule_detail(p)
        assert "nao recomendada" in text

    def test_medium_confidence_label(self):
        bt = _make_backtest()
        p = _make_proposal(
            RuleType.STDDEV_DUAL_GUARD,
            backtest=bt,
            confidence=ConfidenceLevel.MEDIUM,
        )
        text = explain_rule_detail(p)
        assert "revisar parametros" in text


# ===========================================================================
# explain_regime_context
# ===========================================================================

class TestExplainRegimeContext:

    def test_stable_returns_empty(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        profile = SeriesProfile(regime=SeriesRegime.STABLE)
        assert explain_regime_context(p, profile) == ""

    def test_structural_break_mentions_date(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        profile = SeriesProfile(
            regime=SeriesRegime.STRUCTURAL_BREAK,
            has_structural_break=True,
            change_point_date="2026-02-15",
        )
        text = explain_regime_context(p, profile)
        assert "2026-02-15" in text
        assert "mudanca" in text.lower()

    def test_trending_recommends_small_n(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        profile = SeriesProfile(
            regime=SeriesRegime.TRENDING,
            has_trend=True, drift_slope=0.05,
        )
        text = explain_regime_context(p, profile)
        assert "tendencia" in text.lower()
        assert "N menor" in text

    def test_seasonal_recommends_multiple_7(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        profile = SeriesProfile(
            regime=SeriesRegime.SEASONAL,
            is_seasonal=True, seasonality_strength=0.25,
        )
        text = explain_regime_context(p, profile)
        assert "sazonalidade" in text.lower()
        assert "7" in text

    def test_volatile_warns_about_fp(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        profile = SeriesProfile(
            regime=SeriesRegime.VOLATILE,
            is_volatile=True, cv=0.55,
        )
        text = explain_regime_context(p, profile)
        assert "volatil" in text.lower()

    def test_zero_inflated_suggests_completeness(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        profile = SeriesProfile(
            regime=SeriesRegime.ZERO_INFLATED,
            is_zero_inflated=True, zero_pct=45.0,
        )
        text = explain_regime_context(p, profile)
        assert "zeros" in text.lower()
        assert "completeness" in text.lower()

    def test_asymmetric_mentions_skewness(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        profile = SeriesProfile(
            regime=SeriesRegime.ASYMMETRIC,
            is_asymmetric=True, skewness=2.5,
        )
        text = explain_regime_context(p, profile)
        assert "assimetrica" in text.lower()

    def test_sparse_warns_caution(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        profile = SeriesProfile(
            regime=SeriesRegime.SPARSE,
            is_sparse=True, null_pct=60.0,
        )
        text = explain_regime_context(p, profile)
        assert "nulos" in text.lower()

    def test_secondary_regimes_listed(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        profile = SeriesProfile(
            regime=SeriesRegime.TRENDING,
            secondary_regimes=(SeriesRegime.VOLATILE,),
            has_trend=True, is_volatile=True,
        )
        text = explain_regime_context(p, profile)
        assert "volatile" in text.lower()

    def test_completeness_rule_no_crash(self):
        """Non-numeric rules should still get context."""
        p = _make_proposal(RuleType.COMPLETENESS)
        profile = SeriesProfile(
            regime=SeriesRegime.SPARSE,
            is_sparse=True, null_pct=50.0,
        )
        text = explain_regime_context(p, profile)
        assert len(text) > 0


# ===========================================================================
# explain_trade_offs
# ===========================================================================

class TestExplainTradeOffs:

    def test_good_evaluation_minimal_text(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        ev = RuleEvaluation(
            coverage=0.95, stability=0.9,
            interpretability=1.0, cost_efficiency=1.0,
            regime_fit=1.0, fp_risk=0.05, robustness=0.95,
            sensitivity=0.15,
        )
        text = explain_trade_offs(p, ev)
        # Good eval should produce minimal or empty text
        assert "alto" not in text.lower() or len(text) < 200

    def test_low_regime_fit_flagged(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        ev = RuleEvaluation(
            coverage=0.90, stability=0.8,
            interpretability=1.0, cost_efficiency=1.0,
            regime_fit=0.3, fp_risk=0.1, robustness=0.9,
        )
        text = explain_trade_offs(p, ev)
        assert "adequacao" in text.lower()
        assert "baixa" in text.lower()

    def test_high_fp_risk_flagged(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        ev = RuleEvaluation(
            coverage=0.90, stability=0.8,
            interpretability=1.0, cost_efficiency=1.0,
            regime_fit=0.9, fp_risk=0.40, robustness=0.9,
        )
        text = explain_trade_offs(p, ev)
        assert "falsos positivos" in text.lower()

    def test_low_robustness_flagged(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        ev = RuleEvaluation(
            coverage=0.70, stability=0.5,
            interpretability=1.0, cost_efficiency=1.0,
            regime_fit=0.8, fp_risk=0.1, robustness=0.4,
        )
        text = explain_trade_offs(p, ev)
        assert "confiabilidade" in text.lower()

    def test_wide_band_trade_off(self):
        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        ev = RuleEvaluation(
            coverage=0.98, stability=0.9,
            interpretability=1.0, cost_efficiency=1.0,
            regime_fit=0.9, fp_risk=0.1, robustness=0.9,
            sensitivity=0.60,  # wide band
        )
        text = explain_trade_offs(p, ev)
        assert "banda" in text.lower() or "larga" in text.lower()
