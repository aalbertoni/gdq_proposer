"""Testes de contrato: validam shape, tipos e campos obrigatorios dos outputs.

Protegem contra regressao silenciosa — se um modulo muda o formato de saida,
estes testes quebram imediatamente.
"""

import pytest

from core.models.enums import (
    BaselineMethod,
    ConfidenceLevel,
    RuleType,
    SeriesRegime,
)
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.baseline import BaselineStrategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _stable_values(n: int = 45) -> list[float]:
    """Serie estavel centrada em 100."""
    import random
    random.seed(42)
    return [100 + random.gauss(0, 2) for _ in range(n)]


def _stable_dates(n: int = 45) -> list[str]:
    return [f"2026-01-{i+1:02d}" for i in range(n)]


def _make_numeric_proposal(**overrides) -> RuleProposal:
    defaults = dict(
        id="contract-001",
        target_column="VLR_SALDO",
        target_table="tb_test",
        rule_type=RuleType.MEAN_DUAL_GUARD,
        metric_name="mean",
        baseline_window=30,
        baseline_n_sigma=2.0,
        baseline_margin_pct=0.10,
    )
    defaults.update(overrides)
    return RuleProposal(**defaults)


# ---------------------------------------------------------------------------
# compute_dynamic_band — dict shape
# ---------------------------------------------------------------------------

class TestComputeDynamicBandContract:
    """compute_dynamic_band retorna dict com keys fixas e tipos corretos."""

    REQUIRED_KEYS = {"lower", "upper", "center", "std", "n_sigma", "n_periods_used"}

    def test_has_all_required_keys(self):
        from core.statistical_engine import compute_dynamic_band
        result = compute_dynamic_band(_stable_values(), n_periods=30)
        assert self.REQUIRED_KEYS.issubset(result.keys())

    def test_values_are_numeric(self):
        from core.statistical_engine import compute_dynamic_band
        result = compute_dynamic_band(_stable_values(), n_periods=30)
        for key in self.REQUIRED_KEYS:
            assert isinstance(result[key], (int, float)), f"{key} nao e numerico"

    def test_lower_leq_upper(self):
        from core.statistical_engine import compute_dynamic_band
        result = compute_dynamic_band(_stable_values(), n_periods=30)
        assert result["lower"] <= result["upper"]


# ---------------------------------------------------------------------------
# compute_frequency_band — dict shape
# ---------------------------------------------------------------------------

class TestComputeFrequencyBandContract:
    REQUIRED_KEYS = {"lower", "upper", "center", "std", "n_sigma", "margin_pct", "n_periods_used"}

    def test_has_all_required_keys(self):
        from core.statistical_engine import compute_frequency_band
        pct = [30.0 + i * 0.1 for i in range(20)]
        result = compute_frequency_band(pct, n_periods=15)
        assert self.REQUIRED_KEYS.issubset(result.keys())


# ---------------------------------------------------------------------------
# backtest_band — BacktestSummary shape
# ---------------------------------------------------------------------------

class TestBacktestBandContract:
    """backtest_band retorna BacktestSummary com todos os campos."""

    def test_returns_backtest_summary(self):
        from core.backtest import backtest_band
        vals = _stable_values()
        dates = _stable_dates()
        result = backtest_band(vals, dates, n_periods=30)
        assert isinstance(result, BacktestSummary)

    def test_has_required_fields(self):
        from core.backtest import backtest_band
        result = backtest_band(_stable_values(), _stable_dates(), n_periods=30)
        assert isinstance(result.total_periods, int)
        assert isinstance(result.periods_pass, int)
        assert isinstance(result.periods_fail, int)
        assert isinstance(result.coverage_pct, float)
        assert isinstance(result.false_positive_proxy, int)
        assert isinstance(result.band_width_ratio, float)
        assert isinstance(result.stability_score, float)
        assert isinstance(result.has_drift, bool)
        assert isinstance(result.outlier_periods, list)
        assert isinstance(result.point_results, list)

    def test_coverage_in_range(self):
        from core.backtest import backtest_band
        result = backtest_band(_stable_values(), _stable_dates(), n_periods=30)
        assert 0.0 <= result.coverage_pct <= 100.0

    def test_periods_sum(self):
        from core.backtest import backtest_band
        result = backtest_band(_stable_values(), _stable_dates(), n_periods=30)
        assert result.periods_pass + result.periods_fail == result.total_periods

    def test_point_results_shape(self):
        from core.backtest import backtest_band
        result = backtest_band(_stable_values(), _stable_dates(), n_periods=30)
        if result.point_results:
            pt = result.point_results[0]
            assert "index" in pt
            assert "value" in pt
            assert "passed" in pt


