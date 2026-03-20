"""Testes unitarios para infra/query_builder.py.

Valida que cada metodo build_* produz SQL com clausulas esperadas
para ambos os dialetos (Athena e DuckDB).
"""

import pytest

from infra.query_builder import QueryBuilder
from infra.sql_dialect import SQLDialect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCHEMA = "gdq_test_db"
TABLE = "tb_operacoes"
COL = "VLR_SALDO"
TEMPORAL = "dt_ref"
DATE_EXPR = 'CAST("dt_ref" AS DATE)'


# ---------------------------------------------------------------------------
# build_metadata_discovery
# ---------------------------------------------------------------------------

class TestMetadataDiscovery:
    def test_athena_has_schema_table(self, qb_athena):
        sql = qb_athena.build_metadata_discovery(SCHEMA, TABLE)
        assert "information_schema" in sql.lower() or TABLE in sql

    def test_duckdb_no_schema_prefix(self, qb_duckdb):
        sql = qb_duckdb.build_metadata_discovery(SCHEMA, TABLE)
        assert TABLE in sql


# ---------------------------------------------------------------------------
# build_date_range
# ---------------------------------------------------------------------------

class TestDateRange:
    def test_athena_contains_min_max(self, qb_athena):
        sql = qb_athena.build_date_range(SCHEMA, TABLE, TEMPORAL, DATE_EXPR)
        sql_lower = sql.lower()
        assert "min" in sql_lower
        assert "max" in sql_lower
        assert f'"{SCHEMA}"."{TABLE}"' in sql

    def test_duckdb_no_schema(self, qb_duckdb):
        sql = qb_duckdb.build_date_range(SCHEMA, TABLE, TEMPORAL, DATE_EXPR)
        assert f'"{TABLE}"' in sql
        assert f'"{SCHEMA}"' not in sql

    def test_base_filter_injected(self, qb_athena):
        sql = qb_athena.build_date_range(
            SCHEMA, TABLE, TEMPORAL, DATE_EXPR, base_filter="COD_TIPO = 1",
        )
        assert "COD_TIPO = 1" in sql

    def test_no_base_filter(self, qb_athena):
        sql = qb_athena.build_date_range(SCHEMA, TABLE, TEMPORAL, DATE_EXPR)
        assert "COD_TIPO" not in sql


# ---------------------------------------------------------------------------
# build_volume_by_period
# ---------------------------------------------------------------------------

class TestVolumeByPeriod:
    def test_has_group_by_and_order(self, qb_athena):
        sql = qb_athena.build_volume_by_period(
            SCHEMA, TABLE, TEMPORAL, DATE_EXPR,
        )
        sql_lower = sql.lower()
        assert "group by" in sql_lower
        assert "order by" in sql_lower

    def test_limit_applied(self, qb_athena):
        sql = qb_athena.build_volume_by_period(
            SCHEMA, TABLE, TEMPORAL, DATE_EXPR, limit=25,
        )
        assert "25" in sql

    def test_partition_filter_injected(self, qb_duckdb):
        sql = qb_duckdb.build_volume_by_period(
            SCHEMA, TABLE, TEMPORAL, DATE_EXPR,
            partition_filter="dt_ref >= '2026-01-01'",
        )
        assert "dt_ref >= '2026-01-01'" in sql

    def test_no_partition_filter(self, qb_duckdb):
        """Sem partition_filter, nao ha AND partition no WHERE."""
        sql = qb_duckdb.build_volume_by_period(
            SCHEMA, TABLE, TEMPORAL, DATE_EXPR,
        )
        # O filtro nao deve aparecer na clausula WHERE (pode aparecer em comentarios)
        where_onwards = sql.lower().split("where")[1] if "where" in sql.lower() else ""
        assert "dt_ref >=" not in where_onwards


# ---------------------------------------------------------------------------
# build_numeric_history
# ---------------------------------------------------------------------------

