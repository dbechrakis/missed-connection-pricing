"""Three features of the timetable, known at booking, tested once (PREREGISTRATION_V6_SCHEDULE.md, expectation X1).

    hub_arr_15     flights of any marketing network scheduled to arrive at the hub in the inbound flight's quarter-hour
    hub_dep_15     flights scheduled to leave the hub in the onward flight's quarter-hour
    in_block_pad   the inbound flight's scheduled elapsed minutes minus the median actual elapsed minutes of the same network
                   on the same leg in the fit window (missing below MIN_LEG_FLIGHTS completed flights)

Every input is a scheduled field, except the leg's median actual time, which comes from the fit window only.

    cd src && MCP_VARIANT=hist python -m mcp.schedule_features     # fits three models, reads 2023 once, refuses a second run
"""
from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd

from mcp import backcast as B
from mcp import features as F
from mcp.ingest import HUBS, ROOT
from mcp.v5 import legs_cte

RESULT = ROOT / "results" / "schedule_features.json"
FEATURES = ("hub_arr_15", "hub_dep_15", "in_block_pad")
FIT, TEST = ("2018-01", "2023-01"), ("2023-01", "2023-12")          # the fit is half open and leaves the pandemic months out
MIN_LEG_FLIGHTS = 20
TIE_BAND = 0.0002
FRAC = 0.20


def slot_counts_sql(flights: str, hubs=HUBS) -> str:
    """Scheduled arrivals and departures per hub and quarter-hour of the hub-local clock. Cancelled flights are counted."""
    hub_list = ", ".join(f"'{h}'" for h in hubs)
    return f"""
    {legs_cte(flights)}
    SELECT 'arr' AS kind, dest AS hub, time_bucket(INTERVAL 15 MINUTE, sched_arr) AS slot, count(*) AS n FROM legs WHERE dest IN ({hub_list}) GROUP BY ALL
    UNION ALL
    SELECT 'dep' AS kind, origin AS hub, time_bucket(INTERVAL 15 MINUTE, sched_dep) AS slot, count(*) AS n FROM legs WHERE origin IN ({hub_list}) GROUP BY ALL
    """


def leg_history_sql(flights: str, fit_predicate: str) -> str:
    """Median actual elapsed minutes per network and leg over the fit window, for legs with enough completed flights."""
    return f"""
    SELECT carrier, origin, dest, median(actual_elapsed_min) AS med_elapsed, count(*) AS n
    FROM {flights}
    WHERE {fit_predicate} AND actual_elapsed_min IS NOT NULL AND NOT cancelled AND NOT diverted
    GROUP BY ALL HAVING count(*) >= {MIN_LEG_FLIGHTS}
    """


def attach(con, df: pd.DataFrame, flights: str = "flights") -> pd.DataFrame:
    """Add the three features to a frame that carries the connection keys. Needs the tables `slots` and `leg_hist` and the
    view `flights` on the connection. Row order and row count are kept."""
    d = df.reset_index(drop=True).copy()
    d["_row"] = np.arange(len(d))
    con.register("frame_in", d[["_row", "hub", "carrier", "origin", "in_flight_date", "in_flight_number", "in_crs_dep_hhmm", "in_sched_arr", "out_sched_dep"]])
    out = con.execute(f"""
      SELECT f._row, a.n AS hub_arr_15, dp.n AS hub_dep_15, (fl.crs_elapsed_min - h.med_elapsed) AS in_block_pad
      FROM frame_in f
      LEFT JOIN slots a ON a.kind = 'arr' AND a.hub = f.hub AND a.slot = time_bucket(INTERVAL 15 MINUTE, f.in_sched_arr)
      LEFT JOIN slots dp ON dp.kind = 'dep' AND dp.hub = f.hub AND dp.slot = time_bucket(INTERVAL 15 MINUTE, f.out_sched_dep)
      LEFT JOIN (SELECT carrier, flight_date, flight_number, crs_dep_hhmm, origin, dest, any_value(crs_elapsed_min) AS crs_elapsed_min
                 FROM {flights} GROUP BY ALL) fl
             ON fl.carrier = f.carrier AND fl.flight_date = f.in_flight_date AND fl.flight_number = f.in_flight_number
            AND fl.crs_dep_hhmm = f.in_crs_dep_hhmm AND fl.origin = f.origin AND fl.dest = f.hub
      LEFT JOIN leg_hist h ON h.carrier = f.carrier AND h.origin = f.origin AND h.dest = f.hub
      ORDER BY f._row""").fetchdf()
    con.unregister("frame_in")
    assert len(out) == len(d), "a join duplicated or lost connections"
    for c in FEATURES:
        d[c] = out[c].to_numpy(float)
    return d.drop(columns="_row")


