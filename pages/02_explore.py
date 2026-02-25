"""
Pagina 02 — Explore: Calibracao de regras numericas e de tabela.

Tabs:
- Numericas: para cada coluna numerica, grafico + bandas + backtest + carrinho
- Tabela: RowCount com mesmos controles de calibracao

Cada regra tem controles de parametros independentes (inline).
Graficos mostram bandas rolantes (media movel) em vez de bandas fixas.

Definido conforme docs/technical_spec_v1.md secao 12 (Sprint A2 + B1).
"""

import streamlit as st
import plotly.graph_objects as go

from config import load_config, AthenaMode
from core.models.baseline import BaselineStrategy
from core.models.enums import BaselineMethod, ConfidenceLevel, SemanticType
from core.models.rule_selection import RuleSelection
from core.rule_explainer import explain_rule, explain_rule_detail
from infra.athena_client import AthenaClient
from infra.query_builder import QueryBuilder
from services.analysis_service import AnalysisService
from services.proposal_service import ProposalService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client() -> AthenaClient:
    if "client" not in st.session_state:
        config = load_config()
        st.session_state["config"] = config
        st.session_state["client"] = AthenaClient(config)
    return st.session_state["client"]


def _get_analysis_service(client: AthenaClient) -> AnalysisService:
    if "analysis_service" not in st.session_state:
        builder = QueryBuilder(dialect=client.dialect)
        st.session_state["analysis_service"] = AnalysisService(client, builder)
    return st.session_state["analysis_service"]


def _get_proposal_service() -> ProposalService:
    if "proposal_service" not in st.session_state:
        st.session_state["proposal_service"] = ProposalService()
    return st.session_state["proposal_service"]


def _confidence_badge(level: ConfidenceLevel) -> str:
    badges = {
        ConfidenceLevel.HIGH: ":green[HIGH]",
        ConfidenceLevel.MEDIUM: ":orange[MEDIUM]",
        ConfidenceLevel.LOW: ":red[LOW]",
    }
    return badges.get(level, level.value)


def _build_config_from_dict(config_dict):
    from core.models.dataset_config import DatasetConfig
    from core.models.enums import PartitionMethod, GrainType, LookbackMode
    return DatasetConfig(
        schema=config_dict["schema"],
        table=config_dict["table"],
        partition_method=PartitionMethod(config_dict["partition_method"]),
        partition_column=config_dict.get("partition_column"),
        date_column=config_dict["date_column"],
        date_expression=config_dict.get("date_expression"),
        lookback_value=config_dict["lookback_value"],
        grain_type=GrainType(config_dict.get("grain_type", "daily")),
        lookback_mode=LookbackMode(config_dict.get("lookback_mode", "last_n_periods")),
        base_filter_sql=config_dict.get("base_filter_sql"),
    )


def _render_rule_params(rule_key: str) -> tuple:
    """Renderiza controles de parametros inline.

    Returns:
        (n_periods, n_sigma, margin_pct, buffer)
    """
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        n_periods = st.slider(
            "N (periodos):", min_value=5, max_value=90, value=20,
            key=f"n_{rule_key}",
            help="Janela movel de historico para calcular media e desvio. "
                 "Valores maiores suavizam variacao; menores reagem mais rapido a mudancas.",
        )
    with col2:
        n_sigma = st.select_slider(
            "K (sigma):", options=[1.0, 1.5, 2.0, 2.5, 3.0], value=2.0,
            key=f"k_{rule_key}",
            help="Multiplicador de desvio padrao. "
                 "2.0 = ~95% dos dados dentro da banda. 3.0 = ~99.7%. "
                 "Valor menor = regra mais rigorosa.",
        )
    with col3:
        margin_pct = st.slider(
            "Margem %:", min_value=5, max_value=30, value=10,
            key=f"margin_{rule_key}",
            help="Banda alternativa: porcentagem fixa da media. "
                 "Usada pelo dual guard quando a banda sigma e muito estreita "
                 "(ex: dados com variabilidade muito baixa).",
        ) / 100.0
    with col4:
        buffer = st.select_slider(
            "Buffer:", options=[0.0, 0.001, 0.01, 0.1], value=0.01,
            key=f"buffer_{rule_key}",
            help="Valor minimo adicionado aos limites para evitar falsos positivos "
                 "por arredondamento. 0.01 e adequado para a maioria dos casos.",
        )
    return n_periods, n_sigma, margin_pct, buffer