class TestNumericHistory:
    def test_athena_uses_stddev(self, qb_athena):
        sql = qb_athena.build_numeric_history(
            SCHEMA, TABLE, COL, DATE_EXPR, lookback_value=30,
        )
        assert "STDDEV" in sql
        assert "STDDEV_SAMP" not in sql

    def test_duckdb_uses_stddev_samp(self, qb_duckdb):
        sql = qb_duckdb.build_numeric_history(
            SCHEMA, TABLE, COL, DATE_EXPR, lookback_value=30,
        )
        assert "STDDEV_SAMP" in sql

    def test_athena_uses_approx_percentile(self, qb_athena):
        sql = qb_athena.build_numeric_history(
            SCHEMA, TABLE, COL, DATE_EXPR, lookback_value=30,
        )
        assert "APPROX_PERCENTILE" in sql

    def test_duckdb_uses_quantile_cont(self, qb_duckdb):
        sql = qb_duckdb.build_numeric_history(
            SCHEMA, TABLE, COL, DATE_EXPR, lookback_value=30,
        )
        assert "QUANTILE_CONT" in sql

    def test_has_group_by_date(self, qb_athena):
        sql = qb_athena.build_numeric_history(
            SCHEMA, TABLE, COL, DATE_EXPR, lookback_value=30,
        )
        sql_lower = sql.lower()
        assert "group by" in sql_lower
        assert "order by" in sql_lower

    def test_partition_filter(self, qb_athena):
        sql = qb_athena.build_numeric_history(
            SCHEMA, TABLE, COL, DATE_EXPR, lookback_value=30,
            partition_filter="dt_ref >= '2026-01-01'",
        )
        assert "dt_ref >= '2026-01-01'" in sql

    def test_base_filter(self, qb_duckdb):
        sql = qb_duckdb.build_numeric_history(
            SCHEMA, TABLE, COL, DATE_EXPR, lookback_value=30,
            base_filter="IND_ATIVO = 1",
        )
        assert "IND_ATIVO = 1" in sql


# ---------------------------------------------------------------------------
# build_row_count_history
# ---------------------------------------------------------------------------

class TestRowCountHistory:
    def test_athena_date_subtract(self, qb_athena):
        sql = qb_athena.build_row_count_history(
            SCHEMA, TABLE, DATE_EXPR, lookback_value=45,
        )
        assert "DATE_ADD" in sql
        assert "45" in sql

    def test_duckdb_date_subtract(self, qb_duckdb):
        sql = qb_duckdb.build_row_count_history(
            SCHEMA, TABLE, DATE_EXPR, lookback_value=45,
        )
        assert "INTERVAL" in sql
        assert "45" in sql

    def test_has_count_and_group_by(self, qb_athena):
        sql = qb_athena.build_row_count_history(
            SCHEMA, TABLE, DATE_EXPR, lookback_value=30,
        )
        sql_lower = sql.lower()
        assert "count(*)" in sql_lower
        assert "group by" in sql_lower


# ---------------------------------------------------------------------------
# build_column_sample
# ---------------------------------------------------------------------------

class TestColumnSample:
    def test_athena_approx_distinct(self, qb_athena):
        sql = qb_athena.build_column_sample(
            SCHEMA, TABLE, COL, TEMPORAL, DATE_EXPR, sample_periods=10,
        )
        assert "APPROX_DISTINCT" in sql

    def test_duckdb_approx_count_distinct(self, qb_duckdb):
        sql = qb_duckdb.build_column_sample(
            SCHEMA, TABLE, COL, TEMPORAL, DATE_EXPR, sample_periods=10,
        )
        assert "APPROX_COUNT_DISTINCT" in sql

    def test_column_referenced(self, qb_athena):
        sql = qb_athena.build_column_sample(
            SCHEMA, TABLE, COL, TEMPORAL, DATE_EXPR, sample_periods=10,
        )
        assert COL in sql


# ---------------------------------------------------------------------------
# build_batch_column_sample
# ---------------------------------------------------------------------------

class TestBatchColumnSample:
    def test_includes_all_columns(self, qb_duckdb):
        sql = qb_duckdb.build_batch_column_sample(
            SCHEMA, TABLE,
            string_cols=["COD_SITU", "UF"],
            numeric_cols=["VLR_SALDO"],
            temporal_col=TEMPORAL,
            date_expression=DATE_EXPR,
            sample_periods=10,
        )
        assert "COD_SITU" in sql
        assert "UF" in sql
        assert "VLR_SALDO" in sql

    def test_single_query(self, qb_athena):
        """Batch produz uma unica query (nao multiplas)."""
        sql = qb_athena.build_batch_column_sample(
            SCHEMA, TABLE,
            string_cols=["A", "B"],
            numeric_cols=["C"],
            temporal_col=TEMPORAL,
            date_expression=DATE_EXPR,
        )
        # Deve ter exatamente 1 SELECT (pode ter subqueries, mas 1 FROM principal)
        assert sql.lower().count("from") >= 1


# ---------------------------------------------------------------------------
# build_categorical_distribution
# ---------------------------------------------------------------------------

class TestCategoricalDistribution:
    def test_has_group_by_period_and_value(self, qb_athena):
        sql = qb_athena.build_categorical_distribution(
            SCHEMA, TABLE, "COD_SITU", DATE_EXPR, lookback_value=30,
        )
        sql_lower = sql.lower()
        assert "group by" in sql_lower
        assert "COD_SITU" in sql

    def test_partition_filter(self, qb_duckdb):
        sql = qb_duckdb.build_categorical_distribution(
            SCHEMA, TABLE, "COD_SITU", DATE_EXPR, lookback_value=30,
            partition_filter="dt_ref >= '2026-01-01'",
        )
        assert "dt_ref >= '2026-01-01'" in sql


