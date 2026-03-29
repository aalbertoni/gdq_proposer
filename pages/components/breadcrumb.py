"""Breadcrumb navigation component for GDQ Rule Proposer pages."""

import streamlit as st

from pages.components.theme import ORANGE, GRAY_700, NAVY

_STEPS = ["Dashboard", "Setup", "Explore", "Review", "Teste",
          "Ajuda", "Diagnostico", "Query Log"]


def render_breadcrumb(current_page: str) -> None:
    """Render breadcrumb showing user's position in the workflow.

    Args:
        current_page: Label of the current page (e.g., "Explore", "Review").
    """
    parts = []
    for step in _STEPS:
        if step == current_page:
            parts.append(
                f"<span style='color:{ORANGE};font-weight:700'>{step}</span>"
            )
        else:
            parts.append(
                f"<span style='color:{GRAY_700}'>{step}</span>"
            )
    sep = f" <span style='color:{GRAY_700};margin:0 2px'>\u203a</span> "
    st.markdown(
        f"<div style='font-size:0.85rem;margin-bottom:4px'>{sep.join(parts)}</div>",
        unsafe_allow_html=True,
    )
