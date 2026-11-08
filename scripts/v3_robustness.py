"""v3 robustness (development data only, Oct 2025 to Aug 2026): does training on overnight rows, a month term, or any
recalibration fix the monthly swings of the gap cover? Monthly cost-weighted realized/target with a one-month lag.
Exploratory, run after the selection; it did not change the chosen model (VALIDATION.md Part 5).

    cd src && MCP_VARIANT=v3 PYTHONPATH=. python ../scripts/v3_robustness.py
"""
import json

import duckdb
import numpy as np

from mcp import features as F
from mcp.calibration import known_months, make_calibrator, month_stats
from mcp.connections import ROOT
from mcp.model import fit_gbm
from mcp.split import where
from mcp.v2 import FEATURE_SETS, LEAVES
from mcp.v3 import DEV_GLOB, SEL_ROWS, _score_months, frame_sql, gsa_table, labels

table = gsa_table()
con = duckdb.connect()
F.create_stats(con, fit_flights=where("V3_SFIT", "flight_date"), fit_asos=where("V3_SFIT", "obs_utc"))
src = f"read_parquet('{DEV_GLOB}')"
(total,) = con.execute(f"SELECT count(*) FROM {src} WHERE {where('V3_SFIT')}").fetchone()
fit = con.execute(frame_sql(src, where("V3_SFIT", "r.out_sched_dep"), min(1.0, 3 * SEL_ROWS / total))).fetchdf()
fit = fit[fit["overnight"].notna() & fit["fare"].notna()]
print(f"fit rows {len(fit):,}, overnight share {np.average(fit['overnight'], weights=fit['weight']):.3f}", flush=True)
ev = [lab for _, _, lab in labels("2025-10", "2026-08")]
out = {}
for pop in ("all", "overnight"):
    f = fit if pop == "all" else fit[fit["overnight"] == 1]
    f = f.sample(n=min(len(f), SEL_ROWS), random_state=0)
    for name, use in FEATURE_SETS.items():
        g = fit_gbm(f.assign(y=f["y_gap"]), use=use, leaves=LEAVES)
        months = _score_months(con, g, "2025-07", "2026-08", table)
        months = {k: d[d["overnight"] == 1] for k, d in months.items()}
        stats = [month_stats(k, d["hub"], d["y_gap"], d["weight"] * d["claim_cost"], d["p"]) for k, d in months.items()]
        for policy, k in (("none", 0), ("level_global", 1), ("level_global", 3), ("level_hub", 6)):
            per, C, E, ll, W = {}, 0.0, 0.0, 0.0, 0.0
            for mo in ev:
                d = months[mo]
                p = make_calibrator(policy, k, known_months(stats, mo, 1))(d["p"].to_numpy(), d["hub"].to_numpy())
                w, c, y = d["weight"].to_numpy(), d["claim_cost"].to_numpy(), d["y_gap"].to_numpy()
                pc = np.clip(p, 1e-6, 1 - 1e-6)
                ll += float(-np.sum(w * c * (y * np.log(pc) + (1 - y) * np.log(1 - pc)))); W += float(np.sum(w * c))
                per[mo] = float(np.sum(w * y * c) / np.sum(w * p * c))
                C += float(np.sum(w * y * c)); E += float(np.sum(w * p * c))
            r = np.array(list(per.values()))
            key = f"{pop:9s} {name:15s} {policy:12s} k={k}"
            out[key] = {"pooled": C / E, "cost_ll": ll / W, "month_sd": float(r.std()), "max_abs_dev": float(np.abs(r - 1).max()), "months": per}
            print(f"{key}  pooled {C / E:.3f}  cost-weighted ll {ll / W:.5f}  monthly sd {r.std():.3f}  "
                  + " ".join(f"{m[2:]}:{v:.2f}" for m, v in per.items()), flush=True)
(ROOT / "results" / "v3_robustness.json").write_text(json.dumps(out, indent=1))
