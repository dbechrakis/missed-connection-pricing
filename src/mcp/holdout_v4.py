"""The pre-registered test of v4, the loaded gap cover, on September to December 2026 (PREREGISTRATION_2026H2_V4.md).
Run with MCP_VARIANT=v3 (the population and the frozen model are v3's), only after the v3 test has been read:

    MCP_VARIANT=v3 python -m mcp.holdout_v4 9 10 11        # the months published at the time of the first read

v4 is not a new model. It is the frozen v3 gap model (models/pmiss_v3.joblib, no recalibration) with one number added to the
price, a loading of the premium (models/v4_loading.json), because the cover as sold ran above its target loss ratio in
development: the cap lets through the connections the model under-prices. The loading is fitted on development months only.

Each connection is priced twice, at the v3 price (loading 1) and at the v4 price (the frozen loading); both are judged on the
connections that pass the 5% cap at their own price, over the same months. Nothing is refitted.
"""
from __future__ import annotations

import json
import sys

import duckdb
import joblib
import numpy as np
import pandas as pd

from mcp import features as F
from mcp.connections import ROOT
from mcp.model import _codes
from mcp.split import where
from mcp.v3 import BUNDLE, claim_cost, frame_sql, gsa_table, month_file
from mcp.v3_loading import FROZEN, measure, weekly_loss_ratio
from mcp.variant import MARKETING

RESULTS = ROOT / "results" / "holdout_v4_next.json"
SENSITIVITY = (1.0, 1.10, 1.16, 1.21, 1.30)


def month_rows(con, bundle: dict, table: dict, year: int, month: int, label: str, predicate: str) -> pd.DataFrame:
    df = con.execute(frame_sql(f"read_parquet('{month_file(year, month)}')", predicate, 1.0)).fetchdf()
    df = df[df["overnight"].notna() & df["fare"].notna()]
    df = df[df["overnight"] == 1].copy()
    df["p"] = bundle["gbm_gap"].predict_proba(_codes(df[bundle["features"]], bundle["cats"]))[:, 1]
    df["claim_cost"] = claim_cost(df, table)
    day = df["out_sched_dep"].dt.normalize()
    df["week"] = (day - pd.to_timedelta(df["out_sched_dep"].dt.day_of_week, unit="D")).astype(str)
    df["ym"] = label
    return df[["ym", "week", "hub", "fare", "weight", "y_gap", "claim_cost", "p"]]


def summarise(months: dict, lam: float, sensitivity=SENSITIVITY) -> dict:
    """The v3 price (loading 1) and the v4 price (`lam`) on the same months: loss ratio, share sold, the paired difference, weeks."""
    labs = sorted(months)
    v3 = {m: measure(months[m], 1.0) for m in labs}
    v4 = {m: measure(months[m], lam) for m in labs}
    pool = lambda d: sum(d[m]["claims"] for m in labs) / sum(d[m]["premium"] for m in labs)
    allrows = pd.concat(months.values(), ignore_index=True)
    w3, w4 = weekly_loss_ratio(allrows, 1.0), weekly_loss_ratio(allrows, lam)
    return {"months": labs, "lambda": lam,
            "pooled_loss_ratio": {"v3": pool(v3), "v4": pool(v4)},
            "improvement_points": 100 * (pool(v3) - pool(v4)),
            "v4_below_v3_in_every_month": bool(all(v4[m]["loss_ratio"] < v3[m]["loss_ratio"] for m in labs)),
            "monthly": {m: {"v3_loss_ratio": v3[m]["loss_ratio"], "v4_loss_ratio": v4[m]["loss_ratio"], "v3_share_sold": v3[m]["share_sold"], "v4_share_sold": v4[m]["share_sold"]} for m in labs},
            "weeks": int(len(w4)), "weeks_above_100": {"v3": int((w3 > 1).sum()), "v4": int((w4 > 1).sum())},
            "worst_week": {"v3": float(w3.max()), "v4": float(w4.max())},
            "sensitivity": {f"{s:.2f}": {"loss_ratio": measure(allrows, s)["loss_ratio"], "share_sold": measure(allrows, s)["share_sold"]} for s in sensitivity}}


def run(months=(9, 10, 11), year: int = 2026, predicate: str | None = None) -> dict:
    assert MARKETING, "run with MCP_VARIANT=v3"
    bundle, table = joblib.load(BUNDLE), gsa_table()
    lam = float(json.loads(FROZEN.read_text(encoding="utf-8"))["lambda"])
    con = duckdb.connect()
    F.create_stats(con, fit_flights=where("V3_FIT", "flight_date"), fit_asos=where("V3_FIT", "obs_utc"))
    # The single place the v4 test reads the NEXT window:
    predicate = predicate or where("NEXT", "r.out_sched_dep")
    rows = {}
    for m in months:
        label = f"{year}-{m:02d}"
        rows[label] = month_rows(con, bundle, table, year, m, label, predicate)
        print(f"{label}: {len(rows[label]):,} overnight-risk connections scored", flush=True)
    return summarise(rows, lam)


def main(months: tuple) -> None:
    res = run(months)
    RESULTS.write_text(json.dumps(res, indent=2, default=float))
    p = res["pooled_loss_ratio"]
    print(f"sold loss ratio: v3 price {p['v3']:.1%}, v4 price {p['v4']:.1%} ({res['improvement_points']:+.1f} points); "
          f"weeks above 100%: {res['weeks_above_100']['v3']} -> {res['weeks_above_100']['v4']} of {res['weeks']}")


if __name__ == "__main__":
    main(tuple(int(x) for x in sys.argv[1:]) or (9, 10, 11))
