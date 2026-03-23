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


def _friendly_error_message(e: Exception, profile: str = "") -> str:
    """Converte excecoes AWS/boto em mensagens amigaveis com instrucoes de fix."""
    error_msg = str(e).lower()
    error_type = type(e).__name__.lower()

    # SSL / certificado
    if "ssl" in error_msg or "certificate" in error_msg or "ssl" in error_type:
        return (
            "Erro de SSL ao conectar na AWS. Isso geralmente ocorre em redes corporativas "
            "com proxy que intercepta HTTPS.\n\n"
            "Solucoes:\n"
            "1. Configure o certificado CA no AWS CLI:\n"
            "   Edite ~/.aws/config e adicione no seu profile:\n"
            "   ca_bundle = /caminho/do/certificado.pem\n\n"
            "2. Se o erro for especifico do S3, adicione tambem:\n"
            "   s3 =\n"
            "     addressing_style = path\n\n"
            "Consulte: docs/INSTALL_TROUBLESHOOTING.md secao 'Erro de SSL'"
        )

    # SignatureDoesNotMatch
    if "signaturedoesnotmatch" in error_msg or "signature" in error_msg and "match" in error_msg:
        return (
            "Erro SignatureDoesNotMatch ao acessar S3.\n\n"
            "O app ja usa S3 path-style (addressing_style=path) para mitigar "
            "problemas com proxy corporativo. Se o erro persiste, verifique:\n\n"
            "1. Certificado CA do proxy corporativo:\n"
            "   -> Adicione no ~/.aws/config:\n"
            f"   [profile {profile}]\n"
            "   ca_bundle = C:\\caminho\\do\\certificado-ca.pem\n\n"
            "2. Relogio do computador desincronizado\n"
            "   -> Sincronize a hora do sistema\n\n"
            "3. Credenciais expiradas\n"
            f"   -> Execute: aws sso login --profile {profile}\n\n"
            "4. Proxy alterando headers — verifique HTTP_PROXY/HTTPS_PROXY no .env\n\n"
            "Consulte: docs/INSTALL_TROUBLESHOOTING.md secao 'SignatureDoesNotMatch'"
        )

    # Credenciais expiradas
    if "expired" in error_msg or "token" in error_msg and "invalid" in error_msg:
        return (
            f"Credenciais AWS expiradas ou invalidas. "
            f"Execute no terminal: aws sso login --profile {profile}"
        )

    # UnrecognizedClient (credenciais invalidas de outro tipo)
    if "unrecognizedclient" in error_msg or "invalid" in error_msg and "credential" in error_msg:
        return (
            f"Credenciais AWS nao reconhecidas. "
            f"Verifique se o profile '{profile}' esta configurado corretamente.\n"
            f"Execute: aws configure list --profile {profile}"
        )

    # Access denied
    if "access denied" in error_msg or "not authorized" in error_msg or "accessdenied" in error_msg:
        return (
            "Sem permissao para acessar o Athena. "
            "Verifique as permissoes do seu profile AWS."
        )

    # S3 bucket
    if "nosuchbucket" in error_msg or ("s3" in error_msg and "bucket" in error_msg):
        return (
            "Bucket S3 de output nao encontrado ou sem acesso. "
            "Verifique GDQ_ATHENA_S3_OUTPUT no .env"
        )

    # Workgroup
    if "workgroup" in error_msg:
        return (
            "Workgroup do Athena nao encontrado. "
            "Verifique GDQ_ATHENA_WORKGROUP no .env"
        )

    # Connection refused / timeout de rede
    if "connect" in error_msg and ("timeout" in error_msg or "refused" in error_msg):
        return (
            "Timeout ou conexao recusada ao acessar a AWS. "
            "Verifique sua conexao de rede e configuracao de proxy."
        )

    # Fallback generico
    return f"Falha ao conectar no Athena: {type(e).__name__}: {e}"


