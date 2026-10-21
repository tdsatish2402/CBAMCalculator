"""EU CBAM Exposure Calculator page - a public information and planning tool."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

import cbam_eu as eu
import cbam_trade as ct
import common as cm
from trade_view import load_trade, render_trade_section

_CONTAINS = cm.CONTAINS
MARK = cm.MARK
TLO_URL = cm.TLO_URL
OTHER_CHOICE = -1          # "country not listed or not known"

st.set_page_config(
    page_title="EU CBAM Exposure Calculator | Trade Law Observatory",
    page_icon=str(MARK) if MARK else "🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_data(show_spinner=False)
def load_eu():
    return eu.load()


@st.cache_data(show_spinner=False)
def values_for(country: str | None):
    return eu.resolved_values(load_eu(), country)


def euro(value) -> str:
    return "—" if value is None else f"€{value:,.2f}"


def parse_pasted_codes(text: str, known: set[str]) -> tuple[list[str], list[str]]:
    """Read CN codes from free text. 8-digit codes and 10-digit TARIC codes are accepted; an 8-digit code
    that the list splits into TARIC codes adds each of them. Returns (matched codes, unmatched entries)."""
    matched, unmatched = [], []
    for token in re.split(r"[,;\n\r\t|]+", text):
        digits = re.sub(r"\D", "", token)
        if not digits:
            continue
        pieces = [digits] if len(digits) in (8, 10) else (
            [digits[i:i + 8] for i in range(0, len(digits), 8)] if len(digits) % 8 == 0 else [digits.zfill(8)])
        for piece in pieces:
            if piece in known:
                matched.append(piece)
            elif len(piece) == 10 and piece[:8] in known:
                matched.append(piece[:8])
            elif [k for k in known if k.startswith(piece)]:
                matched.extend(sorted(k for k in known if k.startswith(piece)))
            else:
                unmatched.append(piece)
    return list(dict.fromkeys(matched)), list(dict.fromkeys(unmatched))


def add_pasted_codes(by_code):
    """Button callback: add pasted codes to the selection. Runs before the page is redrawn."""
    matched, unmatched = parse_pasted_codes(st.session_state.get("eu_paste_box", ""), set(by_code))
    st.session_state["eu_paste_unmatched"] = unmatched
    if matched:
        st.session_state["eu_code_select"] = list(dict.fromkeys(
            st.session_state.get("eu_code_select", []) + [by_code[c] for c in matched]))


def spaced(code: str) -> str:
    """CN code written the official way, for example 7207 12 10 or 2523 10 00 10."""
    parts = [code[:4], code[4:6], code[6:8]] + ([code[8:]] if len(code) > 8 else [])
    return " ".join(p for p in parts if p)


data = load_eu()

st.title("EU CBAM Exposure Calculator")
st.markdown('<div class="tlo-rule"></div>', unsafe_allow_html=True)
st.caption(
    "Estimates the number and cost of EU Carbon Border Adjustment Mechanism (CBAM) certificates for imported "
    "goods from the European Commission's country-specific default values, CBAM benchmarks and published "
    "certificate prices, and summarises the exporting country's trade with the EU for 2022 to 2024, from BACI data."
)

with st.sidebar:
    st.header("Data status")
    st.metric("Default values loaded", f"{len(data.values):,}")
    st.caption(
        f"Default values for {data.values['country'].nunique() - 1} countries and for other countries and "
        "territories: Implementing Regulation (EU) 2025/2621, Annex I, as corrected by Implementing Regulation "
        "(EU) 2026/1740 (Commission file of 6 August 2026)."
    )
    st.caption(f"CBAM benchmarks for {data.benchmarks['code'].nunique()} CN codes: Implementing Regulation (EU) "
               "2025/2620, Column B.")
    st.caption("Certificate prices: " + "; ".join(f"{q} €{p:.2f}" for q, p in eu.PRICES.items())
               + f". {eu.PRICES_AS_AT}.")
    st.divider()
    st.caption("Trade data: " + ct.SOURCE_NAME + ".")

calculator_tab, about_tab, limitations_tab, sources_tab = st.tabs(
    ["Calculator", "About", "Limitations", "Data and sources"]
)

# --------------------------------------------------------------------------
# Calculator
# --------------------------------------------------------------------------

with calculator_tab:
    st.caption(
        "**1. Country of origin.** Select the country where the goods were produced. EU default values are "
        "set by country, so the country decides the default value.\n\n"
        "**2. CBAM certificate estimate.** Select a sector and CN code(s), then enter a quantity, the year of "
        "import and the certificate price.\n\n"
        "**3. Partner country trade data.** The country's trade with the EU for 2022 to 2024 is shown below "
        "the estimate, at 6-digit level, in the selected CN codes or sector(s), if no code is selected."
    )

    trade_data, trade_error = load_trade()
    baci_to_dv = dict(zip(data.countries["baci_code"].astype(int), data.countries["dv_country"]))
    if trade_data is not None:
        country_pairs = ct.country_options(trade_data, market="EU")
    else:
        # Without the trade tables, the countries with published default values are still offered.
        country_pairs = sorted(((int(b), d) for b, d in baci_to_dv.items()), key=lambda item: item[1].lower())
    country_names = dict(country_pairs)
    country_names[OTHER_CHOICE] = "Other or unknown country"
    country_choice = st.selectbox(
        "Country of origin",
        options=[OTHER_CHOICE] + [code for code, _ in country_pairs],
        format_func=lambda code: country_names[code],
        index=None,
        key="eu_country_choice",
        **_CONTAINS,
        placeholder="Select the country where the goods were produced",
        help=(
            "Sets the default value and, from BACI data, adds the country's trade with the EU. Countries "
            "without their own default value take the value for other countries and territories. Iceland, "
            "Liechtenstein, Norway and Switzerland are outside the EU CBAM and are not listed."
        ),
    )
    if trade_error:
        st.warning(
            "Country trade data could not be loaded, so the trade analysis is unavailable. The certificate "
            "estimate is not affected. Technical detail: " + str(trade_error)
        )

    dv_country = None if country_choice in (None, OTHER_CHOICE) else baci_to_dv.get(int(country_choice))
    if country_choice is not None and country_choice != OTHER_CHOICE and dv_country is None:
        st.info(
            f"No default values are set for {country_names[country_choice]}, so the values for other countries "
            "and territories apply (Implementing Regulation (EU) 2025/2621, Annex I)."
        )
    elif country_choice == OTHER_CHOICE:
        st.info("The values for other countries and territories apply (Implementing Regulation (EU) 2025/2621, Annex I).")

    goods = data.goods.copy()
    goods["display"] = goods.apply(
        lambda row: f"{spaced(row['code'])} | {row['description']} [{row['sector']}]", axis=1)
    by_code = dict(zip(goods["code"], goods["display"]))
    by_display = dict(zip(goods["display"], goods["code"]))

    if "eu_code_select" not in st.session_state:
        st.session_state["eu_code_select"] = []

    sector_choice = st.multiselect(
        "Select CBAM sector",
        key="eu_sector_choice",
        options=list(eu.SECTORS),
        default=[],
        placeholder="All sectors",
        help="Narrows the list of CN codes below. Leave empty to include all five sectors. Electricity is not "
             "covered by the estimate.",
    )
    scoped = goods if not sector_choice else goods[goods["sector"].isin(sector_choice)]

    search_text = str(st.session_state.get("eu_search_box", "") or "")
    if search_text.strip():
        needle = search_text.strip().lower()
        scoped = scoped[
            scoped["code"].str.contains(re.sub(r"\D", "", needle) or needle, na=False)
            | scoped["description"].str.lower().str.contains(needle, na=False)
        ]

    options = list(dict.fromkeys(scoped["display"].tolist() + st.session_state["eu_code_select"]))
    selected_labels = st.multiselect(
        "Select CN code(s)",
        options=options,
        key="eu_code_select",
        placeholder="Type to search, or pick from the list",
        **_CONTAINS,
        help="CN codes listed in Annex I to Regulation (EU) 2023/956, with the TARIC codes used for cement and "
             "calcined clay. A code used in another jurisdiction should not be assumed to be the CN code.",
    )

    st.text_input(
        "Or search by CN code or description",
        key="eu_search_box",
        placeholder="For example 7208, ammonia, or hot-rolled",
        help="Narrows the list in the box above. Clear it to see every code in the selected sectors.",
    )

    with st.expander("Or paste a list of CN codes"):
        st.caption(
            "Paste codes separated by commas or new lines. Spaces inside a code are ignored, so 7208 10 00 "
            "and 72081000 both work."
        )
        st.text_area("CN codes", key="eu_paste_box", height=90, label_visibility="collapsed")
        st.button("Add these codes", on_click=add_pasted_codes, args=(by_code,), key="eu_paste_button")

    if st.session_state.get("eu_paste_unmatched"):
        st.warning(
            "Not found in the CBAM list: " + ", ".join(st.session_state["eu_paste_unmatched"])
            + ". Check the code against Annex I to the CBAM Regulation; it may not be a CBAM good."
        )

    left, right = st.columns(2)
    with left:
        year = st.selectbox(
            "Year of import", options=list(eu.YEARS), index=0, key="eu_year",
            help="Sets the mark-up on the default value, the CBAM factor and, for some goods, the benchmark. "
                 "The year of import is the default reporting period; goods imported in 2026 are always "
                 "reported for 2026.",
        )
    price_options = list(eu.PRICES) + ["Own figure"]
    with right:
        quarter = st.selectbox(
            "Certificate price", options=price_options, index=price_options.index("Q3 2026"), key="eu_quarter",
            format_func=lambda q: f"{q} (€{eu.PRICES[q]:.2f})" if q in eu.PRICES else q,
            help="The Commission's published price for the quarter of import in 2026. From 2027 prices are "
                 "published weekly; for later years enter an assumed figure.",
        )
    price = st.number_input(
        "Price per certificate (€ per tCO₂e)",
        min_value=0.0, value=float(eu.PRICES.get(quarter, eu.PRICES["Q3 2026"])), step=0.01, format="%.2f",
        key=f"eu_price_{quarter}",
        help="Prefilled with the selected published price. It can be replaced.",
    )
    if year > 2026:
        st.caption(
            f"No certificate price has been published for {year}. The price used is the figure above, which is "
            "an assumption, not a forecast."
        )

    if country_choice is None:
        st.info("Select a country of origin to start an estimate. The default value depends on it.")
    elif not selected_labels:
        st.info("Select at least one CN code to start an estimate.")
        if trade_data is not None and country_choice != OTHER_CHOICE:
            render_trade_section(trade_data, country_choice, country_names[country_choice], [], goods,
                                 sector_choice, market="EU")
        label = dv_country or "other countries and territories"
        st.subheader("Published default values")
        st.caption(
            f"The European Commission's default values for {label}, in tonnes of CO₂ equivalent per tonne of "
            "good, before the mark-up. A code with no value of its own takes the value for other countries and "
            "territories. Open a sector to see its table."
        )
        table = values_for(dv_country)
        table = table[table["code"].isin(scoped["code"])]
        open_all = table["sector"].nunique() == 1 or bool(search_text.strip())
        for name in eu.SECTORS:
            part = table[table["sector"] == name]
            if part.empty:
                continue
            shown = part.assign(
                code=part["code"].map(spaced),
                basis=part["basis"].map({"country": "Country value", "other": "Other countries value"}),
            )[["code", "description", "direct", "indirect", "total", "route", "basis"]]
            with st.expander(f"{name} ({len(part):,} {'code' if len(part) == 1 else 'codes'})", expanded=open_all):
                st.dataframe(
                    shown.rename(columns={
                        "code": "CN code", "description": "Description", "direct": "Direct",
                        "indirect": "Indirect", "total": "Total", "route": "Route", "basis": "Value used"}),
                    width="stretch", hide_index=True, height=min(380, 38 + 35 * len(part)),
                    column_config={c: st.column_config.NumberColumn(format="%.3f", width="small")
                                   for c in ("Direct", "Indirect", "Total")},
                )
    else:
        selected_codes = [by_display[label] for label in selected_labels if label in by_display]
        many_codes = len(selected_codes) > 5
        holder = (
            st.expander(f"Enter quantities for the {len(selected_codes)} selected codes", expanded=False)
            if many_codes else st
        )
        records = []
        for code in selected_codes:
            good = goods[goods["code"] == code].iloc[0]
            row, basis = eu.default_value(data, dv_country, code)
            with holder.container(border=True):
                st.markdown(f"**{spaced(code)} · {good['sector']}**")
                st.caption(good["description"])
                if row is None or pd.isna(row["total"]):
                    st.caption("No default value is published for this code.")
                else:
                    counted = "direct and indirect" if good["sector"] in eu.INDIRECT_COUNTED else "direct only"
                    whose = (f"for {dv_country}" if basis == "country"
                             else "for other countries and territories")
                    route = f" · production route {row['route']}" if isinstance(row["route"], str) else ""
                    indirect = "n/a" if pd.isna(row["indirect"]) else f"{float(row['indirect']):.3f}"
                    direct = "n/a" if pd.isna(row["direct"]) else f"{float(row['direct']):.3f}"
                    st.caption(
                        f"Default value {whose}: direct {direct}, indirect {indirect}, total "
                        f"{float(row['total']):.3f} tCO₂e per tonne{route}. Emissions counted: {counted}."
                    )
                    if basis == "other" and dv_country:
                        st.caption(f"No value is set for {dv_country} for this code, so the value for other "
                                   "countries and territories applies.")
                quantity = st.number_input(
                    "Quantity (tonnes)", min_value=0.0, value=None, step=0.01, format="%.2f",
                    key=f"eu_quantity_{code}", placeholder="Enter tonnes",
                )
                with st.expander("Carbon price paid in the country of origin (optional)"):
                    st.write(
                        "Leave at zero unless the amount has been established separately. A carbon price "
                        "effectively paid in the country of origin, net of any rebate or compensation, reduces "
                        "the number of certificates (Article 9 of Regulation (EU) 2023/956). It must be "
                        "supported by a carbon price report certified by an independent person. This Calculator "
                        "does not determine eligibility."
                    )
                    deduction = st.number_input(
                        "Carbon price deduction (€)", min_value=0.0, value=0.0, step=1.0, format="%.2f",
                        key=f"eu_deduction_{code}",
                    )
            result = eu.calculate(data, dv_country, code, float(quantity or 0.0), year, float(price),
                                  float(deduction))
            records.append({"code": code, "sector": good["sector"], "quantity": quantity, **result})

        results = pd.DataFrame(records)
        ready = results[results["ok"] & results["quantity"].notna()]
        missing = results[~(results["ok"] & results["quantity"].notna())]

        st.subheader("Estimated CBAM certificates")
        if not missing.empty:
            reasons = [
                f"{spaced(r['code'])} ({'quantity not entered' if r['ok'] else r['reason']})"
                for _, r in missing.iterrows()
            ]
            if len(reasons) <= 5:
                st.warning("Excluded from the totals: " + "; ".join(reasons) + ".")
            else:
                st.warning(f"{len(reasons)} of the {len(results)} selected codes are excluded from the totals "
                           "because a quantity has not been entered or no default value is published.")

        if ready.empty:
            st.info("No complete calculations yet.")
        else:
            deduction_used = float(ready["cost"].sum() - ready["cost_after_deduction"].sum()) > 0
            first, second, third = st.columns(3)
            first.metric("Embedded emissions (total)", f"{ready['embedded_emissions'].sum():,.3f} tCO₂e")
            second.metric("CBAM certificates (total)", f"{ready['certificates_after_deduction'].sum():,.3f}")
            third.metric("Estimated cost (total)", euro(ready["cost_after_deduction"].sum()))
            st.caption(
                f"Year of import {year}; certificate price {euro(price)}"
                + (f" ({quarter})" if quarter in eu.PRICES and abs(price - eu.PRICES[quarter]) < 0.005 else "")
                + ". Embedded emissions include the mark-up. One certificate covers one tonne of CO₂ equivalent."
            )
            if deduction_used:
                st.caption(
                    f"Before the carbon price deduction: {ready['certificates'].sum():,.3f} certificates, "
                    f"{euro(ready['cost'].sum())}. Deduction entered: "
                    f"{euro(ready['cost'].sum() - ready['cost_after_deduction'].sum())}."
                )

            summary = pd.DataFrame({
                "CN code": ready["code"].map(spaced),
                "Quantity (t)": ready["quantity"].astype(float),
                "Default value": ready["default_value"],
                "Mark-up": ready["mark_up"].map(lambda v: f"{v * 100:.0f}%"),
                "SEE": ready["see"],
                "Benchmark": ready["benchmark"],
                "Adjustment": ready["sefa"],
                "Certificates/t": ready["certificates_per_tonne"],
                "Certificates": ready["certificates_after_deduction"],
                "Cost (€)": ready["cost_after_deduction"],
            })
            three = st.column_config.NumberColumn(format="%.3f", width="small")
            with st.expander(f"Estimate by CN code ({len(ready)} {'code' if len(ready) == 1 else 'codes'})",
                             expanded=not many_codes):
                st.dataframe(
                    summary, width="stretch", hide_index=True,
                    column_config={
                        "Quantity (t)": st.column_config.NumberColumn(format="%.2f", width="small"),
                        "Default value": three, "SEE": three,
                        "Benchmark": three, "Adjustment": three,
                        "Certificates/t": three, "Certificates": three,
                        "Cost (€)": st.column_config.NumberColumn(format="€%.2f", width="small"),
                    },
                )
                st.caption(
                    "Values per tonne are in tCO₂e. Default value: the value counted (direct emissions, or direct and "
                    "indirect for cement and fertilisers). SEE: specific embedded emissions, the default value "
                    "multiplied by (1 + mark-up). Benchmark: CBAM benchmark, Column B. Adjustment: free allocation "
                    "adjustment, CBAM factor "
                    f"({eu.CBAM_FACTOR[year] * 100:.1f}% for {year}) × cross-sectoral correction factor "
                    f"({eu.CSCF[year]:.1f}) × benchmark. Certificates per tonne: SEE less the adjustment, "
                    "and not below zero. Certificates and cost are after any carbon price deduction entered."
                )

        threshold_goods = results[results["sector"] != "Hydrogen"]
        st.caption(
            "**Threshold.** An importer whose imports of CBAM goods, other than hydrogen and electricity, do not "
            "exceed 50 tonnes of net mass in a calendar year is exempt from CBAM obligations (Annex VII, point 1, "
            "to Regulation (EU) 2023/956). The threshold applies to all of the importer's CBAM imports in the "
            "year, not to one consignment, so the Calculator does not apply it."
            if not threshold_goods.empty else
            "**Threshold.** The 50-tonne exemption does not apply to hydrogen."
        )

        if trade_data is not None and country_choice != OTHER_CHOICE:
            render_trade_section(trade_data, country_choice, country_names[country_choice],
                                 [c[:8] for c in selected_codes], goods, sector_choice, market="EU")

    st.divider()
    st.caption(
        "**Basis.** Certificates: quantity in tonnes multiplied by the default value for the country of origin and "
        "CN code, including the mark-up for the year, less the free allocation adjustment (CBAM factor × "
        "cross-sectoral correction factor × CBAM benchmark, Column B), and not below zero (Regulation (EU) "
        "2023/956, Articles 7, 9 and 31; Implementing Regulations (EU) 2025/2621 and 2025/2620). Cost: "
        "certificates multiplied by the price. Trade analysis: " + ct.SOURCE_NAME + ", 6-digit headings, values "
        "in US dollars, 2022 to 2024. See the Limitations and Data and sources tabs."
    )
    st.caption(
        "**Sources.** "
        f"[European Commission, CBAM legislation and guidance]({eu.SOURCES['default_values']}); "
        f"[European Commission, Price of CBAM certificates]({eu.SOURCES['prices']}); "
        "[CEPII, BACI](http://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37) "
        "(" + ct.SOURCE_CITATION + ")."
    )

# --------------------------------------------------------------------------
# About, Limitations, Data and sources
# --------------------------------------------------------------------------

with about_tab:
    st.header("About")

    st.subheader("What the Calculator does")
    st.markdown(
        f"""
