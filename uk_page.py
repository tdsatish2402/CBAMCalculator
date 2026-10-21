"""UK CBAM Exposure Calculator page - a public information and planning tool."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

import cbam_data as cd
import cbam_trade as ct
import common as cm
from trade_view import load_trade, render_trade_section

_CONTAINS = cm.CONTAINS
MARK = cm.MARK
TLO_URL = cm.TLO_URL

st.set_page_config(
    page_title="UK CBAM Exposure Calculator | Trade Law Observatory",
    page_icon=str(MARK) if MARK else "🌍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CACHE_TTL_SECONDS = 12 * 60 * 60

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_dataset():
    frame, status = cd.get_dataset(prefer_live=True)
    return frame, status


def parse_pasted_codes(text: str) -> list[str]:
    """Read commodity codes from free text.

    Handles codes written with spaces inside them (7208 10 00), several codes on
    one line separated by spaces or commas, and 10-digit UK commodity codes,
    which are reduced to the 8-digit level the CBAM dataset uses.
    """
    codes: list[str] = []
    for token in re.split(r"[,;\n\r\t|]+", text):
        digits = re.sub(r"\D", "", token)
        if not digits:
            continue
        if len(digits) == 8:
            codes.append(digits)
        elif len(digits) == 10:
            codes.append(digits[:8])
        elif len(digits) % 8 == 0:
            codes.extend(digits[i:i + 8] for i in range(0, len(digits), 8))
        elif len(digits) % 10 == 0:
            codes.extend(digits[i:i + 10][:8] for i in range(0, len(digits), 10))
        else:
            codes.append(digits.zfill(8))
    return list(dict.fromkeys(codes))


def add_pasted_codes(by_code):
    """Button callback: add pasted codes to the selection. Runs before the page is redrawn."""
    wanted = parse_pasted_codes(st.session_state.get("paste_box", ""))
    matched = [by_code[code] for code in wanted if code in by_code]
    st.session_state["paste_unmatched"] = [code for code in wanted if code not in by_code]
    if matched:
        st.session_state["code_select"] = list(dict.fromkeys(st.session_state.get("code_select", []) + matched))


def money(value) -> str:
    return "—" if value is None else f"£{value:,.2f}"


st.title("UK CBAM Exposure Calculator")
st.markdown('<div class="tlo-rule"></div>', unsafe_allow_html=True)
st.caption(
    "Estimates the UK Carbon Border Adjustment Mechanism (CBAM) charge on imported goods from HMRC's "
    "published default emissions values and illustrative sector rates, and summarises exporting country's "
    "trade with the UK for 2022 to 2024, from BACI data."
)

with st.spinner("Loading the official UK default-value tables..."):
    data, status = load_dataset()

# A routine, successful retrieval is reported at the foot of the page. Anything that affects the
# reliability of the figures (changed values, or the baseline in use) is shown here, at the top.
if status.origin == "live" and not status.matches_baseline:
    st.error(
        "**The published default values have changed since the Calculator's verified baseline of "
        f"{status.baseline_as_at}.** The figures below are the current GOV.UK values. Treat any "
        "earlier estimate as superseded."
    )
    with st.expander("What changed", expanded=True):
        if status.changed:
            st.dataframe(
                pd.DataFrame(status.changed, columns=["Sector and code", "Baseline", "Current"]),
                hide_index=True,
                width="stretch",
            )
        if status.added:
            st.write("Codes added: " + ", ".join(status.added))
        if status.removed:
            st.write("Codes no longer published: " + ", ".join(status.removed))
elif status.origin != "live":
    st.info(
        f"**Default values: verified snapshot of {status.baseline_as_at}.** The automatic check against "
        "the GOV.UK tables did not complete, so the snapshot is in use. The GOV.UK pages remain the "
        "authoritative source."
    )
    with st.expander("Technical detail on the GOV.UK check"):
        for problem in status.fetch_errors:
            st.caption(problem)

with st.sidebar:
    st.header("Data status")
    st.metric("Default values loaded", f"{status.row_count:,}")
    st.caption("Source: " + ("live GOV.UK pages" if status.origin == "live" else "verified baseline"))
    if status.retrieved_at:
        st.caption(f"Last retrieved: {status.retrieved_at}")
    st.caption(f"Verified baseline: {status.baseline_as_at}")
    st.divider()
    st.caption(
        "GOV.UK is re-checked every 12 hours and every value is compared against the verified "
        "baseline."
    )
    if st.button("Check GOV.UK for updates now", width="stretch"):
        load_dataset.clear()
        st.rerun()
    st.divider()
    st.caption(cd.ILLUSTRATIVE_RATE_BASIS)
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
        "**1. CBAM charge estimate.** Select a sector and commodity code(s) at 8-digit level, then enter a "
        "quantity.\n\n"
        "**2. Partner country trade data.** Select an exporting country to see its trade with the UK for "
        "2022 to 2024, at 6-digit level, in the selected commodity codes or sector(s), if no code is "
        "selected. The country selection does not change the charge."
    )

    data = data.copy()
    data["display"] = data.apply(
        lambda row: f"{row['commodity_code']} | {row['description']} [{row['sector']}]", axis=1
    )
    by_code = {row["commodity_code"]: row["display"] for _, row in data.iterrows()}

    if "code_select" not in st.session_state:
        st.session_state["code_select"] = []

    sector_choice = st.multiselect(
        "Select CBAM sector",
        key="sector_choice",
        options=sorted(data["sector"].unique().tolist()),
        default=[],
        placeholder="All sectors",
        help="Narrows the list of commodity codes below. Leave empty to include all five sectors.",
    )

    scoped = data if not sector_choice else data[data["sector"].isin(sector_choice)]

    # The search box sits below the code list, so its text is read from the previous interaction.
    search_text = str(st.session_state.get("search_box", "") or "")
    if search_text.strip():
        needle = search_text.strip().lower()
        scoped = scoped[
            scoped["commodity_code"].str.contains(re.sub(r"\D", "", needle) or needle, na=False)
            | scoped["description"].str.lower().str.contains(needle, na=False)
        ]

    options = list(dict.fromkeys(scoped["display"].tolist() + st.session_state["code_select"]))
    selected_labels = st.multiselect(
        "Select commodity code(s)",
        options=options,
        key="code_select",
        placeholder="Type to search, or pick from the list",
        **_CONTAINS,
        help=(
            "These are UK commodity codes from the official dataset. A code used in another "
            "jurisdiction should not be assumed to be the UK code."
        ),
    )

    st.text_input(
        "Or search by commodity code or description",
        key="search_box",
        placeholder="For example 7208, ammonia, or hot-rolled",
        help="Narrows the list in the box above. Clear it to see every code in the selected sectors.",
    )

    with st.expander("Or paste a list of commodity codes"):
        st.caption(
            "Paste codes separated by commas, spaces or new lines. Spaces inside a code are "
            "ignored, so 7208 10 00 and 72081000 both work."
        )
        st.text_area("Commodity codes", key="paste_box", height=90, label_visibility="collapsed")
        st.button("Add these codes", on_click=add_pasted_codes, args=(by_code,))

    if st.session_state.get("paste_unmatched"):
        st.warning(
            "Not found in the published dataset: "
            + ", ".join(st.session_state["paste_unmatched"])
            + ". Check the code against the scope guidance; it may not be a CBAM good."
        )

    trade_data, trade_error = load_trade()
    country_choice = None
    country_names = {}
    if trade_data is not None:
        country_pairs = ct.country_options(trade_data)
        country_names = dict(country_pairs)
        country_choice = st.selectbox(
            "Exporting country (optional): adds a trade analysis from BACI data",
            options=[code for code, _ in country_pairs],
            format_func=lambda code: country_names[code],
            index=None,
            key="country_choice",
            **_CONTAINS,
            placeholder="Select a country to add its trade with the UK in the selected goods",
            help=(
                "Adds a trade section using BACI data at 6-digit level for 2022 to 2024. It covers the "
                "selected commodity codes or, if none is selected, the selected sector(s), or all five "
                "sectors if no sector is selected. It does not change the charge estimate."
            ),
        )
    else:
        st.warning(
            "Country trade data could not be loaded, so the country analysis is unavailable. "
            "The charge estimate is not affected. Technical detail: " + str(trade_error)
        )

    if not selected_labels:
        if trade_data is not None and country_choice is not None:
            st.info(
                "Select at least one commodity code to start a charge estimate. The trade figures below "
                "cover the selected sector(s) until codes are selected."
            )
        else:
            st.info("Select at least one commodity code to start an estimate.")
        if trade_data is not None and country_choice is not None:
            render_trade_section(
                trade_data, country_choice, country_names[country_choice], [], data, sector_choice
            )
        st.subheader("Published default values")
        st.caption(
            "HMRC's default emissions values by commodity code, in tonnes of CO₂ equivalent per tonne of product. "
            "Open a sector to see its table."
        )
        sectors_listed = [name for name in cd.SECTOR_URLS if name in set(scoped["sector"])]
        open_all = len(sectors_listed) == 1 or bool(search_text.strip())
        for name in sectors_listed:
            part = scoped[scoped["sector"] == name]
            with st.expander(f"{name} ({len(part):,} {'code' if len(part) == 1 else 'codes'})", expanded=open_all):
                st.dataframe(
                    part[["commodity_code", "description", "default_tco2e_per_tonne"]].rename(
                        columns={
                            "commodity_code": "Code",
                            "description": "Official description",
                            "default_tco2e_per_tonne": "tCO₂e / t product",
                        }
                    ),
                    width="stretch",
                    hide_index=True,
                    height=min(380, 38 + 35 * len(part)),
                    column_config={"tCO₂e / t product": st.column_config.NumberColumn(format="%.3f", width="small")},
                )
    else:
        selected = data[data["display"].isin(selected_labels)].reset_index(drop=True)
        records = []

        # With more than a few codes, the per-code inputs go in a collapsed box so the totals and the
        # trade section stay in view.
        many_codes = len(selected) > 5
        holder = (
            st.expander(f"Enter quantities and rates for the {len(selected)} selected codes", expanded=False)
            if many_codes else st
        )

        for _, item in selected.iterrows():
            code = str(item["commodity_code"])
            sector = str(item["sector"])
            description = str(item["description"])
            factor = float(item["default_tco2e_per_tonne"])
            unit_label, unit_type = cd.functional_unit(sector, code)
            caveat = cd.basis_caveat(sector, code)
            key = f"{sector}_{code}"

            with holder.container(border=True):
                st.markdown(f"**{code} · {sector}**")
                st.caption(description)
                st.caption(f"Default value {factor:.3f} tCO₂e per tonne of product · functional unit: {unit_label}")

                special = unit_type in {cd.UNIT_NITROGEN, cd.UNIT_CLINKER}
                basis = "Tonnes of product"
                if special:
                    basis = st.radio(
                        "Quantity basis",
                        options=["Tonnes of product", f"Functional unit ({unit_label})"],
                        horizontal=True,
                        key=f"basis_{key}",
                        help=(
                            "Either basis gives the same result, because the published value is "
                            "expressed per tonne of product. Entering the functional unit requires "
                            "composition data so the quantity can be converted."
                        ),
                    )
                entering_fu = basis.startswith("Functional unit")
                quantity_label = unit_label if entering_fu else "tonnes of product"

                left, right = st.columns(2)
                with left:
                    quantity = st.number_input(
                        f"Quantity ({quantity_label})",
                        min_value=0.0,
                        value=None,
                        step=0.01,
                        format="%.2f",
                        key=f"quantity_{key}",
                        placeholder=f"Enter {quantity_label}",
                    )
                with right:
                    rate = st.number_input(
                        "Illustrative CBAM rate (£/tCO₂e)",
                        min_value=0.0,
                        value=float(cd.ILLUSTRATIVE_RATES.get(sector, 0.0)),
                        step=0.01,
                        format="%.2f",
                        key=f"rate_{key}",
                        help="Prefilled with the illustrative rate. Replace with the official quarterly rate.",
                    )

                composition = None
                if unit_type == cd.UNIT_NITROGEN:
                    composition = st.number_input(
                        f"Nitrogen content ({cd.COMPOSITION_LABELS[cd.UNIT_NITROGEN]})",
                        min_value=0.0, max_value=1000.0, value=None, step=1.0, format="%.2f",
                        key=f"composition_{key}",
                        placeholder="Declared nitrogen content",
                        help="Use the supplier's declaration or the product specification.",
                    )
                elif unit_type == cd.UNIT_CLINKER:
                    composition = st.number_input(
                        f"Clinker content ({cd.COMPOSITION_LABELS[cd.UNIT_CLINKER]})",
                        min_value=0.0, max_value=1.0, value=None, step=0.01, format="%.4f",
                        key=f"composition_{key}",
                        placeholder="Clinker fraction, 0 to 1",
                        help="A fraction between 0 and 1, not a percentage. Needed for the clinker-basis comparison.",
                    )
                elif unit_type == cd.UNIT_CLINKER_SELF:
                    st.caption("This code is cement clinker itself, so one tonne of product is one tonne of clinker.")

                if caveat:
                    st.caption(f"⚠️ {caveat}")

                with st.expander("assumed carbon price relief (optional)"):
                    st.write(
                        "Leave at zero unless relief has been established separately. It depends on "
                        "what the producing installation actually paid under a qualifying overseas "
                        "scheme, evidenced on HMRC's carbon pricing verification form, and is capped "
                        "at the charge itself. It is not a deduction for energy taxes, levies or "
                        "production costs, and this Calculator does not determine eligibility."
                    )
                    relief = st.number_input(
                        "Verified potential relief (£)",
                        min_value=0.0, value=0.0, step=1.0, format="%.2f", key=f"relief_{key}",
                    )

            entered = float(quantity) if quantity is not None else None
            comp = float(composition) if composition not in (None, 0.0) else None
            product_tonnes = None
            incomplete_reason = None

            if entered is None:
                incomplete_reason = "quantity not entered"
            elif entering_fu and not comp:
                incomplete_reason = (
                    "nitrogen content not entered" if unit_type == cd.UNIT_NITROGEN else "clinker content not entered"
                )
            else:
                product_tonnes = entered / comp if entering_fu else entered

            if product_tonnes is None:
                attributed = gross = net = clinker_tonnes = alt_attributed = alt_gross = None
            else:
                attributed = product_tonnes * factor
                gross = attributed * float(rate)
                net = max(0.0, gross - float(relief))
                if unit_type == cd.UNIT_CLINKER_SELF:
                    clinker_tonnes = product_tonnes
                elif unit_type == cd.UNIT_CLINKER:
                    clinker_tonnes = entered if entering_fu else (product_tonnes * comp if comp else None)
                else:
                    clinker_tonnes = None
                alt_attributed = clinker_tonnes * factor if clinker_tonnes is not None else None
                alt_gross = alt_attributed * float(rate) if alt_attributed is not None else None

            if gross is not None and alt_gross is not None and abs(alt_gross - gross) > 0.005:
                st.info(
                    f"**{code}: the published value can be read two ways.** Per tonne of product, "
                    f"{money(gross)} on {attributed:,.3f} tCO₂e. Per tonne of clinker, "
                    f"{money(alt_gross)} on {alt_attributed:,.3f} tCO₂e. The first is used in the "
                    "totals. See the Limitations tab."
                )

            records.append({
                "Code": code,
                "Sector": sector,
                "Official description": description,
                "Functional unit (force of law)": unit_label,
                "Quantity basis entered": quantity_label,
                "Entered quantity": entered,
                "Composition per tonne of product": comp if comp is not None else (1.0 if unit_type == cd.UNIT_CLINKER_SELF else None),
                "Composition unit": cd.COMPOSITION_LABELS.get(unit_type, "Not applicable"),
                "Quantity (t product)": product_tonnes,
                "Default value (tCO₂e/t product)": factor,
                "Emissions (tCO₂e)": attributed,
                "Rate (£/tCO₂e)": float(rate),
                "Indicative charge (£)": gross,
                "Relief entered (£)": float(relief),
                "After relief (£)": net,
                "Clinker-basis emissions (tCO₂e)": alt_attributed,
                "Clinker-basis charge (£)": alt_gross,
                "Basis caveat": caveat,
                "Incomplete because": incomplete_reason,
            })

        results = pd.DataFrame(records)
        ready = results[results["Incomplete because"].isna()]
        relief_used = float(results["Relief entered (£)"].sum()) > 0

        st.subheader("Estimated exposure")

        missing = results[results["Incomplete because"].notna()]
        if not missing.empty:
            if len(missing) <= 5:
                st.warning(
                    "Excluded from the totals: "
                    + "; ".join(f"{row['Code']} ({row['Incomplete because']})" for _, row in missing.iterrows())
                    + "."
                )
            else:
                st.warning(
                    f"{len(missing)} of the {len(results)} selected codes are excluded from the totals "
                    "because a quantity has not been entered for them."
                )
                with st.expander("Codes excluded from the totals"):
                    st.dataframe(
                        missing[["Code", "Sector", "Incomplete because"]], hide_index=True, width="stretch"
                    )

        if ready.empty:
            st.info("No complete calculations yet.")
        else:
            first, second, third = st.columns(3)
            first.metric("Embodied emissions (total)", f"{ready['Emissions (tCO₂e)'].sum():,.3f} tCO₂e")
            third.metric("Codes in the totals", f"{len(ready):,} of {len(results):,}")
            if relief_used:
                second.metric("Indicative charge after relief (total)", money(ready["After relief (£)"].sum()))
                st.caption(
                    f"Before relief: {money(ready['Indicative charge (£)'].sum())}. Relief entered: "
                    f"{money(ready['Relief entered (£)'].sum())}."
                )
            else:
                second.metric("Indicative charge (total)", money(ready["Indicative charge (£)"].sum()))

            st.caption(
                "Calculated on the illustrative rates unless they have been replaced. These are not the "
                "rates that will apply from 1 January 2027."
            )

            summary_columns = ["Code", "Quantity (t product)", "Emissions (tCO₂e)", "Indicative charge (£)"]
            if relief_used:
                summary_columns.append("After relief (£)")
            with st.expander(f"Estimate by commodity code ({len(ready)} {'code' if len(ready) == 1 else 'codes'})", expanded=not many_codes):
                st.dataframe(
                    ready[summary_columns],
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Code": st.column_config.TextColumn(width="small"),
                        "Quantity (t product)": st.column_config.NumberColumn(format="%.3f", width="small"),
                        "Emissions (tCO₂e)": st.column_config.NumberColumn(format="%.3f", width="small"),
                        "Indicative charge (£)": st.column_config.NumberColumn(format="£%.2f", width="small"),
                        "After relief (£)": st.column_config.NumberColumn(format="£%.2f", width="small"),
                    },
                )


        if trade_data is not None and country_choice is not None:
            render_trade_section(
                trade_data, country_choice, country_names[country_choice],
                selected["commodity_code"].tolist(), data, sector_choice
            )

    st.divider()
    st.caption(
        "**Basis.** Charge estimate: quantity in tonnes multiplied by the default value for the 8-digit "
        "commodity code, multiplied by the sector rate (SI 2026/995, reg. 4; Finance Act 2026, s.149(1)). "
        "Trade analysis: " + ct.SOURCE_NAME + ", 6-digit headings, values in US dollars, 2022 to 2024. "
        "See the Limitations and Data and sources tabs."
    )
    st.caption(
        "**Sources.** "
        f"[HMRC, Check the default values for the CBAM]({cd.PUBLICATION_PAGE}) (16 October 2026); "
        "[HMRC, Illustrative CBAM rates and worked example](https://www.gov.uk/government/publications/"
        "illustrative-cbam-rates-and-worked-example-for-carbon-border-adjustment-mechanism-cbam) "
        "(16 October 2026); [CEPII, BACI](http://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37) "
        "(" + ct.SOURCE_CITATION + ")."
    )

# --------------------------------------------------------------------------
# About
# --------------------------------------------------------------------------

with about_tab:
    st.header("About")

    st.subheader("What the Calculator does")
    st.markdown(
        f"""
