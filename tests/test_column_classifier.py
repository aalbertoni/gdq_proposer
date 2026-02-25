"""Testes para core/column_classifier.py.

Cenários conforme docs/technical_spec_v1.md seção 7:
- Camada 1: tipo nativo Athena (int → NUMERIC, date → DATETIME)
- Camada 2: string castável para número (>95%) → NUMERIC
- Camada 3: cardinalidade (low/mid/high)
- Edge cases: nulls, zeros, tipos parametrizados
"""

import pytest

from core.column_classifier import (
    classify_column,
    _normalize_athena_type,
    NUMERIC_CAST_THRESHOLD,
    LOW_CARDINALITY_MAX_DISTINCT,
    LOW_CARDINALITY_MAX_RATIO,
    MID_CARDINALITY_MAX_DISTINCT,
    MID_CARDINALITY_MAX_RATIO,
)
from core.models.enums import SemanticType


# ---------------------------------------------------------------------------
# Camada 1: tipos Athena nativos → NUMERIC
# ---------------------------------------------------------------------------

class TestNativeNumericTypes:
    @pytest.mark.parametrize("athena_type", [
        "int", "integer", "bigint", "smallint", "tinyint",
        "float", "double", "decimal", "real",
    ])
    def test_numeric_types(self, athena_type):
        result = classify_column(
            athena_type=athena_type,
            distinct_count=100,
            total_count=10000,
            non_null_count=10000,
        )
        assert result == SemanticType.NUMERIC

    def test_decimal_with_precision(self):
        """decimal(10,2) deve ser tratado como NUMERIC."""
        result = classify_column(
            athena_type="decimal(10,2)",
            distinct_count=500,
            total_count=10000,
            non_null_count=10000,
        )
        assert result == SemanticType.NUMERIC

    def test_double_ignores_cardinality(self):
        """Tipo nativo numérico sempre retorna NUMERIC, independente da cardinalidade."""
        result = classify_column(
            athena_type="double",
            distinct_count=5,
            total_count=10000,
            non_null_count=10000,
        )
        assert result == SemanticType.NUMERIC


# ---------------------------------------------------------------------------
# Camada 1: tipos Athena nativos → DATETIME
# ---------------------------------------------------------------------------

class TestNativeDateTypes:
    @pytest.mark.parametrize("athena_type", [
        "date", "timestamp", "timestamp with time zone",
    ])
    def test_date_types(self, athena_type):
        result = classify_column(
            athena_type=athena_type,
            distinct_count=30,
            total_count=10000,
            non_null_count=10000,
        )
        assert result == SemanticType.DATETIME


# ---------------------------------------------------------------------------
# Camada 2: string castável para número → NUMERIC
# ---------------------------------------------------------------------------

class TestStringNumericCast:
    def test_string_95_percent_castable(self):
        """String com 95% castável para número → NUMERIC."""
        result = classify_column(
            athena_type="string",
            distinct_count=100,
            total_count=10000,
            non_null_count=10000,
            numeric_cast_count=9500,  # 95%
        )
        assert result == SemanticType.NUMERIC

    def test_string_99_percent_castable(self):
        """String com 99% castável para número → NUMERIC."""
        result = classify_column(
            athena_type="string",
            distinct_count=100,
            total_count=10000,
            non_null_count=10000,
            numeric_cast_count=9900,
        )
        assert result == SemanticType.NUMERIC

    def test_string_94_percent_not_numeric(self):
        """String com 94% castável → NÃO é NUMERIC (abaixo do threshold)."""
        result = classify_column(
            athena_type="string",
            distinct_count=100,
            total_count=10000,
            non_null_count=10000,
            numeric_cast_count=9400,
        )
        assert result != SemanticType.NUMERIC

    def test_string_zero_castable(self):
        """String sem nenhum valor castável → categórica."""
        result = classify_column(
            athena_type="string",
            distinct_count=20,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=0,
        )
        assert result != SemanticType.NUMERIC

    def test_varchar_castable(self):
        """varchar também passa pela heurística de cast."""
        result = classify_column(
            athena_type="varchar(100)",
            distinct_count=50,
            total_count=10000,
            non_null_count=10000,
            numeric_cast_count=9800,
        )
        assert result == SemanticType.NUMERIC


# ---------------------------------------------------------------------------
# Camada 3: cardinalidade — CATEGORICAL_LOW
# ---------------------------------------------------------------------------

class TestCategoricalLow:
    def test_low_cardinality(self):
        """String com <=50 distintos e ratio <0.005 → LOW."""
        result = classify_column(
            athena_type="string",
            distinct_count=20,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=0,
        )
        assert result == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_low_cardinality_boundary_distinct(self):
        """Exatamente 50 distintos com ratio baixo → LOW."""
        result = classify_column(
            athena_type="string",
            distinct_count=50,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=0,
        )
        assert result == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_low_cardinality_3_values(self):
        """Típico: 3 valores distintos (ex: UF, status)."""
        result = classify_column(
            athena_type="string",
            distinct_count=3,
            total_count=50000,
            non_null_count=50000,
            numeric_cast_count=0,
        )
        assert result == SemanticType.CATEGORICAL_LOW_CARDINALITY


