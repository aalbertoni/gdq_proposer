"""Golden dataset para regressao funcional.

Define 14 cenarios representativos com dados sinteticos e expected outputs.
Qualquer mudanca no motor que altere estes resultados e uma regressao
que deve ser revisada conscientemente.

Cenarios cobertos:
1.  numeric_stable       — numerica estavel (double, alta cardinalidade)
2.  numeric_volatile     — numerica volatil (CV > 30%)
3.  identifier_bigint    — identificador inteiro (bigint, alta cardinalidade, alta ratio)
4.  code_int_low_card    — codigo numerico (int, <= 20 distintos)
5.  categorical_low      — categorica low (varchar, <= 50 distintos, < 0.5%)
6.  categorical_mid      — categorica mid (varchar, 51-500 distintos, < 5%)
7.  freetext_high        — texto livre (varchar, alta cardinalidade)
8.  datetime_as_string   — datetime como string (varchar, cast 95%+ numerico = False)
9.  structural_break     — serie com quebra estrutural
10. seasonal_weekly      — serie com sazonalidade semanal
11. sparse_numeric       — numerica com >= 30% nulos
12. zero_inflated        — numerica com >= 30% zeros
13. primary_key_simple   — chave primaria simples
14. composite_key        — chave composta (2 colunas)
"""

from dataclasses import dataclass, field
from core.models.enums import SemanticType, RuleType, SeriesRegime, ConfidenceLevel


@dataclass(frozen=True)
class GoldenScenario:
    """Um cenario do golden dataset com inputs e expected outputs."""

    name: str
    description: str

    # --- Inputs para classify_column ---
    athena_type: str
    distinct_count: int
    total_count: int
    non_null_count: int
    numeric_cast_count: int = 0

    # --- Expected: classificacao ---
    expected_semantic_type: SemanticType = SemanticType.UNKNOWN

    # --- Expected: regras elegiveis ---
    expected_rule_types: tuple[RuleType, ...] = ()

    # --- Expected: regime (para series numericas) ---
    expected_regime: SeriesRegime | None = None

    # --- Expected: confianca minima ---
    expected_min_confidence: ConfidenceLevel | None = None

    # --- Expected: warnings esperados (substrings) ---
    expected_warning_substrings: tuple[str, ...] = ()

    # --- Expected: reclassificacao sugerida ---
    expected_reclassification: SemanticType | None = None


# ---------------------------------------------------------------------------
# 14 cenarios golden
# ---------------------------------------------------------------------------

