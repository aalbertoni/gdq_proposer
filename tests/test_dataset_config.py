"""Testes para core/models/dataset_config.py."""

import pytest
from core.models.dataset_config import DatasetConfig
from core.models.enums import GrainType, LookbackMode, PartitionMethod


# ---------------------------------------------------------------------------
# Fixtures: 3 cenários da spec (seção 3.1)
# ---------------------------------------------------------------------------

@pytest.fixture
def config_incremental():
    """Cenário 1: Tabela incremental (partição = data)."""
    return DatasetConfig(
        schema="gdq_test_db",
        table="tb_operacoes_incremental",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        grain_type=GrainType.DAILY,
        lookback_value=30,
        selected_columns=["VLR_SALD_AVNC_OPCR", "VLR_PARC_OPCR", "COD_SITU_OPCR"],
        unique_key_columns=["NUM_CTRT_OPCR"],
    )


@pytest.fixture
def config_full_snapshot():
    """Cenário 2: Full snapshot (partição != coluna de data para análise)."""
    return DatasetConfig(
        schema="gdq_test_db",
        table="tb_cadastro_full",
        partition_method=PartitionMethod.FULL_SNAPSHOT,
        partition_column="dt_carga",
        date_column="DT_ABERTURA",
        temporal_axis_column="dt_carga",
        grain_type=GrainType.DAILY,
        lookback_value=30,
        base_filter_sql="IND_ATIVO = 1",
        selected_columns=["VLR_LIMITE", "VLR_SALDO", "COD_SEGMENTO", "QTD_PRODUTOS"],
        unique_key_columns=["ID_CLIENTE"],
    )


@pytest.fixture
def config_non_partitioned():
    """Cenário 3: Tabela não particionada."""
    return DatasetConfig(
        schema="analytics_db",
        table="tb_eventos",
        partition_method=PartitionMethod.NON_PARTITIONED,
        partition_column=None,
        date_column="dt_evento",
        grain_type=GrainType.DAILY,
        date_expression="date_trunc('day', dt_evento)",
        lookback_value=30,
    )


# ---------------------------------------------------------------------------
# effective_temporal_axis
# ---------------------------------------------------------------------------

class TestEffectiveTemporalAxis:
    def test_incremental_uses_partition_column(self, config_incremental):
        # partition_column == date_column == "dt_ref"
        assert config_incremental.effective_temporal_axis == "dt_ref"

    def test_full_snapshot_uses_explicit_temporal_axis(self, config_full_snapshot):
        # temporal_axis_column = "dt_carga" (explícito)
        assert config_full_snapshot.effective_temporal_axis == "dt_carga"

    def test_full_snapshot_without_explicit_falls_back_to_partition(self):
        cfg = DatasetConfig(
            schema="db",
            table="tb",
            partition_method=PartitionMethod.FULL_SNAPSHOT,
            partition_column="dt_carga",
            date_column="DT_ABERTURA",
            # temporal_axis_column não definido
        )
        assert cfg.effective_temporal_axis == "dt_carga"

    def test_non_partitioned_uses_date_column(self, config_non_partitioned):
        assert config_non_partitioned.effective_temporal_axis == "dt_evento"

    def test_incremental_without_partition_falls_back_to_date_column(self):
        cfg = DatasetConfig(
            schema="db",
            table="tb",
            partition_method=PartitionMethod.INCREMENTAL,
            partition_column=None,
            date_column="dt_ref",
        )
        assert cfg.effective_temporal_axis == "dt_ref"


# effective_partition_filter foi removido — pruning agora em infra/partition_pruning.py
# Testes de pruning em tests/test_partition_pruning.py


