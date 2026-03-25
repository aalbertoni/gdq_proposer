# GDQ Rule Proposer — Especificação Técnica v1

> **Status:** Draft v1 — pronto para desenvolvimento com Claude Code
> **Última atualização:** 2026-02-24
> **Autor:** Alexandre (refinamento colaborativo)

---

## 1. Visão Geral

### 1.1 Problema

Propor regras de qualidade de dados (AWS Glue Data Quality) para tabelas existentes é um processo manual, demorado e inconsistente entre analistas. Falta uma ferramenta que:

- Analise o histórico real dos dados via Athena
- Proponha regras com bandas estatísticas calibradas
- Permita ao usuário **avaliar visualmente** e ajustar antes de cadastrar
- Gere a **sintaxe GDQ exata** pronta para copiar/cadastrar

### 1.2 Solução

Aplicação **Streamlit** que funciona como **orquestrador leve**: toda computação estatística acontece via SQL pushdown no **Athena**. O app recebe apenas resultados agregados, monta gráficos interativos de calibração e gera sintaxe GDQ validada.

### 1.3 Princípios de Design

| Princípio | Implicação |
|-----------|-----------|
| **Athena-first** | Zero processamento estatístico no servidor; tudo via SQL pushdown |
| **Assistente de decisão** | Nunca gerar regras cegas — sempre exibir evidência e permitir calibração |
| **Falhar cedo** | Validar metadados antes de queries caras |
| **Separação de concerns** | Perfil estatístico ≠ sintaxe GDQ (motores trocáveis) |
| **Segurança por design** | Queries parametrizadas, whitelist de identificadores, limites de custo |

### 1.4 Arquitetura em Camadas

```
┌─────────────────────────────────────────────────────────┐
│  Streamlit UI                                            │
│  ├─ 01_setup.py        Setup / Discovery                 │
│  ├─ 02_explore.py      Explore / Calibração              │
│  ├─ 03_review.py       Rule Review / Export              │
│  └─ 04_presets.py      Presets / Histórico de sessões    │
├─────────────────────────────────────────────────────────┤
│  Application Services (orquestração)                     │
│  ├─ DatasetService      metadata, schema, partitions     │
│  ├─ ProfilingService    classificação de colunas         │
│  ├─ AnalysisService     históricos e bandas              │
│  ├─ ProposalService     propostas e scoring              │
│  └─ ExportService       sintaxe GDQ + txt/json           │
├─────────────────────────────────────────────────────────┤
│  Domain / Core (sem dependência de UI)                   │
│  ├─ Models              configs, proposals, metrics       │
│  ├─ StatisticalEngine   bandas, baselines, backtest      │
│  ├─ RuleScoring         avaliação da qualidade da regra  │
│  ├─ ColumnClassifier    classificação semântica          │
│  └─ GDQRuleGenerator    conversão proposta → sintaxe     │
├─────────────────────────────────────────────────────────┤
│  Infrastructure                                          │
│  ├─ AthenaClient        boto3/pyathena + retry + cache   │
│  ├─ QueryTemplates      Jinja2 parametrizados            │
│  ├─ Cache               st.cache_data + TTL              │
│  ├─ Logging             query log + tempo de execução    │
│  └─ Config/Secrets      .env / AWS credentials           │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Estrutura do Projeto

```
gdq-proposer/
├── app.py                          # Entry point Streamlit
├── config.py                       # Settings globais
├── pages/
│   ├── 01_setup.py                 # Wizard de configuração (validação progressiva)
│   ├── 02_explore.py               # Exploração e calibração
│   ├── 03_review.py                # Revisão e export de regras
│   └── 04_presets.py               # Presets e sessões salvas
├── services/
│   ├── dataset_service.py          # Metadata discovery
│   ├── profiling_service.py        # Column classification
│   ├── analysis_service.py         # Análise histórica
│   ├── proposal_service.py         # Geração de propostas + scoring
│   └── export_service.py           # Geração de sintaxe + export
├── core/
│   ├── models/
│   │   ├── dataset_config.py       # DatasetConfig
│   │   ├── column_profile.py       # ColumnProfile
│   │   ├── dual_guard.py           # DualGuardSpec, MetricRef, FormattingProfile
│   │   ├── rule_proposal.py        # RuleProposal
│   │   ├── rule_selection.py       # RuleSelection (carrinho)
│   │   ├── baseline.py             # BaselineStrategy
│   │   └── enums.py                # SemanticType, RuleType, etc.
│   ├── statistical_engine.py       # Bandas, baselines (funções puras)
│   ├── rule_scoring.py             # Avaliação composta (coverage+stability+interp+cost)
│   ├── column_classifier.py        # Classificação semântica (2 níveis)
│   ├── gdq_renderer.py             # DualGuardSpec → string GDQ (motor de sintaxe)
│   ├── gdq_rule_generator.py       # Proposta → DualGuardSpec → sintaxe
│   └── backtest.py                 # Avaliação histórica pass/fail
├── infra/
│   ├── athena_client.py            # QueryExecutor protocol + Athena/DuckDB executors
│   ├── sql_adapter.py              # SQLDialect (Athena ↔ DuckDB compatibility)
│   ├── query_builder.py            # Montagem de queries a partir de templates
│   ├── query_safety.py             # Validação de identificadores / SQL safety
│   ├── cost_estimator.py           # Estimativa de custo + guardrails
│   └── query_logger.py             # Logging estruturado (QueryLogEntry)
├── queries/
│   └── templates/                  # Templates SQL Jinja2
│       ├── metadata_discovery.sql
│       ├── column_sample.sql
│       ├── numeric_history.sql
│       ├── categorical_distribution.sql
│       ├── categorical_domain.sql
│       ├── row_count_history.sql
│       ├── uniqueness_check.sql
│       └── completeness_check.sql
├── strategies/
│   ├── row_count_strategy.py       # Protocol + GenericBandStrategy
│   └── baseline_strategy.py        # Protocol para cálculo de baseline
├── tests/
│   ├── fixtures/                   # Datasets sintéticos
│   │   ├── stable_series.py
│   │   ├── drift_series.py
│   │   ├── seasonal_series.py
│   │   ├── outlier_series.py
│   │   ├── category_shift.py
│   │   ├── sparse_numeric_series.py    # muitos nulls
│   │   ├── zero_inflated_series.py     # muitos zeros
│   │   └── regime_change_series.py     # mudança brusca de patamar
│   ├── test_statistical_engine.py
│   ├── test_rule_scoring.py
│   ├── test_column_classifier.py
│   ├── test_gdq_renderer.py           # testes contra exemplos de produção
│   ├── test_gdq_rule_generator.py
│   ├── test_backtest.py
│   └── test_query_safety.py
├── presets/                        # Configs salvas (JSON)
├── mock_data/                      # CSVs gerados para dev local (git-ignored)
├── scripts/
│   ├── generate_mock_data.py       # Gera dados mock realistas
│   └── validate_setup.py          # Valida ambiente completo
├── docs/
│   ├── technical_spec_v1.md        # Este documento
│   ├── gdq_syntax_reference.md     # Referência de sintaxe GDQ (produção)
│   └── evolution_dynamic_sql_and_ai.md  # Roadmap pós-MVP
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── CLAUDE.md                       # Instruções para Claude Code
```

---

## 3. Modelos de Dados (Domain Models)

### 3.1 DatasetConfig

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LookbackMode(str, Enum):
    LAST_N_PERIODS = "last_n_periods"
    LAST_X_DAYS = "last_x_days"


class GrainType(str, Enum):
    DAILY = "daily"
    MONTHLY = "monthly"
    TIMESTAMP = "timestamp"
    CUSTOM = "custom"


class PartitionMethod(str, Enum):
    INCREMENTAL = "incremental"
    # Cada partição contém APENAS dados novos daquele período.
    # Partição = eixo temporal = coluna de data para análise.
    # Ex: tb_operacoes com dt_ref=2026-01-15 contém só ops do dia 15.
    # Para análise: GROUP BY partição → cada partição = 1 processamento.

    FULL_SNAPSHOT = "full_snapshot"
    # Cada partição contém a foto COMPLETA dos dados naquele momento.
    # Partição = data de carga/processamento (eixo temporal para GDQ).
    # Coluna de data para análise pode ser outra (ex: DT_ABERTURA).
    # Para análise: filtrar WHERE partição = 'última carga',
    # ou GROUP BY partição para comparar entre cargas.

    NON_PARTITIONED = "non_partitioned"
    # Tabela sem partição física.
    # Eixo temporal determinado por uma coluna de data interna.
    # Para análise: GROUP BY coluna de data.


@dataclass
class DatasetConfig:
    """Configuração da tabela alvo para análise.

    Conceitos-chave:
    - partition_columns: lista de colunas físicas de partição no S3/Glue
    - partition_column: atalho legacy para partition_columns[0] (backward compat)
    - partition_method: como os dados são organizados na partição
    - date_column: coluna que define o eixo temporal para análise/GDQ
    - Quando method=INCREMENTAL: partition_column == date_column (geralmente)
    - Quando method=FULL_SNAPSHOT: partition_column ≠ date_column

    Multi-partition: partition_columns pode ter N colunas (ex: ano, mes, dia).
    Cada coluna tem seu formato em partition_formats e tipo em partition_is_integer_map.
    Os campos legacy (partition_column, partition_format, partition_is_integer) são
    mantidos para backward compat e refletem o valor da primeira coluna.
    """

    # === Identificação da tabela ===
    schema: str
    table: str

    # === Particionamento ===
    partition_method: PartitionMethod = PartitionMethod.INCREMENTAL

    # --- Legacy fields (backward compat — sincronizados via __post_init__) ---
    partition_column: Optional[str] = None
    partition_format: Optional[str] = None
    partition_is_integer: bool = False

    # --- Campos canônicos multi-partição (source of truth) ---
    partition_columns: list[str] = field(default_factory=list)
    # Lista de colunas de partição (ex: ["ano_particao", "mes_particao", "dia_particao"])
    partition_formats: dict[str, Optional[str]] = field(default_factory=dict)
    # Formato strftime por coluna (ex: {"ano_particao": "%Y", "mes_particao": "%m"})
    # None para colunas com tipo nativo (date/timestamp)
    partition_is_integer_map: dict[str, bool] = field(default_factory=dict)
    # True se a coluna de partição é inteira (ex: 20260315 em vez de "2026-03-15")

    # === Eixo temporal (para análise e regras GDQ) ===
    date_column: str = ""
    # Coluna que define o "processamento" para fins de regras.
    # Em INCREMENTAL: geralmente = partition_column (ex: "dt_ref")
    # Em FULL_SNAPSHOT: = partition_column (dt_carga) para eixo temporal
    # OU = coluna interna (DT_ABERTURA) para análise de conteúdo

    temporal_axis_column: Optional[str] = None
    # Coluna usada como eixo temporal no GROUP BY das queries de histórico.
    # Se None, usa partition_column (INCREMENTAL) ou date_column.
    # Em FULL_SNAPSHOT: normalmente = partition_column (cada snapshot = 1 ponto)
    # Isso garante que cada "período" no histórico = 1 execução do GDQ.

    grain_type: GrainType = GrainType.DAILY
    date_expression: Optional[str] = None
    # Expressão SQL para normalizar a coluna de data.
    # Ex.: "date_parse(dt_ref, '%Y.%m.%d')"
    # Ex.: "date_trunc('month', dt_evento)"
    # Se None, usa a coluna diretamente.

    # === Lookback ===
    lookback_mode: LookbackMode = LookbackMode.LAST_N_PERIODS
    lookback_value: int = 30

    # === Filtros ===
    base_filter_sql: Optional[str] = None
    # Filtro WHERE aplicado em TODAS as queries.
    # Ex.: "IND_ATIVO = 1"
    # Ex.: "COD_SEGMENTO != 'TESTE'"
    # Muito usado em FULL_SNAPSHOT para filtrar registros relevantes.

    # === Colunas selecionadas ===
    selected_columns: list[str] = field(default_factory=list)
    unique_key_columns: list[str] = field(default_factory=list)

    @property
    def effective_temporal_axis(self) -> str:
        """Coluna usada como eixo temporal nas queries de histórico.

        Lógica:
        1. Se temporal_axis_column foi definido explicitamente, usar
        2. Se INCREMENTAL, usar partition_column (= date_column)
        3. Se FULL_SNAPSHOT, usar partition_column (cada snapshot = 1 ponto)
        4. Se NON_PARTITIONED, usar date_column
        """
        if self.temporal_axis_column:
            return self.temporal_axis_column
        if self.partition_method == PartitionMethod.INCREMENTAL:
            return self.partition_column or self.date_column
        if self.partition_method == PartitionMethod.FULL_SNAPSHOT:
            return self.partition_column or self.date_column
        return self.date_column

    @property
    def is_multi_partition(self) -> bool:
        """True se a tabela tem mais de uma coluna de partição."""
        return len(self.partition_columns) > 1
```

