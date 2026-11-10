"""v5: protection for self-transfer connections, exactly as PREREGISTRATION_V5_SELF_TRANSFER.md fixes it.

A self-transfer is an inbound A -> H on one marketing network and an outbound H -> B on another, sold as two tickets.
No airline owes the traveller anything if the first flight is late, so the cover pays on any cause: a replacement
one-way fare H -> B (DB1B nonstop mean, train quarters), plus a GSA night when no later H -> B departure exists that
day. The price comes from a cell table, shrunk toward hub x gap bucket with k pseudo-connections.

    python -m mcp.v5 fares                     DB1B nonstop one-way fares (train quarters)
    python -m mcp.v5 build --t 90              cross-network pairings, January 2024 to December 2025 (rates shown)
    python -m mcp.v5 build --t 90 --sealed     January to August 2026, counts only
    python -m mcp.v5 select                    choose k on July to December 2025
    python -m mcp.v5 fit                       the frozen table, models/v5_table.json
    python -m mcp.v5 holdout                   reads January to August 2026 once (refuses a second run)

The pairings are a uniform hash sample of the population (SAMPLE_FRAC), because the full cross product is hundreds of
millions of rows. A uniform sample of an unweighted population estimates the same quantities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from mcp.connections import connections_sql
from mcp.costs import overnight_cost
from mcp.ingest import HUBS, ROOT

ONTIME = ROOT / "data" / "parquet" / "ontime_v3"            # the Marketing Carrier file: carrier = marketing network
PAIRS = ROOT / "data" / "parquet" / "v5_pairs"
DB1B_RAW = ROOT / "data" / "raw" / "db1b"
FARES = ROOT / "data" / "parquet" / "db1b" / "nonstop_fares.parquet"
GSA = ROOT / "results" / "gsa_costs.json"
TABLE = ROOT / "models" / "v5_table.json"
SELECTION = ROOT / "results" / "v5_selection.json"
HOLDOUT_RESULT = ROOT / "results" / "v5_holdout.json"

T_MIN = 90                      # minimum self-transfer time (pre-registered; 60 and 120 are sensitivity only)
GAP_LO, GAP_HI = 90, 300
BUCKET = 15
BANDS = ((5, 11), (11, 16), (16, 21))                       # 05:00-10:59, 11:00-15:59, 16:00-20:59; the rest is band 3
K_GRID = (0, 50, 200, 1000)
TOLERANCE = 0.0002
TARGET_LR = 0.65
CAP, CAP_SENSITIVITY = 0.10, (0.05, 0.15)
SAMPLE_FRAC = 0.05
TRAIN_QUARTERS = ((2024, 1), (2024, 2), (2024, 3), (2024, 4), (2025, 1), (2025, 2))
FARE_MIN, FARE_MAX = 20.0, 5000.0                            # the same placeholder and outlier rule as mcp.ingest
WINDOWS = {"FIT": ("2024-01", "2025-06"), "SELECT": ("2025-07", "2025-12"),
           "FINAL": ("2024-01", "2025-12"), "SEALED": ("2026-01", "2026-08")}


def months(start: str, end: str):
    y, m = int(start[:4]), int(start[5:])
    while f"{y}-{m:02d}" <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def legs_cte(flights: str) -> str:
    """The tested t / f / legs CTEs of connections_sql (timezones, actual times), without its same-carrier pairing."""
    sql = connections_sql(flights, 0, 0)
    return sql[: sql.index("pairs AS (")].rstrip().rstrip(",")


def pairs_sql(flights: str, t_min: int, frac: float = SAMPLE_FRAC, hubs=HUBS) -> str:
    """One row per sampled cross-network pairing at a hub, with the any-cause label and the overnight flag."""
    hub_list = ", ".join(f"'{h}'" for h in hubs)
    keep = int(frac * 1_000_000)
    return f"""
    {legs_cte(flights)},
    last_dep AS (
      SELECT origin AS hub, dest AS destination, sched_dep::DATE AS day, max(sched_dep) AS last_sched_dep
      FROM legs WHERE origin IN ({hub_list}) GROUP BY ALL
    ),
    pairs AS (
      SELECT i.dest AS hub, i.carrier AS in_carrier, o.carrier AS out_carrier, i.origin AS origin, o.dest AS destination,
             i.flight_date AS in_flight_date, i.flight_number AS in_flight_number,
             o.flight_date AS out_flight_date, o.flight_number AS out_flight_number,
             i.sched_arr AS in_sched_arr, o.sched_dep AS out_sched_dep,
             date_diff('minute', i.sched_arr, o.sched_dep) AS slack_min,
             i.cancelled AS in_cancelled, i.diverted AS in_diverted, o.cancelled AS out_cancelled,
             i.act_arr AS in_act_arr, o.act_dep AS out_act_dep
      FROM legs i JOIN legs o
        ON  i.carrier <> o.carrier
        AND i.dest = o.origin
        AND i.sched_arr::DATE = o.sched_dep::DATE
        AND o.sched_dep >= i.sched_arr + to_minutes({GAP_LO})
        AND o.sched_dep <= i.sched_arr + to_minutes({GAP_HI})
      WHERE i.dest IN ({hub_list}) AND i.origin <> o.dest
        AND (hash(i.carrier, i.flight_date, i.flight_number, o.carrier, o.flight_date, o.flight_number) % 1000000) < {keep}
    )
    SELECT p.* EXCLUDE (in_act_arr, out_act_dep), {t_min} AS t_min,
      CASE WHEN out_cancelled THEN 'outbound_cancelled'
           WHEN out_act_dep IS NULL THEN 'missing_time'
           WHEN NOT in_cancelled AND NOT in_diverted AND in_act_arr IS NULL THEN 'missing_time'
           ELSE 'ok' END AS status,
      (in_cancelled OR in_diverted OR (in_act_arr IS NOT NULL AND in_act_arr + to_minutes({t_min}) > out_act_dep))::INT AS missed,
      (in_cancelled OR in_diverted)::INT AS missed_by_cancellation,
      (p.out_sched_dep = l.last_sched_dep)::INT AS overnight
    FROM pairs p
    JOIN last_dep l ON l.hub = p.hub AND l.destination = p.destination AND l.day = p.out_sched_dep::DATE
    """


def month_path(t_min: int, y: int, m: int) -> Path:
    return PAIRS / f"t={t_min}" / f"year={y}" / f"month={m:02d}.parquet"


def build(t_min: int, start: str, end: str, sealed: bool) -> None:
    """Write one Parquet per month of outbound departure. Sealed months print counts only, never an outcome rate."""
    con = duckdb.connect()
    con.execute(f"CREATE VIEW flights AS SELECT * FROM read_parquet('{(ONTIME / '*' / '*.parquet').as_posix()}')")
    for y, m in months(start, end):
        first = f"{y}-{m:02d}-01"
        con.execute(f"""CREATE OR REPLACE TEMP VIEW month_flights AS SELECT * FROM flights
                        WHERE flight_date BETWEEN DATE '{first}' - INTERVAL 1 DAY AND DATE '{first}' + INTERVAL 1 MONTH""")
        out = month_path(t_min, y, m)
        out.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"""COPY (SELECT * FROM ({pairs_sql('month_flights', t_min)})
                              WHERE out_sched_dep >= TIMESTAMP '{first}' AND out_sched_dep < TIMESTAMP '{first}' + INTERVAL 1 MONTH)
                        TO '{out.as_posix()}' (FORMAT parquet, COMPRESSION zstd)""")
        n, ok = con.execute(f"SELECT count(*), sum((status = 'ok')::INT) FROM '{out.as_posix()}'").fetchone()
        line = f"t={t_min} {y}-{m:02d}: {n:,} sampled pairings, {ok:,} usable"
        if not sealed:
            (rate,) = con.execute(f"SELECT avg(missed) FROM '{out.as_posix()}' WHERE status = 'ok'").fetchone()
            line += f", miss rate {rate:.2%}"
        print(line, flush=True)


def fares() -> int:
    """Passenger-weighted mean one-way fare for every nonstop market in the train quarters (all carriers)."""
    con, parts = duckdb.connect(), []
    for y, q in TRAIN_QUARTERS:
        zp = DB1B_RAW / f"Market_{y}_{q}.zip"
        with zipfile.ZipFile(zp) as z:
            (member,) = [n for n in z.namelist() if n.lower().endswith(".csv")]
            csv = DB1B_RAW / f"Market_{y}_{q}.csv"
            with z.open(member) as src, csv.open("wb") as f:
                while chunk := src.read(1 << 24):
                    f.write(chunk)
        try:
            parts.append(con.execute(f"""
              SELECT Origin AS origin, Dest AS dest, sum(TRY_CAST(Passengers AS DOUBLE)) AS pax,
                     sum(TRY_CAST(Passengers AS DOUBLE) * TRY_CAST(MktFare AS DOUBLE)) AS fare_x_pax
              FROM read_csv('{csv.as_posix()}', header=true, all_varchar=true)
              WHERE TRY_CAST(MktCoupons AS INTEGER) = 1 AND TRY_CAST(BulkFare AS DOUBLE) = 0
                AND TRY_CAST(MktFare AS DOUBLE) BETWEEN {FARE_MIN} AND {FARE_MAX}
              GROUP BY ALL""").fetchdf())
        finally:
            csv.unlink(missing_ok=True)
    df = pd.concat(parts).groupby(["origin", "dest"], as_index=False)[["pax", "fare_x_pax"]].sum()
    df["fare"] = df["fare_x_pax"] / df["pax"]
    FARES.parent.mkdir(parents=True, exist_ok=True)
    df[["origin", "dest", "pax", "fare"]].to_parquet(FARES, index=False)
    return len(df)


def gsa_table() -> dict:
    raw = json.loads(GSA.read_text())["rates"]
    return {h: {int(fy): {**p, "lodging": {int(mo): v for mo, v in p["lodging"].items()}} for fy, p in v.items()}
            for h, v in raw.items()}


def band_of(hour: np.ndarray) -> np.ndarray:
    out = np.full(len(hour), 3)
    for i, (lo, hi) in enumerate(BANDS):
        out[(hour >= lo) & (hour < hi)] = i
    return out


def frame(t_min: int, start: str, end: str, fare_multiplier: float = 1.0) -> tuple[pd.DataFrame, dict]:
    """Usable pairings of a window, with fares, payout and the cells. Returns the frame and the drop counts."""
    files = [month_path(t_min, y, m).as_posix() for y, m in months(start, end)]
    df = duckdb.connect().execute(f"SELECT * FROM read_parquet({files})").fetchdf()
    counts = {"pairings": len(df), "not_usable": int((df["status"] != "ok").sum())}
    df = df[df["status"] == "ok"].copy()
    f = pd.read_parquet(FARES)[["origin", "dest", "fare"]]
    df = df.merge(f.rename(columns={"origin": "hub", "dest": "destination", "fare": "fare_onward"}), on=["hub", "destination"], how="left")
    df = df.merge(f.rename(columns={"dest": "hub", "fare": "fare_inbound"}), on=["origin", "hub"], how="left")
    counts["no_onward_fare"] = int(df["fare_onward"].isna().sum())
    df = df[df["fare_onward"].notna()].copy()
    table = gsa_table()
    dep = pd.to_datetime(df["out_sched_dep"])
    keys = pd.DataFrame({"hub": df["hub"].to_numpy(), "y": dep.dt.year.to_numpy(), "m": dep.dt.month.to_numpy()})
    cost = {k: overnight_cost(table, *k) for k in keys.drop_duplicates().itertuples(index=False, name=None)}
    night = np.array([cost[k] for k in keys.itertuples(index=False, name=None)])
    df["payout"] = fare_multiplier * df["fare_onward"] + night * df["overnight"]
    df["fare_total"] = df["fare_inbound"] + df["fare_onward"]
    df["bucket"] = (GAP_LO + BUCKET * ((df["slack_min"] - GAP_LO) // BUCKET)).clip(upper=GAP_HI - BUCKET)
    df["band"] = band_of(pd.to_datetime(df["in_sched_arr"]).dt.hour.to_numpy())
    df["ym"] = dep.dt.strftime("%Y-%m")
    df["week"] = (dep.dt.normalize() - pd.to_timedelta(dep.dt.day_of_week, unit="D")).dt.strftime("%Y-%m-%d")
    counts["usable"] = len(df)
    return df, counts


CELL = ["hub", "in_carrier", "bucket", "band"]
PRIOR = ["hub", "bucket"]


def fit_table(df: pd.DataFrame, k: float) -> dict:
    prior = df.groupby(PRIOR)["missed"].agg(["sum", "count"])
    hub = df.groupby("hub")["missed"].mean()
    cells = df.groupby(CELL)["missed"].agg(["sum", "count"]).reset_index()
    p0 = prior["sum"] / prior["count"]
    cells["prior"] = p0.reindex(pd.MultiIndex.from_frame(cells[PRIOR])).to_numpy()
    cells["p"] = (cells["sum"] + k * cells["prior"]) / (cells["count"] + k)
    return {"k": k,
            "cells": {f"{h}|{c}|{int(b)}|{int(d)}": float(p) for h, c, b, d, p in cells[[*CELL, "p"]].itertuples(index=False)},
            "prior": {f"{h}|{int(b)}": float(v) for (h, b), v in p0.items()},
            "hub": {h: float(v) for h, v in hub.items()}}


def score(df: pd.DataFrame, table: dict) -> np.ndarray:
    """The cell's rate, else its hub x gap prior, else the hub's rate."""
    hub, bucket = df["hub"].astype(str), df["bucket"].astype(int).astype(str)
    cell = hub + "|" + df["in_carrier"].astype(str) + "|" + bucket + "|" + df["band"].astype(int).astype(str)
    p = cell.map(table["cells"])
    p = p.fillna((hub + "|" + bucket).map(table["prior"]))
    return p.fillna(hub.map(table["hub"])).to_numpy(dtype=float)


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def realized_over_target(df: pd.DataFrame, p: np.ndarray, weight: np.ndarray | None = None, payout: np.ndarray | None = None) -> float:
    w = np.ones(len(df)) if weight is None else weight
    c = df["payout"].to_numpy() if payout is None else payout
    return float((w * df["missed"].to_numpy() * c).sum() / (w * p * c).sum())


def week_bootstrap(df: pd.DataFrame, p: np.ndarray, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    g = pd.DataFrame({"week": df["week"].to_numpy(), "c": (df["missed"] * df["payout"]).to_numpy(), "e": p * df["payout"].to_numpy()})
    w = g.groupby("week")[["c", "e"]].sum()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(w), (n_boot, len(w)))
    r = w["c"].to_numpy()[idx].sum(1) / w["e"].to_numpy()[idx].sum(1)
    return float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))


def select(t_min: int = T_MIN) -> dict:
    fit, _ = frame(t_min, *WINDOWS["FIT"])
    sel, counts = frame(t_min, *WINDOWS["SELECT"])
    losses = {k: log_loss(sel["missed"].to_numpy(), score(sel, fit_table(fit, k))) for k in K_GRID}
    best = min(losses.values())
    chosen = max(k for k, v in losses.items() if v <= best + TOLERANCE)        # ties go to the larger k
    p = score(sel, fit_table(fit, chosen))
    out = {"t_min": t_min, "log_loss": {str(k): v for k, v in losses.items()}, "chosen_k": chosen,
           "selection_realized_over_target": realized_over_target(sel, p), "selection_counts": counts,
           "status": "development: July to December 2025, used only to choose k"}
    SELECTION.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def fit(t_min: int = T_MIN) -> str:
    k = json.loads(SELECTION.read_text())["chosen_k"]
    df, counts = frame(t_min, *WINDOWS["FINAL"])
    table = {**fit_table(df, k), "t_min": t_min, "fitted_on": WINDOWS["FINAL"], "counts": counts}
    TABLE.write_text(json.dumps(table, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return hashlib.sha256(TABLE.read_bytes()).hexdigest()


def holdout_metrics(df: pd.DataFrame, p: np.ndarray) -> dict:
    ratio = realized_over_target(df, p)
    lo, hi = week_bootstrap(df, p)
    by = lambda col: {str(k): realized_over_target(g, p[g.index.to_numpy()]) for k, g in df.groupby(col)}
    price = p * df["payout"].to_numpy() / TARGET_LR
    share = price / df["fare_total"].to_numpy()
    caps = {}
    for cap in (CAP, *CAP_SENSITIVITY):
        sold = (share <= cap) & np.isfinite(share)
        caps[f"{cap:.2f}"] = {"share_offered": float(sold.mean()),
                              "realized_over_target": realized_over_target(df[sold], p[sold]) if sold.any() else float("nan")}
    monthly = by("ym")
    first, later = df["bucket"] == GAP_LO, df["bucket"] == GAP_LO + 5 * BUCKET
    s3 = {h: (float(df.loc[first & (df["hub"] == h), "missed"].mean()), float(df.loc[later & (df["hub"] == h), "missed"].mean()))
          for h in HUBS}
    misses = df["missed"].sum()
    return {"realized_over_target": ratio, "interval_95": [lo, hi], "by_hub": by("hub"), "monthly": monthly,
            "by_bucket": by("bucket"), "cap": caps, "miss_rate": float(df["missed"].mean()),
            "share_of_misses_by_cancellation_or_diversion": float(df["missed_by_cancellation"].sum() / misses) if misses else float("nan"),
            "monthly_sd": float(np.std(list(monthly.values()), ddof=1)), "s3_rates_90_vs_165": s3, "n": len(df)}


def grade(m: dict) -> dict:
    return {
        "S1": 0.85 <= m["realized_over_target"] <= 1.15,
        "S2": 0.20 <= m["share_of_misses_by_cancellation_or_diversion"] <= 0.50,
        "S3": all(a > b for a, b in m["s3_rates_90_vs_165"].values()),
        "S4": 0.08 <= m["monthly_sd"] <= 0.35,
        "S5": m["cap"][f"{CAP:.2f}"]["realized_over_target"] > m["realized_over_target"],
    }


MIX_SCALE = 60.0                                            # e^(-buffer/60), as VALIDATION.md 5K
PAYOUT_MULTIPLIERS = (1.5, 2.0)
T_SENSITIVITY = (60, 120)


def sensitivities(df: pd.DataFrame, p: np.ndarray, k: float) -> dict:
    """The pre-registered sensitivities, computed in the same single read: payout, mix, and T rebuilt and refitted."""
    night = (df["payout"] - df["fare_onward"]).to_numpy()
    out = {"payout_multiplier": {str(m): realized_over_target(df, p, payout=m * df["fare_onward"].to_numpy() + night)
                                 for m in PAYOUT_MULTIPLIERS}}
    buffer = (df["slack_min"] - df["t_min"]).to_numpy()
    out["mix_prefer_short"] = realized_over_target(df, p, weight=np.exp(-buffer / MIX_SCALE))
    out["t_min"] = {}
    for t in T_SENSITIVITY:
        dev, _ = frame(t, *WINDOWS["FINAL"])
        sealed, _ = frame(t, *WINDOWS["SEALED"])
        sealed = sealed.reset_index(drop=True)
        q = score(sealed, fit_table(dev, k))
        out["t_min"][str(t)] = {"realized_over_target": realized_over_target(sealed, q), "miss_rate": float(sealed["missed"].mean())}
    return out


def holdout() -> dict:
    """The single read of January to August 2026 under the frozen table."""
    if HOLDOUT_RESULT.exists():
        raise SystemExit(f"{HOLDOUT_RESULT.name} exists: the holdout has been read. It is read once.")
    table = json.loads(TABLE.read_text())
    df, counts = frame(table["t_min"], *WINDOWS["SEALED"])
    df = df.reset_index(drop=True)
    p = score(df, table)
    m = holdout_metrics(df, p)
    out = {"table_sha256": hashlib.sha256(TABLE.read_bytes()).hexdigest(), "counts": counts, "primary": m, "grades": grade(m),
           "sensitivity": sensitivities(df, p, table["k"])}
    HOLDOUT_RESULT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["fares", "build", "select", "fit", "holdout"])
    p.add_argument("--t", type=int, default=T_MIN)
    p.add_argument("--sealed", action="store_true", help="build: counts only, never an outcome rate (default window January to August 2026)")
    p.add_argument("--start", default=None, help="build: first month, YYYY-MM (overrides the default window)")
    p.add_argument("--end", default=None, help="build: last month, YYYY-MM")
    a = p.parse_args(argv)
    if a.step == "fares":
        print(f"{fares():,} nonstop markets")
    elif a.step == "build":
        start, end = WINDOWS["SEALED"] if a.sealed else WINDOWS["FINAL"]
        build(a.t, a.start or start, a.end or end, sealed=a.sealed)
    elif a.step == "select":
        print(json.dumps(select(a.t), indent=1))
    elif a.step == "fit":
        print("models/v5_table.json sha256", fit(a.t))
    else:
        r = holdout()
        print(json.dumps({"grades": r["grades"], "realized_over_target": r["primary"]["realized_over_target"]}, indent=1))


if __name__ == "__main__":
    main()
