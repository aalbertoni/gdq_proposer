"""Testes para infra/partition_pruning.py e integracao com QueryBuilder.

Valida que o partition pruning fisico:
- NUNCA aplica funcao (CAST/DATE_PARSE) sobre a coluna de particao
- Gera predicados brutos compativeis com Athena partition pruning
- Formata corretamente para cada partition_format
- Funciona com e sem reference_date
"""

import pytest
from datetime import date

from infra.partition_pruning import (
    build_partition_predicate,
    build_multi_column_predicate,
    compute_cutoff_date,
)
from infra.query_builder import QueryBuilder
from infra.sql_dialect import SQLDialect


# ---------------------------------------------------------------------------
# compute_cutoff_date
# ---------------------------------------------------------------------------

class TestComputeCutoffDate:
    def test_with_reference_date(self):
        cutoff = compute_cutoff_date("2026-03-20", 30)
        assert cutoff == date(2026, 2, 18)

    def test_without_reference_date(self):
        cutoff = compute_cutoff_date(None, 30)
        assert cutoff == date.today() - __import__("datetime").timedelta(days=30)

    def test_zero_lookback(self):
        cutoff = compute_cutoff_date("2026-01-15", 0)
        assert cutoff == date(2026, 1, 15)


# ---------------------------------------------------------------------------
# build_partition_predicate
# ---------------------------------------------------------------------------

class TestBuildPartitionPredicate:
    def test_yyyy_mm_dd(self):
        result = build_partition_predicate("dt_ref", "%Y-%m-%d", date(2026, 2, 18))
        assert result == "\"dt_ref\" >= '2026-02-18'"
        assert "CAST" not in result
        assert "DATE_PARSE" not in result

    def test_yyyymmdd(self):
        result = build_partition_predicate("dt_ref", "%Y%m%d", date(2026, 2, 18))
        assert result == "\"dt_ref\" >= '20260218'"

    def test_yyyymm(self):
        result = build_partition_predicate("dt_ref", "%Y%m", date(2026, 2, 18))
        assert result == "\"dt_ref\" >= '202602'"

    def test_yyyy_dot_mm_dot_dd(self):
        result = build_partition_predicate("dt_ref", "%Y.%m.%d", date(2026, 2, 18))
        assert result == "\"dt_ref\" >= '2026.02.18'"

    def test_native_date_athena(self):
        result = build_partition_predicate("dt_ref", None, date(2026, 2, 18), SQLDialect.ATHENA)
        assert result == "\"dt_ref\" >= DATE '2026-02-18'"
        assert "CAST" not in result

    def test_native_date_duckdb(self):
        result = build_partition_predicate("dt_ref", None, date(2026, 2, 18), SQLDialect.DUCKDB)
        assert "TRY_CAST" in result
        assert "2026-02-18" in result

    def test_integer_yyyymmdd(self):
        result = build_partition_predicate("dt_ref", "%Y%m%d", date(2026, 2, 18), is_integer=True)
        assert result == "\"dt_ref\" >= 20260218"
        assert "'" not in result  # sem aspas

    def test_integer_yyyymm(self):
        result = build_partition_predicate("dt_ref", "%Y%m", date(2026, 2, 18), is_integer=True)
        assert result == "\"dt_ref\" >= 202602"
        assert "'" not in result

    def test_integer_literal_is_numeric(self):
        result = build_partition_predicate("dt_ref", "%Y%m%d", date(2026, 2, 18), is_integer=True)
        # Extrair o literal e verificar que e numerico
        literal = result.split(">= ")[1]
        assert literal.isdigit()

    def test_string_has_quotes_integer_does_not(self):
        """Mesmo formato, tipos diferentes geram literais diferentes."""
        str_result = build_partition_predicate("dt_ref", "%Y%m%d", date(2026, 2, 18), is_integer=False)
        int_result = build_partition_predicate("dt_ref", "%Y%m%d", date(2026, 2, 18), is_integer=True)
        assert "'" in str_result
        assert "'" not in int_result

    def test_no_function_on_column(self):
        """Nenhum formato/tipo aplica funcao sobre a coluna."""
        for fmt in ["%Y-%m-%d", "%Y%m%d", "%Y%m", "%Y.%m.%d", None]:
            for is_int in [False, True]:
                if fmt is None and is_int:
                    continue  # tipo nativo nao e integer
                result = build_partition_predicate("dt_ref", fmt, date(2026, 1, 1), is_integer=is_int)
                # Coluna deve aparecer como "dt_ref", nao CAST("dt_ref" ...) ou DATE_PARSE(...)
            assert result.startswith('"dt_ref"')


