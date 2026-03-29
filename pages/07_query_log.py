"""
Query Log — Historico completo de queries da sessao.

Exibe todas as queries executadas com status, custo, tempo,
motivo, detalhes de erro e SQL completo.
"""

import streamlit as st

from pages.components.breadcrumb import render_breadcrumb
from pages.components.theme import inject_global_css

st.set_page_config(
    page_title="Query Log — GDQ",
    page_icon=":memo:",
    layout="wide",
)
inject_global_css()

st.title("Query Log")
render_breadcrumb("Query Log")
st.caption("Historico completo de queries executadas nesta sessao.")

# ---------------------------------------------------------------------------
# Guard: precisa de client ativo
# ---------------------------------------------------------------------------
if "client" not in st.session_state:
    st.info("Nenhuma sessao ativa. Volte ao Dashboard para conectar.")
    if st.button("Ir para Dashboard", key="ql_go_dash"):
        st.switch_page("app.py")
    st.stop()

client = st.session_state["client"]
entries = client.logger.entries

if not entries:
    st.info("Nenhuma query executada nesta sessao.")
    if st.button("Ir para Setup", key="ql_go_setup"):
        st.switch_page("pages/01_setup.py")
    st.stop()

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
summary = client.logger.get_session_summary()
time_s = summary["total_elapsed_ms"] / 1000
cost = summary["estimated_cost_usd"]

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total de queries", summary["total_queries"])
m2.metric("Tempo total", f"{time_s:.1f}s")
m3.metric("Cache hits", f"{summary['cache_hits']}/{summary['total_queries']}")
m4.metric("Custo estimado", f"${cost:.4f}")
m5.metric("Erros", summary["errors"])

# Cost guardrail
app_cfg = st.session_state.get("config")
threshold = app_cfg.athena.cost_warning_threshold_usd if app_cfg else 0.50
if cost > threshold:
    st.warning(f"Custo da sessao (${cost:.4f}) excedeu o limite de ${threshold:.2f}.")

st.divider()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
col_f1, col_f2, col_f3 = st.columns(3)

# Status filter
status_options = ["Todas", "OK", "Erro", "Cache Hit"]
with col_f1:
    status_filter = st.selectbox("Status", status_options, key="ql_status_filter")

# Query name filter
query_names = sorted({e.query_name for e in entries})
with col_f2:
    name_filter = st.selectbox(
        "Tipo de query", ["Todas"] + query_names, key="ql_name_filter"
    )

# Column filter
columns_used = sorted({e.column for e in entries if e.column})
with col_f3:
    column_filter = st.selectbox(
        "Coluna", ["Todas"] + columns_used, key="ql_col_filter"
    )

# Apply filters
filtered = list(entries)
if status_filter == "OK":
    filtered = [e for e in filtered if not e.exception_type and not e.cache_hit]
elif status_filter == "Erro":
    filtered = [e for e in filtered if e.exception_type]
elif status_filter == "Cache Hit":
    filtered = [e for e in filtered if e.cache_hit]

if name_filter != "Todas":
    filtered = [e for e in filtered if e.query_name == name_filter]

if column_filter != "Todas":
    filtered = [e for e in filtered if e.column == column_filter]

st.caption(f"Exibindo {len(filtered)} de {len(entries)} queries.")


# ---------------------------------------------------------------------------
# Helper: query purpose descriptions
# ---------------------------------------------------------------------------

