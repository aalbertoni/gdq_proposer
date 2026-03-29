"""Design system Itau — constantes de cor e CSS global para Streamlit.

Paleta baseada na identidade visual Itau (rebranding 2024 by Pentagram).
Fonte fallback: Inter (Google Fonts) — substitui a proprietaria Itau Display.
"""

from html import escape as _html_escape

import streamlit as st

# ---------------------------------------------------------------------------
# Color tokens
# ---------------------------------------------------------------------------

ORANGE = "#EC7000"
ORANGE_LIGHT = "#FF8C33"
ORANGE_DARK = "#C45E00"
NAVY = "#003087"
DARK_BLUE = "#1A5493"
BLACK = "#161616"
GRAY_700 = "#4C4C4C"
GRAY_300 = "#D1D1D1"
GRAY_200 = "#E8E8E8"
GRAY_100 = "#F5F5F5"
WHITE = "#FFFFFF"
GOLD = "#FFF212"
SUCCESS = "#00875A"
SUCCESS_BG = "#E6F4ED"
ERROR = "#CC0000"
ERROR_BG = "#FDEAEA"
WARNING = "#B45309"
WARNING_BG = "#FFF7E6"


# ---------------------------------------------------------------------------
# Badge HTML helpers
# ---------------------------------------------------------------------------

def badge_html(text: str, variant: str = "default") -> str:
    """Return inline HTML badge styled per Itau design system.

    Args:
        text: Badge label.
        variant: One of 'success', 'error', 'warning', 'info', 'default'.
    """
    styles = {
        "success": f"background-color:{SUCCESS_BG};color:{SUCCESS}",
        "error": f"background-color:{ERROR_BG};color:{ERROR}",
        "warning": f"background-color:{WARNING_BG};color:{WARNING}",
        "info": f"background-color:#E8F0FE;color:{DARK_BLUE}",
        "default": f"background-color:{GRAY_100};color:{GRAY_700}",
    }
    style = styles.get(variant, styles["default"])
    return (
        f"<span style='{style};padding:2px 8px;border-radius:6px;"
        f"font-size:0.8em;font-weight:600;letter-spacing:0.02em'>"
        f"{_html_escape(text)}</span>"
    )


# ---------------------------------------------------------------------------
# Global CSS injection
# ---------------------------------------------------------------------------

