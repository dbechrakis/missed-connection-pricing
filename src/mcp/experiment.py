"""Sample-size and duration maths for the pricing experiment (docs/product-brief.md).

The data cannot say how many travellers buy protection, how much they will pay, or how strongly the
riskiest connections self-select. An experiment can. This module sizes it using the quantities we *did*
measure, and leaves every unmeasured quantity as an explicit input.

  n_two_prop        travellers per arm to detect a change in attach rate (two-proportion z-test)
  n_slope           travellers needed to estimate how purchase rises with risk (the selection strength theta)
  weeks_for_ratio   weeks of live data before the realized-over-target loss ratio is known to +-h

Run:  python -m mcp.experiment      (from src/)   writes results/experiment_design.json
"""
from __future__ import annotations

import json
from statistics import NormalDist

import numpy as np

from mcp.connections import ROOT

RESULTS = ROOT / "results" / "experiment_design.json"


def z(p: float) -> float:
    return NormalDist().inv_cdf(p)


def n_two_prop(p0: float, rel_lift: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """Travellers per arm to detect attach rate p0 -> p0 x (1 + rel_lift), two-sided."""
    p1 = p0 * (1 + rel_lift)
    pbar = (p0 + p1) / 2
    num = (z(1 - alpha / 2) * np.sqrt(2 * pbar * (1 - pbar)) + z(power) * np.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) ** 2
    return int(np.ceil(num / (p1 - p0) ** 2))


def n_slope(sd_x: float, attach: float, effect: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """Travellers to estimate the slope of log(purchase odds) on log(risk) to within `effect`
    (e.g. distinguish theta = 0 from theta = effect). Logistic regression, low attach rate:
    var(slope) ~ 1 / (n x attach x (1-attach) x sd_x^2)."""
    return int(np.ceil(((z(1 - alpha / 2) + z(power)) / effect) ** 2 / (sd_x**2 * attach * (1 - attach))))


def weeks_for_ratio(cv_week: float, half_width: float, level: float = 0.95) -> int:
    """Weeks of data so the 95% interval of realized/target is +-half_width, if weekly ratios are
    independent with coefficient of variation cv_week. Policies per week do not appear: weather and
    operations hit every passenger in a week at once, so more volume does not shorten this."""
    return int(np.ceil((z(1 - (1 - level) / 2) * cv_week / half_width) ** 2))


def weeks_for_ratio_at_volume(cv_week: float, cv_claim: float, policies_per_week: float, half_width: float,
                              level: float = 0.95) -> int:
    """As weeks_for_ratio, but with the extra noise of a small book: each week's loss ratio also moves
    with how many policies were sold, because one policy's claim cost has a coefficient of variation
    `cv_claim` (about 4: most pay nothing, a few pay a lot). Variances add:
    cv_total^2 = cv_week^2 + cv_claim^2 / policies_per_week."""
    cv_total = float(np.sqrt(cv_week**2 + cv_claim**2 / policies_per_week))
    return weeks_for_ratio(cv_total, half_width, level)


def pause_threshold(cv_week: float, cv_claim: float, policies_per_week: float, sigmas: float = 2.0) -> float:
    """Weekly claims, as a multiple of expected, above which to flag a week: expected x (1 + sigmas x cv_total).
    The same noise model as weeks_for_ratio_at_volume: a small book is noisier, so its threshold must be higher
    or it would pause on ordinary weeks."""
    return float(1 + sigmas * np.sqrt(cv_week**2 + cv_claim**2 / policies_per_week))


def derived_inputs() -> dict:
    """Quantities taken from our own results, not assumed."""
    import joblib
    import pandas as pd

    from mcp.features import OUT
    from mcp.pricing import MODEL, load_config, load_guards, score

    cfg = load_config()
    df = pd.read_parquet(OUT / "PRICING_TRAIN.parquet")
    p = np.maximum(score(df, joblib.load(MODEL)), load_guards()["min_p_miss"])   # the product never prices below the floor
    w = df["weight"].to_numpy()
    lp = np.log(p)
    mean_lp = np.average(lp, weights=w)
    sd_log_p = float(np.sqrt(np.average((lp - mean_lp) ** 2, weights=w)))
    c = cfg["rebooking_cost"] + cfg["overnight_cost"] * df["overnight"].to_numpy()
    claim = df["y"].to_numpy() * c
    mu = np.average(claim, weights=w)
    cv_claim = float(np.sqrt(np.average((claim - mu) ** 2, weights=w)) / mu)
    # weekly variability of the realized/target ratio, read back from the published holdout interval:
    # half-width ~ 1.96 x cv / sqrt(weeks)  =>  cv ~ (hi - lo) / (2 x 1.96) x sqrt(weeks)
    h = json.loads((ROOT / "results" / "holdout.json").read_text())
    r = h["overall"]["v2_rolling"]["0"]
    cv_week = float((r["hi"] - r["lo"]) / (2 * 1.96) * np.sqrt(h["weeks"]) / r["ratio"])
    return {"sd_log_p": sd_log_p, "cv_claim_per_policy": cv_claim, "cv_week_ratio": cv_week,
            "mean_p": float(np.average(p, weights=w)), "weeks_in_holdout": int(h["weeks"])}


def design(inputs: dict) -> dict:
    attach = [0.01, 0.02, 0.05, 0.10]
    lifts = [0.10, 0.20, 0.30]
    out = {"inputs": inputs, "two_prop_per_arm": {f"{a:.0%}": {f"{l:.0%}": n_two_prop(a, l) for l in lifts} for a in attach}}
    out["theta_travellers"] = {f"{a:.0%}": {f"theta_diff={e}": n_slope(inputs["sd_log_p"], a, e) for e in (0.25, 0.5, 1.0)}
                               for a in attach}
    out["weeks_for_ratio"] = {f"+-{h:.0%}": weeks_for_ratio(inputs["cv_week_ratio"], h) for h in (0.05, 0.10, 0.15, 0.20)}
    out["weeks_for_ratio_by_volume"] = {
        f"{n:,} policies/week": {f"+-{h:.0%}": weeks_for_ratio_at_volume(inputs["cv_week_ratio"], inputs["cv_claim_per_policy"], n, h)
                                 for h in (0.10, 0.20)} for n in (100, 1_000, 10_000, 100_000)}
    out["pause_threshold_multiple"] = {
        f"{n:,} policies/week": round(pause_threshold(inputs["cv_week_ratio"], inputs["cv_claim_per_policy"], n), 2)
        for n in (100, 1_000, 10_000, 100_000)}
    return out


if __name__ == "__main__":
    d = design(derived_inputs())
    RESULTS.write_text(json.dumps(d, indent=2))
    print(json.dumps(d, indent=1))
