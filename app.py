"""CBAM Exposure Calculator (Trade Law Observatory): UK CBAM and EU CBAM.

Layout: four tabs (Calculator, About, Limitations, Data and sources). Each has a UK CBAM and an EU CBAM
tab inside it; the Calculator also has a tab comparing the two. Both regimes are drawn on every run, so
entries made in one are kept when switching to the other.

On-screen text sits in uk_view.py (UK), eu_view.py (EU), compare_view.py (comparison) and trade_view.py
(trade section, both regimes).
"""

from __future__ import annotations

import streamlit as st

import cbam_data as cd
import cbam_trade as ct
import common as cm
import compare_view
import eu_view
import uk_view

st.set_page_config(
    page_title="CBAM Exposure Calculator | Trade Law Observatory",
    page_icon=str(cm.MARK) if cm.MARK else "🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(cm.build_css(), unsafe_allow_html=True)
cm.masthead()

st.title("CBAM Exposure Calculator")
st.markdown('<div class="tlo-rule"></div>', unsafe_allow_html=True)
st.caption(
    "Estimates the UK Carbon Border Adjustment Mechanism (CBAM) charge and the number and cost of EU CBAM "
    "certificates on imported goods, from the default values and rates or prices published by HMRC and the "
    "European Commission, and summarises the exporting country's trade with the UK and the EU for 2022 to 2024, "
    "from BACI data."
)

with st.spinner("Loading the official default-value tables..."):
    uk_data, uk_status = uk_view.load_dataset()
    eu_data = eu_view.load_eu()

with st.sidebar:
    st.header("Data status")
    uk_view.sidebar(uk_status)
    st.divider()
    eu_view.sidebar(eu_data)
    st.divider()
    st.caption("Trade data: " + ct.SOURCE_NAME + ".")

# A link ending in ?regime=eu opens the EU tabs first.
_start = "EU CBAM" if str(st.query_params.get("regime", "")).lower() == "eu" else "UK CBAM"


def regime_tabs(extra: tuple[str, ...] = ()):
    return st.tabs(["UK CBAM", "EU CBAM", *extra], default=_start)


calculator_tab, about_tab, limitations_tab, sources_tab = st.tabs(
    ["Calculator", "About", "Limitations", "Data and sources"]
)

with calculator_tab:
    uk_tab, eu_tab, compare_tab = regime_tabs(("UK and EU compared",))
    with uk_tab:
        uk_view.calculator(uk_data, uk_status)
    with eu_tab:
        eu_view.calculator(eu_data)
    with compare_tab:
        compare_view.render(uk_data, eu_data)

with about_tab:
    uk_tab, eu_tab = regime_tabs()
    with uk_tab:
        uk_view.about()
    with eu_tab:
        eu_view.about()

with limitations_tab:
    uk_tab, eu_tab = regime_tabs()
    with uk_tab:
        uk_view.limitations()
    with eu_tab:
        eu_view.limitations()

with sources_tab:
    uk_tab, eu_tab = regime_tabs()
    with uk_tab:
        uk_view.sources()
    with eu_tab:
        eu_view.sources()

# --------------------------------------------------------------------------
# Notices and footer
# --------------------------------------------------------------------------

st.warning(
    "**For information purposes only.** Nothing on this Calculator is tax, legal or customs advice. The UK sector "
    "rates are HMRC's illustrative figures of 16 October 2026, not the rates that will apply. EU default values, "
    "benchmarks and certificate prices are those published by the European Commission as at the dates shown; "
    "prices after the third quarter of 2026 are not yet published. The trade figures from BACI describe 2022 to "
    "2024 at 6-digit level and are not a forecast."
)

st.markdown(
    f"""
<div class="tlo-footer">
  <strong>Trade Law Observatory</strong> · CBAM Exposure Calculator<br>
  UK default values: GOV.UK, public sector information licensed under the Open Government Licence v3.0
  (verified baseline as at {cd.BASELINE_AS_AT}). EU default values, benchmarks and prices: European Commission;
  EU legislation: EUR-Lex, © European Union. Trade figures: {ct.SOURCE_NAME}, licensed under the
  {ct.SOURCE_LICENCE}.<br>
  <a href="{cm.TLO_URL}" target="_blank">tradelawobservatory.com</a>
</div>
""",
    unsafe_allow_html=True,
)