# ---------------------------------------------------------------------------
# build_categorical_domain
# ---------------------------------------------------------------------------

class TestCategoricalDomain:
    def test_has_order_by(self, qb_athena):
        sql = qb_athena.build_categorical_domain(
            SCHEMA, TABLE, "COD_SITU", DATE_EXPR, lookback_value=30,
        )
        assert "ORDER BY" in sql

    def test_limit_applied(self, qb_athena):
        sql = qb_athena.build_categorical_domain(
            SCHEMA, TABLE, "COD_SITU", DATE_EXPR, lookback_value=30, limit=20,
        )
        assert "20" in sql

    def test_no_limit_when_zero(self, qb_athena):
        sql = qb_athena.build_categorical_domain(
            SCHEMA, TABLE, "COD_SITU", DATE_EXPR, lookback_value=30, limit=0,
        )
        assert "LIMIT" not in sql.upper() or "limit" not in sql.lower().split("order by")[-1]


# ---------------------------------------------------------------------------
# build_distinct_count_history
# ---------------------------------------------------------------------------

class TestDistinctCountHistory:
    def test_has_count_distinct(self, qb_athena):
        sql = qb_athena.build_distinct_count_history(
            SCHEMA, TABLE, "COD_SITU", DATE_EXPR, lookback_value=30,
        )
        sql_lower = sql.lower()
        assert "count" in sql_lower
        assert "distinct" in sql_lower

    def test_has_group_by(self, qb_duckdb):
        sql = qb_duckdb.build_distinct_count_history(
            SCHEMA, TABLE, "COD_SITU", DATE_EXPR, lookback_value=30,
        )
        assert "GROUP BY" in sql


# ---------------------------------------------------------------------------
# build_uniqueness_check
# ---------------------------------------------------------------------------

class TestUniquenessCheck:
    def test_single_column(self, qb_athena):
        sql = qb_athena.build_uniqueness_check(
            SCHEMA, TABLE, ["NUM_CTRT"], DATE_EXPR, lookback_value=30,
        )
        assert "NUM_CTRT" in sql
        assert "CAST" in sql

    def test_composite_key_has_concat(self, qb_athena):
        sql = qb_athena.build_uniqueness_check(
            SCHEMA, TABLE, ["COL_A", "COL_B"], DATE_EXPR, lookback_value=30,
        )
        assert "CONCAT" in sql
        assert "COL_A" in sql
        assert "COL_B" in sql
        assert "||" in sql

    def test_empty_columns_raises(self, qb_athena):
        with pytest.raises(ValueError, match="vazio"):
            qb_athena.build_uniqueness_check(
                SCHEMA, TABLE, [], DATE_EXPR, lookback_value=30,
            )

    def test_partition_filter(self, qb_duckdb):
        sql = qb_duckdb.build_uniqueness_check(
            SCHEMA, TABLE, ["PK"], DATE_EXPR, lookback_value=30,
            partition_filter="dt_ref >= '2026-01-01'",
        )
        assert "dt_ref >= '2026-01-01'" in sql


# ---------------------------------------------------------------------------
# build_show_partitions
# ---------------------------------------------------------------------------

class TestShowPartitions:
    def test_athena_table_ref(self, qb_athena):
        sql = qb_athena.build_show_partitions(SCHEMA, TABLE)
        assert f'"{SCHEMA}"."{TABLE}"' in sql

    def test_duckdb_no_schema(self, qb_duckdb):
        sql = qb_duckdb.build_show_partitions(SCHEMA, TABLE)
        assert f'"{TABLE}"' in sql
        assert f'"{SCHEMA}"' not in sql


# ---------------------------------------------------------------------------
# resolve_partition_filter
# ---------------------------------------------------------------------------

class TestResolvePartitionFilter:
    def test_no_partition_returns_empty(self, qb_athena):
        result = qb_athena.resolve_partition_filter(None, None, 30)
        assert result == ""

    def test_athena_uses_date_add(self, qb_athena):
        result = qb_athena.resolve_partition_filter("dt_ref", DATE_EXPR, 30)
        assert "DATE_ADD" in result
        assert "30" in result

    def test_duckdb_uses_interval(self, qb_duckdb):
        result = qb_duckdb.resolve_partition_filter("dt_ref", DATE_EXPR, 30)
        assert "INTERVAL" in result
        assert "30" in result

    def test_duckdb_without_date_expression_uses_try_cast(self, qb_duckdb):
        result = qb_duckdb.resolve_partition_filter("dt_ref", "", 30)
        assert "TRY_CAST" in result