**Partition pruning** é implementado em `infra/partition_pruning.py`:
- Suporta partição única e múltiplas colunas (ex: ano/mes/dia)
- Multi-coluna gera predicado AND combinado: `"ano" >= 2026 AND "mes" >= 01 AND "dia" >= 25`
- NUNCA aplica função sobre a coluna de partição (preserva pruning do Athena)
- `QueryBuilder.resolve_partition_filter()` é o ponto de entrada para gerar o predicado

### Exemplos de configuração por cenário

```python
# === Cenário 1: Tabela incremental (partição = data) ===
# tb_operacoes_incremental: dt_ref é partição E coluna de data
# Cada partição = dados novos do dia
config_incremental = DatasetConfig(
    schema="gdq_test_db",
    table="tb_operacoes_incremental",
    partition_method=PartitionMethod.INCREMENTAL,
    partition_column="dt_ref",
    date_column="dt_ref",                    # = partition (coincide)
    # temporal_axis_column não precisa (inferido = dt_ref)
    grain_type=GrainType.DAILY,
    lookback_value=30,
    selected_columns=["VLR_SALD_AVNC_OPCR", "VLR_PARC_OPCR", "COD_SITU_OPCR"],
    unique_key_columns=["NUM_CTRT_OPCR"],
)

# === Cenário 2: Full snapshot (partição ≠ coluna de data para análise) ===
# tb_cadastro_full: dt_carga é partição, DT_ABERTURA é data de negócio
# Cada partição = foto completa do cadastro
config_full_snapshot = DatasetConfig(
    schema="gdq_test_db",
    table="tb_cadastro_full",
    partition_method=PartitionMethod.FULL_SNAPSHOT,
    partition_column="dt_carga",             # partição física
    date_column="DT_ABERTURA",               # data de negócio (para análise)
    temporal_axis_column="dt_carga",          # eixo temporal = cada snapshot
    # ^ Cada dt_carga é um "processamento" para fins de regra GDQ
    grain_type=GrainType.DAILY,
    lookback_value=30,
    base_filter_sql="IND_ATIVO = 1",         # só clientes ativos
    selected_columns=["VLR_LIMITE", "VLR_SALDO", "COD_SEGMENTO", "QTD_PRODUTOS"],
    unique_key_columns=["ID_CLIENTE"],
)

# === Cenário 3: Tabela não particionada ===
# Dados em tabela flat com coluna de data interna
config_non_partitioned = DatasetConfig(
    schema="analytics_db",
    table="tb_eventos",
    partition_method=PartitionMethod.NON_PARTITIONED,
    partition_column=None,
    date_column="dt_evento",
    grain_type=GrainType.DAILY,
    date_expression="date_trunc('day', dt_evento)",
    lookback_value=30,
)

# === Cenário 4: Multi-partição (ano/mes/dia em colunas separadas) ===
# tb_operacoes: partições S3 = ano_particao=2026/mes_particao=03/dia_particao=25
# Eixo temporal = coluna de data separada (dt_ref)
config_multi_partition = DatasetConfig(
    schema="datalake_raw",
    table="tb_operacoes_ymd",
    partition_method=PartitionMethod.INCREMENTAL,
    partition_columns=["ano_particao", "mes_particao", "dia_particao"],
    partition_formats={
        "ano_particao": "%Y",
        "mes_particao": "%m",
        "dia_particao": "%d",
    },
    partition_is_integer_map={
        "ano_particao": True,
        "mes_particao": True,
        "dia_particao": True,
    },
    date_column="dt_ref",
    temporal_axis_column="dt_ref",    # eixo temporal = coluna date, não partição
    grain_type=GrainType.DAILY,
    lookback_value=30,
    selected_columns=["VLR_SALDO", "COD_TIPO"],
)
# Pruning gerado: "ano_particao" >= 2026 AND "mes_particao" >= 02 AND "dia_particao" >= 23
```

### 3.2 ColumnProfile

```python
class SemanticType(str, Enum):
    NUMERIC = "numeric"
    CATEGORICAL_LOW_CARDINALITY = "categorical_low"    # domínio
    CATEGORICAL_MID_CARDINALITY = "categorical_mid"    # top-K
    CATEGORICAL_HIGH_CARDINALITY = "categorical_high"  # identificador
    DATETIME = "datetime"
    IDENTIFIER = "identifier"
    FREE_TEXT = "free_text"
    UNKNOWN = "unknown"


@dataclass
class ColumnProfile:
    """Perfil de uma coluna após classificação."""
    column_name: str
    athena_type: str                          # tipo físico Athena (int, string, etc.)
    inferred_semantic_type: SemanticType
    user_override_type: Optional[SemanticType] = None
    # Override manual sempre prevalece

    # Métricas de profiling (calculadas com amostra)
    total_count: int = 0
    non_null_count: int = 0
    distinct_count: int = 0
    null_ratio: float = 0.0
    distinct_ratio: float = 0.0               # distinct / non_null
    numeric_cast_ratio: float = 0.0           # % castável para número
    sample_values: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def effective_type(self) -> SemanticType:
        """Tipo efetivo: override manual > inferência."""
        return self.user_override_type or self.inferred_semantic_type

    @property
    def is_numeric(self) -> bool:
        return self.effective_type == SemanticType.NUMERIC

    @property
    def is_categorical(self) -> bool:
        return self.effective_type in (
            SemanticType.CATEGORICAL_LOW_CARDINALITY,
            SemanticType.CATEGORICAL_MID_CARDINALITY,
            SemanticType.CATEGORICAL_HIGH_CARDINALITY,
        )
```

### 3.3 BaselineStrategy

```python
class BaselineMethod(str, Enum):
    LAST_N_PERIODS = "last_n_periods"
    LAST_X_DAYS = "last_x_days"
    ROLLING_WINDOW_EXCLUDE_CURRENT = "rolling_exclude_current"
    SAME_WEEKDAY = "same_weekday"             # evolução futura
    SAME_DAY_OF_MONTH = "same_day_of_month"   # evolução futura


@dataclass
class BaselineStrategy:
    """Como calcular a baseline para propor thresholds."""
    method: BaselineMethod = BaselineMethod.LAST_N_PERIODS
    n_periods: int = 20
    n_sigma: float = 2.0       # para bandas de desvio padrão
    margin_pct: float = 0.10   # margem percentual (alternativa a sigma)
    percentile_lower: float = 0.05
    percentile_upper: float = 0.95
    min_history_points: int = 7  # mínimo para sugerir banda
```

