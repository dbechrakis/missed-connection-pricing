"""Step 1 of the clear-day coding test of `docs/season3-plan.md` T6: counts only, no cause code read.

A cancelled flight between two of the five hubs is on a clear window when no adverse ASOS hour and no FAA ground stop or ground
delay program touched either end in the three hours either side of the scheduled departure (at the origin) and scheduled arrival
(at the destination). The count is of such flights by airline and calendar quarter, outside the pandemic months. The gate of the
plan is 40 airline-quarters of committing airlines with at least 100 of them. If it is not met the test is not built.

    cd src && python -m mcp.clear_day_counts
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from mcp import coding_audit as C
from mcp import faa
from mcp.ingest import HUBS, ROOT

RESULT = ROOT / "results" / "clear_day_counts.json"
WINDOW_HOURS = 3
MIN_FLIGHTS = 100
MIN_AIRLINE_QUARTERS = 40


def local_to_utc(date: pd.Series, hhmm: pd.Series, hub: pd.Series) -> pd.Series:
    minutes = (hhmm // 100) * 60 + hhmm % 100
    local = pd.to_datetime(date) + pd.to_timedelta(minutes, unit="m")
    out = pd.Series(pd.NaT, index=local.index, dtype="datetime64[ns, UTC]")
    for name, tz in C.TZ.items():
        m = (hub == name).to_numpy()
        if m.any():
            out[m] = local[m].dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return out


def adverse_hours(asos: pd.DataFrame) -> set:
    a = asos.copy()
    a["hour"] = pd.to_datetime(a["obs_utc"]).dt.floor("h").dt.tz_localize("UTC")
    a["adverse"] = a[["thunder", "snow", "freezing", "low_vis", "high_wind"]].any(axis=1)
    flagged = a.groupby(["station", "hour"])["adverse"].max()
    return {key for key, value in flagged.items() if value}


def weather_in_window(station: pd.Series, times: pd.Series, adverse: set) -> np.ndarray:
    out = np.zeros(len(times), bool)
    base = times.dt.floor("h")
    for k in range(-WINDOW_HOURS, WINDOW_HOURS + 1):
        shifted = base + pd.Timedelta(hours=k)
        out |= np.array([(s, h) in adverse for s, h in zip(station, shifted)])
    return out


def program_in_window(station: pd.Series, times: pd.Series, intervals: dict) -> np.ndarray:
    out = np.zeros(len(times), bool)
    for hub, spans in intervals.items():
        m = (station == hub).to_numpy()
        if m.any() and spans:
            for k in range(-WINDOW_HOURS, WINDOW_HOURS + 1):
                t = (times[m] + pd.Timedelta(hours=k)).dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
                out[m] |= faa.covered(spans, t)
    return out


def clear_mask(df: pd.DataFrame, adverse: set, intervals: dict) -> np.ndarray:
    """True where neither end of the flight had adverse weather or an FAA program in its window. `df` has origin, dest, dep_utc, arr_utc."""
    bad = (weather_in_window(df["origin"], df["dep_utc"], adverse) | weather_in_window(df["dest"], df["arr_utc"], adverse)
           | program_in_window(df["origin"], df["dep_utc"], intervals) | program_in_window(df["dest"], df["arr_utc"], intervals))
    return ~bad


def summarise(df: pd.DataFrame) -> dict:
    """`df` has carrier, ym and a boolean `clear`, pandemic months already removed."""
    d = df.assign(q=df["ym"].map(C.quarter_of))
    g = d.groupby(["carrier", "q"]).agg(cancelled=("clear", "size"), clear=("clear", "sum")).reset_index()
    committing = g[g["carrier"].isin(C.COMMITTING)]
    per_airline = {c: {"quarters": int(len(x)), "quarters_with_enough": int((x["clear"] >= MIN_FLIGHTS).sum()), "clear_flights": int(x["clear"].sum()),
                       "cancelled_flights": int(x["cancelled"].sum())} for c, x in g.groupby("carrier")}
    enough = int((committing["clear"] >= MIN_FLIGHTS).sum())
    return {"cancelled_hub_to_hub_flights": int(len(d)), "clear_flights": int(d["clear"].sum()), "clear_share": float(d["clear"].mean()), "per_airline": per_airline,
            "airline_quarters_with_enough_committing": enough, "min_flights": MIN_FLIGHTS, "min_airline_quarters": MIN_AIRLINE_QUARTERS,
            "gate_passed": bool(enough >= MIN_AIRLINE_QUARTERS)}


def run() -> dict:
    import duckdb
    hubs = ", ".join(f"'{h}'" for h in HUBS)
    parts = [f"SELECT carrier, flight_date, origin, dest, crs_dep_hhmm, crs_arr_hhmm FROM read_parquet('{(d / '*' / '*.parquet').as_posix()}') "
             f"WHERE cancelled AND flight_date >= DATE '{C.FIRST}' AND flight_date < DATE '{C.LAST_DATE}'" for d in C.FLIGHT_DIRS if d.exists()]
    df = duckdb.connect().execute("SELECT DISTINCT * FROM (" + " UNION ALL ".join(parts) + f") WHERE origin IN ({hubs}) AND dest IN ({hubs})").fetchdf()
    df["dep_utc"] = local_to_utc(df["flight_date"], df["crs_dep_hhmm"], df["origin"])
    df["arr_utc"] = local_to_utc(df["flight_date"], df["crs_arr_hhmm"], df["dest"])
    df = df.dropna(subset=["dep_utc", "arr_utc"]).copy()
    asos = duckdb.connect().execute(f"SELECT * FROM read_parquet('{C.ASOS_FILE.as_posix()}')").fetchdf()
    df["clear"] = clear_mask(df, adverse_hours(asos), faa.active_intervals(faa.programs("2018-01", "2026-08")))
    df["ym"] = pd.to_datetime(df["flight_date"]).dt.strftime("%Y-%m")
    df = df[~df["ym"].map(C.is_pandemic)]
    res = {"status": "counts only, no cause code read (docs/season3-plan.md T6 step 1)", **summarise(df)}
    RESULT.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return res


if __name__ == "__main__":
    run()