_GLOBAL_CSS = """
<style>
/* ---- Itau Design System — GDQ Rule Proposer ---- */

/* Google Fonts: Inter (fallback for Itau Display) */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* Global font — exclude Material Symbols icon elements */
html, body,
[class*="st-"]:not([class*="material-symbols"]):not([data-testid="stIconMaterial"]) {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
/* Preserve icon font for Streamlit's Material Symbols */
span[class*="material-symbols"],
[data-testid="stIconMaterial"],
.material-symbols-rounded,
.material-symbols-outlined {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
}

/* Headings */
h1, h2, h3, h4, h5, h6,
[data-testid="stHeading"] h1,
[data-testid="stHeading"] h2,
[data-testid="stHeading"] h3 {
    font-family: 'Inter', sans-serif !important;
    font-weight: 700 !important;
    color: """ + NAVY + """ !important;
    letter-spacing: -0.01em;
}

/* Main title — orange accent bar */
[data-testid="stHeading"] h1 {
    border-left: 4px solid """ + ORANGE + """;
    padding-left: 12px;
}

/* Sidebar styling */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, """ + NAVY + """ 0%, #001A4D 100%) !important;
}
[data-testid="stSidebar"] *:not([class*="material-symbols"]):not(.material-symbols-rounded):not(.material-symbols-outlined) {
    color: """ + WHITE + """ !important;
}
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] small {
    color: rgba(255, 255, 255, 0.65) !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: """ + WHITE + """ !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255, 255, 255, 0.15) !important;
}

/* Sidebar buttons */
[data-testid="stSidebar"] button[kind="secondary"] {
    background-color: rgba(255, 255, 255, 0.1) !important;
    color: """ + WHITE + """ !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
}
[data-testid="stSidebar"] button[kind="secondary"]:hover {
    background-color: rgba(255, 255, 255, 0.2) !important;
    border-color: """ + ORANGE + """ !important;
}

/* Primary buttons — Itau orange */
button[kind="primary"],
[data-testid="stFormSubmitButton"] button {
    background-color: """ + ORANGE + """ !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    transition: all 0.2s ease !important;
}
button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button:hover {
    background-color: """ + ORANGE_DARK + """ !important;
    box-shadow: 0 2px 8px rgba(236, 112, 0, 0.3) !important;
}

/* Secondary buttons */
button[kind="secondary"] {
    border: 1.5px solid """ + GRAY_300 + """ !important;
    border-radius: 8px !important;
    color: """ + BLACK + """ !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}
button[kind="secondary"]:hover {
    border-color: """ + ORANGE + """ !important;
    color: """ + ORANGE + """ !important;
    background-color: rgba(236, 112, 0, 0.04) !important;
}

/* Metric cards */
[data-testid="stMetric"] {
    background-color: """ + WHITE + """;
    border: 1px solid """ + GRAY_200 + """;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    transition: box-shadow 0.2s ease;
}
[data-testid="stMetric"]:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
[data-testid="stMetric"] [data-testid="stMetricLabel"] {
    color: """ + GRAY_700 + """ !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    font-size: 0.75rem !important;
    letter-spacing: 0.05em;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: """ + NAVY + """ !important;
    font-weight: 700 !important;
}

/* Containers / Cards — pedra style (squircle) */
[data-testid="stVerticalBlock"] > div > [data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
    border-color: """ + GRAY_200 + """ !important;
}

/* Expander styling */
[data-testid="stExpander"] {
    border-radius: 10px !important;
    border-color: """ + GRAY_200 + """ !important;
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important;
}

/* Tables — header orange */
[data-testid="stTable"] thead th {
    background-color: """ + NAVY + """ !important;
    color: """ + WHITE + """ !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}
[data-testid="stTable"] tbody tr:nth-child(even) {
    background-color: """ + GRAY_100 + """ !important;
}
[data-testid="stTable"] tbody td {
    font-size: 0.9rem !important;
    color: """ + BLACK + """ !important;
}

/* Dataframe styling */
[data-testid="stDataFrame"] {
    border-radius: 10px !important;
    overflow: hidden;
}

/* Tabs — orange indicator */
button[data-baseweb="tab"] {
    font-weight: 500 !important;
    color: """ + GRAY_700 + """ !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: """ + ORANGE + """ !important;
    font-weight: 700 !important;
}
[data-baseweb="tab-highlight"] {
    background-color: """ + ORANGE + """ !important;
}

/* Selectbox / Multiselect */
[data-baseweb="select"] > div {
    border-radius: 8px !important;
}
[data-baseweb="select"] > div:focus-within {
    border-color: """ + ORANGE + """ !important;
    box-shadow: 0 0 0 1px """ + ORANGE + """ !important;
}

/* Input fields */
[data-baseweb="input"] > div {
    border-radius: 8px !important;
}
[data-baseweb="input"] > div:focus-within {
    border-color: """ + ORANGE + """ !important;
    box-shadow: 0 0 0 1px """ + ORANGE + """ !important;
}

/* Number input */
[data-testid="stNumberInput"] > div > div {
    border-radius: 8px !important;
}

/* Slider — orange track */
[data-testid="stSlider"] [role="slider"] {
    background-color: """ + ORANGE + """ !important;
}

/* Success/Error/Warning/Info boxes */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border-left: 4px solid !important;
}

/* Divider */
hr {
    border-color: """ + GRAY_200 + """ !important;
}

/* Code blocks */
[data-testid="stCode"],
code {
    border-radius: 8px !important;
}

/* Caption text */
.stCaption, [data-testid="stCaptionContainer"] {
    color: """ + GRAY_700 + """ !important;
}

/* Checkbox styling */
[data-testid="stCheckbox"] label span[data-testid="stCheckbox-label"] {
    font-weight: 500;
}

/* Spinner / Progress */
[data-testid="stSpinner"] > div {
    border-top-color: """ + ORANGE + """ !important;
}

/* Toast notifications */
[data-testid="stToast"] {
    border-radius: 10px !important;
}

/* Scrollbar styling */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-thumb {
    background: """ + GRAY_300 + """;
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: """ + GRAY_700 + """;
}

</style>
"""


def inject_global_css() -> None:
    """Inject Itau design system CSS into the Streamlit page.

    Call once at the top of each page (idempotent — Streamlit deduplicates).
    """
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
