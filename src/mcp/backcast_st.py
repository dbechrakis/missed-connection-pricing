"""The self-transfer arm of the v6 backcast (expectation B8), January 2019 to December 2023.

PREREGISTRATION_V6_BACKCAST.md section 3 and its addendum fix this: v5's pairings (two different marketing networks, 90 to
300 minute gaps, minimum self-transfer time 90, any cause), a 5% hash sample, v5's cell table with k = 1000, payout the
DB1B nonstop one-way fare of the PREVIOUS calendar year plus a GSA night when no later departure exists that day. For a
month m the table is fitted on non-pandemic months up to m - 5 (the newest month BTS has published when a self-transfer is
sold), a month is scored when at least six such months exist, and the same table with a loading re-estimated from the
earlier scored months (up to m - 5, at least three) is compared with it.

    cd src
    MCP_VARIANT=hist python -m mcp.backcast_st build 2018-01 2023-12     # counts only
    MCP_VARIANT=hist python -m mcp.backcast_st fares                      # DB1B nonstop fares by year
    MCP_VARIANT=hist python -m mcp.backcast_st run                        # writes data/parquet/hist_backcast/self_transfer.json, no rates printed
"""
from __future__ import annotations

import json
import sys
import zipfile

import duckdb
import numpy as np
import pandas as pd

from mcp import v5
from mcp.backcast import DATA, SCORED, is_pandemic, shift
from mcp.costs import overnight_cost
from mcp.ingest import HIST_QUARTERS, ROOT
from mcp.v3 import gsa_table
from mcp.variant import HIST, VARIANT

ONTIME = ROOT / "data" / "parquet" / "ontime_hist"
PAIRS = DATA / "v5_pairs"
FARES = DATA / "fares_by_year.parquet"
OUT = DATA / "self_transfer.json"
LAG = 5
MIN_FIT_MONTHS = 6
MIN_LOADING_MONTHS = 3
K = 1000
TARGET = v5.TARGET_LR


def month_path(y: int, m: int):
    return PAIRS / f"year={y}" / f"month={m:02d}.parquet"


def build(start: str, end: str) -> None:
    """One Parquet per month of outbound departure, as `mcp.v5.build --sealed`: counts only, never an outcome rate."""
    assert HIST, "run with MCP_VARIANT=hist"
    con = duckdb.connect()
    con.execute(f"CREATE VIEW flights AS SELECT * FROM read_parquet('{(ONTIME / '*' / '*.parquet').as_posix()}')")
    for y, m in v5.months(start, end):
        out = month_path(y, m)
        if out.exists():
            continue
        first = f"{y}-{m:02d}-01"
        con.execute(f"""CREATE OR REPLACE TEMP VIEW month_flights AS SELECT * FROM flights
                        WHERE flight_date BETWEEN DATE '{first}' - INTERVAL 1 DAY AND DATE '{first}' + INTERVAL 1 MONTH""")
        out.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"""COPY (SELECT * FROM ({v5.pairs_sql('month_flights', v5.T_MIN)})
                              WHERE out_sched_dep >= TIMESTAMP '{first}' AND out_sched_dep < TIMESTAMP '{first}' + INTERVAL 1 MONTH)
                        TO '{out.as_posix()}' (FORMAT parquet, COMPRESSION zstd)""")
        n, ok = con.execute(f"SELECT count(*), sum((status = 'ok')::INT) FROM '{out.as_posix()}'").fetchone()
        print(f"{y}-{m:02d}: {n:,} sampled pairings, {ok:,} usable", flush=True)


