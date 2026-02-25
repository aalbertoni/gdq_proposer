"""
Pagina 01 — Configuracao da Tabela.

Permite selecionar schema/tabela, validar existencia e ver colunas.
Placeholder para configuracao completa no Sprint A1.
"""

import streamlit as st

from config import load_config, AthenaMode
from infra.athena_client import AthenaClient


def get_client() -> AthenaClient:
    """Get or create a cached AthenaClient in session_state."""
    if "client" not in st.session_state:
        config = load_config()
        st.session_state["config"] = config
        st.session_state["client"] = AthenaClient(config)
    return st.session_state["client"]


st.set_page_config(page_title="Setup - GDQ Rule Proposer", page_icon=":gear:")

st.title("Configuracao da Tabela")
st.caption("Defina a tabela alvo e valide a conexao antes de prosseguir.")

try:
    client = get_client()
except Exception as e:
    st.error(f"Falha na conexao: {e}")
    st.stop()

config = st.session_state["config"]
is_mock = config.athena.mode == AthenaMode.MOCK

# --- Inputs ---

st.subheader("1. Selecionar Tabela")

if is_mock:
    schema = st.text_input("Schema (ignorado no modo mock):", value="mock_db", disabled=True)
    st.caption("No modo mock, o schema e ignorado — tabelas sao acessadas diretamente.")
else:
    schema = st.text_input("Schema (Glue database):", value="gdq_test_db")

table = st.text_input("Tabela:", placeholder="ex: tb_operacoes_credito")

# --- Validate ---

st.subheader("2. Validar")

if st.button("Validar Tabela", disabled=not table):
    with st.spinner("Verificando..."):
        exists = client.table_exists(schema, table)

    if exists:
        st.success(f"Tabela `{schema}.{table}` encontrada!")

        # Show columns
        st.subheader("Colunas")

        if is_mock:
            columns = client._backend.get_columns(table) if client._backend else []
        else:
            columns = client.get_columns(schema, table)

        if columns:
            col_header = st.columns([2, 2])
            col_header[0].markdown("**Coluna**")
            col_header[1].markdown("**Tipo**")

            for col_info in columns:
                row = st.columns([2, 2])
                row[0].code(col_info["name"])
                row[1].write(col_info["type"])

            st.session_state["validated_table"] = {
                "schema": schema,
                "table": table,
                "columns": columns,
            }
        else:
            st.warning("Tabela existe mas nao retornou colunas.")
    else:
        st.error(f"Tabela `{schema}.{table}` nao encontrada.")

# --- Placeholder ---

st.divider()
st.subheader("3. Configuracao Avancada")
st.info(
    "Configuracao de coluna de data, filtro base, partition method e lookback "
    "serao adicionados no Sprint A1."
)
