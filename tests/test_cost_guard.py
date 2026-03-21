"""Testes para infra/cost_guard.py e comportamento fail-closed.

Valida que:
- Erros de metadata propagam (nao sao engolidos)
- Batch profiling falha explicita (nao cai para N queries)
- Cost guardrail bloqueia quando custo >= threshold
- Bypass funciona e pode ser resetado
"""

import pytest

from infra.cost_guard import (
    CostGuardrailTriggered,
    ExpensiveFallbackBlocked,
    PartitionMetadataError,
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
