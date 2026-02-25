"""
GDQ Rule Proposer — Entry point Streamlit.

Pagina inicial com status de conexao, tabelas disponiveis e preview de colunas.
"""

import streamlit as st

from config import load_config, AthenaMode
from infra.athena_client import AthenaClient

__version__ = "0.1.0"


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
    if not config:
        return

    st.sidebar.title("GDQ Rule Proposer")
    st.sidebar.caption(f"v{__version__}")
    st.sidebar.divider()

    env_label = config.environment.value.upper()
    mode_label = config.athena.mode.value.upper()
    st.sidebar.markdown(f"**Ambiente:** {env_label}")
    st.sidebar.markdown(f"**Modo:** {mode_label}")

    if config.athena.mode == AthenaMode.REAL:
        st.sidebar.markdown(f"**Region:** {config.athena.region}")
        st.sidebar.markdown(f"**Workgroup:** {config.athena.workgroup}")


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
        st.error(f"Falha na conexao: {connection_error}")
        st.stop()

    # --- Available tables ---
    st.subheader("Tabelas Disponiveis")

    tables = get_available_tables(client)

    if not tables:
        st.warning("Nenhuma tabela encontrada.")
        st.stop()

    st.info(f"{len(tables)} tabela(s) carregada(s)")

    selected = st.selectbox("Selecione uma tabela:", tables)

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


if __name__ == "__main__":
    main()