# ---------------------------------------------------------------------------
# backtest_allowed_values — BacktestSummary shape
# ---------------------------------------------------------------------------

class TestBacktestAllowedValuesContract:
    def test_returns_backtest_summary(self):
        from core.backtest import backtest_allowed_values
        period_map = {
            "2026-01-01": {"A", "B"},
            "2026-01-02": {"A", "B", "C"},
            "2026-01-03": {"A"},
        }
        result = backtest_allowed_values(period_map, {"A", "B", "C"})
        assert isinstance(result, BacktestSummary)
        assert result.total_periods == 3


# ---------------------------------------------------------------------------
# GDQRuleGenerator.generate — string output
# ---------------------------------------------------------------------------

class TestGeneratorContract:
    """generate() retorna string nao-vazia que comeca com nome de regra valido."""

    VALID_PREFIXES = (
        "Mean", "StandardDeviation", "RowCount", "Completeness",
        "ColumnValues", "DistinctValuesCount", "IsPrimaryKey",
        "CustomSql", "((",  # dual guard abre com ((
    )

    def test_mean_returns_string(self):
        from core.gdq_rule_generator import GDQRuleGenerator
        gen = GDQRuleGenerator()
        p = _make_numeric_proposal()
        result = gen.generate(p)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_mean_starts_with_valid_prefix(self):
        from core.gdq_rule_generator import GDQRuleGenerator
        gen = GDQRuleGenerator()
        p = _make_numeric_proposal()
        result = gen.generate(p)
        assert result.startswith(self.VALID_PREFIXES), f"Prefixo inesperado: {result[:30]}"

    def test_completeness_starts_with_completeness(self):
        from core.gdq_rule_generator import GDQRuleGenerator
        gen = GDQRuleGenerator()
        p = _make_numeric_proposal(
            rule_type=RuleType.COMPLETENESS, suggested_lower=1.0,
        )
        result = gen.generate(p)
        assert result.startswith("Completeness")

    def test_allowed_values_starts_with_columnvalues(self):
        from core.gdq_rule_generator import GDQRuleGenerator
        gen = GDQRuleGenerator()
        p = _make_numeric_proposal(
            rule_type=RuleType.ALLOWED_VALUES,
            target_column="COD_SITU",
            suggested_values=["1", "2"],
        )
        result = gen.generate(p)
        assert result.startswith("ColumnValues")

    def test_primary_key_starts_with_isprimarykey(self):
        from core.gdq_rule_generator import GDQRuleGenerator
        gen = GDQRuleGenerator()
        p = _make_numeric_proposal(
            rule_type=RuleType.IS_PRIMARY_KEY,
            suggested_values=["COL_A", "COL_B"],
        )
        result = gen.generate(p)
        assert result.startswith("IsPrimaryKey")

    def test_column_names_uppercase(self):
        from core.gdq_rule_generator import GDQRuleGenerator
        gen = GDQRuleGenerator()
        p = _make_numeric_proposal(target_column="vlr_saldo")
        result = gen.generate(p)
        assert "VLR_SALDO" in result
        assert "vlr_saldo" not in result


# ---------------------------------------------------------------------------
# classify_series — SeriesProfile shape
# ---------------------------------------------------------------------------

