"""Testes para services/analysis_service.py.

Usa DuckDB (DuckDBTestClient) para validar query numeric_history
end-to-end: SQL → DataFrame normalizado com percentis expandidos.
"""

import math
import pytest

pytestmark = pytest.mark.integration
from datetime import date, timedelta

import pandas as pd
import pytest

from infra.query_builder import QueryBuilder
from infra.sql_dialect import SQLDialect
from services.analysis_service import AnalysisService
from core.models.dataset_config import DatasetConfig
from core.models.enums import PartitionMethod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client(tmp_path):
    """Cria DuckDBTestClient com tabela numérica para teste de histórico."""
    from tests.conftest import DuckDBTestClient

    client = DuckDBTestClient()

    # Gerar dados com 30 dias de datas recentes
    today = date.today()
    rows = []
    for day_offset in range(30):
        dt = (today - timedelta(days=day_offset)).isoformat()
        for j in range(100):
            rows.append({
                "dt_ref": dt,
                "VLR_SALDO": 100.0 + day_offset * 0.5 + j * 0.01,
                "QTD_PARCELAS": float(j % 12 + 1),
            })

    df = pd.DataFrame(rows)
    parquet_path = tmp_path / "tb_numeric.parquet"
    df.to_parquet(parquet_path)
    client.load_table("mock_db", "tb_numeric", str(parquet_path))
    return client


@pytest.fixture
def builder():
    return QueryBuilder(dialect=SQLDialect.DUCKDB)


@pytest.fixture
def service(mock_client, builder):
    return AnalysisService(client=mock_client, builder=builder)


@pytest.fixture
def base_config():
    return DatasetConfig(
        schema="mock_db",
        table="tb_numeric",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        partition_format="%Y-%m-%d",
        date_column="dt_ref",
        date_expression='CAST("dt_ref" AS DATE)',
        lookback_value=60,
    )


# ---------------------------------------------------------------------------
# get_numeric_history
# ---------------------------------------------------------------------------

class TestGetNumericHistory:
    def test_returns_dataframe_with_expected_columns(self, service, base_config):
        df = service.get_numeric_history(base_config, "VLR_SALDO")
        expected_cols = {
            "period", "mean", "stddev", "min", "max",
            "p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99",
            "non_null_count", "null_count", "total_count",
        }
        assert set(df.columns) == expected_cols

    def test_has_30_periods(self, service, base_config):
        df = service.get_numeric_history(base_config, "VLR_SALDO")
        assert len(df) == 30

    def test_mean_values_reasonable(self, service, base_config):
        df = service.get_numeric_history(base_config, "VLR_SALDO")
        # Mean should be around 100.x (base 100 + small offsets)
        assert all(95 < m < 120 for m in df["mean"])

    def test_stddev_values_positive(self, service, base_config):
        df = service.get_numeric_history(base_config, "VLR_SALDO")
        assert all(s > 0 for s in df["stddev"] if not math.isnan(s))

    def test_percentiles_expanded(self, service, base_config):
        df = service.get_numeric_history(base_config, "VLR_SALDO")
        # P01 < P25 < P50 < P75 < P99
        row = df.iloc[0]
        assert row["p01"] <= row["p25"] <= row["p50"] <= row["p75"] <= row["p99"]

    def test_total_count_per_period(self, service, base_config):
        df = service.get_numeric_history(base_config, "VLR_SALDO")
        # Each day has 100 rows
        assert all(df["total_count"] == 100)

    def test_null_count_zero(self, service, base_config):
        df = service.get_numeric_history(base_config, "VLR_SALDO")
        assert all(df["null_count"] == 0)

    def test_sorted_by_period(self, service, base_config):
        df = service.get_numeric_history(base_config, "VLR_SALDO")
        periods = list(df["period"])
        assert periods == sorted(periods)


# ---------------------------------------------------------------------------
# _parse_percentile_array
# ---------------------------------------------------------------------------

class TestParsePercentileArray:
    def test_list_input(self):
        result = AnalysisService._parse_percentile_array([1.0, 2.0, 3.0])
        assert result == [1.0, 2.0, 3.0]

    def test_string_input_json(self):
        result = AnalysisService._parse_percentile_array("[1.0, 2.0, 3.0]")
        assert result == [1.0, 2.0, 3.0]

    def test_none_input(self):
        result = AnalysisService._parse_percentile_array(None)
        assert result is None

    def test_tuple_input(self):
        result = AnalysisService._parse_percentile_array((1.0, 2.0))
        assert result == [1.0, 2.0]


