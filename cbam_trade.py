"""Trade context for the CBAM Exposure Calculator (UK and EU markets).

Source: BACI, International Trade Database at the Product Level (CEPII), HS 2022 edition,
release 202601. BACI reports trade at HS 6-digit level. Values are in thousand US dollars and
quantities in metric tonnes. The CBAM commodity codes are 8-digit, so every figure here is for the
whole 6-digit heading that contains the selected codes.

The data files next to this module were prepared from the BACI release by build_baci_tables.py
and hold only the headings that contain at least one CBAM commodity code, plus 2716.00 (electricity,
EU CBAM only). Two importing markets are covered: the UK, and the EU-27 taken together (imports from
outside the EU only).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
UK_CODE = 826
YEARS = (2022, 2023, 2024)
SECTORS = ("Aluminium", "Cement", "Fertilisers", "Hydrogen", "Iron and steel")
EU_SECTORS = SECTORS + ("Electricity",)
# The 27 EU member states, by BACI country code. Their trade with each other is outside the EU CBAM.
EU27 = frozenset({40, 56, 100, 191, 196, 203, 208, 233, 246, 251, 276, 300, 348, 372, 380, 428, 440, 442, 470,
                  528, 616, 620, 642, 703, 705, 724, 752})

# Iceland, Liechtenstein, Norway and Switzerland are outside the EU CBAM (Annex III to Regulation (EU) 2023/956),
# so their sales into the EU are left out of the EU's CBAM-goods figures.
EU_CBAM_EXEMPT = frozenset({352, 438, 579, 757})

# Each importing market: the trade columns that hold its imports, its all-goods table, the exporters
# that cannot supply it under CBAM, and the sectors in scope.
MARKETS = {
    "UK": {"col": "uk", "all_table": "uk_all", "all_col": "v_uk_all", "excluded": frozenset({UK_CODE}),
           "sectors": SECTORS},
    "EU": {"col": "eu", "all_table": "eu_all", "all_col": "v_eu_all", "excluded": EU27 | EU_CBAM_EXEMPT,
           "sectors": EU_SECTORS},
}
ALL_SECTORS = "All CBAM-covered goods"
ALL_GOODS = "All goods (CBAM and non-CBAM)"

SOURCE_NAME = "BACI (CEPII), HS 2022 edition, release 202601"
SOURCE_CITATION = (
    "Gaulier, G. and Zignago, S. (2010), BACI: International Trade Database at the Product-Level. "
    "The 1994-2007 Version, CEPII Working Paper No. 2010-23."
)
SOURCE_LICENCE = "Etalab Open Licence 2.0"


@dataclass(frozen=True)
class TradeData:
    trade: pd.DataFrame      # year, exporter, hs6, v_world, q_world, nq_world, v_uk, q_uk, nq_uk, v_eu, q_eu, nq_eu
    totals: pd.DataFrame     # year, exporter, v_all   (all goods, all destinations)
    countries: pd.DataFrame  # country_code, country_name, country_iso2, country_iso3
    hs6_names: pd.DataFrame  # hs6, description
    uk_all: pd.DataFrame     # year, exporter, v_uk_all   (all goods sold to the UK)
    eu_all: pd.DataFrame     # year, exporter, v_eu_all   (all goods sold into the EU from outside it)


def load_tables(folder: Path | None = None) -> TradeData:
    folder = Path(folder) if folder else HERE
    trade = pd.read_csv(folder / "baci_cbam_trade.csv.gz", dtype={"hs6": str})
    trade["hs6"] = trade["hs6"].str.zfill(6)
    totals = pd.read_csv(folder / "baci_exporter_totals.csv")
    countries = pd.read_csv(folder / "baci_countries.csv")
    names = pd.read_csv(folder / "baci_hs6_names.csv", dtype={"hs6": str})
    names["hs6"] = names["hs6"].str.zfill(6)
    uk_all = pd.read_csv(folder / "baci_uk_all_goods.csv")
    eu_path = folder / "baci_eu_all_goods.csv"
    eu_all = pd.read_csv(eu_path) if eu_path.exists() else pd.DataFrame(columns=["year", "exporter", "v_eu_all"])
    return TradeData(trade, totals, countries, names, uk_all, eu_all)


def country_options(td: TradeData, market: str = "UK") -> list[tuple[int, str]]:
    """Exporting countries with any CBAM-coded exports in the data, by name. The importing market itself
    (the UK, or the 27 EU member states) is left out."""
    codes = set(td.trade.loc[td.trade["v_world"] > 0, "exporter"].unique()) - set(MARKETS[market]["excluded"])
    names = td.countries.set_index("country_code")["country_name"]
    options = [(int(c), str(names.get(c, f"Country {c}"))) for c in codes]
    return sorted(options, key=lambda item: item[1].lower())


def hs6_of(commodity_codes) -> list[str]:
    """Reduce 8-digit commodity codes to their distinct 6-digit headings."""
    return sorted({str(code).strip()[:6] for code in commodity_codes})


def _ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _rank(frame: pd.DataFrame, country_code: int, column: str = "v_uk"):
    """Rank of a country among a market's suppliers (1 = largest by value) and the number of suppliers.

    Ties share the better rank. Returns (None, count) when the country supplied nothing."""
    by_supplier = frame.groupby("exporter")[column].sum()
    by_supplier = by_supplier[by_supplier > 0]
    mine = float(by_supplier.get(country_code, 0.0))
    if mine <= 0:
        return None, int(len(by_supplier))
    return int((by_supplier > mine).sum()) + 1, int(len(by_supplier))


def top_suppliers(td: TradeData, headings, year: int, country_code: int | None = None, n: int = 5,
                  market: str = "UK") -> pd.DataFrame:
    """A market's largest suppliers of the given headings in one year, with the chosen country added if outside the top n."""
    headings = [str(h).zfill(6) for h in headings]
    rows = td.trade[(td.trade["year"] == year) & (td.trade["hs6"].isin(headings))]
    by_supplier = rows.groupby("exporter")["v_" + MARKETS[market]["col"]].sum()
    by_supplier = by_supplier[by_supplier > 0].sort_values(ascending=False)
    total = float(by_supplier.sum())
    names = td.countries.set_index("country_code")["country_name"]
    ranked = pd.DataFrame({"exporter": by_supplier.index, "value": by_supplier.values})
    ranked["rank"] = ranked["value"].rank(method="min", ascending=False).astype(int)
    keep = ranked.head(n)
    if country_code is not None and country_code in set(ranked["exporter"]) and country_code not in set(keep["exporter"]):
        keep = pd.concat([keep, ranked[ranked["exporter"] == country_code]])
    keep = keep.assign(
        supplier=keep["exporter"].map(lambda c: str(names.get(c, f"Country {c}"))),
        share=keep["value"] / total if total > 0 else None,
    )
    return keep[["rank", "supplier", "value", "share"]].reset_index(drop=True)


