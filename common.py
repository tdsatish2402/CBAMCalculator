"""Shared look and masthead for the CBAM Exposure Calculator (UK and EU pages)."""

from __future__ import annotations

import base64
import inspect
from pathlib import Path

import streamlit as st

import tlo_brand as brand

# Typing in a list box matches on the text itself. Streamlit's default matches any characters that
# appear in order (typing 7224 would also list 7204...), so list boxes use substring matching where
# the installed Streamlit supports it.
CONTAINS = (
    {"filter_mode": "contains"}
    if "filter_mode" in inspect.signature(st.multiselect).parameters
    and "filter_mode" in inspect.signature(st.selectbox).parameters
    else {}
)

MARK = brand.resolve("mark")            # globe mark, square
TLO_URL = "https://www.tradelawobservatory.com/"

# The page follows the visitor's light or dark setting (phones commonly use dark), so the
# brand colours are chosen to match rather than fixed. Streamlit reports each visitor's active theme, so it
# is read on every run (this module is loaded once for all visitors and must not store it).
def theme_type():
    try:
        return st.context.theme.type            # "light", "dark" or None
    except Exception:                            # noqa: BLE001 - older Streamlit
        return None

LIGHT = {"ACCENT": "#3F106E", "HEAD": "#3F106E", "STRONG": "#1E2758", "MUTED": "#5B5770", "CAPTION": "#3A3849",
         "RULE": "#E6E2EF", "TAGBG": "#EDE6F7", "TAGFG": "#3F106E"}
DARK = {"ACCENT": "#CDB1F7", "HEAD": "#CDB1F7", "STRONG": "#F2EFF8", "MUTED": "#AEAAC0", "CAPTION": "#D9D5E6",
        "RULE": "#2E3140", "TAGBG": "#3B2C57", "TAGFG": "#EADDFB"}

def logo_path():
    return brand.resolve("wordmark_dark" if theme_type() == "dark" else "wordmark")

STRUCTURAL_CSS = """
[data-testid="stImage"] img { max-width: min(260px, 72vw) !important; height: auto !important; }
.tlo-logo { display: inline-block; line-height: 0; }
.tlo-logo img { width: 260px; max-width: min(260px, 72vw); height: auto; }
/* Headings carry no clickable anchor icon, so the address bar never picks up a #section suffix. */
[data-testid="stHeaderActionElements"] { display: none !important; }
.block-container { padding-top: 4rem !important; }
div.tlo-rule { height: 3px !important; border: 0 !important; margin: 0.2rem 0 1rem 0 !important;
  background: linear-gradient(90deg, @ACCENT@ 0%, @ACCENT@ 62%, #D8AC59 62%, #D8AC59 100%) !important;
  border-radius: 2px; max-width: 420px; }
.tlo-footer { margin-top: 2.5rem; padding-top: 0.9rem; border-top: 1px solid @RULE@;
              color: @MUTED@; font-size: 0.82rem; line-height: 1.5; }
.tlo-footer a { color: @ACCENT@ !important; text-decoration: none; }
/* Let metric labels wrap instead of clipping on narrow screens. */
[data-testid="stMetricLabel"] p { white-space: normal; line-height: 1.25; }
[data-testid="stMetricValue"] { font-size: clamp(1.1rem, 4.2vw, 1.6rem); }

/* Stack side-by-side blocks on phones and tablets in portrait. */
@media (max-width: 760px) {
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 0.25rem; }
  [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }
  [data-testid="stMetric"] { padding-bottom: 0.35rem; }
  .block-container { padding-left: 0.9rem; padding-right: 0.9rem; }
  h1 { font-size: 1.5rem !important; }
  h2 { font-size: 1.2rem !important; }
  h3 { font-size: 1.05rem !important; }
}

/* Keep the tab bar usable when four labels do not fit one line. */
[data-testid="stTabs"] [role="tablist"] { flex-wrap: wrap; row-gap: 0.2rem; }

/* Long official descriptions should wrap rather than stretch the layout. */
[data-testid="stCaptionContainer"] p { overflow-wrap: anywhere; }
"""

