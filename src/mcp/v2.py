"""v2: choose a feature set and a calibration policy by walk-forward on 2025, then fit the final v2.

Design and the selection rule were committed before this ran (VALIDATION.md Part 3A). This module
never touches 2026: its file globs are limited to the 2024 and 2025 folders, and a test checks it.

    python -m mcp.v2 select     # walk-forward selection experiment on 2025
    python -m mcp.v2 fit        # fit the final v2 GBM and the static calibrator inputs
"""
from __future__ import annotations

import json
import sys

import duckdb
import joblib
import numpy as np
import pandas as pd

from mcp import features as F
from mcp.calibration import MonthStats, POLICIES, make_calibrator, month_stats
from mcp.connections import ROOT, WEIGHTED
from mcp.model import EPS, fit_gbm, _codes
from mcp.pricing import SEVERITY, load_config
from mcp.split import where

# 2024 and 2025 only. The 2026 files, when they exist, are never matched by this pattern.
DEV_GLOB = (WEIGHTED / "mct=45" / "year=202[45]" / "*.parquet").as_posix()
RESULTS = ROOT / "results" / "v2_selection.json"
BUNDLE = ROOT / "models" / "pmiss_v2.joblib"
LEAVES = 15                          # the size chosen for v1 on its validation window; not re-tuned
SEL_ROWS = 5_000_000                 # GBM training rows
EVAL_FRAC = 0.10                     # constant hash-sample fraction of every evaluation month

V1_SET = F.CATEGORICAL + ["slack_min", "out_hour", "out_dow", "in_arr_hour"] + F.ROUTE_HISTORY
FEATURE_SETS = {"v1 set": V1_SET, "v1 set + month": V1_SET + ["month"]}
CANDIDATES = ([("none", 0)] + [("level_global", k) for k in (1, 2, 3, 6)] +
              [("level_hub", k) for k in (1, 3, 6)] + [("iso_global", k) for k in (3, 6)])
SIMPLICITY = {name: i for i, name in enumerate(POLICIES)}
TOLERANCE = 0.0002                   # log-loss gap under which two candidates are treated as tied


def month_bounds(y: int, m: int) -> tuple[str, str]:
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y}-{m:02d}-01", f"{ny}-{nm:02d}-01"


def month_predicate(y: int, m: int) -> str:
    lo, hi = month_bounds(y, m)
    return f"(r.out_sched_dep >= TIMESTAMP '{lo}' AND r.out_sched_dep < TIMESTAMP '{hi}')"


def month_file(y: int, m: int) -> str:
    return (WEIGHTED / "mct=45" / f"year={y}" / f"month={m:02d}.parquet").as_posix()


def pick(rows: list[dict]) -> dict:
    """The pre-declared rule: lowest pooled log loss; within TOLERANCE of the best, prefer the
    simpler policy, then the longer window."""
    best = min(r["log_loss"] for r in rows)
    tied = [r for r in rows if r["log_loss"] <= best + TOLERANCE]
    return min(tied, key=lambda r: (SIMPLICITY[r["policy"]], -r["k"], r["log_loss"]))


def walk_forward(months: dict, stats: list[MonthStats], cfg: dict, eval_months: list[str]) -> list[dict]:
    """Price each evaluation month with calibrators built from earlier months only; pool the results."""
    out = []
    c_cost = lambda df: cfg["rebooking_cost"] + cfg["overnight_cost"] * df["overnight"].to_numpy()
    for policy, k in CANDIDATES:
        w_tot = brier = ll = claim = expect = 0.0
        by_hub: dict = {}
        for mo in eval_months:
            df = months[mo]
            known = [s for s in stats if s.month < mo]               # strictly earlier months
            p = make_calibrator(policy, k, known)(df["p"].to_numpy(), df["hub"].to_numpy())
            y, w, c = df["y"].to_numpy(), df["weight"].to_numpy(), c_cost(df)
            pc = np.clip(p, EPS, 1 - EPS)
            w_tot += w.sum()
            brier += float(np.sum(w * (y - p) ** 2))
            ll += float(-np.sum(w * (y * np.log(pc) + (1 - y) * np.log(1 - pc))))
            claim += float(np.sum(w * y * c))
            expect += float(np.sum(w * p * c))
            for h in np.unique(df["hub"]):
                mask = (df["hub"] == h).to_numpy()
                a = by_hub.get(h, [0.0, 0.0])
                by_hub[h] = [a[0] + float(np.sum(w[mask] * y[mask] * c[mask])), a[1] + float(np.sum(w[mask] * p[mask] * c[mask]))]
        out.append({"policy": policy, "k": k, "log_loss": ll / w_tot, "brier": brier / w_tot,
                    "realized_over_target": claim / expect,
                    "by_hub": {h: v[0] / v[1] for h, v in by_hub.items()}})
    return out


