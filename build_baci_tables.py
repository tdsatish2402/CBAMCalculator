"""Rebuild the baci_*.csv files from a BACI release.

Usage (from the folder that holds app.py):
    python build_baci_tables.py PATH_TO_UNZIPPED_BACI_FOLDER

The folder must contain the three yearly BACI files, product_codes_*.csv and country_codes_*.csv.
Only headings that contain a CBAM commodity code in cbam_default_values_baseline.csv are kept, plus
heading 2716.00 (electricity), which the EU CBAM covers and the UK CBAM does not.

Two importing markets are prepared:
- UK: imports into the United Kingdom (BACI code 826).
- EU: imports into the 27 EU member states from outside the EU. Trade between member states is left
  out, because the EU CBAM applies only to goods entering the EU from third countries.
"""
import glob
import sys
from pathlib import Path

import pandas as pd

UK = 826
# The 27 EU member states, by BACI country code.
EU27 = [40, 56, 100, 191, 196, 203, 208, 233, 246, 251, 276, 300, 348, 372, 380, 428, 440, 442, 470,
        528, 616, 620, 642, 703, 705, 724, 752]
ELECTRICITY = "271600"

src = Path(sys.argv[1])
here = Path(__file__).resolve().parent

cbam = pd.read_csv(here / "cbam_default_values_baseline.csv", dtype=str)
headings = set(cbam["commodity_code"].str[:6]) | {ELECTRICITY}

world, uk, eu, totals, uk_all, eu_all = [], [], [], [], [], []
agg = dict(v=("v", "sum"), q=("q", "sum"), nq=("q", lambda s: s.isna().sum()))
for path in sorted(glob.glob(str(src / "BACI_HS22_Y*_V*.csv"))):
    df = pd.read_csv(path, dtype={"k": str}, usecols=["t", "i", "j", "k", "v", "q"], na_values=["", "NA"])
    df["k"] = df["k"].str.zfill(6)
    sel = df[df["k"].isin(headings)]
    world.append(sel.groupby(["t", "i", "k"], as_index=False).agg(**agg))
    uk.append(sel[sel["j"] == UK].groupby(["t", "i", "k"], as_index=False).agg(**agg))
    into_eu = sel[sel["j"].isin(EU27) & ~sel["i"].isin(EU27)]
    eu.append(into_eu.groupby(["t", "i", "k"], as_index=False).agg(**agg))
    totals.append(df.groupby(["t", "i"], as_index=False).agg(v_all=("v", "sum")))
    uk_all.append(df[df["j"] == UK].groupby(["t", "i"], as_index=False).agg(v_uk_all=("v", "sum")))
    eu_all.append(df[df["j"].isin(EU27) & ~df["i"].isin(EU27)].groupby(["t", "i"], as_index=False)
                  .agg(v_eu_all=("v", "sum")))
    print("read", path)

world = pd.concat(world).rename(columns={"v": "v_world", "q": "q_world", "nq": "nq_world"})
uk = pd.concat(uk).rename(columns={"v": "v_uk", "q": "q_uk", "nq": "nq_uk"})
eu = pd.concat(eu).rename(columns={"v": "v_eu", "q": "q_eu", "nq": "nq_eu"})
trade = world.merge(uk, on=["t", "i", "k"], how="left").merge(eu, on=["t", "i", "k"], how="left")
for col in ("v_uk", "q_uk", "nq_uk", "v_eu", "q_eu", "nq_eu"):
    trade[col] = trade[col].fillna(0)
trade = trade.rename(columns={"t": "year", "i": "exporter", "k": "hs6"})
trade["nq_uk"] = trade["nq_uk"].astype(int)
trade["nq_eu"] = trade["nq_eu"].astype(int)
trade = trade.sort_values(["year", "exporter", "hs6"])
trade.round(3).to_csv(here / "baci_cbam_trade.csv.gz", index=False, compression="gzip")

pd.concat(totals).rename(columns={"t": "year", "i": "exporter"}).round(3).to_csv(
    here / "baci_exporter_totals.csv", index=False)

# Every exporter's sales of all goods to each market, so total imports and supplier ranks can be shown.
pd.concat(uk_all).rename(columns={"t": "year", "i": "exporter"}).round(3).sort_values(["year", "exporter"]).to_csv(
    here / "baci_uk_all_goods.csv", index=False)
pd.concat(eu_all).rename(columns={"t": "year", "i": "exporter"}).round(3).sort_values(["year", "exporter"]).to_csv(
    here / "baci_eu_all_goods.csv", index=False)

countries = pd.read_csv(glob.glob(str(src / "country_codes_V*.csv"))[0])
def _fix(name):
    try:
        return name.encode("latin-1").decode("utf-8")   # repairs double-encoded accents
    except Exception:
        return name
countries["country_name"] = countries["country_name"].map(_fix)
countries.to_csv(here / "baci_countries.csv", index=False, encoding="utf-8")

products = pd.read_csv(glob.glob(str(src / "product_codes_HS22_V*.csv"))[0], dtype=str)
sector_of = cbam.assign(hs6=cbam["commodity_code"].str[:6]).drop_duplicates("hs6").set_index("hs6")["sector"]
names = products[products["code"].isin(headings)].rename(columns={"code": "hs6"})
names["sector"] = names["hs6"].map(sector_of)
names.loc[names["hs6"] == ELECTRICITY, "sector"] = "Electricity"
names.to_csv(here / "baci_hs6_names.csv", index=False)
print("done")