# ---------------------------------------------------------------------------
# Camada 3: cardinalidade — CATEGORICAL_MID
# ---------------------------------------------------------------------------

class TestCategoricalMid:
    def test_mid_cardinality(self):
        """String com ~300 distintos e ratio moderado → MID."""
        result = classify_column(
            athena_type="string",
            distinct_count=300,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=0,
        )
        assert result == SemanticType.CATEGORICAL_MID_CARDINALITY

    def test_mid_boundary_distinct(self):
        """Exatamente 500 distintos com ratio <0.05 → MID."""
        result = classify_column(
            athena_type="string",
            distinct_count=500,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=0,
        )
        assert result == SemanticType.CATEGORICAL_MID_CARDINALITY

    def test_51_distinct_but_high_ratio(self):
        """51 distintos mas ratio alto (>= 0.05) → não é LOW, pode ser MID."""
        # 51 distintos em 1100 rows → ratio 0.046 < 0.05 → MID
        result = classify_column(
            athena_type="string",
            distinct_count=51,
            total_count=1100,
            non_null_count=1100,
            numeric_cast_count=0,
        )
        assert result == SemanticType.CATEGORICAL_MID_CARDINALITY


# ---------------------------------------------------------------------------
# Camada 3: cardinalidade — CATEGORICAL_HIGH
# ---------------------------------------------------------------------------

class TestCategoricalHigh:
    def test_high_cardinality(self):
        """String com >500 distintos → HIGH."""
        result = classify_column(
            athena_type="string",
            distinct_count=10000,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=0,
        )
        assert result == SemanticType.CATEGORICAL_HIGH_CARDINALITY

    def test_501_distinct_values(self):
        """501 distintos ultrapassa limite MID → HIGH."""
        result = classify_column(
            athena_type="string",
            distinct_count=501,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=0,
        )
        assert result == SemanticType.CATEGORICAL_HIGH_CARDINALITY

    def test_high_ratio_few_distinct(self):
        """Poucos distintos mas ratio alto (dataset pequeno) → depende dos thresholds."""
        # 20 distintos em 100 rows → ratio 0.2 (>= 0.005 → não LOW)
        # 20 <= 500 mas ratio 0.2 >= 0.05 → não MID → HIGH
        result = classify_column(
            athena_type="string",
            distinct_count=20,
            total_count=100,
            non_null_count=100,
            numeric_cast_count=0,
        )
        assert result == SemanticType.CATEGORICAL_HIGH_CARDINALITY


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_all_nulls(self):
        """Coluna com 100% nulls → UNKNOWN."""
        result = classify_column(
            athena_type="string",
            distinct_count=0,
            total_count=10000,
            non_null_count=0,
            numeric_cast_count=0,
        )
        assert result == SemanticType.UNKNOWN

    def test_type_case_insensitive(self):
        """Tipo 'INT' maiúsculo → NUMERIC."""
        result = classify_column(
            athena_type="INT",
            distinct_count=100,
            total_count=10000,
            non_null_count=10000,
        )
        assert result == SemanticType.NUMERIC

    def test_type_with_whitespace(self):
        """Tipo com espaços extras → funciona."""
        result = classify_column(
            athena_type="  double  ",
            distinct_count=100,
            total_count=10000,
            non_null_count=10000,
        )
        assert result == SemanticType.NUMERIC

    def test_varchar_parametrized(self):
        """varchar(255) → normaliza para varchar (string)."""
        result = classify_column(
            athena_type="varchar(255)",
            distinct_count=10,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=0,
        )
        assert result == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_numeric_cast_count_defaults_zero(self):
        """Sem numeric_cast_count → não classifica como NUMERIC."""
        result = classify_column(
            athena_type="string",
            distinct_count=5,
            total_count=100000,
            non_null_count=100000,
        )
        assert result == SemanticType.CATEGORICAL_LOW_CARDINALITY


# ---------------------------------------------------------------------------
# _normalize_athena_type
# ---------------------------------------------------------------------------

class TestNormalizeAthenaType:
    @pytest.mark.parametrize("raw, expected", [
        ("int", "int"),
        ("INT", "int"),
        ("  double  ", "double"),
        ("decimal(10,2)", "decimal"),
        ("varchar(255)", "varchar"),
        ("timestamp with time zone", "timestamp with time zone"),
        ("BIGINT", "bigint"),
    ])
    def test_normalization(self, raw, expected):
        assert _normalize_athena_type(raw) == expected
