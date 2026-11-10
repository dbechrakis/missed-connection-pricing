"""v5.2: the v5 self-transfer cover with a fixed price loading, exactly as PREREGISTRATION_V5_2_LOADING.md fixes it.

    python -m mcp.v5_2 freeze      the table on January 2024 to August 2026 and the loading, models/v5_2_prices.json
    python -m mcp.v5_2 holdout     reads December 2026 to February 2027 once (refuses a second run)
"""
from __future__ import annotations

import argparse
import hashlib
import json

import numpy as np

from mcp import v5, v5_1
from mcp.ingest import ROOT

PRICES = ROOT / "models" / "v5_2_prices.json"
HOLDOUT_RESULT = ROOT / "results" / "v5_2_holdout.json"
LAMBDA = 1.16
FIT = ("2024-01", "2026-08")
WINDOW = ("2026-12", "2027-02")
REACH = (0.65, 0.85)


def freeze() -> str:
    k = json.loads(v5.TABLE.read_text())["k"]
    df, counts = v5.frame(v5.T_MIN, *FIT)
    table = {**v5.fit_table(df, k), "fitted_on": list(FIT), "counts": counts}
    PRICES.write_text(json.dumps({"lambda": LAMBDA, "k": k, "table": table}, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return hashlib.sha256(PRICES.read_bytes()).hexdigest()


def holdout() -> dict:
    """The single read of December 2026 to February 2027, loaded and unloaded on the same pairings."""
    if HOLDOUT_RESULT.exists():
        raise SystemExit(f"{HOLDOUT_RESULT.name} exists: the window has been read. It is read once.")
    frozen = json.loads(PRICES.read_text())
    df, counts = v5.frame(v5.T_MIN, *WINDOW)
    df = df.reset_index(drop=True)
    base = v5.score(df, frozen["table"])
    loaded = np.minimum(frozen["lambda"] * base, v5_1.P_MAX)
    r_loaded, r_base = v5.realized_over_target(df, loaded), v5.realized_over_target(df, base)
    monthly = {ym: v5.realized_over_target(g, loaded[g.index.to_numpy()]) for ym, g in df.groupby("ym")}
    share = loaded * df["payout"].to_numpy() / v5.TARGET_LR / df["fare_total"].to_numpy()
    reach = {ym: float(np.nanmean(share[g.index.to_numpy()] <= v5.CAP)) for ym, g in df.groupby("ym")}
    misses = df["missed"].sum()
    cancel = float(df["missed_by_cancellation"].sum() / misses) if misses else float("nan")
    lo, hi = v5.week_bootstrap(df, loaded)
    grades = {"W1": 0.85 <= r_loaded <= 1.15, "W2": abs(r_loaded - 1) < abs(r_base - 1), "W3": max(monthly.values()) <= 1.54,
              "W4": all(REACH[0] <= v <= REACH[1] for v in reach.values()), "W5": 0.20 <= cancel <= 0.50}
    out = {"prices_sha256": hashlib.sha256(PRICES.read_bytes()).hexdigest(), "counts": counts,
           "loaded": {"realized_over_target": r_loaded, "interval_95": [lo, hi], "monthly": monthly, "share_within_cap": reach},
           "unloaded": {"realized_over_target": r_base}, "share_of_misses_by_cancellation_or_diversion": cancel, "grades": grades}
    HOLDOUT_RESULT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["freeze", "holdout"])
    a = p.parse_args(argv)
    if a.step == "freeze":
        print("models/v5_2_prices.json sha256", freeze())
    else:
        print(json.dumps(holdout()["grades"], indent=1))


if __name__ == "__main__":
    main()
