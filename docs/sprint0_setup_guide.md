# Sprint 0 — Setup de Ambiente

> **Objetivo:** Ambiente de desenvolvimento funcional com Claude Code no Windows,
> mock Athena local com dados sintéticos, e estrutura pronta para transição para produção.

---

## Índice

1. [Setup Windows + Claude Code](#1-setup-windows--claude-code)
2. [Estrutura do projeto](#2-estrutura-do-projeto)
3. [Mock Athena local](#3-mock-athena-local)
4. [Dados sintéticos](#4-dados-sintéticos)
5. [Configuração multi-ambiente (local → prod)](#5-configuração-multi-ambiente)
6. [Validação do setup](#6-validação-do-setup)
7. [Tarefas para Claude Code](#7-tarefas-para-claude-code)

---

## 1. Setup Windows + Claude Code

### 1.1 Pré-requisitos

```powershell
# Verificar Node.js (necessário para Claude Code)
node --version   # >= 18.x

# Se não tiver, instalar via winget
winget install OpenJS.NodeJS.LTS

# Python
python --version  # >= 3.11

# Git
git --version

# AWS CLI (para futuro uso em prod)
aws --version     # >= 2.x
```

### 1.2 Instalar Claude Code

```powershell
# Instalar globalmente
npm install -g @anthropic-ai/claude-code

# Verificar
claude --version

# Autenticar (vai abrir browser para login Anthropic)
claude auth login
```

### 1.3 Criar repositório

```powershell
# Criar diretório do projeto
mkdir C:\dev\gdq-proposer
cd C:\dev\gdq-proposer

# Inicializar git
git init

# Criar venv Python
python -m venv .venv
.venv\Scripts\activate

# Instalar dependências base
pip install streamlit plotly pandas pyathena boto3 jinja2 pytest moto[athena,s3,glue]
pip freeze > requirements.txt
```

### 1.4 Iniciar Claude Code

```powershell
cd C:\dev\gdq-proposer

# Iniciar Claude Code (ele vai ler o CLAUDE.md automaticamente)
claude

# Dentro do Claude Code, o CLAUDE.md é carregado como contexto
# Você pode pedir tarefas diretamente:
# > "Leia docs/technical_spec_v1.md e implemente core/models/dataset_config.py"
```

### 1.5 .gitignore

```gitignore
# Python
.venv/
__pycache__/
*.pyc
.pytest_cache/

# Ambiente
.env
.env.local
.env.prod

# IDE
.vscode/
.idea/

# Streamlit
.streamlit/secrets.toml

# AWS
.aws/

# Outputs
presets/*.json
!presets/.gitkeep
logs/
```

---

## 2. Estrutura do Projeto (criar esqueleto)

```powershell
# Script PowerShell para criar toda a estrutura de pastas
$dirs = @(
    "pages",
    "services",
    "core/models",
    "infra",
    "queries/templates",
    "strategies",
    "tests/fixtures",
    "presets",
    "docs",
    "logs"
)

foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path $dir
}

# Criar arquivos __init__.py
$packages = @("core", "core/models", "services", "infra", "strategies", "tests", "tests/fixtures")
foreach ($pkg in $packages) {
    New-Item -ItemType File -Force -Path "$pkg/__init__.py"
}

# Criar .gitkeep em diretórios vazios
New-Item -ItemType File -Force -Path "presets/.gitkeep"
New-Item -ItemType File -Force -Path "logs/.gitkeep"
```

---

## 3. Mock Athena Local

### 3.1 Estratégia: Moto como backend mock do Athena

**Moto** é a biblioteca oficial de mock da AWS que simula serviços AWS localmente.
Ela suporta Athena, S3, Glue Catalog — exatamente o que precisamos.

A ideia é:
- Em **desenvolvimento**: queries rodam contra Moto (mock) com dados sintéticos
- Em **produção**: mesmas queries rodam contra Athena real via AWS CLI/roles
- A **única coisa que muda** é o client de conexão — as queries SQL são idênticas

### 3.2 Como o mock funciona

```
┌─────────────────────────────────────────────┐
│  Seu código (query_builder + templates SQL)  │
│              ↓ (mesmas queries)              │
├─────────────────────────────────────────────┤
│  AthenaClient (abstração)                    │
│  ├─ mode="mock"  → MockAthenaBackend (Moto) │
│  └─ mode="real"  → PyAthena + boto3         │
├─────────────────────────────────────────────┤
│  Mock: moto + SQLite    │  Real: AWS Athena  │
│  (desenvolvimento)      │  (produção)        │
└─────────────────────────────────────────────┘
```

### 3.3 Limitação do Moto e a solução prática

O `moto` mock do Athena é limitado — ele não executa SQL de verdade.
Ele apenas registra queries e retorna resultados pré-definidos.

**Solução recomendada: DuckDB como motor SQL local**

DuckDB é um banco SQL analítico in-process que:
- Suporta sintaxe muito próxima do Presto/Athena
- Roda em memória (zero config)
- Aceita `APPROX_QUANTILE` (equivalente ao `APPROX_PERCENTILE` do Athena)
- Funciona perfeitamente no Windows

```
┌─────────────────────────────────────────────┐
│  Templates SQL Jinja2 (queries idênticas)    │
│              ↓                               │
├─────────────────────────────────────────────┤
│  AthenaClient                                │
│  ├─ mode="local"  → DuckDB (dev)            │
│  │   └─ tabelas criadas a partir de CSVs     │
│  │   └─ adaptador de sintaxe mínimo          │
│  └─ mode="athena" → PyAthena (prod)          │
└─────────────────────────────────────────────┘
```

### 3.4 Instalar DuckDB

```powershell
pip install duckdb
```

### 3.5 Adaptador de sintaxe Athena → DuckDB

A maioria das queries funciona igual. As poucas diferenças:

| Athena (Presto/Trino) | DuckDB | Ação |
|----------------------|--------|------|
| `APPROX_PERCENTILE(col, ARRAY[...])` | `QUANTILE_CONT(col, [...])` | Adaptar no template |
| `DATE_ADD('day', -N, CURRENT_DATE)` | `CURRENT_DATE - INTERVAL N DAY` | Adaptar no template |
| `TRY_CAST(x AS DOUBLE)` | `TRY_CAST(x AS DOUBLE)` | Idêntico ✅ |
| `STDDEV(col)` | `STDDEV_SAMP(col)` | Adaptar |
| `"schema"."table"` | Tabela direta (sem schema) | Adaptar no query builder |

O adaptador é simples e localizado:

```python
# infra/sql_dialect.py

from enum import Enum


class SQLDialect(str, Enum):
    ATHENA = "athena"
    DUCKDB = "duckdb"


# Mapeamento de funções que diferem entre Athena e DuckDB
DIALECT_FUNCTIONS = {
    "APPROX_PERCENTILE": {
        SQLDialect.ATHENA: "APPROX_PERCENTILE({col}, ARRAY[{quantiles}])",
        SQLDialect.DUCKDB: "QUANTILE_CONT({col}, [{quantiles}])",
    },
    "STDDEV": {
        SQLDialect.ATHENA: "STDDEV({expr})",
        SQLDialect.DUCKDB: "STDDEV_SAMP({expr})",
    },
    "DATE_SUBTRACT_DAYS": {
        SQLDialect.ATHENA: "DATE_ADD('day', -{n}, CURRENT_DATE)",
        SQLDialect.DUCKDB: "CURRENT_DATE - INTERVAL '{n}' DAY",
    },
    "TABLE_REF": {
        SQLDialect.ATHENA: '"{schema}"."{table}"',
        SQLDialect.DUCKDB: '"{table}"',
    },
}


def adapt_function(func_name: str, dialect: SQLDialect, **kwargs) -> str:
    """Retorna a expressão SQL correta para o dialeto."""
    template = DIALECT_FUNCTIONS[func_name][dialect]
    return template.format(**kwargs)
```

### 3.6 Template SQL com suporte a dialeto

```sql
-- queries/templates/numeric_history.sql
-- Compatível com Athena e DuckDB via variáveis de dialeto

SELECT
  {{ date_expression }} as processing_period,
  COUNT(*) as total_count,
  COUNT("{{ col }}") as non_null_count,
  AVG(CAST("{{ col }}" AS DOUBLE)) as col_mean,
  {{ stddev_func }}(CAST("{{ col }}" AS DOUBLE)) as col_stddev,
  MIN(CAST("{{ col }}" AS DOUBLE)) as col_min,
  MAX(CAST("{{ col }}" AS DOUBLE)) as col_max,
  {{ approx_percentile_expr }} as col_percentiles
FROM {{ table_ref }}
WHERE {{ date_expression }} >= {{ date_lookback_expr }}
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
GROUP BY {{ date_expression }}
ORDER BY processing_period
```

O `query_builder` injeta as funções corretas baseado no dialeto:

```python
# infra/query_builder.py (trecho relevante)

from jinja2 import Environment, FileSystemLoader
from infra.sql_dialect import SQLDialect, adapt_function


class QueryBuilder:
    def __init__(self, dialect: SQLDialect = SQLDialect.ATHENA):
        self.dialect = dialect
        self.env = Environment(
            loader=FileSystemLoader("queries/templates"),
            keep_trailing_newline=True,
        )

    def build_numeric_history(
        self,
        schema: str,
        table: str,
        col: str,
        date_expression: str,
        lookback_value: int,
        base_filter: str = "",
    ) -> str:
        template = self.env.get_template("numeric_history.sql")

        # Funções adaptadas ao dialeto
        quantiles = "0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99"
        approx_expr = adapt_function(
            "APPROX_PERCENTILE",
            self.dialect,
            col=f'CAST("{col}" AS DOUBLE)',
            quantiles=quantiles,
        )

        return template.render(
            col=col,
            date_expression=date_expression,
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table
            ),
            stddev_func=adapt_function(
                "STDDEV", self.dialect, expr=""
            ).split("(")[0],  # pega só o nome da função
            approx_percentile_expr=approx_expr,
            date_lookback_expr=adapt_function(
                "DATE_SUBTRACT_DAYS", self.dialect, n=lookback_value
            ),
            base_filter=base_filter,
        )
```

---

## 4. Dados Sintéticos (Mock Data)

### 4.1 Script de geração de dados

Este script cria uma tabela mock que simula um cenário real:
operações de crédito com colunas numéricas, categóricas e temporal.

```python
# scripts/generate_mock_data.py
"""
Gera dados sintéticos para desenvolvimento local.
Simula uma tabela de operações de crédito com:
- Colunas numéricas: VLR_SALD_AVNC_OPCR, VLR_PARC_OPCR, VLR_CNTR_OPCR
- Coluna categórica: COD_SITU_OPCR (3 valores: '1', '2', '3')
- Coluna de data: DT_REF (diária, últimos 60 dias)
- Coluna de chave: NUM_CTRT_OPCR
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, timedelta


def generate_mock_data(
    n_days: int = 60,
    rows_per_day: int = 10000,
    seed: int = 42,
    output_dir: str = "mock_data",
) -> pd.DataFrame:
    """Gera dataset sintético para mock do Athena."""
    rng = np.random.default_rng(seed)
    Path(output_dir).mkdir(exist_ok=True)

    all_rows = []
    base_date = date.today() - timedelta(days=n_days)

    for day_offset in range(n_days):
        current_date = base_date + timedelta(days=day_offset)
        n_rows = rows_per_day + rng.integers(-500, 500)

        # Simular drift leve no saldo (cresce ~0.1% por dia)
        drift_factor = 1 + (day_offset * 0.001)

        # Simular outlier no dia 45
        outlier_factor = 1.0
        if day_offset == 45:
            outlier_factor = 1.35  # spike de 35%

        # Simular regime change no dia 50+
        regime_shift = 0
        if day_offset >= 50:
            regime_shift = 200

        # === Colunas numéricas ===

        # VLR_SALD_AVNC_OPCR: saldo médio ~5000, std ~1500
        vlr_sald_avnc = rng.normal(
            loc=5000 * drift_factor * outlier_factor + regime_shift,
            scale=1500,
            size=n_rows,
        ).clip(0)

        # VLR_PARC_OPCR: parcela ~500, std ~150
        vlr_parc = rng.normal(
            loc=500 * drift_factor,
            scale=150,
            size=n_rows,
        ).clip(0)

        # VLR_CNTR_OPCR: valor contrato ~20000, std ~8000
        vlr_cntr = rng.normal(
            loc=20000,
            scale=8000,
            size=n_rows,
        ).clip(0)

        # VLR_SALD_DEVE_CTBL: muitos zeros (zero-inflated)
        vlr_deve = np.where(
            rng.random(n_rows) < 0.7,  # 70% zeros
            0.0,
            rng.exponential(scale=1000, size=n_rows),
        )

        # === Coluna categórica: COD_SITU_OPCR ===
        # Distribuição: '1' ~90%, '2' ~7%, '3' ~3%
        # Com variação leve por dia
        cat_probs = [0.90, 0.07, 0.03]
        # No dia 30-35, categoria '2' sobe para 12%
        if 30 <= day_offset <= 35:
            cat_probs = [0.85, 0.12, 0.03]

        cod_situ = rng.choice(
            ['1', '2', '3'],
            size=n_rows,
            p=cat_probs,
        )

        # === Chave primária ===
        num_ctrt = [f"CTRT{day_offset:03d}{i:06d}" for i in range(n_rows)]

        # === Montar DataFrame ===
        day_df = pd.DataFrame({
            "DT_REF": current_date.isoformat(),
            "NUM_CTRT_OPCR": num_ctrt,
            "VLR_SALD_AVNC_OPCR": vlr_sald_avnc.round(2),
            "VLR_PARC_OPCR": vlr_parc.round(2),
            "VLR_CNTR_OPCR": vlr_cntr.round(2),
            "VLR_SALD_DEVE_CTBL": vlr_deve.round(2),
            "COD_SITU_OPCR": cod_situ,
        })

        all_rows.append(day_df)

    df = pd.concat(all_rows, ignore_index=True)

    # Introduzir nulls esparsos em VLR_PARC_OPCR (~2%)
    null_mask = rng.random(len(df)) < 0.02
    df.loc[null_mask, "VLR_PARC_OPCR"] = None

    # Salvar como parquet (simula formato real)
    output_path = Path(output_dir) / "tb_operacoes_credito.parquet"
    df.to_parquet(output_path, index=False)
    print(f"Mock data gerado: {output_path}")
    print(f"  {len(df)} rows, {n_days} dias")
    print(f"  Colunas: {list(df.columns)}")

    # Salvar também como CSV (para inspeção fácil)
    csv_path = Path(output_dir) / "tb_operacoes_credito.csv"
    df.to_csv(csv_path, index=False)

    return df


if __name__ == "__main__":
    generate_mock_data()
```

### 4.2 Características dos dados sintéticos (by design)

| Característica | Onde aparece | Propósito |
|----------------|-------------|-----------|
| Série estável | VLR_CNTR_OPCR (sem drift) | Testar banda simples |
| Drift leve | VLR_SALD_AVNC_OPCR (+0.1%/dia) | Testar detecção de drift |
| Outlier isolado | VLR_SALD_AVNC_OPCR dia 45 (+35%) | Testar backtest/scoring |
| Regime change | VLR_SALD_AVNC_OPCR dia 50+ (+200 absoluto) | Testar estabilidade |
| Zero-inflated | VLR_SALD_DEVE_CTBL (70% zeros) | Testar edge case |
| Nulls esparsos | VLR_PARC_OPCR (~2% null) | Testar completude |
| Shift categórico | COD_SITU_OPCR dias 30-35 | Testar freq dinâmica |
| Row count variável | ±500 por dia | Testar RowCount |

### 4.3 Carregar dados no DuckDB (mock Athena)

```python
# infra/mock_athena.py
"""
Backend mock que usa DuckDB para simular Athena localmente.
Carrega dados sintéticos e permite executar queries SQL reais.
"""

import duckdb
from pathlib import Path
from typing import Optional


class MockAthenaBackend:
    """Simula Athena usando DuckDB + dados locais.

    Uso:
        backend = MockAthenaBackend()
        backend.load_table("db_credito", "tb_operacoes_credito", "mock_data/tb_operacoes_credito.parquet")
        results = backend.execute("SELECT COUNT(*) FROM tb_operacoes_credito")
    """

    def __init__(self, database: str = ":memory:"):
        self.conn = duckdb.connect(database)
        self._tables: dict[str, str] = {}  # schema.table → table_name

    def load_table(
        self,
        schema: str,
        table: str,
        data_path: str,
    ):
        """Carrega arquivo (parquet/csv) como tabela no DuckDB.

        No DuckDB não usamos schema separado, então mapeamos
        'schema.table' → 'table' internamente.
        """
        path = Path(data_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {data_path}")

        full_name = f"{schema}.{table}"

        if path.suffix == ".parquet":
            self.conn.execute(
                f'CREATE OR REPLACE TABLE "{table}" AS '
                f"SELECT * FROM read_parquet('{path}')"
            )
        elif path.suffix == ".csv":
            self.conn.execute(
                f'CREATE OR REPLACE TABLE "{table}" AS '
                f"SELECT * FROM read_csv_auto('{path}')"
            )
        else:
            raise ValueError(f"Formato não suportado: {path.suffix}")

        self._tables[full_name] = table
        count = self.conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        print(f"Loaded {full_name} → {table} ({count} rows)")

    def execute(self, sql: str) -> list[dict]:
        """Executa query e retorna lista de dicts."""
        result = self.conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def execute_df(self, sql: str):
        """Executa query e retorna DataFrame."""
        return self.conn.execute(sql).fetchdf()

    def get_columns(self, table: str) -> list[dict]:
        """Retorna colunas e tipos (simula DESCRIBE)."""
        result = self.conn.execute(
            f"SELECT column_name, data_type "
            f"FROM information_schema.columns "
            f"WHERE table_name = '{table}'"
        ).fetchall()
        return [{"name": row[0], "type": row[1]} for row in result]

    def table_exists(self, table: str) -> bool:
        """Verifica se a tabela existe."""
        try:
            self.conn.execute(f'SELECT 1 FROM "{table}" LIMIT 1')
            return True
        except duckdb.CatalogException:
            return False

    def close(self):
        self.conn.close()
```

---

## 5. Configuração Multi-Ambiente (Local → Prod)

### 5.1 Arquivo de configuração

```python
# config.py
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
```

### 5.2 Arquivos de ambiente

```bash
# .env.local (desenvolvimento — commitar como exemplo)
GDQ_ENV=local
GDQ_MOCK_DATA_DIR=mock_data
```

```bash
# .env.dev (seu acesso pessoal — NÃO commitar)
GDQ_ENV=dev
GDQ_ATHENA_REGION=us-east-1
GDQ_ATHENA_WORKGROUP=meu-workgroup
GDQ_ATHENA_S3_OUTPUT=s3://meu-bucket/athena-results/
GDQ_AWS_PROFILE=meu-profile-dev
```

```bash
# .env.prod (produção — NÃO commitar)
GDQ_ENV=prod
GDQ_ATHENA_REGION=us-east-1
GDQ_ATHENA_WORKGROUP=prod-workgroup
GDQ_ATHENA_S3_OUTPUT=s3://prod-bucket/athena-results/
# Sem AWS_PROFILE — usa IAM role da instância/container
```

### 5.3 AthenaClient unificado (mock + real)

```python
# infra/athena_client.py
"""
Client unificado que funciona com DuckDB (local) ou Athena real (dev/prod).
A interface é idêntica — só muda o backend.
"""

import time
import pandas as pd
from typing import Optional
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
        self._backend = None

        if config.athena.mode == AthenaMode.MOCK:
            self.dialect = SQLDialect.DUCKDB
            self._init_mock()
        else:
            self.dialect = SQLDialect.ATHENA
            self._init_real()

    def _init_mock(self):
        """Inicializa backend DuckDB com dados mock."""
        from infra.mock_athena import MockAthenaBackend
        self._backend = MockAthenaBackend()
        # Carregar tabelas mock automaticamente
        mock_dir = self.config.athena.mock_data_dir
        import os
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

        # Se tem profile, usar (dev). Senão, usa role (prod).
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
        cache_hit = False
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
                cache_hit=cache_hit,
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
                f"DESCRIBE \"{schema}\".\"{table}\"",
                query_name="describe_table",
                dataset=f"{schema}.{table}",
            )
            return [
                {"name": row["col_name"], "type": row["data_type"]}
                for _, row in df.iterrows()
            ]
```

### 5.4 Diagrama: como muda entre ambientes

```
LOCAL (Windows + Claude Code)
├─ .env.local
├─ GDQ_ENV=local
├─ AthenaClient → DuckDB
├─ SQLDialect = DUCKDB
├─ Dados: mock_data/*.parquet
└─ Queries: templates SQL (mesmos)

DEV (seu acesso pessoal)
├─ .env.dev
├─ GDQ_ENV=dev
├─ AthenaClient → PyAthena
├─ SQLDialect = ATHENA
├─ Auth: aws configure --profile meu-profile
├─ Dados: tabelas reais no catálogo Glue
└─ Queries: templates SQL (mesmos)

PROD (servidor/container na empresa)
├─ .env.prod (ou variáveis de ambiente do container)
├─ GDQ_ENV=prod
├─ AthenaClient → PyAthena
├─ SQLDialect = ATHENA
├─ Auth: IAM role da instância/container (sem profile)
├─ Dados: tabelas reais no catálogo Glue
└─ Queries: templates SQL (mesmos)
```

### 5.5 Setup AWS CLI para dev (quando for conectar real)

```powershell
# Instalar AWS CLI (se não tiver)
winget install Amazon.AWSCLI

# Configurar named profile para desenvolvimento
aws configure --profile gdq-dev
# AWS Access Key ID: [sua key]
# AWS Secret Access Key: [sua secret]
# Default region name: us-east-1
# Default output format: json

# Testar
aws athena list-work-groups --profile gdq-dev

# No .env.dev, referenciar:
# GDQ_AWS_PROFILE=gdq-dev
```

---

## 6. Validação do Setup

### 6.1 Script de validação

```python
# scripts/validate_setup.py
"""
Valida que o ambiente está configurado corretamente.
Roda como primeiro teste após setup.
"""

import sys


def validate():
    errors = []
    warnings = []

    # 1. Python version
    if sys.version_info < (3, 11):
        errors.append(f"Python >= 3.11 necessário (atual: {sys.version})")

    # 2. Imports essenciais
    try:
        import streamlit
        print(f"✅ streamlit {streamlit.__version__}")
    except ImportError:
        errors.append("❌ streamlit não instalado")

    try:
        import plotly
        print(f"✅ plotly {plotly.__version__}")
    except ImportError:
        errors.append("❌ plotly não instalado")

    try:
        import duckdb
        print(f"✅ duckdb {duckdb.__version__}")
    except ImportError:
        errors.append("❌ duckdb não instalado")

    try:
        import pandas
        print(f"✅ pandas {pandas.__version__}")
    except ImportError:
        errors.append("❌ pandas não instalado")

    try:
        import jinja2
        print(f"✅ jinja2 {jinja2.__version__}")
    except ImportError:
        errors.append("❌ jinja2 não instalado")

    try:
        import pyathena
        print(f"✅ pyathena {pyathena.__version__}")
    except ImportError:
        warnings.append("⚠️ pyathena não instalado (necessário apenas para Athena real)")

    # 3. Config
    try:
        from config import load_config
        config = load_config()
        print(f"✅ Config carregada: env={config.environment.value}, mode={config.athena.mode.value}")
    except Exception as e:
        errors.append(f"❌ Erro ao carregar config: {e}")

    # 4. Mock data
    from pathlib import Path
    mock_dir = Path("mock_data")
    if mock_dir.exists():
        files = list(mock_dir.glob("*.parquet")) + list(mock_dir.glob("*.csv"))
        if files:
            print(f"✅ Mock data: {len(files)} arquivo(s) em {mock_dir}")
        else:
            warnings.append(f"⚠️ Diretório {mock_dir} existe mas sem dados. Rode: python scripts/generate_mock_data.py")
    else:
        warnings.append(f"⚠️ Diretório {mock_dir} não existe. Rode: python scripts/generate_mock_data.py")

    # 5. DuckDB query test
    try:
        import duckdb
        conn = duckdb.connect(":memory:")
        result = conn.execute("SELECT 1 + 1 as test").fetchone()
        assert result[0] == 2
        print("✅ DuckDB query engine OK")
        conn.close()
    except Exception as e:
        errors.append(f"❌ DuckDB query test falhou: {e}")

    # 6. Mock Athena integration test
    if mock_dir.exists() and list(mock_dir.glob("*.parquet")):
        try:
            from config import load_config
            from infra.athena_client import AthenaClient
            config = load_config()
            client = AthenaClient(config)
            result = client.execute(
                "SELECT COUNT(*) as cnt FROM tb_operacoes_credito"
            )
            count = result[0]["cnt"]
            print(f"✅ Mock Athena query OK ({count} rows)")
        except Exception as e:
            errors.append(f"❌ Mock Athena query falhou: {e}")

    # Resultado
    print("\n" + "=" * 50)
    if errors:
        print("❌ SETUP INCOMPLETO:")
        for e in errors:
            print(f"   {e}")
    else:
        print("✅ SETUP OK — pronto para desenvolver!")

    if warnings:
        print("\n⚠️ Avisos:")
        for w in warnings:
            print(f"   {w}")

    return len(errors) == 0


if __name__ == "__main__":
    success = validate()
    sys.exit(0 if success else 1)
```

### 6.2 Ordem de execução do setup

```powershell
# 1. Criar venv e instalar deps
python -m venv .venv
.venv\Scripts\activate
pip install streamlit plotly pandas duckdb pyathena boto3 jinja2 pytest numpy pyarrow

# 2. Criar .env.local
echo "GDQ_ENV=local" > .env.local
echo "GDQ_MOCK_DATA_DIR=mock_data" >> .env.local

# 3. Gerar dados mock
python scripts/generate_mock_data.py

# 4. Validar setup
python scripts/validate_setup.py

# 5. Testar Streamlit (criar app.py mínimo primeiro)
streamlit run app.py

# 6. Iniciar Claude Code
claude
```

---

## 7. Tarefas para Claude Code (Sprint 0)

Após completar o setup manual, usar Claude Code para criar os arquivos base:

### Tarefa 0.1 — Esqueleto do projeto

```
Crie a estrutura de pastas e __init__.py conforme docs/technical_spec_v1.md seção 2.
Crie config.py conforme docs/setup_guide.md seção 5.1.
Crie .env.local, .env.example, .gitignore.
```

### Tarefa 0.2 — SQL Dialect + Query Builder

```
Implemente infra/sql_dialect.py com adaptação Athena↔DuckDB.
Implemente infra/query_builder.py com suporte a dialeto nos templates.
Crie queries/templates/numeric_history.sql compatível com ambos dialetos.
Teste com DuckDB local.
```

### Tarefa 0.3 — Mock Athena Backend

```
Implemente infra/mock_athena.py com DuckDB.
Implemente infra/athena_client.py unificado (mock + real).
Implemente infra/query_logger.py.
Teste: carregar parquet mock, executar query de contagem, verificar log.
```

### Tarefa 0.4 — Geração de dados mock

```
Implemente scripts/generate_mock_data.py com as características definidas
em docs/setup_guide.md seção 4.2 (drift, outlier, regime change, zero-inflated, etc.).
Implemente scripts/validate_setup.py.
Rode ambos e confirme que passam.
```

### Tarefa 0.5 — App.py mínimo + smoke test

```
Crie app.py com página inicial que:
1. Mostra ambiente atual (local/dev/prod)
2. Mostra status da conexão (DuckDB/Athena)
3. Lista tabelas disponíveis
4. Permite selecionar uma tabela e ver suas colunas

Rode streamlit run app.py e confirme que funciona.
```

---

## 8. Requirements.txt Final

```
# Core
streamlit>=1.30
plotly>=5.18
pandas>=2.1
numpy>=1.26

# Athena (mock local)
duckdb>=1.0
pyarrow>=14.0

# Athena (real - dev/prod)
pyathena>=3.0
boto3>=1.34

# Templates
jinja2>=3.1

# Testes
pytest>=8.0

# Dados
pyarrow>=14.0
```

---

## Checklist de Validação do Sprint 0

- [ ] Python 3.11+ instalado e venv criada
- [ ] Claude Code instalado e autenticado
- [ ] Estrutura de pastas criada
- [ ] Dependências instaladas
- [ ] .env.local configurado
- [ ] Dados mock gerados (mock_data/*.parquet)
- [ ] `validate_setup.py` passa 100%
- [ ] DuckDB executa query na tabela mock
- [ ] AthenaClient funciona no modo mock
- [ ] QueryLogger registra queries
- [ ] SQLDialect adapta funções Athena↔DuckDB
- [ ] `streamlit run app.py` abre sem erro
- [ ] CLAUDE.md e docs/ copiados para o repositório
- [ ] Git commit inicial feito