def run_selection() -> dict:
    cfg = load_config()
    con = duckdb.connect()
    F.create_stats(con, fit_flights=where("S_FIT", "flight_date"), fit_asos=where("S_FIT", "obs_utc"))
    src = f"read_parquet('{DEV_GLOB}')"
    (total,) = con.execute(f"SELECT count(*) FROM {src} WHERE {where('S_FIT')}").fetchone()
    fit = con.execute(F.feature_sql(src, where("S_FIT", "r.out_sched_dep"), min(1.0, SEL_ROWS / total))).fetchdf()
    print(f"S_FIT: {len(fit):,} rows", flush=True)

    months, eval_months = {}, [f"2025-{m:02d}" for m in range(7, 13)]
    for m in range(4, 13):
        df = con.execute(F.feature_sql(f"read_parquet('{month_file(2025, m)}')", month_predicate(2025, m),
                                       EVAL_FRAC, SEVERITY.as_posix())).fetchdf()
        months[f"2025-{m:02d}"] = df
    print("scored months:", {k: len(v) for k, v in months.items()}, flush=True)

    result = {"candidates": {}, "chosen": None}
    best_overall = []
    for name, use in FEATURE_SETS.items():
        print(f"fitting GBM: {name} ...", flush=True)
        g = fit_gbm(fit, use=use, leaves=LEAVES)
        for mo, df in months.items():
            df["p"] = g(df)
        stats = [month_stats(mo, df["hub"], df["y"], df["weight"], df["p"]) for mo, df in months.items()]
        rows = walk_forward(months, stats, cfg, eval_months)
        for r in rows:
            r["features"] = name
        result["candidates"][name] = rows
        best_overall += rows
    chosen = pick(best_overall)
    result["chosen"] = chosen
    RESULTS.write_text(json.dumps(result, indent=2))
    print("\nwalk-forward Jul-Dec 2025 (lower log loss is better)")
    for r in sorted(best_overall, key=lambda r: r["log_loss"]):
        mark = "  <- chosen" if r is chosen else ""
        print(f"  {r['features']:15s} {r['policy']:13s} k={r['k']}  logloss {r['log_loss']:.5f}  brier {r['brier']:.5f}"
              f"  realized/target {r['realized_over_target']:.3f}{mark}")
    return result


def fit_final(chosen: dict) -> None:
    """v2: GBM on V2_FIT with the chosen features; month statistics for V2_CAL (Oct-Dec 2025),
    which are out-of-sample for this GBM, are what the static calibrator is built from."""
    con = duckdb.connect()
    F.create_stats(con, fit_flights=where("V2_FIT", "flight_date"), fit_asos=where("V2_FIT", "obs_utc"))
    src = f"read_parquet('{DEV_GLOB}')"
    (total,) = con.execute(f"SELECT count(*) FROM {src} WHERE {where('V2_FIT')}").fetchone()
    fit = con.execute(F.feature_sql(src, where("V2_FIT", "r.out_sched_dep"), min(1.0, SEL_ROWS / total))).fetchdf()
    use = FEATURE_SETS[chosen["features"]]
    print(f"V2_FIT: {len(fit):,} rows; fitting {chosen['features']} ...", flush=True)
    g = fit_gbm(fit, use=use, leaves=LEAVES)
    cal = []
    for m in (10, 11, 12):
        df = con.execute(F.feature_sql(f"read_parquet('{month_file(2025, m)}')", month_predicate(2025, m),
                                       EVAL_FRAC, SEVERITY.as_posix())).fetchdf()
        cal.append(month_stats(f"2025-{m:02d}", df["hub"], df["y"], df["weight"], g(df)))
    joblib.dump({"gbm": g.model, "cats": g.cats, "features": g.use, "policy": chosen["policy"], "k": chosen["k"],
                 "feature_set": chosen["features"], "cal_stats": cal, "leaves": LEAVES}, BUNDLE)
    print("saved", BUNDLE)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "select"
    if mode == "select":
        run_selection()
    elif mode == "fit":
        fit_final(json.loads(RESULTS.read_text())["chosen"])
