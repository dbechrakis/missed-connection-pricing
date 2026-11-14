"""A trigger that can settle the same night, and how far it sits from the one the gap cover was priced on (WP6, session 2).

The gap cover pays when a connection is missed overnight and BTS does not code the inbound problem to the airline. BTS
publishes that code about two months late, and the airline writes it. Two triggers built from sources the airline does not
write are fixed here, before any is scored:

    T1  the connection is missed overnight, and an FAA ground stop or ground delay program (not a proposal, not one airline's
        own stop) was in effect at the hub at some moment between three hours before the inbound flight's scheduled arrival
        and its actual arrival (for a cancelled inbound flight, until three hours after the scheduled arrival).
    T2  T1, or severe weather at the hub (ASOS thunder, snow, freezing weather, visibility under one mile, wind of 25 knots
        or a gust of 35) in any hour of the same window.

"Missed overnight" is the label the cover is built on (`y = 1` and the next flight is the next day). What is measured, per
period and over the whole of it, in payout dollars (the hub's GSA night, weighted by the connection's route weight):

    coverage      the share of the BTS-coded gap payouts that the trigger also pays;
    leakage       the share of the trigger's payouts that BTS codes to the airline (the cover as priced would not pay them);
    ratio         trigger payouts divided by BTS-coded gap payouts, in total, and its monthly standard deviation;
    correlation   of the monthly trigger and gap payouts.

That is the basis risk between a cover that can be paid tonight and the one season 1 priced. What stays outside: a same-night
settlement also needs the inbound flight's actual arrival that night, which a flight-status feed has and BTS does not.

    cd src
    MCP_VARIANT=v3 python -m mcp.trigger dev          # 2024 to August 2026, development data
    MCP_VARIANT=hist python -m mcp.trigger backcast   # 2019 to 2023, only after the backcast has been read
"""
from __future__ import annotations

import json
import sys
from datetime import timezone

import numpy as np
import pandas as pd

from mcp import faa
from mcp.ingest import ROOT

WINDOW_BEFORE_H = 3
CANCELLED_AFTER_H = 3
TZ = {"ATL": "America/New_York", "CLT": "America/New_York", "ORD": "America/Chicago", "DFW": "America/Chicago", "DEN": "America/Denver"}
ADVERSE = ("thunder", "snow", "freezing", "low_vis", "high_wind")
RESULT = ROOT / "results" / "trigger.json"
ASOS_ALL = ROOT / "data" / "parquet" / "asos" / "hourly_hist.parquet"      # 2018 to August 2026, built by the hist ingest


def window_utc(df: pd.DataFrame) -> pd.DataFrame:
    """The trigger window of each connection in UTC: from three hours before the scheduled inbound arrival to the actual arrival."""
    out = df.copy()
    sched = pd.to_datetime(out["in_sched_arr"])
    utc = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    for hub, tz in TZ.items():
        m = (out["hub"] == hub).to_numpy()
        if m.any():
            utc[m] = sched[m].dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    delay = pd.to_timedelta(out["arr_delay_min"].fillna(0).clip(lower=0), unit="m")
    cancelled = (out["in_cancelled"].astype(bool) | out["in_diverted"].astype(bool)) | out["arr_delay_min"].isna()
    out["w_start"] = utc - pd.Timedelta(hours=WINDOW_BEFORE_H)
    out["w_end"] = np.where(cancelled, utc + pd.Timedelta(hours=CANCELLED_AFTER_H), utc + delay)
    out["w_end"] = pd.to_datetime(out["w_end"], utc=True)
    return out


