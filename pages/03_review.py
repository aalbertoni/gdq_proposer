"""
Pagina 03 — Review: Carrinho de regras + exportacao.

Mostra regras selecionadas com opcao de habilitar/desabilitar,
preview de sintaxe final e exportacao (copy + .txt).

Definido conforme docs/technical_spec_v1.md secao 12 (Sprint A2).
"""

import streamlit as st

from pages.components.breadcrumb import render_breadcrumb
from pages.components.theme import inject_global_css, badge_html

from core.models.enums import ConfidenceLevel, RuleType, get_rule_label
from core.gdq_capability import capability_badge, capability_warning
from core.rule_explainer import explain_rule, explain_rule_detail
from services.export_service import ExportService


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Review - GDQ Rule Proposer", page_icon=":clipboard:")
inject_global_css()

st.title("Review & Export")
render_breadcrumb("Review")
st.caption(
    "Revise as regras do carrinho, habilite ou desabilite individualmente, "
    "e exporte a sintaxe GDQ final para usar no AWS Glue Data Quality."
)

# Config summary
if "dataset_config" in st.session_state:
    cfg = st.session_state["dataset_config"]
    n_sel = len(cfg.selected_columns) if cfg.selected_columns else 0
    st.caption(
        f"Tabela: `{cfg.schema}.{cfg.table}` · "
        f"Lookback: {cfg.lookback_value}p · "
        f"Colunas: {n_sel}"
    )

# Guard
if "rule_cart" not in st.session_state or not st.session_state["rule_cart"]:
    st.info(
        "Carrinho vazio. Calibre e adicione regras na pagina **Explore**. "
        "Cada regra e adicionada individualmente apos calibracao."
    )
    if st.button("Ir para Explore"):
        st.switch_page("pages/02_explore.py")
    st.stop()

cart = st.session_state["rule_cart"]
export_svc = ExportService()


# ---------------------------------------------------------------------------
# Exibir regras no carrinho (ordenadas por prioridade)
# ---------------------------------------------------------------------------

st.header(f"Carrinho ({len(cart)} regras)")

_enabled_ct = sum(1 for s in cart if s.enabled)
_disabled_ct = len(cart) - _enabled_ct
if _disabled_ct:
    st.caption(f"{_enabled_ct} habilitadas · {_disabled_ct} desabilitadas")

# --- Glue test coverage indicator ---
_tested_ct = sum(1 for s in cart if s.enabled and s.has_test_result)
_tested_passed = sum(1 for s in cart if s.enabled and s.has_test_result and s.glue_test_result.passed)
_tested_failed = _tested_ct - _tested_passed
_stale_ct = sum(1 for s in cart if s.enabled and s.has_test_result and s.is_test_stale)

if _tested_ct > 0:
    if _tested_failed == 0 and _stale_ct == 0:
        st.success(
            f"Todas as {_tested_ct} regras testadas foram aprovadas no Glue."
        )
    elif _tested_failed > 0:
        st.warning(
            f"{_tested_ct} de {_enabled_ct} regras testadas no Glue "
            f"({_tested_passed} aprovadas, {_tested_failed} reprovadas)"
        )
    if _stale_ct > 0:
        st.info(
            f"{_stale_ct} regra(s) com resultado desatualizado "
            f"(sintaxe alterada apos o teste)."
        )

# Ordenar cart por prioridade (maior priority_score primeiro, agrupado por tier)
from core.rule_recommender import _TIER_RANK
_sorted_cart = sorted(
    enumerate(cart),
    key=lambda item: (
        -_TIER_RANK.get(item[1].proposal.recommendation_tier, 0),
        -item[1].proposal.priority_score,
    ),
)

