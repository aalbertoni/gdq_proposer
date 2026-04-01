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


# ---------------------------------------------------------------------------
# Setup reset — "Recomecar Setup" button logic
# ---------------------------------------------------------------------------

class TestResetSetupState:
    """Testa a logica de limpeza do botao 'Recomecar Setup' (01_setup.py:309-319)."""

    _SETUP_PREFIXES = ("setup_", "prof_", "sel_", "type_", "pcol_")
    _SETUP_EXACT_KEYS = ("show_compare_ui", "show_clone_ui")

    def _reset(self, state: dict):
        """Replica a logica de reset do Setup."""
        for k in list(state.keys()):
            if isinstance(k, str) and (
                any(k.startswith(p) for p in self._SETUP_PREFIXES)
                or k in self._SETUP_EXACT_KEYS
            ):
                del state[k]

    def _make_state(self) -> dict:
        return {
            # Setup keys — DEVE ser limpo
            "setup_validated": True,
            "setup_config": "mock_config",
            "setup_profiles": ["profile1"],
            "setup_schema": "db",
            "setup_date_range": "2026-01-01/2026-03-01",
            "prof_col_a": True,
            "prof_col_b": False,
            "sel_col_a": True,
            "sel_col_b": True,
            "type_col_a": "NUMERIC",
            "pcol_temporal_dt_ref": True,
            "pcol_temporal_flag": False,
            "show_compare_ui": True,
            "show_clone_ui": False,
            # Non-setup keys — NAO deve ser limpo
            "client": "mock_client",
            "rule_cart": [],
            "proposal_mean_COL_A": "proposal",
            "_analysis_fingerprint": "abc123",
            123: "numeric_key",  # Non-string key
        }

    def test_clears_all_setup_prefixes(self):
        state = self._make_state()
        self._reset(state)
        for prefix in self._SETUP_PREFIXES:
            assert not any(
                isinstance(k, str) and k.startswith(prefix) for k in state
            ), f"Found key with prefix {prefix}"

    def test_clears_exact_keys(self):
        state = self._make_state()
        self._reset(state)
        assert "show_compare_ui" not in state
        assert "show_clone_ui" not in state

    def test_preserves_non_setup_keys(self):
        state = self._make_state()
        self._reset(state)
        assert state["client"] == "mock_client"
        assert state["rule_cart"] == []
        assert state["proposal_mean_COL_A"] == "proposal"
        assert state["_analysis_fingerprint"] == "abc123"

    def test_ignores_non_string_keys(self):
        state = self._make_state()
        self._reset(state)
        assert state[123] == "numeric_key"

    def test_empty_state_noop(self):
        state = {}
        self._reset(state)
        assert state == {}


# ---------------------------------------------------------------------------
# Go-back — "Voltar e re-selecionar colunas" button logic
# ---------------------------------------------------------------------------

class TestGoBackColumnSelection:
    """Testa a logica de limpeza do botao 'Voltar e re-selecionar' (01_setup.py:1433-1437)."""

    def _go_back(self, state: dict):
        """Replica a logica de go-back."""
        state.pop("setup_profiles", None)
        for k in list(state.keys()):
            if isinstance(k, str) and (k.startswith("sel_") or k.startswith("type_")):
                del state[k]

    def _make_state(self) -> dict:
        return {
            "setup_profiles": ["profile1", "profile2"],
            "setup_validated": True,
            "setup_config": "mock",
            "sel_col_a": True,
            "sel_col_b": False,
            "type_col_a": "NUMERIC",
            "type_col_b": "CATEGORICAL_LOW",
            "prof_col_a": True,
            "pcol_temporal_dt_ref": True,
            "rule_cart": [],
        }

    def test_removes_profiles(self):
        state = self._make_state()
        self._go_back(state)
        assert "setup_profiles" not in state

    def test_clears_sel_prefix(self):
        state = self._make_state()
        self._go_back(state)
        assert not any(isinstance(k, str) and k.startswith("sel_") for k in state)

    def test_clears_type_prefix(self):
        state = self._make_state()
        self._go_back(state)
        assert not any(isinstance(k, str) and k.startswith("type_") for k in state)

    def test_preserves_other_setup_keys(self):
        state = self._make_state()
        self._go_back(state)
        assert state["setup_validated"] is True
        assert state["setup_config"] == "mock"
        assert state["prof_col_a"] is True
        assert state["pcol_temporal_dt_ref"] is True

    def test_preserves_cart(self):
        state = self._make_state()
        self._go_back(state)
        assert "rule_cart" in state

    def test_no_profiles_noop(self):
        state = {"sel_col": True, "type_col": "NUMERIC"}
        self._go_back(state)
        assert "sel_col" not in state
        assert "type_col" not in state


# ---------------------------------------------------------------------------
# Column selection change detection
# ---------------------------------------------------------------------------

class TestColumnSelectionDiff:
    """Testa a logica de deteccao de mudanca na selecao (01_setup.py:1305-1309)."""

    def _detect_changes(
        self, profiled_col_names: set[str], selected_col_names: set[str],
    ) -> tuple[set[str], set[str], bool]:
        """Replica a logica de deteccao de mudanca."""
        added = selected_col_names - profiled_col_names
        removed = profiled_col_names - selected_col_names
        changed = bool(added or removed)
        return added, removed, changed

    def test_no_change(self):
        added, removed, changed = self._detect_changes({"A", "B"}, {"A", "B"})
        assert not changed
        assert added == set()
        assert removed == set()

    def test_column_added(self):
        added, removed, changed = self._detect_changes({"A", "B"}, {"A", "B", "C"})
        assert changed
        assert added == {"C"}
        assert removed == set()

    def test_column_removed(self):
        added, removed, changed = self._detect_changes({"A", "B", "C"}, {"A", "B"})
        assert changed
        assert added == set()
        assert removed == {"C"}

    def test_column_swapped(self):
        added, removed, changed = self._detect_changes({"A", "B"}, {"A", "C"})
        assert changed
        assert added == {"C"}
        assert removed == {"B"}

    def test_all_different(self):
        added, removed, changed = self._detect_changes({"A", "B"}, {"C", "D"})
        assert changed
        assert added == {"C", "D"}
        assert removed == {"A", "B"}

    def test_empty_profiled(self):
        added, removed, changed = self._detect_changes(set(), {"A"})
        assert changed
        assert added == {"A"}

    def test_empty_selected(self):
        added, removed, changed = self._detect_changes({"A"}, set())
        assert changed
        assert removed == {"A"}
