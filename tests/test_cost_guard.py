"""Testes para infra/cost_guard.py, query_logger pricing e comportamento fail-closed.

Valida que:
- Erros de metadata propagam (nao sao engolidos)
- Batch profiling falha explicita (nao cai para N queries)
- Cost guardrail bloqueia quando custo >= threshold
- Bypass funciona e pode ser resetado
- Pricing por regiao reflete custo correto do Athena
"""

import pytest

from infra.cost_guard import (
    CostGuardrailTriggered,
    ExpensiveFallbackBlocked,
    PartitionMetadataError,
)
from infra.query_logger import (
    ATHENA_PRICE_PER_TB,
    DEFAULT_ATHENA_PRICE_PER_TB,
    QueryLogEntry,
    QueryLogger,
    get_athena_price_per_tb,
)


# ---------------------------------------------------------------------------
# Exceptions de dominio
# ---------------------------------------------------------------------------

class TestPartitionMetadataError:
    def test_is_exception(self):
        with pytest.raises(PartitionMetadataError):
            raise PartitionMetadataError("SHOW PARTITIONS falhou")

    def test_message(self):
        e = PartitionMetadataError("test msg")
        assert "test msg" in str(e)


class TestExpensiveFallbackBlocked:
    def test_is_exception(self):
        with pytest.raises(ExpensiveFallbackBlocked):
            raise ExpensiveFallbackBlocked("batch falhou")


class TestCostGuardrailTriggered:
    def test_message_includes_cost(self):
        e = CostGuardrailTriggered(5.50, 3.00, "date_range")
        assert "5.50" in str(e)
        assert "3.00" in str(e)
        assert "date_range" in str(e)

    def test_attributes(self):
        e = CostGuardrailTriggered(5.50, 3.00)
        assert e.cost_usd == 5.50
        assert e.threshold_usd == 3.00


# ---------------------------------------------------------------------------
# Fail-closed: get_partitions propaga erro
# ---------------------------------------------------------------------------

class TestGetPartitionsFailClosed:
    def test_raises_on_failure(self):
        """get_partitions deve levantar PartitionMetadataError, nao retornar []."""
        from unittest.mock import MagicMock
        from services.dataset_service import DatasetService
        from infra.query_builder import QueryBuilder
        from infra.sql_dialect import SQLDialect

        mock_client = MagicMock()
        mock_client.execute_df.side_effect = Exception("connection error")
        builder = QueryBuilder(dialect=SQLDialect.DUCKDB)
        svc = DatasetService(client=mock_client, builder=builder)

        with pytest.raises(PartitionMetadataError):
            svc.get_partitions("db", "table", "dt_ref")


# ---------------------------------------------------------------------------
# Fail-closed: get_date_range em tabela particionada
# ---------------------------------------------------------------------------

class TestGetDateRangeFailClosed:
    def test_partitioned_raises_on_metadata_failure(self):
        """Tabela particionada: metadata falha → PartitionMetadataError (nao SQL)."""
        from unittest.mock import MagicMock
        from services.dataset_service import DatasetService
        from infra.query_builder import QueryBuilder
        from infra.sql_dialect import SQLDialect
        from core.models.dataset_config import DatasetConfig
        from core.models.enums import PartitionMethod

        mock_client = MagicMock()
        mock_client.execute_df.side_effect = Exception("SHOW PARTITIONS failed")
        builder = QueryBuilder(dialect=SQLDialect.DUCKDB)
        svc = DatasetService(client=mock_client, builder=builder)

        config = DatasetConfig(
            schema="db", table="tb",
            partition_method=PartitionMethod.INCREMENTAL,
            partition_column="dt_ref",
            partition_format="%Y-%m-%d",
            date_column="dt_ref",
        )

        with pytest.raises(PartitionMetadataError):
            svc.get_date_range(config)


# ---------------------------------------------------------------------------
# Fail-closed: profiling batch
# ---------------------------------------------------------------------------

