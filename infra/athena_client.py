"""
Client para Amazon Athena via PyAthena.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional

import pandas as pd

from config import AppConfig
from infra.query_logger import QueryLogger, QueryLogEntry
from infra.sql_dialect import SQLDialect

logger = logging.getLogger(__name__)


class AthenaClient:
    """Client para queries no Amazon Athena.

    Uso:
        client = AthenaClient(config)
        df = client.execute_df("SELECT COUNT(*) FROM tabela")
    """

    def __init__(self, config: AppConfig, query_logger: Optional[QueryLogger] = None):
        self.config = config
        self.logger = query_logger or QueryLogger()
        self.dialect = SQLDialect.ATHENA
        self._conn = None
        self._query_timeout: int = config.athena.query_timeout_seconds
        self._init_connection()

    def _init_connection(self):
        """Inicializa conexao PyAthena."""
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

    def health_check(self) -> bool:
        """Testa a conexao com uma query trivial.

        Returns:
            True se a conexao esta funcional.

        Raises:
            Exception com mensagem amigavel se a conexao falhar.
        """
        try:
            self.execute("SELECT 1 AS health", query_name="health_check")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "expired" in error_msg or "invalid" in error_msg or "token" in error_msg:
                profile = self.config.athena.aws_profile
                raise ConnectionError(
                    f"Credenciais AWS expiradas ou invalidas. "
                    f"Execute no terminal: aws sso login --profile {profile}"
                ) from e
            elif "access denied" in error_msg or "not authorized" in error_msg:
                raise ConnectionError(
                    "Sem permissao para acessar o Athena. "
                    "Verifique as permissoes do seu profile AWS."
                ) from e
            elif "s3" in error_msg and ("bucket" in error_msg or "output" in error_msg):
                raise ConnectionError(
                    "Bucket S3 de output nao encontrado ou sem acesso. "
                    "Verifique GDQ_ATHENA_S3_OUTPUT no .env"
                ) from e
            elif "workgroup" in error_msg:
                raise ConnectionError(
                    "Workgroup do Athena nao encontrado. "
                    "Verifique GDQ_ATHENA_WORKGROUP no .env"
                ) from e
            else:
                raise ConnectionError(
                    f"Falha ao conectar no Athena: {type(e).__name__}: {e}"
                ) from e

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
        bytes_scanned: Optional[int] = None
        cache_hit = False

        try:
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
        """Execute query on Athena with timeout enforcement.

        Args:
            sql: SQL statement to execute.

        Returns:
            Tuple of (DataFrame, bytes_scanned, cache_hit).

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
            query_name: Identificador da query para logging.
            dataset: schema.table para logging.
            column: Coluna analisada (vazio para queries de tabela).

        Returns:
            Lista de dicts, um por linha retornada.
        """
        start = time.time()
        rows = 0
        exception_type = None
        bytes_scanned: Optional[int] = None
        cache_hit = False

        try:
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
        """Verifica se a tabela existe.

        Returns:
            True se a tabela existe e e acessivel.

        Raises:
            ConnectionError: Se o erro for de autenticacao/permissao (nao de tabela).
        """
        try:
            self.execute(
                f'SELECT 1 FROM "{schema}"."{table}" LIMIT 1',
                query_name="table_exists",
                dataset=f"{schema}.{table}",
            )
            return True
        except Exception as e:
            error_msg = str(e).lower()
            # Erros de autenticacao/permissao devem ser propagados, nao mascarados
            auth_keywords = [
                "expired", "invalid", "token", "access denied",
                "not authorized", "credentials", "security token",
                "unrecognizedclient",
            ]
            if any(kw in error_msg for kw in auth_keywords):
                profile = self.config.athena.aws_profile
                raise ConnectionError(
                    f"Erro de autenticacao AWS ao acessar '{schema}.{table}'. "
                    f"Suas credenciais podem estar expiradas. "
                    f"Execute: aws sso login --profile {profile}"
                ) from e
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
