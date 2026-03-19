"""
GDQ Rule Proposer — Entry point Streamlit.

Dashboard com overview do projeto, metricas da sessao e navegacao guiada.
"""

import streamlit as st

from config import load_config
from infra.athena_client import AthenaClient

__version__ = "0.2.0"

def get_client() -> AthenaClient:
    """Get or create a cached AthenaClient in session_state."""
    if "client" not in st.session_state:
        config = load_config()
        st.session_state["config"] = config
        st.session_state["client"] = AthenaClient(config)
    return st.session_state["client"]



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
            st.success("Conectado")
        else:
            st.error("Desconectado")

    if not connection_ok:
        st.error(
            f"Falha na conexao: {connection_error}. "
            "Verifique o ambiente selecionado e as credenciais AWS."
        )
        st.stop()

    # --- Metric cards ---
    n_cart = len(st.session_state.get("rule_cart", []))
    has_config = "dataset_config" in st.session_state

    # Cost from query logger
    summary = client.logger.get_session_summary()
    if summary["estimated_cost_usd"] > 0:
        cost_str = f"${summary['estimated_cost_usd']:.4f}"
        cost_help = (
            f"{summary['total_queries']} queries, "
            f"{summary['cache_hits']} cache hits, "
            f"${summary['estimated_cost_usd']:.4f} estimado"
        )
    elif summary["total_queries"] > 0:
        cost_str = "$0.0000"
        cost_help = (
            f"{summary['total_queries']} queries executadas "
            f"({summary['cache_hits']} cache hits Athena, 0 bytes escaneados)"
        )
    else:
        cost_str = "$0.00"
        cost_help = "Nenhuma query executada nesta sessao"

    m1, m2 = st.columns(2)
    with m1:
        st.metric("Regras no carrinho", n_cart)
    with m2:
        st.metric("Custo da sessao", cost_str, help=cost_help)

    st.divider()

    # --- "Como funciona" — 4 steps ---
    st.subheader("Como funciona")

    s1, s2, s3, s4, s5 = st.columns(5)

    with s1:
        st.markdown("### 1. Setup")
        st.markdown(
            "Configure a **tabela**, o **eixo temporal** e selecione as **colunas** "
            "para analise."
        )
        if st.button("Ir para Setup", type="primary", key="nav_setup"):
            st.switch_page("pages/01_setup.py")

    with s2:
        st.markdown("### 2. Explore")
        st.markdown(
            "Calibre regras com graficos interativos e **backtest** em tempo real."
        )
        if has_config:
            if st.button("Ir para Explore", key="nav_explore"):
                st.switch_page("pages/02_explore.py")
        else:
            st.caption("Configure o Setup primeiro.")

    with s3:
        st.markdown("### 3. Review")
        st.markdown(
            "Revise as regras, valide a **sintaxe GDQ** e **exporte** para arquivo."
        )
        if n_cart > 0:
            if st.button("Ir para Review", key="nav_review"):
                st.switch_page("pages/03_review.py")
        else:
            st.caption("Adicione regras no Explore primeiro.")

    with s4:
        st.markdown("### 4. Teste")
        st.markdown(
            "Teste as regras via **Glue job Thundera** antes de implantar."
        )
        if n_cart > 0:
            if st.button("Ir para Teste", key="nav_test"):
                st.switch_page("pages/04_test.py")
        else:
            st.caption("Adicione regras no Explore primeiro.")

    with s5:
        st.markdown("### 5. Ajuda")
        st.markdown(
            "Documentacao completa, conceitos e **glossario**."
        )
        if st.button("Ver Ajuda", key="nav_help"):
            st.switch_page("pages/05_help.py")

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


if __name__ == "__main__":
    main()