def fares() -> int:
    """Passenger-weighted mean one-way fare of every nonstop market, by `fare_year` = the year AFTER the quarters it is
    computed from, so a month never sees a fare of its own year."""
    con, parts = duckdb.connect(), []
    for q in HIST_QUARTERS:
        y, qn = int(q[:4]), int(q[-1])
        zp = v5.DB1B_RAW / f"Market_{y}_{qn}.zip"
        with zipfile.ZipFile(zp) as z:
            (member,) = [n for n in z.namelist() if n.lower().endswith(".csv")]
            csv = v5.DB1B_RAW / f"Market_{y}_{qn}.csv"
            with z.open(member) as src, csv.open("wb") as f:
                while chunk := src.read(1 << 24):
                    f.write(chunk)
        try:
            d = con.execute(f"""
              SELECT Origin AS origin, Dest AS dest, sum(TRY_CAST(Passengers AS DOUBLE)) AS pax,
                     sum(TRY_CAST(Passengers AS DOUBLE) * TRY_CAST(MktFare AS DOUBLE)) AS fare_x_pax
              FROM read_csv('{csv.as_posix()}', header=true, all_varchar=true)
              WHERE TRY_CAST(MktCoupons AS INTEGER) = 1 AND TRY_CAST(BulkFare AS DOUBLE) = 0
                AND TRY_CAST(MktFare AS DOUBLE) BETWEEN {v5.FARE_MIN} AND {v5.FARE_MAX}
              GROUP BY ALL""").fetchdf()
        finally:
            csv.unlink(missing_ok=True)
        d["fare_year"] = y + 1
        parts.append(d)
    df = pd.concat(parts).groupby(["origin", "dest", "fare_year"], as_index=False)[["pax", "fare_x_pax"]].sum()
    df["fare"] = df["fare_x_pax"] / df["pax"]
    FARES.parent.mkdir(parents=True, exist_ok=True)
    df[["origin", "dest", "fare_year", "pax", "fare"]].to_parquet(FARES, index=False)
    return len(df)


