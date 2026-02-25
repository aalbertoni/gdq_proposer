"""
Pagina 03 — Review: Carrinho de regras + exportacao.

Mostra regras selecionadas com opcao de habilitar/desabilitar,
preview de sintaxe final e exportacao (copy + .txt).

Definido conforme docs/technical_spec_v1.md secao 12 (Sprint A2).
"""

import streamlit as st

from core.models.enums import ConfidenceLevel
from services.export_service import ExportService


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Review - GDQ Rule Proposer", page_icon=":clipboard:")

st.title("Review & Export")
st.caption("Revise as regras selecionadas e exporte a sintaxe GDQ final.")


# Guard
if "rule_cart" not in st.session_state or not st.session_state["rule_cart"]:
    st.info("Carrinho vazio. Adicione regras na pagina **Explore**.")
    st.stop()

cart = st.session_state["rule_cart"]
export_svc = ExportService()


# ---------------------------------------------------------------------------
# Exibir regras no carrinho
# ---------------------------------------------------------------------------

st.header(f"Carrinho ({len(cart)} regras)")

for i, selection in enumerate(cart):
    p = selection.proposal
    col1, col2, col3 = st.columns([1, 5, 2])

    with col1:
        enabled = st.checkbox(
            "On",
            value=selection.enabled,
            key=f"review_enable_{i}",
            label_visibility="collapsed",
        )
        selection.enabled = enabled

    with col2:
        label = p.rule_type.value.replace("_", " ").title()
        target = p.target_column or "(tabela)"
        st.markdown(f"**{label}** — `{target}`")
        if p.backtest:
            st.caption(
                f"Cobertura: {p.backtest.coverage_pct:.1f}% | "
                f"Estabilidade: {p.backtest.stability_score:.2f} | "
                f"Drift: {'Sim' if p.backtest.has_drift else 'Nao'}"
            )

    with col3:
        badges = {
            ConfidenceLevel.HIGH: ":green[HIGH]",
            ConfidenceLevel.MEDIUM: ":orange[MEDIUM]",
            ConfidenceLevel.LOW: ":red[LOW]",
        }
        st.markdown(badges.get(p.confidence, p.confidence.value))

    with st.expander("Sintaxe GDQ", expanded=False):
        st.code(selection.final_gdq_syntax)

    if p.warnings:
        for w in p.warnings:
            st.caption(f"  {w}")

st.divider()

# Remover regras desabilitadas do carrinho
if st.button("Remover desabilitadas"):
    st.session_state["rule_cart"] = [s for s in cart if s.enabled]
    st.rerun()


# ---------------------------------------------------------------------------
# Preview de sintaxe final
# ---------------------------------------------------------------------------

st.header("Sintaxe Final")

result = export_svc.export(cart)

if result.warnings:
    for w in result.warnings:
        st.warning(w)

if result.rules_text:
    st.code(result.rules_text, language=None)
    st.caption(f"{result.rules_count} regras habilitadas")
else:
    st.info("Nenhuma regra habilitada.")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

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
    )

with col2:
    if result.rules_text:
        st.info("Use **Ctrl+A** no bloco acima para copiar manualmente.")