# ---------------------------------------------------------------------------
# QueryBuilder.resolve_partition_filter (novo comportamento)
# ---------------------------------------------------------------------------

class TestResolvePartitionFilterNew:
    def test_string_partition_no_cast(self, qb_athena):
        result = qb_athena.resolve_partition_filter(
            partition_column="dt_ref",
            partition_format="%Y-%m-%d",
            lookback_value=30,
            reference_date="2026-03-20",
        )
        assert '"dt_ref" >= \'2026-02-18\'' == result
        assert "CAST" not in result
        assert "DATE_PARSE" not in result
        assert "DATE_ADD" not in result

    def test_yyyymmdd_format(self, qb_athena):
        result = qb_athena.resolve_partition_filter(
            partition_column="dt_ref",
            partition_format="%Y%m%d",
            lookback_value=30,
            reference_date="2026-03-20",
        )
        assert "20260218" in result

    def test_native_date_partition(self, qb_athena):
        result = qb_athena.resolve_partition_filter(
            partition_column="dt_ref",
            partition_format=None,
            lookback_value=30,
            reference_date="2026-03-20",
        )
        assert "DATE '2026-02-18'" in result
        assert "CAST" not in result

    def test_no_partition_returns_empty(self, qb_athena):
        result = qb_athena.resolve_partition_filter(
            partition_column=None,
            partition_format=None,
            lookback_value=30,
        )
        assert result == ""

    def test_duckdb_native_uses_try_cast(self, qb_duckdb):
        result = qb_duckdb.resolve_partition_filter(
            partition_column="dt_ref",
            partition_format=None,
            lookback_value=30,
            reference_date="2026-03-20",
        )
        assert "TRY_CAST" in result

    def test_duckdb_string_no_try_cast(self, qb_duckdb):
        result = qb_duckdb.resolve_partition_filter(
            partition_column="dt_ref",
            partition_format="%Y-%m-%d",
            lookback_value=30,
            reference_date="2026-03-20",
        )
        assert "TRY_CAST" not in result
        assert "2026-02-18" in result

    def test_integer_yyyymmdd_no_quotes(self, qb_athena):
        """Integer partition: literal sem aspas."""
        result = qb_athena.resolve_partition_filter(
            partition_column="dt_ref",
            partition_format="%Y%m%d",
            lookback_value=30,
            reference_date="2026-03-20",
            partition_is_integer=True,
        )
        assert result == '"dt_ref" >= 20260218'
        assert "'" not in result

    def test_integer_yyyymm_no_quotes(self, qb_athena):
        result = qb_athena.resolve_partition_filter(
            partition_column="dt_ref",
            partition_format="%Y%m",
            lookback_value=30,
            reference_date="2026-03-20",
            partition_is_integer=True,
        )
        assert result == '"dt_ref" >= 202602'
        assert "'" not in result

    def test_string_yyyymmdd_has_quotes(self, qb_athena):
        """String partition: literal com aspas."""
        result = qb_athena.resolve_partition_filter(
            partition_column="dt_ref",
            partition_format="%Y%m%d",
            lookback_value=30,
            reference_date="2026-03-20",
            partition_is_integer=False,
        )
        assert "'" in result
        assert "'20260218'" in result