# ---------------------------------------------------------------------------
# Defaults e campos básicos
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_default_values(self):
        cfg = DatasetConfig(schema="db", table="tb")
        assert cfg.partition_method == PartitionMethod.INCREMENTAL
        assert cfg.grain_type == GrainType.DAILY
        assert cfg.lookback_mode == LookbackMode.LAST_N_PERIODS
        assert cfg.lookback_value == 30
        assert cfg.base_filter_sql is None
        assert cfg.selected_columns == []
        assert cfg.unique_key_columns == []
        assert cfg.date_expression is None
        assert cfg.temporal_axis_column is None

    def test_incremental_fields(self, config_incremental):
        assert config_incremental.schema == "gdq_test_db"
        assert config_incremental.table == "tb_operacoes_incremental"
        assert config_incremental.partition_column == "dt_ref"
        assert config_incremental.date_column == "dt_ref"
        assert len(config_incremental.selected_columns) == 3

    def test_full_snapshot_fields(self, config_full_snapshot):
        assert config_full_snapshot.partition_column == "dt_carga"
        assert config_full_snapshot.date_column == "DT_ABERTURA"
        assert config_full_snapshot.base_filter_sql == "IND_ATIVO = 1"
        assert config_full_snapshot.unique_key_columns == ["ID_CLIENTE"]

    def test_non_partitioned_fields(self, config_non_partitioned):
        assert config_non_partitioned.partition_column is None
        assert config_non_partitioned.date_column == "dt_evento"
        assert config_non_partitioned.date_expression is not None


# ---------------------------------------------------------------------------
# Multi-partition migration and sync
# ---------------------------------------------------------------------------

class TestMultiPartitionMigration:
    def test_single_to_list_migration(self):
        """Legacy partition_column auto-migrates to partition_columns."""
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_column="dt_ref",
            partition_format="%Y-%m-%d",
            partition_is_integer=False,
        )
        assert cfg.partition_columns == ["dt_ref"]
        assert cfg.partition_formats == {"dt_ref": "%Y-%m-%d"}
        assert cfg.partition_is_integer_map == {"dt_ref": False}

    def test_list_already_populated_no_overwrite(self):
        """If partition_columns already set, migration does not overwrite."""
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_column="old_col",
            partition_columns=["ano", "mes"],
            partition_formats={"ano": "%Y", "mes": "%m"},
            partition_is_integer_map={"ano": True, "mes": True},
        )
        assert cfg.partition_columns == ["ano", "mes"]
        # Legacy fields synced from first in list
        assert cfg.partition_column == "ano"
        assert cfg.partition_format == "%Y"
        assert cfg.partition_is_integer is True

    def test_list_syncs_to_legacy(self):
        """Canonical list syncs first element to legacy fields."""
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_columns=["ano", "mes", "dia"],
            partition_formats={"ano": "%Y", "mes": "%m", "dia": "%d"},
            partition_is_integer_map={"ano": True, "mes": True, "dia": True},
        )
        assert cfg.partition_column == "ano"
        assert cfg.partition_format == "%Y"
        assert cfg.partition_is_integer is True

    def test_non_partitioned_legacy_none(self):
        """NON_PARTITIONED: all partition fields are None/empty."""
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_method=PartitionMethod.NON_PARTITIONED,
        )
        assert cfg.partition_columns == []
        assert cfg.partition_column is None
        assert cfg.partition_format is None
        assert cfg.partition_is_integer is False

    def test_is_multi_partition(self):
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_columns=["ano", "mes"],
        )
        assert cfg.is_multi_partition is True

    def test_is_multi_partition_single(self):
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_columns=["dt_ref"],
        )
        assert cfg.is_multi_partition is False

    def test_is_multi_partition_empty(self):
        cfg = DatasetConfig(schema="db", table="tb")
        assert cfg.is_multi_partition is False


# ---------------------------------------------------------------------------
# Fingerprint sensitivity for multi-partition fields
# ---------------------------------------------------------------------------