def month_frame(y: int, m: int, fares_df: pd.DataFrame, table: dict) -> pd.DataFrame:
    """Usable pairings of one month with the previous year's fares, the payout and the cells (`mcp.v5.frame`, by year)."""
    df = pd.read_parquet(month_path(y, m))
    df = df[df["status"] == "ok"].copy()
    f = fares_df[fares_df["fare_year"] == y][["origin", "dest", "fare"]]
    df = df.merge(f.rename(columns={"origin": "hub", "dest": "destination", "fare": "fare_onward"}), on=["hub", "destination"], how="left")
    df = df[df["fare_onward"].notna()].copy()
    dep = pd.to_datetime(df["out_sched_dep"])
    keys = pd.DataFrame({"hub": df["hub"].to_numpy(), "y": dep.dt.year.to_numpy(), "m": dep.dt.month.to_numpy()})
    cost = {k: overnight_cost(table, *k) for k in keys.drop_duplicates().itertuples(index=False, name=None)}
    night = np.array([cost[k] for k in keys.itertuples(index=False, name=None)])
    df["payout"] = df["fare_onward"] + night * df["overnight"]
    df["bucket"] = (v5.GAP_LO + v5.BUCKET * ((df["slack_min"] - v5.GAP_LO) // v5.BUCKET)).clip(upper=v5.GAP_HI - v5.BUCKET)
    df["band"] = v5.band_of(pd.to_datetime(df["in_sched_arr"]).dt.hour.to_numpy())
    return df


# ---- the table from monthly sufficient statistics, and the walk-forward --------------------------------------------

def month_stats(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby(v5.CELL)["missed"].agg(["sum", "count"]).reset_index()


def table_from_stats(stats: pd.DataFrame, k: float) -> dict:
    """`mcp.v5.fit_table` from per-cell sums and counts (which may come from several months). Identical by construction."""
    cells = stats.groupby(v5.CELL)[["sum", "count"]].sum().reset_index()
    pri = cells.groupby(v5.PRIOR)[["sum", "count"]].sum()
    p0 = pri["sum"] / pri["count"]
    hub = cells.groupby("hub")[["sum", "count"]].sum()
    cells["prior"] = p0.reindex(pd.MultiIndex.from_frame(cells[v5.PRIOR])).to_numpy()
    cells["p"] = (cells["sum"] + k * cells["prior"]) / (cells["count"] + k)
    return {"k": k,
            "cells": {f"{h}|{c}|{int(b)}|{int(d)}": float(p) for h, c, b, d, p in cells[[*v5.CELL, "p"]].itertuples(index=False)},
            "prior": {f"{h}|{int(b)}": float(v) for (h, b), v in p0.items()},
            "hub": {h: float(v) for h, v in (hub["sum"] / hub["count"]).items()}}


def calendar(first: str, last: str) -> list[str]:
    out, m = [], first
    while m <= last:
        out.append(m)
        m = shift(m, 1)
    return out


def walk_forward(stats: dict, month_df, scored: list[str], pandemic=is_pandemic, lag: int = LAG, k: float = K,
                 min_fit: int = MIN_FIT_MONTHS, min_loading: int = MIN_LOADING_MONTHS) -> dict:
    """Month by month: the table fitted on the non-pandemic months up to m - lag, the month scored with it, and the loading
    re-estimated from the earlier scored months (up to m - lag, at least `min_loading`).

    `stats` maps 'YYYY-MM' to that month's per-cell sums and counts. `month_df(ym)` returns the month's frame with
    `missed`, `payout` and the cell columns. Nothing later than m - lag enters m's table or loading."""
    rows = {}
    for m in scored:
        if pandemic(m):
            continue
        known = [s for s in sorted(stats) if s <= shift(m, -lag) and not pandemic(s)]
        if len(known) < min_fit:
            continue
        table = table_from_stats(pd.concat([stats[s] for s in known]), k)
        df = month_df(m)
        p = v5.score(df, table)
        w = df["payout"].to_numpy()
        rows[m] = {"claims": float((df["missed"].to_numpy() * w).sum()), "expected": float((p * w).sum()), "pairings": int(len(df)), "fit_months": len(known)}
    loaded = {}
    for m in rows:
        earlier = [s for s in rows if s <= shift(m, -lag)]
        if len(earlier) < min_loading:
            continue
        lam = sum(rows[s]["claims"] for s in earlier) / sum(rows[s]["expected"] for s in earlier)
        loaded[m] = lam
    both = [m for m in rows if m in loaded]
    c = sum(rows[m]["claims"] for m in both)
    e = sum(rows[m]["expected"] for m in both)
    el = sum(rows[m]["expected"] * loaded[m] for m in both)
    return {"months_scored": len(rows), "months_compared": len(both), "ratio_unloaded": c / e if e else float("nan"),
            "ratio_loaded": c / el if el else float("nan"), "pooled_all_scored": sum(r["claims"] for r in rows.values()) / sum(r["expected"] for r in rows.values()),
            "monthly_ratio": {m: r["claims"] / r["expected"] for m, r in rows.items()}, "loading": loaded}


def run() -> dict:
    assert VARIANT == "hist", "run with MCP_VARIANT=hist"
    fares_df, table = pd.read_parquet(FARES), gsa_table()
    cal = calendar("2018-01", SCORED[1])
    stats, cache = {}, {}
    for ym in cal:
        y, m = int(ym[:4]), int(ym[5:])
        if not month_path(y, m).exists():
            raise SystemExit(f"missing pairings for {ym}: run build first")
        df = month_frame(y, m, fares_df, table)
        stats[ym] = month_stats(df)
        if ym >= SCORED[0]:
            cache[ym] = df
    res = walk_forward(stats, lambda ym: cache[ym], calendar(*SCORED))
    res["status"] = "the self-transfer arm of the v6 backcast; merged into results/backcast.json at the single read"
    OUT.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return {"months_scored": res["months_scored"], "months_compared": res["months_compared"]}


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "build":
        build(sys.argv[2], sys.argv[3])
    elif cmd == "fares":
        print(f"fare rows: {fares():,}")
    elif cmd == "run":
        print(run())