# ---------------------------------------------------------------------------
# Integracao: partition_filter nos templates
# ---------------------------------------------------------------------------

class TestPartitionFilterInTemplates:
    def test_numeric_history_has_separate_partition_filter(self, qb_athena):
        """partition_filter e date_expression sao predicados distintos."""
        sql = qb_athena.build_numeric_history(
            schema="db", table="tb", col="VLR",
            date_expression='CAST("dt_ref" AS DATE)',
            lookback_value=30,
            partition_filter="\"dt_ref\" >= '2026-02-18'",
            reference_date="2026-03-20",
        )
        # date_expression no WHERE principal (para analise)
        assert 'CAST("dt_ref" AS DATE)' in sql
        # partition_filter bruto (para pruning)
        assert "\"dt_ref\" >= '2026-02-18'" in sql

    def test_column_sample_partition_filter_no_cast(self, qb_athena):
        """column_sample com partition_filter bruto."""
        sql = qb_athena.build_column_sample(
            schema="db", table="tb", col="VLR", temporal_col="dt_ref",
            date_expression='CAST("dt_ref" AS DATE)',
            sample_periods=10,
            partition_filter="\"dt_ref\" >= '2026-02-18'",
            reference_date="2026-03-20",
        )
        assert "\"dt_ref\" >= '2026-02-18'" in sql


# ---------------------------------------------------------------------------
# Regression: date_expression NAO foi removido dos templates
# ---------------------------------------------------------------------------

class TestDateExpressionPreserved:
    def test_numeric_history_still_uses_date_expression(self, qb_athena):
        sql = qb_athena.build_numeric_history(
            schema="db", table="tb", col="VLR",
            date_expression='CAST("dt_ref" AS DATE)',
            lookback_value=30,
            reference_date="2026-03-20",
        )
        # date_expression para analise temporal — deve estar no WHERE
        assert 'CAST("dt_ref" AS DATE)' in sql


# ---------------------------------------------------------------------------
# build_multi_column_predicate
# ---------------------------------------------------------------------------

class TestBuildMultiColumnPredicate:
    def test_empty_columns_returns_empty(self):
        result = build_multi_column_predicate([], {}, {}, date(2026, 2, 23))
        assert result == ""

    def test_single_column_same_as_single_predicate(self):
        result = build_multi_column_predicate(
            ["dt_ref"], {"dt_ref": "%Y-%m-%d"}, {"dt_ref": False},
            date(2026, 2, 23),
        )
        expected = build_partition_predicate("dt_ref", "%Y-%m-%d", date(2026, 2, 23))
        assert result == expected

    def test_golden_output_ymd_integer(self):
        """Golden output: ano/mes/dia como inteiros."""
        result = build_multi_column_predicate(
            ["ano", "mes", "dia"],
            {"ano": "%Y", "mes": "%m", "dia": "%d"},
            {"ano": True, "mes": True, "dia": True},
            date(2026, 2, 23),
        )
        assert result == '"ano" >= 2026 AND "mes" >= 02 AND "dia" >= 23'

    def test_two_columns(self):
        result = build_multi_column_predicate(
            ["ano", "mes"],
            {"ano": "%Y", "mes": "%m"},
            {"ano": True, "mes": True},
            date(2026, 2, 23),
        )
        assert result == '"ano" >= 2026 AND "mes" >= 02'

    def test_mixed_types_int_and_string(self):
        """ano integer, mes string."""
        result = build_multi_column_predicate(
            ["ano", "mes"],
            {"ano": "%Y", "mes": "%m"},
            {"ano": True, "mes": False},
            date(2026, 2, 23),
        )
        assert '"ano" >= 2026' in result
        assert "\"mes\" >= '02'" in result
        assert " AND " in result

    def test_native_date_column(self):
        """Coluna com tipo nativo (formato None)."""
        result = build_multi_column_predicate(
            ["dt_ref"], {"dt_ref": None}, {},
            date(2026, 2, 23), dialect=SQLDialect.ATHENA,
        )
        assert "DATE '2026-02-23'" in result

    def test_duckdb_dialect(self):
        result = build_multi_column_predicate(
            ["ano", "mes"],
            {"ano": "%Y", "mes": "%m"},
            {"ano": True, "mes": True},
            date(2026, 2, 23),
            dialect=SQLDialect.DUCKDB,
        )
        assert '"ano" >= 2026' in result
        assert '"mes" >= 02' in result

    def test_no_function_on_columns(self):
        """Multi-column predicates must never apply functions on columns."""
        result = build_multi_column_predicate(
            ["ano", "mes", "dia"],
            {"ano": "%Y", "mes": "%m", "dia": "%d"},
            {"ano": True, "mes": True, "dia": True},
            date(2026, 2, 23),
        )
        assert "CAST" not in result
        assert "DATE_PARSE" not in result

    def test_missing_format_defaults_native(self):
        """Column not in formats dict uses None (native date)."""
        result = build_multi_column_predicate(
            ["dt_ref"], {}, {},
            date(2026, 2, 23), dialect=SQLDialect.ATHENA,
        )
        assert "DATE '2026-02-23'" in result

    def test_missing_is_integer_defaults_false(self):
        """Column not in is_integer map defaults to False (string)."""
        result = build_multi_column_predicate(
            ["dt_ref"], {"dt_ref": "%Y%m%d"}, {},
            date(2026, 2, 23),
        )
        assert "'" in result  # string literal with quotes