### 3.4 DualGuardSpec (Representação intermediária)

```python
class MetricRef(str, Enum):
    """Tipo de métrica GDQ para dual guard."""
    MEAN = "Mean"
    STANDARD_DEVIATION = "StandardDeviation"
    ROW_COUNT = "RowCount"
    CUSTOM_SQL = "CustomSql"


@dataclass
class FormattingProfile:
    """Diferenças de formatação por tipo de regra.

    Mean/StdDev: K inteiro, buffer 0.01, margem como 'avg * factor'
    RowCount: K float (2.0), sem buffer, margem como 'avg - (avg * pct)', avg * 1.0
    CustomSql: SQL entre aspas duplas, valores entre aspas simples, from primary
    """
    k_as_float: bool = False         # True para RowCount (2.0), False para Mean/StdDev (2)
    include_buffer: bool = True      # True para Mean/StdDev, False para RowCount
    avg_multiply_one: bool = False   # True para RowCount (avg * 1.0)
    margin_format: str = "factor"    # "factor" → avg * 0.9/1.1; "delta" → avg - (avg * 0.1)


# Profiles pré-definidos
MEAN_PROFILE = FormattingProfile()
STDDEV_PROFILE = FormattingProfile()
ROWCOUNT_PROFILE = FormattingProfile(
    k_as_float=True,
    include_buffer=False,
    avg_multiply_one=True,
    margin_format="delta",
)


@dataclass
class DualGuardSpec:
    """Representação intermediária do padrão dual guard.

    Nunca gerar string GDQ diretamente — sempre montar DualGuardSpec
    e passar pelo DualGuardRenderer.

    A representação é:
      (banda_sigma) OR (banda_margem)

    Onde:
      banda_sigma: metric >= avg(last(N)) - K*std(last(N)) [-buffer]
                   AND metric <= avg(last(N)) + K*std(last(N)) [+buffer]
      banda_margem: metric >= avg(last(N)) * lo_margin [-buffer]
                    AND metric <= avg(last(N)) * hi_margin [+buffer]
    """
    metric: MetricRef
    target: str = ""               # nome da coluna (vazio para RowCount)
    n_periods: int = 30
    n_sigma: float = 2             # int para Mean/StdDev, float para RowCount
    margin_pct: float = 0.10
    buffer: float = 0.01           # 0 para RowCount
    profile: FormattingProfile = None
    # Se None, inferido automaticamente do metric type
    custom_sql_expression: str = ""  # Apenas para MetricRef.CUSTOM_SQL

    def __post_init__(self):
        if self.profile is None:
            if self.metric == MetricRef.MEAN:
                self.profile = MEAN_PROFILE
            elif self.metric == MetricRef.STANDARD_DEVIATION:
                self.profile = STDDEV_PROFILE
            elif self.metric == MetricRef.ROW_COUNT:
                self.profile = ROWCOUNT_PROFILE
                self.buffer = 0
                self.n_sigma = float(self.n_sigma)
```

### 3.5 RuleProposal

```python
class RuleType(str, Enum):
    # Numéricas (built-in GDQ com dual guard dinâmico)
    MEAN_DUAL_GUARD = "mean_dual_guard"              # Mean com avg(last(N))/std(last(N))
    STDDEV_DUAL_GUARD = "stddev_dual_guard"          # StandardDeviation com avg(last(N))/std(last(N))
    NUMERIC_PERCENTILE_BAND = "numeric_percentile"   # Análise: percentis P5/P95
    # Categóricos / Domínio
    ALLOWED_VALUES = "allowed_values"                # ColumnValues ... in [...]
    CATEGORY_FREQUENCY_STATIC = "cat_freq_static"    # CustomSql frequency % (valores fixos)
    CATEGORY_FREQUENCY_DYNAMIC = "cat_freq_dynamic"  # CustomSql frequency % com avg(last(N))
    CATEGORY_FREQUENCY_HYBRID = "cat_freq_hybrid"    # Dinâmico com floor/ceiling absolutos
    DISTINCT_COUNT_EXACT = "distinct_count_exact"    # DistinctValuesCount = N
    DISTINCT_COUNT_RANGE = "distinct_count_range"    # (DVC >= X) AND (DVC <= Y)
    # Tabela
    ROW_COUNT_DUAL_GUARD = "row_count_dual_guard"    # RowCount com avg(last(N))/std(last(N))
    IS_PRIMARY_KEY = "is_primary_key"                # IsPrimaryKey COL
    # Geral
    COMPLETENESS = "completeness"                    # Completeness COL >= T
    CUSTOM_SQL = "custom_sql"                        # CustomSql genérico


class ConfidenceLevel(str, Enum):
    HIGH = "high"                # bom para produção
    MEDIUM = "medium"            # precisa ajuste
    LOW = "low"                  # instável / não recomendado


@dataclass
class BacktestSummary:
    """Resultado do backtest da regra no histórico."""
    total_periods: int
    periods_pass: int
    periods_fail: int
    coverage_pct: float          # % dentro da banda
    false_positive_proxy: int    # históricos "normais" reprovados
    band_width_ratio: float      # largura da banda / centro (sensibilidade)
    stability_score: float       # 0-1; banda muda pouco com variação de n?
    has_drift: bool              # tendência detectada
    outlier_periods: list[str]   # datas dos outliers


@dataclass
class RuleProposal:
    """Uma proposta de regra com evidência e scoring."""
    id: str                      # uuid
    target_column: Optional[str] # None para regras de tabela
    target_table: str
    rule_type: RuleType
    metric_name: str             # ex: "mean", "stddev", "allowed_values"

    # Thresholds sugeridos
    suggested_lower: Optional[float] = None
    suggested_upper: Optional[float] = None
    suggested_values: Optional[list[str]] = None  # para allowed_values

    # Baseline
    baseline_method: Optional[BaselineMethod] = None
    baseline_window: Optional[int] = None
    baseline_n_sigma: Optional[float] = None

    # Avaliação
    backtest: Optional[BacktestSummary] = None
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    warnings: list[str] = field(default_factory=list)

    # Sintaxe
    gdq_syntax_preview: str = ""

    # Histórico para gráfico (dados agregados, não raw)
    history_dates: list[str] = field(default_factory=list)
    history_values: list[float] = field(default_factory=list)
```

### 3.5 RuleSelection (Carrinho)

```python
@dataclass
class UserOverride:
    """Ajustes manuais do usuário sobre a proposta."""
    custom_lower: Optional[float] = None
    custom_upper: Optional[float] = None
    custom_values: Optional[list[str]] = None
    custom_n_periods: Optional[int] = None
    custom_n_sigma: Optional[float] = None
    notes: str = ""


@dataclass
class RuleSelection:
    """Regra selecionada pelo usuário para exportação."""
    proposal_id: str
    proposal: RuleProposal
    enabled: bool = True
    user_overrides: Optional[UserOverride] = None
    final_gdq_syntax: str = ""
    # Gerada com base em proposal + overrides
```

---

## 4. Contratos dos Serviços

### 4.1 DatasetService

```python
class DatasetService:
    """Camada A: Metadata Discovery."""

    def validate_table(self, schema: str, table: str) -> bool:
        """Verifica se schema.table existe no catálogo Athena."""
        ...

    def get_columns(self, schema: str, table: str) -> list[dict]:
        """Retorna colunas com nome e tipo Athena.
        Returns: [{"name": "col1", "type": "string"}, ...]
        """
        ...

    def get_partitions(self, schema: str, table: str) -> list[str]:
        """Retorna partições disponíveis (se particionada)."""
        ...

    def get_date_range(self, config: DatasetConfig) -> dict:
        """Retorna min/max da coluna temporal e contagem de períodos distintos.
        Returns: {"min_date": "...", "max_date": "...", "n_periods": N}
        """
        ...

    def get_volume_by_period(
        self, config: DatasetConfig, limit: int = 50
    ) -> list[dict]:
        """Row count por período (para validar grão e volume).
        Returns: [{"period": "2026-01-15", "row_count": 50000}, ...]
        """
        ...
```

### 4.2 ProfilingService

```python
class ProfilingService:
    """Camada B: Column Classification."""

    def profile_columns(
        self,
        config: DatasetConfig,
        columns: list[str],
        sample_periods: int = 10,
    ) -> list[ColumnProfile]:
        """Classifica colunas usando estratégia em camadas:
        1. Tipo físico Athena (int/bigint/double → numérica)
        2. Heurística de conteúdo (amostra limitada para strings)
        3. Cardinalidade para subclassificar categóricas

        Thresholds de classificação:
        - numeric_cast_ratio > 0.95 → NUMERIC
        - distinct_ratio < 0.005 e distinct_count <= 50 → CATEGORICAL_LOW
        - distinct_ratio < 0.05 e distinct_count <= 500 → CATEGORICAL_MID
        - distinct_ratio >= 0.05 ou distinct_count > 500 → CATEGORICAL_HIGH / IDENTIFIER
        """
        ...

    def apply_user_overrides(
        self,
        profiles: list[ColumnProfile],
        overrides: dict[str, SemanticType],
    ) -> list[ColumnProfile]:
        """Aplica overrides manuais do usuário."""
        ...
```

