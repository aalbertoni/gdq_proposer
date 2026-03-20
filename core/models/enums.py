"""
Enums compartilhados do domínio GDQ Rule Proposer.

Definidos conforme docs/technical_spec_v1.md.
"""

from enum import Enum


class LookbackMode(str, Enum):
    """Modo de lookback para janela de análise."""
    LAST_N_PERIODS = "last_n_periods"
    LAST_X_DAYS = "last_x_days"


class GrainType(str, Enum):
    """Granularidade dos períodos temporais."""
    DAILY = "daily"
    MONTHLY = "monthly"
    TIMESTAMP = "timestamp"
    CUSTOM = "custom"


class PartitionMethod(str, Enum):
    """Estratégia de organização de partições."""

    INCREMENTAL = "incremental"
    # Cada partição contém APENAS dados novos daquele período.
    # Partição = eixo temporal = coluna de data para análise.
    # Ex: tb_operacoes com dt_ref=2026-01-15 contém só ops do dia 15.
    # Para análise: GROUP BY partição -> cada partição = 1 processamento.

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


class SemanticType(str, Enum):
    """Classificação semântica de colunas (2 níveis: tipo Athena + heurísticas)."""
    NUMERIC = "numeric"
    CATEGORICAL_LOW_CARDINALITY = "categorical_low"    # domínio fixo (< ~20 valores)
    CATEGORICAL_MID_CARDINALITY = "categorical_mid"    # top-K monitorável (~20-500)
    CATEGORICAL_HIGH_CARDINALITY = "categorical_high"  # identificador (> ~500)
    DATETIME = "datetime"
    IDENTIFIER = "identifier"
    FREE_TEXT = "free_text"
    UNKNOWN = "unknown"


class RuleType(str, Enum):
    """Tipos de regra GDQ suportados pela ferramenta."""

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

    # Unicidade
    UNIQUENESS_CUSTOM_SQL = "uniqueness_custom_sql"  # CustomSql COUNT(DISTINCT) >= 100%

    # Geral
    COMPLETENESS = "completeness"                    # Completeness COL >= T
    CUSTOM_SQL = "custom_sql"                        # CustomSql genérico


class ConfidenceLevel(str, Enum):
    """Nível de confiança da regra proposta."""
    HIGH = "high"                # bom para produção
    MEDIUM = "medium"            # precisa ajuste
    LOW = "low"                  # instável / não recomendado


class MetricRef(str, Enum):
    """Tipo de métrica GDQ para dual guard (usado no DualGuardSpec)."""
    MEAN = "Mean"
    STANDARD_DEVIATION = "StandardDeviation"
    ROW_COUNT = "RowCount"
    CUSTOM_SQL = "CustomSql"


class BaselineMethod(str, Enum):
    """Estratégia de cálculo de baseline."""
    LAST_N_PERIODS = "last_n_periods"
    LAST_X_DAYS = "last_x_days"
    ROLLING_WINDOW_EXCLUDE_CURRENT = "rolling_exclude_current"
    SAME_WEEKDAY = "same_weekday"             # evolução futura
    SAME_DAY_OF_MONTH = "same_day_of_month"   # evolução futura


class SeriesRegime(str, Enum):
    """Regime estatistico da serie temporal.

    Classificacao pragmatica para orientar a escolha e calibracao
    de regras DQ. Nao e mutuamente exclusivo — uma serie pode ter
    tendencia + sazonalidade. O regime principal e o mais dominante.
    """

    STABLE = "stable"                        # baixa volatilidade, sem tendencia
    VOLATILE = "volatile"                    # alta volatilidade (CV > 30%)
    TRENDING = "trending"                    # tendencia monotonica detectada
    SEASONAL = "seasonal"                    # padrao ciclico (semanal, mensal)
    STRUCTURAL_BREAK = "structural_break"    # mudanca abrupta de patamar
    ZERO_INFLATED = "zero_inflated"          # >= 30% dos valores sao zero
    ASYMMETRIC = "asymmetric"               # skewness alta (|skew| > 1.0)
    SPARSE = "sparse"                        # >= 30% dos valores sao nulos


