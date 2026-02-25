"""
GDQ Rule Proposer — Entry point Streamlit.

Pagina inicial com status de conexao, tabelas disponiveis e preview de colunas.
"""

import os

import streamlit as st

from config import load_config, AthenaMode, Environment
from infra.athena_client import AthenaClient

__version__ = "0.1.0"

_SESSION_KEYS_TO_CLEAR = [
    "client", "config",
    "analysis_service", "proposal_service",
    "dataset_service", "profiling_service",
    "dataset_config", "column_profiles",
    "setup_validated", "setup_schema", "setup_table",
    "setup_columns", "setup_config", "setup_profiles", "setup_date_range",
]


def get_client() -> AthenaClient:
    """Get or create a cached AthenaClient in session_state."""
    if "client" not in st.session_state:
        config = load_config()
        st.session_state["config"] = config
        st.session_state["client"] = AthenaClient(config)
    return st.session_state["client"]


def get_available_tables(client: AthenaClient) -> list[str]:
    """List tables available in the current backend."""
    if client.config.athena.mode == AthenaMode.MOCK:
        if client._backend:
            return sorted(client._backend._tables.values())
        return []
    else:
        # Real Athena: query information_schema
        df = client.execute_df(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'gdq_test_db' ORDER BY table_name",
            query_name="list_tables",
        )
        return df["table_name"].tolist()


def get_table_columns(client: AthenaClient, table: str) -> list[dict]:
    """Get columns for a table."""
    if client.config.athena.mode == AthenaMode.MOCK:
        if client._backend:
            return client._backend.get_columns(table)
        return []
    else:
        return client.get_columns("gdq_test_db", table)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar():
    config = st.session_state.get("config")

    st.sidebar.title("GDQ Rule Proposer")
    st.sidebar.caption(f"v{__version__}")
    st.sidebar.divider()

    # Seletor de ambiente
    env_options = [e.value for e in Environment]
    current_env = config.environment.value if config else "local"

    selected_env = st.sidebar.selectbox(
        "Ambiente:",
        env_options,
        index=env_options.index(current_env),
        format_func=lambda x: {
            "local": "Local (Mock/DuckDB)",
            "dev": "Dev (Athena real)",
            "prod": "Prod (Athena + IAM)",
        }.get(x, x),
        key="env_selector",
        help="Ambiente de execucao. Local usa DuckDB com dados sinteticos. Dev e Prod conectam ao Athena real da AWS.",
    )

    if selected_env != current_env:
        os.environ["GDQ_ENV"] = selected_env
        for key in _SESSION_KEYS_TO_CLEAR:
            st.session_state.pop(key, None)
        # Limpar caches de proposals tambem
        keys_to_remove = [k for k in st.session_state if k.startswith("proposal_")]
        for k in keys_to_remove:
            del st.session_state[k]
        st.rerun()

    if not config:
        return

    mode_label = config.athena.mode.value.upper()
    st.sidebar.markdown(f"**Modo:** {mode_label}")

    if config.athena.mode == AthenaMode.REAL:
        st.sidebar.markdown(f"**Region:** {config.athena.region}")
        st.sidebar.markdown(f"**Workgroup:** {config.athena.workgroup}")
        if not os.environ.get("AWS_PROFILE") and not config.athena.aws_profile:
            st.sidebar.warning("AWS_PROFILE nao configurado. Defina antes de usar Athena.")

    # Active config indicator
    if "dataset_config" in st.session_state:
        cfg = st.session_state["dataset_config"]
        n_sel = len(cfg.selected_columns) if cfg.selected_columns else 0
        st.sidebar.divider()
        st.sidebar.success(f"Config ativa: `{cfg.schema}.{cfg.table}` ({n_sel} colunas)")
        n_cart = len(st.session_state.get("rule_cart", []))
        if n_cart:
            st.sidebar.caption(f"Carrinho: {n_cart} regra(s)")


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="GDQ Rule Proposer",
        page_icon=":shield:",
        layout="wide",
    )

    st.title("GDQ Rule Proposer")
    st.caption(f"v{__version__} — Proposta automatica de regras AWS Glue Data Quality")
    st.info(
        "Esta ferramenta analisa o historico de dados de uma tabela via Athena "
        "e propoe regras de qualidade para AWS Glue Data Quality (GDQ). "
        "Comece pela pagina **Setup** para configurar sua tabela."
    )

    # Init client (triggers config load)
    try:
        client = get_client()
        connection_ok = True
        connection_error = None
    except Exception as e:
        connection_ok = False
        connection_error = str(e)
        client = None

    render_sidebar()

    # --- Connection status ---
    st.subheader("Status da Conexao")

    if connection_ok:
        config = st.session_state["config"]
        mode = config.athena.mode.value
        env = config.environment.value
        st.success(f"Conectado — ambiente **{env}**, modo **{mode}**")
    else:
        st.error(
            f"Falha na conexao: {connection_error}. "
            "Verifique o ambiente selecionado na barra lateral e as credenciais AWS."
        )
        st.stop()

    # --- Available tables ---
    st.subheader("Tabelas Disponiveis")
    st.caption(
        "Tabelas detectadas no backend ativo. "
        "Para configurar regras, va para a pagina **Setup**."
    )

    tables = get_available_tables(client)

    if not tables:
        st.warning(
            "Nenhuma tabela encontrada. Verifique se o ambiente esta correto "
            "e se os dados mock estao disponiveis em `mock_data/`."
        )
        st.stop()

    st.info(f"{len(tables)} tabela(s) carregada(s)")

    selected = st.selectbox(
        "Selecione uma tabela:",
        tables,
        help="Escolha uma tabela para visualizar suas colunas. Para configurar regras, use a pagina Setup.",
    )

    if selected:
        st.subheader(f"Colunas de `{selected}`")

        columns = get_table_columns(client, selected)

        if columns:
            col_header = st.columns([2, 2])
            col_header[0].markdown("**Coluna**")
            col_header[1].markdown("**Tipo**")

            for col_info in columns:
                row = st.columns([2, 2])
                row[0].code(col_info["name"])
                row[1].write(col_info["type"])
        else:
            st.warning("Nao foi possivel obter colunas.")

    # --- Navigation shortcuts ---
    st.divider()
    nav1, nav2, nav3 = st.columns(3)
    with nav1:
        if st.button("Ir para Setup", type="primary"):
            st.switch_page("pages/01_setup.py")
    with nav2:
        if "dataset_config" in st.session_state:
            if st.button("Ir para Explore"):
                st.switch_page("pages/02_explore.py")
    with nav3:
        if st.session_state.get("rule_cart"):
            if st.button("Ir para Review"):
                st.switch_page("pages/03_review.py")


if __name__ == "__main__":
    main()