### 4.3 AnalysisService

```python
class AnalysisService:
    """Camada C: Rule Proposal Analysis — queries históricas no Athena."""

    def get_numeric_history(
        self, config: DatasetConfig, column: str
    ) -> pd.DataFrame:
        """Retorna série histórica agregada por período:
        Columns: [period, mean, stddev, min, max, p01, p05, p25, p50, p75, p95, p99,
                  non_null_count, null_count, total_count]
        """
        ...

    def get_categorical_distribution(
        self, config: DatasetConfig, column: str
    ) -> pd.DataFrame:
        """Retorna distribuição por período:
        Columns: [period, category_value, count, pct]
        """
        ...

    def get_categorical_domain(
        self, config: DatasetConfig, column: str
    ) -> list[str]:
        """Retorna lista de valores distintos (para baixa cardinalidade)."""
        ...

    def get_row_count_history(
        self, config: DatasetConfig
    ) -> pd.DataFrame:
        """Row count por período.
        Columns: [period, row_count]
        """
        ...

    def get_uniqueness_history(
        self, config: DatasetConfig, columns: list[str]
    ) -> pd.DataFrame:
        """Unicidade por período.
        Columns: [period, total_rows, distinct_rows, duplicate_ratio]
        """
        ...

    def get_completeness_history(
        self, config: DatasetConfig, column: str
    ) -> pd.DataFrame:
        """Completude por período.
        Columns: [period, total_count, non_null_count, completeness_ratio]
        """
        ...
```

### 4.4 ProposalService

```python
class ProposalService:
    """Gera propostas com scoring, unindo análise + engine estatístico."""

    def propose_numeric_rules(
        self,
        history: pd.DataFrame,
        column: str,
        baseline: BaselineStrategy,
    ) -> list[RuleProposal]:
        """Gera propostas de mean_band, stddev_band, percentile_band.
        Inclui backtest e confidence scoring.
        """
        ...

    def propose_categorical_rules(
        self,
        distribution: pd.DataFrame,
        domain: list[str],
        column: str,
        profile: ColumnProfile,
        baseline: BaselineStrategy,
    ) -> list[RuleProposal]:
        """Gera propostas baseadas no subtipo categórico:
        - LOW: allowed_values + frequency + completeness
        - MID: top-K frequency + distinct_count + completeness
        - HIGH: completeness + distinct_ratio (sem allowed_values)
        """
        ...

    def propose_table_rules(
        self,
        row_count_history: pd.DataFrame,
        uniqueness_history: pd.DataFrame,
        config: DatasetConfig,
        baseline: BaselineStrategy,
    ) -> list[RuleProposal]:
        """Gera propostas de row_count e uniqueness."""
        ...

    def recalculate_proposal(
        self,
        proposal: RuleProposal,
        new_baseline: BaselineStrategy,
    ) -> RuleProposal:
        """Recalcula thresholds quando usuário ajusta parâmetros (interativo)."""
        ...
```

### 4.5 ExportService

```python
class ExportOutputMode(str, Enum):
    GDQ_RUNTIME = "gdq_runtime"       # sintaxe final para cadastro
    ANALYTICAL_REPORT = "analytical"   # metadados + evidência


@dataclass
class ExportResult:
    rules_text: str                    # bloco de sintaxe GDQ
    rules_json: dict                   # estruturado para integração
    report: Optional[str]              # relatório analítico (markdown)


class ExportService:
    """Converte RuleSelections em output final."""

    def generate_syntax(
        self, selections: list[RuleSelection]
    ) -> str:
        """Gera bloco de sintaxe GDQ pronto para copiar."""
        ...

    def validate_syntax(self, syntax: str) -> list[str]:
        """Validação básica da sintaxe gerada.
        Returns: lista de warnings (vazia se OK)
        """
        ...

    def export(
        self,
        selections: list[RuleSelection],
        mode: ExportOutputMode = ExportOutputMode.GDQ_RUNTIME,
    ) -> ExportResult:
        """Exporta regras com metadados opcionais."""
        ...

    def export_analytical_report(
        self, selections: list[RuleSelection]
    ) -> str:
        """Relatório markdown da proposta:
        - Por que a regra foi sugerida
        - Histórico usado
        - Cobertura do backtest
        - Warnings
        """
        ...
```

---

## 5. Core: Statistical Engine (funções puras)

```python
# core/statistical_engine.py
# Todas as funções recebem dados AGREGADOS (já vindos do Athena).
# Nenhuma função acessa banco, I/O ou UI.

def compute_dynamic_band(
    values: list[float],
    n_periods: int,
    n_sigma: float = 2.0,
) -> dict:
    """Calcula banda dinâmica sobre últimos n períodos.
    Returns: {"lower": float, "upper": float, "center": float,
              "n_sigma": float, "n_periods_used": int}
    Raises ValueError se len(values) < min_required (3).
    """
    ...

def compute_margin_band(
    values: list[float],
    n_periods: int,
    margin_pct: float = 0.10,
) -> dict:
    """Banda por margem percentual sobre a média dos últimos n."""
    ...

def compute_percentile_band(
    p_lower_series: list[float],
    p_upper_series: list[float],
    n_periods: int,
) -> dict:
    """Banda usando percentis históricos (ex: p05/p95 dos últimos n)."""
    ...

def compute_frequency_band(
    pct_series: list[float],
    n_periods: int,
    margin_pct: float = 0.05,
) -> dict:
    """Banda para frequência de categoria (% histórica ± margem)."""
    ...

def detect_drift(
    values: list[float],
    window: int = 10,
) -> dict:
    """Detecção simples de drift (tendência linear).
    Returns: {"has_drift": bool, "slope": float, "r_squared": float}
    """
    ...
```

---

## 6. Core: Rule Scoring

```python
# core/rule_scoring.py

@dataclass
class RuleScore:
    # Componentes individuais (0-1)
    coverage: float              # % processamentos dentro da banda
    stability: float             # 0-1; banda muda pouco variando n ±2
    interpretability: float      # 1.0 para dual guard padrão, menor para custom
    cost_efficiency: float       # 1.0 para regras simples, menor para queries caras

    # Derivados
    false_positive_count: int    # processamentos "normais" que falhariam
    sensitivity: float           # band_width / center (0=apertada, 1+=folgada)

    # Score composto
    score_total: float           # 0.35*coverage + 0.25*stability + 0.20*interp + 0.20*cost
    confidence: ConfidenceLevel  # HIGH / MEDIUM / LOW (derivado de score_total)
    recommendation: str          # texto curto para o usuário
    warnings: list[str] = field(default_factory=list)

    @staticmethod
    def compute_total(
        coverage: float,
        stability: float,
        interpretability: float,
        cost_efficiency: float,
    ) -> float:
        return (
            0.35 * coverage
            + 0.25 * stability
            + 0.20 * interpretability
            + 0.20 * cost_efficiency
        )

    @staticmethod
    def total_to_confidence(score: float) -> ConfidenceLevel:
        if score >= 0.80:
            return ConfidenceLevel.HIGH
        elif score >= 0.55:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW


def score_proposal(
    proposal: RuleProposal,
    history_values: list[float],
) -> RuleScore:
    """Avalia qualidade da regra proposta.

    Coverage:
    - coverage >= 0.90 e < 3 false positives → score alto
    - coverage < 0.75 → score baixo

    Stability:
    - Recalcular banda variando n em ±2 e ±5
    - Se banda muda < 10%: stability = 1.0
    - Se muda > 30%: stability < 0.5

    Interpretability:
    - Dual guard padrão (Mean/StdDev/RowCount): 1.0
    - CustomSql padrão (frequência): 0.8
    - CustomSql genérico: 0.5

    Cost efficiency:
    - Regra built-in sem query extra: 1.0
    - Regra que precisa 1 query Athena: 0.7
    - Regra que precisa N queries: 0.4

    Warnings (não afetam score, mas informam):
    - n_periods < 7 → "pouco histórico"
    - n_periods < 3 → LOW forçado, "dados insuficientes"
    - has_drift → "tendência detectada, avaliar baseline"
    - stability < 0.5 → "banda instável"
    - zero_inflated → "muitos zeros, considerar filtro"
    """
    ...
```

---

## 7. Core: Column Classifier

```python
# core/column_classifier.py

# Thresholds de classificação (configuráveis)
NUMERIC_CAST_THRESHOLD = 0.95
LOW_CARDINALITY_MAX_DISTINCT = 50
LOW_CARDINALITY_MAX_RATIO = 0.005
MID_CARDINALITY_MAX_DISTINCT = 500
MID_CARDINALITY_MAX_RATIO = 0.05

# Tipos Athena que são nativamente numéricos
ATHENA_NUMERIC_TYPES = {
    "tinyint", "smallint", "int", "integer", "bigint",
    "float", "double", "decimal", "real",
}

ATHENA_DATE_TYPES = {"date", "timestamp", "timestamp with time zone"}


def classify_column(
    athena_type: str,
    distinct_count: int,
    total_count: int,
    non_null_count: int,
    numeric_cast_count: int,
) -> SemanticType:
    """Classificação em camadas:
    1. Tipo Athena nativo
    2. Heurística de conteúdo para strings
    3. Cardinalidade para subclassificar categóricas
    """
    ...
```

---

## 8. Core: GDQ Rule Generator

> **Referência completa de sintaxe:** `docs/gdq_syntax_reference.md`

