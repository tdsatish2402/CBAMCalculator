"""CBAM Exposure Calculator (Trade Law Observatory): UK CBAM and EU CBAM.

This file is the entry point. It sets the page style and logo, offers the choice between the two
regimes and then runs the chosen page: uk_page.py (the UK CBAM) or eu_page.py (the EU CBAM).
The UK page is the default, so the existing link opens it; the EU page is also reachable at /eu.
"""

from __future__ import annotations

import streamlit as st

import common as cm

st.set_page_config(
    page_title="CBAM Exposure Calculator | Trade Law Observatory",
    page_icon=str(cm.MARK) if cm.MARK else "🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(cm.build_css(), unsafe_allow_html=True)
cm.masthead()

UK_LABEL, EU_LABEL = "UK CBAM", "EU CBAM"
uk_page = st.Page("uk_page.py", title=UK_LABEL, url_path="uk", default=True)
eu_page = st.Page("eu_page.py", title=EU_LABEL, url_path="eu")
page = st.navigation([uk_page, eu_page], position="hidden")

current = EU_LABEL if page.title == EU_LABEL else UK_LABEL
choice = st.segmented_control(
    "Regime",
    options=[UK_LABEL, EU_LABEL],
    default=current,
    label_visibility="collapsed",
    help="Switch between the UK CBAM (from 1 January 2027) and the EU CBAM (definitive period from 1 January 2026).",
)
if choice and choice != current:
    st.switch_page(eu_page if choice == EU_LABEL else uk_page)

page.run()