The Calculator has two parts:

**1. Charge estimate.** For each selected 8-digit commodity code, the Calculator multiplies the quantity
by the default emissions value HMRC published for that code and by a sector rate, to give an indicative
CBAM charge. The default values are read from GOV.UK
and checked against a verified baseline of 16 October 2026. The rates are HMRC's illustrative rates of
16 October 2026 and can be replaced. The estimate does not determine whether a good is in scope, whether
a business is liable, or what the rate will be, and it does not replace the calculation HMRC prescribes.

**2. Country trade data.** Where an exporting country is selected, the Calculator shows that country's
trade with the UK for 2022 to 2024 in the selected goods or, if no commodity code is selected, in the
selected sector(s). It uses {ct.SOURCE_NAME}, at 6-digit level. For each scope it gives the country's
exports to the UK, the share of its exports that go to the UK, its share of UK imports and its rank among
the UK's suppliers, with the whole sector, all CBAM-covered goods and all goods shown alongside. The
figures describe past trade. They are not a forecast and do not measure the effect of the charge.

The Calculator is intended for exporters to the UK, importers, advisers and analysts who need a first
estimate of the charge across a product range, and a view of how much of an exporting country's trade
with the UK is in CBAM-covered goods. It is not a substitute for a classification ruling, emissions
monitoring and verification, a CBAM return, or professional advice.
"""
    )

    st.subheader("The UK CBAM in brief")
    st.markdown(
        """
