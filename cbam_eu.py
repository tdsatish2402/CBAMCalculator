"""EU CBAM: default values, benchmarks and the calculation of CBAM certificates (definitive period).

Sources (all informational Excel files and guidance published by the European Commission, DG TAXUD):
- Default values: Implementing Regulation (EU) 2025/2621, Annex I, as corrected by Implementing Regulation
  (EU) 2026/1740 (Commission Excel file, version of 6 August 2026). Values are set by country of origin.
- CBAM benchmarks: Implementing Regulation (EU) 2025/2620, Annex, point 5, Column B (Commission Excel file).
- CBAM factor and cross-sectoral correction factor: Commission Guidance No. 4, Table 2-1 (14 August 2026); the
  correction factor for 2026 to 2030 is set by Implementing Decision (EU) 2026/1862.
- Certificate prices: Commission, "Price of CBAM certificates" page (Implementing Regulation (EU) 2025/2548).

Calculation where default values are used (Commission Guidance No. 1 and No. 4):
    specific embedded emissions (SEE) = default value x (1 + mark-up for the year)
    free allocation adjustment (SEFA) = CBAM factor x CSCF x CBAM benchmark (Column B)
    certificates per tonne            = max(0, SEE - SEFA)
    cost                              = certificates per tonne x quantity x certificate price
Indirect emissions count only for cement and fertilisers. Electricity is not covered here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OTHER = "Other Countries and Territories"
SECTORS = ("Aluminium", "Cement", "Fertilisers", "Hydrogen", "Iron and steel")
INDIRECT_COUNTED = {"Cement", "Fertilisers"}

# Mark-up on default values (IR 2025/2621 as corrected): 10% in 2026, 20% in 2027, 30% from 2028;
# fertilisers 1% from 2026.
def mark_up(sector: str, year: int) -> float:
    if sector == "Fertilisers":
        return 0.01
    return 0.10 if year <= 2026 else 0.20 if year == 2027 else 0.30

# CBAM factor (Article 10a(1a), Directive 2003/87/EC) and the cross-sectoral correction factor, from
# Commission Guidance No. 4, Table 2-1 (CSCF for 2026-2030: Implementing Decision (EU) 2026/1862). The years
# offered stop at 2030, the last year with a set CSCF value.
CBAM_FACTOR = {2026: 0.975, 2027: 0.95, 2028: 0.90, 2029: 0.775, 2030: 0.515}
CSCF = {2026: 1.0, 2027: 1.0, 2028: 1.0, 2029: 1.0, 2030: 1.0}
YEARS = tuple(CBAM_FACTOR)

# Published certificate prices (EUR per tonne of CO2e), by quarter of import in 2026.
PRICES = {"Q1 2026": 75.36, "Q2 2026": 75.28, "Q3 2026": 82.32}
PRICES_AS_AT = "Q4 2026 price due 4 January 2027; weekly prices from 2027"

SOURCES = {
    "default_values": "https://taxation-customs.ec.europa.eu/carbon-border-adjustment-mechanism/cbam-legislation-and-guidance_en",
    "prices": "https://taxation-customs.ec.europa.eu/carbon-border-adjustment-mechanism/price-cbam-certificates_en",
    "regulation": "https://eur-lex.europa.eu/eli/reg/2023/956/oj",
    "ir_2025_2621": "https://eur-lex.europa.eu/eli/reg_impl/2025/2621/oj",
    "ir_2026_1740": "https://eur-lex.europa.eu/eli/reg_impl/2026/1740/oj",
    "ir_2025_2620": "https://eur-lex.europa.eu/eli/reg_impl/2025/2620/oj",
}

ROUTES = {
    "A": "grey clinker or cement", "B": "white clinker or cement",
    "C": "carbon steel, blast furnace / basic oxygen furnace", "D": "carbon steel, direct reduced iron / EAF",
    "E": "carbon steel, scrap / EAF", "F": "low-alloy steel, blast furnace / basic oxygen furnace",
    "G": "low-alloy steel, direct reduced iron / EAF", "H": "low-alloy steel, scrap / EAF",
    "J": "high-alloy steel, EAF", "K": "primary aluminium", "L": "secondary aluminium",
}


@dataclass(frozen=True)
class EUData:
    values: pd.DataFrame      # country, code, sector, direct, indirect, total, route
    benchmarks: pd.DataFrame  # code, sector, bm_b, parameter
    goods: pd.DataFrame       # code, description, sector
    countries: pd.DataFrame   # dv_country, baci_code


def load(folder: Path | None = None) -> EUData:
    folder = Path(folder) if folder else HERE
    values = pd.read_csv(folder / "eu_default_values.csv.gz", dtype={"code": str})
    benchmarks = pd.read_csv(folder / "eu_benchmarks.csv", dtype={"code": str})
    goods = pd.read_csv(folder / "eu_goods.csv", dtype={"code": str})
    countries = pd.read_csv(folder / "eu_country_map.csv")
    return EUData(values, benchmarks, goods, countries)


def _best_match(rows: pd.DataFrame, code: str):
    """The default-value row whose code is the longest prefix of the selected code (codes are listed at
    4-, 6-, 8- and 10-digit level)."""
    hits = rows[[code.startswith(c) for c in rows["code"]]]
    if hits.empty:
        return None
    return hits.loc[hits["code"].str.len().idxmax()]


def default_value(data: EUData, country: str | None, code: str):
    """(row, basis). The country's own value where one is given; otherwise the value for other countries
    and territories, as Annex I requires where a country is not listed or its field shows '-'."""
    if country and country != OTHER:
        own = _best_match(data.values[data.values["country"] == country], code)
        if own is not None and pd.notna(own["total"]):
            return own, "country"
    other = _best_match(data.values[data.values["country"] == OTHER], code)
    return other, "other"


def benchmark(data: EUData, code: str, route: str | None, year: int):
    """Column B benchmark for the good, chosen by the production route given with the default value and,
    where the benchmark changes over time, by year ((1) for 2026-27, (2) for 2028-30)."""
    rows = data.benchmarks[data.benchmarks["code"] == code[:8]]
    if rows.empty:
        return None, None
    period = "(1)" if year <= 2027 else "(2)"
    letters = [l for l in "ABCDEFGHJKL" if route and f"({l})" in route]
    if len(rows) == 1:
        r = rows.iloc[0]
        return float(r["bm_b"]), r["parameter"] if isinstance(r["parameter"], str) else None
    def fits(param):
        p = param if isinstance(param, str) else ""
        letter_ok = (not letters) or any(f"({l})" in p for l in letters) or not any(ch in p for ch in "ABCDEFGHJKL")
        period_ok = ("(1)" not in p and "(2)" not in p) or period in p
        return letter_ok and period_ok
    chosen = rows[rows["parameter"].map(fits)]
    if chosen.empty:
        return None, None
    r = chosen.iloc[0]
    return float(r["bm_b"]), r["parameter"]


def resolved_values(data: EUData, country: str | None) -> pd.DataFrame:
    """The default value that applies to every selectable good for one country of origin."""
    rows = []
    for _, good in data.goods.iterrows():
        row, basis = default_value(data, country, good["code"])
        ok = row is not None and pd.notna(row["total"])
        rows.append({
            "code": good["code"], "description": good["description"], "sector": good["sector"],
            "direct": float(row["direct"]) if ok and pd.notna(row["direct"]) else None,
            "indirect": float(row["indirect"]) if ok and pd.notna(row["indirect"]) else None,
            "total": float(row["total"]) if ok else None,
            "route": row["route"] if ok and isinstance(row["route"], str) else None,
            "basis": basis if ok else None,
        })
    return pd.DataFrame(rows)


def calculate(data: EUData, country: str | None, code: str, tonnes: float, year: int, price: float,
              deduction: float = 0.0) -> dict:
    """CBAM certificates and cost for one good from one country of origin, using default values."""
    row, basis = default_value(data, country, code)
    if row is None or pd.isna(row["total"]):
        return {"ok": False, "reason": "no default value published for this code"}
    sector = str(row["sector"])
    counted = float(row["total"]) if sector in INDIRECT_COUNTED else float(row["direct"])
    up = mark_up(sector, year)
    see = counted * (1 + up)
    bm, param = benchmark(data, code, row["route"] if isinstance(row["route"], str) else None, year)
    if bm is None:
        return {"ok": False, "reason": "no matching CBAM benchmark"}
    sefa = CBAM_FACTOR[year] * CSCF[year] * bm
    per_tonne = max(0.0, see - sefa)
    certificates = per_tonne * tonnes
    gross = certificates * price
    # A carbon price effectively paid in the country of origin reduces the number of certificates
    # (Article 9 of Regulation (EU) 2023/956). It is entered as an amount in euro, established separately.
    net = max(0.0, gross - deduction)
    net_certificates = net / price if price > 0 else certificates
    return {
        "ok": True, "sector": sector, "basis": basis, "dv_code": row["code"],
        "route": row["route"] if isinstance(row["route"], str) else None, "benchmark_parameter": param,
        "default_value": counted, "mark_up": up, "see": see, "benchmark": bm,
        "cbam_factor": CBAM_FACTOR[year], "cscf": CSCF[year], "sefa": sefa,
        "certificates_per_tonne": per_tonne, "embedded_emissions": see * tonnes,
        "certificates": certificates, "cost": gross, "cost_after_deduction": net,
        "certificates_after_deduction": net_certificates,
        "cost_per_tonne": per_tonne * price,
    }
