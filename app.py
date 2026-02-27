"""
GDQ Rule Proposer — Entry point Streamlit.

Dashboard com overview do projeto, metricas da sessao e navegacao guiada.
"""

import os

import streamlit as st

from config import load_config, AthenaMode, Environment
from infra.athena_client import AthenaClient

__version__ = "0.2.0"

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
        df = client.execute_df(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'gdq_test_db' ORDER BY table_name",
            query_name="list_tables",
        )
        return df["table_name"].tolist()


# ---------------------------------------------------------------------------
# Sidebar (environment-aware)
# ---------------------------------------------------------------------------

def render_sidebar():
    config = st.session_state.get("config")

    st.sidebar.title("GDQ Rule Proposer")
    st.sidebar.caption(f"v{__version__}")
    st.sidebar.divider()

    if not config:
        return

    # Ambiente fixo — definido no launch via run.py --env
    env_labels = {
        Environment.LOCAL: ":blue[Local]",
        Environment.DEV: ":orange[Dev]",
        Environment.PROD: ":green[Producao]",
    }
    st.sidebar.markdown(
        f"**Ambiente:** {env_labels.get(config.environment, config.environment.value)}"
    )

    mode_label = config.athena.mode.value.upper()
    st.sidebar.markdown(f"**Modo:** {mode_label}")

    if config.athena.mode == AthenaMode.REAL:
        st.sidebar.markdown(f"**Region:** {config.athena.region}")
        st.sidebar.markdown(f"**Workgroup:** {config.athena.workgroup}")
        # Em prod com IAM role, AWS_PROFILE nao e necessario
        if config.environment != Environment.PROD and not os.environ.get("AWS_PROFILE") and not config.athena.aws_profile:
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
# Main page — Dashboard
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="GDQ Rule Proposer",
        page_icon=":shield:",
        layout="wide",
    )

    # Init client
    try:
        client = get_client()
        connection_ok = True
        connection_error = None
    except Exception as e:
        connection_ok = False
        connection_error = str(e)
        client = None

    render_sidebar()

    config = st.session_state.get("config")

    # --- Header ---
    header_col, status_col = st.columns([4, 1])
    with header_col:
        st.title("GDQ Rule Proposer")
        st.caption(
            f"v{__version__} — Proposta automatica de regras AWS Glue Data Quality"
        )
    with status_col:
        if connection_ok:
            env_label = config.environment.value.upper() if config else "?"
            st.success(f"Conectado ({env_label})")
        else:
            st.error("Desconectado")

    if not connection_ok:
        st.error(
            f"Falha na conexao: {connection_error}. "
            "Verifique o ambiente selecionado e as credenciais AWS."
        )
        st.stop()

    # --- Metric cards ---
    tables = get_available_tables(client)
    n_tables = len(tables)
    n_cart = len(st.session_state.get("rule_cart", []))
    has_config = "dataset_config" in st.session_state

    # Cost from query logger
    cost_str = "$0.00"
    if hasattr(client, "logger"):
        summary = client.logger.get_session_summary()
        if summary["estimated_cost_usd"] > 0:
            cost_str = f"${summary['estimated_cost_usd']:.4f}"
        elif config and config.athena.mode == AthenaMode.MOCK:
            cost_str = "Local"

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Tabelas disponiveis", n_tables)
    with m2:
        st.metric("Regras no carrinho", n_cart)
    with m3:
        st.metric("Custo da sessao", cost_str)

    st.divider()

    # --- "Como funciona" — 4 steps ---
    st.subheader("Como funciona")

    s1, s2, s3, s4 = st.columns(4)

    with s1:
        st.markdown("### 1. Setup")
        st.markdown(
            "Configure a **tabela**, o **eixo temporal** e selecione as **colunas** "
            "para analise. O profiling classifica cada coluna automaticamente."
        )
        if st.button("Ir para Setup", type="primary", key="nav_setup"):
            st.switch_page("pages/01_setup.py")

    with s2:
        st.markdown("### 2. Explore")
        st.markdown(
            "Calibre regras **Mean**, **StdDev**, **Percentil**, **Frequencia** "
            "e **RowCount** com graficos interativos e backtest em tempo real."
        )
        if has_config:
            if st.button("Ir para Explore", key="nav_explore"):
                st.switch_page("pages/02_explore.py")
        else:
            st.caption("Configure o Setup primeiro.")

    with s3:
        st.markdown("### 3. Review")
        st.markdown(
            "Revise as regras no carrinho, valide a **sintaxe GDQ**, "
            "gere o **relatorio analitico** e **exporte** para arquivo."
        )
        if n_cart > 0:
            if st.button("Ir para Review", key="nav_review"):
                st.switch_page("pages/03_review.py")
        else:
            st.caption("Adicione regras no Explore primeiro.")

    with s4:
        st.markdown("### 4. Ajuda")
        st.markdown(
            "Documentacao completa: conceitos, parametros, "
            "sintaxe GDQ, perguntas frequentes e glossario."
        )
        if st.button("Ver Ajuda", key="nav_help"):
            st.switch_page("pages/04_help.py")

    st.divider()

    # --- Active config section OR quick start ---
    if has_config:
        cfg = st.session_state["dataset_config"]
        profiles = st.session_state.get("column_profiles", [])

        st.subheader("Configuracao ativa")

        from core.models.enums import SemanticType

        n_sel = len(cfg.selected_columns) if cfg.selected_columns else 0
        n_num = sum(
            1 for p in profiles
            if p.effective_type == SemanticType.NUMERIC
            and p.column_name in set(cfg.selected_columns or [])
        )
        n_cat = sum(
            1 for p in profiles
            if p.is_categorical
            and p.column_name in set(cfg.selected_columns or [])
        )

        info_c1, info_c2, info_c3, info_c4 = st.columns(4)
        info_c1.markdown(f"**Tabela:** `{cfg.schema}.{cfg.table}`")
        info_c2.markdown(f"**Colunas:** {n_sel} ({n_num} num, {n_cat} cat)")
        info_c3.markdown(f"**Lookback:** {cfg.lookback_value} periodos")
        info_c4.markdown(f"**Particao:** {cfg.partition_method.value}")

        if cfg.base_filter_sql:
            st.caption(f"Filtro: `{cfg.base_filter_sql}`")

        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("Continuar analise", type="primary", key="continue_explore"):
                st.switch_page("pages/02_explore.py")
        with btn_c2:
            if n_cart > 0:
                if st.button(f"Revisar {n_cart} regra(s)", key="continue_review"):
                    st.switch_page("pages/03_review.py")

    else:
        st.subheader("Inicio rapido")

        st.markdown(
            "Bem-vindo ao **GDQ Rule Proposer**. Esta ferramenta analisa o historico "
            "de dados de uma tabela e propoe regras de qualidade prontas para o "
            "AWS Glue Data Quality."
        )

        st.markdown(
            "- Conecta ao **Amazon Athena** para consultar dados agregados (sem trazer dados brutos)\n"
            "- Propoe regras dinamicas (**Mean**, **StdDev**, **RowCount**, **Percentil**) "
            "e estaticas (**AllowedValues**, **DistinctCount**, **Frequencia**)\n"
            "- Todas as regras passam por **backtest** no historico antes de serem sugeridas\n"
            "- A sintaxe GDQ gerada e validada e pode ser exportada diretamente"
        )

        if st.button("Comecar configuracao", type="primary", key="quick_start"):
            st.switch_page("pages/01_setup.py")

    # --- Tables preview (collapsible) ---
    if tables:
        with st.expander(f"Tabelas disponiveis ({n_tables})", expanded=False):
            for t in tables:
                st.caption(f"- `{t}`")


if __name__ == "__main__":
    main()