From 1 January 2027 the United Kingdom will charge CBAM on the carbon emissions embodied in
imported goods. Five sectors are covered: aluminium, cement, fertilisers, hydrogen, and iron and
steel. The charge falls on the importer.

Liability is tied to registration, which is triggered by value rather than volume: importing CBAM
goods worth **£50,000 or more** in the preceding twelve months, or expecting to import that value
within the next thirty days.

"""
    )

    st.subheader("How the charge is worked out")
    st.markdown(
        """
The charge is the embodied emissions of the imported goods, multiplied by the sector rate, less any
eligible carbon price relief. Embodied emissions are the quantity of goods multiplied by the
emissions figure for the commodity code.

The Calculator applies this calculation using the published default value as the emissions figure, an
illustrative rate, and any relief amount entered by the user.

"""
    )

    st.subheader("1. Quantity")
    st.markdown(
        """

For most goods the quantity is tonnes of product. The technical rules set two exceptions: for
fertilisers the measure is kilograms of nitrogen contained in the goods, and for four cement codes it
is tonnes of clinker contained in the goods.

The published tables are expressed per tonne of product, and HMRC's guidance describes the
calculation as weight multiplied by the default value. The Calculator accepts either basis and
converts between them using composition data entered by the user. For the four cement codes it shows
both readings, because they give different results and the published position does not resolve
which applies.