def weighted_log_loss(y, p, w) -> float:
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y, w = np.asarray(y, float), np.asarray(w, float)
    return float(-(w * (y * np.log(p) + (1 - y) * np.log(1 - p))).sum() / w.sum())


def read() -> dict:
    from mcp.model import fit_gbm
    from mcp.v2 import FEATURE_SETS, LEAVES
    from mcp.v3 import claim_cost, gap_label_sql, gsa_table, labels, month_file, month_predicate
    from mcp.variant import VARIANT
    assert VARIANT == "hist", "run with MCP_VARIANT=hist"
    if RESULT.exists():
        raise SystemExit("results/schedule_features.json exists: the test is read once (PREREGISTRATION_V6_SCHEDULE.md section 6)")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW flights AS SELECT * FROM read_parquet('{F.FLIGHTS}')")
    fit_fl, fit_as, pred = (B.fit_window("C", c, *FIT) for c in ("flight_date", "obs_utc", "r.out_sched_dep"))
    F.create_stats(con, fit_flights=fit_fl, fit_asos=fit_as)
    con.execute(f"CREATE TABLE slots AS {slot_counts_sql('flights')}")
    con.execute(f"CREATE TABLE leg_hist AS {leg_history_sql('flights', fit_fl)}")
    frame = lambda s, p, f: con.execute(gap_label_sql(F.feature_sql(s, p, f, B.SEVERITY_FULL.as_posix(), with_keys=True))).fetchdf()
    src = f"read_parquet('{B.SOURCE_GLOB}')"
    (total,) = con.execute(f"SELECT count(*) FROM {src} r WHERE {pred}").fetchone()
    fit = attach(con, frame(src, pred, min(1.0, B.FIT_ROWS / total)))
    fit = fit.assign(y=fit["y_gap"])
    base_use = list(FEATURE_SETS["v1 set"])
    models = {"base": fit_gbm(fit, use=base_use, leaves=LEAVES), "base_seed1": fit_gbm(fit, use=base_use, leaves=LEAVES, seed=1),
              "all": fit_gbm(fit, use=base_use + list(FEATURES), leaves=LEAVES)}
    for f in FEATURES:
        models[f"only_{f}"] = fit_gbm(fit, use=base_use + [f], leaves=LEAVES)
    table = gsa_table()
    acc = {k: [0.0, 0.0, 0.0] for k in models}            # sum of w * loss, claims, expected
    wsum, n_rows, missing = 0.0, 0, {f: 0 for f in FEATURES}
    for y, m, lab in labels(*TEST):
        df = frame(f"read_parquet('{month_file(y, m)}')", month_predicate(y, m), FRAC)
        df = df[df["overnight"].notna() & df["fare"].notna() & (df["overnight"] == 1)].copy()
        df = attach(con, df)
        cost = claim_cost(df, table)
        w, yv = df["weight"].to_numpy(float), df["y_gap"].to_numpy(float)
        wsum += w.sum()
        n_rows += len(df)
        for f in FEATURES:
            missing[f] += int(df[f].isna().sum())
        for k, g in models.items():
            p = g(df)
            acc[k][0] += weighted_log_loss(yv, p, w) * w.sum()
            acc[k][1] += float((w * yv * cost).sum())
            acc[k][2] += float((w * p * cost).sum())
        print(f"  {lab}: {len(df):,} connections scored", flush=True)
    ll = {k: v[0] / wsum for k, v in acc.items()}
    res = {"status": "the schedule-structure test, read once", "fit": list(FIT), "test": list(TEST), "fit_rows": int(len(fit)), "test_rows": n_rows,
           "log_loss": ll, "gain": ll["base"] - ll["all"], "gain_pct": 100 * (ll["base"] - ll["all"]) / ll["base"], "seed_difference": abs(ll["base"] - ll["base_seed1"]),
           "gain_each_alone": {f: ll["base"] - ll[f"only_{f}"] for f in FEATURES}, "tie_band": TIE_BAND,
           "ratio": {k: v[1] / v[2] for k, v in acc.items() if k in ("base", "all")}, "missing_share_test": {f: missing[f] / n_rows for f in FEATURES}}
    RESULT.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return res


