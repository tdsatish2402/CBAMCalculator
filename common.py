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

MARK = brand.resolve("mark")                    # globe mark, square: reads on light and dark
LOGO = brand.resolve("wordmark")                # purple lettering, for light backgrounds
LOGO_DARK = brand.resolve("wordmark_dark")      # pale lettering, for dark backgrounds
TLO_URL = "https://www.tradelawobservatory.com/"

# How colours are handled
# -----------------------
# The page follows the visitor's light or dark setting (phones commonly use dark). The brand colours
# for each setting live in .streamlit/config.toml, so Streamlit itself colours tabs, links, selections
# and text to suit the background on screen. The page does not try to work out the setting in Python:
# that check can report "light" on a phone that is showing the dark page, which left purple and grey
# text on a dark background.
#
# The CSS below therefore never fixes a text colour. It only adjusts layout, makes captions follow the
# main text colour, and swaps the logo and the rule beneath the title with the device setting.

CSS = """
<style>
/* ---- Logo ---- */
.tlo-logo { display: inline-block; line-height: 0; }
.tlo-logo img { width: 260px; max-width: min(260px, 72vw); height: auto; }

/* ---- Title rule: brand purple then gold; lighter purple on dark screens ---- */
div.tlo-rule { height: 3px; border: 0; margin: 0.2rem 0 1rem 0; border-radius: 2px; max-width: 420px;
  background: linear-gradient(90deg, #3F106E 0%, #3F106E 62%, #D8AC59 62%, #D8AC59 100%); }
@media (prefers-color-scheme: dark) {
  div.tlo-rule { background: linear-gradient(90deg, #CDB1F7 0%, #CDB1F7 62%, #D8AC59 62%, #D8AC59 100%); }
}

/* ---- Text that Streamlit fades: keep it in the main text colour so it stays readable ---- */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p,
[data-testid="stCaptionContainer"] small { color: inherit !important; opacity: 0.86 !important; }
[data-testid="stCaptionContainer"] p { overflow-wrap: anywhere; }

.tlo-footer { margin-top: 2.5rem; padding-top: 0.9rem; border-top: 1px solid rgba(128, 128, 128, 0.35);
              opacity: 0.86; font-size: 0.82rem; line-height: 1.5; }
.tlo-footer a { text-decoration: none; }

/* Selected items in list boxes: a soft purple tint with the main text colour, readable on both
   backgrounds (Streamlit's default puts white text on the accent colour, which is pale on dark). */
[data-tag] { background-color: rgba(124, 77, 196, 0.22) !important; color: inherit !important;
             border: 1px solid rgba(124, 77, 196, 0.45) !important; }
[data-tag] span, [data-tag] svg { color: inherit !important; }

h1 { letter-spacing: 0.01em; }

/* Headings carry no clickable anchor icon, so the address bar never picks up a #section suffix. */
[data-testid="stHeaderActionElements"] { display: none !important; }
.block-container { padding-top: 4rem !important; }

/* Let metric labels wrap instead of clipping on narrow screens. */
[data-testid="stMetricLabel"] p { white-space: normal; line-height: 1.25; }
[data-testid="stMetricValue"] { font-size: clamp(1.1rem, 4.2vw, 1.6rem); }

/* Keep the tab bar usable when four labels do not fit one line. */
[data-testid="stTabs"] [role="tablist"] { flex-wrap: wrap; row-gap: 0.2rem; }

/* ---- Phones and tablets in portrait ---- */
@media (max-width: 760px) {
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 0.25rem; }
  [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    min-width: 100% !important;
    flex: 1 1 100% !important;
  }
  [data-testid="stMetric"] { padding-bottom: 0.35rem; }
  .block-container { padding-left: 0.9rem; padding-right: 0.9rem; padding-top: 3.2rem !important; }
  h1 { font-size: 1.5rem !important; }
  h2 { font-size: 1.2rem !important; }
  h3 { font-size: 1.05rem !important; }
  [data-testid="stCaptionContainer"] p { font-size: 0.9rem; line-height: 1.5; }
}
</style>
"""


def build_css() -> str:
    return CSS


def _b64(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def masthead() -> None:
    """Trade Law Observatory logo, linked to the website, in the version that suits the screen."""
    if MARK is not None:
        try:
            # The globe mark reads on both backgrounds, so it is used for the corner logo.
            st.logo(str(MARK), size="large", link=TLO_URL, icon_image=str(MARK))
        except Exception:          # noqa: BLE001 - older Streamlit has no st.logo
            pass

    if LOGO is None:
        st.caption(
            "Trade Law Observatory — the logo could not be loaded. Check that tlo_logo.png "
            "sits next to app.py."
        )
        return

    dark_source = (
        f'<source srcset="data:image/png;base64,{_b64(LOGO_DARK)}" media="(prefers-color-scheme: dark)">'
        if LOGO_DARK is not None
        else ""
    )
    st.markdown(
        f'<a class="tlo-logo" href="{TLO_URL}" target="_blank" rel="noopener"><picture>{dark_source}'
        f'<img src="data:image/png;base64,{_b64(LOGO)}" alt="Trade Law Observatory"></picture></a>',
        unsafe_allow_html=True,
    )