class TestClassifySeriesContract:
    """classify_series retorna SeriesProfile com campos obrigatorios."""

    def test_returns_series_profile(self):
        from core.series_regime import classify_series
        result = classify_series(_stable_values(), _stable_dates())
        assert hasattr(result, "regime")
        assert isinstance(result.regime, SeriesRegime)

    def test_has_numeric_fields(self):
        from core.series_regime import classify_series
        result = classify_series(_stable_values(), _stable_dates())
        assert isinstance(result.n_points, int)
        assert isinstance(result.n_valid, int)
        assert isinstance(result.cv, float)
        assert isinstance(result.skewness, float)

    def test_has_boolean_flags(self):
        from core.series_regime import classify_series
        result = classify_series(_stable_values(), _stable_dates())
        for attr in ("is_volatile", "has_trend", "is_seasonal", "has_structural_break",
                     "is_zero_inflated", "is_asymmetric", "is_sparse"):
            assert isinstance(getattr(result, attr), bool), f"{attr} nao e bool"

    def test_frozen_immutable(self):
        from core.series_regime import classify_series
        result = classify_series(_stable_values(), _stable_dates())
        with pytest.raises(AttributeError):
            result.regime = SeriesRegime.VOLATILE


# ---------------------------------------------------------------------------
# score_proposal — RuleScore shape
# ---------------------------------------------------------------------------

class TestScoreProposalContract:
    """score_proposal retorna RuleScore com campos obrigatorios."""

    REQUIRED_ATTRS = (
        "coverage", "stability", "interpretability", "cost_efficiency",
        "false_positive_count", "sensitivity", "score_total",
        "confidence", "recommendation", "warnings",
    )

    def _score_with_backtest(self):
        from core.rule_scoring import score_proposal
        p = _make_numeric_proposal(
            backtest=BacktestSummary(
                total_periods=30, periods_pass=28, periods_fail=2,
                coverage_pct=93.3, false_positive_proxy=1,
                band_width_ratio=0.05, stability_score=0.9,
                has_drift=False,
            ),
        )
        return score_proposal(p, _stable_values())

    def test_has_all_required_attrs(self):
        result = self._score_with_backtest()
        for attr in self.REQUIRED_ATTRS:
            assert hasattr(result, attr), f"Faltando atributo: {attr}"

    def test_score_total_in_range(self):
        result = self._score_with_backtest()
        assert 0.0 <= result.score_total <= 1.0

    def test_confidence_is_enum(self):
        result = self._score_with_backtest()
        assert isinstance(result.confidence, ConfidenceLevel)

    def test_recommendation_is_string(self):
        result = self._score_with_backtest()
        assert isinstance(result.recommendation, str)
        assert len(result.recommendation) > 0

    def test_warnings_is_list(self):
        result = self._score_with_backtest()
        assert isinstance(result.warnings, list)

    def test_no_backtest_returns_low_confidence(self):
        from core.rule_scoring import score_proposal
        p = _make_numeric_proposal()  # sem backtest
        result = score_proposal(p)
        assert result.confidence == ConfidenceLevel.LOW


# ---------------------------------------------------------------------------
# validate_syntax — warnings list
# ---------------------------------------------------------------------------

class TestValidateSyntaxContract:
    """validate_syntax retorna lista de warnings (vazia = valido)."""

    def test_valid_syntax_returns_empty(self):
        from services.export_service import ExportService
        svc = ExportService()
        warnings = svc.validate_syntax(
            "Completeness VLR_SALDO >= 1.00"
        )
        assert isinstance(warnings, list)
        assert len(warnings) == 0

    def test_invalid_syntax_returns_warnings(self):
        from services.export_service import ExportService
        svc = ExportService()
        warnings = svc.validate_syntax(
            '(Mean "VLR_SALDO" >= 10)'  # coluna com aspas = warning
        )
        assert isinstance(warnings, list)
        assert len(warnings) > 0
        assert all(isinstance(w, str) for w in warnings)