The Calculator has two parts:

**1. Certificate estimate.** For each selected CN code, the Calculator takes the default value the European
Commission set for the country of origin, adds the mark-up for the year of import, deducts the free
allocation adjustment and multiplies the result by the quantity, to give the number of CBAM certificates.
Multiplied by the certificate price, this gives an indicative cost. The estimate does not determine whether
a good is in scope, whether an importer is liable, or what the price will be, and it does not replace the
CBAM declaration.

**2. Country trade data.** For the selected country, the Calculator shows its trade with the EU for 2022 to
2024 in the selected goods or, if no CN code is selected, in the selected sector(s). It uses
{ct.SOURCE_NAME}, at 6-digit level. EU imports are imports into the 27 member states from outside the EU.
The figures describe past trade. They are not a forecast and do not measure the effect of the CBAM.
"""
    )

    st.subheader("The EU CBAM in brief")
    st.markdown(
        """
The CBAM is established by Regulation (EU) 2023/956, as amended by Regulation (EU) 2025/2083. Its definitive
period began on 1 January 2026. It covers cement, iron and steel, aluminium, fertilisers, hydrogen and
electricity, listed by CN code in Annex I to the Regulation.

The authorised CBAM declarant, usually the importer, buys CBAM certificates and surrenders them for the
emissions embedded in the goods imported in a calendar year. The annual CBAM declaration is due by
30 September of the following year, the first by 30 September 2027 for goods imported in 2026.
Certificates are sold on a common central platform from February 2027.

