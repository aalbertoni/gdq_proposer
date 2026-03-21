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

from config import load_config
from core.models.baseline import BaselineStrategy
from core.models.enums import BaselineMethod, ConfidenceLevel, RuleType, SemanticType, get_rule_label
from core.models.rule_selection import RuleSelection
from core.backtest_analysis import analyze_backtest, summarize_backtest_analysis
from core.gdq_capability import capability_badge, capability_warning, is_experimental
from core.rule_explainer import explain_rule, explain_rule_detail, explain_regime_context, explain_trade_offs
from core.rule_scoring import evaluate_proposal
from core.series_regime import classify_series
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


def _filter_minimal(proposals: list) -> list:
    """Filtra propostas para modo minimo (se ativo)."""
    if not st.session_state.get("proposal_mode") == "Minimo":
        return proposals
    from core.rule_recommender import select_minimal_set
    return select_minimal_set(proposals)


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
        partition_format=config_dict.get("partition_format"),
        partition_is_integer=config_dict.get("partition_is_integer", False),
        date_column=config_dict["date_column"],
        date_expression=config_dict.get("date_expression"),
        lookback_value=config_dict["lookback_value"],
        grain_type=GrainType(config_dict.get("grain_type", "daily")),
        lookback_mode=LookbackMode(config_dict.get("lookback_mode", "last_n_periods")),
        base_filter_sql=config_dict.get("base_filter_sql"),
        unique_key_columns=config_dict.get("unique_key_columns", []),
        reference_date=config_dict.get("reference_date"),
    )


