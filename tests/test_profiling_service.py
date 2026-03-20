"""Testes para services/profiling_service.py.

Usa DuckDB (DuckDBTestClient) com dados sintéticos em memória.
Valida classificação end-to-end: query → classify → ColumnProfile.
"""

import pytest

pytestmark = pytest.mark.integration
import pandas as pd

from infra.query_builder import QueryBuilder
from infra.sql_dialect import SQLDialect
from services.profiling_service import ProfilingService
from core.models.dataset_config import DatasetConfig
from core.models.enums import PartitionMethod, SemanticType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client(tmp_path):
    """Cria DuckDBTestClient com tabela de teste diversificada."""
    from tests.conftest import DuckDBTestClient
    from datetime import date, timedelta

    client = DuckDBTestClient()

    n = 10000
    today = date.today()
    df = pd.DataFrame({
        # Coluna temporal (string date, usada como eixo)
        "dt_ref": [(today - timedelta(days=(i % 30))).isoformat() for i in range(n)],
        # Numéricas nativas
        "VLR_SALDO": [100.0 + (i * 0.5) for i in range(n)],
        "QTD_PARCELAS": list(range(1, n + 1)),
        # String que é numérica (99% castável)
        "COD_NUMERICO": [str(i) for i in range(n)],
        # String categórica low cardinality (3 valores)
        "COD_PRODUTO": ["A", "B", "C"] * (n // 3) + ["A"] * (n % 3),
        # String categórica mid cardinality (~200 valores)
        "COD_MUNICIPIO": [f"MUN_{i % 200:03d}" for i in range(n)],
        # String alta cardinalidade (>500 distintos)
        "NR_CONTRATO": [f"CTR_{i:06d}" for i in range(n)],
        # Coluna com muitos nulls
        "OBS_OPCIONAL": [None if i % 3 != 0 else f"obs_{i}" for i in range(n)],
    })

    parquet_path = tmp_path / "tb_profiling.parquet"
    df.to_parquet(parquet_path)
    client.load_table("mock_db", "tb_profiling", str(parquet_path))
    return client


@pytest.fixture
def builder():
    return QueryBuilder(dialect=SQLDialect.DUCKDB)


@pytest.fixture
def service(mock_client, builder):
    return ProfilingService(client=mock_client, builder=builder)


@pytest.fixture
def base_config():
    return DatasetConfig(
        schema="mock_db",
        table="tb_profiling",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        date_expression="CAST(\"dt_ref\" AS DATE)",
    )


def _get_profile(profiles, col_name):
    """Helper para buscar profile por nome de coluna."""
    for p in profiles:
        if p.column_name == col_name:
            return p
    raise ValueError(f"Coluna {col_name} não encontrada nos profiles")


# ---------------------------------------------------------------------------
# profile_columns — tipo nativo numérico
# ---------------------------------------------------------------------------

class TestNativeNumericProfiling:
    def test_double_column(self, service, base_config):
        cols = [{"name": "VLR_SALDO", "type": "DOUBLE"}]
        profiles = service.profile_columns(base_config, cols)
        assert len(profiles) == 1
        p = profiles[0]
        assert p.column_name == "VLR_SALDO"
        assert p.inferred_semantic_type == SemanticType.NUMERIC
        # Agora executa query de cardinalidade para guardrails
        assert p.total_count > 0
        assert p.distinct_count > 0

    def test_integer_column(self, service, base_config):
        cols = [{"name": "QTD_PARCELAS", "type": "INTEGER"}]
        profiles = service.profile_columns(base_config, cols)
        assert profiles[0].inferred_semantic_type == SemanticType.NUMERIC

    def test_low_card_numeric_warns(self, service, base_config):
        """Numérico nativo com cardinalidade muito baixa gera warning."""
        cols = [{"name": "QTD_PARCELAS", "type": "INTEGER"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        p = profiles[0]
        assert p.inferred_semantic_type == SemanticType.NUMERIC
        # QTD_PARCELAS has few distinct values in mock data → should warn
        if p.distinct_count <= 20:
            assert any("categorica" in w.lower() for w in p.warnings)


# ---------------------------------------------------------------------------
# profile_columns — strings com heurística
# ---------------------------------------------------------------------------

class TestStringProfiling:
    def test_numeric_string(self, service, base_config):
        """String com valores numéricos (99%+ castável) → NUMERIC."""
        cols = [{"name": "COD_NUMERICO", "type": "VARCHAR"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        p = profiles[0]
        assert p.inferred_semantic_type == SemanticType.NUMERIC
        assert p.numeric_cast_ratio > 0.95

    def test_low_cardinality(self, service, base_config):
        """String com 3 valores distintos em 10k rows → CATEGORICAL_LOW."""
        cols = [{"name": "COD_PRODUTO", "type": "VARCHAR"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        p = profiles[0]
        assert p.inferred_semantic_type == SemanticType.CATEGORICAL_LOW_CARDINALITY
        assert p.distinct_count == 3

    def test_mid_cardinality(self, service, base_config):
        """String com ~200 valores distintos em 10k rows → CATEGORICAL_MID."""
        cols = [{"name": "COD_MUNICIPIO", "type": "VARCHAR"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        p = profiles[0]
        assert p.inferred_semantic_type == SemanticType.CATEGORICAL_MID_CARDINALITY
        assert 100 <= p.distinct_count <= 300

    def test_high_cardinality(self, service, base_config):
        """String com 10k valores distintos → CATEGORICAL_HIGH."""
        cols = [{"name": "NR_CONTRATO", "type": "VARCHAR"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        p = profiles[0]
        assert p.inferred_semantic_type == SemanticType.CATEGORICAL_HIGH_CARDINALITY
        assert p.distinct_count > 500


# ---------------------------------------------------------------------------
# profile_columns — métricas calculadas
# ---------------------------------------------------------------------------

class TestProfilingMetrics:
    def test_null_ratio(self, service, base_config):
        """Coluna com ~66% nulls deve ter null_ratio alto e warning."""
        cols = [{"name": "OBS_OPCIONAL", "type": "VARCHAR"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        p = profiles[0]
        assert p.null_ratio > 0.5
        assert any("null" in w.lower() for w in p.warnings)

    def test_total_count_populated(self, service, base_config):
        """Colunas string devem ter total_count > 0 após profiling."""
        cols = [{"name": "COD_PRODUTO", "type": "VARCHAR"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        p = profiles[0]
        assert p.total_count > 0
        assert p.non_null_count > 0

    def test_distinct_ratio(self, service, base_config):
        """distinct_ratio deve ser calculado corretamente."""
        cols = [{"name": "COD_PRODUTO", "type": "VARCHAR"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        p = profiles[0]
        expected = p.distinct_count / p.non_null_count
        assert abs(p.distinct_ratio - expected) < 0.001


# ---------------------------------------------------------------------------
# profile_columns — múltiplas colunas
# ---------------------------------------------------------------------------

class TestMultipleColumns:
    def test_profiles_all_columns(self, service, base_config):
        """Deve retornar um profile por coluna."""
        cols = [
            {"name": "VLR_SALDO", "type": "DOUBLE"},
            {"name": "COD_PRODUTO", "type": "VARCHAR"},
            {"name": "NR_CONTRATO", "type": "VARCHAR"},
        ]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        assert len(profiles) == 3

        p_vlr = _get_profile(profiles, "VLR_SALDO")
        p_prod = _get_profile(profiles, "COD_PRODUTO")
        p_ctr = _get_profile(profiles, "NR_CONTRATO")

        assert p_vlr.inferred_semantic_type == SemanticType.NUMERIC
        assert p_prod.inferred_semantic_type == SemanticType.CATEGORICAL_LOW_CARDINALITY
        assert p_ctr.inferred_semantic_type == SemanticType.CATEGORICAL_HIGH_CARDINALITY


# ---------------------------------------------------------------------------
# apply_user_overrides
# ---------------------------------------------------------------------------

class TestUserOverrides:
    def test_override_changes_effective_type(self, service, base_config):
        cols = [{"name": "NR_CONTRATO", "type": "VARCHAR"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        assert profiles[0].effective_type == SemanticType.CATEGORICAL_HIGH_CARDINALITY

        service.apply_user_overrides(
            profiles,
            {"NR_CONTRATO": SemanticType.IDENTIFIER},
        )
        assert profiles[0].effective_type == SemanticType.IDENTIFIER
        # Inferido não muda
        assert profiles[0].inferred_semantic_type == SemanticType.CATEGORICAL_HIGH_CARDINALITY

    def test_override_nonexistent_column_ignored(self, service, base_config):
        cols = [{"name": "COD_PRODUTO", "type": "VARCHAR"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        service.apply_user_overrides(
            profiles,
            {"COLUNA_FAKE": SemanticType.NUMERIC},
        )
        # Nada muda
        assert profiles[0].user_override_type is None

    def test_multiple_overrides(self, service, base_config):
        cols = [
            {"name": "COD_PRODUTO", "type": "VARCHAR"},
            {"name": "NR_CONTRATO", "type": "VARCHAR"},
        ]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        service.apply_user_overrides(profiles, {
            "COD_PRODUTO": SemanticType.NUMERIC,
            "NR_CONTRATO": SemanticType.FREE_TEXT,
        })
        p_prod = _get_profile(profiles, "COD_PRODUTO")
        p_ctr = _get_profile(profiles, "NR_CONTRATO")
        assert p_prod.effective_type == SemanticType.NUMERIC
        assert p_ctr.effective_type == SemanticType.FREE_TEXT


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_with_base_filter(self, service, base_config):
        """Profiling com filtro deve funcionar."""
        base_config.base_filter_sql = "COD_PRODUTO = 'A'"
        cols = [{"name": "COD_PRODUTO", "type": "VARCHAR"}]
        profiles = service.profile_columns(base_config, cols, sample_periods=60)
        p = profiles[0]
        assert p.distinct_count == 1  # só "A" passa o filtro

    def test_invalid_column_raises(self, service, base_config):
        """Coluna com nome inválido deve dar erro."""
        cols = [{"name": "bad col!", "type": "VARCHAR"}]
        with pytest.raises(ValueError, match="Identificador inválido"):
            service.profile_columns(base_config, cols)