# ---------------------------------------------------------------------------
# get_row_count_history
# ---------------------------------------------------------------------------

class TestGetRowCountHistory:
    def test_returns_dataframe_with_expected_columns(self, service, base_config):
        df = service.get_row_count_history(base_config)
        assert set(df.columns) == {"period", "row_count"}

    def test_has_30_periods(self, service, base_config):
        df = service.get_row_count_history(base_config)
        assert len(df) == 30

    def test_row_count_is_100_per_period(self, service, base_config):
        df = service.get_row_count_history(base_config)
        # Each day has 100 rows in our mock data
        assert all(df["row_count"] == 100.0)

    def test_sorted_by_period(self, service, base_config):
        df = service.get_row_count_history(base_config)
        periods = list(df["period"])
        assert periods == sorted(periods)

    def test_row_count_is_float(self, service, base_config):
        df = service.get_row_count_history(base_config)
        assert df["row_count"].dtype == float


# ---------------------------------------------------------------------------
# get_numeric_history_filtered (subpopulation)
# ---------------------------------------------------------------------------

@pytest.fixture
def segmented_client(tmp_path):
    """DuckDBTestClient com coluna de segmentacao TIPO_PRODUTO."""
    from tests.conftest import DuckDBTestClient

    client = DuckDBTestClient()
    today = date.today()
    rows = []
    for day_offset in range(30):
        dt = (today - timedelta(days=day_offset)).isoformat()
        # Subpop A: mean ~100
        for j in range(50):
            rows.append({
                "dt_ref": dt,
                "TIPO_PRODUTO": "A",
                "VLR_SALDO": 100.0 + day_offset * 0.5 + j * 0.01,
            })
        # Subpop B: mean ~200
        for j in range(50):
            rows.append({
                "dt_ref": dt,
                "TIPO_PRODUTO": "B",
                "VLR_SALDO": 200.0 + day_offset * 0.5 + j * 0.01,
            })

    df = pd.DataFrame(rows)
    parquet_path = tmp_path / "tb_segmented.parquet"
    df.to_parquet(parquet_path)
    client.load_table("mock_db", "tb_segmented", str(parquet_path))
    return client


@pytest.fixture
def seg_service(segmented_client, builder):
    return AnalysisService(client=segmented_client, builder=builder)


@pytest.fixture
def seg_config():
    return DatasetConfig(
        schema="mock_db",
        table="tb_segmented",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        partition_format="%Y-%m-%d",
        date_column="dt_ref",
        date_expression='CAST("dt_ref" AS DATE)',
        lookback_value=60,
    )


class TestGetNumericHistoryFiltered:
    def test_returns_expected_columns(self, seg_service, seg_config):
        df = seg_service.get_numeric_history_filtered(
            seg_config, "VLR_SALDO", "\"TIPO_PRODUTO\" = 'A'",
        )
        expected_cols = {
            "period", "mean", "stddev", "min", "max",
            "p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99",
            "non_null_count", "null_count", "total_count",
        }
        assert set(df.columns) == expected_cols

    def test_has_30_periods(self, seg_service, seg_config):
        df = seg_service.get_numeric_history_filtered(
            seg_config, "VLR_SALDO", "\"TIPO_PRODUTO\" = 'A'",
        )
        assert len(df) == 30

    def test_filtered_total_count_is_half(self, seg_service, seg_config):
        """Subpop A has 50 rows/day, full table has 100."""
        df_full = seg_service.get_numeric_history(seg_config, "VLR_SALDO")
        df_a = seg_service.get_numeric_history_filtered(
            seg_config, "VLR_SALDO", "\"TIPO_PRODUTO\" = 'A'",
        )
        assert all(df_a["total_count"] < df_full["total_count"])

    def test_different_subpops_have_different_means(self, seg_service, seg_config):
        """Subpop B mean (~200) > subpop A mean (~100)."""
        df_a = seg_service.get_numeric_history_filtered(
            seg_config, "VLR_SALDO", "\"TIPO_PRODUTO\" = 'A'",
        )
        df_b = seg_service.get_numeric_history_filtered(
            seg_config, "VLR_SALDO", "\"TIPO_PRODUTO\" = 'B'",
        )
        assert df_b["mean"].mean() > df_a["mean"].mean() + 50