def _render_rule_params(rule_key: str, n_min: int = 5, n_max: int = 90, n_default: int = 20) -> tuple:
    """Renderiza controles de parametros inline.

    Returns:
        (n_periods, n_sigma, margin_pct, buffer, margin_enabled)
    """
    col1, col2, col3, col4, col5 = st.columns([3, 2, 1, 3, 2])
    with col1:
        n_periods = st.slider(
            "N (periodos):", min_value=n_min, max_value=n_max, value=n_default,
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
        height=300,
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

    # Backtest analysis insights (streaks, tail risk)
    if bt and bt.point_results:
        analysis = analyze_backtest(bt)
        summary = summarize_backtest_analysis(analysis)
        if summary:
            with st.expander("Analise do backtest", expanded=False):
                st.markdown(summary)

    if proposal.warnings:
        for w in proposal.warnings:
            st.caption(f"  {w}")


def _render_regime_panel(profile):
    """Renderiza painel compacto do regime detectado."""
    if profile is None or (profile.regime.value == "stable" and not profile.secondary_regimes):
        return

    regime_badges = {
        "stable": ":green[estavel]",
        "volatile": ":orange[volatil]",
        "trending": ":orange[tendencia]",
        "seasonal": ":blue[sazonal]",
        "structural_break": ":red[mudanca de regime]",
        "zero_inflated": ":orange[zero-inflated]",
        "asymmetric": ":orange[assimetrica]",
        "sparse": ":red[esparsa]",
    }
    badge = regime_badges.get(profile.regime.value, profile.regime.value)
    secondary = ""
    if profile.secondary_regimes:
        sec_labels = [regime_badges.get(r.value, r.value) for r in profile.secondary_regimes]
        secondary = " + " + " + ".join(sec_labels)

    st.caption(f"Regime da serie: {badge}{secondary}")


def _render_add_to_cart(proposal, label, stable_key, show_syntax=True, profile=None, fp=""):
    """Renderiza badge de categoria, sintaxe e botao de adicionar ao carrinho."""
    from core.rule_recommender import category_badge as _cat_badge
    from core.models.enums import ProposalCategory
    # Namespace widget keys com fingerprint
    _wk = f"{fp}_{stable_key}" if fp else stable_key

    # Unified category badge (replaces dual tier + capability badges)
    cat = getattr(proposal, "proposal_category", ProposalCategory.STRONG)
    st.caption(_cat_badge(proposal))

    reasons = getattr(proposal, "recommendation_reasons", [])
    if cat in (ProposalCategory.NOT_RECOMMENDED, ProposalCategory.EXPERIMENTAL):
        warning_text = capability_warning(proposal.rule_type)
        if warning_text:
            st.warning(warning_text)
    if cat == ProposalCategory.NOT_RECOMMENDED and reasons:
        st.caption(f"Motivo: {'; '.join(reasons)}")

    if show_syntax:
        with st.expander("Sintaxe GDQ e detalhes", expanded=False):
            st.code(proposal.gdq_syntax_preview)
            st.info(explain_rule(proposal))
            detail = explain_rule_detail(proposal)
            if detail.strip():
                st.markdown(detail)

            # Regime context and trade-offs
            if profile is not None:
                regime_ctx = explain_regime_context(proposal, profile)
                if regime_ctx:
                    st.markdown("---")
                    st.markdown(regime_ctx)

                ev = evaluate_proposal(proposal, profile=profile)
                trade_off_text = explain_trade_offs(proposal, ev)
                if trade_off_text:
                    st.markdown("---")
                    st.markdown(trade_off_text)

    existing_ids = {s.proposal_id for s in st.session_state["rule_cart"]}
    if proposal.id in existing_ids:
        st.success(f"Regra {label} ja esta no carrinho.")
    elif st.button(
        f"Adicionar {label} ao carrinho",
        key=f"cart_{_wk}",
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


def _update_col_health(column: str, rule_key: str, confidence: ConfidenceLevel) -> None:
    """Store proposal confidence in a summary dict for the Resumo tab.

    Args:
        column: Column name (or "__table__" for table-level rules).
        rule_key: Short key identifying the rule type (e.g. "mean", "stddev",
                  "completeness", "allowed_values", "frequency", "distinct_count",
                  "rowcount", "pk").
        confidence: The ConfidenceLevel of the proposal.
    """
    health_key = "col_health"
    if health_key not in st.session_state:
        st.session_state[health_key] = {}
    if column not in st.session_state[health_key]:
        st.session_state[health_key][column] = {}
    st.session_state[health_key][column][rule_key] = confidence


def _render_diagnostics_panel(proposal):
    """Painel consolidado de ferramentas de apoio a calibragem.

    Agrupa sazonalidade, change-point, IQR/MAD e cobertura ponderada
    em um unico expander com explicacoes claras sobre o que cada item
    faz e se impacta ou nao a regra gerada.
    """
    if not proposal:
        return

    # Collect diagnostics
    has_seasonality = (
        proposal.seasonality_info
        and proposal.seasonality_info.get("has_seasonality")
    )
    has_change_point = (
        proposal.change_point_info
        and proposal.change_point_info.get("has_change_point")
    )
    has_outliers = (
        proposal.robust_info
        and proposal.robust_info.get("outliers", {}).get("n_outliers", 0) > 0
    )
    has_weighted_cov = (
        proposal.backtest
        and hasattr(proposal.backtest, "weighted_coverage_pct")
        and abs(proposal.backtest.weighted_coverage_pct - proposal.backtest.coverage_pct) > 1.0
    )

    n_findings = sum([
        bool(has_seasonality),
        bool(has_change_point),
        bool(has_outliers),
        bool(has_weighted_cov),
    ])

    if n_findings == 0:
        return

    # Build label
    tags = []
    if has_change_point:
        tags.append("change-point")
    if has_seasonality:
        tags.append("sazonalidade")
    if has_outliers:
        tags.append("outliers")
    if has_weighted_cov:
        tags.append("recencia")
    label = f"Diagnosticos de apoio a calibragem ({n_findings}): {', '.join(tags)}"

    with st.expander(label, expanded=n_findings >= 2):
        st.caption(
            "Estas ferramentas analisam o comportamento dos dados para ajudar "
            "na escolha dos parametros. Apenas o **Change-Point** altera o "
            "calculo da regra. Os demais sao **informativos**."
        )

        # ------ 1. Change-Point (IMPACTA a regra) ------
        if has_change_point:
            cp = proposal.change_point_info
            st.markdown("---")
            st.markdown("**Change-Point (Mudanca de Regime)** — :red[IMPACTA A REGRA]")
            st.caption(
                "Detecta mudancas bruscas de patamar na serie (ex: migracao de sistema). "
                "Usa o algoritmo CUSUM bilateral com threshold de 4 sigma."
            )
            n_post = len(cp.get("post_change_values", []))
            st.warning(
                f"Mudanca detectada em **{cp.get('change_date', '?')}**. "
                f"{cp.get('message', '')} "
                f"Os limites da regra foram calculados usando apenas os "
                f"**{n_post} periodos pos-mudanca** (dados do regime atual)."
            )
            st.caption(
                "Gabarito: a regra deve usar N <= periodos pos-mudanca. "
                f"Neste caso, N <= {n_post}."
            )

        # ------ 2. Sazonalidade (NAO impacta) ------
        if has_seasonality:
            info = proposal.seasonality_info
            st.markdown("---")
            st.markdown("**Sazonalidade Semanal** — :green[NAO IMPACTA A REGRA]")
            st.caption(
                "Detecta padroes repetitivos por dia da semana usando eta-squared "
                "(variancia entre grupos / variancia total). "
                "Positivo quando eta-squared > 15% e amplitude > 10% da media."
            )
            st.info(
                f"Forca: **{info['seasonality_strength']:.0%}** · "
                f"Amplitude: **{info['amplitude_ratio']:.0%}** da media. "
                f"{info['message']}"
            )
            st.caption(
                "Gabarito: use N multiplo de 7 (14, 21, 28, 35) para alinhar a "
                "janela com semanas completas e evitar vies. "
                "O auto-tune ja prioriza isso automaticamente (+0.02 no score)."
            )

        # ------ 3. Outliers / IQR / MAD (NAO impacta) ------
        if has_outliers:
            robust = proposal.robust_info
            outlier_info = robust.get("outliers", {})
            comparison = robust.get("iqr_vs_sigma", {})
            iqr_b = robust.get("iqr_band", {})
            mad_b = robust.get("mad_band", {})

            st.markdown("---")
            st.markdown("**Analise de Outliers (IQR/MAD)** — :green[NAO IMPACTA A REGRA]")
            st.caption(
                "Compara a banda classica (sigma) com bandas robustas (IQR de Tukey "
                "e MAD). Se a banda sigma for muito mais larga, outliers podem estar "
                "distorcendo o desvio padrao."
            )

            # Key metrics side by side
            oc1, oc2, oc3 = st.columns(3)
            with oc1:
                st.metric(
                    "Outliers",
                    f"{outlier_info['n_outliers']} ({outlier_info['pct_outliers']:.0%})",
                    help="Periodos com valores fora de [Q1 - 1.5*IQR, Q3 + 1.5*IQR].",
                )
            with oc2:
                sigma_w = comparison.get("sigma_width", 0)
                iqr_w = comparison.get("iqr_width", 0)
                ratio = sigma_w / iqr_w if iqr_w > 0 else 0
                st.metric(
                    "Sigma / IQR",
                    f"{ratio:.1f}x",
                    help="Razao entre largura da banda sigma e largura da banda IQR. "
                         "Acima de 2x indica distorcao por outliers.",
                )
            with oc3:
                rec = comparison.get("recommendation", "classical")
                rec_labels = {
                    "classical": "Classica (OK)",
                    "robust_iqr": "Considerar IQR",
                    "robust_mad": "Considerar MAD",
                }
                st.metric(
                    "Recomendacao",
                    rec_labels.get(rec, rec),
                    help="'Classica (OK)' = banda sigma adequada. "
                         "'Considerar IQR' = sigma inflada, aumentar K ou margem. "
                         "'Considerar MAD' = distorcao severa.",
                )

            if iqr_b and mad_b:
                st.caption(
                    f"Banda IQR: [{iqr_b['lower']:.2f}, {iqr_b['upper']:.2f}] · "
                    f"Banda MAD: [{mad_b['lower']:.2f}, {mad_b['upper']:.2f}]"
                )

            if rec != "classical":
                st.caption(
                    "Gabarito: aumente sigma (K) de 2 para 2.5 ou 3, ou aumente "
                    "a margem % para compensar a distorcao causada pelos outliers."
                )
            else:
                st.caption(
                    "Gabarito: banda classica (sigma) esta adequada. "
                    "Os outliers nao distorcem significativamente os limites."
                )

        # ------ 4. Cobertura Ponderada (NAO impacta) ------
        if has_weighted_cov:
            bt = proposal.backtest
            st.markdown("---")
            st.markdown("**Cobertura Ponderada (Recencia)** — :green[NAO IMPACTA A REGRA]")
            st.caption(
                "Atribui mais peso aos periodos recentes no backtest "
                "(meia-vida ~14 periodos, decaimento exponencial). "
                "Compara com a cobertura classica para indicar tendencia."
            )
            wc1, wc2 = st.columns(2)
            with wc1:
                st.metric(
                    "Cobertura classica",
                    f"{bt.coverage_pct:.1f}%",
                    help="Todos os periodos com peso igual.",
                )
            with wc2:
                delta = bt.weighted_coverage_pct - bt.coverage_pct
                st.metric(
                    "Cobertura recente",
                    f"{bt.weighted_coverage_pct:.1f}%",
                    delta=f"{delta:+.1f}pp",
                    delta_color="normal",
                    help="Periodos recentes pesam mais. "
                         "Delta positivo = regra funciona melhor recentemente.",
                )
            if bt.weighted_coverage_pct > bt.coverage_pct:
                st.caption(
                    "Gabarito: periodos recentes mais estaveis — bom sinal "
                    "para producao. A regra tende a funcionar bem daqui pra frente."
                )
            else:
                st.caption(
                    "Gabarito: periodos recentes menos estaveis — sinal de "
                    "atencao. Considere reduzir N para focar em dados mais recentes "
                    "ou investigar o que mudou."
                )


def _render_auto_tune(proposal_svc, values, dates, rule_key, metric_kind="numeric"):
    """Renderiza botao de auto-tuning, exibe resultado com justificativa e aplica parametros.

    Alem de mostrar os parametros recomendados, exibe um breakdown detalhado
    do score composto e uma comparacao antes/depois quando possivel.
    """
    cache_key = f"autotune_{rule_key}"

    # Captura parametros atuais dos sliders para comparacao antes/depois
    current_n = st.session_state.get(f"n_{rule_key}")
    current_k = st.session_state.get(f"k_{rule_key}")
    current_margin_pct_int = st.session_state.get(f"margin_{rule_key}")
    current_margin_on = st.session_state.get(f"margin_on_{rule_key}")

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
            # Captura tambem o backtest com parametros atuais para comparacao
            current_snapshot = None
            if current_n is not None and current_k is not None:
                try:
                    current_margin = (current_margin_pct_int or 10) / 100.0
                    current_margin_enabled = current_margin_on if current_margin_on is not None else True
                    current_snapshot = proposal_svc.find_best_params(
                        values=values, dates=dates, metric_kind=metric_kind,
                        n_range=[current_n],
                        sigma_range=[current_k],
                        margin_range=[current_margin],
                    )
                except Exception:
                    current_snapshot = None
            st.session_state[cache_key] = result
            st.session_state[f"{cache_key}_before"] = current_snapshot

    if cache_key in st.session_state:
        result = st.session_state[cache_key]
        before = st.session_state.get(f"{cache_key}_before")
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

        # -- Metricas-chave em colunas --
        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
        with m_c1:
            cov_delta = None
            if before and before.get("coverage_pct", 0) > 0:
                cov_delta = f"{result['coverage_pct'] - before['coverage_pct']:+.1f}%"
            st.metric(
                "Cobertura",
                f"{result['coverage_pct']:.1f}%",
                delta=cov_delta,
                help="Porcentagem de periodos historicos que passariam na regra com os parametros sugeridos.",
            )
        with m_c2:
            fp_delta = None
            if before and "false_positives" in before:
                fp_diff = result["false_positives"] - before["false_positives"]
                if fp_diff != 0:
                    fp_delta = f"{fp_diff:+d}"
            st.metric(
                "Falsos Positivos",
                f"~{result['false_positives']}",
                delta=fp_delta,
                delta_color="inverse",
                help="Estimativa de periodos normais que seriam reprovados indevidamente.",
            )
        with m_c3:
            score_delta = None
            if before and before.get("score_total", 0) > 0:
                score_delta = f"{result['score_total'] - before['score_total']:+.4f}"
            st.metric(
                "Score Total",
                f"{result['score_total']:.4f}",
                delta=score_delta,
                help="Score composto do grid search. Maior = melhor. "
                     "Combina cobertura, FP, estabilidade, largura da banda e drift.",
            )
        with m_c4:
            st.metric(
                "Confianca",
                badge,
                help="HIGH = recomendada, MEDIUM = revisar, LOW = nao recomendada.",
            )

        # -- Parametros recomendados --
        p_c1, p_c2, p_c3, p_c4 = st.columns(4)
        with p_c1:
            st.caption(f"**N:** {result['n_periods']} periodos")
        with p_c2:
            st.caption(f"**Sigma:** {result['n_sigma']}")
        with p_c3:
            st.caption(f"**Margem:** {result['margin_pct']*100:.0f}%")
        with p_c4:
            st.caption(f"**Margem:** {'ativada' if result['margin_enabled'] else 'desativada'}")

        # -- Expander com detalhes do score e comparacao --
        with st.expander("Detalhes do auto-tune", expanded=False):
            # Score breakdown table
            st.markdown("**Decomposicao do Score**")
            st.caption(
                "O score total e a soma dos componentes abaixo. "
                "Valores positivos contribuem, negativos penalizam."
            )

            breakdown_items = [
                ("Cobertura normal", result.get("normal_coverage", 0), "+", "pontos normais cobertos / total normais"),
                ("Penalidade outliers", result.get("outlier_penalty", 0), "-", "outliers cobertos * 0.15"),
                ("Penalidade FP", result.get("fp_penalty", 0), "-", "FP * 0.05"),
                ("Bonus estabilidade", result.get("stability_bonus", 0), "+", "stability * 0.10"),
                ("Penalidade largura", result.get("width_penalty", 0), "-", "(width_ratio - 0.20)^2 * 0.5"),
                ("Bonus/penalidade drift", result.get("drift_bonus", 0), "+/-", "+0.05 sem drift, -0.05 com drift"),
                ("Penalidade N curto", result.get("n_penalty", 0), "-", "0.05 se N < 15"),
                ("Preferencia sigma", result.get("sigma_preference", 0), "-", "sigma * 0.02"),
                ("Preferencia margem", result.get("margin_preference", 0), "-", "margem * 0.10"),
                ("Bonus recencia", result.get("recency_bonus", 0), "+", "(weighted_cov - flat_cov)/100 * 0.10"),
            ]

            # Build markdown table
            md_rows = ["| Componente | Valor | Sinal | Formula |", "|---|---|---|---|"]
            for name, value, sign, formula in breakdown_items:
                if sign == "-" and value > 0:
                    md_rows.append(f"| {name} | :red[-{value:.4f}] | {sign} | `{formula}` |")
                elif sign == "+/-":
                    if value >= 0:
                        md_rows.append(f"| {name} | :green[+{value:.4f}] | {sign} | `{formula}` |")
                    else:
                        md_rows.append(f"| {name} | :red[{value:.4f}] | {sign} | `{formula}` |")
                else:
                    md_rows.append(f"| {name} | :green[+{value:.4f}] | {sign} | `{formula}` |")
            md_rows.append(f"| **Score Total** | **{result['score_total']:.4f}** | = | soma |")
            st.markdown("\n".join(md_rows))

            # Largura da banda
            bwr = result.get("band_width_ratio", 0)
            if bwr > 0:
                st.caption(
                    f"Largura relativa da banda: {bwr:.4f} "
                    f"({'estreita' if bwr < 0.2 else 'moderada' if bwr < 0.5 else 'larga'}). "
                    f"Penalidade quadratica quando > 0.20."
                )
            n_outliers = result.get("outliers_detected", 0)
            if n_outliers > 0:
                n_covered = result.get("outliers_covered", 0)
                st.caption(
                    f"Outliers detectados (IQR 2.5x): {n_outliers}, "
                    f"excluidos da banda: {n_outliers - n_covered}."
                )

            # Weighted coverage insight
            weighted_cov = result.get("weighted_coverage_pct", 0)
            flat_cov = result.get("coverage_pct", 0)
            if abs(weighted_cov - flat_cov) > 1.0:
                if weighted_cov > flat_cov:
                    st.caption(
                        f":green[Cobertura recente ({weighted_cov:.1f}%) e melhor que historica ({flat_cov:.1f}%).] "
                        f"Os periodos mais recentes estao mais estaveis."
                    )
                else:
                    st.caption(
                        f":orange[Cobertura recente ({weighted_cov:.1f}%) e pior que historica ({flat_cov:.1f}%).] "
                        f"Os periodos mais recentes estao mais instaveis."
                    )

            # Comparacao antes vs depois
            if before and before.get("score_total", 0) > 0:
                st.divider()
                st.markdown("**Comparacao: parametros atuais vs sugeridos**")

                cmp_c1, cmp_c2 = st.columns(2)
                with cmp_c1:
                    st.markdown("**Antes** (parametros atuais)")
                    st.caption(
                        f"N={before['n_periods']}, "
                        f"sigma={before['n_sigma']}, "
                        f"margem={before['margin_pct']*100:.0f}%"
                        f"{' (ativada)' if before['margin_enabled'] else ' (desativada)'}"
                    )
                    st.caption(
                        f"Cobertura: {before['coverage_pct']:.1f}% | "
                        f"FP: ~{before['false_positives']} | "
                        f"Score: {before['score_total']:.4f}"
                    )
                with cmp_c2:
                    st.markdown("**Depois** (parametros sugeridos)")
                    st.caption(
                        f"N={result['n_periods']}, "
                        f"sigma={result['n_sigma']}, "
                        f"margem={result['margin_pct']*100:.0f}%"
                        f"{' (ativada)' if result['margin_enabled'] else ' (desativada)'}"
                    )
                    st.caption(
                        f"Cobertura: {result['coverage_pct']:.1f}% | "
                        f"FP: ~{result['false_positives']} | "
                        f"Score: {result['score_total']:.4f}"
                    )

                # Highlight improvements
                improvements = []
                cov_diff = result["coverage_pct"] - before["coverage_pct"]
                fp_diff = result["false_positives"] - before["false_positives"]
                score_diff = result["score_total"] - before["score_total"]

                if cov_diff > 0:
                    improvements.append(f"cobertura +{cov_diff:.1f}pp")
                if fp_diff < 0:
                    improvements.append(f"FP {fp_diff:+d}")
                if score_diff > 0:
                    improvements.append(f"score +{score_diff:.4f}")

                if improvements:
                    st.caption(f"Ganhos: {', '.join(improvements)}")
                elif score_diff == 0 and cov_diff == 0:
                    st.caption("Os parametros atuais ja sao otimos para esta metrica.")

        # Botao para aplicar parametros sugeridos nos sliders.
        # Armazena em _pending_autotune para aplicar ANTES dos widgets no proximo rerun.
        if result["viable"] and st.button(
            "Aplicar parametros sugeridos",
            key=f"apply_autotune_{rule_key}",
            help="Atualiza os sliders com os parametros recomendados.",
        ):
            st.session_state["_pending_autotune"] = {
                "rule_key": rule_key,
                "n_periods": result["n_periods"],
                "n_sigma": result["n_sigma"],
                "margin_pct": int(result["margin_pct"] * 100),
                "margin_enabled": result["margin_enabled"],
            }
            st.rerun()


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Explore - GDQ Rule Proposer", page_icon=":bar_chart:", layout="wide")

# Aplicar auto-tune pendente ANTES de qualquer widget ser criado
_pending = st.session_state.pop("_pending_autotune", None)
if _pending:
    rk = _pending["rule_key"]
    st.session_state[f"n_{rk}"] = _pending["n_periods"]
    st.session_state[f"k_{rk}"] = _pending["n_sigma"]
    st.session_state[f"margin_{rk}"] = _pending["margin_pct"]
    st.session_state[f"margin_on_{rk}"] = _pending["margin_enabled"]
    # Limpar cache de proposals que dependem destes params
    for k in [k for k in list(st.session_state.keys()) if k.startswith("proposal_") and rk in k]:
        del st.session_state[k]

st.title("Calibracao de Regras")
st.caption(
    "Ajuste os parametros de cada regra e visualize o impacto no historico. "
    "Adicione as regras aprovadas ao carrinho para exportar na pagina Review."
)

# Guard: precisa ter passado pelo setup
if "dataset_config" not in st.session_state:
    st.warning("Configure a tabela na pagina **Setup** primeiro.")
    if st.button("Ir para Setup", key="goto_setup_config"):
        st.switch_page("pages/01_setup.py")
    st.stop()

if "column_profiles" not in st.session_state:
    st.warning("Execute o profiling na pagina **Setup** primeiro.")
    if st.button("Ir para Setup", key="goto_setup_profile"):
        st.switch_page("pages/01_setup.py")
    st.stop()

dataset_config = st.session_state["dataset_config"]
profiles = st.session_state["column_profiles"]

# Fingerprint para namespace de widgets e cache keys
_fp = dataset_config.analysis_fingerprint()[:6]

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

# --- Config summary com lookback ajustavel ---
_setup_lookback = dataset_config.lookback_value

cfg_c1, cfg_c2, cfg_c3, cfg_c4 = st.columns([3, 2, 2, 2])
with cfg_c1:
    st.markdown(
        f"**Tabela:** `{dataset_config.schema}.{dataset_config.table}` — "
        f"{len(selected_set)} colunas ({len(numeric_profiles)} num, {len(cat_profiles)} cat)"
    )
with cfg_c2:
    st.markdown(f"**Data:** `{dataset_config.date_expression or dataset_config.date_column}`")
with cfg_c3:
    st.markdown(f"**Particao:** {dataset_config.partition_method.value}")
with cfg_c4:
    effective_lookback = st.number_input(
        "Lookback (periodos):",
        min_value=5,
        max_value=365,
        value=_setup_lookback,
        step=5,
        key="explore_lookback",
        help="Ajuste o periodo de historico sem voltar ao Setup. "
             "Mais periodos = mais dados para calibrar, mas queries mais caras.",
    )

if effective_lookback != _setup_lookback:
    st.caption(
        f"Lookback ajustado de {_setup_lookback} para **{effective_lookback}** periodos. "
        "Os graficos e propostas usarao o novo valor."
    )

with st.expander("Detalhes da configuracao", expanded=False):
    if dataset_config.base_filter_sql:
        st.caption(f"Filtro: `{dataset_config.base_filter_sql}`")

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
# Services (antes do sidebar para que client esteja disponivel)
# ---------------------------------------------------------------------------

try:
    client = _get_client()
except Exception as e:
    st.error(f"Falha na conexao: {e}")
    st.stop()

# --- Cost guardrail check ---
from infra.cost_guard import CostGuardrailTriggered

def _handle_cost_guardrail(e: CostGuardrailTriggered):
    """Exibe UI de bloqueio por custo com opcao de bypass."""
    st.error(
        f"Custo acumulado da sessao: **${e.cost_usd:.4f}** "
        f"(limiar: ${e.threshold_usd:.2f})"
    )
    _qs = client.logger.get_session_summary()
    st.caption(
        f"{_qs['total_queries']} queries · "
        f"{_qs['total_elapsed_ms'] / 1000:.1f}s · "
        f"${_qs['estimated_cost_usd']:.4f}"
    )
    # Ultimas queries
    with st.expander("Queries da sessao"):
        for _e in reversed(client.logger.entries[-10:]):
            _bs = _e.bytes_scanned or 0
            _cost = _e.estimated_cost_usd
            st.caption(
                f"**{_e.query_name}** — {_e.rows_returned} rows, "
                f"{_bs:,} bytes, ${_cost:.6f}"
            )
    if st.button(
        "Entendo o custo. Continuar executando queries.",
        type="primary",
        key="cost_guardrail_bypass",
    ):
        client.bypass_cost_guardrail()
        st.rerun()
    st.stop()

# Verificar se custo ja foi excedido antes de qualquer query
try:
    client._check_cost_guardrail("explore_page_load")
except CostGuardrailTriggered as e:
    _handle_cost_guardrail(e)

analysis_svc = _get_analysis_service(client)
proposal_svc = _get_proposal_service()
proposal_svc.set_grain_policy(dataset_config.grain_policy)

_grain_policy = dataset_config.grain_policy

config_dict = {
    "schema": dataset_config.schema,
    "table": dataset_config.table,
    "partition_method": dataset_config.partition_method.value,
    "partition_column": dataset_config.partition_column,
    "partition_format": dataset_config.partition_format,
    "partition_is_integer": dataset_config.partition_is_integer,
    "date_column": dataset_config.date_column,
    "date_expression": dataset_config.date_expression,
    "lookback_value": effective_lookback,
    "grain_type": dataset_config.grain_type.value,
    "lookback_mode": dataset_config.lookback_mode.value,
    "base_filter_sql": dataset_config.base_filter_sql,
    "unique_key_columns": getattr(dataset_config, "unique_key_columns", []),
    "reference_date": dataset_config.reference_date,
}


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

    # --- Navegacao rapida entre colunas ---
    _col_health = st.session_state.get("col_health", {})
    _cart_cols = {
        sel.proposal.target_column
        for sel in st.session_state.get("rule_cart", [])
        if sel.proposal.target_column
    }
    _all_cols = [p.column_name for p in numeric_profiles] + [p.column_name for p in cat_profiles]
    if _all_cols:
        st.divider()
        st.caption("**Colunas**")
        for _cn in _all_cols:
            _has_health = _cn in _col_health
            _in_cart = _cn in _cart_cols
            if _in_cart:
                _icon = ":green[●]"
            elif _has_health:
                _icon = ":blue[○]"
            else:
                _icon = "·"
            st.caption(f"{_icon} `{_cn}`")

    st.divider()

    cart_count = len(st.session_state["rule_cart"])
    if cart_count > 0:
        st.subheader(f"Carrinho ({cart_count})")
        for sel in st.session_state["rule_cart"]:
            p = sel.proposal
            target = p.target_column or "(tabela)"
            label = get_rule_label(p.rule_type)
            st.caption(f"- {label} `{target}`")
        if st.button("Ir para Review", type="primary", key="sidebar_review"):
            st.switch_page("pages/03_review.py")
    else:
        st.caption("Carrinho vazio.")

    st.divider()

    # Query summary (compact)
    _qs = client.logger.get_session_summary()
    if _qs["total_queries"] > 0:
        _time_s = _qs["total_elapsed_ms"] / 1000
        _cost = _qs["estimated_cost_usd"]
        _err_label = f" · :red[{_qs['errors']} erros]" if _qs["errors"] > 0 else ""
        st.caption(f"{_qs['total_queries']} queries · {_time_s:.1f}s · ${_cost:.4f}{_err_label}")

        # Cost guardrail
        _app_cfg = st.session_state.get("config")
        _threshold = _app_cfg.athena.cost_warning_threshold_usd if _app_cfg else 0.50
        if _cost > _threshold:
            st.warning(f"Custo (${_cost:.4f}) excedeu ${_threshold:.2f}.")

        with st.expander("Log de queries"):
            _entries = client.logger.entries
            if _entries:
                for _e in reversed(_entries[-10:]):
                    _status = ":red[ERRO]" if _e.exception_type else ":green[OK]"
                    _col_label = f".{_e.column}" if _e.column else ""
                    st.caption(
                        f"{_status} **{_e.query_name}**{_col_label} "
                        f"— {_e.rows_returned} rows, {_e.elapsed_ms}ms"
                    )
            st.download_button(
                label="Exportar log (JSON)",
                data=client.logger.export_json(),
                file_name="gdq_query_log.json",
                mime="application/json",
                key="sidebar_export_log",
            )

    st.divider()
    if st.button("Voltar ao Setup", key="sidebar_back_setup"):
        st.switch_page("pages/01_setup.py")


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


@st.cache_data(ttl=900, show_spinner="Consultando historico de distintos...")
def fetch_distinct_count_history(_config_dict, column):
    config = _build_config_from_dict(_config_dict)
    return analysis_svc.get_distinct_count_history(config, column)


@st.cache_data(ttl=900, show_spinner="Consultando historico de unicidade...")
def fetch_uniqueness_history(_config_dict, _key_columns_tuple):
    """Busca historico de unicidade para colunas de chave primaria.

    Args:
        _config_dict: Dict com configuracao da tabela (hashable para cache).
        _key_columns_tuple: Tuple com nomes das colunas-chave (hashable para cache).

    Returns:
        DataFrame com colunas [period, total_rows, distinct_keys,
        duplicate_count, non_null_{col}...].
    """
    config = _build_config_from_dict(_config_dict)
    # Convert tuple back to list (tuples are hashable for cache key)
    return analysis_svc.get_uniqueness_history(config, list(_key_columns_tuple))


# ---------------------------------------------------------------------------
# Modo de proposta (Completo vs Minimo)
# ---------------------------------------------------------------------------

proposal_mode = st.radio(
    "Modo de proposta",
    options=["Completo", "Minimo"],
    index=0,
    horizontal=True,
    help=(
        "**Completo:** todas as regras propostas. "
        "**Minimo:** apenas regras essenciais de alta confianca "
        "(RowCount, PrimaryKey, Completeness, AllowedValues, Mean)."
    ),
)
st.session_state["proposal_mode"] = proposal_mode
_is_minimal_mode = proposal_mode == "Minimo"

# ---------------------------------------------------------------------------
# Colunas excluidas (motivos de nao-recomendacao)
# ---------------------------------------------------------------------------

from core.rule_recommender import explain_column_exclusions

_selected_profiles = [p for p in profiles if p.column_name in selected_set]
_exclusions = explain_column_exclusions(_selected_profiles)

# ---------------------------------------------------------------------------
# Resumo executivo (acima das tabs)
# ---------------------------------------------------------------------------

from core.analysis_summary import build_analysis_summary
from core.rule_recommender import CATEGORY_BADGES

def _collect_all_proposals() -> list:
    """Coleta todas as propostas cacheadas no session_state."""
    from core.models.rule_proposal import RuleProposal
    _PROPOSAL_PREFIXES = ("proposal_mean_", "proposal_stddev_", "proposal_comp_",
                          "proposal_pct_", "proposal_rc_", "proposal_pk_",
                          "cat_proposals_")
    all_props = []
    for key, val in st.session_state.items():
        if not isinstance(key, str):
            continue
        if any(key.startswith(p) for p in _PROPOSAL_PREFIXES):
            if isinstance(val, list) and val and isinstance(val[0], RuleProposal):
                all_props.extend(val)
    return all_props


def _collect_series_profiles() -> dict:
    """Coleta SeriesProfiles do session_state."""
    return {
        k: v for k, v in st.session_state.items()
        if isinstance(k, str) and k.startswith("series_profile_")
    }


_all_proposals = _collect_all_proposals()
_cart = st.session_state.get("rule_cart", [])
_col_health = st.session_state.get("col_health", {})
_series_profiles = _collect_series_profiles()

_summary = build_analysis_summary(
    profiles=_selected_profiles,
    all_proposals=_all_proposals,
    cart=_cart,
    col_health=_col_health,
    series_profiles=_series_profiles,
    exclusions=_exclusions,
)

# --- Resumo compacto (1 linha) ---
_cov_label = f" · Cobertura media {_summary.avg_coverage:.0f}%" if _summary.avg_coverage > 0 else ""
st.caption(
    f"**{_summary.total_columns}** colunas · "
    f"**{_summary.columns_with_proposals}** com proposta · "
    f"**{_summary.rules_in_cart}** regras no carrinho"
    f"{_cov_label}"
)

# --- Alertas inline (apenas se houver) ---
_alerts = []
if _summary.experimental_in_cart > 0:
    _alerts.append(f"{_summary.experimental_in_cart} experimental(is) no carrinho")
if _summary.low_coverage_rules > 0:
    _alerts.append(f"{_summary.low_coverage_rules} com cobertura < 80%")
for _regime, _cols in _summary.problematic_regimes.items():
    _alerts.append(f"Regime {_regime}: {', '.join(_cols)}")
if _alerts:
    st.warning(" · ".join(_alerts))

# --- Detalhes (expander colapsado) ---
from core.models.enums import SEMANTIC_TYPE_LABELS as _STYPE_MAP
_STYPE_LABELS = {st.value: label for st, label in _STYPE_MAP.items()}
_CAT_INLINE_BADGES = {
    "strong": ":green[Forte]", "conservative": ":blue[Conservadora]",
    "experimental": ":orange[Experimental]", "needs_review": ":orange[Revisar]",
    "not_recommended": ":red[N/R]",
}
_has_details = bool(
    _summary.by_semantic_type or _summary.by_proposal_category or _exclusions
)
if _has_details:
    with st.expander("Detalhes da analise", expanded=False):
        _dc1, _dc2 = st.columns(2)
        with _dc1:
            _parts = [
                f"{_STYPE_LABELS.get(k, k)} ({v})"
                for k, v in sorted(_summary.by_semantic_type.items(), key=lambda x: -x[1])
            ]
            if _parts:
                st.caption("**Tipos:** " + " · ".join(_parts))
        with _dc2:
            _cat_parts = [
                f"{_CAT_INLINE_BADGES.get(k, k)} ({v})"
                for k, v in sorted(_summary.by_proposal_category.items(), key=lambda x: -x[1])
                if v > 0
            ]
            if _cat_parts:
                st.caption("**Propostas:** " + " · ".join(_cat_parts))
        if _exclusions:
            st.markdown("---")
            st.caption(f"**Colunas sem regras ({len(_exclusions)}):**")
            for exc in _exclusions:
                st.caption(f"- **{exc.column_name}** ({_STYPE_LABELS.get(exc.semantic_type.value, exc.semantic_type.value)}): {exc.reason}")

# ---------------------------------------------------------------------------
# Calibracao em lote (acima das tabs para visibilidade)
# ---------------------------------------------------------------------------

if numeric_profiles:
    with st.expander("Calibracao em lote (auto-tune)", expanded=False):
        st.caption(
            "Executa auto-tune em todas as colunas numericas e adiciona "
            "regras de alta confianca ao carrinho automaticamente."
        )

        _batch_min = st.selectbox(
            "Confianca minima",
            options=["HIGH", "MEDIUM"],
            index=0,
            key="batch_min_confidence_top",
            help="HIGH: apenas regras muito confiaveis. MEDIUM: inclui regras que precisam revisao.",
        )

        if st.button("Auto-calibrar todas", key="btn_batch_calibrate_top", type="primary"):
            _batch_cols = [p.column_name for p in numeric_profiles]
            if not _batch_cols:
                st.warning("Nenhuma coluna numerica encontrada.")
            else:
                _batch_progress = st.progress(0, text="Iniciando...")
                _batch_results = []

                for _bi, _bc in enumerate(_batch_cols):
                    _batch_progress.progress(
                        (_bi + 1) / len(_batch_cols),
                        text=f"Analisando {_bc} ({_bi + 1}/{len(_batch_cols)})...",
                    )
                    try:
                        _bh = fetch_numeric_history(config_dict, _bc)
                        if _bh.empty or len(_bh) < _grain_policy.batch_min_periods:
                            _batch_results.append({"column": _bc, "status": "skip", "reason": "dados insuficientes"})
                            continue

                        _bvals = _bh["mean"].tolist()
                        _bdates = _bh["period"].astype(str).tolist()
                        _b_n_range = [n for n in _grain_policy.n_range if n <= len(_bvals) - _grain_policy.min_history]
                        _bbest = proposal_svc.find_best_params(
                            values=_bvals, dates=_bdates,
                            n_range=_b_n_range or [_grain_policy.slider_n_min],
                            seasonality_enabled=_grain_policy.seasonality_enabled,
                            n_penalty_threshold=_grain_policy.n_penalty_threshold,
                        )

                        if _bbest["confidence"].value == "LOW":
                            _batch_results.append({"column": _bc, "status": "skip", "reason": "confianca LOW"})
                            continue
                        if _batch_min == "HIGH" and _bbest["confidence"] != ConfidenceLevel.HIGH:
                            _batch_results.append({"column": _bc, "status": "skip", "reason": f"confianca {_bbest['confidence'].value}"})
                            continue

                        _bbl = BaselineStrategy(
                            n_periods=_bbest["n_periods"], n_sigma=_bbest["n_sigma"],
                            margin_pct=_bbest["margin_pct"], margin_enabled=_bbest["margin_enabled"],
                            min_history_points=_grain_policy.min_history,
                        )
                        _bprops = proposal_svc.propose_numeric_rules(
                            history=_bh, column=_bc,
                            table=config_dict.get("table", ""), baseline=_bbl,
                        )
                        _bcart = st.session_state.get("rule_cart", [])
                        _badded = 0
                        for _bp in _bprops:
                            if _bp.rule_type in (RuleType.MEAN_DUAL_GUARD, RuleType.STDDEV_DUAL_GUARD):
                                if not any(
                                    r.proposal.rule_type == _bp.rule_type
                                    and r.proposal.target_column == _bp.target_column
                                    for r in _bcart
                                ):
                                    _bcart.append(RuleSelection(
                                        proposal_id=_bp.id, proposal=_bp,
                                        final_gdq_syntax=_bp.gdq_syntax_preview,
                                    ))
                                    _badded += 1
                        st.session_state["rule_cart"] = _bcart
                        _batch_results.append({
                            "column": _bc, "status": "added" if _badded > 0 else "exists",
                            "confidence": _bbest["confidence"].value,
                            "coverage": _bbest["coverage_pct"],
                            "n": _bbest["n_periods"], "sigma": _bbest["n_sigma"],
                            "added": _badded,
                        })
                    except Exception as e:
                        _batch_results.append({"column": _bc, "status": "error", "reason": str(e)})

                _batch_progress.empty()
                _total_added = sum(r.get("added", 0) for r in _batch_results)
                if _total_added > 0:
                    st.success(f"{_total_added} regras adicionadas de {len(_batch_cols)} colunas.")
                with st.expander(f"Detalhes: {len(_batch_results)} colunas", expanded=_total_added > 0):
                    for _br in _batch_results:
                        if _br["status"] == "added":
                            st.caption(f":green[+{_br['added']}] **{_br['column']}** -- {_br['confidence']}, cob. {_br['coverage']:.1f}%")
                        elif _br["status"] == "exists":
                            st.caption(f":blue[=] **{_br['column']}** -- ja no carrinho")
                        elif _br["status"] == "skip":
                            st.caption(f":orange[-] **{_br['column']}** -- {_br['reason']}")
                        elif _br["status"] == "error":
                            st.caption(f":red[!] **{_br['column']}** -- erro: {_br['reason']}")

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
        st.info("Nenhuma coluna numerica selecionada.")
        if st.button("Selecionar colunas no Setup", key="goto_setup_num"):
            st.switch_page("pages/01_setup.py")
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
        except CostGuardrailTriggered as e:
            _handle_cost_guardrail(e)
        except Exception as e:
            st.error(f"Erro ao consultar historico: {e}")
            st.stop()

        if history_df.empty:
            st.warning(f"Nenhum dado historico encontrado para `{selected_col}`.")
        else:
            # Classify series regime once per column
            _mean_vals = history_df["mean"].tolist() if "mean" in history_df.columns else []
            _mean_dates = history_df["period"].astype(str).tolist() if "period" in history_df.columns else []
            _series_profile_key = f"series_profile_{selected_col}_{effective_lookback}"
            if _series_profile_key not in st.session_state and _mean_vals:
                st.session_state[_series_profile_key] = classify_series(_mean_vals, _mean_dates)
            series_profile = st.session_state.get(_series_profile_key)

            # Show regime badge
            _render_regime_panel(series_profile)

            # Auto-tune automatico na primeira visita a coluna
            _at_key = f"autotune_{_fp}_mean_{selected_col}"
            _at_min = _grain_policy.min_history + 1  # precisa de min_history + pelo menos 1 ponto
            if _at_key not in st.session_state and _mean_vals and len(_mean_vals) >= _at_min:
                _at_n_range = [n for n in _grain_policy.n_range if n <= len(_mean_vals) - _grain_policy.min_history]
                with st.spinner(f"Auto-tune {selected_col}..."):
                    _at_result = proposal_svc.find_best_params(
                        values=_mean_vals, dates=_mean_dates,
                        n_range=_at_n_range or [_grain_policy.slider_n_min],
                        seasonality_enabled=_grain_policy.seasonality_enabled,
                        n_penalty_threshold=_grain_policy.n_penalty_threshold,
                    )
                    st.session_state[_at_key] = _at_result
                    if _at_result["viable"]:
                        _rk = f"{_fp}_mean_{selected_col}"
                        st.session_state[f"n_{_rk}"] = _at_result["n_periods"]
                        st.session_state[f"k_{_rk}"] = _at_result["n_sigma"]
                        st.session_state[f"margin_{_rk}"] = int(_at_result["margin_pct"] * 100)
                        st.session_state[f"margin_on_{_rk}"] = _at_result["margin_enabled"]
                        # Tambem aplicar ao StdDev
                        _rk_std = f"{_fp}_stddev_{selected_col}"
                        st.session_state[f"n_{_rk_std}"] = _at_result["n_periods"]
                        st.session_state[f"k_{_rk_std}"] = _at_result["n_sigma"]
                        st.session_state[f"margin_{_rk_std}"] = int(_at_result["margin_pct"] * 100)
                        st.session_state[f"margin_on_{_rk_std}"] = _at_result["margin_enabled"]
                    st.rerun()

            _at_cached = st.session_state.get(_at_key)
            if _at_cached and _at_cached.get("viable"):
                st.caption(
                    f"Parametros sugeridos pelo auto-tune: "
                    f"N={_at_cached['n_periods']}, sigma={_at_cached['n_sigma']}, "
                    f"margem={_at_cached['margin_pct']*100:.0f}% — "
                    f"cobertura {_at_cached['coverage_pct']:.0f}%, "
                    f"{_confidence_badge(_at_cached['confidence'])}"
                )

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
                f"{_fp}_mean_{selected_col}",
                n_min=_grain_policy.slider_n_min, n_max=_grain_policy.slider_n_max,
                n_default=_grain_policy.slider_n_default,
            )

            mean_baseline = BaselineStrategy(
                method=BaselineMethod.LAST_N_PERIODS,
                n_periods=mean_n,
                n_sigma=mean_k,
                margin_pct=mean_margin,
                margin_enabled=mean_margin_on,
                min_history_points=_grain_policy.min_history,
            )

            mean_cache_key = f"proposal_mean_{selected_col}_{mean_n}_{mean_k}_{mean_margin}_{mean_margin_on}_{effective_lookback}"
            mean_proposals = _filter_minimal(_get_cached_proposals(
                mean_cache_key,
                lambda: [
                    p for p in proposal_svc.propose_numeric_rules(
                        history_df, selected_col, dataset_config.table, mean_baseline,
                    )
                    if "mean" in p.rule_type.value
                ],
            ))

            if mean_proposals:
                proposal = mean_proposals[0]
                _update_col_health(selected_col, "mean", proposal.confidence)
                values = proposal.history_values
                dates = proposal.history_dates

                if values and dates:
                    _render_rolling_chart(
                        values, dates, mean_n, mean_k, mean_margin, "Mean",
                        margin_enabled=mean_margin_on,
                    )

                    # Diagnostics panel (seasonality, change-point, outliers, recency)
                    _render_diagnostics_panel(proposal)

                    _render_auto_tune(
                        proposal_svc, values, dates,
                        f"{_fp}_mean_{selected_col}", metric_kind="numeric",
                    )

                # Metricas do backtest (ocultar se auto-tune ja exibe metricas)
                if f"autotune_{_fp}_mean_{selected_col}" not in st.session_state:
                    _render_backtest_metrics(proposal)
                _render_add_to_cart(
                    proposal, "Mean",
                    f"mean_{selected_col}",
                    profile=series_profile, fp=_fp,
                )

            st.divider()

            # ---- StdDev ----
            st.subheader(f"StdDev -- {selected_col}")

            std_n, std_k, std_margin, std_buffer, std_margin_on = _render_rule_params(
                f"{_fp}_stddev_{selected_col}",
                n_min=_grain_policy.slider_n_min, n_max=_grain_policy.slider_n_max,
                n_default=_grain_policy.slider_n_default,
            )

            std_baseline = BaselineStrategy(
                method=BaselineMethod.LAST_N_PERIODS,
                n_periods=std_n,
                n_sigma=std_k,
                margin_pct=std_margin,
                margin_enabled=std_margin_on,
                min_history_points=_grain_policy.min_history,
            )

            std_cache_key = f"proposal_stddev_{selected_col}_{std_n}_{std_k}_{std_margin}_{std_margin_on}_{effective_lookback}"
            std_proposals = _filter_minimal(_get_cached_proposals(
                std_cache_key,
                lambda: [
                    p for p in proposal_svc.propose_numeric_rules(
                        history_df, selected_col, dataset_config.table, std_baseline,
                    )
                    if "stddev" in p.rule_type.value
                ],
            ))

            if std_proposals:
                proposal = std_proposals[0]
                _update_col_health(selected_col, "stddev", proposal.confidence)
                values = proposal.history_values
                dates = proposal.history_dates

                if values and dates:
                    _render_rolling_chart(
                        values, dates, std_n, std_k, std_margin, "StdDev",
                        margin_enabled=std_margin_on,
                    )

                    # Diagnostics panel (outliers, recency — seasonality/change-point already shown in Mean)
                    _render_diagnostics_panel(proposal)

                    _render_auto_tune(
                        proposal_svc, values, dates,
                        f"{_fp}_stddev_{selected_col}", metric_kind="numeric",
                    )

                if f"autotune_{_fp}_stddev_{selected_col}" not in st.session_state:
                    _render_backtest_metrics(proposal)
                _render_add_to_cart(
                    proposal, "StdDev",
                    f"stddev_{selected_col}",
                    profile=series_profile,
                    fp=_fp,
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
                    f"{_fp}_pct_{selected_col}",
                    n_min=_grain_policy.slider_n_min, n_max=_grain_policy.slider_n_max,
                    n_default=_grain_policy.slider_n_default,
                )

                pct_baseline = BaselineStrategy(
                    method=BaselineMethod.LAST_N_PERIODS,
                    n_periods=pct_n,
                    n_sigma=pct_k,
                    margin_pct=pct_margin,
                    margin_enabled=pct_margin_on,
                    min_history_points=_grain_policy.min_history,
                )

                pct_levels = [pct_options[p] for p in selected_pcts]
                pct_cache_key = (
                    f"proposal_pct_{selected_col}_{pct_n}_{pct_k}_{pct_margin}"
                    f"_{pct_margin_on}_{'_'.join(pct_levels)}_{effective_lookback}"
                )
                pct_proposals = _get_cached_proposals(
                    pct_cache_key,
                    lambda: proposal_svc.propose_percentile_rules(
                        history_df, selected_col, dataset_config.table,
                        pct_baseline, percentile_levels=pct_levels,
                    ),
                )

                for pct_prop in pct_proposals:
                    _update_col_health(selected_col, f"pct_{pct_prop.metric_name}", pct_prop.confidence)
                    pct_label = pct_prop.metric_name.upper()
                    with st.expander(f"{pct_label} -- {selected_col}", expanded=len(pct_proposals) <= 2):
                        pct_vals = pct_prop.history_values
                        pct_dates = pct_prop.history_dates

                        if pct_vals and pct_dates:
                            _render_rolling_chart(
                                pct_vals, pct_dates, pct_n, pct_k, pct_margin,
                                pct_label, margin_enabled=pct_margin_on,
                            )

                        _render_backtest_metrics(pct_prop)
                        _render_add_to_cart(
                            pct_prop, f"Percentil {pct_label}",
                            f"pct_{selected_col}_{pct_prop.metric_name}",
                            profile=series_profile,
                            fp=_fp,
                        )

            st.divider()

            # ---- Completeness ----
            comp_cache_key = f"proposal_comp_{selected_col}_{effective_lookback}"
            comp_proposals = _filter_minimal(_get_cached_proposals(
                comp_cache_key,
                lambda: [
                    p for p in proposal_svc.propose_numeric_rules(
                        history_df, selected_col, dataset_config.table,
                        BaselineStrategy(method=BaselineMethod.LAST_N_PERIODS),
                    )
                    if p.rule_type.value.startswith("completeness")
                ],
            ))

            if comp_proposals:
                _update_col_health(selected_col, "completeness", comp_proposals[0].confidence)
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
                        fp=_fp,
                    )


