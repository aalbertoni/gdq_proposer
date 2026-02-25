"""
Configuração multi-ambiente para o GDQ Rule Proposer.
Carrega de variáveis de ambiente ou .env file.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Environment(str, Enum):
    LOCAL = "local"       # DuckDB + dados mock
    DEV = "dev"           # Athena real com credenciais AWS CLI
    PROD = "prod"         # Athena real com IAM roles


class AthenaMode(str, Enum):
    MOCK = "mock"         # DuckDB local
    REAL = "real"         # PyAthena → AWS Athena


@dataclass
class AthenaConfig:
    mode: AthenaMode = AthenaMode.MOCK
    # Athena real (dev/prod)
    region: str = "us-east-1"
    workgroup: str = "primary"
    s3_output: str = ""                # s3://bucket/athena-results/
    catalog: str = "AwsDataCatalog"
    # AWS Auth
    aws_profile: str = ""              # para dev (AWS CLI named profile)
    # Para prod: usa IAM role automaticamente (sem profile)
    # Mock (local)
    mock_data_dir: str = "mock_data"
    # Geral
    query_timeout_seconds: int = 120
    cache_ttl_metadata: int = 3600     # 1h
    cache_ttl_history: int = 900       # 15min
    cache_ttl_profiling: int = 1800    # 30min


@dataclass
class AppConfig:
    environment: Environment = Environment.LOCAL
    athena: AthenaConfig = field(default_factory=AthenaConfig)
    log_dir: str = "logs"
    preset_dir: str = "presets"


def load_config() -> AppConfig:
    """Carrega configuração do ambiente.

    Hierarquia:
    1. Variáveis de ambiente (sempre prevalecem)
    2. Arquivo .env.{environment}
    3. Defaults

    Variáveis de ambiente:
    - GDQ_ENV: local, dev, prod
    - GDQ_ATHENA_REGION: região AWS
    - GDQ_ATHENA_WORKGROUP: workgroup do Athena
    - GDQ_ATHENA_S3_OUTPUT: bucket de output
    - GDQ_AWS_PROFILE: named profile do AWS CLI
    - GDQ_MOCK_DATA_DIR: diretório dos dados mock
    """
    env_name = os.getenv("GDQ_ENV", "local")
    env = Environment(env_name)

    # Tentar carregar .env file
    env_file = Path(f".env.{env_name}")
    if env_file.exists():
        _load_dotenv(env_file)

    if env == Environment.LOCAL:
        athena = AthenaConfig(
            mode=AthenaMode.MOCK,
            mock_data_dir=os.getenv("GDQ_MOCK_DATA_DIR", "mock_data"),
        )
    else:
        athena = AthenaConfig(
            mode=AthenaMode.REAL,
            region=os.getenv("GDQ_ATHENA_REGION", "us-east-1"),
            workgroup=os.getenv("GDQ_ATHENA_WORKGROUP", "primary"),
            s3_output=os.getenv("GDQ_ATHENA_S3_OUTPUT", ""),
            aws_profile=os.getenv("GDQ_AWS_PROFILE", ""),
        )

    return AppConfig(environment=env, athena=athena)


def _load_dotenv(path: Path):
    """Parser simples de .env (sem dependência externa)."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