"""
    )

    st.subheader("2. Emissions")
    st.markdown(
        """

An importer can establish the emissions embodied in its goods in one of two ways: verified actual
emissions data from the overseas installation that produced them, monitored and verified under the
UK rules, or the default value HMRC publishes for the commodity code.

On 16 October 2026 HMRC published 570 default values across the five sectors, in tonnes of CO2
equivalent per tonne of product. The published tables give one value for each commodity code. A producer's
own emissions intensity may sit above or below that figure. Where it
sits below, the default will overstate the charge, and verified actual data will produce a lower
result at the cost of monitoring and verification. Where it sits above, the default will produce a
lower charge than the producer's actual figure would.

Two procedural points apply to the choice of route.

- **Amendment of a return.** HMRC's guidance on the default values states, of a return that uses
  them, "you cannot amend it later with actual emissions data". HMRC's policy summary states that a
  liable person will be able to amend a return to correct an error, within three years. The pages
  reviewed do not address whether replacing default values with actual data counts as such a
  correction, and the position should be confirmed with HMRC before it is relied on.
- **Combining default values and actual data.** Default values may be used for precursor goods while
  actual data is used for the processes that turn those precursors into the finished good. The
  reverse is not available: once a default value is used for the finished good, the calculation is
  weight multiplied by that value, with no route to add precursor emissions.

