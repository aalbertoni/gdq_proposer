"""Testes para infra/sql_dialect.py."""

import pytest
from infra.sql_dialect import SQLDialect, DIALECT_FUNCTIONS, adapt_function


# ---------------------------------------------------------------------------
# APPROX_PERCENTILE
# ---------------------------------------------------------------------------

class TestApproxPercentile:
    def test_athena(self):
        result = adapt_function(
            "APPROX_PERCENTILE",
            SQLDialect.ATHENA,
            col='CAST("VLR" AS DOUBLE)',
            quantiles="0.25, 0.5, 0.75",
        )
        assert result == 'APPROX_PERCENTILE(CAST("VLR" AS DOUBLE), ARRAY[0.25, 0.5, 0.75])'

    def test_duckdb(self):
        result = adapt_function(
            "APPROX_PERCENTILE",
            SQLDialect.DUCKDB,
            col='CAST("VLR" AS DOUBLE)',
            quantiles="0.25, 0.5, 0.75",
        )
        assert result == 'QUANTILE_CONT(CAST("VLR" AS DOUBLE), [0.25, 0.5, 0.75])'


# ---------------------------------------------------------------------------
# STDDEV
# ---------------------------------------------------------------------------

class TestStddev:
    def test_athena(self):
        result = adapt_function(
            "STDDEV", SQLDialect.ATHENA, expr='CAST("VLR" AS DOUBLE)'
        )
        assert result == 'STDDEV(CAST("VLR" AS DOUBLE))'

    def test_duckdb(self):
        result = adapt_function(
            "STDDEV", SQLDialect.DUCKDB, expr='CAST("VLR" AS DOUBLE)'
        )
        assert result == 'STDDEV_SAMP(CAST("VLR" AS DOUBLE))'


# ---------------------------------------------------------------------------
# DATE_SUBTRACT_DAYS
# ---------------------------------------------------------------------------

class TestDateSubtractDays:
    def test_athena(self):
        result = adapt_function(
            "DATE_SUBTRACT_DAYS", SQLDialect.ATHENA, n=30
        )
        assert result == "DATE_ADD('day', -30, CURRENT_DATE)"

    def test_duckdb(self):
        result = adapt_function(
            "DATE_SUBTRACT_DAYS", SQLDialect.DUCKDB, n=30
        )
        assert result == "CURRENT_DATE - INTERVAL '30' DAY"


# ---------------------------------------------------------------------------
# TABLE_REF
# ---------------------------------------------------------------------------

class TestTableRef:
    def test_athena(self):
        result = adapt_function(
            "TABLE_REF", SQLDialect.ATHENA, schema="db_credito", table="tb_ops"
        )
        assert result == '"db_credito"."tb_ops"'

    def test_duckdb(self):
        result = adapt_function(
            "TABLE_REF", SQLDialect.DUCKDB, schema="db_credito", table="tb_ops"
        )
        assert result == '"tb_ops"'


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unknown_function_raises_key_error(self):
        with pytest.raises(KeyError):
            adapt_function("NONEXISTENT", SQLDialect.ATHENA)

    def test_all_functions_have_both_dialects(self):
        for func_name, dialects in DIALECT_FUNCTIONS.items():
            assert SQLDialect.ATHENA in dialects, f"{func_name} missing ATHENA"
            assert SQLDialect.DUCKDB in dialects, f"{func_name} missing DUCKDB"

    def test_dialect_enum_values(self):
        assert SQLDialect.ATHENA.value == "athena"
        assert SQLDialect.DUCKDB.value == "duckdb"
