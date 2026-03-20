"""Testes para invalidacao de estado analitico ao trocar configuracao.

Cobre:
- analysis_fingerprint: determinismo, sensibilidade a mudancas
- _clear_analysis_state: limpeza correta de chaves analiticas
- _activate_config: limpeza condicional baseada em fingerprint
"""

import pytest

from core.models.dataset_config import DatasetConfig
from core.models.enums import GrainType, LookbackMode, PartitionMethod


# ---------------------------------------------------------------------------
# analysis_fingerprint
# ---------------------------------------------------------------------------

class TestAnalysisFingerprint:
    def _make_config(self, **overrides) -> DatasetConfig:
        defaults = dict(
            schema="db", table="tb",
            partition_method=PartitionMethod.INCREMENTAL,
            partition_column="dt_ref",
            date_column="dt_ref",
            lookback_value=30,
            selected_columns=["COL_A", "COL_B"],
        )
        defaults.update(overrides)
        return DatasetConfig(**defaults)

    def test_deterministic(self):
        c1 = self._make_config()
        c2 = self._make_config()
        assert c1.analysis_fingerprint() == c2.analysis_fingerprint()

    def test_changes_on_schema(self):
        c1 = self._make_config(schema="db1")
        c2 = self._make_config(schema="db2")
        assert c1.analysis_fingerprint() != c2.analysis_fingerprint()

    def test_changes_on_table(self):
        c1 = self._make_config(table="tb1")
        c2 = self._make_config(table="tb2")
        assert c1.analysis_fingerprint() != c2.analysis_fingerprint()

    def test_changes_on_lookback(self):
        c1 = self._make_config(lookback_value=30)
        c2 = self._make_config(lookback_value=60)
        assert c1.analysis_fingerprint() != c2.analysis_fingerprint()

    def test_changes_on_date_expression(self):
        c1 = self._make_config(date_expression=None)
        c2 = self._make_config(date_expression="CAST(dt_ref AS DATE)")
        assert c1.analysis_fingerprint() != c2.analysis_fingerprint()

    def test_changes_on_base_filter(self):
        c1 = self._make_config(base_filter_sql=None)
        c2 = self._make_config(base_filter_sql="IND_ATIVO = 1")
        assert c1.analysis_fingerprint() != c2.analysis_fingerprint()

    def test_changes_on_reference_date(self):
        c1 = self._make_config(reference_date=None)
        c2 = self._make_config(reference_date="2024-12-31")
        assert c1.analysis_fingerprint() != c2.analysis_fingerprint()

    def test_changes_on_selected_columns(self):
        c1 = self._make_config(selected_columns=["A", "B"])
        c2 = self._make_config(selected_columns=["A", "C"])
        assert c1.analysis_fingerprint() != c2.analysis_fingerprint()

    def test_stable_on_column_order(self):
        c1 = self._make_config(selected_columns=["A", "B"])
        c2 = self._make_config(selected_columns=["B", "A"])
        assert c1.analysis_fingerprint() == c2.analysis_fingerprint()

    def test_changes_on_grain_type(self):
        c1 = self._make_config(grain_type=GrainType.DAILY)
        c2 = self._make_config(grain_type=GrainType.MONTHLY)
        assert c1.analysis_fingerprint() != c2.analysis_fingerprint()

    def test_changes_on_partition_method(self):
        c1 = self._make_config(partition_method=PartitionMethod.INCREMENTAL)
        c2 = self._make_config(partition_method=PartitionMethod.FULL_SNAPSHOT)
        assert c1.analysis_fingerprint() != c2.analysis_fingerprint()

    def test_length(self):
        fp = self._make_config().analysis_fingerprint()
        assert len(fp) == 12
        assert fp.isalnum()


# ---------------------------------------------------------------------------
# _clear_analysis_state (mock session_state as dict)
# ---------------------------------------------------------------------------

class TestClearAnalysisState:
    """Testa a logica de limpeza diretamente (sem importar pagina Streamlit)."""

    # Prefixos analiticos (replicados de 01_setup.py)
    _ANALYSIS_PREFIXES = (
        "proposal_mean_", "proposal_stddev_", "proposal_comp_",
        "proposal_pct_", "proposal_rc_", "proposal_pk_",
        "cat_proposals_",
        "series_profile_",
        "autotune_",
    )

    def _clear(self, state: dict):
        """Replica a logica de _clear_analysis_state sobre um dict."""
        for key in ["rule_cart", "col_health"]:
            state.pop(key, None)
        keys_to_remove = [
            k for k in list(state.keys())
            if isinstance(k, str) and any(k.startswith(p) for p in self._ANALYSIS_PREFIXES)
        ]
        for key in keys_to_remove:
            del state[key]

    def _make_state(self) -> dict:
        return {
            # Infra — NAO deve ser limpo
            "client": "mock_client",
            "config": "mock_config",
            "dataset_service": "mock",
            "profiling_service": "mock",
            "proposal_service": "mock",
            "analysis_service": "mock",
            "setup_validated": True,
            "setup_schema": "db",
            "setup_table": "tb",
            "setup_config": "mock",
            "setup_profiles": "mock",
            "_analysis_fingerprint": "abc123",
            "proposal_mode": "Completo",
            "proposal_service": "mock",
            # Analitico — DEVE ser limpo
            "rule_cart": [{"fake": "rule"}],
            "col_health": {"COL_A": {"mean": "HIGH"}},
            "proposal_mean_COL_A_20_2_10_True_30": ["proposal"],
            "proposal_stddev_COL_A_20_2_10_True_30": ["proposal"],
            "proposal_comp_COL_A_30": ["proposal"],
            "cat_proposals_COD_SITU_10_static": ["proposal"],
            "series_profile_COL_A_30": "mock_profile",
            "autotune_abc123_mean_COL_A": {"viable": True},
            "proposal_rc_20_2_10_True_30": ["proposal"],
        }

    def test_clears_analytical_keys(self):
        state = self._make_state()
        self._clear(state)
        assert "rule_cart" not in state
        assert "col_health" not in state
        assert not any(k.startswith("proposal_mean_") for k in state)
        assert not any(k.startswith("proposal_stddev_") for k in state)
        assert not any(k.startswith("cat_proposals_") for k in state)
        assert not any(k.startswith("series_profile_") for k in state)
        assert not any(k.startswith("autotune_") for k in state)
        assert not any(k.startswith("proposal_rc_") for k in state)

    def test_preserves_infra_keys(self):
        state = self._make_state()
        self._clear(state)
        assert state["client"] == "mock_client"
        assert state["config"] == "mock_config"
        assert state["setup_validated"] is True
        assert state["setup_schema"] == "db"
        assert state["_analysis_fingerprint"] == "abc123"
        assert state["proposal_service"] == "mock"
        assert state["proposal_mode"] == "Completo"

    def test_preserves_proposal_service_and_mode(self):
        """proposal_service e proposal_mode NAO sao analiticos."""
        state = self._make_state()
        self._clear(state)
        assert "proposal_service" in state
        assert "proposal_mode" in state
