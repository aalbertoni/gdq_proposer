"""Funcoes compartilhadas de limpeza de session_state.

Extraidas de pages/01_setup.py para evitar drift entre logica inline e testes.
Todas as funcoes operam sobre um dict (compativel com st.session_state).
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Prefixos e chaves por escopo
# ---------------------------------------------------------------------------

SETUP_PREFIXES = ("setup_", "prof_", "sel_", "type_", "pcol_")
SETUP_EXACT_KEYS = ("show_compare_ui", "show_clone_ui")

ANALYSIS_PREFIXES = (
    "proposal_mean_", "proposal_stddev_", "proposal_comp_",
    "proposal_pct_", "proposal_rc_", "proposal_pk_",
    "proposal_subpop_",
    "cat_proposals_",
    "series_profile_",
    "autotune_",
)
ANALYSIS_EXACT_KEYS = ("rule_cart", "col_health")


# ---------------------------------------------------------------------------
# Funcoes de limpeza
# ---------------------------------------------------------------------------

def reset_setup_state(state: dict[str, Any]) -> None:
    """Limpa todo o estado do Setup (botao 'Recomecar Setup').

    Remove chaves com prefixos setup_, prof_, sel_, type_, pcol_
    e chaves exatas show_compare_ui, show_clone_ui.
    Preserva infraestrutura (client, services) e estado analitico.
    """
    for k in list(state.keys()):
        if isinstance(k, str) and (
            any(k.startswith(p) for p in SETUP_PREFIXES)
            or k in SETUP_EXACT_KEYS
        ):
            del state[k]


def go_back_column_selection(state: dict[str, Any]) -> None:
    """Limpa estado para re-selecao de colunas (botao 'Voltar e re-selecionar').

    Remove setup_profiles e chaves sel_*/type_* para que os checkboxes
    reflitam novas escolhas. Preserva pcol_*, prof_* e infraestrutura.
    """
    state.pop("setup_profiles", None)
    for k in list(state.keys()):
        if isinstance(k, str) and (k.startswith("sel_") or k.startswith("type_")):
            del state[k]


def clear_analysis_state(state: dict[str, Any]) -> None:
    """Limpa estado analitico ao trocar configuracao.

    Remove carrinho, proposals, series profiles, auto-tune e col_health.
    Nao remove chaves de infraestrutura (client, services, setup_*).
    """
    for key in ANALYSIS_EXACT_KEYS:
        state.pop(key, None)
    keys_to_remove = [
        k for k in list(state.keys())
        if isinstance(k, str) and any(k.startswith(p) for p in ANALYSIS_PREFIXES)
    ]
    for key in keys_to_remove:
        del state[key]


def clear_stale_selections(state: dict[str, Any]) -> None:
    """Remove chaves sel_* obsoletas (apos carregar preset).

    Limpa checkboxes de selecao para que os defaults do preset entrem em vigor.
    """
    for k in list(state.keys()):
        if isinstance(k, str) and k.startswith("sel_"):
            del state[k]
