"""
Configuracao do GDQ Rule Proposer.
Carrega de variaveis de ambiente ou .env file.

O app roda localmente com acesso ao Athena real via AWS CLI profile.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AthenaConfig:
    region: str = "sa-east-1"
    workgroup: str = "analytics-workgroup-v3"
    s3_output: str = ""                # s3://bucket/athena-results/
    catalog: str = "AwsDataCatalog"
    aws_profile: str = ""              # AWS CLI named profile
    query_timeout_seconds: int = 120   # default, adaptado pela volumetria
    cache_ttl_metadata: int = 3600     # 1h
    cache_ttl_history: int = 900       # 15min
    cache_ttl_profiling: int = 1800    # 30min
    cost_warning_threshold_usd: float = 0.50


@dataclass
class GlueTestConfig:
    """Configuracao para integracao com Thundera (Glue DQ)."""
    glue_job_name: str = "glueplataformathundera"
    region: str = ""  # defaults to AthenaConfig.region if empty
    poll_interval_seconds: int = 15
    poll_timeout_seconds: int = 600
    default_squad: str = ""
    default_comunidade: str = ""
    default_racf: str = ""
    default_periodicidade: str = "D"
    default_tipo_qualidade: str = "POUSADO"
    default_conta: str = "DISTRIBUICAOMODELO"
    default_timeout: str = "60"
    default_workers: str = "20"


@dataclass
class AppConfig:
    athena: AthenaConfig = field(default_factory=AthenaConfig)
    glue_test: GlueTestConfig = field(default_factory=GlueTestConfig)
    log_dir: str = "logs"
    preset_dir: str = "presets"


def load_config() -> AppConfig:
    """Carrega configuracao do ambiente.

    Hierarquia:
    1. Variaveis de ambiente (sempre prevalecem)
    2. Arquivo .env
    3. Defaults

    Variaveis de ambiente:
    - GDQ_ATHENA_REGION: regiao AWS
    - GDQ_ATHENA_WORKGROUP: workgroup do Athena
    - GDQ_ATHENA_S3_OUTPUT: bucket de output
    - GDQ_AWS_PROFILE: named profile do AWS CLI
    """
    # Tentar carregar .env file
    env_file = Path(".env")
    if env_file.exists():
        _load_dotenv(env_file)

    # AWS profile: da env var ou do .env file
    aws_profile = os.getenv("GDQ_AWS_PROFILE", "")
    if aws_profile and not os.environ.get("AWS_PROFILE"):
        os.environ["AWS_PROFILE"] = aws_profile

    athena = AthenaConfig(
        region=os.getenv("GDQ_ATHENA_REGION", "sa-east-1"),
        workgroup=os.getenv("GDQ_ATHENA_WORKGROUP", "analytics-workgroup-v3"),
        s3_output=os.getenv("GDQ_ATHENA_S3_OUTPUT", ""),
        aws_profile=aws_profile,
    )

    glue_test = GlueTestConfig(
        glue_job_name=os.getenv("GDQ_GLUE_JOB_NAME", "glueplataformathundera"),
        region=os.getenv("GDQ_GLUE_REGION", ""),
        default_racf=os.getenv("GDQ_RACF", ""),
        default_squad=os.getenv("GDQ_SQUAD", ""),
        default_comunidade=os.getenv("GDQ_COMUNIDADE", ""),
    )

    return AppConfig(athena=athena, glue_test=glue_test)


def _load_dotenv(path: Path):
    """Parser simples de .env (sem dependencia externa)."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
