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


# ---------------------------------------------------------------------------
# effective_partition_filter
# ---------------------------------------------------------------------------

class TestEffectivePartitionFilter:
    def test_incremental_generates_filter(self, config_incremental):
        f = config_incremental.effective_partition_filter
        assert f is not None
        assert '"dt_ref"' in f
        assert "DATE_ADD" in f
        assert "-30" in f

    def test_full_snapshot_generates_filter(self, config_full_snapshot):
        f = config_full_snapshot.effective_partition_filter
        assert f is not None
        assert '"dt_carga"' in f
        assert "-30" in f

    def test_non_partitioned_returns_none(self, config_non_partitioned):
        assert config_non_partitioned.effective_partition_filter is None

    def test_with_date_expression_uses_expression(self):
        cfg = DatasetConfig(
            schema="db",
            table="tb",
            partition_column="dt_ref",
            date_expression="date_parse(dt_ref, '%Y.%m.%d')",
            lookback_value=60,
        )
        f = cfg.effective_partition_filter
        assert f is not None
        assert "date_parse" in f
        assert "-60" in f
        # Deve usar a expressão, não a coluna crua
        assert '"dt_ref" >=' not in f


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
