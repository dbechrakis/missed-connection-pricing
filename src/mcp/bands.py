"""Size the monthly job's alert bands from data BEFORE 2026 (VALIDATION.md 4J).

The first version of the monitor used bands chosen by hand (+-10% overall, +-20% per hub). A dry run showed they
fire most months, because a month's realized level moves by more than that around what was expected. The principled
fix is to size a band from the measured spread and average over several months so one noisy month cannot fire it:

    flag when the rolling k-month ratio is outside 1 +- z x sigma / sqrt(k)

sigma is the standard deviation of the monthly realized / expected ratio, measured here on the walk-forward of the
2025 selection experiment: the GBM fitted through March 2025, each month July to December 2025 priced from earlier
months only (the policy v2 chose: isotonic over six months). That is 6 monthly ratios overall and 30 hub-months.
The 2026 months play no part. (The author had already seen the 2026 spread, about 0.15, so this cannot be called
blind; it is checked against 2026 afterwards and the check is labelled as contaminated.)

Run:  python -m mcp.bands     (from src/; a few minutes; writes config/monitoring.yaml and results/monitoring_bands.json)
"""
from __future__ import annotations

import json

import duckdb
import numpy as np
import yaml

from mcp import features as F
from mcp.calibration import make_calibrator, month_stats
from mcp.connections import ROOT
from mcp.model import fit_gbm
from mcp.monitor import band
from mcp.pricing import SEVERITY, load_config
from mcp.split import where
from mcp.v2 import DEV_GLOB, EVAL_FRAC, FEATURE_SETS, LEAVES, SEL_ROWS, month_file, month_predicate

CONFIG = ROOT / "config" / "monitoring.yaml"
RESULTS = ROOT / "results" / "monitoring_bands.json"
Z, K = 2.0, 3                       # two standard errors, a three-month window
POLICY, POLICY_K = "iso_global", 6  # the calibration policy v2 chose (results/v2_selection.json)
LF = chr(10)                        # write the hashed config with Unix line endings on every system


def main() -> None:
    cfg = load_config()
    con = duckdb.connect()
    F.create_stats(con, fit_flights=where("S_FIT", "flight_date"), fit_asos=where("S_FIT", "obs_utc"))
    src = f"read_parquet('{DEV_GLOB}')"
    (total,) = con.execute(f"SELECT count(*) FROM {src} WHERE {where('S_FIT')}").fetchone()
    fit = con.execute(F.feature_sql(src, where("S_FIT", "r.out_sched_dep"), min(1.0, SEL_ROWS / total))).fetchdf()
    use = FEATURE_SETS["v1 set + month"]
    g = fit_gbm(fit, use=use, leaves=LEAVES)
    months, stats = {}, []
    for m in range(4, 13):
        label = f"2025-{m:02d}"
        df = con.execute(F.feature_sql(f"read_parquet('{month_file(2025, m)}')", month_predicate(2025, m), EVAL_FRAC, SEVERITY.as_posix())).fetchdf()
        df["p_raw"] = g(df)
        months[label] = df
        stats.append(month_stats(label, df["hub"], df["y"], df["weight"], df["p_raw"]))
    overall, per_hub = [], {}
    for label in (f"2025-{m:02d}" for m in range(7, 13)):
        df = months[label]
        cal = make_calibrator(POLICY, POLICY_K, [s for s in stats if s.month < label])
        p = cal(df["p_raw"].to_numpy(), df["hub"].to_numpy())
        c = cfg["rebooking_cost"] + cfg["overnight_cost"] * df["overnight"].to_numpy()
        w, y = df["weight"].to_numpy(), df["y"].to_numpy()
        overall.append(float(np.sum(w * y * c) / np.sum(w * p * c)))
        for h in np.unique(df["hub"]):
            m = (df["hub"] == h).to_numpy()
            per_hub.setdefault(h, []).append(float(np.sum((w * y * c)[m]) / np.sum((w * p * c)[m])))
    sigma_overall = float(np.std(overall, ddof=1))
    hub_months = np.concatenate([np.array(v) for v in per_hub.values()])
    sigma_hub = float(np.std(hub_months, ddof=1))
    out = {"derived_from": "walk-forward Jul-Dec 2025 (GBM fitted through Mar 2025; each month priced from earlier months only)",
           "monthly_ratios_overall": overall, "hub_month_ratios": per_hub, "n_months": len(overall), "n_hub_months": int(hub_months.size),
           "sigma_overall": sigma_overall, "sigma_hub": sigma_hub, "z": Z, "window_months": K,
           "band_overall": band(sigma_overall, K, Z), "band_hub": band(sigma_hub, K, Z)}
    RESULTS.write_text(json.dumps(out, indent=2))
    CONFIG.write_text(yaml.safe_dump({"monitoring": {
        "window_months": K, "z": Z, "sigma_overall": round(sigma_overall, 4), "sigma_hub": round(sigma_hub, 4),
        "derived_from": out["derived_from"],
        "note": "Alert when the rolling window_months ratio of realized to expected claims is outside 1 +- z x sigma / sqrt(window_months). "
                "Sigma is the sd of the monthly (overall) or hub-month ratio on 2025 data; 2026 plays no part in the derivation."}}, sort_keys=False), encoding="utf-8", newline=LF)   # Unix endings: this file is hashed
    print(f"monthly ratios Jul-Dec 2025: {np.round(overall, 3).tolist()}  sd {sigma_overall:.3f}  -> band +-{band(sigma_overall, K, Z):.3f}")
    print(f"hub-month ratios ({hub_months.size}): sd {sigma_hub:.3f}  -> band +-{band(sigma_hub, K, Z):.3f}")


if __name__ == "__main__":
    main()
