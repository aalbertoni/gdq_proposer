"""Servico de teste de regras GDQ via Thundera (Glue job).

Orquestra: construcao do payload JSON, execucao do Glue job,
polling de status e coleta de resultados.
"""

import logging
import time
from typing import Optional, Callable

from core.models.enums import RuleType

logger = logging.getLogger(__name__)


class GlueTestService:
    """Orquestra teste de regras GDQ via Thundera Glue job.

    Responsabilidades:
    1. Construir payload JSON a partir do carrinho de regras
    2. Disparar execucao do Glue job
    3. Fazer polling de status ate conclusao
    4. Retornar resultado estruturado

    Usage:
        svc = GlueTestService(glue_client, config)
        payload = svc.build_payload(dataset_config, selections, classificatory)
        result = svc.run_test(payload)
    """

    def __init__(self, glue_client, config):
        """Inicializa o servico.

        Args:
            glue_client: GlueClient para operacoes boto3.
            config: AppConfig com GlueTestConfig.
        """
        self._client = glue_client
        self._config = config

    def build_payload(
        self,
        dataset_config,
        selections: list,
        classificatory: dict[str, str],
        partition_columns: list[str] | None = None,
    ):
        """Constroi ThunderaPayload a partir do carrinho e config.

        Args:
            dataset_config: DatasetConfig ativo.
            selections: Lista de RuleSelection habilitadas.
            classificatory: Campos classificatorios editados pelo usuario.
            partition_columns: Colunas de particao (None = usa dataset_config).

        Returns:
            ThunderaPayload pronto para serializacao.
        """
        from core.models.glue_test import ThunderaPayload, ThunderaProcessamento

        # Extract unique column names from rules
        columns = self._extract_columns(selections)

        # Extract GDQ syntax strings
        regras = []
        for sel in selections:
            if sel.enabled and sel.final_gdq_syntax and sel.final_gdq_syntax.strip():
                regras.append(sel.final_gdq_syntax.strip())

        # Build partition list
        if partition_columns:
            particao = partition_columns
        elif dataset_config.partition_column:
            particao = [dataset_config.partition_column]
        else:
            particao = []

        # COD_TABE = schema.table
        cod_tabe = f"{dataset_config.schema}.{dataset_config.table}"

        glue_cfg = self._config.glue_test

        return ThunderaPayload(
            squad=classificatory.get("squad", glue_cfg.default_squad),
            comunidade=classificatory.get("comunidade", glue_cfg.default_comunidade),
            racf=classificatory.get("racf", glue_cfg.default_racf),
            periodicidade=classificatory.get("periodicidade", glue_cfg.default_periodicidade),
            tipo_qualidade=classificatory.get("tipo_qualidade", glue_cfg.default_tipo_qualidade),
            status_regra=classificatory.get("status_regra", "ATIVA"),
            nome_orig_tablea=classificatory.get("nome_orig_tablea", "AWS"),
            cod_regr_even_cred=classificatory.get("cod_regr_even_cred", ""),
            release_train=classificatory.get("release_train", ""),
            cod_tabe=cod_tabe,
            processamento=ThunderaProcessamento(
                conta=classificatory.get("conta", glue_cfg.default_conta),
                timeout=classificatory.get("timeout", glue_cfg.default_timeout),
                workers=classificatory.get("workers", glue_cfg.default_workers),
            ),
            nome_glue_job=classificatory.get("nome_glue_job", glue_cfg.glue_job_name),
            infer_schema=classificatory.get("infer_schema", False),
            iceberg=classificatory.get("iceberg", False),
            particao=particao,
            particoes_evento=classificatory.get("particoes_evento", ""),
            delay_processamento=int(classificatory.get("delay_processamento", 0)),
            columns_name=columns,
            regras_gdq=regras,
        )

    def _extract_columns(self, selections: list) -> list[str]:
        """Extrai nomes unicos de colunas referenciadas nas regras.

        Formato Thundera: lowercase entre aspas duplas (ex: '"vlr_saldo"').

        Args:
            selections: Lista de RuleSelection.

        Returns:
            Lista ordenada de nomes de colunas formatados.
        """
        columns: set[str] = set()
        for sel in selections:
            if not sel.enabled:
                continue
            p = sel.proposal
            if not p.target_column:
                continue
            if p.rule_type == RuleType.IS_PRIMARY_KEY:
                # IsPrimaryKey has space-separated columns
                columns.update(p.target_column.split())
            else:
                columns.add(p.target_column)
        return sorted(f'"{c.lower()}"' for c in columns)

    def run_test(
        self,
        payload,
        on_status: Callable[[str, str], None] | None = None,
    ):
        """Executa teste: dispara job, faz polling, retorna resultado.

        Args:
            payload: ThunderaPayload construido por build_payload().
            on_status: Callback(status, message) para atualizacao de UI.

        Returns:
            GlueTestResult com status final.

        Raises:
            GlueTestError: Em caso de falha do job ou timeout.
        """
        from core.models.glue_test import GlueTestResult
        from infra.glue_client import GlueTestError

        cfg = self._config.glue_test
        job_name = payload.nome_glue_job
        json_str = payload.to_json()

        # Trigger
        if on_status:
            on_status("STARTING", "Disparando Glue job...")
        run_id = self._client.start_job_run(
            job_name=job_name,
            arguments={"--objson": json_str},
        )

        # Poll
        elapsed = 0
        interval = cfg.poll_interval_seconds
        timeout = cfg.poll_timeout_seconds

        while elapsed < timeout:
            time.sleep(interval)
            elapsed += interval

            try:
                status_info = self._client.get_job_run(job_name, run_id)
            except GlueTestError:
                # Transient error, retry
                continue

            state = status_info["JobRunState"]
            if on_status:
                on_status(state, f"Job {state}... ({elapsed}s)")

            if state in ("SUCCEEDED", "FAILED", "STOPPED", "ERROR", "TIMEOUT"):
                result = GlueTestResult(
                    run_id=run_id,
                    job_name=job_name,
                    status=state,
                    started_at=status_info.get("StartedOn", ""),
                    completed_at=status_info.get("CompletedOn", ""),
                    duration_seconds=status_info.get("ExecutionTime", 0),
                    error_message=status_info.get("ErrorMessage", ""),
                )
                self._fetch_and_parse_logs(result, on_status)
                return result

        # Timeout — try to cancel
        self._client.stop_job_run(job_name, run_id)
        return GlueTestResult(
            run_id=run_id,
            job_name=job_name,
            status="TIMEOUT",
            duration_seconds=elapsed,
            error_message=f"Job excedeu timeout de {timeout}s. Cancelamento solicitado.",
        )

    def _fetch_and_parse_logs(self, result, on_status=None):
        """Busca logs do CloudWatch e faz parse dos resultados por regra.

        Args:
            result: GlueTestResult a ser enriquecido com logs e rule_results.
            on_status: Callback opcional para atualizacao de UI.
        """
        from core.glue_log_parser import parse_glue_log

        if on_status:
            on_status("FETCHING_LOGS", "Buscando logs do CloudWatch...")

        try:
            log_text = self._client.get_job_logs(result.job_name, result.run_id)
        except Exception as e:
            logger.warning("Falha ao buscar logs: %s", e)
            if on_status:
                on_status("NO_LOGS", "Falha ao buscar logs do CloudWatch.")
            return

        result.execution_log = log_text

        if log_text:
            if on_status:
                on_status("PARSING_LOGS", "Analisando resultados por regra...")
            result.rule_results = parse_glue_log(log_text)
        else:
            if on_status:
                on_status("NO_LOGS", "Logs nao disponiveis no CloudWatch.")
