"""
Client unificado que funciona com DuckDB (local) ou Athena real (dev/prod).
A interface é idêntica — só muda o backend.
"""

import os
import time
from typing import Optional

import pandas as pd

from config import AppConfig, AthenaMode
from infra.mock_athena import MockAthenaBackend
from infra.query_logger import QueryLogger, QueryLogEntry
from infra.sql_dialect import SQLDialect


class AthenaClient:
    """Client unificado para queries.

    Uso:
        client = AthenaClient(config)
        df = client.execute_df("SELECT COUNT(*) FROM tabela")
    """

    def __init__(self, config: AppConfig, logger: Optional[QueryLogger] = None):
        self.config = config
        self.logger = logger or QueryLogger()
        self._backend: Optional[MockAthenaBackend] = None
        self._conn = None  # pyathena connection (modo real)

        if config.athena.mode == AthenaMode.MOCK:
            self.dialect = SQLDialect.DUCKDB
            self._init_mock()
        else:
            self.dialect = SQLDialect.ATHENA
            self._init_real()

    def _init_mock(self):
        """Inicializa backend DuckDB com dados mock."""
        self._backend = MockAthenaBackend()
        mock_dir = self.config.athena.mock_data_dir
        if not os.path.isdir(mock_dir):
            return
        for f in os.listdir(mock_dir):
            if f.endswith((".parquet", ".csv")):
                table_name = f.rsplit(".", 1)[0]
                self._backend.load_table(
                    schema="mock_db",
                    table=table_name,
                    data_path=os.path.join(mock_dir, f),
                )

    def _init_real(self):
        """Inicializa conexão PyAthena."""
        from pyathena import connect
        from pyathena.pandas.cursor import PandasCursor

        connect_kwargs = {
            "region_name": self.config.athena.region,
            "work_group": self.config.athena.workgroup,
            "s3_staging_dir": self.config.athena.s3_output,
            "cursor_class": PandasCursor,
        }

        if self.config.athena.aws_profile:
            import boto3
            session = boto3.Session(profile_name=self.config.athena.aws_profile)
            connect_kwargs["boto3_session"] = session

        self._conn = connect(**connect_kwargs)

    def execute_df(
        self,
        sql: str,
        query_name: str = "unnamed",
        dataset: str = "",
        column: str = "",
    ) -> pd.DataFrame:
        """Executa query e retorna DataFrame. Loga métricas."""
        start = time.time()
        rows = 0
        exception_type = None

        try:
            if self.config.athena.mode == AthenaMode.MOCK:
                df = self._backend.execute_df(sql)
            else:
                cursor = self._conn.cursor()
                cursor.execute(sql)
                df = cursor.as_pandas()

            rows = len(df)
            return df

        except Exception as e:
            exception_type = type(e).__name__
            raise

        finally:
            elapsed = int((time.time() - start) * 1000)
            self.logger.log_query(QueryLogEntry(
                query_name=query_name,
                dataset=dataset,
                column=column,
                elapsed_ms=elapsed,
                cache_hit=False,
                rows_returned=rows,
                exception_type=exception_type,
            ))

    def execute(self, sql: str) -> list[dict]:
        """Executa query e retorna lista de dicts."""
        if self.config.athena.mode == AthenaMode.MOCK:
            return self._backend.execute(sql)
        else:
            cursor = self._conn.cursor()
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def table_exists(self, schema: str, table: str) -> bool:
        """Verifica se a tabela existe."""
        if self.config.athena.mode == AthenaMode.MOCK:
            return self._backend.table_exists(table)
        else:
            try:
                self.execute(f'SELECT 1 FROM "{schema}"."{table}" LIMIT 1')
                return True
            except Exception:
                return False

    def get_columns(self, schema: str, table: str) -> list[dict]:
        """Retorna colunas e tipos."""
        if self.config.athena.mode == AthenaMode.MOCK:
            return self._backend.get_columns(table)
        else:
            df = self.execute_df(
                f'DESCRIBE "{schema}"."{table}"',
                query_name="describe_table",
                dataset=f"{schema}.{table}",
            )
            return [
                {"name": row["col_name"], "type": row["data_type"]}
                for _, row in df.iterrows()
            ]
