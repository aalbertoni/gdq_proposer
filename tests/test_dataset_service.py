"""Testes para services/dataset_service.py.

Usa DuckDB (DuckDBTestClient) com dados sintéticos em memória.
"""

import pytest

pytestmark = pytest.mark.integration
import pandas as pd

from infra.query_builder import QueryBuilder
from infra.sql_dialect import SQLDialect
from services.dataset_service import DatasetService
from core.models.dataset_config import DatasetConfig
from core.models.enums import PartitionMethod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client(tmp_path):
    """Cria DuckDBTestClient com tabela de teste."""
    from tests.conftest import DuckDBTestClient
    client = DuckDBTestClient()
    df = pd.DataFrame({
        "dt_ref": pd.date_range("2026-01-01", periods=30, freq="D").astype(str),
        "COD_PRODUTO": ["A", "B", "C"] * 10,
        "VLR_SALDO": [100.0 + i for i in range(30)],
        "QTD_PARCELAS": list(range(1, 31)),
    })
    parquet_path = tmp_path / "tb_teste.parquet"
    df.to_parquet(parquet_path)
    client.load_table("mock_db", "tb_teste", str(parquet_path))
    return client


@pytest.fixture
def builder():
    return QueryBuilder(dialect=SQLDialect.DUCKDB)


@pytest.fixture
def service(mock_client, builder):
    return DatasetService(client=mock_client, builder=builder)


@pytest.fixture
def base_config():
    return DatasetConfig(
        schema="mock_db",
        table="tb_teste",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
    )


# ---------------------------------------------------------------------------
# validate_table
# ---------------------------------------------------------------------------

class TestValidateTable:
    def test_existing_table(self, service):
        assert service.validate_table("mock_db", "tb_teste") is True

    def test_nonexistent_table(self, service):
        assert service.validate_table("mock_db", "tabela_fake") is False

    def test_invalid_schema_raises(self, service):
        with pytest.raises(ValueError, match="Identificador inválido"):
            service.validate_table("bad schema!", "tb_teste")

    def test_invalid_table_raises(self, service):
        with pytest.raises(ValueError, match="Identificador inválido"):
            service.validate_table("mock_db", "bad;table")


# ---------------------------------------------------------------------------
# get_columns
# ---------------------------------------------------------------------------

class TestGetColumns:
    def test_returns_all_columns(self, service):
        cols = service.get_columns("mock_db", "tb_teste")
        col_names = [c["name"] for c in cols]
        assert "dt_ref" in col_names
        assert "COD_PRODUTO" in col_names
        assert "VLR_SALDO" in col_names
        assert "QTD_PARCELAS" in col_names

    def test_returns_types(self, service):
        cols = service.get_columns("mock_db", "tb_teste")
        col_map = {c["name"]: c["type"] for c in cols}
        # DuckDB types from parquet
        assert "VARCHAR" in col_map["dt_ref"].upper() or "TEXT" in col_map["dt_ref"].upper()
        assert "DOUBLE" in col_map["VLR_SALDO"].upper() or "FLOAT" in col_map["VLR_SALDO"].upper()

    def test_invalid_identifier_raises(self, service):
        with pytest.raises(ValueError, match="Identificador inválido"):
            service.get_columns("mock_db", "DROP TABLE")


# ---------------------------------------------------------------------------
# get_date_range
# ---------------------------------------------------------------------------

class TestGetDateRange:
    def test_returns_range(self, service, base_config):
        result = service.get_date_range(base_config)
        assert result["min_date"] is not None
        assert result["max_date"] is not None
        assert result["n_periods"] == 30

    def test_min_max_correct(self, service, base_config):
        result = service.get_date_range(base_config)
        assert "2026-01-01" in result["min_date"]
        assert "2026-01-30" in result["max_date"]

    def test_with_base_filter(self, service, base_config):
        base_config.base_filter_sql = "COD_PRODUTO = 'A'"
        result = service.get_date_range(base_config)
        assert result["n_periods"] == 10  # 30 dias / 3 produtos = 10 por produto

    def test_invalid_temporal_col_raises(self, service):
        config = DatasetConfig(
            schema="mock_db",
            table="tb_teste",
            date_column="bad col!",
        )
        with pytest.raises(ValueError, match="Identificador inválido"):
            service.get_date_range(config)


# ---------------------------------------------------------------------------
# get_volume_by_period
# ---------------------------------------------------------------------------

class TestGetVolumeByPeriod:
    def test_returns_periods(self, service, base_config):
        result = service.get_volume_by_period(base_config)
        assert len(result) == 30
        for row in result:
            assert "period" in row
            assert "row_count" in row

    def test_row_count_correct(self, service, base_config):
        result = service.get_volume_by_period(base_config)
        # Cada dia tem 1 row no nosso dataset
        for row in result:
            assert row["row_count"] == 1

    def test_limit_works(self, service, base_config):
        result = service.get_volume_by_period(base_config, limit=5)
        assert len(result) == 5

    def test_ordered_descending(self, service, base_config):
        result = service.get_volume_by_period(base_config, limit=5)
        periods = [r["period"] for r in result]
        assert periods == sorted(periods, reverse=True)

    def test_with_base_filter(self, service, base_config):
        base_config.base_filter_sql = "COD_PRODUTO = 'A'"
        result = service.get_volume_by_period(base_config)
        assert len(result) == 10


# ---------------------------------------------------------------------------
# get_partitions
# ---------------------------------------------------------------------------

class TestGetPartitions:
    def test_returns_empty_on_error(self, service):
        # Tabela sem coluna partition_0 → erro → retorna []
        result = service.get_partitions("mock_db", "tb_teste")
        assert result == []
