"""
Backend mock que usa DuckDB para simular Athena localmente.
Carrega dados sintéticos e permite executar queries SQL reais.
"""

import duckdb
import pandas as pd
from pathlib import Path


class MockAthenaBackend:
    """Simula Athena usando DuckDB + dados locais.

    Uso:
        backend = MockAthenaBackend()
        backend.load_table("db_credito", "tb_operacoes_credito", "mock_data/tb_operacoes_credito.parquet")
        results = backend.execute("SELECT COUNT(*) FROM tb_operacoes_credito")
    """

    def __init__(self, database: str = ":memory:"):
        self.conn = duckdb.connect(database)
        self._tables: dict[str, str] = {}  # schema.table → table_name

    def load_table(
        self,
        schema: str,
        table: str,
        data_path: str,
    ):
        """Carrega arquivo (parquet/csv) como tabela no DuckDB.

        No DuckDB não usamos schema separado, então mapeamos
        'schema.table' → 'table' internamente.
        """
        path = Path(data_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {data_path}")

        full_name = f"{schema}.{table}"

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
        else:
            raise ValueError(f"Formato não suportado: {path.suffix}")

        self._tables[full_name] = table
        count = self.conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        print(f"Loaded {full_name} -> {table} ({count} rows)")

    def execute(self, sql: str) -> list[dict]:
        """Executa query e retorna lista de dicts."""
        result = self.conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def execute_df(self, sql: str) -> pd.DataFrame:
        """Executa query e retorna DataFrame."""
        return self.conn.execute(sql).fetchdf()

    def get_columns(self, table: str) -> list[dict]:
        """Retorna colunas e tipos (simula DESCRIBE)."""
        result = self.conn.execute(
            f"SELECT column_name, data_type "
            f"FROM information_schema.columns "
            f"WHERE table_name = '{table}'"
        ).fetchall()
        return [{"name": row[0], "type": row[1]} for row in result]

    def table_exists(self, table: str) -> bool:
        """Verifica se a tabela existe."""
        try:
            self.conn.execute(f'SELECT 1 FROM "{table}" LIMIT 1')
            return True
        except duckdb.CatalogException:
            return False

    def close(self):
        """Fecha a conexão DuckDB."""
        self.conn.close()