```python
# core/gdq_rule_generator.py
# Conhece APENAS a sintaxe GDQ. Não conhece estatística.
# Recebe RuleProposal (ou UserOverride) e retorna string.
#
# IMPORTANTE — Convenções de sintaxe GDQ reais:
# - Nomes de coluna SEM aspas: Completeness COLUMN_NAME >= 0.99
# - Valores string com aspas duplas em ColumnValues in: ["A","B"]
# - Valores string com aspas simples em CustomSql: 'VALUE'
# - NULL sem aspas na lista de ColumnValues
# - Percentuais em CustomSql vão de 0 a 100 (não 0 a 1)
# - Mean e StandardDeviation usam padrão "dual guard" (σ OR margem%)
# - RowCount dinâmico usa avg(last(N)) e std(last(N))
# - Composição com AND/OR entre parênteses

class GDQRuleGenerator:
    """Converte propostas em sintaxe GDQ."""

    def generate(self, proposal: RuleProposal, overrides: Optional[UserOverride] = None) -> str:
        """Dispatcher principal — chama o método correto por rule_type."""
        ...

    # --- Numéricas: Padrão "Dual Guard" (σ OR margem%) ---

    def mean_dual_guard(
        self,
        col: str,
        n_periods: int = 30,
        n_sigma: int = 2,
        margin_pct: float = 0.10,
        buffer: float = 0.01,
    ) -> str:
        """Regra Mean com dual guard: banda Nσ OR margem percentual.

        Padrão:
          (Mean COL dentro de avg±Kσ±buffer) OR (Mean COL dentro de avg×margin±buffer)

        Parâmetros:
            col: nome da coluna (sem aspas, uppercase)
            n_periods: janela de last(N) — default 30
            n_sigma: multiplicador σ (inteiro) — default 2
            margin_pct: margem percentual — default 0.10 (10%)
            buffer: margem absoluta — default 0.01
        """
        n = n_periods
        k = n_sigma  # int
        lo_margin = round(1 - margin_pct, 2)
        hi_margin = round(1 + margin_pct, 2)
        return (
            f"(((Mean {col} >= (avg(last({n})) - ({k} * std(last({n}))) - {buffer})) "
            f"AND (Mean {col} <= (avg(last({n})) + ({k} * std(last({n}))) + {buffer}))) "
            f"OR ((Mean {col} >= (avg(last({n})) * {lo_margin}) - {buffer}) "
            f"AND (Mean {col} <= (avg(last({n})) * {hi_margin}) + {buffer})))"
        )

    def stddev_dual_guard(
        self,
        col: str,
        n_periods: int = 30,
        n_sigma: int = 2,
        margin_pct: float = 0.10,
        buffer: float = 0.01,
    ) -> str:
        """Regra StandardDeviation com dual guard: mesmo padrão do Mean.

        As funções avg(last(N))/std(last(N)) aqui referem-se à média e
        desvio padrão históricos DO desvio padrão calculado em cada processamento.
        """
        n = n_periods
        k = n_sigma
        lo_margin = round(1 - margin_pct, 2)
        hi_margin = round(1 + margin_pct, 2)
        return (
            f"(((StandardDeviation {col} >= (avg(last({n})) - ({k} * std(last({n}))) - {buffer})) "
            f"AND (StandardDeviation {col} <= (avg(last({n})) + ({k} * std(last({n}))) + {buffer}))) "
            f"OR ((StandardDeviation {col} >= (avg(last({n})) * {lo_margin}) - {buffer}) "
            f"AND (StandardDeviation {col} <= (avg(last({n})) * {hi_margin}) + {buffer})))"
        )

    # --- Completude (qualquer coluna) ---

    def completeness(self, col: str, threshold: float) -> str:
        """Completeness COL >= {threshold}"""
        return f"Completeness {col} >= {threshold:.2f}"

    # --- Categóricas ---

    def column_values_in(
        self, col: str, values: list[str], include_null: bool = False,
        is_numeric: bool = False,
    ) -> str:
        """ColumnValues COL in ["A","B","C", NULL]
        - Strings: aspas duplas
        - Numéricos: sem aspas
        - NULL: sem aspas, adicionado se include_null=True
        """
        if is_numeric:
            formatted = ", ".join(str(v) for v in values)
        else:
            formatted = ", ".join(f'"{v}"' for v in values)
        if include_null:
            formatted += ", NULL"
        return f"ColumnValues {col} in [{formatted}]"

    def distinct_values_count_exact(self, col: str, count: int) -> str:
        """DistinctValuesCount COL = {N}"""
        return f"DistinctValuesCount {col} = {count}"

    def distinct_values_count_range(self, col: str, min_count: int, max_count: int) -> str:
        """(DistinctValuesCount COL >= {min}) AND (DistinctValuesCount COL <= {max})"""
        return (
            f"(DistinctValuesCount {col} >= {min_count}) "
            f"AND (DistinctValuesCount {col} <= {max_count})"
        )

    def category_frequency(self, col: str, value: str, min_pct: float, max_pct: float) -> str:
        """CustomSql para frequência percentual de um valor.
        min_pct/max_pct em escala 0-100.
        Usa -0.01 como lower bound para categorias que podem ser 0%.
        """
        sql = (
            f"select cast(sum(case when {col} = '{value}' "
            f"then 1 else 0 end) as double) * 100.0 / count(*) from primary"
        )
        return f'CustomSql "{sql}" between {min_pct:.2f} and {max_pct:.2f}'

    # --- Tabela: RowCount ---

    def row_count_dynamic(
        self,
        n_periods: int = 30,
        n_sigma: float = 2.0,
        margin_pct: float = 0.1,
    ) -> str:
        """Regra genérica de RowCount: banda Nσ OR margem percentual.

        Lógica: (dentro de Nσ) OR (dentro de X% da média)
        O OR garante que:
        - Se σ ≈ 0 (tabela muito estável), a margem dá tolerância mínima
        - Se há variação natural, Nσ é mais preciso

        Parâmetros:
            n_periods: janela de last(N)
            n_sigma: multiplicador do desvio padrão (default 2.0)
            margin_pct: margem percentual fallback (default 0.1 = 10%)
        """
        n = n_periods
        s = n_sigma
        m = margin_pct
        return (
            f"(((RowCount >= (avg(last({n})) * 1.0 - ({s} * std(last({n}))))) "
            f"AND (RowCount <= (avg(last({n})) * 1.0 + ({s} * std(last({n})))))) "
            f"OR ((RowCount >= (avg(last({n})) - (avg(last({n})) * {m}))) "
            f"AND (RowCount <= (avg(last({n})) + (avg(last({n})) * {m})))))"
        )

    # --- Chave primária / Unicidade ---

    def is_primary_key(self, col: str) -> str:
        """IsPrimaryKey COL"""
        return f"IsPrimaryKey {col}"
```

### Exemplos de output esperado

```python
gen = GDQRuleGenerator()

# Mean dual guard (padrão: 30 períodos, 2σ, 10% margem, buffer 0.01)
gen.mean_dual_guard("VLR_SALD_AVNC_OPCR")
# → "(((Mean VLR_SALD_AVNC_OPCR >= (avg(last(30)) - (2 * std(last(30))) - 0.01)) AND (Mean VLR_SALD_AVNC_OPCR <= (avg(last(30)) + (2 * std(last(30))) + 0.01))) OR ((Mean VLR_SALD_AVNC_OPCR >= (avg(last(30)) * 0.9) - 0.01) AND (Mean VLR_SALD_AVNC_OPCR <= (avg(last(30)) * 1.1) + 0.01)))"

# Mean com 3σ e 15% margem
gen.mean_dual_guard("VLR_PARC_OPCR", n_periods=20, n_sigma=3, margin_pct=0.15)
# → "(((Mean VLR_PARC_OPCR >= (avg(last(20)) - (3 * std(last(20))) - 0.01)) AND (Mean VLR_PARC_OPCR <= (avg(last(20)) + (3 * std(last(20))) + 0.01))) OR ((Mean VLR_PARC_OPCR >= (avg(last(20)) * 0.85) - 0.01) AND (Mean VLR_PARC_OPCR <= (avg(last(20)) * 1.15) + 0.01)))"

# StandardDeviation dual guard
gen.stddev_dual_guard("VLR_PARC_OPCR")
# → "(((StandardDeviation VLR_PARC_OPCR >= (avg(last(30)) - (2 * std(last(30))) - 0.01)) AND (StandardDeviation VLR_PARC_OPCR <= (avg(last(30)) + (2 * std(last(30))) + 0.01))) OR ((StandardDeviation VLR_PARC_OPCR >= (avg(last(30)) * 0.9) - 0.01) AND (StandardDeviation VLR_PARC_OPCR <= (avg(last(30)) * 1.1) + 0.01)))"

# Completude
gen.completeness("TOTAL_BALANCE", 0.76)
# → "Completeness TOTAL_BALANCE >= 0.76"

# Valores permitidos (string com NULL)
gen.column_values_in("PRODUCT_VARIANT",
    ["INFINITE", "INTERNACIONAL", "GOLD", "BLACK", "PLATINUM", "SIGNATURE"],
    include_null=True)
# → 'ColumnValues PRODUCT_VARIANT in ["INFINITE", "INTERNACIONAL", "GOLD", "BLACK", "PLATINUM", "SIGNATURE", NULL]'

# Valores permitidos (numérico com NULL)
gen.column_values_in("CPRODLIM", [70364, 48589, 48597], include_null=True, is_numeric=True)
# → "ColumnValues CPRODLIM in [70364, 48589, 48597, NULL]"

# Distinct count exato
gen.distinct_values_count_exact("ACCOUNT_STATUS", 6)
# → "DistinctValuesCount ACCOUNT_STATUS = 6"

# Distinct count range
gen.distinct_values_count_range("CPRODLIM", 27, 30)
# → "(DistinctValuesCount CPRODLIM >= 27) AND (DistinctValuesCount CPRODLIM <= 30)"

# Frequência de categoria
gen.category_frequency("PRODUCT_VARIANT", "PLATINUM", 72.41, 79.23)
# → 'CustomSql "select cast(sum(case when PRODUCT_VARIANT = \'PLATINUM\' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between 72.41 and 79.23'

# RowCount dinâmico
gen.row_count_dynamic(n_periods=30, n_sigma=2.0, margin_pct=0.1)
# → "(((RowCount >= (avg(last(30)) * 1.0 - (2.0 * std(last(30))))) AND ..."

# Chave primária
gen.is_primary_key("ACCOUNT_ID")
# → "IsPrimaryKey ACCOUNT_ID"
```