"""
    )

    st.subheader("3. The rate")
    st.markdown(
        """

A single rate applies to each sector for the relevant quarter, so goods imported across a year are
charged at several different rates. It is built from the average UK ETS auction clearing price for
the preceding quarter, reduced to reflect the free allowances a comparable UK producer still
receives. The deduction for free allocation falls each year as free allocation is phased out.

From 1 January 2027 HMRC will publish rates by the beginning of each quarter. Until then the
Calculator uses HMRC's illustrative rates of 16 October 2026.

HMRC's worked example for cement starts from an average UK ETS price of £58.15 for the third
quarter of 2026, applies free allocation of 87.1% and a 2027 reduction factor of 97.5%, and arrives
at £8.78 per tonne. The reduction factor is the same for all five sectors. The free allocation share
differs, and the illustrative rates range from £9.79 for aluminium to £1.45 for fertiliser.

"""
    )

    st.subheader("4. Relief for a carbon price already paid")
    st.markdown(
        """

Where the emissions in imported goods have already been subject to a carbon price under a
qualifying overseas scheme, the UK charge can be reduced. Relief cannot exceed the CBAM liability.

**Qualifying schemes.** A qualifying scheme is a carbon tax or emissions trading scheme run by a
government or supranational body, which controls how the revenue is used. Participation must be
required by law for the installation concerned, the rules, scope and headline price must be public,
and emissions must be priced directly or, indirectly, through fossil fuel use. Voluntary schemes and
fuel duties do not qualify. HMRC's list of current qualifying schemes was published as a draft on
27 August 2026, based on information available as of 19 June 2026. It is not exhaustive and is kept
under review.