class AthenaClient:
    """Client para queries no Amazon Athena.

    Uso:
        client = AthenaClient(config)
        df = client.execute_df("SELECT COUNT(*) FROM tabela")
    """

    # Timeout tiers based on estimated table volume.
    # Adapts the query timeout so large tables don't fail on the default 120s.
    _TIMEOUT_TIERS: list[tuple[int, int]] = [
        (500_000_000, 600),   # > 500M rows: 10 min
        (100_000_000, 360),   # > 100M rows: 6 min
        (10_000_000, 240),    # > 10M rows:  4 min
        (0, 120),             # default:     2 min
    ]

    def __init__(self, config: AppConfig, query_logger: Optional[QueryLogger] = None):
        self.config = config
        self.logger = query_logger or QueryLogger(region=config.athena.region)
        self.dialect = SQLDialect.ATHENA
        self._conn = None
        self._query_timeout: int = config.athena.query_timeout_seconds
        self._cost_hard_limit: float = getattr(
            config.athena, "cost_hard_limit_usd", 3.0
        )
        self._cost_guardrail_bypassed: bool = False
        self._init_connection()

    def _init_connection(self):
        """Inicializa conexao PyAthena.

        Usa DictCursor que busca resultados via API GetQueryResults,
        sem acessar S3 diretamente. Isso evita erros de SSL/Signature
        causados por proxy corporativo interceptando acesso ao S3.

        Se workgroup estiver configurado, passa s3_staging_dir="" para
        desabilitar qualquer referencia ao S3 no PyAthena — o Athena
        usa o output location do workgroup server-side.
        """
        from pyathena import connect
        from pyathena.cursor import DictCursor

        connect_kwargs = {
            "region_name": self.config.athena.region,
            "cursor_class": DictCursor,
            "kill_on_interrupt": True,
            "result_reuse_enable": True,
        }

        # Se workgroup configurado, nao precisamos de s3_staging_dir.
        # Passar "" desabilita o fallback para S3 no PyAthena, eliminando
        # qualquer criacao de client S3 que falha com proxy corporativo.
        if self.config.athena.workgroup:
            connect_kwargs["work_group"] = self.config.athena.workgroup
            connect_kwargs["s3_staging_dir"] = ""
        elif self.config.athena.s3_output:
            connect_kwargs["s3_staging_dir"] = self.config.athena.s3_output

        if self.config.athena.aws_profile:
            from infra.aws_session import create_session
            session = create_session(self.config.athena.aws_profile)
            connect_kwargs["boto3_session"] = session

        self._conn = connect(**connect_kwargs)

    def adapt_timeout(self, estimated_rows: int) -> None:
        """Adapta o timeout de query baseado na volumetria estimada da tabela.

        Tabelas grandes precisam de mais tempo para queries de agregação.
        O timeout é ajustado para cima (nunca reduzido abaixo do configurado).

        Args:
            estimated_rows: Número estimado de linhas na tabela.
        """
        for threshold, timeout in self._TIMEOUT_TIERS:
            if estimated_rows >= threshold:
                new_timeout = max(timeout, self._query_timeout)
                if new_timeout != self._query_timeout:
                    logger.info(
                        "Timeout adaptado: %ds -> %ds (estimativa: %s linhas)",
                        self._query_timeout,
                        new_timeout,
                        f"{estimated_rows:,}",
                    )
                    self._query_timeout = new_timeout
                return

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
            friendly = _friendly_error_message(e, self.config.athena.aws_profile)
            logger.error(
                "Health check failed: %s: %s | profile=%s | region=%s | "
                "s3_output=%s | s3_addressing=%s",
                type(e).__name__,
                e,
                self.config.athena.aws_profile,
                self.config.athena.region,
                self.config.athena.s3_output,
                os.environ.get("AWS_S3_ADDRESSING_STYLE", "(not set)"),
            )
            raise ConnectionError(friendly) from e

    def _check_cost_guardrail(self, query_name: str = "") -> None:
        """Verifica custo acumulado antes de executar query.

        Usa session_state para persistir bypass entre reruns do Streamlit.

        Raises:
            CostGuardrailTriggered: Se custo >= threshold e bypass nao ativo.
        """
        # Verificar bypass persistido no session_state (sobrevive a reruns)
        try:
            import streamlit as st
            if st.session_state.get("_cost_guardrail_bypassed", False):
                return
        except Exception:
            pass
        if self._cost_guardrail_bypassed:
            return
        summary = self.logger.get_session_summary()
        if summary["estimated_cost_usd"] >= self._cost_hard_limit:
            from infra.cost_guard import CostGuardrailTriggered
            raise CostGuardrailTriggered(
                summary["estimated_cost_usd"],
                self._cost_hard_limit,
                query_name,
            )

    def bypass_cost_guardrail(self) -> None:
        """Desbloqueia guardrail de custo. Persiste no session_state."""
        self._cost_guardrail_bypassed = True
        try:
            import streamlit as st
            st.session_state["_cost_guardrail_bypassed"] = True
        except Exception:
            pass

    def reset_cost_guardrail(self) -> None:
        """Reseta bypass (ex: ao trocar configuracao)."""
        self._cost_guardrail_bypassed = False
        try:
            import streamlit as st
            st.session_state.pop("_cost_guardrail_bypassed", None)
        except Exception:
            pass

    def execute_df(
        self,
        sql: str,
        query_name: str = "unnamed",
        dataset: str = "",
        column: str = "",
    ) -> pd.DataFrame:
        """Executa query e retorna DataFrame. Loga metricas."""
        self._check_cost_guardrail(query_name)
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
            # Enriquecer erro com contexto da query
            raise type(e)(
                f"[{query_name}] {e}\n\nSQL:\n{sql[:500]}"
            ) from e

        finally:
            elapsed = int((time.time() - start) * 1000)
            self.logger.log_query(QueryLogEntry(
                query_name=query_name,
                dataset=dataset,
                column=column,
                elapsed_ms=elapsed,
                cache_hit=cache_hit,
                rows_returned=rows,
                sql=sql,
                bytes_scanned=bytes_scanned,
                exception_type=exception_type,
            ))

    def _execute_real_df(self, sql: str) -> tuple[pd.DataFrame, Optional[int], bool]:
        """Execute query on Athena with timeout enforcement.

        Uses DictCursor + pd.DataFrame conversion instead of PandasCursor.
        DictCursor fetches results via Athena API (GetQueryResults), avoiding
        direct S3 access that fails with corporate proxy SSL inspection.

        Timeout uses shutdown(wait=False) to unblock the caller immediately.
        The worker thread may continue for up to ~60s until the underlying
        socket/boto3 call returns. cursor.cancel() is best-effort.

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
            rows = cursor.fetchall()
            bytes_scanned = getattr(cursor, "data_scanned_in_bytes", None)
            cache_hit = bool(getattr(cursor, "reused_previous_result", False))
            df = pd.DataFrame(rows) if rows else pd.DataFrame()
            return df, bytes_scanned, cache_hit

        pool = ThreadPoolExecutor(max_workers=1)
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
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

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
        self._check_cost_guardrail(query_name)
        start = time.time()
        rows = 0
        exception_type = None
        bytes_scanned: Optional[int] = None
        cache_hit = False

        try:
            cursor = self._conn.cursor()

            def _run():
                cursor.execute(sql)
                result = cursor.fetchall()
                bs = getattr(cursor, "data_scanned_in_bytes", None)
                ch = bool(getattr(cursor, "reused_previous_result", False))
                return result, bs, ch

            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(_run)
            try:
                result, bytes_scanned, cache_hit = future.result(
                    timeout=self._query_timeout,
                )
            except FuturesTimeoutError:
                try:
                    cursor.cancel()
                except Exception:
                    pass
                raise TimeoutError(
                    f"Query exceeded timeout of {self._query_timeout}s."
                )
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

            rows = len(result)
            return result

        except Exception as e:
            exception_type = type(e).__name__
            raise type(e)(
                f"[{query_name}] {e}\n\nSQL:\n{sql[:500]}"
            ) from e

        finally:
            elapsed = int((time.time() - start) * 1000)
            self.logger.log_query(QueryLogEntry(
                query_name=query_name,
                dataset=dataset,
                column=column,
                elapsed_ms=elapsed,
                cache_hit=cache_hit,
                rows_returned=rows,
                sql=sql,
                bytes_scanned=bytes_scanned,
                exception_type=exception_type,
            ))

    def table_exists(self, schema: str, table: str) -> bool:
        """Verifica se a tabela existe.

        Returns:
            True se a tabela existe e e acessivel.

        Raises:
            ConnectionError: Se o erro for de infra (auth, SSL, proxy) e nao de tabela.
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
            # Erros de infra devem ser propagados, nao mascarados como "tabela nao encontrada"
            infra_keywords = [
                "expired", "invalid", "token", "access denied",
                "not authorized", "credentials", "security token",
                "unrecognizedclient", "ssl", "certificate",
                "signaturedoesnotmatch", "signature",
                "timeout", "refused", "nosuchbucket",
            ]
            if any(kw in error_msg for kw in infra_keywords):
                raise ConnectionError(
                    _friendly_error_message(e, self.config.athena.aws_profile)
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

        Usa information_schema.columns (SQL padrao) em vez de DESCRIBE,
        pois DESCRIBE retorna metadados em formato que varia conforme
        o tipo de cursor (PandasCursor vs DictCursor).

        Args:
            schema: Nome do schema/database.
            table: Nome da tabela.

        Returns:
            Tuple de (columns, partition_columns) onde:
            - columns: [{"name": str, "type": str}, ...]
            - partition_columns: ["dt_ref", ...] (vazia se nao particionada)
        """
        # information_schema retorna colunas com nomes padrao e funciona
        # independente do cursor. extra_info contem 'partition key' para
        # colunas de particao no Athena.
        rows = self.execute(
            f"""
            SELECT column_name, data_type, extra_info
            FROM information_schema.columns
            WHERE table_schema = '{schema}'
              AND table_name = '{table}'
            ORDER BY ordinal_position
            """,
            query_name="get_columns",
            dataset=f"{schema}.{table}",
        )

        columns = []
        partition_columns = []

        for row in rows:
            col_name = row.get("column_name", "")
            data_type = row.get("data_type", "")
            extra_info = row.get("extra_info", "") or ""

            if not isinstance(col_name, str) or not col_name.strip():
                continue
            col_name = col_name.strip()
            data_type = str(data_type).strip() if data_type else "string"

            columns.append({"name": col_name, "type": data_type})

            if "partition" in extra_info.lower():
                partition_columns.append(col_name)

        return columns, partition_columns
