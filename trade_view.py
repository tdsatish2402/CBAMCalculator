"""Country trade section, shared by the UK and EU pages. The importing market is "UK" or "EU"."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import cbam_trade as ct
from common import TLO_URL

# How each market is named in the text: (noun with article, adjective).
MARKET_WORDS = {"UK": ("the UK", "UK"), "EU": ("the EU", "EU")}


@st.cache_data(show_spinner=False)
def _read_trade():
    """Read the BACI tables. A failure raises, so it is never cached and the next run retries."""
    return ct.load_tables()


def load_trade():
    """Return (trade data, error text). The error is None when the tables loaded."""
    try:
        return _read_trade(), None
    except Exception as exc:          # noqa: BLE001 - reported on screen, the rest of the app still works
        return None, f"{type(exc).__name__}: {exc}"


def _fmt(value, kind):
    if value is None:
        return "n/a"
    if kind == "usd":
        return f"{value / 1000:,.1f}"
    if kind == "t":
        return f"{value:,.0f}"
    return f"{value * 100:,.1f}%"


def _ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _rank_text(rank, suppliers):
    return f"{_ordinal(rank)} of {suppliers}" if rank else "Not a supplier"


def _hs_label(headings):
    """Short, readable list of 6-digit headings, for example '7326.90' or '7326.90, 7208.10 and 94 more'."""
    shown = [f"{h[:4]}.{h[4:]}" for h in headings[:3]]
    text = ", ".join(shown)
    return text + (f" and {len(headings) - 3} more" if len(headings) > 3 else "")


def render_trade_section(td, country_code, country_name, selected_codes, all_codes, sector_scope=(), market="UK"):
    """Country trade context. Scope is the selected commodity codes (6-digit headings) or, when no code is
    selected, the selected sectors (all sectors if none). Layers: at a glance and the three-year view."""
    years = list(ct.YEARS)
    first, latest = min(years), max(years)
    c = country_name
    T, M = MARKET_WORDS[market]
    codes_word = "CN codes" if market == "EU" else "commodity codes"
    estimate_word = "certificate estimate" if market == "EU" else "charge estimate"
    all_sectors = list(ct.MARKETS[market]["sectors"])
    code_mode = bool(len(selected_codes))
    sector_scope = [name for name in all_sectors if name in set(sector_scope)]

    if code_mode:
        headings = ct.hs6_of(selected_codes)
        scope_name = f"Selected goods (HS {_hs_label(headings)})"
        scope_noun = "the selected goods"
        glance_sectors = ct.sectors_of(td, headings, market)
    else:
        sectors = sector_scope or all_sectors
        headings = td.hs6_names.loc[td.hs6_names["sector"].isin(sectors), "hs6"].tolist()
        glance_sectors = sectors
        if len(sectors) == len(all_sectors):
            scope_noun = "all CBAM-covered goods"
        elif len(sectors) == 1:
            scope_noun = f"goods in the {sectors[0]} sector"
        else:
            scope_noun = "goods in the selected sectors"
        scope_name = scope_noun[0].upper() + scope_noun[1:]

    result = ct.summarise(td, country_code, headings, years, market=market)
    by_year = result["years"]
    start, last = by_year[first], by_year[latest]

    st.subheader(f"Trade exposure: {c}")
    if code_mode:
        st.caption(
            f"{c}'s trade with {T} in the selected goods, {first} to {latest}. The selected goods are the "
            f"6-digit headings that contain the selected {codes_word} (HS {_hs_label(headings)}). Figures are "
            "BACI trade totals in US dollars, by value. They do not depend on the quantity entered above, "
            f"which is used only for the {estimate_word}."
        )
    else:
        st.caption(
            f"{c}'s trade with {T} in {scope_noun}, {first} to {latest}. No {codes_word[:-1]} is selected, so "
            f"the figures cover every 6-digit heading in the sector or sectors. Select {codes_word} above to "
            "narrow them to specific goods. Figures are BACI trade totals in US dollars, by value."
        )

    # Layer 1: at a glance, latest year. Columns are scopes, so the heading-level and sector-wide figures
    # sit side by side.
    def norm(entry, from_year):
        return {
            "to_uk": entry["to_uk_value"],
            "share_world": entry["uk_share_of_selected"] if from_year else entry["uk_share"],
            "share_uk": entry["share_of_uk_imports"],
            "rank": entry["uk_rank"],
            "suppliers": entry["uk_suppliers"],
        }

    columns = []
    if code_mode:
        columns.append((scope_name, norm(last, True), start["to_uk_value"]))
    # With no sector chosen the sector columns would crowd the table.
    shown = glance_sectors if (code_mode or sector_scope) else []
    for name in shown + [ct.ALL_SECTORS, ct.ALL_GOODS]:
        label = name if name in (ct.ALL_SECTORS, ct.ALL_GOODS) else f"{name} (whole sector)"
        columns.append((label, norm(result["by_sector"][latest][name], False),
                        result["by_sector"][first][name]["to_uk_value"]))

    def change_text(now, before):
        return "n/a" if not before or before <= 0 else f"{(now / before - 1) * 100:+.1f}%"

    glance_rows = [
        (f"{c}'s exports to {T} (US$ million)", lambda d, f: _fmt(d["to_uk"], "usd")),
        (f"Change in {c}'s exports to {T} since {first}", lambda d, f: change_text(d["to_uk"], f)),
        (f"Share of {c}'s exports going to {T}", lambda d, f: _fmt(d["share_world"], "pct")),
        (f"{c}'s share of {M} imports", lambda d, f: _fmt(d["share_uk"], "pct")),
        (f"{c}'s rank among {M} suppliers", lambda d, f: _rank_text(d["rank"], d["suppliers"])),
    ]
    st.markdown(f"**At a glance, {latest}: {c} and {T}**")
    glance_frame = pd.DataFrame(
        [[label] + [fn(d, f) for _, d, f in columns] for label, fn in glance_rows],
        columns=[f"Measure, {latest}"] + [title for title, _, _ in columns],
    )
    # A plain table wraps its headings, so it stays within the page however many sectors are selected.
    st.table(glance_frame.set_index(glance_frame.columns[0]))
    st.caption(
        f"Share of {c}'s exports going to {T} = {c}'s exports to {T} divided by {c}'s exports to all "
        f"destinations. {c}'s share of {M} imports = {c}'s exports to {T} divided by {M} imports from all "
        "countries. Both are by value and cover the goods named in the column heading. Rank is by value among "
        f"all countries supplying {T}, with 1st the largest. A whole-sector column covers every 6-digit "
        "heading in the sector, not only the selected goods. The last column covers every product traded, "
        "CBAM-covered or not."
    )
    if market == "EU":
        st.caption(
            "EU imports are imports into the 27 member states from countries outside the EU; trade between "
            "member states is left out. In the CBAM columns, imports from Iceland, Liechtenstein, Norway and "
            "Switzerland are also left out, because the EU CBAM does not apply to them. The all-goods column "
            "includes them."
        )

    def table(title, rows):
        st.markdown(f"**{title}**")
        frame = pd.DataFrame(
            [
                [label] + [
                    _rank_text(by_year[y]["uk_rank"], by_year[y]["uk_suppliers"]) if kind == "rank"
                    else _fmt(by_year[y][key], kind)
                    for y in years
                ]
                for label, key, kind in rows
            ],
            columns=["Measure"] + [str(y) for y in years],
        )
        st.dataframe(frame, hide_index=True, width="stretch")

    # Layer 2: the scope over time (selected goods, or a single chosen sector).
    if code_mode or len(sector_scope) == 1:
        title = scope_name if code_mode else f"{sector_scope[0]} (whole sector)"
        table(f"{title}, {first} to {latest}", [
            (f"{c}'s exports to {T} (US$ million)", "to_uk_value", "usd"),
            (f"{c}'s exports to {T} (tonnes)", "to_uk_tonnes", "t"),
            (f"{c}'s exports to all destinations (US$ million)", "to_world_value", "usd"),
            (f"{M} imports from all countries (US$ million)", "uk_imports_value", "usd"),
            (f"Share of {c}'s exports going to {T}", "uk_share_of_selected", "pct"),
            (f"{c}'s share of {M} imports", "share_of_uk_imports", "pct"),
            (f"{c}'s rank among {M} suppliers", "uk_rank", "rank"),
        ])

    # Further layers (by-sector view, supplier rankings, detail tables) are offered as custom analysis.
    st.info(
        "**Need more detail?** Comparisons across countries and sectors, full supplier rankings, product-by-product "
        "exposure and custom dashboards can be prepared on request by the "
        f"[Trade Law Observatory]({TLO_URL})."
    )

    if result["missing_quantity_uk"] or result["missing_quantity_country"]:
        parts = []
        if result["missing_quantity_uk"]:
            parts.append(f"{M} imports")
        if result["missing_quantity_country"]:
            parts.append(f"{c}'s exports")
        st.caption(
            "BACI does not report the weight (tonnes) for part of the trade in " + " and ".join(parts)
            + ", so the tonnes shown for it may be understated. Values in US dollars are not affected."
        )

    st.caption(
        "The CBAM scope is set at 8-digit level and BACI reports at 6 digits, so these figures can include "
        "trade in goods that are not CBAM goods. BACI values are reconciled estimates and will differ from "
        "national customs statistics. The figures describe trade in 2022 to 2024. They are not a forecast "
        "of how trade will respond to CBAM. Source: " + ct.SOURCE_NAME + "."
    )
