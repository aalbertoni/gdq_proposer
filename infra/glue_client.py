"""Client boto3 para AWS Glue job execution.

Wrapper para operacoes de Glue job (start, status, cancel)
usado na integracao com o Thundera para teste de regras GDQ.
"""

import logging
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

    Usage:
        client = GlueClient(config)
        run_id = client.start_job_run("job-name", {"--objson": json_str})
        status = client.get_job_run("job-name", run_id)
    """

    def __init__(self, config):
        """Inicializa o client Glue.

        Args:
            config: AppConfig com configuracoes AWS e GlueTestConfig.
        """
        self.config = config
        self._client = None
        self._init_client()

    def _init_client(self):
        """Inicializa boto3 client para Glue."""
        import boto3
        region = self.config.glue_test.region or self.config.athena.region
        if self.config.athena.aws_profile:
            from infra.aws_session import create_session
            session = create_session(self.config.athena.aws_profile)
            self._client = session.client("glue", region_name=region)
        else:
            self._client = boto3.client("glue", region_name=region)

    def start_job_run(self, job_name: str, arguments: dict[str, str]) -> str:
        """Inicia uma execucao do Glue job.

        Args:
            job_name: Nome do Glue job (ex: "glueplataformathundera").
            arguments: Argumentos do job (chave: "--objson", valor: JSON).

        Returns:
            Run ID da execucao.

        Raises:
            GluePermissionError: Se IAM nao tem glue:StartJobRun.
            GlueJobNotFoundError: Se o job nao existe.
            GlueTestError: Para outros erros.
        """
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

    def get_job_logs(self, job_name: str, run_id: str) -> str:
        """Busca logs de output de uma execucao do Glue job via CloudWatch.

        AWS Glue grava logs de output em /aws-glue/jobs/output com
        log stream nomeado pelo run_id.

        Args:
            job_name: Nome do Glue job.
            run_id: ID da execucao.

        Returns:
            Texto concatenado dos logs de output. String vazia se falhar.
        """
        try:
            import boto3
            region = self.config.glue_test.region or self.config.athena.region
            if self.config.athena.aws_profile:
                from infra.aws_session import create_session
                session = create_session(self.config.athena.aws_profile)
                logs_client = session.client("logs", region_name=region)
            else:
                logs_client = boto3.client("logs", region_name=region)

            log_group = "/aws-glue/jobs/output"
            log_stream = run_id

            events = []
            kwargs = {
                "logGroupName": log_group,
                "logStreamName": log_stream,
                "startFromHead": True,
            }
            while True:
                response = logs_client.get_log_events(**kwargs)
                batch = response.get("events", [])
                if not batch:
                    break
                events.extend(batch)
                next_token = response.get("nextForwardToken")
                if next_token == kwargs.get("nextToken"):
                    break
                kwargs["nextToken"] = next_token

            return "\n".join(e.get("message", "") for e in events)

        except Exception as e:
            logger.warning("Falha ao buscar logs do CloudWatch para %s: %s", run_id, e)
            return ""

    def stop_job_run(self, job_name: str, run_id: str) -> bool:
        """Cancela uma execucao do Glue job.

        Args:
            job_name: Nome do Glue job.
            run_id: ID da execucao.

        Returns:
            True se cancelado com sucesso.
        """
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