def _render_rolling_chart(values, dates, n_periods, n_sigma, margin_pct, y_label):
    """Renderiza grafico Plotly com bandas rolantes (media movel)."""
    from core.statistical_engine import compute_rolling_bands

    bands = compute_rolling_bands(values, n_periods, n_sigma, margin_pct)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=dates, y=values,
        mode="lines+markers",
        name=f"{y_label} historico",
        line=dict(color="royalblue", width=2),
        marker=dict(size=4),
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=bands["sigma_upper"],
        mode="lines", name=f"{n_sigma}\u03c3 upper",
        line=dict(color="rgba(100,149,237,0.4)", width=1),
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=bands["sigma_lower"],
        mode="lines", name=f"{n_sigma}\u03c3 band",
        line=dict(color="rgba(100,149,237,0.4)", width=1),
        fill="tonexty", fillcolor="rgba(173,216,230,0.3)",
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=bands["margin_upper"],
        mode="lines", name=f"{margin_pct*100:.0f}% upper",
        line=dict(color="rgba(60,179,113,0.4)", width=1),
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=bands["margin_lower"],
        mode="lines", name=f"{margin_pct*100:.0f}% margin",
        line=dict(color="rgba(60,179,113,0.4)", width=1),
        fill="tonexty", fillcolor="rgba(144,238,144,0.2)",
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=bands["center"],
        mode="lines", name="media movel",
        line=dict(color="gray", dash="dash", width=1),
    ))

    fig.update_layout(
        height=400,
        margin=dict(l=50, r=20, t=30, b=30),
        xaxis_title="Periodo",
        yaxis_title=y_label,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_backtest_metrics(proposal):
    bt = proposal.backtest
    if bt:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "Cobertura", f"{bt.coverage_pct:.1f}%",
                help="Porcentagem de periodos historicos que passariam na regra. Ideal: > 90%.",
            )
        with col2:
            st.metric(
                "Falsos Positivos", f"~{bt.false_positive_proxy}",
                help="Periodos historicos normais que seriam reprovados pela regra. Ideal: 0 ou proximo.",
            )
        with col3:
            st.metric(
                "Estabilidade", f"{bt.stability_score:.2f}",
                help="Quao pouco a banda muda com variacao de parametros. "
                     "1.0 = muito estavel. Abaixo de 0.5 pode indicar instabilidade.",
            )
        with col4:
            st.metric(
                "Confianca", _confidence_badge(proposal.confidence),
                help="Avaliacao geral: HIGH = recomendada, MEDIUM = revisar parametros, LOW = nao recomendada.",
            )

        if bt.has_drift:
            st.warning(
                "Tendencia (drift) detectada no historico. "
                "A banda pode nao ser confiavel. Considere reduzir N para usar dados mais recentes."
            )
        if bt.outlier_periods:
            st.caption(f"Periodos outlier: {', '.join(bt.outlier_periods[:5])}")

    if proposal.warnings:
        for w in proposal.warnings:
            st.caption(f"  {w}")


def _render_add_to_cart(proposal, label, stable_key, show_syntax=True):
    # Explicacao em linguagem natural
    st.info(explain_rule(proposal))

    if show_syntax:
        with st.expander("Sintaxe GDQ e detalhes", expanded=False):
            st.code(proposal.gdq_syntax_preview)
            st.markdown(explain_rule_detail(proposal))

    existing_ids = {s.proposal_id for s in st.session_state["rule_cart"]}
    if proposal.id in existing_ids:
        st.success(f"Regra {label} ja esta no carrinho.")
    elif st.button(
        f"Adicionar {label} ao carrinho",
        key=f"cart_{stable_key}",
        type="primary",
    ):
        selection = RuleSelection(
            proposal_id=proposal.id,
            proposal=proposal,
            final_gdq_syntax=proposal.gdq_syntax_preview,
        )
        st.session_state["rule_cart"].append(selection)
        st.rerun()


def _get_cached_proposals(cache_key, generate_fn):
    if cache_key not in st.session_state:
        st.session_state[cache_key] = generate_fn()
    return st.session_state[cache_key]


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Explore - GDQ Rule Proposer", page_icon=":bar_chart:", layout="wide")

st.title("Calibracao de Regras")
st.caption(
    "Ajuste os parametros de cada regra e visualize o impacto no historico. "
    "Adicione as regras aprovadas ao carrinho para exportar na pagina Review."
)