An importer whose imports of CBAM goods, other than hydrogen and electricity, do not exceed 50 tonnes of
net mass in a calendar year is exempt. Goods originating in Iceland, Liechtenstein, Norway and Switzerland
are outside the CBAM.
"""
    )

    st.subheader("How the number of certificates is worked out")
    st.markdown(
        """
For each good, the certificates to be surrendered are the specific embedded emissions, less the free
allocation adjustment, less any carbon price effectively paid in the country of origin, multiplied by the
mass of the good. A negative result counts as zero. The Calculator applies this using default values.

**1. Default value.** The Commission sets default values by country of origin and CN code (Implementing
Regulation (EU) 2025/2621, Annex I, as corrected by Implementing Regulation (EU) 2026/1740). Where a
country is not listed, or no value is given for it, the value for other countries and territories applies.
A mark-up is added: 10% for 2026, 20% for 2027 and 30% from 2028, and 1% for fertilisers. For iron and
steel, aluminium and hydrogen only direct emissions are counted; for cement and fertilisers, direct and
indirect emissions are counted.

**2. Free allocation adjustment.** Because EU producers still receive some free allowances under the EU
ETS, the embedded emissions are reduced by the CBAM factor × the cross-sectoral correction factor × the
CBAM benchmark. Where default values are used, the benchmark is taken from Column B of Implementing
Regulation (EU) 2025/2620. Where a benchmark depends on the production route, the route is the one given
with the default value for the country of origin. Some steel benchmarks also change from 2028.

