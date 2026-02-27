"""
Client unificado que funciona com DuckDB (local) ou Athena real (dev/prod).
A interface é idêntica — só muda o backend.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional

import pandas as pd

from config import AppConfig, AthenaMode
from infra.mock_athena import MockAthenaBackend
from infra.query_logger import QueryLogger, QueryLogEntry
from infra.sql_dialect import SQLDialect

logger = logging.getLogger(__name__)


class AthenaClient:
    """Client unificado para queries.

    Uso:
        client = AthenaClient(config)
        df = client.execute_df("SELECT COUNT(*) FROM tabela")
    """

    def __init__(self, config: AppConfig, query_logger: Optional[QueryLogger] = None):
        self.config = config
        self.logger = query_logger or QueryLogger()
        self._backend: Optional[MockAthenaBackend] = None
        self._conn = None  # pyathena connection (modo real)
        self._query_timeout: int = config.athena.query_timeout_seconds

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
            "kill_on_interrupt": True,
            "result_reuse_enable": True,
        }

        if self.config.athena.aws_profile:
            import boto3
            os.environ.setdefault("AWS_PROFILE", self.config.athena.aws_profile)
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
        """Executa query e retorna DataFrame. Loga metricas."""
        start = time.time()
        rows = 0
        exception_type = None
        bytes_scanned: Optional[int] = 0 if self.config.athena.mode == AthenaMode.MOCK else None
        cache_hit = False

        try:
            if self.config.athena.mode == AthenaMode.MOCK:
                df = self._backend.execute_df(sql)
            else:
                df, bytes_scanned, cache_hit = self._execute_real_df(sql)

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
                cache_hit=cache_hit,
                rows_returned=rows,
                bytes_scanned=bytes_scanned,
                exception_type=exception_type,
            ))

    def _execute_real_df(self, sql: str) -> tuple[pd.DataFrame, Optional[int], bool]:
        """Execute query on real Athena with timeout enforcement.

        Uses a thread pool to run the query and enforces the configured
        ``query_timeout_seconds``.  On timeout, attempts to cancel the
        running Athena query to avoid unnecessary cost.

        Args:
            sql: SQL statement to execute.

        Returns:
            Tuple of (DataFrame, bytes_scanned, cache_hit) where:
            - bytes_scanned: Number of bytes scanned by Athena (None if unavailable).
            - cache_hit: True if Athena reused a previous result (result_reuse_enable).

        Raises:
            TimeoutError: If the query exceeds ``query_timeout_seconds``.
        """
        cursor = self._conn.cursor()

        def _run():
            cursor.execute(sql)
            df = cursor.as_pandas()
            bytes_scanned = getattr(cursor, "data_scanned_in_bytes", None)
            cache_hit = bool(getattr(cursor, "reused_previous_result", False))
            return df, bytes_scanned, cache_hit

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run)
            try:
                return future.result(timeout=self._query_timeout)
            except FuturesTimeoutError:
                # Attempt to cancel the Athena query to save cost
                try:
                    cursor.cancel()
                    logger.warning(
                        "Query cancelled after %ds timeout", self._query_timeout,
                    )
                except Exception:
                    logger.warning(
                        "Query timed out after %ds but cancel failed",
                        self._query_timeout,
                    )
                raise TimeoutError(
                    f"Query exceeded timeout of {self._query_timeout}s. "
                    f"Consider reducing the lookback period or simplifying the query."
                )

    def execute(
        self,
        sql: str,
        query_name: str = "unnamed",
        dataset: str = "",
        column: str = "",
    ) -> list[dict]:
        """Executa query e retorna lista de dicts. Loga metricas.

        Args:
            sql: SQL statement to execute.
            query_name: Identificador da query para logging (ex: "table_exists").
            dataset: schema.table para logging.
            column: Coluna analisada (vazio para queries de tabela).

        Returns:
            Lista de dicts, um por linha retornada.
        """
        start = time.time()
        rows = 0
        exception_type = None
        bytes_scanned: Optional[int] = 0 if self.config.athena.mode == AthenaMode.MOCK else None
        cache_hit = False

        try:
            if self.config.athena.mode == AthenaMode.MOCK:
                result = self._backend.execute(sql)
            else:
                cursor = self._conn.cursor()

                def _run():
                    cursor.execute(sql)
                    return cursor

                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(_run)
                    try:
                        cursor = future.result(timeout=self._query_timeout)
                    except FuturesTimeoutError:
                        try:
                            cursor.cancel()
                        except Exception:
                            pass
                        raise TimeoutError(
                            f"Query exceeded timeout of {self._query_timeout}s."
                        )

                bytes_scanned = getattr(cursor, "data_scanned_in_bytes", None)
                cache_hit = bool(getattr(cursor, "reused_previous_result", False))
                columns = [desc[0] for desc in cursor.description]
                result = [dict(zip(columns, row)) for row in cursor.fetchall()]

            rows = len(result)
            return result

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
                cache_hit=cache_hit,
                rows_returned=rows,
                bytes_scanned=bytes_scanned,
                exception_type=exception_type,
            ))

    def table_exists(self, schema: str, table: str) -> bool:
        """Verifica se a tabela existe."""
        if self.config.athena.mode == AthenaMode.MOCK:
            return self._backend.table_exists(table)
        else:
            try:
                self.execute(
                    f'SELECT 1 FROM "{schema}"."{table}" LIMIT 1',
                    query_name="table_exists",
                    dataset=f"{schema}.{table}",
                )
                return True
            except Exception:
                return False

    def get_columns(self, schema: str, table: str) -> list[dict]:
        """Retorna colunas e tipos (sem metadados de particao)."""
        columns, _ = self.get_columns_with_partitions(schema, table)
        return columns

    def get_columns_with_partitions(
        self, schema: str, table: str,
    ) -> tuple[list[dict], list[str]]:
        """Retorna colunas e nomes das colunas de particao.

        Args:
            schema: Nome do schema/database.
            table: Nome da tabela.

        Returns:
            Tuple de (columns, partition_columns) onde:
            - columns: [{"name": str, "type": str}, ...]
            - partition_columns: ["dt_ref", ...] (vazia se nao particionada)
        """
        if self.config.athena.mode == AthenaMode.MOCK:
            return self._backend.get_columns(table), []

        df = self.execute_df(
            f"DESCRIBE {schema}.{table}",
            query_name="describe_table",
            dataset=f"{schema}.{table}",
        )
        columns = []
        partition_columns = []
        in_partition_section = False

        for _, row in df.iterrows():
            col_name = row.get("col_name")
            data_type = row.get("data_type")
            if not isinstance(col_name, str):
                continue
            col_name = col_name.strip()

            # Detect partition section header
            if col_name == "# Partition Information":
                in_partition_section = True
                continue
            # Skip comment rows
            if col_name.startswith("#") or not col_name:
                continue
            if not isinstance(data_type, str):
                continue
            data_type = data_type.strip()
            if not data_type:
                continue

            if in_partition_section:
                partition_columns.append(col_name)
            else:
                columns.append({"name": col_name, "type": data_type})

        # Add partition cols to column list if not already present
        col_names = {c["name"] for c in columns}
        for pc in partition_columns:
            if pc not in col_names:
                columns.append({"name": pc, "type": "string"})

        return columns, partition_columns