remove_idx = None
for i, selection in _sorted_cart:
    p = selection.proposal
    col1, col2, col3, col4 = st.columns([0.6, 5, 1.5, 0.5])

    with col1:
        enabled = st.checkbox(
            "On",
            value=selection.enabled,
            key=f"review_enable_{i}",
            label_visibility="collapsed",
            help="Desmarque para excluir esta regra da exportacao sem remove-la do carrinho.",
        )
        selection.enabled = enabled

    with col2:
        label = get_rule_label(p.rule_type)
        target = p.target_column or "(tabela)"
        if p.subpopulation_label:
            target = f"{target} [{p.subpopulation_label}]"

        # Glue test badge (inline after rule name)
        _test_badge = ""
        if selection.has_test_result:
            if selection.is_test_stale:
                _test_badge = " " + badge_html("Resultado desatualizado", "warning")
            elif selection.glue_test_result.passed:
                _test_badge = " " + badge_html("Validada no Glue", "success")
            else:
                # Check if first execution + dynamic rule
                _is_dynamic = "last(" in selection.final_gdq_syntax.lower()
                _exec_num = st.session_state.get("glue_run_execution_num", 1)
                if _is_dynamic and _exec_num <= 1:
                    _test_badge = " " + badge_html("Falha esperada (1a execucao)", "warning")
                else:
                    _test_badge = " " + badge_html("Falhou no Glue", "error")

        st.markdown(f"**{label}** — `{target}`{_test_badge}", unsafe_allow_html=True)
        warning_text = capability_warning(p.rule_type)
        if warning_text:
            st.caption(warning_text)
        if p.backtest:
            st.caption(
                f"Cobertura: {p.backtest.coverage_pct:.1f}% · "
                f"Estabilidade: {p.backtest.stability_score:.2f} · "
                f"Drift: {'Sim' if p.backtest.has_drift else 'Nao'}"
            )

    with col3:
        from core.rule_recommender import category_badge as _cat_badge
        st.markdown(_cat_badge(p))
        reasons = getattr(p, "recommendation_reasons", [])
        if reasons:
            st.caption("; ".join(reasons))

    with col4:
        if st.button("X", key=f"remove_{i}", help="Remover esta regra"):
            remove_idx = i

    st.caption(explain_rule(p))

    with st.expander("Sintaxe GDQ e detalhes", expanded=False):
        st.code(selection.final_gdq_syntax)
        st.markdown(explain_rule_detail(p))

        # Inline Glue test feedback
        if selection.has_test_result:
            _gr = selection.glue_test_result
            st.markdown("---")
            st.markdown("**Resultado do teste Glue:**")
            if selection.is_test_stale:
                st.warning(
                    "Sintaxe alterada apos o teste — "
                    "resultado pode nao refletir a regra atual.",
                    icon="⚠️",
                )
            _metric_cols = st.columns(3)
            with _metric_cols[0]:
                _val = _gr.metric_value
                st.metric(
                    "Valor medido",
                    f"{_val:,.4f}" if _val is not None else "—",
                )
            with _metric_cols[1]:
                st.metric(
                    "Limite inferior",
                    f"{_gr.compiled_lower:,.4f}" if _gr.compiled_lower is not None else "—",
                )
            with _metric_cols[2]:
                st.metric(
                    "Limite superior",
                    f"{_gr.compiled_upper:,.4f}" if _gr.compiled_upper is not None else "—",
                )
            if _gr.failure_reason and not _gr.passed:
                st.error(f"**Motivo:** {_gr.failure_reason}")
            if selection.glue_tested_at:
                st.caption(f"Testado em: {selection.glue_tested_at[:19]}")

    if p.warnings:
        for w in p.warnings:
            st.caption(f"  Aviso: {w}")

if remove_idx is not None:
    st.session_state["rule_cart"].pop(remove_idx)
    st.rerun()

st.divider()

# Action buttons
act_col1, act_col2 = st.columns(2)
with act_col1:
    if st.button("Adicionar mais regras"):
        st.switch_page("pages/02_explore.py")
with act_col2:
    disabled_count = sum(1 for s in cart if not s.enabled)
    _confirm_key = "confirm_remove_disabled"
    if _confirm_key not in st.session_state:
        st.session_state[_confirm_key] = False

    if not st.session_state[_confirm_key]:
        if st.button(
            f"Remover desabilitadas ({disabled_count})",
            disabled=disabled_count == 0,
        ):
            st.session_state[_confirm_key] = True
            st.rerun()
    else:
        st.warning(f"Remover {disabled_count} regras desabilitadas do carrinho?")
        _cfm1, _cfm2 = st.columns(2)
        with _cfm1:
            if st.button("Confirmar", key="confirm_remove_yes"):
                st.session_state["rule_cart"] = [s for s in cart if s.enabled]
                st.session_state[_confirm_key] = False
                st.rerun()
        with _cfm2:
            if st.button("Cancelar", key="confirm_remove_no"):
                st.session_state[_confirm_key] = False
                st.rerun()


# ---------------------------------------------------------------------------
# Preview de sintaxe final
# ---------------------------------------------------------------------------

st.header("Sintaxe Final")
st.caption(
    "Bloco com todas as regras habilitadas em sintaxe GDQ. "
    "Cole diretamente no campo de regras do AWS Glue Data Quality."
)

result = export_svc.export(cart)

if result.warnings:
    st.caption("A validacao encontrou problemas. Revise antes de exportar.")
    for w in result.warnings:
        st.warning(w)

if result.rules_text:
    st.code(result.rules_text, language=None)
    st.caption(f"{result.rules_count} regras habilitadas")

    # Resumo em linguagem natural
    with st.expander("O que essas regras fazem?", expanded=False):
        enabled_sels = [s for s in cart if s.enabled and s.final_gdq_syntax.strip()]
        for j, sel in enumerate(enabled_sels):
            p = sel.proposal
            target = p.target_column or "(tabela)"
            rule_label = get_rule_label(p.rule_type)
            exp_badge = capability_badge(p.rule_type)
            st.markdown(f"**{j + 1}. {rule_label}** {exp_badge} — `{target}`")
            st.markdown(explain_rule(p))
            if j < len(enabled_sels) - 1:
                st.markdown("---")
else:
    st.info("Nenhuma regra habilitada.")