**What is needed.** Relief is claimed on installation-level data. A carbon pricing verification form
is required, completed by an independent, accredited verifier and obtained from the installation or
its supply chain. HMRC states that relief cannot be claimed without it. The scheme's own published
prices are also needed, including the headline price and any graduated prices or compensation. A
default value is a figure for a commodity code and does not carry this data.

**Default values and relief.** Relief is the effective carbon price multiplied by the emissions
embodied in the good (SI 2026/809, reg. 13(1)). The regulations allow a notice to make provision
about using default values to calculate those embodied emissions (reg. 13(3)(b)). Neither the
regulations nor the HMRC guidance reviewed states whether relief can be claimed where default
values are used, and none of the provisions reviewed excludes it. The position should be confirmed
with HMRC.

**How relief is worked out.** HMRC's guidance sets out the steps:

1. Take the installation's total emissions, as stated on the form, for one of the two calendar years
   before the year of import.
2. Multiply the emissions subject to each element of the scheme, such as the headline price, by that
   element's price, using the average price over the calendar quarter before the import. Emissions
   covered by free allowances, or below a threshold, are given no price but remain in the total.
3. Divide the result by the total emissions. This is the effective carbon price. Because emissions
   with no price stay in the total, it can be lower than the headline price.
4. Where the form lists compensation, such as a rebate or refund, received or due for the same
   calendar year, divide it by the total emissions and subtract it.
5. Multiply the effective carbon price by the embodied emissions to which the scheme applied. A
   result in a foreign currency is converted to sterling at the rate for the calendar quarter before
   import and rounded down to two decimal places. HMRC is to publish exchange rates from 1 January
   2027.

The Calculator does not calculate relief. The relief field is a manual input for an amount
established separately, and it does not establish eligibility.
"""
    )


    st.subheader("Reading the trade figures")
    st.markdown(
        f"""
**Scopes.** Each column or row of the trade tables covers one scope. *Selected goods* are the 6-digit
headings (HS 2022) that contain the selected commodity codes. *Whole sector* is every 6-digit heading in
one of the five CBAM sectors. *All CBAM-covered goods* is every heading in the five sectors. *All goods*
is every product the country trades, CBAM-covered or not.

**Measures.** For an exporting country and a scope, all by value in US dollars:

- *Exports to the UK*: the value of the country's exports of the goods to the UK, with the change since 2022.
- *Share of the country's exports going to the UK*: its exports to the UK divided by its exports to all destinations.
- *The country's share of UK imports*: its exports to the UK divided by UK imports of the goods from all countries.
- *Rank among UK suppliers*: its position by value among all countries supplying the goods to the UK, with 1st the largest.

The shares, ranks and changes are calculated by the Trade Law Observatory from BACI values. Source:
{ct.SOURCE_NAME}; {ct.SOURCE_CITATION}
"""
    )


# --------------------------------------------------------------------------
# Limitations
# --------------------------------------------------------------------------

with limitations_tab:
    st.header("Limitations of the charge estimate")

    st.subheader("The rates are illustrative, and they change every quarter")
    st.markdown(
        """
The prefilled rates — aluminium £9.79, iron and steel £9.69, hydrogen £9.24, cement £8.78 and
fertiliser £1.45 per tonne of CO2 equivalent — are HMRC's illustrative figures of 16 October 2026.
HMRC states they are illustrative only, should not be read as forecasts, create no liability, and
rest on baseline data still being checked.

The rate is recalculated each quarter. Applying a single rate to imports across several quarters is
a simplification.
"""
    )

    st.subheader("The cement figures could mean one of two things")
    st.markdown(
        """
For clinker, white Portland, grey Portland and other cement, the technical rules make the measure
tonnes of clinker, while the published table is expressed per tonne of product. The published
figures do not settle which applies: clinker is 1.433, white Portland 1.425, grey Portland 1.375
and other cement 1.441, within about 5% of each other, although blended cements contain
considerably less clinker per tonne of product.

On 1,000 tonnes of Portland cement at a clinker factor of 0.75, one reading gives roughly
**£12,073** and the other roughly **£9,054**. The Calculator shows both and uses the product-weight
reading in the totals. The basis should be confirmed with HMRC before either figure is relied on
for cement.
"""
    )

    st.subheader("The fertiliser treatment involves a judgement")
    st.markdown(
        """
The nitrogen measure is stated for "fertilisers" without a list of codes, so the Calculator applies
it across all 27 codes on the fertiliser list, including nitric acid, ammonia and potassium
nitrate. That is an interpretation rather than a quoted rule.