class TestFingerprintMultiPartition:
    def test_partition_columns_change_fingerprint(self):
        base = DatasetConfig(
            schema="db", table="tb",
            partition_columns=["ano", "mes"],
            partition_formats={"ano": "%Y", "mes": "%m"},
        )
        changed = DatasetConfig(
            schema="db", table="tb",
            partition_columns=["ano", "mes", "dia"],
            partition_formats={"ano": "%Y", "mes": "%m", "dia": "%d"},
        )
        assert base.analysis_fingerprint() != changed.analysis_fingerprint()

    def test_partition_formats_change_fingerprint(self):
        base = DatasetConfig(
            schema="db", table="tb",
            partition_columns=["dt_ref"],
            partition_formats={"dt_ref": "%Y-%m-%d"},
        )
        changed = DatasetConfig(
            schema="db", table="tb",
            partition_columns=["dt_ref"],
            partition_formats={"dt_ref": "%Y%m%d"},
        )
        assert base.analysis_fingerprint() != changed.analysis_fingerprint()

    def test_partition_is_integer_map_change_fingerprint(self):
        base = DatasetConfig(
            schema="db", table="tb",
            partition_columns=["dt_ref"],
            partition_formats={"dt_ref": "%Y%m%d"},
            partition_is_integer_map={"dt_ref": False},
        )
        changed = DatasetConfig(
            schema="db", table="tb",
            partition_columns=["dt_ref"],
            partition_formats={"dt_ref": "%Y%m%d"},
            partition_is_integer_map={"dt_ref": True},
        )
        assert base.analysis_fingerprint() != changed.analysis_fingerprint()

    def test_single_vs_multi_same_column_same_fingerprint(self):
        """Single partition_column migrated should match direct partition_columns."""
        single = DatasetConfig(
            schema="db", table="tb",
            partition_column="dt_ref",
            partition_format="%Y-%m-%d",
        )
        multi = DatasetConfig(
            schema="db", table="tb",
            partition_columns=["dt_ref"],
            partition_formats={"dt_ref": "%Y-%m-%d"},
            partition_is_integer_map={"dt_ref": False},
        )
        assert single.analysis_fingerprint() == multi.analysis_fingerprint()


# ---------------------------------------------------------------------------
# partition_is_temporal
# ---------------------------------------------------------------------------

class TestPartitionIsTemporal:
    def test_true_with_explicit_format(self):
        """partition_format explícito → temporal."""
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_column="dt_ref",
            partition_format="%Y-%m-%d",
            date_column="dt_ref",
        )
        assert cfg.partition_is_temporal is True

    def test_true_partition_equals_date_no_format(self):
        """partition == date_column, format None (native date) → temporal."""
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_column="dt_ref",
            partition_format=None,
            date_column="dt_ref",
        )
        assert cfg.partition_is_temporal is True

    def test_false_non_temporal_flag(self):
        """partition="flag_ativo", date="dt_ref", no format → not temporal."""
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_column="flag_ativo",
            date_column="dt_ref",
        )
        assert cfg.partition_is_temporal is False

    def test_false_non_partitioned(self):
        """Sem partition_column → not temporal."""
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_method=PartitionMethod.NON_PARTITIONED,
            date_column="dt_ref",
        )
        assert cfg.partition_is_temporal is False

    def test_full_snapshot_with_format(self):
        """FULL_SNAPSHOT com partition_format explícito → temporal."""
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_method=PartitionMethod.FULL_SNAPSHOT,
            partition_column="dt_carga",
            partition_format="%Y-%m-%d",
            date_column="DT_ABERTURA",
        )
        assert cfg.partition_is_temporal is True

    def test_full_snapshot_without_format_different_cols(self):
        """FULL_SNAPSHOT sem formato, partition != date → not temporal."""
        cfg = DatasetConfig(
            schema="db", table="tb",
            partition_method=PartitionMethod.FULL_SNAPSHOT,
            partition_column="dt_carga",
            date_column="DT_ABERTURA",
        )
        assert cfg.partition_is_temporal is False