### 8.2 DualGuardRenderer (motor de sintaxe separado)

```python
# core/gdq_renderer.py
# Converte DualGuardSpec → string GDQ.
# Conhece APENAS formatação. Não conhece estatística ou análise.
# Testado contra exemplos de produção reais (docs/gdq_syntax_reference.md).

class DualGuardRenderer:
    """Renderiza DualGuardSpec em sintaxe GDQ real.

    Garante:
    - Parênteses balanceados
    - Casing correto (coluna sem aspas, avg/std lowercase)
    - K inteiro vs float conforme profile
    - Buffer presente/ausente conforme profile
    - Formato de margem correto conforme profile
    """

    def render(self, spec: DualGuardSpec) -> str:
        """Renderiza a string GDQ completa para uma DualGuardSpec.
        Dispatcher que chama _render_builtin ou _render_custom_sql.
        """
        if spec.metric == MetricRef.CUSTOM_SQL:
            return self._render_custom_sql(spec)
        return self._render_builtin(spec)

    def _render_builtin(self, spec: DualGuardSpec) -> str:
        """Renderiza Mean, StandardDeviation ou RowCount.

        Pattern:
          (((Metric TARGET >= (avg(last(N)) [* 1.0] - (K * std(last(N))) [- buffer]))
            AND (Metric TARGET <= (avg(last(N)) [* 1.0] + (K * std(last(N))) [+ buffer])))
           OR
           ((Metric TARGET >= (avg(last(N)) * lo_factor) [- buffer])
            AND (Metric TARGET <= (avg(last(N)) * hi_factor) [+ buffer])))
        """
        p = spec.profile
        n = spec.n_periods

        # K formatting: int para Mean/StdDev, float para RowCount
        k_str = f"{spec.n_sigma}" if not p.k_as_float else f"{spec.n_sigma}"
        # Já é float se RowCount via __post_init__

        # avg reference: "avg(last(N))" ou "avg(last(N)) * 1.0"
        avg_ref = f"avg(last({n}))"
        if p.avg_multiply_one:
            avg_ref = f"avg(last({n})) * 1.0"

        # buffer suffix
        buf_lo = f" - {spec.buffer}" if p.include_buffer and spec.buffer > 0 else ""
        buf_hi = f" + {spec.buffer}" if p.include_buffer and spec.buffer > 0 else ""

        # metric + target
        metric_target = f"{spec.metric.value} {spec.target}".strip()

        # Banda A (sigma)
        band_a_lo = f"({avg_ref} - ({k_str} * std(last({n})))" + buf_lo + ")"
        band_a_hi = f"({avg_ref} + ({k_str} * std(last({n})))" + buf_hi + ")"

        # Banda B (margem) - formato depende do profile
        lo_margin = round(1 - spec.margin_pct, 2)
        hi_margin = round(1 + spec.margin_pct, 2)

        if p.margin_format == "factor":
            band_b_lo = f"(avg(last({n})) * {lo_margin})" + buf_lo
            band_b_hi = f"(avg(last({n})) * {hi_margin})" + buf_hi
        else:  # "delta"
            band_b_lo = f"(avg(last({n})) - (avg(last({n})) * {spec.margin_pct}))"
            band_b_hi = f"(avg(last({n})) + (avg(last({n})) * {spec.margin_pct}))"

        return (
            f"((({metric_target} >= {band_a_lo}) "
            f"AND ({metric_target} <= {band_a_hi})) "
            f"OR (({metric_target} >= {band_b_lo}) "
            f"AND ({metric_target} <= {band_b_hi})))"
        )

    def _render_custom_sql(self, spec: DualGuardSpec) -> str:
        """Renderiza CustomSql com dual guard dinâmico.

        Pattern (dual guard):
          ((CustomSql "..." between (avg(last(N)) - K*std(last(N)) - buffer)
                                and (avg(last(N)) + K*std(last(N)) + buffer))
           OR (CustomSql "..." between (avg(last(N)) * lo - buffer)
                                   and (avg(last(N)) * hi + buffer)))
        """
        n = spec.n_periods
        k = int(spec.n_sigma)
        buf = spec.buffer
        lo_margin = round(1 - spec.margin_pct, 2)
        hi_margin = round(1 + spec.margin_pct, 2)
        sql = spec.custom_sql_expression

        return (
            f'((CustomSql "{sql}" between '
            f"(avg(last({n})) - ({k} * std(last({n}))) - {buf}) "
            f"and (avg(last({n})) + ({k} * std(last({n}))) + {buf})) "
            f'OR (CustomSql "{sql}" between '
            f"(avg(last({n})) * {lo_margin} - {buf}) "
            f"and (avg(last({n})) * {hi_margin} + {buf})))"
        )
```

### 8.3 Testes obrigatórios do Renderer

O DualGuardRenderer DEVE ser testado contra os exemplos reais de produção:

```python
# tests/test_gdq_renderer.py

def test_mean_matches_production():
    spec = DualGuardSpec(
        metric=MetricRef.MEAN,
        target="VLR_SALD_AVNC_OPCR",
        n_periods=30,
        n_sigma=2,
        margin_pct=0.10,
        buffer=0.01,
    )
    result = DualGuardRenderer().render(spec)
    expected = (
        "(((Mean VLR_SALD_AVNC_OPCR >= (avg(last(30)) - (2 * std(last(30))) - 0.01)) "
        "AND (Mean VLR_SALD_AVNC_OPCR <= (avg(last(30)) + (2 * std(last(30))) + 0.01))) "
        "OR ((Mean VLR_SALD_AVNC_OPCR >= (avg(last(30)) * 0.9) - 0.01) "
        "AND (Mean VLR_SALD_AVNC_OPCR <= (avg(last(30)) * 1.1) + 0.01)))"
    )
    assert result == expected


def test_rowcount_matches_production():
    spec = DualGuardSpec(
        metric=MetricRef.ROW_COUNT,
        n_periods=30,
        n_sigma=2.0,
        margin_pct=0.1,
    )
    result = DualGuardRenderer().render(spec)
    # Validate K is float, no buffer, avg * 1.0, margin as delta
    assert "2.0 * std" in result
    assert "avg(last(30)) * 1.0" in result
    assert "0.01" not in result  # no buffer
```

---

## 9. Infrastructure: SQL Safety + Cost Guardrails

### 9.1 SQL Safety

```python
# infra/query_safety.py

import re

# Whitelist de caracteres permitidos em identificadores
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Limites padrão
MAX_LOOKBACK_DAYS = 365
MAX_LOOKBACK_PERIODS = 100
DEFAULT_QUERY_TIMEOUT_SECONDS = 120
MAX_SAMPLE_ROWS = 100_000


def validate_identifier(name: str) -> str:
    """Valida e retorna identificador seguro.
    Raises ValueError se inválido.
    """
    if not IDENTIFIER_PATTERN.match(name):
        raise ValueError(f"Identificador inválido: {name}")
    return name


def validate_lookback(value: int, mode: LookbackMode) -> int:
    """Garante que lookback está dentro dos limites."""
    ...


def sanitize_filter(sql_fragment: str) -> str:
    """Validação básica de filtro custom (bloqueia DDL, DML, subqueries).
    Para MVP: permitir apenas expressões simples (col = 'val', col IN (...)).
    """
    ...
```

### 9.2 Cost Guardrails

```python
# infra/cost_estimator.py

@dataclass
class QueryCostEstimate:
    """Estimativa de custo/impacto de uma query Athena."""
    query_name: str
    estimated_scan_gb: Optional[float] = None  # quando disponível
    lookback_periods: int = 0
    uses_count_distinct: bool = False
    uses_approx: bool = False
    risk_level: str = "low"  # "low", "medium", "high"
    warnings: list[str] = field(default_factory=list)


# Limites de proteção (configuráveis em config.py)
MAX_LOOKBACK_PERIODS = 100
MAX_LOOKBACK_DAYS = 365
MAX_CATEGORIES_FOR_FREQUENCY = 50  # acima disso, warning
MAX_DISTINCT_SCAN_THRESHOLD = 0.5  # distinct_ratio > 0.5 → warning
QUERY_TIMEOUT_SECONDS = 120


def estimate_query_cost(
    query_type: str,
    column_profile: Optional[ColumnProfile],
    lookback: int,
) -> QueryCostEstimate:
    """Estima risco/custo antes de executar a query.

    Warnings gerados:
    - CAT_HIGH + frequency → "alta cardinalidade, considere distinct_count em vez de frequency"
    - COUNT(DISTINCT) + lookback > 60 → "query potencialmente cara"
    - lookback > MAX → "lookback excede limite"
    """
    ...
```

### 9.3 Structured Logging (Observabilidade)