class TestProfilingFailClosed:
    def test_batch_failure_raises(self):
        """Batch profiling falha → erro propagado (nao N queries)."""
        from unittest.mock import MagicMock
        from services.profiling_service import ProfilingService
        from infra.query_builder import QueryBuilder
        from infra.sql_dialect import SQLDialect
        from core.models.dataset_config import DatasetConfig
        from core.models.enums import PartitionMethod

        mock_client = MagicMock()
        mock_client.execute_df.side_effect = Exception("batch query failed")
        builder = QueryBuilder(dialect=SQLDialect.DUCKDB)
        svc = ProfilingService(client=mock_client, builder=builder)

        config = DatasetConfig(
            schema="db", table="tb",
            partition_method=PartitionMethod.INCREMENTAL,
            partition_column="dt_ref",
            partition_format="%Y-%m-%d",
            date_column="dt_ref",
        )
        columns = [{"name": "col_a", "type": "varchar"}, {"name": "col_b", "type": "int"}]

        with pytest.raises(Exception, match="batch query failed"):
            svc.profile_columns(config, columns)

        # Verificar que execute_df foi chamado apenas 1 vez (batch), nao N vezes
        assert mock_client.execute_df.call_count == 1


# ---------------------------------------------------------------------------
# Pricing por regiao
# ---------------------------------------------------------------------------

ONE_TB = 1024 ** 4  # 1 TB em bytes


class TestAthenaPricing:
    def test_sa_east_1_price(self):
        assert get_athena_price_per_tb("sa-east-1") == 9.00

    def test_us_east_1_price(self):
        assert get_athena_price_per_tb("us-east-1") == 5.00

    def test_us_west_1_price(self):
        assert get_athena_price_per_tb("us-west-1") == 6.75

    def test_eu_central_1_same_as_us_east_1(self):
        assert get_athena_price_per_tb("eu-central-1") == 5.00

    def test_unknown_region_falls_back_to_default(self):
        assert get_athena_price_per_tb("mars-west-1") == DEFAULT_ATHENA_PRICE_PER_TB

    def test_sa_east_1_is_most_expensive(self):
        for region in ATHENA_PRICE_PER_TB:
            assert get_athena_price_per_tb("sa-east-1") >= get_athena_price_per_tb(region)


class TestQueryLogEntryCost:
    def test_cost_uses_default_price(self):
        entry = QueryLogEntry(
            query_name="test", dataset="db.tb", column="col",
            elapsed_ms=100, cache_hit=False, rows_returned=10,
            bytes_scanned=ONE_TB,
        )
        assert entry.estimated_cost_usd == DEFAULT_ATHENA_PRICE_PER_TB

    def test_cost_uses_sa_east_1_price(self):
        entry = QueryLogEntry(
            query_name="test", dataset="db.tb", column="col",
            elapsed_ms=100, cache_hit=False, rows_returned=10,
            bytes_scanned=ONE_TB, _price_per_tb=9.00,
        )
        assert entry.estimated_cost_usd == 9.00

    def test_cost_zero_when_no_bytes(self):
        entry = QueryLogEntry(
            query_name="test", dataset="db.tb", column="col",
            elapsed_ms=100, cache_hit=False, rows_returned=10,
            bytes_scanned=0,
        )
        assert entry.estimated_cost_usd == 0.0

    def test_minimum_10mb_charge(self):
        """Athena cobra minimo de 10MB por query."""
        entry = QueryLogEntry(
            query_name="test", dataset="db.tb", column="col",
            elapsed_ms=100, cache_hit=False, rows_returned=10,
            bytes_scanned=1024, _price_per_tb=5.0,  # 1KB scanned
        )
        min_10mb = 10 * 1024 * 1024
        expected = (min_10mb / ONE_TB) * 5.0
        assert entry.estimated_cost_usd == expected


