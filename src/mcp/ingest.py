"""Ingest BTS Reporting Carrier On-Time Performance into Parquet via DuckDB.

Scope decisions (see docs/spec.md):
  * Hubs ATL, ORD, DFW, DEN, CLT. We keep every flight that touches a hub
    (Origin OR Dest), because a connection needs both the inbound A->H leg
    and the outbound H->B leg.
  * Cancelled and diverted flights are KEPT. They are the label's signal.
  * This module only types, filters and stores. No business logic (MCT, label,
    slack): that belongs in connections.py so it is testable in isolation.

Usage:
    python -m mcp.ingest --start 2024-01 --end 2025-12            (from src/)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import duckdb

HUBS = ("ATL", "ORD", "DFW", "DEN", "CLT")

URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{y}_{m}.zip"
)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "ontime"
OUT = ROOT / "data" / "parquet" / "ontime"
MANIFEST = ROOT / "data" / "manifest.json"

# Source column -> (output name, DuckDB type). Only what later steps need.
# Times (hhmm) stay as SMALLINT here; turning them into timestamps needs the
# overnight-rollover logic, which is connections.py's job.
COLUMNS = {
    "FlightDate": ("flight_date", "DATE"),
    "Reporting_Airline": ("carrier", "VARCHAR"),
    "Flight_Number_Reporting_Airline": ("flight_number", "INTEGER"),
    "Tail_Number": ("tail_number", "VARCHAR"),
    "Origin": ("origin", "VARCHAR"),
    "Dest": ("dest", "VARCHAR"),
    "CRSDepTime": ("crs_dep_hhmm", "SMALLINT"),
    "DepTime": ("dep_hhmm", "SMALLINT"),
    "DepDelay": ("dep_delay_min", "DOUBLE"),
    "CRSArrTime": ("crs_arr_hhmm", "SMALLINT"),
    "ArrTime": ("arr_hhmm", "SMALLINT"),
    "ArrDelay": ("arr_delay_min", "DOUBLE"),
    "Cancelled": ("cancelled", "BOOLEAN"),
    "CancellationCode": ("cancellation_code", "VARCHAR"),
    "Diverted": ("diverted", "BOOLEAN"),
    "CRSElapsedTime": ("crs_elapsed_min", "DOUBLE"),
    "ActualElapsedTime": ("actual_elapsed_min", "DOUBLE"),
    "Distance": ("distance_mi", "DOUBLE"),
}


def months(start: str, end: str):
    y, m = map(int, start.split("-"))
    ye, me = map(int, end.split("-"))
    while (y, m) <= (ye, me):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(y: int, m: int) -> Path:
    dest = RAW / f"{y}_{m:02d}.zip"
    if dest.exists():
        return dest
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    urllib.request.urlretrieve(URL.format(y=y, m=m), tmp)
    tmp.replace(dest)  # atomic: a killed run never leaves a truncated .zip
    return dest


def to_parquet(zip_path: Path, y: int, m: int) -> int:
    """Read one month's CSV, filter to hub flights, write one Parquet file."""
    out = OUT / f"year={y}" / f"month={m:02d}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as z:
        (member,) = [n for n in z.namelist() if n.lower().endswith(".csv")]
        csv_path = zip_path.with_suffix(".csv")
        with z.open(member) as src, csv_path.open("wb") as dst:
            dst.write(src.read())

    # all_varchar + TRY_CAST: BTS writes times as "1234" or "1234.00" and
    # leaves cancelled-flight fields empty. Letting DuckDB infer types would
    # guess per file and could differ month to month; explicit casts cannot.
    select = ",\n  ".join(
        f"TRY_CAST(NULLIF(TRIM(\"{src}\"), '') AS DOUBLE)::{typ} AS {name}"
        if typ in ("SMALLINT", "INTEGER")
        else f"TRY_CAST(NULLIF(TRIM(\"{src}\"), '') AS {typ}) AS {name}"
        if typ in ("DOUBLE", "DATE")
        else f"(TRY_CAST(NULLIF(TRIM(\"{src}\"), '') AS DOUBLE) = 1) AS {name}"
        if typ == "BOOLEAN"
        else f"NULLIF(TRIM(\"{src}\"), '') AS {name}"
        for src, (name, typ) in COLUMNS.items()
    )
    hubs = ", ".join(f"'{h}'" for h in HUBS)
    con = duckdb.connect()
    try:
        con.execute(
            f"""
            COPY (
              SELECT {select}
              FROM read_csv('{csv_path.as_posix()}', header=true, all_varchar=true)
              WHERE "Origin" IN ({hubs}) OR "Dest" IN ({hubs})
            ) TO '{out.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
            """
        )
        (n,) = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()
    finally:
        con.close()
        csv_path.unlink(missing_ok=True)  # raw CSV is ~5x the zip; keep only the zip
    return n


