"""UK and EU CBAM side by side: the same goods from the same country under both regimes."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import cbam_data as cd
import cbam_eu as eu
import cbam_trade as ct
import common as cm
from trade_view import _fmt, _hs_label, _rank_text, load_trade

OTHER_CHOICE = -1


def _spaced(code: str) -> str:
    parts = [code[:4], code[4:6], code[6:8]] + ([code[8:]] if len(code) > 8 else [])
    return " ".join(p for p in parts if p)


def _money(value, sign):
    return "n/a" if value is None else f"{sign}{value:,.2f}"


def render(uk_data: pd.DataFrame, eu_data: eu.EUData) -> None:
    st.caption(
        "Compares the same goods from the same country under the UK CBAM and the EU CBAM: the default values, "
        "the estimated charge or certificate cost, and the country's trade with each market. The UK and EU lists "
        "of CBAM goods contain the same 570 8-digit codes. The figures use each regime's own published values "
        "and are not converted into a common currency unless an exchange rate is entered."
    )

    trade_data, trade_error = load_trade()
    baci_to_dv = dict(zip(eu_data.countries["baci_code"].astype(int), eu_data.countries["dv_country"]))
    if trade_data is not None:
        uk_set = dict(ct.country_options(trade_data, "UK"))
        eu_set = dict(ct.country_options(trade_data, "EU"))
        pairs = sorted(((c, n) for c, n in eu_set.items() if c in uk_set), key=lambda item: item[1].lower())
    else:
        pairs = sorted(((int(b), d) for b, d in baci_to_dv.items()), key=lambda item: item[1].lower())
    names = dict(pairs)
    names[OTHER_CHOICE] = "Other or unknown country"

    country = st.selectbox(
        "Country of origin",
        options=[OTHER_CHOICE] + [c for c, _ in pairs],
        format_func=lambda c: names[c],
        index=None,
        key="cmp_country",
        **cm.CONTAINS,
        placeholder="Select the country where the goods were produced",
        help="Decides the EU default value; the UK default value is the same for every country. Countries "
             "outside the EU CBAM (Iceland, Liechtenstein, Norway and Switzerland) and EU member states are not "
             "listed.",
    )

    goods = eu_data.goods.copy()
    goods["display"] = goods.apply(lambda r: f"{_spaced(r['code'])} | {r['description']} [{r['sector']}]", axis=1)
    by_display = dict(zip(goods["display"], goods["code"]))
    labels = st.multiselect(
        "Select CN / commodity code(s)",
        options=goods["display"].tolist(),
        key="cmp_codes",
        placeholder="Type to search, or pick from the list",
        **cm.CONTAINS,
        help="Cement clinker, other hydraulic cement and calcined clay are split into 10-digit TARIC codes on the "
             "EU side, because the EU default value differs between them. The UK has one value for the 8-digit code.",
    )

    first, second, third = st.columns(3)
    with first:
        tonnes = st.number_input("Quantity per code (tonnes)", min_value=0.0, value=1.0, step=1.0, format="%.2f",
                                 key="cmp_tonnes", help="Applied to each selected code.")
    with second:
        year = st.selectbox("Year of import", options=list(eu.YEARS), index=1, key="cmp_year",
                            help="The UK CBAM applies from 1 January 2027, so 2027 is preselected. The year sets the "
                                 "EU mark-up and free allocation adjustment. The UK figures use HMRC's illustrative "
                                 "rates of 16 October 2026 in every year.")
    with third:
        quarter = st.selectbox(
            "EU certificate price", options=list(eu.PRICES), index=len(eu.PRICES) - 1, key="cmp_quarter",
            format_func=lambda q: f"{q} (€{eu.PRICES[q]:.2f})",
            help="The Commission's published price. Prices for imports from 2027 are not yet published, so a 2026 "
                 "price is used as an assumption.",
        )
    price = float(eu.PRICES[quarter])
    fx = st.number_input(
        "Exchange rate, euro per pound (optional)", min_value=0.0, value=None, step=0.0001, format="%.4f",
        key="cmp_fx", placeholder="Leave blank to keep each regime's own currency",
        help="If entered, the EU cost is also shown in pounds. The rate is the user's own figure.",
    )

    if country is None or not labels:
        st.info("Select a country of origin and at least one code to compare the two regimes.")
        _differences()
        return

    dv_country = None if country == OTHER_CHOICE else baci_to_dv.get(int(country))
    where = dv_country or "other countries and territories"
    uk_by_code = uk_data.set_index("commodity_code")
    uk_total, eu_total, blocks = 0.0, 0.0, []
    for label in labels:
        code = by_display[label]
        uk_row = uk_by_code.loc[code[:8]] if code[:8] in uk_by_code.index else None
        uk_value = float(uk_row["default_tco2e_per_tonne"]) if uk_row is not None else None
        uk_rate = cd.ILLUSTRATIVE_RATES.get(str(uk_row["sector"])) if uk_row is not None else None
        uk_per_t = uk_value * uk_rate if uk_value is not None and uk_rate is not None else None
        r = eu.calculate(eu_data, dv_country, code, tonnes, year, price)
        eu_per_t = r["cost_per_tonne"] if r["ok"] else None
        uk_total += (uk_per_t or 0.0) * tonnes
        eu_total += (eu_per_t or 0.0) * tonnes
        if r["ok"]:
            whose = where if r["basis"] == "country" else "other countries and territories"
            eu_cells = [
                f"{r['default_value']:.3f} ({whose})",
                f"{r['mark_up'] * 100:.0f}%, giving {r['see']:.3f}",
                f"{r['sefa']:.3f} deducted ({r['cbam_factor'] * 100:.1f}% × {r['cscf']:.1f} × {r['benchmark']:.3f})",
                f"{r['certificates_per_tonne']:.3f} certificates at €{price:.2f}",
                _money(eu_per_t, "€") + (f" (about {_money(eu_per_t / fx, '£')})" if fx else ""),
                _money(eu_per_t * tonnes, "€") + (f" (about {_money(eu_per_t * tonnes / fx, '£')})" if fx else ""),
            ]
        else:
            eu_cells = ["No default value published"] + ["n/a"] * 5
        uk_cells = [
            f"{uk_value:.3f} (all countries)" if uk_value is not None else "n/a",
            "No separate mark-up",
            "Reflected in the sector rate",
            f"{uk_value:.3f} tCO₂e at £{uk_rate:.2f}" if uk_per_t is not None else "n/a",
            _money(uk_per_t, "£"),
            _money(uk_per_t * tonnes if uk_per_t is not None else None, "£"),
        ]
        measures = [
            "Default value (tCO₂e per tonne)", "Mark-up", "Free allocation (tCO₂e per tonne)",
            "Priced per tonne", "Charge or cost per tonne", f"For {tonnes:,.2f} tonnes",
        ]
        frame = pd.DataFrame({"Measure": measures, "UK CBAM": uk_cells, f"EU CBAM, {year}": eu_cells})
        title = goods.loc[goods["code"] == code, "description"].iloc[0]
        blocks.append((f"{_spaced(code)} · {title}", frame))

    st.subheader("Charge and certificate cost")
    a, b = st.columns(2)
    a.metric("UK CBAM, indicative charge (total)", _money(uk_total, "£"))
    b.metric("EU CBAM, certificate cost (total)", _money(eu_total, "€"))
    if fx:
        b.caption(f"About {_money(eu_total / fx, '£')} at €{fx:.4f} per £.")
    for title, frame in blocks:
        st.markdown(f"**{title}**")
        st.table(frame.set_index("Measure"))
    st.caption(
        "UK: HMRC's default value for the commodity code, the same for every country, multiplied by HMRC's "
        "illustrative sector rate of 16 October 2026; the rate already reflects free allocation. EU: the "
        "Commission's default value for the country of origin (emissions counted for the sector), plus the mark-up "
        "for the year, less the free allocation adjustment (CBAM factor × correction factor × benchmark), priced at "
        f"the {quarter} certificate price. Carbon price relief and deductions are not applied."
    )
    _differences()

    if trade_data is None:
        st.warning("Country trade data could not be loaded. Technical detail: " + str(trade_error))
        return
    if country == OTHER_CHOICE:
        return

    codes = [by_display[label][:8] for label in labels]
    headings = ct.hs6_of(codes)
    c = names[country]
    years = list(ct.YEARS)
    latest, earliest = max(years), min(years)
    res = {m: ct.summarise(trade_data, country, headings, years, market=m) for m in ("UK", "EU")}

    def col(m, scope):
        if scope == "sel":
            now, before = res[m]["years"][latest], res[m]["years"][earliest]
            share_world = now["uk_share_of_selected"]
        else:
            now, before = res[m]["by_sector"][latest][ct.ALL_SECTORS], res[m]["by_sector"][earliest][ct.ALL_SECTORS]
            share_world = now["uk_share"]
        change = ("n/a" if not before["to_uk_value"] or before["to_uk_value"] <= 0
                  else f"{(now['to_uk_value'] / before['to_uk_value'] - 1) * 100:+.1f}%")
        return [_fmt(now["to_uk_value"], "usd"), change, _fmt(share_world, "pct"),
                _fmt(now["share_of_uk_imports"], "pct"), _rank_text(now["uk_rank"], now["uk_suppliers"])]

    st.subheader(f"Trade with each market: {c}, {latest}")
    frame = pd.DataFrame({
        f"Measure, {latest}": [
            f"{c}'s exports (US$ million)", f"Change in {c}'s exports since {earliest}",
            f"Share of {c}'s exports going to the market", f"{c}'s share of the market's imports",
            f"{c}'s rank among the market's suppliers"],
        f"UK, selected goods": col("UK", "sel"),
        f"EU, selected goods": col("EU", "sel"),
        "UK, all CBAM-covered goods": col("UK", "all"),
        "EU, all CBAM-covered goods": col("EU", "all"),
    })
    st.table(frame.set_index(frame.columns[0]))
    st.caption(
        f"Selected goods: the 6-digit headings that contain the selected codes (HS {_hs_label(headings)}). The EU "
        "is the 27 member states, with imports from outside the EU only; imports from Iceland, Liechtenstein, "
        "Norway and Switzerland are left out. EU CBAM-covered goods include electricity (heading 2716.00); UK "
        "CBAM-covered goods do not. Figures are BACI trade values in US dollars and are not a forecast. Source: "
        + ct.SOURCE_NAME + "."
    )
    st.info(
        "**Need more detail?** Comparisons across countries and sectors, full supplier rankings, product-by-product "
        f"exposure and custom dashboards can be prepared on request by the [Trade Law Observatory]({cm.TLO_URL})."
    )


def _differences() -> None:
    with st.expander("How the two regimes differ"):
        st.markdown(
            """
| | UK CBAM | EU CBAM |
| --- | --- | --- |
| Start | 1 January 2027 | Definitive period from 1 January 2026 |
| Sectors | Aluminium, cement, fertilisers, hydrogen, iron and steel | The same five, and electricity |
| Who pays | The importer, once registered | The authorised CBAM declarant, usually the importer |
| How it is paid | A charge: embodied emissions × the sector rate for the quarter | Certificates bought and surrendered for the year's imports |
| Free allocation | Reflected in the sector rate | Deducted per tonne: CBAM factor × correction factor × benchmark |
| Default values | One value per commodity code, for all countries | A value per country and CN code, with a mark-up (10% in 2026, 20% in 2027, 30% from 2028; 1% for fertilisers) |
| Threshold | Registration at £50,000 of CBAM goods in 12 months | Exemption up to 50 tonnes a year (not for hydrogen or electricity) |
| Carbon price paid abroad | Relief under a qualifying scheme | Deduction under Article 9 of Regulation (EU) 2023/956 |

The About tab of each regime sets out the sources.
"""
        )
