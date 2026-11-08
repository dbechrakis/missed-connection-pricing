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

from mcp.variant import MARKETING, sfx

HUBS = ("ATL", "ORD", "DFW", "DEN", "CLT")

URL_REPORTING = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{y}_{m}.zip"
)
URL_MARKETING = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Marketing_Carrier_On_Time_Performance_Beginning_January_2018_{y}_{m}.zip"
)
URL = URL_MARKETING if MARKETING else URL_REPORTING

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / ("marketing" if MARKETING else "ontime")
OUT = ROOT / "data" / "parquet" / sfx("ontime")
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
    # Minutes of arrival delay attributed to each cause (reported only for flights arriving 15+ minutes late).
    # Used to split missed connections into what the airline is responsible for and what it is not.
    "CarrierDelay": ("delay_carrier_min", "DOUBLE"),
    "WeatherDelay": ("delay_weather_min", "DOUBLE"),
    "NASDelay": ("delay_nas_min", "DOUBLE"),
    "SecurityDelay": ("delay_security_min", "DOUBLE"),
    "LateAircraftDelay": ("delay_late_aircraft_min", "DOUBLE"),
}


# The marketing-carrier table (v3): the same flight fields, but the carrier is the brand network that sells it,
# and the operating airline is kept alongside. (Its "Operating_Airline " header has a trailing space, so the
# IATA code column is used instead.)
COLUMNS_MARKETING = {
    "FlightDate": ("flight_date", "DATE"),
    "Marketing_Airline_Network": ("carrier", "VARCHAR"),
    "IATA_Code_Operating_Airline": ("operating_carrier", "VARCHAR"),
    "Flight_Number_Operating_Airline": ("flight_number", "INTEGER"),
    **{k: v for k, v in COLUMNS.items() if k not in ("FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline")},
}
ACTIVE_COLUMNS = COLUMNS_MARKETING if MARKETING else COLUMNS


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
    dest = RAW / (f"{y}_{m}.zip" if MARKETING else f"{y}_{m:02d}.zip")
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
        for src, (name, typ) in ACTIVE_COLUMNS.items()
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


DB1B_RAW = ROOT / "data" / "raw" / "db1b"
DB1B_OUT = ROOT / "data" / "parquet" / "db1b"
# v1 pairs coupons by the reporting carrier; v3 by the ticketing carrier, the brand on the ticket
DB1B_CARRIER = "TkCarrier" if MARKETING else "RPCarrier"
FARE_MIN, FARE_MAX = 20.0, 5000.0  # drop $0/$1 placeholder fares and data-entry outliers


def db1b_routes_sql(coupon_csv: str, market_csv: str, quarter: str) -> str:
    """One row per (carrier, A, hub, B) for one quarter: passengers and mean fare.

    A route is a *market* with exactly 2 coupons (one stop) where both coupons
    are flown by the same reporting carrier, are consecutive (SeqNum 1 -> 2),
    meet at one of our hubs, and the first coupon does not end a trip (Break<>'A').
    Joining Coupon to Market on MktID gives the fare of that exact A->H->B market.
    Passengers is a 10%-sample count, so only relative sizes mean anything.
    """
    hub_list = ", ".join(f"'{h}'" for h in HUBS)
    return f"""
    WITH m AS (
      SELECT TRY_CAST(MktID AS BIGINT) AS mkt_id,
             TRY_CAST(Passengers AS DOUBLE) AS pax,
             TRY_CAST(MktFare AS DOUBLE) AS fare
      FROM read_csv('{market_csv}', header=true, all_varchar=true)
      WHERE TRY_CAST(MktCoupons AS INTEGER) = 2
        AND TRY_CAST(BulkFare AS DOUBLE) = 0
        AND TRY_CAST(MktFare AS DOUBLE) BETWEEN {FARE_MIN} AND {FARE_MAX}
    ),
    c AS (
      SELECT TRY_CAST(MktID AS BIGINT) AS mkt_id, TRY_CAST(SeqNum AS INTEGER) AS seq,
             Origin AS origin, Dest AS dest, {DB1B_CARRIER} AS carrier, COALESCE(Break, '') AS brk
      FROM read_csv('{coupon_csv}', header=true, all_varchar=true)
    )
    SELECT '{quarter}' AS quarter, c1.carrier, c1.origin, c1.dest AS hub, c2.dest AS destination,
           sum(m.pax) AS passengers, count(*) AS n_markets,
           sum(m.pax * m.fare) / sum(m.pax) AS fare_mean
    FROM c c1
    JOIN c c2 ON c1.mkt_id = c2.mkt_id AND c1.seq = 1 AND c2.seq = 2
    JOIN m ON m.mkt_id = c1.mkt_id
    WHERE c1.dest IN ({hub_list}) AND c1.dest = c2.origin
      AND c1.carrier = c2.carrier AND c1.brk <> 'A' AND c1.origin <> c2.dest
    GROUP BY ALL
    """


