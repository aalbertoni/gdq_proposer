"""
Pagina 02 — Explore: Calibracao de regras numericas, categoricas e de tabela.

Tabs:
- Numericas: Mean, StdDev, Percentil, Completeness por coluna
- Categoricas: AllowedValues, DistinctValuesCount, Frequency (individual), Completeness
- Tabela: RowCount com mesmos controles de calibracao
- Resumo: lista das regras adicionadas ao carrinho

Definido conforme docs/technical_spec_v1.md secao 12.
"""

import streamlit as st
import plotly.graph_objects as go

from config import load_config, AthenaMode
from core.models.baseline import BaselineStrategy
from core.models.enums import BaselineMethod, ConfidenceLevel, RuleType, SemanticType
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
        (n_periods, n_sigma, margin_pct, buffer, margin_enabled)
    """
    col1, col2, col3, col4, col5 = st.columns([3, 2, 1, 3, 2])
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
        margin_enabled = st.checkbox(
            "Margem",
            value=True,
            key=f"margin_on_{rule_key}",
            help="Ativar banda margem (dual guard). Quando ativada, a regra "
                 "combina banda sigma OR banda margem, reduzindo falsos positivos "
                 "em dados de baixa variabilidade. Desative para usar apenas sigma.",
        )
    with col4:
        if margin_enabled:
            margin_pct = st.slider(
                "Margem %:", min_value=1, max_value=30, value=10,
                key=f"margin_{rule_key}",
                help="Porcentagem fixa da media para a banda alternativa.",
            ) / 100.0
        else:
            margin_pct = st.session_state.get(f"margin_{rule_key}", 10) / 100.0
            st.caption("Margem desativada")
    with col5:
        buffer = st.select_slider(
            "Buffer:", options=[0.0, 0.001, 0.01, 0.1], value=0.01,
            key=f"buffer_{rule_key}",
            help="Valor minimo adicionado aos limites para evitar falsos positivos "
                 "por arredondamento. 0.01 e adequado para a maioria dos casos.",
        )
    return n_periods, n_sigma, margin_pct, buffer, margin_enabled


def _render_rolling_chart(
    values, dates, n_periods, n_sigma, margin_pct, y_label,
    margin_enabled=True,
):
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

    if margin_enabled:
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
                help="Estimativa de periodos normais reprovados indevidamente. "
                     "Calculado como: periodos que violam a regra MAS estao dentro de "
                     "4 desvios padrao da media global (provavelmente normais). "
                     "E uma aproximacao — nao ha como saber com certeza se um valor "
                     "e realmente anomalo. Ideal: 0.",
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


def _render_auto_tune(proposal_svc, values, dates, rule_key, metric_kind="numeric"):
    """Renderiza botao de auto-tuning, exibe resultado e aplica parametros."""
    cache_key = f"autotune_{rule_key}"

    if st.button(
        "Sugerir melhor combinacao",
        key=f"btn_autotune_{rule_key}",
        help="Testa diversas combinacoes de N, sigma e margem para encontrar "
             "a que maximiza cobertura com menos falsos positivos.",
    ):
        with st.spinner("Avaliando combinacoes..."):
            result = proposal_svc.find_best_params(
                values=values, dates=dates, metric_kind=metric_kind,
            )
            st.session_state[cache_key] = result

    if cache_key in st.session_state:
        result = st.session_state[cache_key]
        confidence = result["confidence"]
        badge = _confidence_badge(confidence)

        if result["viable"]:
            st.success(
                f"{badge} {result['recommendation']}"
            )
        else:
            st.error(
                f"{badge} {result['recommendation']}"
            )

        st.caption(
            f"Melhor: N={result['n_periods']}, "
            f"sigma={result['n_sigma']}, "
            f"margem={result['margin_pct']*100:.0f}%"
            f"{' (ativada)' if result['margin_enabled'] else ' (desativada)'} "
            f"-- cobertura {result['coverage_pct']:.1f}%, "
            f"FP: {result['false_positives']}, "
            f"estabilidade: {result['stability']:.2f}"
        )

        # Botao para aplicar parametros sugeridos nos sliders
        if result["viable"] and st.button(
            "Aplicar parametros sugeridos",
            key=f"apply_autotune_{rule_key}",
            help="Atualiza os sliders com os parametros recomendados.",
        ):
            st.session_state[f"n_{rule_key}"] = result["n_periods"]
            st.session_state[f"k_{rule_key}"] = result["n_sigma"]
            st.session_state[f"margin_{rule_key}"] = int(result["margin_pct"] * 100)
            st.session_state[f"margin_on_{rule_key}"] = result["margin_enabled"]
            # Limpar cache de proposals que dependem destes params
            keys_to_clear = [
                k for k in list(st.session_state.keys())
                if k.startswith("proposal_") and rule_key in k
            ]
            for k in keys_to_clear:
                del st.session_state[k]
            st.rerun()


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
    f"Configuracao: `{dataset_config.schema}.{dataset_config.table}` -- "
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
    n_cat = len(cat_profiles)
    st.caption(f"{n_sel} colunas selecionadas ({n_num} num, {n_cat} cat)")

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

    # Query cost summary
    _summary = client.logger.get_session_summary()
    if _summary["total_queries"] > 0:
        st.subheader("Queries")
        _cols = st.columns(2)
        _cols[0].metric("Executadas", _summary["total_queries"])
        _cols[1].metric("Tempo total", f"{_summary['total_elapsed_ms'] / 1000:.1f}s")

        if _summary["total_bytes_scanned"] > 0:
            _bytes = _summary["total_bytes_scanned"]
            if _bytes >= 1024 ** 3:
                _bytes_label = f"{_bytes / (1024 ** 3):.2f} GB"
            elif _bytes >= 1024 ** 2:
                _bytes_label = f"{_bytes / (1024 ** 2):.1f} MB"
            else:
                _bytes_label = f"{_bytes / 1024:.0f} KB"
            st.caption(f"Dados escaneados: {_bytes_label}")
            st.caption(f"Custo estimado: ${_summary['estimated_cost_usd']:.4f}")
        elif client.dialect.value == "duckdb":
            st.caption("Modo local (DuckDB) -- sem custo Athena")

        if _summary["errors"] > 0:
            st.caption(f":red[Erros: {_summary['errors']}]")

        # Cost guardrail warning
        _app_cfg = st.session_state.get("config")
        _threshold = _app_cfg.athena.cost_warning_threshold_usd if _app_cfg else 0.50
        if _summary["estimated_cost_usd"] > _threshold:
            st.warning(
                f"Custo da sessao (${_summary['estimated_cost_usd']:.4f}) "
                f"excedeu o limite de ${_threshold:.2f}. "
                f"Considere reduzir o lookback ou o numero de colunas.",
                icon="💰",
            )

        with st.expander("Log de queries"):
            st.download_button(
                label="Exportar log",
                data=client.logger.export_json(),
                file_name="gdq_query_log.json",
                mime="application/json",
                key="sidebar_export_log",
                help="JSON com resumo da sessao e detalhes de cada query executada.",
            )

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


@st.cache_data(ttl=900, show_spinner="Consultando distribuicao categorica...")
def fetch_categorical_distribution(_config_dict, column):
    config = _build_config_from_dict(_config_dict)
    return analysis_svc.get_categorical_distribution(config, column)


@st.cache_data(ttl=900, show_spinner="Consultando dominio categorico...")
def fetch_categorical_domain(_config_dict, column):
    config = _build_config_from_dict(_config_dict)
    return analysis_svc.get_categorical_domain(config, column)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_numericas, tab_categoricas, tab_tabela, tab_resumo = st.tabs(
    ["Numericas", "Categoricas", "Tabela", "Resumo"],
)


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
            help="Selecione a coluna para calibrar. Cada coluna gera regras Mean (media), "
                 "StdDev (desvio padrao) e Percentil independentes.",
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

            mean_n, mean_k, mean_margin, mean_buffer, mean_margin_on = _render_rule_params(
                f"mean_{selected_col}",
            )

            mean_baseline = BaselineStrategy(
                method=BaselineMethod.LAST_N_PERIODS,
                n_periods=mean_n,
                n_sigma=mean_k,
                margin_pct=mean_margin,
                margin_enabled=mean_margin_on,
            )

            mean_cache_key = f"proposal_mean_{selected_col}_{mean_n}_{mean_k}_{mean_margin}_{mean_margin_on}"
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
                        margin_enabled=mean_margin_on,
                    )
                    _render_auto_tune(
                        proposal_svc, values, dates,
                        f"mean_{selected_col}", metric_kind="numeric",
                    )

                _render_backtest_metrics(proposal)
                _render_add_to_cart(
                    proposal, "Mean",
                    f"mean_{selected_col}",
                )

            st.divider()

            # ---- StdDev ----
            st.subheader(f"StdDev -- {selected_col}")

            std_n, std_k, std_margin, std_buffer, std_margin_on = _render_rule_params(
                f"stddev_{selected_col}",
            )

            std_baseline = BaselineStrategy(
                method=BaselineMethod.LAST_N_PERIODS,
                n_periods=std_n,
                n_sigma=std_k,
                margin_pct=std_margin,
                margin_enabled=std_margin_on,
            )

            std_cache_key = f"proposal_stddev_{selected_col}_{std_n}_{std_k}_{std_margin}_{std_margin_on}"
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
                        margin_enabled=std_margin_on,
                    )
                    _render_auto_tune(
                        proposal_svc, values, dates,
                        f"stddev_{selected_col}", metric_kind="numeric",
                    )

                _render_backtest_metrics(proposal)
                _render_add_to_cart(
                    proposal, "StdDev",
                    f"stddev_{selected_col}",
                )

            st.divider()

            # ---- Percentil (D.1b) ----
            st.subheader(f"Percentil -- {selected_col}")
            st.caption(
                "Regras de percentil monitoram a forma da distribuicao, nao apenas a media. "
                "P10 detecta mudancas nos valores baixos; P90 detecta mudancas nos valores altos. "
                "Implementada via CustomSql com dual guard dinamico."
            )

            pct_options = {
                "P1": "p01", "P5": "p05", "P10": "p10",
                "P90": "p90", "P95": "p95", "P99": "p99",
            }
            selected_pcts = st.multiselect(
                "Percentis a monitorar:",
                options=list(pct_options.keys()),
                default=["P10", "P90"],
                key=f"pct_select_{selected_col}",
                help="Selecione quais percentis gerar regras. P10/P90 sao os mais comuns.",
            )

            if selected_pcts:
                pct_n, pct_k, pct_margin, pct_buffer, pct_margin_on = _render_rule_params(
                    f"pct_{selected_col}",
                )

                pct_baseline = BaselineStrategy(
                    method=BaselineMethod.LAST_N_PERIODS,
                    n_periods=pct_n,
                    n_sigma=pct_k,
                    margin_pct=pct_margin,
                    margin_enabled=pct_margin_on,
                )

                pct_levels = [pct_options[p] for p in selected_pcts]
                pct_cache_key = (
                    f"proposal_pct_{selected_col}_{pct_n}_{pct_k}_{pct_margin}"
                    f"_{pct_margin_on}_{'_'.join(pct_levels)}"
                )
                pct_proposals = _get_cached_proposals(
                    pct_cache_key,
                    lambda: proposal_svc.propose_percentile_rules(
                        history_df, selected_col, dataset_config.table,
                        pct_baseline, percentile_levels=pct_levels,
                    ),
                )

                for pct_prop in pct_proposals:
                    pct_label = pct_prop.metric_name.upper()
                    with st.expander(f"{pct_label} -- {selected_col}", expanded=len(pct_proposals) <= 2):
                        pct_vals = pct_prop.history_values
                        pct_dates = pct_prop.history_dates

                        if pct_vals and pct_dates:
                            _render_rolling_chart(
                                pct_vals, pct_dates, pct_n, pct_k, pct_margin,
                                pct_label, margin_enabled=pct_margin_on,
                            )
                            _render_auto_tune(
                                proposal_svc, pct_vals, pct_dates,
                                f"pct_{selected_col}_{pct_prop.metric_name}",
                                metric_kind="numeric",
                            )

                        _render_backtest_metrics(pct_prop)
                        _render_add_to_cart(
                            pct_prop, f"Percentil {pct_label}",
                            f"pct_{selected_col}_{pct_prop.metric_name}",
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
# Tab: Categoricas
# ===========================================================================

with tab_categoricas:
    if not cat_profiles:
        st.info("Nenhuma coluna categorica selecionada. Volte ao **Setup** para selecionar colunas.")
    else:
        cat_col_names = [p.column_name for p in cat_profiles]
        selected_cat_col = st.selectbox(
            "Coluna categorica:",
            cat_col_names,
            key="explore_selected_cat_col",
            help="Selecione a coluna para configurar regras categoricas. "
                 "As regras disponiveis dependem da cardinalidade (low/mid/high).",
        )

        # Get profile for selected column
        cat_profile = next(p for p in cat_profiles if p.column_name == selected_cat_col)
        effective = cat_profile.effective_type

        # Cardinality badge
        card_labels = {
            SemanticType.CATEGORICAL_LOW_CARDINALITY: (
                ":green[Low cardinality]",
                "Dominio fixo com poucos valores. Todas as regras categoricas estao disponiveis.",
            ),
            SemanticType.CATEGORICAL_MID_CARDINALITY: (
                ":orange[Mid cardinality]",
                "Muitos valores distintos. Monitoramento limitado aos mais frequentes.",
            ),
            SemanticType.CATEGORICAL_HIGH_CARDINALITY: (
                ":red[High cardinality]",
                "Alta cardinalidade. Apenas completude e contagem de distintos.",
            ),
        }
        badge, caption = card_labels.get(effective, ("", ""))
        st.markdown(f"**Classificacao:** {badge} ({cat_profile.distinct_count} valores distintos)")
        st.caption(caption)

        with st.expander("O que e cardinalidade?", expanded=False):
            st.markdown(
                "A **cardinalidade** indica quantos valores distintos uma coluna tem:\n\n"
                "- **Baixa (low):** ate ~50 valores (ex: UF, status). "
                "Gera: valores permitidos, contagem de distintos, frequencia por valor, completude.\n"
                "- **Media (mid):** ~50 a ~500 valores (ex: cidade, produto). "
                "Gera: contagem de distintos (range), frequencia top-K, completude.\n"
                "- **Alta (high):** mais de ~500 valores (ex: CPF, ID). "
                "Gera apenas completude.\n\n"
                "A classificacao e feita automaticamente no profiling (Setup, passo 5)."
            )

        st.divider()

        # --- Fetch data ---
        try:
            cat_dist_df = fetch_categorical_distribution(config_dict, selected_cat_col)
            cat_domain_df = fetch_categorical_domain(config_dict, selected_cat_col)
        except Exception as e:
            st.error(f"Erro ao consultar dados categoricos: {e}")
            st.stop()

        if cat_domain_df.empty:
            st.warning(f"Nenhum dado encontrado para `{selected_cat_col}`.")
        else:
            is_low = effective == SemanticType.CATEGORICAL_LOW_CARDINALITY
            is_mid = effective == SemanticType.CATEGORICAL_MID_CARDINALITY
            is_high = effective == SemanticType.CATEGORICAL_HIGH_CARDINALITY

            # ---- Distribution chart (panoramic) ----
            if (is_low or is_mid) and not cat_dist_df.empty:
                domain_values = cat_domain_df["category_value"].tolist()

                fig = go.Figure()
                for val in domain_values[:20]:
                    mask = cat_dist_df["category_value"] == val
                    val_df = cat_dist_df[mask].sort_values("period")
                    fig.add_trace(go.Bar(
                        x=val_df["period"].tolist(),
                        y=val_df["value_pct"].tolist(),
                        name=str(val),
                    ))

                fig.update_layout(
                    barmode="stack",
                    height=350,
                    margin=dict(l=50, r=20, t=30, b=30),
                    xaxis_title="Periodo",
                    yaxis_title="Frequencia (%)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig, use_container_width=True)

            # --- Default frequency mode selector (column-level) ---
            if is_low or is_mid:
                cat_freq_mode = st.radio(
                    "Modo padrao das regras de frequencia:",
                    options=["static", "dynamic", "hybrid"],
                    format_func=lambda m: {
                        "static": "Estatico (valores fixos)",
                        "dynamic": "Dinamico (auto-ajuste)",
                        "hybrid": "Hibrido (dinamico + limites absolutos)",
                    }[m],
                    key=f"cat_freq_mode_{selected_cat_col}",
                    horizontal=True,
                    help=(
                        "Modo padrao para todos os valores. Pode ser sobrescrito individualmente.\n\n"
                        "**Estatico:** limites fixos calculados do historico.\n\n"
                        "**Dinamico:** usa avg(last(N))/std(last(N)) para auto-ajustar.\n\n"
                        "**Hibrido:** auto-ajuste dinamico com floor/ceiling absolutos."
                    ),
                )
            else:
                cat_freq_mode = "static"

            # --- Frequency params (dynamic/hybrid) ---
            if cat_freq_mode in ("dynamic", "hybrid") and (is_low or is_mid):
                cat_p_c1, cat_p_c2, cat_p_c3 = st.columns([3, 3, 3])
                with cat_p_c1:
                    cat_n_periods = st.slider(
                        "N periodos:", min_value=5, max_value=90, value=30,
                        key=f"cat_n_{selected_cat_col}",
                        help="Janela de lookback para calcular media e desvio.",
                    )
                with cat_p_c2:
                    cat_n_sigma = st.slider(
                        "Sigma:", min_value=1.0, max_value=4.0, value=2.0, step=0.5,
                        key=f"cat_sigma_{selected_cat_col}",
                        help="Multiplicador de desvio padrao (mais alto = mais tolerante).",
                    )
                with cat_p_c3:
                    cat_margin_pct = st.slider(
                        "Margem (%):", min_value=1, max_value=30, value=10,
                        key=f"cat_margin_{selected_cat_col}",
                        help="Margem percentual alternativa (dual guard OR).",
                    )
            elif is_low or is_mid:
                cat_n_periods = 20
                cat_n_sigma = 2.0
                cat_margin_pct = st.slider(
                    "Margem (pp):", min_value=1, max_value=30, value=10,
                    key=f"cat_margin_{selected_cat_col}",
                    help="Margem em pontos percentuais sobre a frequencia media para "
                         "definir a faixa aceitavel. Mais alto = regra mais tolerante.",
                )
            else:
                cat_n_periods = 20
                cat_n_sigma = 2.0
                cat_margin_pct = 10

            # --- Hybrid floor/ceiling ---
            cat_floor_pct = None
            cat_ceiling_pct = None
            if cat_freq_mode == "hybrid" and (is_low or is_mid):
                cat_h_c1, cat_h_c2 = st.columns(2)
                with cat_h_c1:
                    cat_floor_pct = st.number_input(
                        "Floor (%):", min_value=0.0, max_value=100.0, value=0.0, step=0.5,
                        key=f"cat_floor_{selected_cat_col}",
                        help="Limite inferior absoluto.",
                    )
                with cat_h_c2:
                    cat_ceiling_pct = st.number_input(
                        "Ceiling (%):", min_value=0.0, max_value=100.0, value=100.0, step=0.5,
                        key=f"cat_ceiling_{selected_cat_col}",
                        help="Limite superior absoluto.",
                    )

            # Validar floor < ceiling no modo hibrido
            if cat_freq_mode == "hybrid" and cat_floor_pct is not None and cat_ceiling_pct is not None:
                if cat_floor_pct >= cat_ceiling_pct:
                    st.error(
                        f"Floor ({cat_floor_pct}%) deve ser menor que Ceiling ({cat_ceiling_pct}%). "
                        "Ajuste os valores para que o intervalo faca sentido."
                    )
                    st.stop()

            # --- Frequency guardrail (D.1c) ---
            if is_low or is_mid:
                max_freq_rules = st.slider(
                    "Max regras de frequencia:",
                    min_value=1, max_value=10, value=5,
                    key=f"max_freq_{selected_cat_col}",
                    help="Limita o numero de regras CustomSql de frequencia. "
                         "Os valores mais frequentes tem prioridade. "
                         "Reduz sobrecarga de queries no GDQ em producao.",
                )
            else:
                max_freq_rules = 5

            cat_baseline = BaselineStrategy(
                method=BaselineMethod.LAST_N_PERIODS,
                n_periods=cat_n_periods,
                n_sigma=cat_n_sigma,
                margin_pct=cat_margin_pct / 100.0,
                margin_enabled=cat_freq_mode != "static",
            )

            cat_cache_key = (
                f"cat_proposals_{selected_cat_col}_{cat_margin_pct}"
                f"_{cat_freq_mode}_{cat_n_periods}_{cat_n_sigma}"
                f"_{cat_floor_pct}_{cat_ceiling_pct}_{max_freq_rules}"
            )
            cat_proposals = _get_cached_proposals(
                cat_cache_key,
                lambda: proposal_svc.propose_categorical_rules(
                    cat_dist_df, cat_domain_df, selected_cat_col,
                    dataset_config.table, cat_profile, cat_baseline,
                    freq_mode=cat_freq_mode,
                    floor_pct=cat_floor_pct,
                    ceiling_pct=cat_ceiling_pct,
                    max_frequency_rules=max_freq_rules,
                ),
            )

            if is_high:
                st.warning(
                    "Coluna com alta cardinalidade. "
                    "Regras de valores permitidos e frequencia nao sao recomendadas."
                )

            # ---- AllowedValues (CAT_LOW) ----
            av_proposals = [p for p in cat_proposals if p.rule_type == RuleType.ALLOWED_VALUES]
            if av_proposals:
                st.subheader("Valores Permitidos (AllowedValues)")
                st.caption(
                    "Verifica que todos os valores da coluna pertencem a lista abaixo. "
                    "Qualquer valor novo faz a regra falhar."
                )
                _render_add_to_cart(
                    av_proposals[0], "AllowedValues",
                    f"av_{selected_cat_col}",
                )
                st.divider()

            # ---- DistinctValuesCount ----
            dc_proposals = [
                p for p in cat_proposals
                if p.rule_type in (RuleType.DISTINCT_COUNT_EXACT, RuleType.DISTINCT_COUNT_RANGE)
            ]
            if dc_proposals:
                st.subheader("Contagem de Distintos (DistinctValuesCount)")
                proposal = dc_proposals[0]
                if proposal.rule_type == RuleType.DISTINCT_COUNT_EXACT:
                    st.caption(
                        f"Verifica que a coluna tem exatamente "
                        f"{int(proposal.suggested_lower)} valores distintos."
                    )
                else:
                    st.caption(
                        f"Verifica que a coluna tem entre "
                        f"{int(proposal.suggested_lower)} e {int(proposal.suggested_upper)} valores distintos."
                    )
                _render_add_to_cart(
                    proposal, "DistinctValuesCount",
                    f"dc_{selected_cat_col}",
                )
                st.divider()

            # ---- Category Frequency (individual per value with charts) ----
            freq_types = {
                RuleType.CATEGORY_FREQUENCY_STATIC,
                RuleType.CATEGORY_FREQUENCY_DYNAMIC,
                RuleType.CATEGORY_FREQUENCY_HYBRID,
            }
            freq_proposals = [
                p for p in cat_proposals
                if p.rule_type in freq_types
            ]
            if freq_proposals:
                mode_labels = {
                    "static": "Estatico",
                    "dynamic": "Dinamico",
                    "hybrid": "Hibrido",
                }
                mode_label = mode_labels.get(cat_freq_mode, cat_freq_mode)
                st.subheader(f"Frequencia por Valor ({mode_label})")

                st.caption(
                    f"Top {len(freq_proposals)} valores por frequencia. "
                    f"Cada valor tem grafico individual e pode ter modo diferente."
                )

                for fp in freq_proposals:
                    cat_val = fp.category_value
                    cov_str = f"{fp.backtest.coverage_pct:.0f}%" if fp.backtest else "N/A"
                    conf_str = _confidence_badge(fp.confidence)

                    with st.expander(
                        f"**{cat_val}** -- faixa: {fp.suggested_lower:.1f}% a {fp.suggested_upper:.1f}% "
                        f"| Cobertura: {cov_str} | {conf_str}",
                        expanded=False,
                    ):
                        # Individual rolling chart
                        if fp.history_values and fp.history_dates:
                            margin_pct_chart = cat_margin_pct / 100.0
                            _render_rolling_chart(
                                fp.history_values, fp.history_dates,
                                cat_n_periods, cat_n_sigma, margin_pct_chart,
                                f"Freq % ({cat_val})",
                                margin_enabled=cat_freq_mode != "static",
                            )

                        _render_backtest_metrics(fp)
                        _render_add_to_cart(
                            fp, f"Freq({cat_val})",
                            f"freq_{selected_cat_col}_{cat_val}",
                        )

                if len(freq_proposals) > 1:
                    # Bulk add button
                    existing_ids = {s.proposal_id for s in st.session_state["rule_cart"]}
                    not_in_cart = [p for p in freq_proposals if p.id not in existing_ids]
                    if not_in_cart and st.button(
                        f"Adicionar todas {len(not_in_cart)} frequencias ao carrinho",
                        key=f"freq_bulk_{selected_cat_col}",
                    ):
                        for fp in not_in_cart:
                            from core.models.rule_selection import RuleSelection as RS
                            st.session_state["rule_cart"].append(RS(
                                proposal_id=fp.id,
                                proposal=fp,
                                final_gdq_syntax=fp.gdq_syntax_preview,
                            ))
                        st.rerun()

                st.divider()

            # ---- Completeness ----
            comp_proposals = [p for p in cat_proposals if p.rule_type == RuleType.COMPLETENESS]
            if comp_proposals:
                with st.expander(f"Completeness {selected_cat_col}", expanded=False):
                    st.caption(
                        "Regra de completude: verifica que a porcentagem de valores nao-nulos "
                        "esta acima de um limite."
                    )
                    proposal = comp_proposals[0]
                    st.code(proposal.gdq_syntax_preview)
                    _render_add_to_cart(
                        proposal, "Completeness",
                        f"cat_comp_{selected_cat_col}",
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

    rc_n, rc_k, rc_margin, rc_buffer, rc_margin_on = _render_rule_params("rowcount")

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
            margin_enabled=rc_margin_on,
        )

        rc_cache_key = f"proposal_rc_{rc_n}_{rc_k}_{rc_margin}_{rc_margin_on}"
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
                    margin_enabled=rc_margin_on,
                )
                _render_auto_tune(
                    proposal_svc, values, dates,
                    "rowcount", metric_kind="numeric",
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
            "Use as abas **Numericas**, **Categoricas** e **Tabela** para calibrar e adicionar regras."
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
            res_c1.markdown(f"**{label}** -- `{target}`")
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