def overlaps(intervals: list[tuple], start, end) -> np.ndarray:
    """True where [start, end] meets one of the merged, sorted, non-overlapping intervals."""
    s = np.asarray(pd.to_datetime(start, utc=True).dt.tz_localize(None), dtype="datetime64[s]").astype("int64")
    e = np.asarray(pd.to_datetime(end, utc=True).dt.tz_localize(None), dtype="datetime64[s]").astype("int64")
    if not intervals:
        return np.zeros(len(s), bool)
    a = np.array([x.astimezone(timezone.utc).replace(tzinfo=None) for x, _ in intervals], dtype="datetime64[s]").astype("int64")
    b = np.array([y.astimezone(timezone.utc).replace(tzinfo=None) for _, y in intervals], dtype="datetime64[s]").astype("int64")
    i = np.searchsorted(a, e, side="right") - 1            # the last interval that starts at or before the end of the window
    return (i >= 0) & (b[np.clip(i, 0, None)] >= s)


def adverse_hours(asos: pd.DataFrame) -> dict[str, pd.Series]:
    """Per hub, a cumulative count of adverse-weather hours indexed by UTC hour, to test any window in constant time."""
    a = asos.copy()
    a["hour"] = pd.to_datetime(a["obs_utc"]).dt.floor("h")
    a["adverse"] = a[list(ADVERSE)].any(axis=1)
    out = {}
    for hub, g in a.groupby("station"):
        h = g.groupby("hour")["adverse"].max()
        full = h.reindex(pd.date_range(h.index.min(), h.index.max(), freq="h"), fill_value=False).astype(int)
        out[hub] = full.cumsum()
    return out


def weather_overlap(df: pd.DataFrame, cum: dict[str, pd.Series]) -> np.ndarray:
    res = np.zeros(len(df), bool)
    for hub, c in cum.items():
        m = (df["hub"] == hub).to_numpy()
        if not m.any():
            continue
        s = pd.to_datetime(df.loc[m, "w_start"], utc=True).dt.tz_localize(None).dt.floor("h")
        e = pd.to_datetime(df.loc[m, "w_end"], utc=True).dt.tz_localize(None).dt.floor("h")
        lo = c.index.min()
        hi = c.index.max()
        s2, e2 = s.clip(lower=lo, upper=hi), e.clip(lower=lo, upper=hi)
        before = c.reindex(s2 - pd.Timedelta(hours=1)).fillna(0).to_numpy()          # cumulative count up to the hour before the window starts
        within = c.reindex(e2).to_numpy() - before
        valid = ((e >= lo) & (s <= hi)).to_numpy()
        res[m] = valid & (within > 0)
    return res


def evaluate(df: pd.DataFrame, programs: list[dict], asos: pd.DataFrame) -> dict:
    """The two triggers on the missed overnight connections of `df`: hub, in_sched_arr, arr_delay_min, in_cancelled, in_diverted,
    cause, weight, cost (the payout), ym. Returns the measures of the module docstring."""
    d = window_utc(df)
    iv = faa.active_intervals(programs)
    t1 = np.zeros(len(d), bool)
    for hub, spans in iv.items():
        m = (d["hub"] == hub).to_numpy()
        if m.any():
            t1[m] = overlaps(spans, d.loc[m, "w_start"], d.loc[m, "w_end"])
    t2 = t1 | weather_overlap(d, adverse_hours(asos))
    pay = (d["weight"] * d["cost"]).to_numpy(float)
    gap = (d["cause"] != "carrier").to_numpy()
    out = {"connections_weighted": float(d["weight"].sum())}
    series = {"gap": pay * gap, "T1": pay * t1, "T2": pay * t2}
    monthly = pd.DataFrame(series).groupby(d["ym"].to_numpy()).sum()
    for name, t in (("T1", t1), ("T2", t2)):
        tp = pay * t
        out[name] = {"coverage": float((pay * gap * t).sum() / (pay * gap).sum()), "leakage": float((tp * ~gap).sum() / tp.sum()) if tp.sum() else None,
                     "ratio": float(tp.sum() / (pay * gap).sum()), "monthly_ratio_sd": float((monthly[name] / monthly["gap"]).std(ddof=1)),
                     "monthly_correlation": float(np.corrcoef(monthly[name], monthly["gap"])[0, 1]), "share_of_missed_overnight_paid": float((pay * t).sum() / pay.sum())}
    out["gap_share_of_missed_overnight"] = float((pay * gap).sum() / pay.sum())
    out["months"] = int(len(monthly))
    return out


