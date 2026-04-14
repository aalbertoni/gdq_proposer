"""Testes de integração DuckDB para amostragem com TABLESAMPLE BERNOULLI.

Valida:
- Fatia 0: Sintaxe TABLESAMPLE funciona em DuckDB
- Fatia 2: Templates SQL com tablesample_clause
- Fatia 3: Roteamento — templates não-amostrados nunca contêm TABLESAMPLE

Marcador: @pytest.mark.integration (usa DuckDB).
"""

import pytest
import duckdb

from infra.query_builder import QueryBuilder
from infra.sql_dialect import SQLDialect

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fatia 0 — Validação de sintaxe DuckDB
# ---------------------------------------------------------------------------

class TestTableSampleSyntaxDuckDB:
    """Valida que TABLESAMPLE BERNOULLI funciona em DuckDB."""

    @pytest.fixture
    def conn(self):
        """Conexão DuckDB in-memory com tabela de teste."""
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE test_data AS
            SELECT
                i as id,
                random() as val,
                CASE WHEN i % 3 = 0 THEN 'A'
                     WHEN i % 3 = 1 THEN 'B'
                     ELSE 'C' END as cat,
                CURRENT_DATE - INTERVAL (i % 30) DAY as dt
            FROM range(10000) t(i)
        """)
        yield conn
        conn.close()

    def test_basic_tablesample(self, conn):
        """FROM table TABLESAMPLE BERNOULLI(10 PERCENT) funciona."""
        count = conn.execute(
            "SELECT COUNT(*) FROM test_data TABLESAMPLE BERNOULLI(10 PERCENT)"
        ).fetchone()[0]
        assert 0 < count < 10000

    def test_tablesample_with_where(self, conn):
        """TABLESAMPLE + WHERE funciona junto."""
        count = conn.execute(
            "SELECT COUNT(*) FROM test_data TABLESAMPLE BERNOULLI(50 PERCENT) "
            "WHERE dt >= CURRENT_DATE - INTERVAL 15 DAY"
        ).fetchone()[0]
        total = conn.execute(
            "SELECT COUNT(*) FROM test_data WHERE dt >= CURRENT_DATE - INTERVAL 15 DAY"
        ).fetchone()[0]
        assert count < total

    def test_avg_estimator(self, conn):
        """AVG com sample é estimador não-viesado (±20%)."""
        avg_full = conn.execute("SELECT AVG(val) FROM test_data").fetchone()[0]
        avg_sample = conn.execute(
            "SELECT AVG(val) FROM test_data TABLESAMPLE BERNOULLI(50 PERCENT)"
        ).fetchone()[0]
        diff_pct = abs(avg_full - avg_sample) / max(avg_full, 1e-10) * 100
        assert diff_pct < 20

    def test_returns_fewer_rows(self, conn):
        """Sample retorna subset."""
        full = conn.execute("SELECT COUNT(*) FROM test_data").fetchone()[0]
        sample = conn.execute(
            "SELECT COUNT(*) FROM test_data TABLESAMPLE BERNOULLI(1 PERCENT)"
        ).fetchone()[0]
        assert sample < full


# ---------------------------------------------------------------------------
# Fatia 2 — Templates com tablesample_clause
# ---------------------------------------------------------------------------

class TestQueryBuilderSampling:
    """Testa QueryBuilder com sample_pct."""

    @pytest.fixture
    def qb(self):
        return QueryBuilder(dialect=SQLDialect.DUCKDB)

    def test_numeric_history_without_sample(self, qb):
        """Sem sample_pct → SQL não contém TABLESAMPLE."""
        sql = qb.build_numeric_history(
            schema="test", table="data", col="val",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
        )
        assert "TABLESAMPLE" not in sql

    def test_numeric_history_with_sample(self, qb):
        """Com sample_pct → SQL contém TABLESAMPLE BERNOULLI."""
        sql = qb.build_numeric_history(
            schema="test", table="data", col="val",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
            sample_pct=10.0,
        )
        assert "TABLESAMPLE BERNOULLI(10.0 PERCENT)" in sql

    def test_categorical_distribution_without_sample(self, qb):
        sql = qb.build_categorical_distribution(
            schema="test", table="data", col="cat",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
        )
        assert "TABLESAMPLE" not in sql

    def test_categorical_distribution_with_sample(self, qb):
        sql = qb.build_categorical_distribution(
            schema="test", table="data", col="cat",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
            sample_pct=5.0,
        )
        assert "TABLESAMPLE BERNOULLI(5.0 PERCENT)" in sql

    def test_batch_column_sample_without_sample(self, qb):
        sql = qb.build_batch_column_sample(
            schema="test", table="data",
            string_cols=["cat"], numeric_cols=["val"],
            temporal_col="dt",
            date_expression='CAST("dt" AS DATE)',
            sample_periods=10,
        )
        assert "TABLESAMPLE" not in sql

    def test_batch_column_sample_with_sample(self, qb):
        sql = qb.build_batch_column_sample(
            schema="test", table="data",
            string_cols=["cat"], numeric_cols=["val"],
            temporal_col="dt",
            date_expression='CAST("dt" AS DATE)',
            sample_periods=10,
            sample_pct=0.5,
        )
        assert "TABLESAMPLE BERNOULLI(0.5 PERCENT)" in sql

    def test_column_sample_without_sample(self, qb):
        sql = qb.build_column_sample(
            schema="test", table="data", col="val",
            temporal_col="dt",
            date_expression='CAST("dt" AS DATE)',
            sample_periods=10,
        )
        assert "TABLESAMPLE" not in sql

    def test_column_sample_with_sample(self, qb):
        sql = qb.build_column_sample(
            schema="test", table="data", col="val",
            temporal_col="dt",
            date_expression='CAST("dt" AS DATE)',
            sample_periods=10,
            sample_pct=1.0,
        )
        assert "TABLESAMPLE BERNOULLI(1.0 PERCENT)" in sql

    def test_invalid_sample_pct_zero(self, qb):
        """sample_pct=0 → ValueError."""
        with pytest.raises(ValueError, match="sample_pct"):
            qb.build_numeric_history(
                schema="test", table="data", col="val",
                date_expression='CAST("dt" AS DATE)',
                lookback_value=30,
                sample_pct=0,
            )

    def test_invalid_sample_pct_negative(self, qb):
        with pytest.raises(ValueError, match="sample_pct"):
            qb.build_numeric_history(
                schema="test", table="data", col="val",
                date_expression='CAST("dt" AS DATE)',
                lookback_value=30,
                sample_pct=-5,
            )

    def test_invalid_sample_pct_over_100(self, qb):
        with pytest.raises(ValueError, match="sample_pct"):
            qb.build_numeric_history(
                schema="test", table="data", col="val",
                date_expression='CAST("dt" AS DATE)',
                lookback_value=30,
                sample_pct=101,
            )


# ---------------------------------------------------------------------------
# Fatia 2 — Athena dialect
# ---------------------------------------------------------------------------

class TestQueryBuilderSamplingAthena:
    """Testa que Athena dialect gera TABLESAMPLE sem PERCENT."""

    @pytest.fixture
    def qb(self):
        return QueryBuilder(dialect=SQLDialect.ATHENA)

    def test_athena_tablesample_no_percent_keyword(self, qb):
        """Athena usa TABLESAMPLE BERNOULLI(pct) sem PERCENT."""
        sql = qb.build_numeric_history(
            schema="myschema", table="mytable", col="val",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
            sample_pct=10.0,
        )
        assert "TABLESAMPLE BERNOULLI(10.0)" in sql
        # Athena: sem PERCENT keyword na cláusula TABLESAMPLE
        # (APPROX_PERCENTILE contém PERCENT mas é parte do nome da função)
        assert "BERNOULLI(10.0 PERCENT)" not in sql


# ---------------------------------------------------------------------------
# Fatia 3 — Templates NÃO-amostrados (contratos)
# ---------------------------------------------------------------------------

class TestNonSampledTemplates:
    """Templates que NÃO devem aceitar TABLESAMPLE."""

    @pytest.fixture
    def qb(self):
        return QueryBuilder(dialect=SQLDialect.DUCKDB)

    def test_row_count_history_no_sample(self, qb):
        """row_count_history NÃO tem parâmetro sample_pct."""
        sql = qb.build_row_count_history(
            schema="test", table="data",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
        )
        assert "TABLESAMPLE" not in sql

    def test_distinct_count_history_no_sample(self, qb):
        """distinct_count_history NÃO tem parâmetro sample_pct."""
        sql = qb.build_distinct_count_history(
            schema="test", table="data", col="cat",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
        )
        assert "TABLESAMPLE" not in sql

    def test_categorical_domain_no_sample(self, qb):
        """categorical_domain NÃO tem parâmetro sample_pct."""
        sql = qb.build_categorical_domain(
            schema="test", table="data", col="cat",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
        )
        assert "TABLESAMPLE" not in sql

    def test_uniqueness_check_no_sample(self, qb):
        """uniqueness_check NÃO tem parâmetro sample_pct."""
        sql = qb.build_uniqueness_check(
            schema="test", table="data",
            key_columns=["id"],
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
        )
        assert "TABLESAMPLE" not in sql

    def test_date_range_no_sample(self, qb):
        sql = qb.build_date_range(
            schema="test", table="data",
            temporal_col="dt",
        )
        assert "TABLESAMPLE" not in sql

    def test_volume_by_period_no_sample(self, qb):
        sql = qb.build_volume_by_period(
            schema="test", table="data",
            temporal_col="dt",
        )
        assert "TABLESAMPLE" not in sql


# ---------------------------------------------------------------------------
# Fatia 2+3 — Execução end-to-end DuckDB com sample
# ---------------------------------------------------------------------------

class TestSamplingExecutionDuckDB:
    """Executa queries amostradas em DuckDB e verifica resultados."""

    @pytest.fixture
    def conn_and_qb(self):
        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE test_data AS
            SELECT
                i as id,
                (i % 100) * 1.5 as val,
                CASE WHEN i % 3 = 0 THEN 'A'
                     WHEN i % 3 = 1 THEN 'B'
                     ELSE 'C' END as cat,
                CURRENT_DATE - INTERVAL (i % 30) DAY as dt
            FROM range(100000) t(i)
        """)
        qb = QueryBuilder(dialect=SQLDialect.DUCKDB)
        yield conn, qb
        conn.close()

    def test_numeric_history_sampled_returns_fewer_rows(self, conn_and_qb):
        """numeric_history com sample retorna dados por período."""
        conn, qb = conn_and_qb
        sql_full = qb.build_numeric_history(
            schema="test", table="test_data", col="val",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
        )
        sql_sampled = qb.build_numeric_history(
            schema="test", table="test_data", col="val",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
            sample_pct=10.0,
        )
        df_full = conn.execute(sql_full).fetchdf()
        df_sampled = conn.execute(sql_sampled).fetchdf()

        # Ambos devem ter períodos (GROUP BY date)
        assert len(df_full) > 0
        assert len(df_sampled) > 0
        # Total count por período deve ser menor na amostra
        assert df_sampled["total_count"].sum() < df_full["total_count"].sum()

    def test_categorical_distribution_sampled(self, conn_and_qb):
        """categorical_distribution com sample preserva categorias."""
        conn, qb = conn_and_qb
        sql = qb.build_categorical_distribution(
            schema="test", table="test_data", col="cat",
            date_expression='CAST("dt" AS DATE)',
            lookback_value=30,
            sample_pct=50.0,
        )
        df = conn.execute(sql).fetchdf()
        assert len(df) > 0
        categories = df["category_value"].unique()
        # Com 50% de 100k rows, todas 3 categorias devem estar presentes
        assert set(categories) == {"A", "B", "C"}