def _describe_query_purpose(query_name: str) -> str:
    """Retorna descricao do proposito de cada tipo de query."""
    purposes = {
        "health_check": "Verificacao de conectividade com o Athena.",
        "table_exists": "Validacao de existencia da tabela no catalogo.",
        "get_columns": "Leitura de metadados (colunas e tipos) via information_schema.",
        "get_columns_with_partitions": "Leitura de colunas com deteccao de partition keys.",
        "count_rows": "Contagem de linhas para estimativa de volume e timeout adaptativo.",
        "estimate_volume": "Estimativa de volumetria para ajustar timeout da sessao.",
        "column_sample": "Amostragem de coluna para classificacao semantica (tipo, cardinalidade, cast ratio).",
        "batch_column_sample": "Amostragem em lote de varias colunas para classificacao semantica.",
        "numeric_history": "Historico temporal de metricas numericas (mean, stddev, percentis) para calibracao de regras.",
        "row_count_history": "Historico de contagem de linhas por periodo para regra de RowCount.",
        "distinct_count_history": "Historico de contagem de valores distintos por periodo.",
        "categorical_distribution": "Distribuicao de frequencia de valores categoricos.",
        "categorical_domain": "Dominio de valores (valores unicos) de coluna categorica.",
        "uniqueness_check": "Verificacao de unicidade para deteccao de chaves primarias.",
        "completeness_check": "Verificacao de completude (nulls) da coluna.",
        "partition_values": "Listagem de valores de particao disponiveis.",
        "partition_range": "Range de particoes (min/max) para definir lookback.",
    }
    return purposes.get(query_name, f"Query do tipo `{query_name}`.")


# ---------------------------------------------------------------------------
# Query list (most recent first)
# ---------------------------------------------------------------------------
for i, entry in enumerate(reversed(filtered)):
    # Status badge
    if entry.exception_type:
        status_icon = ":red_circle:"
        status_text = "ERRO"
    elif entry.cache_hit:
        status_icon = ":large_blue_circle:"
        status_text = "CACHE"
    else:
        status_icon = ":green_circle:"
        status_text = "OK"

    # Cost per query
    entry_cost = entry.estimated_cost_usd
    cost_label = f"${entry_cost:.6f}" if entry_cost > 0 else "—"

    # Bytes scanned
    if entry.bytes_scanned and entry.bytes_scanned > 0:
        mb = entry.bytes_scanned / (1024 ** 2)
        if mb >= 1024:
            scan_label = f"{mb / 1024:.2f} GB"
        else:
            scan_label = f"{mb:.2f} MB"
    else:
        scan_label = "—"

    # Column label
    col_label = f" → `{entry.column}`" if entry.column else ""

    # Header line
    header = (
        f"{status_icon} **{entry.query_name}**{col_label} — "
        f"{status_text} · {entry.elapsed_ms}ms · {entry.rows_returned} rows · "
        f"custo {cost_label}"
    )

    with st.expander(header, expanded=False):
        # Detail grid
        d1, d2, d3 = st.columns(3)

        with d1:
            st.markdown("**Detalhes da execucao**")
            st.markdown(f"- **Query:** {entry.query_name}")
            st.markdown(f"- **Dataset:** {entry.dataset}")
            st.markdown(f"- **Coluna:** {entry.column or '(tabela inteira)'}")
            st.markdown(f"- **Timestamp:** {entry.timestamp}")

        with d2:
            st.markdown("**Metricas**")
            st.markdown(f"- **Tempo:** {entry.elapsed_ms}ms")
            st.markdown(f"- **Rows retornadas:** {entry.rows_returned}")
            st.markdown(f"- **Bytes escaneados:** {scan_label}")
            st.markdown(f"- **Custo:** {cost_label}")
            st.markdown(f"- **Cache hit:** {'Sim' if entry.cache_hit else 'Nao'}")

        with d3:
            st.markdown("**Motivo da query**")
            st.markdown(f"{_describe_query_purpose(entry.query_name)}")

            if entry.exception_type:
                st.markdown("**Erro**")
                st.error(f"Tipo: `{entry.exception_type}`")

        # SQL
        if entry.sql:
            st.markdown("**SQL executado:**")
            st.code(entry.sql, language="sql")
        else:
            st.caption("SQL nao disponivel para esta query.")

st.divider()

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
exp1, exp2 = st.columns(2)
with exp1:
    st.download_button(
        label="Exportar log completo (JSON)",
        data=client.logger.export_json(),
        file_name="gdq_query_log.json",
        mime="application/json",
        key="ql_export_json",
    )
with exp2:
    if st.button("Voltar ao Dashboard", key="ql_back_dash"):
        st.switch_page("app.py")