ASOS_RAW = ROOT / "data" / "raw" / "asos"
ASOS_OUT = ROOT / "data" / "parquet" / "asos" / "hourly.parquet"


def ingest_asos(raw_dir: Path = ASOS_RAW, out: Path = ASOS_OUT) -> int:
    """IEM METAR CSVs -> one hourly Parquet with weather flags per observation.

    Flags (METAR present-weather codes; 'VC' = in the vicinity, kept on purpose
    because a thunderstorm near the field still stops operations):
      thunder  : TS in wxcodes          snow : SN / SG / BLSN
      freezing : FZ (freezing rain/drizzle/fog)
      low_vis  : visibility < 1 statute mile
      high_wind: sustained wind >= 25 kt or gust >= 35 kt
    Observations are stored as reported (UTC). Climatology is aggregated later,
    from train months only, in features.py: nothing here may see the test set.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
          SELECT station,
                 CAST(valid AS TIMESTAMP) AS obs_utc,
                 TRY_CAST(NULLIF(vsby, '') AS DOUBLE) AS vis_mi,
                 TRY_CAST(NULLIF(sknt, '') AS DOUBLE) AS wind_kt,
                 TRY_CAST(NULLIF(gust, '') AS DOUBLE) AS gust_kt,
                 TRY_CAST(NULLIF(replace(p01i, 'T', '0.001'), '') AS DOUBLE) AS precip_1h_in,
                 COALESCE(wxcodes, '') LIKE '%TS%' AS thunder,
                 regexp_matches(COALESCE(wxcodes, ''), 'SN|SG') AS snow,
                 COALESCE(wxcodes, '') LIKE '%FZ%' AS freezing,
                 COALESCE(TRY_CAST(NULLIF(vsby, '') AS DOUBLE) < 1, false) AS low_vis,
                 COALESCE(TRY_CAST(NULLIF(sknt, '') AS DOUBLE) >= 25
                          OR TRY_CAST(NULLIF(gust, '') AS DOUBLE) >= 35, false) AS high_wind
          FROM read_csv('{(raw_dir / '*.csv').as_posix()}', header=true, all_varchar=true)
          WHERE station IN ({", ".join(f"'{h}'" for h in HUBS)})
        ) TO '{out.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
        """
    )
    (n,) = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()
    return n


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2024-01")
    p.add_argument("--end", default="2025-12")
    p.add_argument("--force", action="store_true", help="rebuild existing Parquet")
    a = p.parse_args(argv)

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    files = manifest.setdefault("ontime", {})
    manifest["hubs"] = list(HUBS)

    for y, m in months(a.start, a.end):
        key = f"{y}-{m:02d}"
        out = OUT / f"year={y}" / f"month={m:02d}.parquet"
        if out.exists() and key in files and not a.force:
            print(f"{key}: skip (already ingested)")
            continue
        zp = download(y, m)
        n = to_parquet(zp, y, m)
        files[key] = {
            "url": URL.format(y=y, m=m),
            "zip_bytes": zp.stat().st_size,
            "zip_sha256": sha256(zp),
            "hub_rows": n,
            "ingested": date.today().isoformat(),
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        print(f"{key}: {n:,} hub rows")


if __name__ == "__main__":
    sys.exit(main())