```python
# infra/query_logger.py
import logging
import time
from dataclasses import dataclass


@dataclass
class QueryLogEntry:
    """Entrada de log estruturada para cada query Athena executada."""
    query_name: str            # ex: "numeric_history", "categorical_distribution"
    dataset: str               # schema.table
    column: Optional[str]      # coluna analisada (None para tabela)
    elapsed_ms: int
    cache_hit: bool
    rows_returned: int
    bytes_scanned: Optional[int] = None  # se disponível do Athena
    exception_type: Optional[str] = None
    timestamp: str = ""


class QueryLogger:
    """Logger estruturado para queries Athena.

    Cada query executada gera uma entrada com métricas.
    Útil para debug ("a tela travou"), otimização de custo,
    e identificação de queries lentas.
    """

    def __init__(self):
        self.logger = logging.getLogger("gdq_proposer.queries")
        self.entries: list[QueryLogEntry] = []

    def log_query(self, entry: QueryLogEntry):
        self.entries.append(entry)
        self.logger.info(
            f"[{entry.query_name}] {entry.dataset}.{entry.column or '*'} "
            f"→ {entry.rows_returned} rows, {entry.elapsed_ms}ms, "
            f"cache={'HIT' if entry.cache_hit else 'MISS'}"
        )

    def get_session_summary(self) -> dict:
        """Resumo da sessão: total queries, tempo total, cache hits."""
        ...
```

---

## 10. Fluxo de Telas Streamlit

### Tela 1: Setup (01_setup.py)

```
┌─────────────────────────────────────────────────────┐
│  🔧 Configuração da Tabela                          │
│                                                      │
│  Schema:  [gdq_test_db_▼]    Table: [____________▼]│
│  [🔍 Validar Tabela]                                │
│                                                      │
│  ── Particionamento ──                               │
│  Método:  [● Incremental  ○ Full Snapshot  ○ Sem]   │
│  Coluna de partição:  [dt_ref_________▼]            │
│                                                      │
│  ── Eixo Temporal ──                                 │
│  ┌──────────────────────────────────────────┐       │
│  │ ℹ️ Incremental: a partição dt_ref é o    │       │
│  │    eixo temporal (cada partição = 1 dia) │       │
│  └──────────────────────────────────────────┘       │
│  Coluna de data:     [dt_ref_________▼]  (= part.)│
│  Eixo temporal:      [dt_ref] (inferido)           │
│  Tipo de grão:       [● Diário ○ Mensal ○ Custom]  │
│  Expressão data:     [_________________________]    │
│    (ex: date_parse(dt_ref, '%Y.%m.%d'))            │
│  Lookback:           [30] [● Períodos ○ Dias]      │
│                                                      │
│  ── Filtros ──                                       │
│  Filtro WHERE base:  [_________________________]    │
│    (ex: IND_ATIVO = 1)                              │
│                                                      │
│  ── Colunas ──                                       │
│  │ Coluna               │ Tipo Athena │ Tipo Inf.│▼│
│  │ VLR_SALD_AVNC_OPCR   │ double      │ 🔢 Num. │▼│
│  │ VLR_PARC_OPCR         │ double      │ 🔢 Num. │▼│
│  │ COD_SITU_OPCR         │ string      │ 📋 Cat.B│▼│
│  │ NUM_CTRT_OPCR         │ string      │ 🔑 ID   │▼│
│                                                      │
│  [▼] = Numérica / Cat. Baixa / Cat. Média /        │
│         Cat. Alta / ID / Ignorar                     │
│                                                      │
│  Selecionar para análise:                            │
│  [☑] VLR_SALD_AVNC_OPCR  [☑] COD_SITU_OPCR       │
│  [☑] VLR_PARC_OPCR        [☐] NUM_CTRT_OPCR       │
│                                                      │
│  Chave de unicidade: [NUM_CTRT_OPCR, dt_ref]       │
│                                                      │
│  [▶ Iniciar Análise]                                │
└─────────────────────────────────────────────────────┘

--- Variação: Full Snapshot ---

┌─────────────────────────────────────────────────────┐
│  ── Particionamento ──                               │
│  Método:  [○ Incremental  ● Full Snapshot  ○ Sem]   │
│  Coluna de partição:  [dt_carga_______▼]            │
│                                                      │
│  ── Eixo Temporal ──                                 │
│  ┌──────────────────────────────────────────┐       │
│  │ ℹ️ Full Snapshot: cada partição dt_carga │       │
│  │    contém a foto completa. O eixo        │       │
│  │    temporal para GDQ = dt_carga.         │       │
│  │    A coluna de data pode ser outra.      │       │
│  └──────────────────────────────────────────┘       │
│  Coluna de data (negócio): [DT_ABERTURA___▼]       │
│  Eixo temporal (GDQ):      [dt_carga] (= partição) │
│  Tipo de grão:             [● Diário ○ Mensal]     │
│  Lookback:                 [30] [● Períodos]        │
│                                                      │
│  ── Filtros ──                                       │
│  Filtro WHERE base:  [IND_ATIVO = 1___________]     │
│    ⚠️ Em Full Snapshot, filtro é recomendado        │
└─────────────────────────────────────────────────────┘
```

### Tela 2: Explore / Calibração (02_explore.py)

```
┌─────────────────────────────────────────────────────┐
│  📊 Análise: db.vendas                              │
│                                                      │
│  [Tab: 🔢 Numéricas] [Tab: 📋 Categóricas]         │
│  [Tab: 📋 Tabela]                                    │
│                                                      │
│  ── Coluna: VALOR (numérica) ──────────────────     │
│                                                      │
│  Teste: [● Média ± Nσ  ○ Desvio Padrão  ○ Percentil] │
│                                                      │
│  Parâmetros:                                         │
│  N períodos: [====●====] 20                         │
│  Desvio (σ):  [● 2σ  ○ 3σ  ○ Custom: ___]          │
│                                                      │
│  ┌──────────── Gráfico ────────────────────┐        │
│  │                                          │        │
│  │   ● ●                    banda 2σ ░░░░  │        │
│  │ ●     ● ●  ●                            │        │
│  │          ●    ● ●  ●                    │        │
│  │                     ● ●                  │        │
│  │                        ✗  ← FORA        │        │
│  │──────────────────────────────────────    │        │
│  │ D-30    D-20     D-10      D-1  Hoje    │        │
│  └──────────────────────────────────────────┘        │
│                                                      │
│  Resultado do backtest:                              │
│  ✅ Cobertura: 96.7% (29/30 períodos OK)            │
│  ⚠️ 1 falso positivo detectado (2026-01-15)         │
│  📏 Sensibilidade: 0.34 (banda moderada)            │
│  📈 Drift: não detectado                            │
│  Confiança: 🟢 ALTA                                 │
│                                                      │
│  Banda sugerida: [145.23] a [892.11]                │
│                                                      │
│  Output:                                             │
│  ○ CustomSql (thresholds estáticos)                  │
│  ● Proposta analítica (para decisão)                 │
│                                                      │
│  Preview: CustomSql "select avg(CAST(VALOR AS        │
│    DOUBLE)) from primary" between 145.23 and 892.11  │
│                                                      │
│  [🛒 Adicionar ao Carrinho]  [⏭ Próxima Coluna]    │
└─────────────────────────────────────────────────────┘
```

### Tela 3: Review / Export (03_review.py)

