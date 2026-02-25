"""Testes para core/gdq_renderer.py.

Valida string GDQ contra exemplos de produção de docs/gdq_syntax_reference.md.
"""

import pytest

from core.gdq_renderer import DualGuardRenderer
from core.models.dual_guard import (
    DualGuardSpec,
    FormattingProfile,
    MEAN_PROFILE,
    STDDEV_PROFILE,
    ROWCOUNT_PROFILE,
)
from core.models.enums import MetricRef


@pytest.fixture
def renderer():
    return DualGuardRenderer()


# ---------------------------------------------------------------------------
# Mean — produção
# ---------------------------------------------------------------------------

class TestMeanProduction:
    EXPECTED = (
        '(((Mean VLR_SALD_AVNC_OPCR >= (avg(last(30)) - (2 * std(last(30))) - 0.01))'
        ' AND '
        '(Mean VLR_SALD_AVNC_OPCR <= (avg(last(30)) + (2 * std(last(30))) + 0.01)))'
        ' OR '
        '((Mean VLR_SALD_AVNC_OPCR >= (avg(last(30)) * 0.9) - 0.01)'
        ' AND '
        '(Mean VLR_SALD_AVNC_OPCR <= (avg(last(30)) * 1.1) + 0.01)))'
    )

    def test_mean_matches_production(self, renderer):
        spec = DualGuardSpec(
            metric=MetricRef.MEAN,
            target="VLR_SALD_AVNC_OPCR",
            n_periods=30,
            n_sigma=2,
            margin_pct=0.10,
            buffer=0.01,
        )
        result = renderer.render(spec)
        assert result == self.EXPECTED, f"\nExpected:\n{self.EXPECTED}\nGot:\n{result}"

    def test_mean_no_quotes_on_column(self, renderer):
        spec = DualGuardSpec(
            metric=MetricRef.MEAN,
            target="MY_COL",
            n_periods=30,
        )
        result = renderer.render(spec)
        assert '"' not in result
        assert "MY_COL" in result


# ---------------------------------------------------------------------------
# StandardDeviation — produção
# ---------------------------------------------------------------------------

class TestStdDevProduction:
    EXPECTED = (
        '(((StandardDeviation VLR_PARC_OPCR >= (avg(last(30)) - (2 * std(last(30))) - 0.01))'
        ' AND '
        '(StandardDeviation VLR_PARC_OPCR <= (avg(last(30)) + (2 * std(last(30))) + 0.01)))'
        ' OR '
        '((StandardDeviation VLR_PARC_OPCR >= (avg(last(30)) * 0.9) - 0.01)'
        ' AND '
        '(StandardDeviation VLR_PARC_OPCR <= (avg(last(30)) * 1.1) + 0.01)))'
    )

    def test_stddev_matches_production(self, renderer):
        spec = DualGuardSpec(
            metric=MetricRef.STANDARD_DEVIATION,
            target="VLR_PARC_OPCR",
            n_periods=30,
            n_sigma=2,
            margin_pct=0.10,
            buffer=0.01,
        )
        result = renderer.render(spec)
        assert result == self.EXPECTED, f"\nExpected:\n{self.EXPECTED}\nGot:\n{result}"


# ---------------------------------------------------------------------------
# RowCount — produção
# ---------------------------------------------------------------------------

class TestRowCountProduction:
    EXPECTED = (
        '(((RowCount >= (avg(last(30)) * 1.0 - (2.0 * std(last(30)))))'
        ' AND '
        '(RowCount <= (avg(last(30)) * 1.0 + (2.0 * std(last(30))))))'
        ' OR '
        '((RowCount >= (avg(last(30)) - (avg(last(30)) * 0.1)))'
        ' AND '
        '(RowCount <= (avg(last(30)) + (avg(last(30)) * 0.1)))))'
    )

    def test_rowcount_matches_production(self, renderer):
        spec = DualGuardSpec(
            metric=MetricRef.ROW_COUNT,
            target="",
            n_periods=30,
            n_sigma=2,
            margin_pct=0.10,
        )
        result = renderer.render(spec)
        assert result == self.EXPECTED, f"\nExpected:\n{self.EXPECTED}\nGot:\n{result}"

    def test_rowcount_k_is_float(self, renderer):
        spec = DualGuardSpec(
            metric=MetricRef.ROW_COUNT,
            n_periods=30,
            n_sigma=2,
        )
        result = renderer.render(spec)
        assert "2.0 *" in result

    def test_rowcount_no_buffer(self, renderer):
        spec = DualGuardSpec(
            metric=MetricRef.ROW_COUNT,
            n_periods=30,
        )
        result = renderer.render(spec)
        assert "0.01" not in result


# ---------------------------------------------------------------------------
# Custom params
# ---------------------------------------------------------------------------

class TestCustomParams:
    def test_mean_custom_n_k_margin(self, renderer):
        spec = DualGuardSpec(
            metric=MetricRef.MEAN,
            target="COL_X",
            n_periods=20,
            n_sigma=3,
            margin_pct=0.15,
            buffer=0.01,
        )
        result = renderer.render(spec)
        assert "last(20)" in result
        assert "3 *" in result
        assert "* 0.85" in result
        assert "* 1.15" in result

    def test_mean_zero_buffer(self, renderer):
        spec = DualGuardSpec(
            metric=MetricRef.MEAN,
            target="COL_X",
            n_periods=30,
            buffer=0.0,
        )
        result = renderer.render(spec)
        assert "0.01" not in result


# ---------------------------------------------------------------------------
# Balanced parentheses
# ---------------------------------------------------------------------------

class TestParentheses:
    def test_mean_balanced(self, renderer):
        spec = DualGuardSpec(metric=MetricRef.MEAN, target="COL")
        result = renderer.render(spec)
        assert result.count("(") == result.count(")")

    def test_stddev_balanced(self, renderer):
        spec = DualGuardSpec(metric=MetricRef.STANDARD_DEVIATION, target="COL")
        result = renderer.render(spec)
        assert result.count("(") == result.count(")")

    def test_rowcount_balanced(self, renderer):
        spec = DualGuardSpec(metric=MetricRef.ROW_COUNT)
        result = renderer.render(spec)
        assert result.count("(") == result.count(")")
