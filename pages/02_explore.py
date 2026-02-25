"""
Pagina 02 — Explore: Calibracao de regras numericas.

Para cada coluna numerica selecionada:
- Grafico Plotly com historico + bandas de confianca
- Sliders para N (periodos), K (sigma), margem %
- Resultado do backtest (cobertura, FP, estabilidade, drift)
- Badge de confianca (HIGH/MEDIUM/LOW)
- Botao "Adicionar ao carrinho"

Definido conforme docs/technical_spec_v1.md secao 12 (Sprint A2).
"""

import streamlit as st
import plotly.graph_objects as go

from config import load_config, AthenaMode
from core.models.baseline import BaselineStrategy
from core.models.enums import BaselineMethod, ConfidenceLevel, SemanticType
from core.models.rule_selection import RuleSelection
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


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Explore - GDQ Rule Proposer", page_icon=":bar_chart:", layout="wide")

st.title("Calibracao de Regras Numericas")

# Guard: precisa ter passado pelo setup
if "dataset_config" not in st.session_state:
    st.warning("Configure a tabela na pagina **Setup** primeiro.")
    st.stop()

if "column_profiles" not in st.session_state:
    st.warning("Execute o profiling na pagina **Setup** primeiro.")
    st.stop()

dataset_config = st.session_state["dataset_config"]
profiles = st.session_state["column_profiles"]

# Filtrar colunas numericas selecionadas
numeric_profiles = [
    p for p in profiles
    if p.effective_type == SemanticType.NUMERIC
    and p.column_name in (dataset_config.selected_columns or [])
]

if not numeric_profiles:
    st.info("Nenhuma coluna numerica selecionada. Volte ao Setup para selecionar colunas.")
    st.stop()

# Inicializar carrinho
if "rule_cart" not in st.session_state:
    st.session_state["rule_cart"] = []

# Services
try:
    client = _get_client()
except Exception as e:
    st.error(f"Falha na conexao: {e}")
    st.stop()

analysis_svc = _get_analysis_service(client)
proposal_svc = _get_proposal_service()


# ---------------------------------------------------------------------------
# Column selector
# ---------------------------------------------------------------------------

col_names = [p.column_name for p in numeric_profiles]
selected_col = st.selectbox(
    "Selecione a coluna numerica:",
    col_names,
    key="explore_selected_col",
)

st.divider()


# ---------------------------------------------------------------------------
# Parametros via sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Parametros")
    n_periods = st.slider("N (periodos):", min_value=5, max_value=90, value=20, key="explore_n")
    n_sigma = st.select_slider("K (sigma):", options=[1.0, 1.5, 2.0, 2.5, 3.0], value=2.0, key="explore_k")
    margin_pct = st.slider("Margem %:", min_value=5, max_value=30, value=10, key="explore_margin") / 100.0
    buffer = st.select_slider("Buffer:", options=[0.0, 0.001, 0.01, 0.1], value=0.01, key="explore_buffer")

    st.divider()
    st.caption(f"Carrinho: {len(st.session_state['rule_cart'])} regras")


# ---------------------------------------------------------------------------
# Fetch history + generate proposals
# ---------------------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner="Consultando historico...")
def fetch_history(_config_dict, column):
    """Fetch cached — _config_dict is a serializable dict for caching."""
    from core.models.dataset_config import DatasetConfig
    from core.models.enums import PartitionMethod, GrainType, LookbackMode
    config = DatasetConfig(
        schema=_config_dict["schema"],
        table=_config_dict["table"],
        partition_method=PartitionMethod(_config_dict["partition_method"]),
        partition_column=_config_dict.get("partition_column"),
        date_column=_config_dict["date_column"],
        date_expression=_config_dict.get("date_expression"),
        lookback_value=_config_dict["lookback_value"],
        grain_type=GrainType(_config_dict.get("grain_type", "daily")),
        lookback_mode=LookbackMode(_config_dict.get("lookback_mode", "last_n_periods")),
        base_filter_sql=_config_dict.get("base_filter_sql"),
    )
    return analysis_svc.get_numeric_history(config, column)


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

try:
    history_df = fetch_history(config_dict, selected_col)
except Exception as e:
    st.error(f"Erro ao consultar historico: {e}")
    st.stop()

if history_df.empty:
    st.warning(f"Nenhum dado historico encontrado para `{selected_col}`.")
    st.stop()


# ---------------------------------------------------------------------------
# Generate / recalculate proposals
# ---------------------------------------------------------------------------