def load_rows(start: str, end: str) -> pd.DataFrame:
    """Missed overnight connections of the active variant between two months (inclusive), with the inbound flight's delay and cause."""
    import duckdb
    from mcp.causes import inbound_cause_sql
    from mcp.connections import WEIGHTED
    from mcp.pricing import SEVERITY
    from mcp.variant import sfx
    severity_full = SEVERITY.with_name(f"{sfx('severity_full')}.parquet")      # the active variant's table (v3's name is fixed inside mcp.v3, which is why it is not used)
    from mcp.v3 import claim_cost, gsa_table
    from mcp.features import FLIGHTS
    con = duckdb.connect()
    files = (WEIGHTED / "mct=45" / "year=*" / "*.parquet").as_posix()
    sql = f"""
    WITH ic AS ({inbound_cause_sql()}),
    fl AS (SELECT carrier, flight_date, flight_number, crs_dep_hhmm, origin, dest, arr_delay_min FROM read_parquet('{FLIGHTS}'))
    SELECT r.hub, r.carrier, r.in_sched_arr, r.out_sched_dep, r.weight, r.in_cancelled, r.in_diverted, fl.arr_delay_min,
           COALESCE(ic.cause, 'unattributed') AS cause, strftime(r.out_sched_dep, '%Y-%m') AS ym
    FROM read_parquet('{files}') r
    JOIN read_parquet('{severity_full.as_posix()}') s ON s.carrier = r.carrier AND s.flight_date = r.out_flight_date
         AND s.flight_number = r.out_flight_number AND s.crs_dep_hhmm = r.out_crs_dep_hhmm
    LEFT JOIN ic ON ic.carrier = r.carrier AND ic.flight_date = r.in_flight_date AND ic.flight_number = r.in_flight_number
                AND ic.crs_dep_hhmm = r.in_crs_dep_hhmm AND ic.origin = r.origin AND ic.dest = r.hub
    LEFT JOIN fl ON fl.carrier = r.carrier AND fl.flight_date = r.in_flight_date AND fl.flight_number = r.in_flight_number
                AND fl.crs_dep_hhmm = r.in_crs_dep_hhmm AND fl.origin = r.origin AND fl.dest = r.hub
    WHERE r.missed AND s.overnight
      AND r.out_sched_dep >= TIMESTAMP '{start}-01' AND r.out_sched_dep < TIMESTAMP '{start}-01' + INTERVAL '{months_between(start, end) + 1} months'
    """
    df = con.execute(sql).fetchdf()
    df["cost"] = claim_cost(df.assign(overnight=1), gsa_table())
    return df


def months_between(start: str, end: str) -> int:
    return (int(end[:4]) - int(start[:4])) * 12 + int(end[5:]) - int(start[5:])


def pandemic_free(df: pd.DataFrame) -> pd.DataFrame:
    return df[~((df["ym"] >= "2020-03") & (df["ym"] <= "2021-06"))]


def run(start: str, end: str, label: str) -> dict:
    import duckdb
    df = pandemic_free(load_rows(start, end))
    asos = duckdb.connect().execute(f"SELECT * FROM read_parquet('{ASOS_ALL.as_posix()}')").fetchdf()
    res = {"period": [start, end], "label": label, **evaluate(df, faa.programs(start, end), asos)}
    path = json.loads(RESULT.read_text(encoding="utf-8")) if RESULT.exists() else {}
    path[label] = res
    RESULT.write_text(json.dumps(path, indent=1) + "\n", encoding="utf-8", newline="\n")
    return res


if __name__ == "__main__":
    {"dev": lambda: run("2024-01", "2026-08", "development_2024_2026"), "backcast": lambda: run("2019-01", "2023-12", "backcast_2019_2023")}[sys.argv[1]]()