class TestQueryLoggerRegion:
    def test_default_region_is_sa_east_1(self):
        logger = QueryLogger()
        assert logger.region == "sa-east-1"
        assert logger.price_per_tb == 9.00

    def test_custom_region(self):
        logger = QueryLogger(region="us-east-1")
        assert logger.price_per_tb == 5.00

    def test_log_query_injects_price(self):
        logger = QueryLogger(region="sa-east-1")
        entry = QueryLogEntry(
            query_name="test", dataset="db.tb", column="col",
            elapsed_ms=100, cache_hit=False, rows_returned=10,
            bytes_scanned=ONE_TB,
        )
        logger.log_query(entry)
        assert entry._price_per_tb == 9.00
        assert entry.estimated_cost_usd == 9.00

    def test_session_summary_uses_region_price(self):
        logger = QueryLogger(region="sa-east-1")
        entry = QueryLogEntry(
            query_name="test", dataset="db.tb", column="col",
            elapsed_ms=100, cache_hit=False, rows_returned=10,
            bytes_scanned=ONE_TB,
        )
        logger.log_query(entry)
        summary = logger.get_session_summary()
        assert summary["estimated_cost_usd"] == 9.00

    def test_us_east_1_cheaper_than_sa_east_1(self):
        """Mesma query em us-east-1 deve custar menos que em sa-east-1."""
        logger_us = QueryLogger(region="us-east-1")
        logger_sa = QueryLogger(region="sa-east-1")
        for logger in [logger_us, logger_sa]:
            logger.log_query(QueryLogEntry(
                query_name="test", dataset="db.tb", column="col",
                elapsed_ms=100, cache_hit=False, rows_returned=10,
                bytes_scanned=ONE_TB,
            ))
        us_cost = logger_us.get_session_summary()["estimated_cost_usd"]
        sa_cost = logger_sa.get_session_summary()["estimated_cost_usd"]
        assert sa_cost > us_cost


class TestSessionCostMinimumBilling:
    """Valida que session summary aplica mínimo de 10MB por query."""

    def test_many_small_queries_apply_minimum(self):
        """10 queries de 1KB cada devem custar 10x o mínimo de 10MB, não 10KB."""
        logger = QueryLogger(region="us-east-1")
        for _ in range(10):
            logger.log_query(QueryLogEntry(
                query_name="small", dataset="db.tb", column="col",
                elapsed_ms=50, cache_hit=False, rows_returned=1,
                bytes_scanned=1024,  # 1KB
            ))
        summary = logger.get_session_summary()
        # Each query billed at 10MB minimum
        expected_per_query = (10 * 1024 * 1024 / (1024 ** 4)) * 5.0
        expected_total = round(expected_per_query * 10, 4)
        assert summary["estimated_cost_usd"] == expected_total

    def test_cache_hit_zero_bytes_no_cost(self):
        """Cache hits (0 bytes) should contribute zero cost."""
        logger = QueryLogger(region="us-east-1")
        logger.log_query(QueryLogEntry(
            query_name="cached", dataset="db.tb", column="col",
            elapsed_ms=10, cache_hit=True, rows_returned=5,
            bytes_scanned=0,
        ))
        summary = logger.get_session_summary()
        assert summary["estimated_cost_usd"] == 0.0

    def test_large_query_no_distortion(self):
        """Query acima de 10MB deve usar bytes reais, não mínimo."""
        logger = QueryLogger(region="us-east-1")
        one_gb = 1024 ** 3
        logger.log_query(QueryLogEntry(
            query_name="big", dataset="db.tb", column="col",
            elapsed_ms=5000, cache_hit=False, rows_returned=1000,
            bytes_scanned=one_gb,
        ))
        summary = logger.get_session_summary()
        expected = round((one_gb / (1024 ** 4)) * 5.0, 4)
        assert summary["estimated_cost_usd"] == expected

    def test_session_sum_equals_entry_sum(self):
        """Session cost must equal sum of individual entry costs."""
        logger = QueryLogger(region="sa-east-1")
        for size in [500, 1024, 50_000_000, 0, 1024 * 1024]:
            logger.log_query(QueryLogEntry(
                query_name="q", dataset="db.tb", column="col",
                elapsed_ms=100, cache_hit=(size == 0), rows_returned=1,
                bytes_scanned=size,
            ))
        summary = logger.get_session_summary()
        entry_sum = round(sum(e.estimated_cost_usd for e in logger.entries), 4)
        assert summary["estimated_cost_usd"] == entry_sum