# ---------------------------------------------------------------------------
# Colunas necessarias
# ---------------------------------------------------------------------------

_enabled_sels = [s for s in cart if s.enabled and s.final_gdq_syntax.strip()]
if _enabled_sels:
    import re
    _col_pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")

    _all_columns: set[str] = set()
    for _sel in _enabled_sels:
        _p = _sel.proposal
        # Target column
        if _p.rule_type == RuleType.IS_PRIMARY_KEY:
            if _p.suggested_values:
                _all_columns.update(v.upper() for v in _p.suggested_values)
        elif _p.target_column:
            _all_columns.add(_p.target_column.upper())
        # Coluna de subpopulacao (usada no WHERE)
        if _p.subpopulation_filter:
            _m = _col_pattern.match(_p.subpopulation_filter.strip())
            if _m:
                _all_columns.add(_m.group(1).upper())

    # Coluna de date filter (usada no WHERE das regras filtradas)
    if "dataset_config" in st.session_state:
        _dc = st.session_state["dataset_config"]
        _date_expr = getattr(_dc, "gdq_date_filter_expr", None)
        if _date_expr:
            _dm = _col_pattern.match(_date_expr.strip())
            if _dm:
                _all_columns.add(_dm.group(1).upper())

    if _all_columns:
        _sorted_cols = sorted(_all_columns)
        st.subheader("Colunas")
        st.caption(
            "Todas as colunas necessarias para as regras habilitadas "
            "(alvos, filtros de data e subpopulacao). "
            "Use esta lista no campo COLUMNS_NAME do payload Thundera."
        )
        st.code(", ".join(_sorted_cols), language=None)


# ---------------------------------------------------------------------------
# Consistency check
# ---------------------------------------------------------------------------

enabled_rules = [s for s in cart if s.enabled and s.final_gdq_syntax.strip()]
if len(enabled_rules) >= 2:
    consistency_warnings = export_svc.check_consistency(cart)
    if consistency_warnings:
        st.warning(f"{len(consistency_warnings)} avisos de consistencia detectados:")
        for w in consistency_warnings:
            st.caption(f"- {w}")
    else:
        st.caption(":green[Nenhum conflito detectado entre as regras.]")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

# --- Sampling warning ---
_ds_config = st.session_state.get("dataset_config")
if _ds_config and _ds_config.is_sampling_active:
    st.warning(
        "A analise exploratoria usou amostragem. Os thresholds propostos sao aproximacoes. "
        "Recomendado: desabilitar amostragem e recalibrar antes de exportar para producao."
    )
    st.info(
        "Regras GDQ exportadas referem a tabela original. "
        "Em producao, avg(last(N)) e std(last(N)) operam sobre dados completos."
    )

st.header("Exportar")

col1, col2 = st.columns(2)

with col1:
    st.download_button(
        label="Baixar .txt",
        data=result.rules_text,
        file_name="gdq_rules.txt",
        mime="text/plain",
        disabled=not result.rules_text,
        type="primary",
        help="Exporta as regras habilitadas em arquivo de texto. Cada linha contem uma regra GDQ.",
    )

with col2:
    if result.rules_text:
        st.caption(
            "Voce tambem pode copiar diretamente do bloco de sintaxe acima "
            "usando o icone de copia no canto superior direito."
        )
    else:
        st.caption("Habilite ao menos uma regra para exportar.")


# ---------------------------------------------------------------------------
# Relatorio Analitico
# ---------------------------------------------------------------------------

st.divider()
st.header("Relatorio Analitico")
st.caption(
    "Relatorio detalhado em markdown com evidencia, racional e recomendacoes "
    "para cada regra. Ideal para documentacao e aprovacao tecnica."
)

if result.rules_text:
    report = export_svc.export_analytical_report(cart)
    with st.expander("Preview do relatorio", expanded=False):
        st.markdown(report)
    st.download_button(
        label="Baixar relatorio.md",
        data=report,
        file_name="gdq_analytical_report.md",
        mime="text/markdown",
        disabled=not result.rules_text,
        help="Relatorio analitico markdown com: "
             "evidencia estatistica (cobertura, estabilidade, drift), "
             "racional de cada regra em linguagem natural, "
             "sintaxe GDQ completa com parametros aplicados, "
             "avisos e recomendacoes de ajuste, "
             "e resumo executivo por nivel de confianca. "
             "Ideal para documentacao interna e aprovacao tecnica antes do cadastro no GDQ.",
    )
else:
    st.info("Habilite ao menos uma regra para gerar o relatorio.")


# ---------------------------------------------------------------------------
# Testar via Thundera
# ---------------------------------------------------------------------------

st.divider()
st.header("Testar via Thundera")
st.caption(
    "Teste as regras exportadas em um Glue job de teste antes de "
    "implantar em producao."
)

if result.rules_count > 0:
    if st.button("Ir para pagina de Teste", type="secondary", key="go_test"):
        st.switch_page("pages/04_test.py")
else:
    st.info("Habilite ao menos uma regra para testar.")