def ingest_db1b(year: int, q: int, raw_dir: Path = DB1B_RAW, out_dir: Path = DB1B_OUT) -> int:
    """Coupon + Market zips for one quarter -> routes Parquet (the raw CSV is ~2 GB, so it is
    extracted to a temp file, queried, and deleted)."""
    out = out_dir / sfx("routes") / f"year={year}" / f"quarter={q}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = []
    try:
        for kind in ("Coupon", "Market"):
            with zipfile.ZipFile(raw_dir / f"{kind}_{year}_{q}.zip") as z:
                (member,) = [n for n in z.namelist() if n.lower().endswith(".csv")]
                dst = raw_dir / f"{kind}_{year}_{q}.csv"
                with z.open(member) as src, dst.open("wb") as f:
                    while chunk := src.read(1 << 24):
                        f.write(chunk)
                tmp.append(dst)
        con = duckdb.connect()
        con.execute(
            f"COPY ({db1b_routes_sql(tmp[0].as_posix(), tmp[1].as_posix(), f'{year}Q{q}')}) "
            f"TO '{out.as_posix()}' (FORMAT parquet, COMPRESSION zstd)"
        )
        (n,) = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()
        con.close()
    finally:
        for t in tmp:
            t.unlink(missing_ok=True)
    return n


TRAIN_QUARTERS = ("2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2")  # Jan 2024 - Jun 2025


def build_route_weights(out_dir: Path = DB1B_OUT, quarters=TRAIN_QUARTERS) -> int:
    """Pool the TRAIN quarters into one weight per (carrier, A, hub, B).

    Test quarters (2025Q3/Q4) are not published and must not be used anyway: weights
    are a train-only statistic, applied unchanged to the holdout (spec: Method 4).
    """
    src = (out_dir / sfx("routes") / "*" / "*.parquet").as_posix()
    out = out_dir / f"{sfx('route_weights')}.parquet"
    qs = ", ".join(f"'{q}'" for q in quarters)
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
          SELECT carrier, origin, hub, destination,
                 sum(passengers) AS passengers,
                 sum(passengers * fare_mean) / sum(passengers) AS fare_mean
          FROM read_parquet('{src}')
          WHERE quarter IN ({qs})
          GROUP BY ALL
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
    p.add_argument("--source", choices=["ontime", "db1b", "asos"], default="ontime")
    a = p.parse_args(argv)

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    if a.source == "asos":
        manifest["asos"] = {"rows": ingest_asos(), "ingested": date.today().isoformat(),
                            "files": {f.name: sha256(f) for f in sorted(ASOS_RAW.glob("*.csv"))}}
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        print(f"asos: {manifest['asos']['rows']:,} rows")
        return
    if a.source == "db1b":
        entry = manifest.setdefault(sfx("db1b"), {})
        for q in TRAIN_QUARTERS:
            y, qn = int(q[:4]), int(q[-1])
            out = DB1B_OUT / sfx("routes") / f"year={y}" / f"quarter={qn}.parquet"
            if out.exists() and q in entry and not a.force:
                print(f"{q}: skip (already ingested)")
                continue
            n = ingest_db1b(y, qn)
            entry[q] = {"rows": n, "ingested": date.today().isoformat(),
                        **{k.lower() + "_sha256": sha256(DB1B_RAW / f"{k}_{y}_{qn}.zip")
                           for k in ("Coupon", "Market")}}
            MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
            print(f"{q}: {n:,} route rows")
        print(f"route_weights: {build_route_weights():,} rows")
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        return

    files = manifest.setdefault(sfx("ontime"), {})
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