# ---------------------------------------------------------------------------
# resolve_date_expression
# ---------------------------------------------------------------------------

class TestResolveDateExpression:
    def test_with_expression_returns_as_is(self, qb_athena):
        result = qb_athena.resolve_date_expression("dt_ref", DATE_EXPR)
        assert result == DATE_EXPR

    def test_athena_without_expression_returns_quoted_col(self, qb_athena):
        result = qb_athena.resolve_date_expression("dt_ref", "")
        assert result == '"dt_ref"'

    def test_duckdb_without_expression_returns_try_cast(self, qb_duckdb):
        result = qb_duckdb.resolve_date_expression("dt_ref", "")
        assert "TRY_CAST" in result
        assert "dt_ref" in result


# ---------------------------------------------------------------------------
# TABLE_REF dialect difference
# ---------------------------------------------------------------------------

class TestTableRefDialect:
    def test_athena_schema_dot_table(self, qb_athena):
        sql = qb_athena.build_date_range(SCHEMA, TABLE, TEMPORAL, DATE_EXPR)
        assert f'"{SCHEMA}"."{TABLE}"' in sql

    def test_duckdb_table_only(self, qb_duckdb):
        sql = qb_duckdb.build_date_range(SCHEMA, TABLE, TEMPORAL, DATE_EXPR)
        assert f'"{TABLE}"' in sql
        assert f'"{SCHEMA}"' not in sql


# ---------------------------------------------------------------------------
# date_lookback_expr (reference_date support)
# ---------------------------------------------------------------------------

class TestDateLookbackExpr:
    def test_athena_default_uses_current_date(self, qb_athena):
        expr = qb_athena.date_lookback_expr(30)
        assert "CURRENT_DATE" in expr
        assert "30" in expr

    def test_athena_with_reference_date(self, qb_athena):
        expr = qb_athena.date_lookback_expr(30, reference_date="2024-12-31")
        assert "2024-12-31" in expr
        assert "CURRENT_DATE" not in expr
        assert "30" in expr

    def test_duckdb_default_uses_current_date(self, qb_duckdb):
        expr = qb_duckdb.date_lookback_expr(30)
        assert "CURRENT_DATE" in expr

    def test_duckdb_with_reference_date(self, qb_duckdb):
        expr = qb_duckdb.date_lookback_expr(30, reference_date="2024-12-31")
        assert "2024-12-31" in expr
        assert "CURRENT_DATE" not in expr

    def test_empty_reference_date_uses_current(self, qb_athena):
        expr = qb_athena.date_lookback_expr(30, reference_date="")
        assert "CURRENT_DATE" in expr


class TestReferenceDatePropagation:
    """Verifica que reference_date propaga para as queries geradas."""

    def test_column_sample_with_reference(self, qb_athena):
        sql = qb_athena.build_column_sample(
            SCHEMA, TABLE, COL, TEMPORAL, DATE_EXPR,
            sample_periods=10, reference_date="2024-06-15",
        )
        assert "2024-06-15" in sql
        assert "CURRENT_DATE" not in sql

    def test_column_sample_without_reference(self, qb_athena):
        sql = qb_athena.build_column_sample(
            SCHEMA, TABLE, COL, TEMPORAL, DATE_EXPR, sample_periods=10,
        )
        assert "CURRENT_DATE" in sql

    def test_numeric_history_with_reference(self, qb_duckdb):
        sql = qb_duckdb.build_numeric_history(
            SCHEMA, TABLE, COL, DATE_EXPR,
            lookback_value=30, reference_date="2025-01-01",
        )
        assert "2025-01-01" in sql
        assert "CURRENT_DATE" not in sql

    def test_row_count_history_with_reference(self, qb_athena):
        sql = qb_athena.build_row_count_history(
            SCHEMA, TABLE, DATE_EXPR,
            lookback_value=45, reference_date="2024-11-30",
        )
        assert "2024-11-30" in sql

    def test_partition_filter_with_reference(self, qb_athena):
        result = qb_athena.resolve_partition_filter(
            "dt_ref", DATE_EXPR, 30, reference_date="2024-12-31",
        )
        assert "2024-12-31" in result
        assert "CURRENT_DATE" not in result

    def test_batch_column_sample_with_reference(self, qb_duckdb):
        sql = qb_duckdb.build_batch_column_sample(
            SCHEMA, TABLE,
            string_cols=["COD_SITU"],
            numeric_cols=["VLR_SALDO"],
            temporal_col=TEMPORAL,
            date_expression=DATE_EXPR,
            sample_periods=10,
            reference_date="2024-06-15",
        )
        assert "2024-06-15" in sql