# ===========================================================================
# Tab: Categoricas
# ===========================================================================

with tab_categoricas:
    if not cat_profiles:
        st.info("Nenhuma coluna categorica selecionada.")
        if st.button("Selecionar colunas no Setup", key="goto_setup_cat"):
            st.switch_page("pages/01_setup.py")
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

        # --- Cost guardrail for high-cardinality columns ---
        if effective == SemanticType.CATEGORICAL_HIGH_CARDINALITY:
            st.warning(
                f"Coluna `{selected_cat_col}` tem alta cardinalidade "
                f"({cat_profile.distinct_count} valores distintos). "
                f"As queries categoricas podem ser mais caras e lentas. "
                f"Apenas regras de completude e contagem de distintos serao geradas. "
                f"Considere reclassificar a coluna no Setup se a cardinalidade real for menor.",
            )

        # --- Fetch data (domain sempre, distribution e distinct sob demanda) ---
        try:
            cat_domain_df = fetch_categorical_domain(config_dict, selected_cat_col)
        except CostGuardrailTriggered as e:
            _handle_cost_guardrail(e)
        except Exception as e:
            st.error(f"Erro ao consultar dominio categorico: {e}")
            st.stop()

        # Distribution e distinct_count carregados sob demanda para reduzir custo
        import pandas as pd
        cat_dist_df = pd.DataFrame()
        cat_dc_history_df = pd.DataFrame()

        _cat_detail_key = f"cat_detail_loaded_{selected_cat_col}"
        if st.button(
            "Carregar historico de frequencia e distintos",
            key=f"btn_cat_detail_{_fp}_{selected_cat_col}",
            help="Executa 2 queries adicionais no Athena para obter distribuicao por periodo e contagem de distintos.",
        ) or st.session_state.get(_cat_detail_key, False):
            st.session_state[_cat_detail_key] = True
            try:
                cat_dist_df = fetch_categorical_distribution(config_dict, selected_cat_col)
            except Exception as e:
                st.warning(f"Erro na distribuicao: {e}")
            try:
                cat_dc_history_df = fetch_distinct_count_history(config_dict, selected_cat_col)
            except Exception as e:
                st.warning(f"Erro no historico de distintos: {e}")

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
                min_history_points=_grain_policy.min_history,
            )

            cat_cache_key = (
                f"cat_proposals_{selected_cat_col}_{cat_margin_pct}"
                f"_{cat_freq_mode}_{cat_n_periods}_{cat_n_sigma}"
                f"_{cat_floor_pct}_{cat_ceiling_pct}_{max_freq_rules}_{effective_lookback}"
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
                    distinct_count_history=cat_dc_history_df,
                ),
            )

            # --- Update col_health for categorical proposals ---
            _freq_tracked = False
            for cp in cat_proposals:
                if cp.rule_type in (
                    RuleType.CATEGORY_FREQUENCY_STATIC,
                    RuleType.CATEGORY_FREQUENCY_DYNAMIC,
                    RuleType.CATEGORY_FREQUENCY_HYBRID,
                ):
                    if not _freq_tracked:
                        _update_col_health(selected_cat_col, "frequency", cp.confidence)
                        _freq_tracked = True
                elif cp.rule_type == RuleType.ALLOWED_VALUES:
                    _update_col_health(selected_cat_col, "allowed_values", cp.confidence)
                elif cp.rule_type in (RuleType.DISTINCT_COUNT_EXACT, RuleType.DISTINCT_COUNT_RANGE):
                    _update_col_health(selected_cat_col, "distinct_count", cp.confidence)
                elif cp.rule_type == RuleType.COMPLETENESS:
                    _update_col_health(selected_cat_col, "completeness", cp.confidence)

            if is_high:
                st.warning(
                    "Coluna com alta cardinalidade. "
                    "Regras de valores permitidos e frequencia nao sao recomendadas."
                )

            # ---- Category Frequency (individual per value with charts) ----
            freq_types = {
                RuleType.CATEGORY_FREQUENCY_STATIC,
                RuleType.CATEGORY_FREQUENCY_DYNAMIC,
                RuleType.CATEGORY_FREQUENCY_HYBRID,
            }
            freq_proposals = _filter_minimal([
                p for p in cat_proposals
                if p.rule_type in freq_types
            ])
            if freq_proposals:
                mode_labels = {
                    "static": "Estatico",
                    "dynamic": "Dinamico",
                    "hybrid": "Hibrido",
                }
                mode_label = mode_labels.get(cat_freq_mode, cat_freq_mode)
                st.subheader(f"Frequencia por Valor ({mode_label})")

                # Show experimental badge for dynamic/hybrid frequency modes
                if cat_freq_mode in ("dynamic", "hybrid"):
                    _exp_rt = (
                        RuleType.CATEGORY_FREQUENCY_DYNAMIC
                        if cat_freq_mode == "dynamic"
                        else RuleType.CATEGORY_FREQUENCY_HYBRID
                    )
                    _exp_badge = capability_badge(_exp_rt)
                    if _exp_badge:
                        st.caption(_exp_badge)

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
                            fp=_fp,
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

            # ---- AllowedValues (CAT_LOW) ----
            av_proposals = _filter_minimal([p for p in cat_proposals if p.rule_type == RuleType.ALLOWED_VALUES])
            if av_proposals:
                st.subheader("Valores Permitidos (AllowedValues)")
                av = av_proposals[0]
                st.caption(
                    "Verifica que todos os valores da coluna pertencem a lista abaixo. "
                    "Qualquer valor novo faz a regra falhar."
                )

                # Historical pass/fail chart
                if av.history_dates and av.history_values:
                    colors = ["green" if v >= 1.0 else "red" for v in av.history_values]
                    fig_av = go.Figure(data=[go.Bar(
                        x=av.history_dates,
                        y=[1] * len(av.history_dates),
                        marker_color=colors,
                        hovertext=[
                            "OK" if v >= 1.0 else "Valor inesperado"
                            for v in av.history_values
                        ],
                        hoverinfo="text+x",
                    )])
                    fig_av.update_layout(
                        height=200,
                        margin=dict(l=50, r=20, t=30, b=30),
                        xaxis_title="Periodo",
                        yaxis=dict(visible=False),
                        title="Historico: regra teria passado?",
                    )
                    st.plotly_chart(fig_av, use_container_width=True)

                _render_backtest_metrics(av)
                _render_add_to_cart(
                    av, "AllowedValues",
                    f"av_{selected_cat_col}",
                    fp=_fp,
                )
                st.divider()

            # ---- DistinctValuesCount ----
            dc_proposals = _filter_minimal([
                p for p in cat_proposals
                if p.rule_type in (RuleType.DISTINCT_COUNT_EXACT, RuleType.DISTINCT_COUNT_RANGE)
            ])
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

                # Historical distinct count chart
                if proposal.history_dates and proposal.history_values:
                    dates = proposal.history_dates
                    values = proposal.history_values

                    fig_dc = go.Figure()

                    # Main line
                    fig_dc.add_trace(go.Scatter(
                        x=dates, y=values,
                        mode="lines+markers",
                        name="Distintos",
                        line=dict(color="steelblue"),
                    ))

                    if proposal.rule_type == RuleType.DISTINCT_COUNT_EXACT:
                        expected = int(proposal.suggested_lower)
                        fig_dc.add_hline(
                            y=expected, line_dash="dash", line_color="green",
                            annotation_text=f"Esperado: {expected}",
                        )
                        # Red markers for outliers
                        outlier_x = [d for d, v in zip(dates, values) if int(v) != expected]
                        outlier_y = [v for v in values if int(v) != expected]
                        if outlier_x:
                            fig_dc.add_trace(go.Scatter(
                                x=outlier_x, y=outlier_y,
                                mode="markers", name="Fora do esperado",
                                marker=dict(color="red", size=10, symbol="x"),
                            ))
                    else:
                        lower = proposal.suggested_lower
                        upper = proposal.suggested_upper
                        fig_dc.add_hrect(
                            y0=lower, y1=upper, fillcolor="green", opacity=0.1,
                            line_width=0,
                            annotation_text=f"Faixa: {int(lower)}-{int(upper)}",
                        )
                        # Red markers for outliers
                        outlier_x = [d for d, v in zip(dates, values) if v < lower or v > upper]
                        outlier_y = [v for v in values if v < lower or v > upper]
                        if outlier_x:
                            fig_dc.add_trace(go.Scatter(
                                x=outlier_x, y=outlier_y,
                                mode="markers", name="Fora da faixa",
                                marker=dict(color="red", size=10, symbol="x"),
                            ))

                    fig_dc.update_layout(
                        height=300,
                        margin=dict(l=50, r=20, t=30, b=30),
                        xaxis_title="Periodo",
                        yaxis_title="Valores distintos",
                    )
                    st.plotly_chart(fig_dc, use_container_width=True)

                _render_backtest_metrics(proposal)
                _render_add_to_cart(
                    proposal, "DistinctValuesCount",
                    f"dc_{selected_cat_col}",
                    fp=_fp,
                )
                st.divider()

            # ---- Completeness ----
            comp_proposals = _filter_minimal([p for p in cat_proposals if p.rule_type == RuleType.COMPLETENESS])
            if comp_proposals:
                with st.expander(f"Completeness {selected_cat_col}", expanded=False):
                    proposal = comp_proposals[0]
                    st.caption(
                        "Regra de completude: verifica que a porcentagem de valores nao-nulos "
                        "esta acima de um limite."
                    )

                    # Completeness history chart
                    if proposal.history_dates and proposal.history_values:
                        fig_comp = go.Figure()
                        fig_comp.add_trace(go.Scatter(
                            x=proposal.history_dates, y=proposal.history_values,
                            mode="lines+markers", name="Completude (%)",
                            line=dict(color="steelblue"),
                        ))
                        if proposal.suggested_lower:
                            fig_comp.add_hline(
                                y=proposal.suggested_lower * 100, line_dash="dash",
                                line_color="green",
                                annotation_text=f"Limite: {proposal.suggested_lower * 100:.0f}%",
                            )
                        fig_comp.update_layout(
                            height=250,
                            margin=dict(l=50, r=20, t=30, b=30),
                            xaxis_title="Periodo",
                            yaxis_title="Completude (%)",
                        )
                        st.plotly_chart(fig_comp, use_container_width=True)

                    st.code(proposal.gdq_syntax_preview)
                    _render_add_to_cart(
                        proposal, "Completeness",
                        f"cat_comp_{selected_cat_col}",
                        show_syntax=False,
                        fp=_fp,
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

    try:
        rc_history_df = fetch_row_count_history(config_dict)
    except CostGuardrailTriggered as e:
        _handle_cost_guardrail(e)
    except Exception as e:
        st.error(f"Erro ao consultar historico de volume: {e}")
        st.stop()

    if rc_history_df.empty:
        st.warning("Nenhum dado de volume encontrado.")
    else:
        # Classify row count series
        _rc_vals = rc_history_df["row_count"].tolist() if "row_count" in rc_history_df.columns else []
        _rc_dates = rc_history_df["period"].astype(str).tolist() if "period" in rc_history_df.columns else []

        # Auto-tune automatico para RowCount
        _at_rc_key = f"autotune_{_fp}_rowcount"
        _at_rc_min = _grain_policy.min_history + 1
        if _at_rc_key not in st.session_state and _rc_vals and len(_rc_vals) >= _at_rc_min:
            _at_rc_n_range = [n for n in _grain_policy.n_range if n <= len(_rc_vals) - _grain_policy.min_history]
            with st.spinner("Auto-tune RowCount..."):
                _at_rc = proposal_svc.find_best_params(
                    values=_rc_vals, dates=_rc_dates,
                    n_range=_at_rc_n_range or [_grain_policy.slider_n_min],
                    seasonality_enabled=_grain_policy.seasonality_enabled,
                    n_penalty_threshold=_grain_policy.n_penalty_threshold,
                )
                st.session_state[_at_rc_key] = _at_rc
                if _at_rc["viable"]:
                    st.session_state[f"n_{_fp}_rowcount"] = _at_rc["n_periods"]
                    st.session_state[f"k_{_fp}_rowcount"] = _at_rc["n_sigma"]
                    st.session_state[f"margin_{_fp}_rowcount"] = int(_at_rc["margin_pct"] * 100)
                    st.session_state[f"margin_on_{_fp}_rowcount"] = _at_rc["margin_enabled"]
                st.rerun()

        _at_rc_cached = st.session_state.get(_at_rc_key)
        if _at_rc_cached and _at_rc_cached.get("viable"):
            st.caption(
                f"Auto-tune: N={_at_rc_cached['n_periods']}, sigma={_at_rc_cached['n_sigma']}, "
                f"margem={_at_rc_cached['margin_pct']*100:.0f}% — "
                f"cobertura {_at_rc_cached['coverage_pct']:.0f}%, "
                f"{_confidence_badge(_at_rc_cached['confidence'])}"
            )
        rc_n, rc_k, rc_margin, rc_buffer, rc_margin_on = _render_rule_params(
            f"{_fp}_rowcount",
            n_min=_grain_policy.slider_n_min, n_max=_grain_policy.slider_n_max,
            n_default=_grain_policy.slider_n_default,
        )

        _rc_profile_key = f"series_profile_rowcount_{effective_lookback}"
        if _rc_profile_key not in st.session_state and _rc_vals:
            st.session_state[_rc_profile_key] = classify_series(_rc_vals, _rc_dates)
        rc_series_profile = st.session_state.get(_rc_profile_key)
        _render_regime_panel(rc_series_profile)

        rc_baseline = BaselineStrategy(
            method=BaselineMethod.LAST_N_PERIODS,
            n_periods=rc_n,
            n_sigma=rc_k,
            margin_pct=rc_margin,
            margin_enabled=rc_margin_on,
            min_history_points=_grain_policy.min_history,
        )

        rc_cache_key = f"proposal_rc_{rc_n}_{rc_k}_{rc_margin}_{rc_margin_on}_{effective_lookback}"
        rc_proposals = _filter_minimal(_get_cached_proposals(
            rc_cache_key,
            lambda: proposal_svc.propose_table_rules(
                rc_history_df, dataset_config.table, rc_baseline,
            ),
        ))

        if rc_proposals:
            rc_proposal = rc_proposals[0]
            _update_col_health("__table__", "rowcount", rc_proposal.confidence)

            values = rc_proposal.history_values
            dates = rc_proposal.history_dates

            if values and dates:
                _render_rolling_chart(
                    values, dates, rc_n, rc_k, rc_margin, "Row Count",
                    margin_enabled=rc_margin_on,
                )
                _render_auto_tune(
                    proposal_svc, values, dates,
                    f"{_fp}_rowcount", metric_kind="numeric",
                )

            if "autotune_rowcount" not in st.session_state:
                _render_backtest_metrics(rc_proposal)
            _render_add_to_cart(rc_proposal, "RowCount", "rowcount", profile=rc_series_profile, fp=_fp)
        else:
            st.warning(
                "Dados insuficientes para gerar regra RowCount. "
                "Verifique o lookback e o eixo temporal no Setup."
            )

    # -----------------------------------------------------------------------
    # Primary Key Analysis
    # -----------------------------------------------------------------------
    pk_cols = getattr(dataset_config, "unique_key_columns", []) or []
    if pk_cols:
        st.divider()
        st.subheader(f"Chave Primaria -- {', '.join(pk_cols)}")
        st.caption(
            "Analise de unicidade e completude das colunas de chave primaria. "
            "A regra `IsPrimaryKey` valida ambas. Se houver nulls, "
            "uma alternativa `CustomSql` de unicidade e sugerida."
        )

        try:
            pk_history_df = fetch_uniqueness_history(
                config_dict, tuple(pk_cols),
            )
        except Exception as e:
            st.error(f"Erro ao consultar historico de unicidade: {e}")
            pk_history_df = None

        if pk_history_df is not None and not pk_history_df.empty:
            # --- Chart 1: Duplicate ratio over time ---
            pk_dates = pk_history_df["period"].tolist()
            pk_total = pk_history_df["total_rows"].tolist()
            pk_dupes = pk_history_df["duplicate_count"].tolist()
            pk_dupe_pct = [
                (d / t * 100) if t > 0 else 0
                for d, t in zip(pk_dupes, pk_total)
            ]

            fig_pk = go.Figure()
            has_any_dupes = any(d > 0 for d in pk_dupes)

            if has_any_dupes:
                fig_pk.add_trace(go.Bar(
                    x=pk_dates, y=pk_dupe_pct,
                    name="Duplicatas (%)",
                    marker_color=[
                        "red" if d > 0 else "green" for d in pk_dupes
                    ],
                ))
            else:
                fig_pk.add_trace(go.Bar(
                    x=pk_dates,
                    y=[0.01] * len(pk_dates),  # minimal bar to show green
                    name="Sem duplicatas",
                    marker_color="green",
                ))

            fig_pk.update_layout(
                height=250,
                margin=dict(l=50, r=20, t=30, b=30),
                xaxis_title="Periodo",
                yaxis_title="Duplicatas (%)",
                title="Duplicatas por periodo",
            )
            st.plotly_chart(fig_pk, use_container_width=True)

            # --- Chart 2: Null ratio per key column ---
            null_cols = [
                c for c in pk_history_df.columns
                if c.startswith("non_null_")
            ]
            if null_cols:
                fig_nulls = go.Figure()
                for nc in null_cols:
                    col_name = nc.replace("non_null_", "")
                    non_null = pk_history_df[nc].tolist()
                    null_pct = [
                        ((t - nn) / t * 100) if t > 0 else 0
                        for t, nn in zip(pk_total, non_null)
                    ]
                    fig_nulls.add_trace(go.Scatter(
                        x=pk_dates, y=null_pct,
                        mode="lines+markers",
                        name=f"Nulls {col_name} (%)",
                    ))

                fig_nulls.update_layout(
                    height=250,
                    margin=dict(l=50, r=20, t=30, b=30),
                    xaxis_title="Periodo",
                    yaxis_title="Nulls (%)",
                    title="Nulls por coluna-chave por periodo",
                )
                st.plotly_chart(fig_nulls, use_container_width=True)

            # --- Recommendation badge ---
            has_dupes = any(d > 0 for d in pk_dupes)
            has_nulls_any = False
            for nc in null_cols:
                non_null = pk_history_df[nc].tolist()
                if any(t - nn > 0 for t, nn in zip(pk_total, non_null)):
                    has_nulls_any = True
                    break

            if not has_dupes and not has_nulls_any:
                st.success(
                    "Recomendacao: **IsPrimaryKey** -- unicidade e completude "
                    "perfeitas em todo o historico."
                )
            elif not has_dupes and has_nulls_any:
                st.warning(
                    "Recomendacao: **CustomSql (unicidade)** -- sem duplicatas, "
                    "porem nulls detectados. IsPrimaryKey exige completude. "
                    "A alternativa CustomSql valida apenas unicidade."
                )
            else:
                st.error(
                    "Duplicatas detectadas no historico. Nenhuma regra de chave "
                    "primaria e recomendada com alta confianca. "
                    "Verifique a definicao da chave."
                )

            # --- Generate proposals ---
            pk_cache_key = (
                f"proposal_pk_{'_'.join(pk_cols)}_{effective_lookback}"
            )
            pk_proposals = _get_cached_proposals(
                pk_cache_key,
                lambda: proposal_svc.propose_primary_key_rules(
                    pk_history_df, pk_cols, dataset_config.table,
                ),
            )

            if pk_proposals:
                for pk_p in pk_proposals:
                    _update_col_health("__table__", f"pk_{pk_p.rule_type.value}", pk_p.confidence)
                    label = get_rule_label(pk_p.rule_type)
                    conf = _confidence_badge(pk_p.confidence)
                    cov_str = (
                        f"{pk_p.backtest.coverage_pct:.0f}%"
                        if pk_p.backtest else "N/A"
                    )

                    with st.expander(
                        f"**{label}** | Cobertura: {cov_str} | {conf}",
                        expanded=True,
                    ):
                        st.code(pk_p.gdq_syntax_preview)
                        if pk_p.warnings:
                            for w in pk_p.warnings:
                                st.caption(f":orange[{w}]")
                        _render_backtest_metrics(pk_p)
                        _render_add_to_cart(
                            pk_p, label,
                            f"pk_{pk_p.rule_type.value}",
                            fp=_fp,
                        )
        elif pk_history_df is not None:
            st.warning(
                "Nenhum dado de unicidade encontrado para as colunas "
                "selecionadas."
            )
    else:
        st.divider()
        st.info(
            "Nenhuma chave primaria configurada. "
            "Defina as colunas de PK no **Setup** (passo 6b) "
            "para analisar unicidade."
        )


# ===========================================================================
# Tab: Resumo
# ===========================================================================

with tab_resumo:

    # ------------------------------------------------------------------
    # Column Health Dashboard
    # ------------------------------------------------------------------
    st.subheader("Visao Geral das Colunas")
    st.caption(
        "Panorama das colunas analisadas. Visite cada coluna nas abas "
        "Numericas/Categoricas/Tabela para preencher o painel."
    )

    import pandas as pd

    col_health = st.session_state.get("col_health", {})
    cart = st.session_state.get("rule_cart", [])

    # Build cart lookup
    _cart_by_col: dict[str, int] = {}
    for sel in cart:
        p = sel.proposal
        col_key = p.target_column or "__table__"
        _cart_by_col[col_key] = _cart_by_col.get(col_key, 0) + 1

    # Columns to display
    all_display_cols: list[tuple[str, str]] = []
    for p in numeric_profiles:
        all_display_cols.append((p.column_name, p.column_name))
    for p in cat_profiles:
        if p.column_name not in {c[1] for c in all_display_cols}:
            all_display_cols.append((p.column_name, p.column_name))
    all_display_cols.append((f"{dataset_config.table} (tabela)", "__table__"))

    _rule_cols = [
        ("Mean", "mean"), ("StdDev", "stddev"), ("Compl.", "completeness"),
        ("Freq.", "frequency"), ("RowCount", "rowcount"),
    ]

    _conf_display = {
        ConfidenceLevel.HIGH: "HIGH",
        ConfidenceLevel.MEDIUM: "MEDIUM",
        ConfidenceLevel.LOW: "LOW",
    }

    if all_display_cols:
        rows = []
        for display_name, health_key in all_display_cols:
            health_data = col_health.get(health_key, {})
            row_data = {"Coluna": display_name}
            for label, rule_key in _rule_cols:
                if rule_key in health_data:
                    row_data[label] = _conf_display.get(health_data[rule_key], "--")
                else:
                    row_data[label] = "--"
            n_cart = _cart_by_col.get(health_key, 0)
            row_data["Carrinho"] = f"{n_cart}" if n_cart > 0 else "--"
            rows.append(row_data)

        df_health = pd.DataFrame(rows)

        def _style_cell(val):
            if val == "HIGH":
                return "color: green; font-weight: bold"
            elif val == "MEDIUM":
                return "color: orange; font-weight: bold"
            elif val == "LOW":
                return "color: red; font-weight: bold"
            elif val == "--":
                return "color: #ccc"
            return ""

        styled = df_health.style.map(
            _style_cell,
            subset=[c for c, _ in _rule_cols] + ["Carrinho"],
        ).hide(axis="index")

        st.dataframe(styled, use_container_width=True, hide_index=True)

        n_analyzed = sum(1 for _, hk in all_display_cols if hk in col_health)
        st.caption(
            f"{n_analyzed}/{len(all_display_cols)} colunas analisadas | "
            f"{len(cart)} regra(s) no carrinho"
        )

    # Batch calibrate e carrinho acessiveis acima das tabs e pelo sidebar
