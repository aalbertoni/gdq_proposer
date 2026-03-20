"""Shared test fixtures.

Provides DuckDB-backed test client that mimics AthenaClient interface,
used by service tests that need a SQL backend without real Athena.

Also provides shared QueryBuilder fixtures for both dialects.
"""

import os

import duckdb
import pandas as pd
import pytest

from infra.query_builder import QueryBuilder
from infra.query_logger import QueryLogger
from infra.sql_dialect import SQLDialect


# ---------------------------------------------------------------------------
# QueryBuilder fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def qb_athena() -> QueryBuilder:
    """QueryBuilder configurado para dialeto Athena."""
    return QueryBuilder(dialect=SQLDialect.ATHENA)


@pytest.fixture
def qb_duckdb() -> QueryBuilder:
    """QueryBuilder configurado para dialeto DuckDB."""
    return QueryBuilder(dialect=SQLDialect.DUCKDB)


class DuckDBTestClient:
    """DuckDB-backed client with the same interface as AthenaClient.

    Used in tests to avoid depending on real Athena.
    Supports execute_df(), execute(), table_exists(), get_columns(),
    get_columns_with_partitions().
    """

    def __init__(self):
        self.conn = duckdb.connect(":memory:")
        self.dialect = SQLDialect.DUCKDB
        self.logger = QueryLogger()
        self._tables: dict[str, str] = {}  # schema.table -> table_name

    def load_table(self, schema: str, table: str, data_path: str):
        """Load parquet/csv into DuckDB as a table."""
        from pathlib import Path
        path = Path(data_path)
        if path.suffix == ".parquet":
            self.conn.execute(
                f'CREATE OR REPLACE TABLE "{table}" AS '
                f"SELECT * FROM read_parquet('{path}')"
            )
        elif path.suffix == ".csv":
            self.conn.execute(
                f'CREATE OR REPLACE TABLE "{table}" AS '
                f"SELECT * FROM read_csv_auto('{path}')"
            )
        self._tables[f"{schema}.{table}"] = table

    def load_df(self, schema: str, table: str, df: pd.DataFrame):
        """Load a DataFrame directly into DuckDB."""
        self.conn.execute(
            f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM df'
        )
        self._tables[f"{schema}.{table}"] = table

    def execute_df(self, sql: str, **kwargs) -> pd.DataFrame:
        """Execute query and return DataFrame."""
        return self.conn.execute(sql).fetchdf()

    def execute(self, sql: str, **kwargs) -> list[dict]:
        """Execute query and return list of dicts."""
        result = self.conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def table_exists(self, schema: str, table: str) -> bool:
        """Check if table exists in DuckDB."""
        table_name = self._tables.get(f"{schema}.{table}", table)
        try:
            self.conn.execute(f'SELECT 1 FROM "{table_name}" LIMIT 1')
            return True
        except duckdb.CatalogException:
            return False

    def get_columns(self, schema: str, table: str) -> list[dict]:
        """Return columns and types."""
        table_name = self._tables.get(f"{schema}.{table}", table)
        result = self.conn.execute(
            f"SELECT column_name, data_type "
            f"FROM information_schema.columns "
            f"WHERE table_name = '{table_name}'"
        ).fetchall()
        return [{"name": row[0], "type": row[1]} for row in result]

    def get_columns_with_partitions(self, schema: str, table: str) -> tuple[list[dict], list[str]]:
        """Return columns and empty partition list (DuckDB has no partitions)."""
        return self.get_columns(schema, table), []