# Guard: precisa ter passado pelo setup
if "dataset_config" not in st.session_state:
    st.warning("Configure a tabela na pagina **Setup** primeiro. Use o menu lateral para navegar.")
    st.stop()

if "column_profiles" not in st.session_state:
    st.warning("Execute o profiling na pagina **Setup** primeiro. Use o menu lateral para navegar.")
    st.stop()

dataset_config = st.session_state["dataset_config"]
profiles = st.session_state["column_profiles"]

# Filtrar colunas selecionadas por tipo
selected_set = set(dataset_config.selected_columns or [])
numeric_profiles = [
    p for p in profiles
    if p.effective_type == SemanticType.NUMERIC and p.column_name in selected_set
]
cat_profiles = [
    p for p in profiles
    if p.is_categorical and p.column_name in selected_set
]

# --- Config summary ---
with st.expander(
    f"Configuracao: `{dataset_config.schema}.{dataset_config.table}` — "
    f"{len(selected_set)} colunas ({len(numeric_profiles)} num, {len(cat_profiles)} cat)",
    expanded=False,
):
    cfg_c1, cfg_c2, cfg_c3 = st.columns(3)
    cfg_c1.markdown(f"**Data:** `{dataset_config.date_expression or dataset_config.date_column}`")
    cfg_c2.markdown(f"**Lookback:** {dataset_config.lookback_value} periodos")
    cfg_c3.markdown(f"**Particao:** {dataset_config.partition_method.value}")

    if dataset_config.base_filter_sql:
        st.caption(f"Filtro: `{dataset_config.base_filter_sql}`")

    # Column list grouped by type
    col_list_1, col_list_2 = st.columns(2)
    with col_list_1:
        st.markdown("**Numericas**")
        if numeric_profiles:
            for p in numeric_profiles:
                null_pct = p.null_ratio * 100
                st.caption(f"- `{p.column_name}` (null {null_pct:.0f}%)")
        else:
            st.caption("Nenhuma")
    with col_list_2:
        st.markdown("**Categoricas**")
        if cat_profiles:
            for p in cat_profiles:
                st.caption(f"- `{p.column_name}` ({p.distinct_count} distintos)")
        else:
            st.caption("Nenhuma")

# Inicializar carrinho
if "rule_cart" not in st.session_state:
    st.session_state["rule_cart"] = []


# ---------------------------------------------------------------------------
# Sidebar: contexto da tabela + carrinho
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Tabela ativa")
    st.code(f"{dataset_config.schema}.{dataset_config.table}")

    n_sel = len(dataset_config.selected_columns) if dataset_config.selected_columns else 0
    n_num = len(numeric_profiles)
    st.caption(f"{n_sel} colunas selecionadas ({n_num} numericas)")

    if dataset_config.date_expression:
        st.caption(f"Data: `{dataset_config.date_expression}`")
    else:
        st.caption(f"Data: `{dataset_config.date_column}`")

    st.caption(f"Lookback: {dataset_config.lookback_value} periodos")

    st.divider()

    cart_count = len(st.session_state["rule_cart"])
    if cart_count > 0:
        st.subheader(f"Carrinho ({cart_count})")
        for sel in st.session_state["rule_cart"]:
            p = sel.proposal
            target = p.target_column or "(tabela)"
            label = p.rule_type.value.split("_")[0].title()
            st.caption(f"- {label} `{target}`")
        if st.button("Ir para Review", type="primary", key="sidebar_review"):
            st.switch_page("pages/03_review.py")
    else:
        st.caption("Carrinho vazio.")

    st.divider()
    if st.button("Voltar ao Setup", key="sidebar_back_setup"):
        st.switch_page("pages/01_setup.py")


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

try:
    client = _get_client()
except Exception as e:
    st.error(f"Falha na conexao: {e}")
    st.stop()

analysis_svc = _get_analysis_service(client)
proposal_svc = _get_proposal_service()

config_dict = {
    "schema": dataset_config.schema,
    "table": dataset_config.table,
    "partition_method": dataset_config.partition_method.value,
    "partition_column": dataset_config.partition_column,
    "date_column": dataset_config.date_column,
    "date_expression": dataset_config.date_expression,
    "lookback_value": dataset_config.lookback_value,
    "grain_type": dataset_config.grain_type.value,
    "lookback_mode": dataset_config.lookback_mode.value,
    "base_filter_sql": dataset_config.base_filter_sql,
}