GOLDEN_SCENARIOS: list[GoldenScenario] = [
    # 1. Numerica estavel
    GoldenScenario(
        name="numeric_stable",
        description="Coluna double com alta cardinalidade — classificada como NUMERIC",
        athena_type="double",
        distinct_count=5000,
        total_count=100000,
        non_null_count=100000,
        expected_semantic_type=SemanticType.NUMERIC,
        expected_rule_types=(
            RuleType.MEAN_DUAL_GUARD,
            RuleType.STDDEV_DUAL_GUARD,
            RuleType.COMPLETENESS,
        ),
        expected_regime=SeriesRegime.STABLE,
        expected_min_confidence=ConfidenceLevel.HIGH,
    ),
    # 2. Numerica volatil
    GoldenScenario(
        name="numeric_volatile",
        description="Coluna double com alta cardinalidade — CV > 30% = VOLATILE",
        athena_type="double",
        distinct_count=8000,
        total_count=100000,
        non_null_count=100000,
        expected_semantic_type=SemanticType.NUMERIC,
        expected_rule_types=(
            RuleType.MEAN_DUAL_GUARD,
            RuleType.STDDEV_DUAL_GUARD,
            RuleType.COMPLETENESS,
        ),
        expected_regime=SeriesRegime.VOLATILE,
    ),
    # 3. Identificador bigint
    GoldenScenario(
        name="identifier_bigint",
        description="Bigint com >= 10k distintos e ratio >= 50% — IDENTIFIER",
        athena_type="bigint",
        distinct_count=80000,
        total_count=100000,
        non_null_count=100000,
        expected_semantic_type=SemanticType.NUMERIC,
        expected_reclassification=SemanticType.IDENTIFIER,
    ),
    # 4. Codigo numerico (int com <= 20 distintos)
    GoldenScenario(
        name="code_int_low_card",
        description="Int com <= 20 distintos — NUMERIC mas sugerido como CATEGORICAL_LOW",
        athena_type="int",
        distinct_count=5,
        total_count=100000,
        non_null_count=100000,
        expected_semantic_type=SemanticType.NUMERIC,
        expected_reclassification=SemanticType.CATEGORICAL_LOW_CARDINALITY,
    ),
    # 5. Categorica low (varchar)
    GoldenScenario(
        name="categorical_low",
        description="Varchar com 3 distintos em 100k linhas — CATEGORICAL_LOW",
        athena_type="varchar",
        distinct_count=3,
        total_count=100000,
        non_null_count=100000,
        numeric_cast_count=0,
        expected_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY,
        expected_rule_types=(
            RuleType.ALLOWED_VALUES,
            RuleType.DISTINCT_COUNT_EXACT,
            RuleType.COMPLETENESS,
        ),
    ),
    # 6. Categorica mid (varchar)
    GoldenScenario(
        name="categorical_mid",
        description="Varchar com 200 distintos em 100k linhas — CATEGORICAL_MID",
        athena_type="varchar",
        distinct_count=200,
        total_count=100000,
        non_null_count=100000,
        numeric_cast_count=0,
        expected_semantic_type=SemanticType.CATEGORICAL_MID_CARDINALITY,
        expected_rule_types=(
            RuleType.DISTINCT_COUNT_RANGE,
            RuleType.COMPLETENESS,
        ),
    ),
    # 7. Texto livre (varchar alta cardinalidade)
    GoldenScenario(
        name="freetext_high",
        description="Varchar com 50k distintos em 100k linhas — CATEGORICAL_HIGH",
        athena_type="varchar",
        distinct_count=50000,
        total_count=100000,
        non_null_count=100000,
        numeric_cast_count=0,
        expected_semantic_type=SemanticType.CATEGORICAL_HIGH_CARDINALITY,
        # High cardinality: apenas Completeness se null_ratio baixa
    ),
    # 8. Datetime como string
    GoldenScenario(
        name="datetime_as_string",
        description="Varchar com datas (2026-01-01), cast numerico falha — CATEGORICAL_LOW",
        athena_type="varchar",
        distinct_count=30,
        total_count=100000,
        non_null_count=100000,
        numeric_cast_count=0,  # datas nao sao castaveis para double
        expected_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY,
    ),
    # 9. Serie com quebra estrutural
    GoldenScenario(
        name="structural_break",
        description="Serie numerica com mudanca de regime no meio",
        athena_type="double",
        distinct_count=5000,
        total_count=100000,
        non_null_count=100000,
        expected_semantic_type=SemanticType.NUMERIC,
        expected_regime=SeriesRegime.STRUCTURAL_BREAK,
    ),
    # 10. Serie sazonal
    GoldenScenario(
        name="seasonal_weekly",
        description="Serie numerica com padrao semanal claro",
        athena_type="double",
        distinct_count=5000,
        total_count=100000,
        non_null_count=100000,
        expected_semantic_type=SemanticType.NUMERIC,
        expected_regime=SeriesRegime.SEASONAL,
    ),
    # 11. Sparse (>= 30% nulos)
    GoldenScenario(
        name="sparse_numeric",
        description="Coluna double com 35% nulos",
        athena_type="double",
        distinct_count=3000,
        total_count=100000,
        non_null_count=65000,
        expected_semantic_type=SemanticType.NUMERIC,
        expected_regime=SeriesRegime.SPARSE,
    ),
    # 12. Zero-inflated
    GoldenScenario(
        name="zero_inflated",
        description="Coluna double com 40% zeros",
        athena_type="double",
        distinct_count=4000,
        total_count=100000,
        non_null_count=100000,
        expected_semantic_type=SemanticType.NUMERIC,
        expected_regime=SeriesRegime.ZERO_INFLATED,
    ),
    # 13. Chave primaria simples
    GoldenScenario(
        name="primary_key_simple",
        description="Bigint com 100% unicidade — identificador para PK",
        athena_type="bigint",
        distinct_count=100000,
        total_count=100000,
        non_null_count=100000,
        expected_semantic_type=SemanticType.NUMERIC,
        expected_reclassification=SemanticType.IDENTIFIER,
    ),
    # 14. Chave composta (testado via propose_table_rules)
    GoldenScenario(
        name="composite_key",
        description="Duas colunas que juntas sao unicas",
        athena_type="bigint",
        distinct_count=50000,
        total_count=100000,
        non_null_count=100000,
        expected_semantic_type=SemanticType.NUMERIC,
        expected_reclassification=SemanticType.IDENTIFIER,
    ),
]

# Index por nome para acesso direto
GOLDEN_BY_NAME: dict[str, GoldenScenario] = {s.name: s for s in GOLDEN_SCENARIOS}