| Year | 2026 | 2027 | 2028 | 2029 | 2030 |
| --- | --- | --- | --- | --- | --- |
| CBAM factor | 97.5% | 95.0% | 90.0% | 77.5% | 51.5% |
| Cross-sectoral correction factor | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

The CBAM factor falls to 0% in 2034, when free allocation for CBAM goods ends.

**3. Certificate price.** In 2026 the Commission publishes one price a quarter, which applies to goods
imported in that quarter: €75.36 for the first quarter, €75.28 for the second and €82.32 for the third.
The fourth-quarter price is due on 4 January 2027. From 2027 prices are published weekly.

**4. Carbon price paid in the country of origin.** A carbon price effectively paid where the goods were
produced, net of any rebate or compensation, reduces the number of certificates (Article 9 of Regulation
(EU) 2023/956). It must be supported by a carbon price report certified by an independent person. The
Calculator does not calculate it; the deduction field is a manual input for an amount established
separately.

**Example.** For one tonne of semi-finished non-alloy steel (CN 7207 12 10) from India imported in 2026,
the default value of 4.270 tCO₂e plus the 10% mark-up gives 4.697 tCO₂e. The free allocation adjustment is
97.5% × 1.0 × 1.364 = 1.330 tCO₂e. The difference, 3.367 certificates, costs €277.18 at the third-quarter
price of €82.32 (Trade Law Observatory calculation).
"""
    )

    st.subheader("Reading the trade figures")
    st.markdown(
        f"""
