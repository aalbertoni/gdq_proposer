"""Breadcrumb navigation component for GDQ Rule Proposer pages."""

import streamlit as st

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
            parts.append(f"**{step}**")
        else:
            parts.append(step)
    st.caption(" \u203a ".join(parts))
