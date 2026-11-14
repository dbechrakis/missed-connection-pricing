"""GSA per-diem rates for fiscal years 2018 to 2023, from the master rate files the GSA publishes.

The GSA rate pages that `mcp.costs` reads carry no table for fiscal years before 2024, and its API returns nothing for
them. The same rates are in the master files on https://www.gsa.gov/travel/per-diem-rates/per-diem-files. This module reads
them for the five hub airports and writes the cache files `mcp.costs` reads, in the same form as a page read
(`data/external/gsa/<zip>_FY<year>_page.json`), so the 2018 to 2023 build prices a night the way the 2024 build does.

    cd src && pip install -r ../requirements-hist.txt && python -m mcp.gsa_hist     # downloads, parses, writes the cache

Matching. A hub is a state and a destination: ATL Georgia "Atlanta", ORD Illinois "Chicago", DFW Texas "Dallas",
DEN Colorado "Denver / Aurora", CLT North Carolina "Charlotte". Those are the destinations the GSA pages return for the
hubs' own ZIP codes in fiscal year 2024 (tests/test_gsa_hist.py compares them). A season runs from its begin month to its
end month and may wrap past December. Rows without a season apply to the whole year.
"""
from __future__ import annotations

import json
import time
import urllib.request

from mcp.costs import HUB_ZIP, RAW
from mcp.ingest import ROOT

BASE = "https://www.gsa.gov/system/files/"
FILES = {2018: "FY2018_PerDiemRatesMasterFile.xls", 2019: "FY2019_PerDiemRatesMasterFile_0.xls", 2020: "FY2020_PerDiemMasterRatesFile.xls",
         2021: "FY2021_PerDiemMasterRatesFile.xlsx", 2022: "FY2022_PerDiemMasterRatesFile.xlsx", 2023: "FY2023_PerDiemMasterRatesFile.xlsx"}
HUB_DESTINATION = {"ATL": ("GA", "Atlanta"), "ORD": ("IL", "Chicago"), "DFW": ("TX", "Dallas"), "DEN": ("CO", "Denver / Aurora"), "CLT": ("NC", "Charlotte")}
MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
          "september": 9, "october": 10, "november": 11, "december": 12}
RAW_DIR = ROOT / "data" / "raw" / "gsa_hist"


def month_of(text) -> int | None:
    if text is None or str(text).strip().lower() in ("", "nan", "none"):
        return None
    return MONTHS[str(text).split()[0].strip().lower()]


def lodging_by_month(rows: list[dict]) -> dict[int, float]:
    """{1..12: nightly lodging rate} from the seasonal rows of one destination (begin and end may be None for a full year)."""
    out: dict[int, float] = {}
    for r in rows:
        b, e = month_of(r["begin"]), month_of(r["end"])
        if b is None or e is None:
            months = range(1, 13)
        elif b <= e:
            months = range(b, e + 1)
        else:
            months = list(range(b, 13)) + list(range(1, e + 1))
        for m in months:
            out[m] = float(r["lodging"])
    if sorted(out) != list(range(1, 13)):
        raise ValueError(f"seasons do not cover the year: {sorted(out)}")
    return out


def read_master(path) -> list[dict]:
    import pandas as pd
    d = pd.read_excel(path, header=1)
    d.columns = ["id", "state", "dest", "county", "begin", "end", "lodging", "mie"]
    return d.to_dict("records")


def hub_rates(records: list[dict]) -> dict:
    out = {}
    for hub, (state, dest) in HUB_DESTINATION.items():
        rows = [r for r in records if str(r["state"]).strip() == state and str(r["dest"]).strip() == dest]
        if not rows:
            raise ValueError(f"no rows for {hub}: {state} {dest}")
        mie = {float(r["mie"]) for r in rows}
        if len(mie) != 1:
            raise ValueError(f"{hub}: more than one meals rate {mie}")
        out[hub] = {"lodging": lodging_by_month(rows), "mie": mie.pop(), "county": str(rows[0]["county"]).strip(), "city": dest}
    return out


def download(fy: int):
    path = RAW_DIR / FILES[fy]
    if not path.exists():
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(BASE + FILES[fy], headers={"User-Agent": "missed-connection-pricing (public research)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
        time.sleep(1.5)
    return path


def main() -> None:
    for fy in FILES:
        rates = hub_rates(read_master(download(fy)))
        for hub, p in rates.items():
            rec = {"source": BASE + FILES[fy], "retrieved": time.strftime("%Y-%m-%d"), "mie": p["mie"], "county": p["county"], "city": p["city"],
                   "standard_rate": False, "lodging": {str(m): v for m, v in p["lodging"].items()}}
            path = RAW / f"{HUB_ZIP[hub]}_FY{fy}_page.json"
            path.write_text(json.dumps(rec, indent=1), encoding="utf-8", newline="\n")
        print(f"FY{fy}: " + ", ".join(f"{h} ${min(p['lodging'].values()):.0f} to ${max(p['lodging'].values()):.0f}, M&IE ${p['mie']:.0f}" for h, p in rates.items()))


if __name__ == "__main__":
    main()