**Scopes.** *Selected goods* are the 6-digit headings (HS 2022) that contain the selected CN codes. *Whole
sector* is every 6-digit heading in one CBAM sector. *All CBAM-covered goods* is every heading in the six
sectors, including electricity. *All goods* is every product the country trades, CBAM-covered or not.

**Measures.** For an exporting country and a scope, all by value in US dollars:

- *Exports to the EU*: the value of the country's exports of the goods to the 27 member states, with the change since 2022.
- *Share of the country's exports going to the EU*: its exports to the EU divided by its exports to all destinations.
- *The country's share of EU imports*: its exports to the EU divided by EU imports of the goods from all countries outside the EU.
- *Rank among EU suppliers*: its position by value among all countries outside the EU supplying the goods, with 1st the largest.

In the CBAM scopes, imports from Iceland, Liechtenstein, Norway and Switzerland are left out, because the
EU CBAM does not apply to them. The shares, ranks and changes are calculated by the Trade Law Observatory
from BACI values. Source: {ct.SOURCE_NAME}; {ct.SOURCE_CITATION}
"""
    )

with limitations_tab:
    st.header("Limitations of the certificate estimate")

    st.subheader("A default value is not producer-specific")
    st.markdown(
        """
A default value is set for a country and a CN code, so it does not vary with the producer. It also carries
a mark-up that rises from 10% in 2026 to 30% from 2028. Where a producer's verified actual emissions are
lower, the default overstates the number of certificates. Actual emissions, verified under the EU rules,
are the alternative, with the monitoring and verification that come with them.
"""
    )

    st.subheader("The production route and the year are assumptions")
    st.markdown(
        """