The result is arithmetically unchanged: because the published values are per tonne of product,
entering a nitrogen quantity with its matching nitrogen content returns the same answer as entering
the product tonnage. The nitrogen basis is offered for consistency with the technical definition.
"""
    )

    st.subheader("A default value is not producer-specific")
    st.markdown(
        """
The published tables give one value for each commodity code, so the figure does not vary with the
producer. Where a producer's actual emissions intensity is lower than the default, the default
overstates the charge, and the Calculator overstates that producer's exposure with it. Where it is higher, the reverse applies. The
alternative to a default value is verified actual emissions data, with the monitoring and
verification requirements that come with it.
"""
    )

    st.subheader("Classification is not checked here")
    st.markdown(
        """
Scope is defined by commodity code at mixed levels of detail, with exclusions sitting inside
otherwise covered headings. The Calculator does not classify goods: an incorrect code returns a
figure without any indication that the code is wrong.

A code used in another jurisdiction should not be assumed to match the UK code. Classification can
be confirmed against the UK Trade Tariff and the scope guidance.
"""
    )

    st.subheader("Relief is not calculated here")
    st.markdown(
        """
Relief depends on what a particular installation paid under a qualifying scheme, evidenced on
HMRC's carbon pricing verification form. The relief field on the Calculator is a manual input for a
figure established elsewhere. The Calculator does not establish eligibility, and relief is not a
general deduction for energy taxes, levies or production costs.
"""
    )

    st.header("Limitations of the trade data")

    st.subheader("The trade figures are at 6-digit level")
    st.markdown(
        f"""
The CBAM list is set at 8-digit level, while BACI reports trade at 6 digits. A trade figure therefore
covers the whole 6-digit heading that contains a selected code. That includes CBAM codes that were
not selected and, where a heading is only partly covered, goods that are not CBAM goods. The
8-digit charge estimate is not affected. Source: {ct.SOURCE_NAME}.
"""
    )

    st.subheader("BACI figures are estimates, not customs statistics")
    st.markdown(
        f"""
BACI reconciles the declarations of exporting and importing countries into one set of bilateral
trade flows. Its values are estimates and will differ from national customs statistics. Source:
{ct.SOURCE_CITATION}
"""
    )

    st.subheader("The figures are historical and descriptive")
    st.markdown(
        """
The figures describe trade in 2022 to 2024. They are not a forecast of how trade will respond to CBAM,
and they do not measure the effect of the charge. A share of a country's exports going to the UK, or of
UK imports, describes the trading relationship. It does not indicate how much of the charge a country's
exporters would bear. Source: BACI (CEPII), release 202601.
"""
    )

    st.subheader("Some partners are groups, and weights are incomplete")
    st.markdown(
        """
BACI reports some partners as groups of economies rather than single countries, for example "Other
Asia, nes" and "Europe EFTA, nes". For part of the trade in some headings BACI does not report a weight,
so the tonnes shown may be understated. Values in US dollars are not affected. Source: BACI (CEPII),
release 202601.
"""
    )

    st.header("Limitations of both parts")

    st.subheader("What the Calculator does not do")
    st.markdown(
        """
- Test the £50,000 registration threshold. A business below it may have no liability at all.
- Model precursor emissions, the treatment of indirect emissions, verification requirements,
  return and payment mechanics, exemptions, goods under special customs procedures, or penalties.
- Forecast how trade will respond to CBAM, or measure the effect of the charge on any country's exports.
- Act as a CBAM return, or as advice.
"""
    )

    st.subheader("What the data check covers")
    st.markdown(
        f"""
The Calculator reads the default values from the five GOV.UK pages whenever the cache expires, and
checks each fetch before use: the expected number of entries in every sector, eight-digit codes, no
duplicates, and values within a plausible range. A fetch that fails is discarded, the verified
baseline of {cd.BASELINE_AS_AT} is shown instead, and the Calculator says so. Any difference between
the live tables and that baseline is reported at the top of the Calculator.

The baseline was checked entry by entry against the GOV.UK pages and, for the 478 iron and steel
entries, against HMRC's PDF of that table, with no discrepancy found. That establishes that the
Calculator reproduces the published values. It does not validate the methodology behind them, and it
does not resolve the questions set out above.
"""
    )

    st.error(
        "These figures are not, on their own, a basis for a contract price, a sourcing change or a "
        "submission to HMRC. Those decisions depend on a classification ruling, verified emissions "
        "data and professional advice."
    )

# --------------------------------------------------------------------------
# Data and sources
# --------------------------------------------------------------------------

with sources_tab:
    st.header("Data and sources")

    st.subheader("Primary legislation")
    st.markdown(
        """