```
┌─────────────────────────────────────────────────────────────┐
│  🛒 Regras Selecionadas — db.vendas                         │
│                                                              │
│  │ # │ Regra                                           │ 🟢│ │
│  │ 1 │ Completeness VALOR >= 0.99                      │ ☑ │ │
│  │ 2 │ Completeness STATUS >= 1.00                     │ ☑ │ │
│  │ 3 │ ColumnValues STATUS in ["A","B","C"]            │ ☑ │ │
│  │ 4 │ DistinctValuesCount STATUS = 3                  │ ☑ │ │
│  │ 5 │ CustomSql "select cast(sum(case when STATUS =   │ ☑ │ │
│  │   │   'A' then 1 else 0 end)..." between 45 and 55 │    │ │
│  │ 6 │ (((RowCount >= (avg(last(30)) * 1.0 - ...      │ ☑ │ │
│  │ 7 │ IsPrimaryKey ID_VENDA                           │ ☐ │ │
│                                                              │
│  ── Preview ──                                               │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Completeness VALOR >= 0.99                          │     │
│  │ Completeness STATUS >= 1.00                         │     │
│  │ ColumnValues STATUS in ["A","B","C"]                │     │
│  │ DistinctValuesCount STATUS = 3                      │     │
│  │ CustomSql "select cast(sum(case when STATUS = 'A'   │     │
│  │   then 1 else 0 end) as double) * 100.0 / count(*) │     │
│  │   from primary" between 45.00 and 55.00             │     │
│  │ (((RowCount >= (avg(last(30)) * 1.0 - (2.0 *       │     │
│  │   std(last(30))))) AND (RowCount <= (avg(last(30))  │     │
│  │   * 1.0 + (2.0 * std(last(30)))))) OR ((RowCount   │     │
│  │   >= (avg(last(30)) - (avg(last(30)) * 0.1))) AND  │     │
│  │   (RowCount <= (avg(last(30)) + (avg(last(30)) *   │     │
│  │   0.1)))))                                          │     │
│  └────────────────────────────────────────────────────┘     │
│                                                              │
│  [📋 Copiar Sintaxe] [📥 Exportar .txt]                     │
│  [📊 Exportar Relatório Analítico]                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 11. Tipos de Regra por Fase

### Sprint A (MVP) — Numéricas + Fundação

| Regra | Tipo de coluna | Sintaxe GDQ | Dinâmica |
|-------|---------------|-------------|----------|
| Mean dual guard | Numérica | `(((Mean COL >= (avg(last(N)) - (K * std(last(N))) - 0.01)) AND (...)) OR ((...)))` | Sim |
| StandardDeviation dual guard | Numérica | `(((StandardDeviation COL >= (avg(last(N)) - ...)) AND (...)) OR ((...)))` | Sim |
| Completude | Qualquer | `Completeness COL >= {T}` | Não |
| RowCount dual guard | Tabela | `(((RowCount >= (avg(last(N)) * 1.0 - (K * std(last(N))))) AND (...)) OR ((...)))` | Sim |

### Sprint B (MVP) — Categóricas + Tabela

| Regra | Tipo de coluna | Sintaxe GDQ | Dinâmica |
|-------|---------------|-------------|----------|
| Valores permitidos | Cat. baixa | `ColumnValues COL in [2, 1, 3]` | Não |
| Frequência por categoria | Cat. baixa/média | `CustomSql "select cast(sum(case when COL = 'V' ...) from primary" between X and Y` | Não |
| Contagem de distintos (exato) | Cat. baixa | `DistinctValuesCount COL = N` | Não |
| Contagem de distintos (range) | Cat. média | `(DistinctValuesCount COL >= X) AND (DistinctValuesCount COL <= Y)` | Não |
| Completude | Qualquer | `Completeness COL >= {T}` | Não |
| Chave primária | Tabela/Coluna | `IsPrimaryKey COL1 COL2 COL3` | Não |

### Sprint C (Polish) — Extensões

| Regra | Nota |
|-------|------|
| Distinct ratio | `distinct / total` como métrica via CustomSql |
| Padrão/regex | Para IDs com formato conhecido |
| IQR / MAD | Robustez a outliers (melhoria do engine estatístico) |
| Percentil via CustomSql | `CustomSql "select approx_percentile(...) from primary" between X and Y` |

### Nota: Regras dinâmicas vs estáticas (confirmado)

Pela referência de produção, **Mean, StandardDeviation e RowCount** são regras built-in do GDQ que suportam `avg(last(N))` e `std(last(N))` nativamente. O motor GDQ recalcula a cada execução.

Para **categóricas**, os limites de frequência (CustomSql) são **estáticos** — a ferramenta calcula os valores e o usuário ajusta antes de exportar.

O padrão "dual guard" (σ OR margem%) é usado consistentemente em todas as regras dinâmicas, com pequenas variações:
- Mean/StdDev: K como inteiro, buffer 0.01, margem como `avg * factor`
- RowCount: K como float (2.0), sem buffer, margem como `avg - (avg * pct)`

---

## 12. Critérios de Aceite por Sprint

### Sprint A1 — Fundação técnica mínima

- [ ] Usuário informa `schema.table` e app valida existência via Athena
- [ ] Colunas exibidas com tipo Athena e classificação semântica inferida
- [ ] Classificação em 2 níveis: tipo físico + tipo semântico (NUMERIC/CAT_LOW/MID/HIGH/ID/FREE_TEXT)
- [ ] Override manual de tipo sempre disponível
- [ ] Usuário configura coluna temporal (tipo de grão, expressão de normalização, lookback)
- [ ] Filtro base opcional (ex: `ind_ativo = 1`)
- [ ] Configuração da sessão persiste em JSON (presets/)
- [ ] query_safety.py validando todos os identificadores
- [ ] Timeout configurável nas queries Athena
- [ ] Warning de custo antes de profiling completo
- [ ] Wizard com validação progressiva (impede "Próxima" se config inválida)

### Sprint A2 — Numéricas + Backtest + Score + Export

- [ ] Query Athena retorna série histórica agregada por período
- [ ] DualGuardSpec como representação intermediária (nunca gerar string direto)
- [ ] DualGuardRenderer testado contra exemplos de produção reais
- [ ] Para cada coluna numérica selecionada:
  - [ ] Gráfico Plotly com histórico + banda proposta (hrect)
  - [ ] Usuário ajusta N, σ e margem% via sliders, gráfico atualiza
  - [ ] Preview de impacto lado a lado: coverage, falsos positivos, score
  - [ ] Backtest exibe cobertura e falsos positivos
  - [ ] Score composto exibido (0.35×coverage + 0.25×stability + 0.20×interp + 0.20×cost)
  - [ ] Confidence badge: 🟢 ALTA / 🟡 MÉDIA / 🔴 BAIXA
  - [ ] Regra Mean dual guard gerada corretamente
  - [ ] Regra StandardDeviation dual guard gerada corretamente
  - [ ] Usuário adiciona regra ao "carrinho" com evidência + racional
- [ ] Completeness para colunas numéricas
- [ ] Export básico: copiar sintaxe + .txt
- [ ] Tela de review com carrinho e preview de bloco GDQ
- [ ] 8 fixtures de teste cobrindo: estável, drift, sazonal, outlier, category_shift, sparse, zero_inflated, regime_change

### Sprint B1 — RowCount + Plugin de Estratégia

- [ ] RowCountStrategy como Protocol (facilita plugar regra enterprise)
- [ ] GenericBandRowCountStrategy implementada (dual guard padrão)
- [ ] Diferenças de formato RowCount vs Mean/StdDev respeitadas (K float, sem buffer, avg*1.0)
- [ ] Backtest e score de row count
- [ ] Gráfico de calibração de row count

### Sprint B2 — Categóricas MVP

- [ ] Classificação categórica em subtipos (low/mid/high) com thresholds configuráveis
- [ ] Para cat. baixa: ColumnValues in [...] + gráfico de frequência
- [ ] Para cat. média: top-K frequency + DistinctValuesCount
- [ ] Para cat. alta: completude + distinct ratio (sem allowed values, com warning)
- [ ] CustomSql frequência estática (valores fixos calculados pela ferramenta)
- [ ] Completeness para categóricas
- [ ] IsPrimaryKey (colunas separadas por espaço)
- [ ] Warning automático se CAT_HIGH e usuário tentar frequency por categoria
- [ ] Cost estimate antes de rodar distribuição categórica

### Sprint C1 — Review + Validação de Sintaxe

- [ ] validate_syntax() no export_service
- [ ] Carrinho com 3 itens por regra: sintaxe GDQ + evidência + racional
- [ ] Relatório analítico markdown exportável
- [ ] Warnings de sintaxe e consistência antes de export

### Sprint C2 — CustomSql Dinâmico Categórico

- [ ] CustomSql frequência dinâmica com dual guard (avg(last(N))/std(last(N)) no between)
- [ ] Modo híbrido: dinâmico com floor/ceiling absolutos
- [ ] Toggle estático/dinâmico/híbrido na UI por regra
- [ ] Backtest adaptado para simular comportamento dinâmico
- [ ] Documentação "quando usar cada modo"

### Sprint D — Polish + IA

- [ ] Cache TTL diferenciado por tipo de query (metadata: 1h, histórico: 15min)
- [ ] Logs estruturados (QueryLogEntry) com tempo, cache, bytes_scanned
- [ ] Cost guardrails com warnings antes de queries caras
- [ ] Presets reutilizáveis por família de tabela (clonar, comparar)
- [ ] AI provider protocol + adapters (Bedrock/StackSpot/Mock)
- [ ] AI insights panel (não bloqueante, expandível)

---

## 13. Decisões Técnicas

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| Framework UI | Streamlit (multi-page) | Deploy simples, bom para PoC interno, Plotly nativo |
| Acesso Athena | `pyathena` + `boto3` | Suporte a cursor DictCursor, fácil cache |
| Templates SQL | Jinja2 | Parametrização segura sem string interpolation |
| Modelos de dados | `dataclasses` | Leve, sem dependência extra (Pydantic se necessário depois) |
| Gráficos | Plotly via `st.plotly_chart` | Interativo, suporte a bandas/heatmaps/hover |
| Cache | `st.cache_data` com TTL | Metadata: 1h, Histórico: 15min, Profiling: 30min |
| Serialização | JSON | Presets, export, sessões |
| Container | Docker + docker-compose | Deploy consistente no homelab ou cloud |

---

## 14. Backlog Futuro (pós-MVP)

| Item | Prioridade | Nota |
|------|-----------|------|
| Sazonalidade (dia da semana, dia do mês) | Alta | Melhora muito as bandas |
| IQR / MAD como alternativa a σ | Alta | Robustez a outliers |
| Detecção de mudança de regime | Média | Alerta quando baseline muda |
| Classificação semântica avançada | Média | "percentual", "indicador binário", "contador" |
| Integração direta com API GDQ | Média | Cadastro automático (se API existir) |
| Agendamento de reavaliação | Baixa | Recalcular bandas periodicamente |
| Multi-tabela batch | Baixa | Pipeline de análise para N tabelas |
| Exportar para Great Expectations / Soda | Baixa | Portabilidade para outros motores |

---

## 15. Requisitos Não-Funcionais

| Requisito | Target |
|-----------|--------|
| Tempo de setup (até colunas classificadas) | < 30s |
| Tempo de análise por coluna numérica | < 15s |
| Tempo de análise por coluna categórica | < 15s |
| Timeout máximo de query Athena | 120s (configurável) |
| Máximo de dados trafegados para o app | Apenas agregados (nunca raw rows) |
| Persistência de sessão | JSON local em presets/ |
| Segurança de query | Whitelist de identificadores, sem interpolação direta |