Where a benchmark depends on the production route, the Calculator uses the route given with the default
value for the country of origin, as the Commission's guidance provides when default values are used. The
year of import is used as the reporting period. Where there is evidence of the actual time of production
in a later year, the reporting period, and so the CBAM factor and the benchmark, can differ. Goods imported
in 2026 are always reported for 2026. For other hydraulic cements containing both white and grey clinker or
calcined clay, the benchmark is a weighted average reflecting the composition, which the Calculator does not
model.
"""
    )

    st.subheader("Prices after 2026 are not published")
    st.markdown(
        """
The published prices apply to goods imported in the first three quarters of 2026. For later imports the
price entered is an assumption. The years offered stop at 2030, the last year for which the cross-sectoral
correction factor has been set.
"""
    )

    st.subheader("Classification and origin are not checked here")
    st.markdown(
        """
The Calculator does not classify goods or determine origin. An incorrect CN code or country returns a
figure without any indication that it is wrong. Electricity is not covered by the estimate. A proposal to
extend the CBAM to further downstream goods is under negotiation; goods that it may add are not covered.
"""
    )

    st.subheader("What the Calculator does not do")
    st.markdown(
        """
- Apply the 50-tonne threshold, which depends on all of an importer's CBAM imports in a year.
- Model actual emissions, precursors, verification, the carbon price report, the CBAM declaration,
  the purchase, surrender or repurchase of certificates, or penalties.
