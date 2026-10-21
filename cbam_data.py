"""Shared data layer for the UK CBAM Exposure Calculator.

Responsibilities
----------------
1. Fetch the five official GOV.UK default-value tables.
2. Validate a fetch before it is trusted (expected row counts, 8-digit codes,
   plausible values). An unvalidated fetch is never used.
3. Fall back to a verified baseline snapshot if the live fetch fails or fails
   validation, so the published dashboard keeps working.
4. Report any difference between the live tables and the baseline, so a
   revision by HMRC is visible rather than silent.
5. Classify the UK CBAM functional unit for each commodity code.

The parser lives here only. app.py, build_dataset.py and build_excel_workbook.py
all import it, so there is one place to fix if GOV.UK changes its page structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

# --------------------------------------------------------------------------
# Official sources
# --------------------------------------------------------------------------

PUBLICATION_PAGE = (
    "https://www.gov.uk/government/publications/"
    "check-the-default-values-for-the-carbon-border-adjustment-mechanism-cbam"
)

SECTOR_URLS = {
    "Aluminium": f"{PUBLICATION_PAGE}/aluminium-default-values",
    "Cement": f"{PUBLICATION_PAGE}/cement-default-values",
    "Fertilisers": f"{PUBLICATION_PAGE}/fertilisers-default-values",
    "Hydrogen": f"{PUBLICATION_PAGE}/hydrogen-default-values",
    "Iron and steel": f"{PUBLICATION_PAGE}/iron-and-steel-default-values",
}

# Row counts in the tables published on 16 October 2026, verified entry by entry
# against the GOV.UK pages and the HMRC PDF of the iron and steel table.
# A live fetch that does not return these counts is treated as incomplete.
EXPECTED_ROW_COUNTS = {
    "Aluminium": 58,
    "Cement": 6,
    "Fertilisers": 27,
    "Hydrogen": 1,
    "Iron and steel": 478,
}
EXPECTED_TOTAL_ROWS = sum(EXPECTED_ROW_COUNTS.values())  # 570

BASELINE_FILE = Path(__file__).with_name("cbam_default_values_baseline.csv")
BASELINE_AS_AT = "2026-10-16"
BASELINE_NOTE = (
    "Baseline snapshot of the default values published on 16 October 2026. "
    "All 570 entries were checked entry by entry against the five GOV.UK sector "
    "pages and, for iron and steel, against the HMRC PDF of that table."
)

# Illustrative rates published by HMRC on 16 October 2026. These are NOT the
# rates that will apply from 1 January 2027.
# https://www.gov.uk/government/publications/illustrative-cbam-rates-and-worked-example-for-carbon-border-adjustment-mechanism-cbam
ILLUSTRATIVE_RATES = {
    "Aluminium": 9.79,
    "Cement": 8.78,
    "Fertilisers": 1.45,
    "Hydrogen": 9.24,
    "Iron and steel": 9.69,
}
ILLUSTRATIVE_RATE_BASIS = (
    "Illustrative rates published 16 October 2026, derived from a 58.15 GBP/tCO2e "
    "average UK ETS auction clearing price for Q3 2026 and a 97.5% free-allocation "
    "phase-out factor for 2027. HMRC states they are illustrative only, are not "
    "forecasts, and create no liability."
)

# --------------------------------------------------------------------------
# Functional units
# --------------------------------------------------------------------------
# CBAM System Boundaries Document v1.00, section 1(7):
#   general rule  - the functional unit is tonnes of goods;
#   exception (a) - fertilisers: kilograms of nitrogen contained in the goods;
#   exception (b) - commodity codes 2523 10 00, 2523 21 00, 2523 29 00 and
#                   2523 90 00: tonnes of clinker contained in the goods.
# The published default-value tables are headed "per tonne of product", and the
# emissions-intensity guidance says embodied emissions are the weight of the good
# multiplied by the default value. This calculator therefore converts a quantity
# entered in a special functional unit back to tonnes of product before applying
# the default value, and flags the cement codes where that reading is uncertain.

CLINKER_FUNCTIONAL_UNIT_CODES = {"25231000", "25232100", "25232900", "25239000"}
CLINKER_SELF_CODE = "25231000"

UNIT_PRODUCT = "product"
UNIT_NITROGEN = "nitrogen"
UNIT_CLINKER = "clinker"
UNIT_CLINKER_SELF = "clinker_self"

UNIT_LABELS = {
    UNIT_PRODUCT: "tonnes of product",
    UNIT_NITROGEN: "kg nitrogen",
    UNIT_CLINKER: "tonnes clinker",
    UNIT_CLINKER_SELF: "tonnes clinker",
}

COMPOSITION_LABELS = {
    UNIT_NITROGEN: "kg nitrogen per tonne of product",
    UNIT_CLINKER: "tonnes clinker per tonne of product",
}


def normalise_code(commodity_code) -> str:
    """Strip spaces and punctuation from a commodity code and pad to 8 digits."""
    return re.sub(r"\D", "", str(commodity_code)).zfill(8)


def functional_unit(sector: str, commodity_code) -> tuple[str, str]:
    """Return (display label, unit type) for a commodity code."""
    code = normalise_code(commodity_code)
    if sector == "Fertilisers":
        return UNIT_LABELS[UNIT_NITROGEN], UNIT_NITROGEN
    if sector == "Cement" and code in CLINKER_FUNCTIONAL_UNIT_CODES:
        unit = UNIT_CLINKER_SELF if code == CLINKER_SELF_CODE else UNIT_CLINKER
        return UNIT_LABELS[unit], unit
    return UNIT_LABELS[UNIT_PRODUCT], UNIT_PRODUCT


def basis_caveat(sector: str, commodity_code) -> str:
    """Return a caveat where the basis of the published value is not settled."""
    code = normalise_code(commodity_code)
    if sector == "Cement" and code in CLINKER_FUNCTIONAL_UNIT_CODES:
        return (
            "Basis unsettled. The published table is headed per tonne of product, "
            "but the force-of-law functional unit for this code is tonnes of clinker. "
            "Both bases are shown; confirm with HMRC before relying on either."
        )
    if sector == "Fertilisers":
        return (
            "The functional unit for the fertiliser sector is kilograms of nitrogen. "
            "The published value is expressed per tonne of product, so the entered "
            "nitrogen quantity is converted to tonnes of product using the declared "
            "nitrogen content."
        )
    return ""


# --------------------------------------------------------------------------
# Fetching and validation
# --------------------------------------------------------------------------

USER_AGENT = "UK-CBAM-Exposure-Calculator/2.0 (planning tool; contact site owner)"
COLUMNS = [
    "sector",
    "commodity_code",
    "description",
    "default_tco2e_per_tonne",
    "source_url",
]


@dataclass
class DatasetStatus:
    """What the app knows about the data it is holding."""

    origin: str = "unknown"          # "live", "baseline" or "none"
    retrieved_at: str = ""
    baseline_as_at: str = BASELINE_AS_AT
    row_count: int = 0
    sector_counts: dict = field(default_factory=dict)
    fetch_errors: list = field(default_factory=list)
    validation_errors: list = field(default_factory=list)
    changed: list = field(default_factory=list)   # (code, baseline value, live value)
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)

    @property
    def matches_baseline(self) -> bool:
        return not (self.changed or self.added or self.removed)

    @property
    def is_trustworthy(self) -> bool:
        return self.origin in {"live", "baseline"} and not self.validation_errors


def _parse_sector_page(sector: str, url: str, html: str) -> list[dict]:
    """Extract the default-value rows from one GOV.UK sector page."""
    tables = pd.read_html(StringIO(html))

    table = None
    for candidate in tables:
        columns = [str(column).lower() for column in candidate.columns]
        if any("default value" in c for c in columns) and any("code" in c for c in columns):
            table = candidate.copy()
            break
    if table is None:
        raise ValueError("Could not identify the default-values table on the page.")

    table.columns = [str(column).strip() for column in table.columns]
    code_col = next(c for c in table.columns if "code" in c.lower())
    desc_col = next(c for c in table.columns if "description" in c.lower())
    value_col = next(c for c in table.columns if "default value" in c.lower())

    rows = []
    for _, record in table.iterrows():
        raw_code = str(record[code_col])
        if raw_code.strip().lower() in {"nan", ""}:
            continue
        code = re.sub(r"\D", "", raw_code)
        if len(code) != 8:
            raise ValueError(f"Unexpected commodity code format: {raw_code!r}")

        match = re.search(r"\d+\.?\d*", str(record[value_col]).replace(",", ""))
        if not match:
            raise ValueError(f"No numeric default value found for code {code}.")

        rows.append({
            "sector": sector,
            "commodity_code": code,
            "description": str(record[desc_col]).strip(),
            "default_tco2e_per_tonne": float(match.group()),
            "source_url": url,
        })

    if not rows:
        raise ValueError("The default-values table contained no readable rows.")
    return rows


def fetch_live_dataset(timeout: int = 30) -> tuple[pd.DataFrame, list[str]]:
    """Fetch and parse all five official tables. Returns (dataframe, errors)."""
    rows: list[dict] = []
    errors: list[str] = []

    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT})
        for sector, url in SECTOR_URLS.items():
            try:
                response = session.get(url, timeout=timeout)
                response.raise_for_status()
                rows.extend(_parse_sector_page(sector, url, response.text))
            except Exception as exc:                      # noqa: BLE001
                errors.append(f"{sector}: {type(exc).__name__}: {exc}")

    frame = pd.DataFrame(rows, columns=COLUMNS)
    if not frame.empty:
        frame["commodity_code"] = frame["commodity_code"].astype(str)
    return frame, errors


def validate_dataset(frame: pd.DataFrame) -> list[str]:
    """Return a list of reasons the dataset should not be trusted. Empty is good."""
    problems: list[str] = []

    if frame.empty:
        return ["No rows were parsed from any sector page."]

    for sector, expected in EXPECTED_ROW_COUNTS.items():
        found = int((frame["sector"] == sector).sum())
        if found != expected:
            problems.append(
                f"{sector}: expected {expected} entries, found {found}. "
                "The table may have been truncated, or HMRC may have revised the scope."
            )

    total = len(frame)
    if total != EXPECTED_TOTAL_ROWS:
        problems.append(f"Expected {EXPECTED_TOTAL_ROWS} entries in total, found {total}.")

    duplicates = frame[frame.duplicated(subset=["sector", "commodity_code"], keep=False)]
    if not duplicates.empty:
        codes = ", ".join(sorted(duplicates["commodity_code"].unique())[:10])
        problems.append(f"Duplicate commodity codes were parsed: {codes}.")

    bad_codes = frame.loc[~frame["commodity_code"].str.fullmatch(r"\d{8}"), "commodity_code"]
    if not bad_codes.empty:
        problems.append(f"Commodity codes that are not 8 digits: {list(bad_codes)[:10]}.")

    values = frame["default_tco2e_per_tonne"]
    out_of_range = frame.loc[(values <= 0) | (values > 50)]
    if not out_of_range.empty:
        problems.append(
            "Default values outside the plausible 0 to 50 tCO2e range were parsed for codes: "
            + ", ".join(out_of_range["commodity_code"].head(10))
        )

    return problems


def load_baseline() -> pd.DataFrame:
    """Load the verified baseline snapshot shipped with the application."""
    frame = pd.read_csv(BASELINE_FILE, dtype={"commodity_code": str})
    return frame[COLUMNS]


def compare_with_baseline(live: pd.DataFrame, baseline: pd.DataFrame) -> dict:
    """Identify values HMRC has changed, codes added, and codes removed."""
    left = baseline.set_index(["sector", "commodity_code"])["default_tco2e_per_tonne"]
    right = live.set_index(["sector", "commodity_code"])["default_tco2e_per_tonne"]

    changed = [
        (f"{sector} {code}", round(float(left[(sector, code)]), 3), round(float(right[(sector, code)]), 3))
        for sector, code in left.index.intersection(right.index)
        if abs(float(left[(sector, code)]) - float(right[(sector, code)])) > 1e-9
    ]
    added = [f"{sector} {code}" for sector, code in right.index.difference(left.index)]
    removed = [f"{sector} {code}" for sector, code in left.index.difference(right.index)]

    return {"changed": sorted(changed), "added": sorted(added), "removed": sorted(removed)}


def get_dataset(prefer_live: bool = True) -> tuple[pd.DataFrame, DatasetStatus]:
    """Return the dataset to use, plus a status record describing its provenance.

    A live fetch is used only if it parses and passes validation. Otherwise the
    verified baseline is used and the reasons are recorded on the status object.
    """
    status = DatasetStatus()
    baseline = load_baseline()

    if not prefer_live:
        status.origin = "baseline"
        status.row_count = len(baseline)
        status.sector_counts = baseline["sector"].value_counts().to_dict()
        return baseline, status

    live, fetch_errors = fetch_live_dataset()
    status.fetch_errors = fetch_errors
    status.retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    validation_errors = validate_dataset(live)
    if validation_errors:
        status.origin = "baseline"
        status.validation_errors = []          # the baseline itself is valid
        status.fetch_errors = fetch_errors + validation_errors
        status.row_count = len(baseline)
        status.sector_counts = baseline["sector"].value_counts().to_dict()
        return baseline, status

    diff = compare_with_baseline(live, baseline)
    status.origin = "live"
    status.row_count = len(live)
    status.sector_counts = live["sector"].value_counts().to_dict()
    status.changed, status.added, status.removed = diff["changed"], diff["added"], diff["removed"]
    return live.sort_values(["sector", "commodity_code"]).reset_index(drop=True), status


def dataset_for_export(frame: pd.DataFrame) -> pd.DataFrame:
    """Add functional-unit and caveat columns for CSV or Excel output."""
    out = frame.copy()
    out["functional_unit"] = [
        functional_unit(s, c)[0] for s, c in zip(out["sector"], out["commodity_code"])
    ]
    out["functional_unit_type"] = [
        functional_unit(s, c)[1] for s, c in zip(out["sector"], out["commodity_code"])
    ]
    out["basis_caveat"] = [
        basis_caveat(s, c) for s, c in zip(out["sector"], out["commodity_code"])
    ]
    out["source_checked"] = date.today().isoformat()
    return out