# ---------------------------------------------------------------------------
# Cached data fetchers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner="Consultando historico numerico...")
def fetch_numeric_history(_config_dict, column):
    config = _build_config_from_dict(_config_dict)
    return analysis_svc.get_numeric_history(config, column)


@st.cache_data(ttl=900, show_spinner="Consultando historico de volume...")
def fetch_row_count_history(_config_dict):
    config = _build_config_from_dict(_config_dict)
    return analysis_svc.get_row_count_history(config)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_numericas, tab_tabela, tab_resumo = st.tabs(["Numericas", "Tabela", "Resumo"])


# ===========================================================================
# Tab: Numericas
# ===========================================================================

with tab_numericas:
    if not numeric_profiles:
        st.info("Nenhuma coluna numerica selecionada. Volte ao **Setup** para selecionar colunas.")
    else:
        col_names = [p.column_name for p in numeric_profiles]
        selected_col = st.selectbox(
            "Coluna numerica:",
            col_names,
            key="explore_selected_col",
            help="Selecione a coluna para calibrar. Cada coluna gera regras Mean (media) "
                 "e StdDev (desvio padrao) independentes.",
        )

        st.divider()

        try:
            history_df = fetch_numeric_history(config_dict, selected_col)
        except Exception as e:
            st.error(f"Erro ao consultar historico: {e}")
            st.stop()

        if history_df.empty:
            st.warning(f"Nenhum dado historico encontrado para `{selected_col}`.")
        else:
            # ---- Mean ----
            st.subheader(f"Mean -- {selected_col}")

            with st.expander("O que e o dual guard?", expanded=False):
                st.markdown(
                    "O **dual guard** combina duas bandas de validacao com OR:\n\n"
                    "1. **Banda sigma:** media +/- K desvios padrao — captura a variabilidade normal dos dados\n"
                    "2. **Banda margem:** media +/- X% — captura variacao proporcional\n\n"
                    "A regra passa se o valor estiver dentro de **qualquer uma** das bandas. "
                    "Isso evita falsos positivos quando o dado e muito estavel (sigma proximo de 0).\n\n"
                    "O grafico mostra ambas as bandas: azul (sigma) e verde (margem). "
                    "Ajuste os parametros abaixo e observe como as bandas mudam."
                )

            mean_n, mean_k, mean_margin, mean_buffer = _render_rule_params(
                f"mean_{selected_col}",
            )

            mean_baseline = BaselineStrategy(
                method=BaselineMethod.LAST_N_PERIODS,
                n_periods=mean_n,
                n_sigma=mean_k,
                margin_pct=mean_margin,
            )

            mean_cache_key = f"proposal_mean_{selected_col}_{mean_n}_{mean_k}_{mean_margin}"
            mean_proposals = _get_cached_proposals(
                mean_cache_key,
                lambda: [
                    p for p in proposal_svc.propose_numeric_rules(
                        history_df, selected_col, dataset_config.table, mean_baseline,
                    )
                    if "mean" in p.rule_type.value
                ],
            )

            if mean_proposals:
                proposal = mean_proposals[0]
                values = proposal.history_values
                dates = proposal.history_dates

                if values and dates:
                    _render_rolling_chart(
                        values, dates, mean_n, mean_k, mean_margin, "Mean",
                    )

                _render_backtest_metrics(proposal)
                _render_add_to_cart(
                    proposal, "Mean",
                    f"mean_{selected_col}",
                )

            st.divider()

            # ---- StdDev ----
            st.subheader(f"StdDev -- {selected_col}")

            std_n, std_k, std_margin, std_buffer = _render_rule_params(
                f"stddev_{selected_col}",
            )

            std_baseline = BaselineStrategy(
                method=BaselineMethod.LAST_N_PERIODS,
                n_periods=std_n,
                n_sigma=std_k,
                margin_pct=std_margin,
            )

            std_cache_key = f"proposal_stddev_{selected_col}_{std_n}_{std_k}_{std_margin}"
            std_proposals = _get_cached_proposals(
                std_cache_key,
                lambda: [
                    p for p in proposal_svc.propose_numeric_rules(
                        history_df, selected_col, dataset_config.table, std_baseline,
                    )
                    if "stddev" in p.rule_type.value
                ],
            )

            if std_proposals:
                proposal = std_proposals[0]
                values = proposal.history_values
                dates = proposal.history_dates

                if values and dates:
                    _render_rolling_chart(
                        values, dates, std_n, std_k, std_margin, "StdDev",
                    )

                _render_backtest_metrics(proposal)
                _render_add_to_cart(
                    proposal, "StdDev",
                    f"stddev_{selected_col}",
                )

            st.divider()

            # ---- Completeness ----
            comp_cache_key = f"proposal_comp_{selected_col}"
            comp_proposals = _get_cached_proposals(
                comp_cache_key,
                lambda: [
                    p for p in proposal_svc.propose_numeric_rules(
                        history_df, selected_col, dataset_config.table,
                        BaselineStrategy(method=BaselineMethod.LAST_N_PERIODS),
                    )
                    if p.rule_type.value.startswith("completeness")
                ],
            )

            if comp_proposals:
                with st.expander(f"Completeness {selected_col}", expanded=False):
                    st.caption(
                        "Regra de completude: verifica que a porcentagem de valores nao-nulos "
                        "esta acima de um limite. Util para colunas que devem ser sempre preenchidas."
                    )
                    proposal = comp_proposals[0]
                    st.code(proposal.gdq_syntax_preview)
                    _render_add_to_cart(
                        proposal, "Completeness",
                        f"comp_{selected_col}",
                        show_syntax=False,
                    )