baseline = BaselineStrategy(
    method=BaselineMethod.LAST_N_PERIODS,
    n_periods=n_periods,
    n_sigma=n_sigma,
    margin_pct=margin_pct,
)

proposals = proposal_svc.propose_numeric_rules(
    history_df, selected_col, dataset_config.table, baseline,
)


# ---------------------------------------------------------------------------
# Display proposals
# ---------------------------------------------------------------------------

for proposal in proposals:
    if proposal.rule_type.value.startswith("completeness"):
        # Completeness: simple display
        with st.expander(f"Completeness {selected_col}", expanded=False):
            st.code(proposal.gdq_syntax_preview)
            if st.button("Adicionar ao carrinho", key=f"cart_comp_{proposal.id}"):
                selection = RuleSelection(
                    proposal_id=proposal.id,
                    proposal=proposal,
                    final_gdq_syntax=proposal.gdq_syntax_preview,
                )
                st.session_state["rule_cart"].append(selection)
                st.success("Regra adicionada ao carrinho!")
        continue

    # Dual guard proposals: full chart + backtest
    metric_label = "Mean" if "mean" in proposal.rule_type.value else "StdDev"
    st.subheader(f"{metric_label} — {selected_col}")

    # --- Plotly chart ---
    values = proposal.history_values
    dates = proposal.history_dates

    if values and dates:
        from core.statistical_engine import compute_dynamic_band, compute_margin_band, _filter_valid

        valid_vals = _filter_valid(values)
        try:
            sigma_band = compute_dynamic_band(valid_vals, n_periods, n_sigma)
            margin_band = compute_margin_band(valid_vals, n_periods, margin_pct)
        except ValueError:
            sigma_band = {"lower": 0, "upper": 0, "center": 0}
            margin_band = {"lower": 0, "upper": 0, "center": 0}

        fig = go.Figure()

        # Historic values
        fig.add_trace(go.Scatter(
            x=dates, y=values,
            mode="lines+markers",
            name=f"{metric_label} historico",
            line=dict(color="royalblue", width=2),
            marker=dict(size=4),
        ))

        # Sigma band (light blue)
        fig.add_hrect(
            y0=sigma_band["lower"], y1=sigma_band["upper"],
            fillcolor="lightblue", opacity=0.3,
            line_width=0,
            annotation_text=f"{n_sigma}σ band",
            annotation_position="top left",
        )

        # Margin band (light green)
        fig.add_hrect(
            y0=margin_band["lower"], y1=margin_band["upper"],
            fillcolor="lightgreen", opacity=0.2,
            line_width=0,
            annotation_text=f"{margin_pct*100:.0f}% margin",
            annotation_position="bottom left",
        )

        # Center line
        fig.add_hline(
            y=sigma_band["center"], line_dash="dash",
            line_color="gray", opacity=0.5,
        )

        fig.update_layout(
            height=400,
            margin=dict(l=50, r=20, t=30, b=30),
            xaxis_title="Periodo",
            yaxis_title=metric_label,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )

        st.plotly_chart(fig, use_container_width=True)

    # --- Backtest results ---
    bt = proposal.backtest
    if bt:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Cobertura", f"{bt.coverage_pct:.1f}%")
        with col2:
            st.metric("Falsos Positivos", f"~{bt.false_positive_proxy}")
        with col3:
            st.metric("Estabilidade", f"{bt.stability_score:.2f}")
        with col4:
            st.metric("Confianca", _confidence_badge(proposal.confidence))

        if bt.has_drift:
            st.warning("Tendencia detectada no historico.")
        if bt.outlier_periods:
            st.caption(f"Periodos outlier: {', '.join(bt.outlier_periods[:5])}")

    # --- Warnings ---
    if proposal.warnings:
        for w in proposal.warnings:
            st.caption(f"  {w}")

    # --- Syntax preview ---
    with st.expander("Sintaxe GDQ", expanded=False):
        st.code(proposal.gdq_syntax_preview)

    # --- Add to cart ---
    if st.button(
        f"Adicionar {metric_label} ao carrinho",
        key=f"cart_{proposal.id}",
        type="primary",
    ):
        selection = RuleSelection(
            proposal_id=proposal.id,
            proposal=proposal,
            final_gdq_syntax=proposal.gdq_syntax_preview,
        )
        st.session_state["rule_cart"].append(selection)
        st.success(f"Regra {metric_label} adicionada ao carrinho!")

    st.divider()

# Footer
st.caption(
    f"Carrinho: {len(st.session_state['rule_cart'])} regras. "
    "Va para a pagina **Review** para revisar e exportar."
)
