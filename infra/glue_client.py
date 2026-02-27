"""Client boto3 para AWS Glue job execution.

Wrapper para operacoes de Glue job (start, status, cancel)
usado na integracao com o Thundera para teste de regras GDQ.

Reutiliza o mesmo AWS profile/session do AthenaClient.
Suporta modo mock para desenvolvimento local.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class GlueTestError(Exception):
    """Erro base para operacoes de teste Glue."""


class GluePermissionError(GlueTestError):
    """Permissoes IAM insuficientes para operacoes Glue."""


class GlueJobNotFoundError(GlueTestError):
    """Glue job especificado nao existe."""


class GlueClient:
    """Wrapper boto3 para execucao de Glue jobs.

    Reutiliza o AWS profile do AthenaClient para consistencia.
    Em modo mock (DuckDB), retorna respostas simuladas.

    Usage:
        client = GlueClient(config)
        run_id = client.start_job_run("job-name", {"--payload": json_str})
        status = client.get_job_run("job-name", run_id)
    """

    def __init__(self, config):
        """Inicializa o client Glue.

        Args:
            config: AppConfig com configuracoes AWS e GlueTestConfig.
        """
        from config import AthenaMode
        self.config = config
        self._client = None
        self._mock = config.athena.mode == AthenaMode.MOCK

        if not self._mock:
            self._init_client()

    def _init_client(self):
        """Inicializa boto3 client para Glue."""
        import boto3
        region = self.config.glue_test.region or self.config.athena.region
        if self.config.athena.aws_profile:
            session = boto3.Session(profile_name=self.config.athena.aws_profile)
            self._client = session.client("glue", region_name=region)
        else:
            self._client = boto3.client("glue", region_name=region)

    def start_job_run(self, job_name: str, arguments: dict[str, str]) -> str:
        """Inicia uma execucao do Glue job.

        Args:
            job_name: Nome do Glue job (ex: "glueplataformathundera").
            arguments: Argumentos do job (chave: "--payload", valor: JSON).

        Returns:
            Run ID da execucao.

        Raises:
            GluePermissionError: Se IAM nao tem glue:StartJobRun.
            GlueJobNotFoundError: Se o job nao existe.
            GlueTestError: Para outros erros.
        """
        if self._mock:
            import uuid
            mock_id = f"jr_mock_{uuid.uuid4().hex[:8]}"
            logger.info("Mock: Glue job '%s' started with run_id=%s", job_name, mock_id)
            return mock_id

        try:
            response = self._client.start_job_run(
                JobName=job_name,
                Arguments=arguments,
            )
            run_id = response["JobRunId"]
            logger.info("Glue job '%s' started: run_id=%s", job_name, run_id)
            return run_id

        except self._client.exceptions.EntityNotFoundException:
            raise GlueJobNotFoundError(
                f"Glue job '{job_name}' nao encontrado. "
                f"Verifique o nome do job na configuracao."
            )
        except self._client.exceptions.AccessDeniedException as e:
            raise GluePermissionError(
                f"Sem permissao para executar o Glue job '{job_name}'. "
                f"Verifique se o perfil AWS tem permissao glue:StartJobRun. "
                f"Detalhe: {e}"
            )
        except Exception as e:
            raise GlueTestError(f"Erro ao iniciar Glue job: {e}")

    def get_job_run(self, job_name: str, run_id: str) -> dict:
        """Consulta status de uma execucao do Glue job.

        Args:
            job_name: Nome do Glue job.
            run_id: ID da execucao.

        Returns:
            Dict com: JobRunState, StartedOn, CompletedOn,
            ExecutionTime, ErrorMessage.
        """
        if self._mock:
            return {
                "JobRunState": "SUCCEEDED",
                "StartedOn": "2026-02-27T10:00:00",
                "CompletedOn": "2026-02-27T10:02:00",
                "ExecutionTime": 120,
                "ErrorMessage": "",
            }

        try:
            response = self._client.get_job_run(
                JobName=job_name,
                RunId=run_id,
            )
            run = response["JobRun"]
            return {
                "JobRunState": run.get("JobRunState", "UNKNOWN"),
                "StartedOn": str(run.get("StartedOn", "")),
                "CompletedOn": str(run.get("CompletedOn", "")),
                "ExecutionTime": run.get("ExecutionTime", 0),
                "ErrorMessage": run.get("ErrorMessage", ""),
            }
        except Exception as e:
            raise GlueTestError(f"Erro ao consultar status do job: {e}")

    def stop_job_run(self, job_name: str, run_id: str) -> bool:
        """Cancela uma execucao do Glue job.

        Args:
            job_name: Nome do Glue job.
            run_id: ID da execucao.

        Returns:
            True se cancelado com sucesso.
        """
        if self._mock:
            logger.info("Mock: Glue job cancelled: %s", run_id)
            return True

        try:
            self._client.batch_stop_job_run(
                JobName=job_name,
                JobRunIds=[run_id],
            )
            logger.info("Glue job cancelled: %s", run_id)
            return True
        except Exception as e:
            logger.warning("Failed to cancel Glue job %s: %s", run_id, e)
            return False