- Forecast how trade will respond to the CBAM, or measure its effect on any country's exports.
- Act as a CBAM declaration, or as advice.
"""
    )

    st.header("Limitations of the trade data")
    st.markdown(
        """
The CBAM list is set at 8-digit level, while BACI reports trade at 6 digits, so a trade figure covers the
whole 6-digit heading that contains a selected code, including goods that may not be CBAM goods. BACI
values are reconciled estimates and will differ from Eurostat and national customs statistics. The EU
figures add up the imports of the 27 member states from outside the EU. The figures describe trade in
2022 to 2024. They are not a forecast. BACI reports some partners as groups, for example "Other Asia, nes",
and does not report a weight for part of the trade. Source: BACI (CEPII), release 202601.
"""
    )

    st.error(
        "These figures are not, on their own, a basis for a contract price, a sourcing change or a CBAM "
        "declaration. Those decisions depend on classification, verified emissions data and professional advice."
    )

with sources_tab:
    st.header("Data and sources")

    st.subheader("Legislation")
    st.markdown(
        """
- [Regulation (EU) 2023/956 establishing a carbon border adjustment mechanism](https://eur-lex.europa.eu/eli/reg/2023/956/oj) — Annex I (goods), Article 7 (embedded emissions), Article 9 (carbon price paid in a third country), Article 31 (free allocation adjustment), Annex III (countries outside the CBAM), Annex VII (50-tonne threshold)
- [Regulation (EU) 2025/2083 amending Regulation (EU) 2023/956](https://eur-lex.europa.eu/eli/reg/2025/2083/oj) — simplification, including the single mass-based threshold
- [Implementing Regulation (EU) 2025/2621 on default values](https://eur-lex.europa.eu/eli/reg_impl/2025/2621/oj) — Annex I, values by country and CN code, and the mark-ups
- [Implementing Regulation (EU) 2026/1740](https://eur-lex.europa.eu/eli/reg_impl/2026/1740/oj) — correcting the default values
- [Implementing Regulation (EU) 2025/2620 on the free allocation adjustment](https://eur-lex.europa.eu/eli/reg_impl/2025/2620/oj) — CBAM benchmarks, Column B
- [Implementing Regulation (EU) 2025/2548 on the price of CBAM certificates](https://eur-lex.europa.eu/eli/reg_impl/2025/2548/oj)
- [Implementing Decision (EU) 2026/1862](https://eur-lex.europa.eu/eli/dec_impl/2026/1862/oj) — cross-sectoral correction factor, 2026 to 2030
"""
    )

    st.subheader("European Commission guidance and data")
    st.markdown(
        f"""
- [CBAM legislation and guidance]({eu.SOURCES['default_values']}) — informational Excel files of the default values (version of 6 August 2026) and of the CBAM benchmarks, which the Calculator uses
- Guidance No. 1, Introduction to CBAM concepts, and Guidance No. 4, Calculation of the free allocation adjustment (14 August 2026), on the same page
- [Price of CBAM certificates]({eu.SOURCES['prices']})
- [CBAM definitive regime](https://taxation-customs.ec.europa.eu/carbon-border-adjustment-mechanism/cbam-definitive-regime_en)
"""
    )
    st.caption(
        "The Excel files are published by the Commission for information; the legally binding values are those "
        "in the Official Journal. The Calculator's values were checked against the Official Journal text for "
        "sample entries. EU legal texts and Commission content are reused under the Commission's reuse policy "
        "(Decision 2011/833/EU)."
    )

    st.subheader("Trade data")
    st.markdown(
        f"""
- [BACI, International Trade Database at the Product Level (CEPII)](http://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37) — HS 2022 edition, release 202601 (22 January 2026), years 2022 to 2024. Values in thousand US dollars, quantities in metric tonnes, products at HS 6-digit level.
- Reference: {ct.SOURCE_CITATION}
"""
    )
    st.caption(
        "BACI is published by CEPII under the " + ct.SOURCE_LICENCE + ". The Calculator holds an extract "
        "limited to the 6-digit headings that contain a CBAM code and heading 2716.00 (electricity), together "
        "with each exporter's total exports and total exports to the UK and to the EU across all products."
    )

st.warning(
    "**For information purposes only.** Nothing on this Calculator is tax, legal or customs advice. Default "
    "values, benchmarks and prices are those published by the European Commission as at the dates shown; "
    "prices after the third quarter of 2026 are not published. The trade figures from BACI describe 2022 to "
    "2024 at 6-digit level and are not a forecast."
)

st.markdown(
    f"""
<div class="tlo-footer">
  <strong>Trade Law Observatory</strong> · EU CBAM Exposure Calculator<br>
  Default values, benchmarks and prices: European Commission; EU legislation: EUR-Lex, © European Union.
  Trade figures: {ct.SOURCE_NAME}, licensed under the {ct.SOURCE_LICENCE}.<br>
  <a href="{TLO_URL}" target="_blank">tradelawobservatory.com</a>
</div>
""",
    unsafe_allow_html=True,
)