THEMED_CSS = """
a, a:visited { color: @ACCENT@ !important; }
[data-testid="stTab"][aria-selected="true"],
[data-testid="stTab"][aria-selected="true"] p,
[data-testid="stTab"]:hover p { color: @ACCENT@ !important; }
[data-testid="stTab"] .react-aria-SelectionIndicator,
[data-baseweb="tab-highlight"] { background-color: @ACCENT@ !important; }
[data-testid="stSpinner"] i { border-top-color: @ACCENT@ !important; }
[data-testid="stExpander"] summary:hover { color: @ACCENT@ !important; }
[data-tag], [data-baseweb="tag"] { background-color: @TAGBG@ !important; color: @TAGFG@ !important; }
[data-tag] span, [data-tag] svg, [data-baseweb="tag"] span, [data-baseweb="tag"] svg {
  color: @TAGFG@ !important; fill: @TAGFG@ !important; }
[data-testid="stNumberInputContainer"]:focus-within, [data-baseweb="input"]:focus-within,
[data-baseweb="textarea"]:focus-within, [data-baseweb="select"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within, [data-testid="stTextInputRootElement"]:focus-within
  { border-color: @ACCENT@ !important; box-shadow: none !important; }
textarea:focus, input:focus { caret-color: @ACCENT@; }
[data-testid="stRadioOption"][data-selected="true"] > div > div:first-child
  { background-color: @ACCENT@ !important; border-color: @ACCENT@ !important; }
h1, [data-testid="stMetricValue"] { color: @STRONG@; letter-spacing: 0.01em; }
/* Captions carry the explanatory text, so they are darker than Streamlit's default light grey. */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, [data-testid="stCaptionContainer"] small
  { color: @CAPTION@ !important; opacity: 1 !important; }
[data-testid="stTable"] th, [data-testid="stTable"] td { color: @CAPTION@ !important; }
h2, h3 { color: @HEAD@; }
/* Regime switch (UK CBAM | EU CBAM) in the brand colour rather than Streamlit's default red. */
button[data-variant="segmented_control"][aria-checked="true"],
[data-testid="stBaseButton-segmented_controlActive"] { background-color: @TAGBG@ !important;
  border-color: @ACCENT@ !important; color: @ACCENT@ !important; }
button[data-variant="segmented_control"][aria-checked="true"] *,
[data-testid="stBaseButton-segmented_controlActive"] * { color: @ACCENT@ !important; font-weight: 600; }
button[data-variant="segmented_control"]:hover, button[data-variant="segmented_control"]:hover *
  { color: @ACCENT@ !important; border-color: @ACCENT@ !important; }
"""

# Used only if Streamlit does not report the active theme: the wordmark then sits on a light panel.
UNKNOWN_THEME_LOGO_CSS = """
[data-testid="stImage"] img, .tlo-logo img { background: #FFFFFF; padding: 10px 14px; border-radius: 8px; }
"""


def _fill(css: str, palette: dict[str, str]) -> str:
    for key, value in palette.items():
        css = css.replace(f"@{key}@", value)
    return css


def build_css() -> str:
    theme = theme_type()
    if theme == "dark":
        body = _fill(STRUCTURAL_CSS + THEMED_CSS, DARK)
    elif theme == "light":
        body = _fill(STRUCTURAL_CSS + THEMED_CSS, LIGHT)
    else:
        body = (
            _fill(STRUCTURAL_CSS + THEMED_CSS, LIGHT)
            + UNKNOWN_THEME_LOGO_CSS
            + "@media (prefers-color-scheme: dark) {"
            + _fill(STRUCTURAL_CSS + THEMED_CSS, DARK)
            + "}"
        )
    return "<style>" + body + "</style>"


def masthead() -> None:
    """Trade Law Observatory logo, linked to the website."""
    LOGO = logo_path()
    if LOGO is not None:
        try:
            st.logo(str(LOGO), size="large", link=TLO_URL, icon_image=str(MARK) if MARK else None)
        except Exception:          # noqa: BLE001 - older Streamlit has no st.logo
            pass
        logo_b64 = base64.b64encode(Path(LOGO).read_bytes()).decode("ascii")
        st.markdown(
            f'<a class="tlo-logo" href="{TLO_URL}" target="_blank" rel="noopener">'
            f'<img src="data:image/png;base64,{logo_b64}" alt="Trade Law Observatory"></a>',
            unsafe_allow_html=True,
        )
    else:
        st.caption(
            "Trade Law Observatory — the logo could not be loaded. Check that assets/tlo_logo.png "
            "sits next to app.py."
        )
