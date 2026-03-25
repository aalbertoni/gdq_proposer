"""Modelos para integracao com Thundera (Glue Data Quality).

Define o payload JSON para o Glue job Thundera e os modelos
de resultado da execucao.

Referencia: docs/technical_spec_v1.md
"""

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ThunderaProcessamento:
    """Configuracao de processamento do Glue job."""
    conta: str = "DISTRIBUICAOMODELO"
    timeout: str = "60"
    workers: str = "20"
    motor: str = "THUNDERADQ"


@dataclass
class ThunderaPayload:
    """Payload JSON completo para o Glue job Thundera.

    Mapeia DatasetConfig + regras do carrinho para o formato
    JSON esperado pelo pipeline Thundera de qualidade de dados.

    Campos classificatorios sao editaveis pelo usuario na UI
    com defaults pre-preenchidos. Campos de tabela, colunas e
    regras sao preenchidos automaticamente a partir da configuracao.

    Attributes:
        squad: Nome do squad responsavel.
        comunidade: Nome da comunidade de dados.
        racf: Identificador do usuario (login corporativo).
        periodicidade: Periodicidade dos dados (D=diario, M=mensal, S=semanal).
        tipo_qualidade: Tipo de qualidade (POUSADO, STREAMING, etc).
        status_regra: Status da regra (ATIVA, INATIVA).
        nome_orig_tablea: Origem da tabela (AWS, ON_PREM, etc).
        cod_regr_even_cred: Codigo identificador unico do evento/regra.
        release_train: Release train (opcional).
        cod_tabe: Identificador da tabela no formato schema.table.
        processamento: Configuracao de processamento do Glue job.
        nome_glue_job: Nome do Glue job a ser executado.
        infer_schema: Se deve inferir schema automaticamente.
        iceberg: Se a tabela usa formato Iceberg.
        particao: Lista de colunas de particao.
        particoes_evento: Particoes de evento (filtro adicional).
        delay_processamento: Delay em minutos antes do processamento.
        columns_name: Lista de colunas referenciadas nas regras.
        regras_gdq: Lista de strings com sintaxe GDQ das regras.
    """
    # Classificatory (user-editable)
    squad: str = ""
    comunidade: str = ""
    racf: str = ""
    periodicidade: str = "D"
    tipo_qualidade: str = "POUSADO"
    status_regra: str = "ATIVA"
    nome_orig_tablea: str = "AWS"
    cod_regr_even_cred: str = ""
    release_train: str = ""

    # Table identification
    cod_tabe: str = ""

    # Processing
    processamento: ThunderaProcessamento = field(default_factory=ThunderaProcessamento)
    nome_glue_job: str = "glueplataformathundera"

    # Schema flags
    infer_schema: bool = False
    iceberg: bool = False

    # Partitions
    particao: list[str] = field(default_factory=list)
    particoes_evento: str = ""

    # Delay
    delay_processamento: int = 0

    # Rules (auto-populated from cart)
    columns_name: list[str] = field(default_factory=list)
    regras_gdq: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serializa para o formato JSON Thundera (chaves UPPER_CASE).

        Returns:
            Dict com a estrutura exata esperada pelo Thundera.
        """
        return {
            "SQUAD": self.squad,
            "INFER_SCHEMA": self.infer_schema,
            "RELEASE_TRAIN": self.release_train,
            "COMUNIDADE": self.comunidade,
            "DELAY_PROCESSAMENTO": self.delay_processamento,
            "NOME_GLUE_JOB": self.nome_glue_job,
            "TIPO_QUALIDADE": self.tipo_qualidade,
            "STATUS_REGRA": self.status_regra,
            "NOME_ORIG_TABLEA": self.nome_orig_tablea,
            "PROCESSAMENTO": {
                "CONTA": self.processamento.conta,
                "TIMEOUT": self.processamento.timeout,
                "WORKERS": self.processamento.workers,
                "MOTOR": self.processamento.motor,
            },
            "ICEBERG": self.iceberg,
            "PERIODICIDADE": self.periodicidade,
            "PARTICOES_EVENTO": self.particoes_evento,
            "VARIAVEIS": {
                "GDQ": [{"RegraGDQ": r} for r in self.regras_gdq],
            },
            "RACF": self.racf,
            "COLUMNS_NAME": self.columns_name,
            "COD_TABE": self.cod_tabe,
            "PARTICAO": self.particao,
            "COD_REGR_EVEN_CRED": self.cod_regr_even_cred,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serializa para string JSON.

        O json.dumps trata automaticamente o escaping de aspas duplas
        internas nas regras CustomSql (\" no output JSON).

        Returns:
            String JSON formatada.
        """
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class GlueRuleResult:
    """Resultado individual de uma regra GDQ executada pelo Thundera.

    Attributes:
        rule_syntax: Sintaxe GDQ completa da regra (como enviada no payload).
        outcome: Resultado (Passed, Failed).
        evaluated_metrics: Metricas avaliadas (ex: Dataset.*.CustomSQL -> valor).
        failure_reason: Motivo da falha (se houver).
        evaluated_rule: Regra compilada pelo GDQ (limites expandidos de avg/std).
        rule_label: Label curta para exibicao (ex: "Mean vlr_saldo").
        rule_category: Categoria da regra (Mean, StandardDeviation, Completeness, etc).
        target_column: Coluna alvo da regra.
        compiled_lower: Limite inferior compilado (extraido do evaluated_rule ou failure_reason).
        compiled_upper: Limite superior compilado (extraido do evaluated_rule ou failure_reason).
    """
    rule_syntax: str = ""
    outcome: str = ""
    evaluated_metrics: dict[str, float] = field(default_factory=dict)
    failure_reason: str = ""
    evaluated_rule: str = ""
    rule_label: str = ""
    rule_category: str = ""
    target_column: str = ""
    compiled_lower: Optional[float] = None
    compiled_upper: Optional[float] = None

    @property
    def passed(self) -> bool:
        return self.outcome.lower() == "passed"

    @property
    def metric_value(self) -> Optional[float]:
        """Retorna o valor da metrica principal avaliada."""
        if self.evaluated_metrics:
            return next(iter(self.evaluated_metrics.values()))
        return None


@dataclass
class GlueTestResult:
    """Resultado de uma execucao do Glue job de teste.

    Attributes:
        run_id: ID da execucao do Glue job.
        job_name: Nome do Glue job executado.
        status: Estado final (SUCCEEDED, FAILED, TIMEOUT, STOPPED, RUNNING).
        started_at: Timestamp de inicio.
        completed_at: Timestamp de conclusao.
        duration_seconds: Duracao em segundos.
        error_message: Mensagem de erro (se houver).
        execution_log: Log completo da execucao.
        rule_results: Resultados individuais por regra (parsed dos logs).
    """
    run_id: str = ""
    job_name: str = ""
    status: str = "PENDING"
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: int = 0
    error_message: str = ""
    execution_log: str = ""
    rule_results: list[GlueRuleResult] = field(default_factory=list)
