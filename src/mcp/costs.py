"""Sourced overnight costs: official US federal per-diem rates (GSA) for each hub airport's ZIP code.

v1 assumed $180 for a night away. The GSA publishes, per county and month, a maximum lodging rate and a meals and
incidentals rate (M&IE) for federal travellers. They are an official, public, documented benchmark for "a hotel
night plus a day's meals near this airport". A stranded traveller's real cost can differ; the point is to replace an
invented number with a sourced one that varies by hub and season.

    overnight cost (hub, month) = GSA lodging rate (hub ZIP, month) + GSA M&IE rate (hub ZIP)

Raw API responses are saved under data/external/gsa/ and committed, so the numbers are traceable without a key.
The API's free DEMO_KEY allows few calls an hour: fetch() caches and stops politely when rate-limited.

Run:  python -m mcp.costs         (from src/; fetches what is missing, then writes results/gsa_costs.json)
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from mcp.connections import ROOT

RAW = ROOT / "data" / "external" / "gsa"
RESULTS = ROOT / "results" / "gsa_costs.json"
# ZIP codes of the airports themselves (rates are set by county, so the airport's ZIP gives the airport-area rate)
HUB_ZIP = {"ATL": "30320", "ORD": "60666", "DFW": "75261", "DEN": "80249", "CLT": "28208"}
FISCAL_YEARS = (2024, 2025, 2026, 2027)   # a federal fiscal year runs October to September
API = "https://api.gsa.gov/travel/perdiem/v2/rates/zip/{zip}/year/{year}?api_key=" + os.environ.get("GSA_API_KEY", "DEMO_KEY")
PAGE = "https://www.gsa.gov/travel/plan-book/per-diem-rates/per-diem-rates-results?action=perdiems_report&fiscal_year={year}&zip={zip}"
FY_MONTHS = (10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9)      # column order of GSA's lodging table


def parse_page(html: str) -> dict:
    """The same fields as the API, read from GSA's public rate page: the first row of the lodging table (the
    destination that applies to this ZIP; 'Standard Rate' if none) and of the meals table."""
    lod = re.search(r"Daily lodging rates.*?<tbody>(.*?)</tbody>", html, re.S).group(1)
    cells = re.findall(r"<td>(.*?)</td>", re.findall(r"<tr>(.*?)</tr>", lod, re.S)[0])
    vals = [float(c.strip().lstrip("$").replace(",", "")) for c in cells[2:14]]
    meals = re.search(r"id='perdiem-meals-breakdown'.*?<tbody>(.*?)</tbody>", html, re.S).group(1)
    mcells = re.findall(r"<td[^>]*>(.*?)</td>", re.findall(r"<tr>(.*?)</tr>", meals, re.S)[0])
    return {"lodging": dict(zip(FY_MONTHS, vals)), "mie": float(re.sub(r"[^0-9.]", "", mcells[2])),
            "county": cells[1].strip(), "city": cells[0].strip(), "standard_rate": cells[0].strip() == "Standard Rate"}


def fetch_page(zip_code: str, year: int) -> dict | None:
    """Cached read of GSA's public rate page (no key needed). Keeps the parsed rates and the source URL."""
    path = RAW / f"{zip_code}_FY{year}_page.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)
    url = PAGE.format(zip=zip_code, year=year)
    req = urllib.request.Request(url, headers={"User-Agent": "missed-connection-pricing (public research)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
        parsed = parse_page(html)
    except (urllib.error.URLError, AttributeError, IndexError):
        return None
    rec = {"source": url, "retrieved": time.strftime("%Y-%m-%d"), **{k: v for k, v in parsed.items() if k != "lodging"},
           "lodging": {str(k): v for k, v in parsed["lodging"].items()}}
    path.write_text(json.dumps(rec, indent=1), encoding="utf-8", newline=chr(10))
    time.sleep(1.5)
    return rec


def fetch(zip_code: str, year: int) -> dict | None:
    """Cached GET of one ZIP-year. Returns None if rate-limited (try again later) or unavailable."""
    path = RAW / f"{zip_code}_FY{year}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    RAW.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(API.format(zip=zip_code, year=year), timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return None
        raise
    if "rates" not in data:                      # rate-limit errors also come back as JSON without 'rates'
        return None
    path.write_text(json.dumps(data, indent=1), encoding="utf-8", newline="\n")
    time.sleep(2)
    return data


def parse(data: dict) -> dict:
    """{'lodging': {month_number: dollars}, 'mie': dollars, 'county': ..., 'city': ...} from one API response."""
    r = data["rates"][0]["rate"][0]
    lodging = {m["number"]: float(m["value"]) for m in r["months"]["month"]}
    return {"lodging": lodging, "mie": float(r["meals"]), "county": r.get("county"), "city": r.get("city"),
            "standard_rate": r.get("standardRate")}


def fiscal_year(year: int, month: int) -> int:
    """US federal fiscal year: October to December belong to the next year's FY."""
    return year + 1 if month >= 10 else year


def overnight_cost(table: dict, hub: str, year: int, month: int) -> float:
    """Lodging + M&IE for a hub in a calendar month, from the parsed table {hub: {fy: parsed}}."""
    p = table[hub][fiscal_year(year, month)]
    return p["lodging"][month] + p["mie"]


def main() -> None:
    table, missing = {}, []
    for hub, z in HUB_ZIP.items():
        for fy in FISCAL_YEARS:
            rec = fetch_page(z, fy)
            if rec is not None:
                table.setdefault(hub, {})[fy] = {**rec, "lodging": {int(k): v for k, v in rec["lodging"].items()}}
                continue
            d = None if (missing and not (RAW / f"{z}_FY{fy}.json").exists()) else fetch(z, fy)   # API fallback
            if d is None:
                missing.append(f"{hub} FY{fy}")
                continue
            table.setdefault(hub, {})[fy] = parse(d)
    if missing:
        print("rate-limited or unavailable, run again later:", ", ".join(missing))
    out = {h: {str(fy): p for fy, p in v.items()} for h, v in table.items()}
    RESULTS.write_text(json.dumps({"source": "GSA per diem rates (gsa.gov rate pages; API as fallback), cached under data/external/gsa/",
                                   "zip_by_hub": HUB_ZIP, "rates": out, "missing": missing}, indent=1), encoding="utf-8")
    for h, v in table.items():
        fys = sorted(v)
        last = v[fys[-1]]
        print(f"{h} ({last['city']}, {last['county']}): M&IE ${last['mie']:.0f}; lodging FY{fys[-1]} "
              f"${min(last['lodging'].values()):.0f} to ${max(last['lodging'].values()):.0f}; fiscal years cached {fys}")


if __name__ == "__main__":
    main()