# ===========================================================================
# Tab: Tabela (RowCount)
# ===========================================================================

with tab_tabela:
    st.subheader(f"RowCount -- {dataset_config.table}")
    st.caption(
        "Regra de volume: verifica que a quantidade de linhas por periodo "
        "esta dentro do esperado com base no historico."
    )

    rc_n, rc_k, rc_margin, rc_buffer = _render_rule_params("rowcount")

    try:
        rc_history_df = fetch_row_count_history(config_dict)
    except Exception as e:
        st.error(f"Erro ao consultar historico de volume: {e}")
        st.stop()

    if rc_history_df.empty:
        st.warning("Nenhum dado de volume encontrado.")
    else:
        rc_baseline = BaselineStrategy(
            method=BaselineMethod.LAST_N_PERIODS,
            n_periods=rc_n,
            n_sigma=rc_k,
            margin_pct=rc_margin,
        )

        rc_cache_key = f"proposal_rc_{rc_n}_{rc_k}_{rc_margin}"
        rc_proposals = _get_cached_proposals(
            rc_cache_key,
            lambda: proposal_svc.propose_table_rules(
                rc_history_df, dataset_config.table, rc_baseline,
            ),
        )

        if rc_proposals:
            rc_proposal = rc_proposals[0]

            values = rc_proposal.history_values
            dates = rc_proposal.history_dates

            if values and dates:
                _render_rolling_chart(
                    values, dates, rc_n, rc_k, rc_margin, "Row Count",
                )

            _render_backtest_metrics(rc_proposal)
            _render_add_to_cart(rc_proposal, "RowCount", "rowcount")
        else:
            st.warning(
                "Dados insuficientes para gerar regra RowCount. "
                "Verifique o lookback e o eixo temporal no Setup."
            )


# ===========================================================================
# Tab: Resumo
# ===========================================================================

with tab_resumo:
    st.subheader("Resumo de Regras")

    cart = st.session_state.get("rule_cart", [])
    if not cart:
        st.info(
            "Nenhuma regra no carrinho ainda. "
            "Use as abas **Numericas** e **Tabela** para calibrar e adicionar regras."
        )
    else:
        for sel in cart:
            p = sel.proposal
            label = p.rule_type.value.replace("_", " ").title()
            target = p.target_column or "(tabela)"
            confidence = p.confidence.value.upper()

            badge = {
                "HIGH": ":green[HIGH]",
                "MEDIUM": ":orange[MEDIUM]",
                "LOW": ":red[LOW]",
            }.get(confidence, confidence)

            coverage_str = f"{p.backtest.coverage_pct:.1f}%" if p.backtest else "N/A"

            res_c1, res_c2, res_c3 = st.columns([4, 1.5, 1.5])
            res_c1.markdown(f"**{label}** — `{target}`")
            res_c2.markdown(badge)
            res_c3.caption(f"Cobertura: {coverage_str}")

            st.caption(explain_rule(p))

        st.divider()

        res_btn1, res_btn2 = st.columns(2)
        with res_btn1:
            if st.button("Ir para Review & Export", type="primary", key="resumo_review"):
                st.switch_page("pages/03_review.py")
        with res_btn2:
            st.caption(f"{len(cart)} regra(s) no carrinho")
