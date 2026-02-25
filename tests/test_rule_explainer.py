"""Testes para core/rule_explainer.py."""

import pytest

from core.models.enums import (
    BaselineMethod,
    ConfidenceLevel,
    RuleType,
)
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.rule_explainer import explain_rule, explain_rule_detail


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