SEEDS_RESULT = ROOT / "results" / "schedule_features_seeds.json"


def seed_summary(log_loss: dict, n: int) -> dict:
    """From the log loss of `base_<s>` and `all_<s>` for seeds 0 to n - 1: the mean and standard deviation of each model, the paired gains
    (base minus all, same seed), their mean and standard deviation, and whether the mean gain exceeds twice the base model's spread."""
    base = np.array([log_loss[f"base_{s}"] for s in range(n)])
    allf = np.array([log_loss[f"all_{s}"] for s in range(n)])
    gains = base - allf
    sd = lambda x: float(x.std(ddof=1)) if len(x) > 1 else None
    return {"seeds": n, "base_mean": float(base.mean()), "base_sd": sd(base), "all_mean": float(allf.mean()), "all_sd": sd(allf),
            "paired_gains": [float(g) for g in gains], "mean_gain": float(gains.mean()), "gain_sd": sd(gains),
            "mean_gain_above_twice_base_sd": bool(gains.mean() > 2 * sd(base)) if sd(base) is not None else None,
            "gains_above_tie_band": int((gains > TIE_BAND).sum())}


def seeds(n: int = 5) -> dict:
    """The comparison of `read` repeated over `n` random seeds of the fit, on the same rows. Exploratory, after the read, and it does not
    regrade X1 (VALIDATION.md 7K). Writes results/schedule_features_seeds.json and refuses a second run."""
    from mcp.model import fit_gbm
    from mcp.v2 import FEATURE_SETS, LEAVES
    from mcp.v3 import claim_cost, gap_label_sql, gsa_table, labels, month_file, month_predicate
    from mcp.variant import VARIANT
    assert VARIANT == "hist", "run with MCP_VARIANT=hist"
    if SEEDS_RESULT.exists():
        raise SystemExit("results/schedule_features_seeds.json exists")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW flights AS SELECT * FROM read_parquet('{F.FLIGHTS}')")
    fit_fl, fit_as, pred = (B.fit_window("C", c, *FIT) for c in ("flight_date", "obs_utc", "r.out_sched_dep"))
    F.create_stats(con, fit_flights=fit_fl, fit_asos=fit_as)
    con.execute(f"CREATE TABLE slots AS {slot_counts_sql('flights')}")
    con.execute(f"CREATE TABLE leg_hist AS {leg_history_sql('flights', fit_fl)}")
    frame = lambda s, p, f: con.execute(gap_label_sql(F.feature_sql(s, p, f, B.SEVERITY_FULL.as_posix(), with_keys=True))).fetchdf()
    src = f"read_parquet('{B.SOURCE_GLOB}')"
    (total,) = con.execute(f"SELECT count(*) FROM {src} r WHERE {pred}").fetchone()
    fit = attach(con, frame(src, pred, min(1.0, B.FIT_ROWS / total)))
    fit = fit.assign(y=fit["y_gap"])
    base_use = list(FEATURE_SETS["v1 set"])
    models = {}
    for s in range(n):
        models[f"base_{s}"] = fit_gbm(fit, use=base_use, leaves=LEAVES, seed=s)
        models[f"all_{s}"] = fit_gbm(fit, use=base_use + list(FEATURES), leaves=LEAVES, seed=s)
    acc = {k: 0.0 for k in models}
    wsum = 0.0
    for y, m, lab in labels(*TEST):
        df = frame(f"read_parquet('{month_file(y, m)}')", month_predicate(y, m), FRAC)
        df = df[df["overnight"].notna() & df["fare"].notna() & (df["overnight"] == 1)].copy()
        df = attach(con, df)
        w, yv = df["weight"].to_numpy(float), df["y_gap"].to_numpy(float)
        wsum += w.sum()
        for k, g in models.items():
            acc[k] += weighted_log_loss(yv, g(df), w) * w.sum()
        print(f"  {lab}: {len(df):,} connections scored", flush=True)
    ll = {k: v / wsum for k, v in acc.items()}
    res = {"status": "exploratory replication of the schedule test over fit seeds, after the single read (VALIDATION.md 7K)", "log_loss": ll, **seed_summary(ll, n)}
    SEEDS_RESULT.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return res


if __name__ == "__main__":
    import sys
    seeds() if sys.argv[1:] == ["seeds"] else read()
