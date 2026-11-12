"""The pre-registered test of v3, the overnight gap cover (PREREGISTRATION_2026H2_V3.md), on September to
December 2026. Run with MCP_VARIANT=v3, only after the original pre-registered evaluation has been read:

    MCP_VARIANT=v3 python -m mcp.holdout_v3 9 10 11        # the months published at the time of the first read

Two calibration policies, both declared before the data existed:
  primary    the policy the selection rule chose (models/pmiss_v3.joblib: 'none'), the headline
  hub_level  per-hub level over the last 6 known months: the rule's tie-break dropped it, but it was within the rule's
             own tolerance and it fixed the hub spread on development data, so it is tested as a declared second arm
Both price month m from months known one month before it (booking lag), starting from the saved state through
August 2026 (models/v3_state.json); each new month becomes known only after it has been scored.
"""
from __future__ import annotations

import json
import sys

import duckdb
import joblib
import numpy as np
import pandas as pd

from mcp import features as F
from mcp.backtest import ratio_with_ci
from mcp.calibration import known_months, make_calibrator, month_stats
from mcp.connections import ROOT
from mcp.model import EPS, _codes
from mcp.monitor import load_state
from mcp.split import where
from mcp.v3 import BUNDLE, LAG, STATE, WTP_CAPS, claim_cost, frame_sql, gsa_table, month_file, price
from mcp.variant import MARKETING, VARIANT

RESULTS = ROOT / "results" / "holdout_v3_next.json"
HUBS = ("ATL", "CLT", "DEN", "DFW", "ORD")


def arms(bundle: dict) -> dict:
    return {"primary": (bundle["policy"], bundle["k"]), "hub_level": ("level_hub", 6)}


def summarise(df: pd.DataFrame, arm: str) -> dict:
    """Realized / target = actual payouts over the payouts the price assumed (claims / expected claims, cost-weighted),
    with a 95% interval from resampling whole weeks; the same overall and per hub. 1.0 = priced on target."""
    sums = pd.DataFrame({"week": df["week"], "hub": df["hub"],
                         "claims": df["weight"] * df["y_gap"] * df["claim_cost"],
                         "expected": df["weight"] * df[f"p_{arm}"] * df["claim_cost"]})
    weeks = sorted(sums["week"].unique())
    y, w, p = df["y_gap"].to_numpy(), df["weight"].to_numpy(), np.clip(df[f"p_{arm}"].to_numpy(), EPS, 1 - EPS)
    ov = df["claim_cost"].to_numpy() > 0                                      # the cover only exists where a miss means a night
    prem = price(df[f"p_{arm}"], df["claim_cost"])
    offered = {}
    for cap in WTP_CAPS:
        mk = ov & (prem <= cap * df["fare"].to_numpy())
        offered[f"{cap:.2f}"] = {"share_of_overnight_offered": float(w[mk].sum() / w[ov].sum()),
                                 "realized_over_target": ratio_with_ci(sums[mk], "claims", "expected", weeks=weeks)}
    return {"overall": ratio_with_ci(sums, "claims", "expected", weeks=weeks),
            "monthly": {mo: float(g["claims"].sum() / g["expected"].sum()) for mo, g in sums.groupby(df["month"])},
            "offered_within_cap": offered,
            "mean_price_overnight": float(np.average(prem[ov], weights=w[ov])),
            "by_hub": {h: ratio_with_ci(sums[sums["hub"] == h], "claims", "expected", weeks=weeks) for h in HUBS},
            "log_loss": float(-np.sum(w * (y * np.log(p) + (1 - y) * np.log(1 - p))) / w.sum()),
            "mean_pred": float(np.average(p, weights=w)), "observed_rate": float(np.average(y, weights=w))}


def run(months=(9, 10, 11, 12), year: int = 2026, predicate: str | None = None) -> dict:
    assert VARIANT == "v3", "run with MCP_VARIANT=v3"
    bundle, table = joblib.load(BUNDLE), gsa_table()
    policies = arms(bundle)
    con = duckdb.connect()
    F.create_stats(con, fit_flights=where("V3_FIT", "flight_date"), fit_asos=where("V3_FIT", "obs_utc"))
    # The single place the v3 test reads the NEXT window:
    predicate = predicate or where("NEXT", "r.out_sched_dep")
    known, parts, dropped = list(load_state(STATE)), [], 0
    for m in months:
        label = f"{year}-{m:02d}"
        df = con.execute(frame_sql(f"read_parquet('{month_file(year, m)}')", predicate, 1.0)).fetchdf()
        bad = df["overnight"].isna() | df["fare"].isna()
        dropped += int(bad.sum())
        df = df[~bad].copy()
        df["p_raw"] = bundle["gbm_gap"].predict_proba(_codes(df[bundle["features"]], bundle["cats"]))[:, 1]
        hubs = df["hub"].to_numpy()
        for arm, (policy, k) in policies.items():
            df[f"p_{arm}"] = make_calibrator(policy, k, known_months(known, label, LAG))(df["p_raw"].to_numpy(), hubs)
        df["claim_cost"] = claim_cost(df, table)
        day = df["out_sched_dep"].dt.normalize()
        df["week"] = (day - pd.to_timedelta(df["out_sched_dep"].dt.day_of_week, unit="D")).astype(str)
        df["month"] = label
        # only now does this month's outcome become known, for later months
        known.append(month_stats(label, df["hub"], df["y_gap"], df["weight"], df["p_raw"]))
        parts.append(df[["week", "month", "hub", "weight", "fare", "y", "y_gap", "claim_cost", *(f"p_{a}" for a in policies)]])
        print(f"{label}: {len(df):,} connections scored (dropped {int(bad.sum())})", flush=True)
    df = pd.concat(parts, ignore_index=True)
    ov = df["claim_cost"] > 0
    # the product's premise: most overnight misses are ones the airline does not pay for
    gap_share = float((df["weight"] * df["y_gap"])[ov].sum() / (df["weight"] * df["y"])[ov].sum())
    return {"months_evaluated": [f"{year}-{m:02d}" for m in months], "gap_share_of_overnight_misses": gap_share,
            "arms": {a: {"policy": p, "k": k} for a, (p, k) in policies.items()}, "lag": LAG,
            "rows": {"scored": len(df), "dropped_missing_severity_or_fare": dropped},
            "results": {a: summarise(df, a) for a in policies}}


def main(months: tuple) -> None:
    res = run(months)
    RESULTS.write_text(json.dumps(res, indent=2, default=float))
    for arm, r in res["results"].items():
        o = r["overall"]
        hubs = "  ".join(f"{h} {v['ratio']:.2f}" for h, v in r["by_hub"].items())
        print(f"{arm:10s} realized/target {o['ratio']:.3f} [{o['lo']:.3f}, {o['hi']:.3f}]   {hubs}")


if __name__ == "__main__":
    main(tuple(int(x) for x in sys.argv[1:]) or (9, 10, 11, 12))