- [Finance Act 2026 (c. 11), Part 5, sections 142 to 158](https://www.legislation.gov.uk/ukpga/2026/11/part/5) — the charge (s.143), importation (s.144), special customs procedures (s.145), person liable (s.146), exemptions (s.147), embodied emissions (s.148), rate (s.149), carbon price relief (s.150), administration and enforcement (s.151), offences (s.152), commencement (s.158)
- [Schedule 16 — CBAM goods](https://www.legislation.gov.uk/ukpga/2026/11/schedule/16)
- [Schedule 17, Part 2 — registration and the £50,000 threshold](https://www.legislation.gov.uk/ukpga/2026/11/schedule/17/part/2)
"""
    )

    st.subheader("Regulations")
    st.markdown(
        """
- [The CBAM (Emissions and Verification) Regulations 2026, SI 2026/995](https://www.legislation.gov.uk/uksi/2026/995/made) — default values (reg. 2), the default-value route (reg. 4), the actual-emissions calculation (reg. 5), precursor goods (reg. 7), verification reports (reg. 16)
- [The CBAM (Calculation of CBAM Rate and Determination of Carbon Price Relief) Regulations 2026, SI 2026/809](https://www.legislation.gov.uk/uksi/2026/809/made) — average UK ETS price (reg. 3), free-allocation factor (reg. 4), effective carbon price and relief (regs. 12 and 13)
- [The CBAM (Administrative Provisions) Regulations 2026, SI 2026/802](https://www.legislation.gov.uk/uksi/2026/802/made) — return contents (reg. 10), determination of weight (reg. 12)
"""
    )

    st.subheader("Force of law notices and technical reference")
    st.markdown(
        """
- [Force of law notices and reference document](https://www.gov.uk/government/publications/carbon-border-adjustment-mechanism-force-of-law-notice-and-reference-document)
- [Administrative Provisions and Determination of Carbon Price Relief Force of Law Notice (draft)](https://www.gov.uk/government/publications/carbon-border-adjustment-mechanism-force-of-law-notice-and-reference-document/the-carbon-border-adjustment-mechanism-force-of-law-notice-draft)
- [System Boundaries Document, version 1.00](https://www.gov.uk/government/publications/carbon-border-adjustment-mechanism-force-of-law-notice-and-reference-document/carbon-border-adjustment-mechanism-system-boundaries-document-version-100) — functional units at section 1(7)
"""
    )

    st.subheader("HMRC guidance")
    st.markdown(f"- [Check the default values for the CBAM]({cd.PUBLICATION_PAGE}) — the publication the Calculator reads")
    for sector, url in cd.SECTOR_URLS.items():
        st.markdown(f"    - [{sector} default values]({url})")
    st.markdown(
        """
- [Illustrative CBAM rates and worked example](https://www.gov.uk/government/publications/illustrative-cbam-rates-and-worked-example-for-carbon-border-adjustment-mechanism-cbam)
- [Rates for the CBAM](https://www.gov.uk/guidance/rates-for-the-carbon-border-adjustment-mechanism-cbam)
- [CBAM policy summary](https://www.gov.uk/government/publications/carbon-border-adjustment-mechanism-cbam-policy-summary/carbon-border-adjustment-mechanism-cbam-policy-summary)
- [Check which goods are in scope](https://www.gov.uk/government/publications/check-which-goods-are-in-scope-of-carbon-border-adjustment-mechanism-cbam)
- [Getting the emissions intensity when importing CBAM goods](https://www.gov.uk/guidance/getting-the-emissions-intensity-when-importing-carbon-border-adjustment-mechanism-cbam-goods)
- [Work out the date you will need to register](https://www.gov.uk/guidance/work-out-the-date-youll-need-to-register-for-carbon-border-adjustment-mechanism-cbam)
- [Current qualifying carbon pricing schemes](https://www.gov.uk/government/publications/uk-cbam-current-qualifying-carbon-pricing-schemes)
- [Keeping records for CBAM](https://www.gov.uk/guidance/keeping-records-for-carbon-border-adjustment-mechanism-cbam)
"""
    )

    st.caption(
        "Legislation is reproduced from legislation.gov.uk under the Open Government Licence v3.0. "
        "Guidance content contains public sector information licensed under the Open Government "
        "Licence v3.0."
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
        "limited to the 6-digit headings that contain a CBAM commodity code, together with each exporter's "
        "total exports and total exports to the UK across all products. Shares, ranks and changes are "
        "calculated by the Trade Law Observatory from these values."
    )


# --------------------------------------------------------------------------
# Notices (below the tabs, above the footer)
# --------------------------------------------------------------------------

st.warning(
    "**For information purposes only.** Nothing on this Calculator is tax, legal or customs advice. "
    "The sector rates are HMRC's illustrative figures of 16 October 2026, not the rates that will apply. "
    "The trade figures from BACI describe 2022 to 2024 at 6-digit level and are not a forecast."
)

# --------------------------------------------------------------------------
# Footer
# --------------------------------------------------------------------------

st.markdown(
    f"""
<div class="tlo-footer">
  <strong>Trade Law Observatory</strong> · UK CBAM Exposure Calculator<br>
  Default values: GOV.UK, public sector information licensed under the Open Government Licence v3.0
  (verified baseline as at {cd.BASELINE_AS_AT}). Trade figures: {ct.SOURCE_NAME}, licensed under the
  {ct.SOURCE_LICENCE}.<br>
  <a href="{TLO_URL}" target="_blank">tradelawobservatory.com</a>
</div>
""",
    unsafe_allow_html=True,
)