class RecommendationTier(str, Enum):
    """Tier de recomendacao da regra proposta."""

    RECOMMENDED = "recommended"          # propor ao usuario por padrao
    POSSIBLE = "possible"                # mostrar colapsado, usuario decide
    NOT_RECOMMENDED = "not_recommended"  # gerar mas esconder por padrao


class ProposalCategory(str, Enum):
    """Categoria operacional unificada da proposta.

    Sintese de RecommendationTier + GDQCapabilityStatus + tipo de regra
    em um rotulo unico e interpretavel para o usuario.
    """

    STRONG = "strong"                    # Segura para producao (RECOMMENDED + VALIDATED)
    CONSERVATIVE = "conservative"        # Simples e segura (built-in simples, alta cobertura)
    EXPERIMENTAL = "experimental"        # Boa evidencia, sintaxe nao validada em prod
    NEEDS_REVIEW = "needs_review"        # Metricas moderadas, precisa ajuste
    NOT_RECOMMENDED = "not_recommended"  # Evitar sem ajustes significativos


class GDQCapabilityStatus(str, Enum):
    """Status de suporte de uma feature no GDQ runtime real."""

    VALIDATED = "validated"      # testado e confirmado em producao
    EXPERIMENTAL = "experimental"  # funciona em testes, nao confirmado em prod
    UNKNOWN = "unknown"          # sem evidencia


class ExportOutputMode(str, Enum):
    """Modo de output do export."""
    GDQ_RUNTIME = "gdq_runtime"       # sintaxe final para cadastro
    ANALYTICAL_REPORT = "analytical"   # metadados + evidência


# ---------------------------------------------------------------------------
# Labels legíveis para tipos semanticos
# ---------------------------------------------------------------------------

SEMANTIC_TYPE_LABELS: dict[SemanticType, str] = {
    SemanticType.NUMERIC: "Numerico",
    SemanticType.CATEGORICAL_LOW_CARDINALITY: "Cat. Baixa",
    SemanticType.CATEGORICAL_MID_CARDINALITY: "Cat. Media",
    SemanticType.CATEGORICAL_HIGH_CARDINALITY: "Cat. Alta",
    SemanticType.DATETIME: "Data/Hora",
    SemanticType.IDENTIFIER: "Identificador",
    SemanticType.FREE_TEXT: "Texto Livre",
    SemanticType.UNKNOWN: "Desconhecido",
}


def get_semantic_label(semantic_type: SemanticType) -> str:
    """Retorna label legivel para o tipo semantico."""
    return SEMANTIC_TYPE_LABELS.get(semantic_type, semantic_type.value)


# ---------------------------------------------------------------------------
# Labels legíveis para tipos de regra
# ---------------------------------------------------------------------------

RULE_TYPE_LABELS: dict[RuleType, str] = {
    RuleType.MEAN_DUAL_GUARD: "Mean (Dinamico)",
    RuleType.STDDEV_DUAL_GUARD: "StdDev (Dinamico)",
    RuleType.NUMERIC_PERCENTILE_BAND: "Percentil (Dinamico)",
    RuleType.ALLOWED_VALUES: "Valores Permitidos",
    RuleType.CATEGORY_FREQUENCY_STATIC: "Frequencia (Estatico)",
    RuleType.CATEGORY_FREQUENCY_DYNAMIC: "Frequencia (Dinamico)",
    RuleType.CATEGORY_FREQUENCY_HYBRID: "Frequencia (Hibrido)",
    RuleType.DISTINCT_COUNT_EXACT: "Distintos (Exato)",
    RuleType.DISTINCT_COUNT_RANGE: "Distintos (Faixa)",
    RuleType.ROW_COUNT_DUAL_GUARD: "RowCount (Dinamico)",
    RuleType.IS_PRIMARY_KEY: "Chave Primaria",
    RuleType.UNIQUENESS_CUSTOM_SQL: "Unicidade (CustomSql)",
    RuleType.COMPLETENESS: "Completude",
    RuleType.CUSTOM_SQL: "CustomSql",
}


def get_rule_label(rule_type: RuleType) -> str:
    """Retorna label legivel para o tipo de regra."""
    return RULE_TYPE_LABELS.get(rule_type, rule_type.value.replace("_", " ").title())
