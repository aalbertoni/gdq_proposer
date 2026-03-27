"""Testes para core/gdq_date_filter.py."""

import pytest

from core.gdq_date_filter import (
    build_gdq_date_filter_expr,
    explain_date_filter,
    explain_execution_frequency_warning,
)
from core.models.enums import DateFilterGranularity, DateReferenceStrategy


class TestBuildGdqDateFilterExpr:
    """Testes do builder de expressão WHERE Spark."""

    def test_none_returns_none(self):
        result = build_gdq_date_filter_expr(
            "COL", DateFilterGranularity.NONE, DateReferenceStrategy.CURRENT
        )
        assert result is None

    def test_current_month_string(self):
        result = build_gdq_date_filter_expr(
            "ANO_MES_RFRC_CRED",
            DateFilterGranularity.MONTH,
            DateReferenceStrategy.CURRENT,
        )
        assert result == "ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')"

    def test_current_day_string(self):
        result = build_gdq_date_filter_expr(
            "DT_REF", DateFilterGranularity.DAY, DateReferenceStrategy.CURRENT
        )
        assert result == "DT_REF = date_format(current_date(), 'yyyyMMdd')"

    def test_current_year_string(self):
        result = build_gdq_date_filter_expr(
            "ANO_REF", DateFilterGranularity.YEAR, DateReferenceStrategy.CURRENT
        )
        assert result == "ANO_REF = date_format(current_date(), 'yyyy')"

    def test_current_month_integer(self):
        result = build_gdq_date_filter_expr(
            "COD_MES",
            DateFilterGranularity.MONTH,
            DateReferenceStrategy.CURRENT,
            column_is_integer=True,
        )
        assert result == "COD_MES = cast(date_format(current_date(), 'yyyyMM') as int)"

    def test_lag_1_month(self):
        result = build_gdq_date_filter_expr(
            "ANO_MES",
            DateFilterGranularity.MONTH,
            DateReferenceStrategy.LAG_N,
            lag=1,
        )
        assert result == "ANO_MES = date_format(add_months(current_date(), -1), 'yyyyMM')"

    def test_lag_3_months(self):
        result = build_gdq_date_filter_expr(
            "ANO_MES",
            DateFilterGranularity.MONTH,
            DateReferenceStrategy.LAG_N,
            lag=3,
        )
        assert result == "ANO_MES = date_format(add_months(current_date(), -3), 'yyyyMM')"

    def test_lag_7_days(self):
        result = build_gdq_date_filter_expr(
            "DT_REF",
            DateFilterGranularity.DAY,
            DateReferenceStrategy.LAG_N,
            lag=7,
        )
        assert result == "DT_REF = date_format(date_sub(current_date(), 7), 'yyyyMMdd')"

    def test_lag_1_year(self):
        result = build_gdq_date_filter_expr(
            "ANO",
            DateFilterGranularity.YEAR,
            DateReferenceStrategy.LAG_N,
            lag=1,
        )
        assert result == "ANO = date_format(add_months(current_date(), -12), 'yyyy')"

    def test_lag_integer_column(self):
        result = build_gdq_date_filter_expr(
            "COD_MES",
            DateFilterGranularity.MONTH,
            DateReferenceStrategy.LAG_N,
            lag=1,
            column_is_integer=True,
        )
        assert result == "COD_MES = cast(date_format(add_months(current_date(), -1), 'yyyyMM') as int)"

    def test_max_value(self):
        result = build_gdq_date_filter_expr(
            "ANO_MES_RFRC_CRED",
            DateFilterGranularity.MONTH,
            DateReferenceStrategy.MAX_VALUE,
        )
        assert result == "ANO_MES_RFRC_CRED = (select max(ANO_MES_RFRC_CRED) from primary)"

    def test_max_value_ignores_integer_flag(self):
        """max() works regardless of column type."""
        result = build_gdq_date_filter_expr(
            "COD_MES",
            DateFilterGranularity.MONTH,
            DateReferenceStrategy.MAX_VALUE,
            column_is_integer=True,
        )
        assert result == "COD_MES = (select max(COD_MES) from primary)"

    def test_custom_spark_format(self):
        result = build_gdq_date_filter_expr(
            "DT_REF",
            DateFilterGranularity.DAY,
            DateReferenceStrategy.CURRENT,
            custom_spark_format="yyyy-MM-dd",
        )
        assert result == "DT_REF = date_format(current_date(), 'yyyy-MM-dd')"


class TestExplainDateFilter:
    """Testes das explicações em pt-BR."""

    def test_none(self):
        result = explain_date_filter(
            "COL", DateFilterGranularity.NONE, DateReferenceStrategy.CURRENT
        )
        assert "snapshot inteiro" in result

    def test_current_month(self):
        result = explain_date_filter(
            "ANO_MES", DateFilterGranularity.MONTH, DateReferenceStrategy.CURRENT
        )
        assert "ANO_MES" in result
        assert "mes corrente" in result

    def test_lag_2(self):
        result = explain_date_filter(
            "ANO_MES", DateFilterGranularity.MONTH, DateReferenceStrategy.LAG_N, lag=2
        )
        assert "2 mes(s) atras" in result

    def test_max_value(self):
        result = explain_date_filter(
            "ANO_MES", DateFilterGranularity.MONTH, DateReferenceStrategy.MAX_VALUE
        )
        assert "ultimo valor" in result


class TestExplainExecutionFrequencyWarning:
    """Testes do warning de frequência."""

    def test_none_returns_empty(self):
        assert explain_execution_frequency_warning(DateFilterGranularity.NONE) == ""

    def test_monthly_contains_frequency_guidance(self):
        result = explain_execution_frequency_warning(DateFilterGranularity.MONTH)
        assert "mensal" in result
        assert "last(N)" in result
        assert "std" in result

    def test_daily_contains_frequency_guidance(self):
        result = explain_execution_frequency_warning(DateFilterGranularity.DAY)
        assert "diaria" in result


class TestHasDateFilter:
    """Testes da property has_date_filter no DatasetConfig."""

    def test_none_means_no_filter(self):
        from core.models.dataset_config import DatasetConfig
        config = DatasetConfig(schema="s", table="t", date_column="dt")
        assert config.has_date_filter is False

    def test_month_means_has_filter(self):
        from core.models.dataset_config import DatasetConfig
        config = DatasetConfig(
            schema="s", table="t", date_column="dt",
            date_filter_granularity=DateFilterGranularity.MONTH,
        )
        assert config.has_date_filter is True