def sectors_of(td: TradeData, headings, market: str = "UK") -> list[str]:
    """The sectors that contain the given 6-digit headings, in the standard order."""
    mapping = td.hs6_names.set_index("hs6")["sector"]
    found = {mapping[h] for h in headings if h in mapping.index}
    return [s for s in MARKETS[market]["sectors"] if s in found]


def summarise(td: TradeData, country_code: int, headings, years=YEARS, market: str = "UK") -> dict:
    """Trade measures for one exporting country and a set of 6-digit headings, by year, for one importing
    market ("UK" or "EU"). The result keys keep the "uk_" names for both markets: for "EU" they hold the
    EU-27's imports from outside the EU.

    Returns {"years": {year: {measure: value or None}},
             "by_sector": {year: {sector or ALL_SECTORS: {measure: value or None}}},
             "missing_quantity_uk": bool, "missing_quantity_country": bool}.
    Values are in thousand US dollars and tonnes as reported; shares are fractions (0 to 1).
    """
    headings = [str(h).zfill(6) for h in headings]
    spec = MARKETS[market]
    sector_of = td.hs6_names.set_index("hs6")["sector"]
    in_scope = set(td.hs6_names.loc[td.hs6_names["sector"].isin(spec["sectors"]), "hs6"])
    trade = td.trade[td.trade["hs6"].isin(in_scope)]
    # The market's import columns are read under the UK names, so the measures below serve both markets.
    if spec["col"] != "uk":
        trade = trade[~trade["exporter"].isin(spec["excluded"])]
        trade = trade.drop(columns=["v_uk", "q_uk", "nq_uk"]).rename(
            columns={"v_" + spec["col"]: "v_uk", "q_" + spec["col"]: "q_uk", "nq_" + spec["col"]: "nq_uk"})
    all_goods_table = getattr(td, spec["all_table"]).rename(columns={spec["all_col"]: "v_uk_all"})
    out: dict[int, dict] = {}
    by_sector: dict[int, dict] = {}
    missing_uk = False        # some UK import flows of the selected headings have no reported quantity
    missing_country = False   # some of the selected country's flows have no reported quantity

    for year in years:
        rows = trade[trade["year"] == year]
        selected = rows[rows["hs6"].isin(headings)]
        country_all = rows[rows["exporter"] == country_code]
        country_sel = selected[selected["exporter"] == country_code]

        total_row = td.totals[(td.totals["year"] == year) & (td.totals["exporter"] == country_code)]
        total_exports = float(total_row["v_all"].iloc[0]) if len(total_row) else None

        m = {
            # The UK as a market for the selected headings, from every source.
            "uk_imports_value": float(selected["v_uk"].sum()),
            "uk_imports_tonnes": float(selected["q_uk"].sum()),
            # The selected country's exports of the selected headings.
            "to_uk_value": float(country_sel["v_uk"].sum()),
            "to_uk_tonnes": float(country_sel["q_uk"].sum()),
            "to_world_value": float(country_sel["v_world"].sum()),
            "to_world_tonnes": float(country_sel["q_world"].sum()),
            # The selected country's exports of every CBAM-coded heading.
            "cbam_to_uk_value": float(country_all["v_uk"].sum()),
            "cbam_to_world_value": float(country_all["v_world"].sum()),
            "total_exports_value": total_exports,
        }
        m["uk_rank"], m["uk_suppliers"] = _rank(selected, country_code)
        m["share_of_uk_imports"] = _ratio(m["to_uk_value"], m["uk_imports_value"])
        m["uk_share_of_selected"] = _ratio(m["to_uk_value"], m["to_world_value"])
        m["selected_share_of_cbam"] = _ratio(m["to_world_value"], m["cbam_to_world_value"])
        m["uk_share_of_cbam"] = _ratio(m["cbam_to_uk_value"], m["cbam_to_world_value"])
        m["cbam_share_of_total"] = _ratio(m["cbam_to_world_value"], total_exports)
        m["uk_cbam_share_of_total"] = _ratio(m["cbam_to_uk_value"], total_exports)
        out[year] = m

        rows_with_sector = rows.assign(sector=rows["hs6"].map(sector_of))
        per_sector = {}
        for name in list(spec["sectors"]) + [ALL_SECTORS]:
            part = rows_with_sector if name == ALL_SECTORS else rows_with_sector[rows_with_sector["sector"] == name]
            mine = part[part["exporter"] == country_code]
            entry = {
                "uk_imports_value": float(part["v_uk"].sum()),
                "to_uk_value": float(mine["v_uk"].sum()),
                "to_world_value": float(mine["v_world"].sum()),
            }
            entry["uk_rank"], entry["uk_suppliers"] = _rank(part, country_code)
            entry["share_of_uk_imports"] = _ratio(entry["to_uk_value"], entry["uk_imports_value"])
            entry["uk_share"] = _ratio(entry["to_uk_value"], entry["to_world_value"])
            per_sector[name] = entry
        # All goods, CBAM and non-CBAM: the UK's total imports and the country's total sales to the UK and the world.
        uk_year = all_goods_table[all_goods_table["year"] == year].set_index("exporter")["v_uk_all"]
        uk_year = uk_year[uk_year > 0]
        mine_uk = float(uk_year.get(country_code, 0.0))
        all_goods = {
            "uk_imports_value": float(uk_year.sum()),
            "to_uk_value": mine_uk,
            "to_world_value": total_exports if total_exports is not None else 0.0,
            "uk_rank": int((uk_year > mine_uk).sum()) + 1 if mine_uk > 0 else None,
            "uk_suppliers": int(len(uk_year)),
        }
        all_goods["share_of_uk_imports"] = _ratio(mine_uk, all_goods["uk_imports_value"])
        all_goods["uk_share"] = _ratio(mine_uk, total_exports)
        per_sector[ALL_GOODS] = all_goods
        by_sector[year] = per_sector

        missing_uk = missing_uk or bool(selected["nq_uk"].sum() > 0)
        missing_country = missing_country or bool(country_sel["nq_world"].sum() > 0)

    return {
        "years": out,
        "by_sector": by_sector,
        "missing_quantity_uk": missing_uk,
        "missing_quantity_country": missing_country,
    }


def heading_table(td: TradeData, commodity_codes_all: pd.DataFrame, selected_codes) -> pd.DataFrame:
    """One row per 6-digit heading: its BACI description, CBAM codes inside it, and how many are selected."""
    selected_codes = [str(c) for c in selected_codes]
    headings = hs6_of(selected_codes)
    names = td.hs6_names.set_index("hs6")["description"]
    all_codes = commodity_codes_all["commodity_code"].astype(str)
    rows = []
    for h in headings:
        in_heading = all_codes[all_codes.str[:6] == h]
        rows.append({
            "HS6 heading": h,
            "BACI description": str(names.get(h, "")),
            "CBAM codes in heading": int(len(in_heading)),
            "Selected": int(sum(1 for c in selected_codes if c[:6] == h)),
        })
    return pd.DataFrame(rows)