# ---------------------------------------------------------------------------
# QueryBuilder.resolve_partition_filter — multi-column path
# ---------------------------------------------------------------------------

class TestResolvePartitionFilterMultiColumn:
    def test_multi_col_generates_and_predicate(self, qb_athena):
        result = qb_athena.resolve_partition_filter(
            partition_columns=["ano", "mes"],
            partition_formats={"ano": "%Y", "mes": "%m"},
            partition_is_integer_map={"ano": True, "mes": True},
            lookback_value=30,
            reference_date="2026-03-20",
        )
        assert " AND " in result
        assert '"ano"' in result
        assert '"mes"' in result

    def test_multi_col_takes_priority_over_single(self, qb_athena):
        """When both partition_columns and partition_column given, multi wins."""
        result = qb_athena.resolve_partition_filter(
            partition_column="dt_ref",
            partition_format="%Y-%m-%d",
            partition_columns=["ano", "mes"],
            partition_formats={"ano": "%Y", "mes": "%m"},
            partition_is_integer_map={"ano": True, "mes": True},
            lookback_value=30,
            reference_date="2026-03-20",
        )
        assert " AND " in result
        assert '"ano"' in result
        assert "dt_ref" not in result

    def test_empty_multi_col_falls_to_single(self, qb_athena):
        """Empty partition_columns falls back to single partition_column."""
        result = qb_athena.resolve_partition_filter(
            partition_column="dt_ref",
            partition_format="%Y-%m-%d",
            partition_columns=[],
            lookback_value=30,
            reference_date="2026-03-20",
        )
        assert "dt_ref" in result
        assert " AND " not in result

    def test_both_empty_returns_empty(self, qb_athena):
        result = qb_athena.resolve_partition_filter(
            partition_columns=[],
            lookback_value=30,
        )
        assert result == ""

    def test_duckdb_multi_col(self, qb_duckdb):
        result = qb_duckdb.resolve_partition_filter(
            partition_columns=["ano", "mes", "dia"],
            partition_formats={"ano": "%Y", "mes": "%m", "dia": "%d"},
            partition_is_integer_map={"ano": True, "mes": True, "dia": True},
            lookback_value=30,
            reference_date="2026-03-20",
        )
        assert " AND " in result
        assert '"ano"' in result
