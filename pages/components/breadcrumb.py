"""Breadcrumb navigation component for GDQ Rule Proposer pages."""

import streamlit as st

from pages.components.theme import ORANGE, ORANGE_DARK, GRAY_700, GRAY_300, NAVY, WHITE

# Sequential workflow steps (core pipeline)
_PIPELINE_STEPS = ["Setup", "Explore", "Review", "Teste"]
# Auxiliary pages (accessible anytime, not sequential)
_AUX_STEPS = ["Ajuda", "Diagnostico", "Query Log"]
_ALL_STEPS = ["Dashboard"] + _PIPELINE_STEPS + _AUX_STEPS


def render_breadcrumb(current_page: str) -> None:
    """Render breadcrumb showing user's position in the workflow.

    Pipeline steps (Setup > Explore > Review > Teste) are visually
    highlighted as a numbered sequence. Auxiliary pages are dimmed.

    Args:
        current_page: Label of the current page (e.g., "Explore", "Review").
    """
    parts = []

    # Dashboard
    if current_page == "Dashboard":
        parts.append(f"<span style='color:{ORANGE};font-weight:700'>Dashboard</span>")
    else:
        parts.append(f"<span style='color:{GRAY_700}'>Dashboard</span>")

    # Pipeline steps — numbered, with pill highlight for current
    for i, step in enumerate(_PIPELINE_STEPS, 1):
        num = f"<span style='font-size:0.7em;margin-right:2px'>{i}.</span>"
        if step == current_page:
            parts.append(
                f"<span style='background:{ORANGE};color:{WHITE};"
                f"padding:2px 10px;border-radius:12px;font-weight:700;"
                f"font-size:0.85em'>{num}{step}</span>"
            )
        else:
            parts.append(
                f"<span style='color:{NAVY};font-weight:600;"
                f"font-size:0.85em'>{num}{step}</span>"
            )

    # Separator before auxiliary
    parts.append(f"<span style='color:{GRAY_300};margin:0 4px'>|</span>")

    # Auxiliary pages — dimmed
    for step in _AUX_STEPS:
        if step == current_page:
            parts.append(
                f"<span style='color:{ORANGE};font-weight:600;"
                f"font-size:0.8em'>{step}</span>"
            )
        else:
            parts.append(
                f"<span style='color:{GRAY_300};font-size:0.8em'>{step}</span>"
            )

    sep = f" <span style='color:{GRAY_300};margin:0 3px'>\u203a</span> "
    aux_sep = f" <span style='color:{GRAY_300};margin:0 2px'>\u00b7</span> "

    # Build HTML: pipeline with arrows, aux with dots
    pipeline_html = sep.join(parts[:1 + len(_PIPELINE_STEPS)])
    aux_html = aux_sep.join(parts[1 + len(_PIPELINE_STEPS) + 1:])  # skip the | separator
    divider = parts[1 + len(_PIPELINE_STEPS)]  # the | separator

    st.markdown(
        f"<div style='font-size:0.85rem;margin-bottom:6px;display:flex;"
        f"align-items:center;gap:0px'>"
        f"{pipeline_html} {divider} {aux_html}</div>",
        unsafe_allow_html=True,
    )
