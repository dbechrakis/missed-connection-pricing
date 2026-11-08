"""v3 audit, round 2 (development data only, March to August 2026; the pre-registered window is never read).

Four questions the first round left open, each answered from data this project already has:

  bootstrap   How much of the gap cover's result is the model, not the weather? Refit the gap model on bootstrap
              resamples of its training sample and score the same connections each time.
  grid        How much do the two assumed numbers, the price cap and the target loss ratio, move the answer?
              Share of overnight-risk connections that can be offered, and what happens to the ones that are.
  exposure    What does a book of these covers look like week by week? Loss ratio by week, the worst week, and what an
              aggregate stop-loss would have cost on these weeks (indicative: 26 weeks).
  mct         The minimum connection time is assumed (45 minutes) and differs by hub. If a hub's true value is 35 or
              60, how wrong are prices set for 45? Hubs are independent, so one table covers every combination.

    cd src
    MCP_VARIANT=v3 python -m mcp.v3_audit frames       # score the evaluation connections once (needs weighted 35, 45, 60)
    MCP_VARIANT=v3 python -m mcp.v3_audit bootstrap    # 8 refits, about 40 minutes
    MCP_VARIANT=v3 python -m mcp.v3_audit report       # grid, exposure, mct; writes results/v3_audit.json

None of this changes the frozen v3 model or its pre-registration. It reports on it.
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
from mcp.connections import ROOT, WEIGHTED
from mcp.model import _codes, fit_gbm
from mcp.split import where
from mcp.v2 import FEATURE_SETS, LEAVES
from mcp.v3 import BUNDLE, DEV_GLOB, EVAL_FRAC, SEL_ROWS, TARGET_LR, WTP_CAP, claim_cost, frame_sql, gsa_table, labels, month_predicate
from mcp.variant import MARKETING

CACHE = ROOT / "data" / "parquet" / "audit_v3"
OUT = ROOT / "results" / "v3_audit.json"
FIRST, LAST = "2026-03", "2026-08"          # the evaluation months: out of sample for the model, already read
MCTS = (35, 45, 60)
CAPS = (0.03, 0.05, 0.07, 0.10)
LOSS_RATIOS = (0.55, 0.65, 0.75)
HUBS = ("ATL", "CLT", "DEN", "DFW", "ORD")
N_REFITS, REFIT_ROWS = 8, 2_500_000
USE = FEATURE_SETS["v1 set"]
KEEP = list(dict.fromkeys(list(USE) + ["hub", "slack_min", "fare", "weight", "y", "y_gap", "claim_cost", "week", "ym", "p"]))


# ---- pure helpers (tested on toy tables) --------------------------------------------------------------------------

def ratio(df: pd.DataFrame, p: str = "p") -> float:
    """Realized / expected payouts (cost-weighted): 1.0 = priced on target."""
    e = float((df["weight"] * df[p] * df["claim_cost"]).sum())
    return float((df["weight"] * df["y_gap"] * df["claim_cost"]).sum() / e) if e > 0 else float("nan")


def offered(df: pd.DataFrame, cap: float, loss_ratio: float = TARGET_LR, p: str = "p") -> pd.Series:
    """Connections whose premium (expected payout / target loss ratio) is within `cap` of the fare."""
    return df[p] * df["claim_cost"] / loss_ratio <= cap * df["fare"]


def weekly_loss_ratio(df: pd.DataFrame, loss_ratio: float = TARGET_LR, p: str = "p") -> pd.Series:
    """Claims over premium by week for a book that sells every connection in `df` at the target-loss-ratio price."""
    g = df.assign(c=df["weight"] * df["y_gap"] * df["claim_cost"], prem=df["weight"] * df[p] * df["claim_cost"] / loss_ratio)
    s = g.groupby("week")[["c", "prem"]].sum()
    return s["c"] / s["prem"]


def stop_loss_cost(lr: pd.Series, attach: float) -> float:
    """Average excess of the weekly loss ratio over `attach`, per unit of premium: what a stop-loss at `attach`
    would have paid on these weeks, which is the least it could cost (no loading, no tail beyond what was seen)."""
    return float(np.maximum(lr.to_numpy() - attach, 0).mean())


def by_hub(df: pd.DataFrame, f) -> dict:
    return {h: f(g) for h, g in df.groupby("hub")}


# ---- frames -------------------------------------------------------------------------------------------------------

def month_file(mct: int, y: int, m: int) -> str:
    return (WEIGHTED / f"mct={mct}" / f"year={y}" / f"month={m:02d}.parquet").as_posix()


def build_frame(mct: int) -> pd.DataFrame:
    """Overnight-risk connections (the only ones the cover pays on), a 10% sample, scored with the frozen v3 model."""
    assert MARKETING, "run with MCP_VARIANT=v3"
    bundle, table = joblib.load(BUNDLE), gsa_table()
    con = duckdb.connect()
    F.create_stats(con, fit_flights=where("V3_FIT", "flight_date"), fit_asos=where("V3_FIT", "obs_utc"))
    parts = []
    for y, m, lab in labels(FIRST, LAST):
        df = con.execute(frame_sql(f"read_parquet('{month_file(mct, y, m)}')", month_predicate(y, m), EVAL_FRAC)).fetchdf()
        df = df[df["overnight"].notna() & df["fare"].notna()]
        df = df[df["overnight"] == 1].copy()
        df["p"] = bundle["gbm_gap"].predict_proba(_codes(df[bundle["features"]], bundle["cats"]))[:, 1]
        df["claim_cost"] = claim_cost(df, table)
        day = df["out_sched_dep"].dt.normalize()
        df["week"] = (day - pd.to_timedelta(df["out_sched_dep"].dt.day_of_week, unit="D")).astype(str)
        df["ym"] = lab
        parts.append(df[KEEP])
        print(f"mct={mct} {lab}: {len(df):,} overnight-risk connections", flush=True)
    return pd.concat(parts, ignore_index=True)


def load_frame(mct: int) -> pd.DataFrame:
    return pd.read_parquet(CACHE / f"eval_mct{mct}.parquet")


# ---- 1. refit bootstrap -------------------------------------------------------------------------------------------

def summarise_model(df: pd.DataFrame, p: np.ndarray, cap: float = WTP_CAP) -> dict:
    d = df.assign(q=p)
    mo = offered(d, cap, p="q")
    return {"pooled": ratio(d, "q"), "monthly": {k: ratio(g, "q") for k, g in d.groupby("ym")},
            "share_offered": float(d["weight"][mo].sum() / d["weight"].sum()),
            "offered_ratio": ratio(d[mo], "q"), "mean_p": float(np.average(p, weights=d["weight"]))}


def run_bootstrap() -> dict:
    assert MARKETING, "run with MCP_VARIANT=v3"
    ev = load_frame(45)
    con = duckdb.connect()
    F.create_stats(con, fit_flights=where("V3_FIT", "flight_date"), fit_asos=where("V3_FIT", "obs_utc"))
    src = f"read_parquet('{DEV_GLOB}')"
    (total,) = con.execute(f"SELECT count(*) FROM {src} WHERE {where('V3_FIT')}").fetchone()
    fit = con.execute(frame_sql(src, where("V3_FIT", "r.out_sched_dep"), min(1.0, SEL_ROWS / total))).fetchdf()
    bundle = joblib.load(BUNDLE)
    frozen = summarise_model(ev, ev["p"].to_numpy())
    sums = pd.DataFrame({"week": ev["week"], "claims": ev["weight"] * ev["y_gap"] * ev["claim_cost"],
                         "expected": ev["weight"] * ev["p"] * ev["claim_cost"]})
    out = {"frozen": frozen, "frozen_weekly_bootstrap_ci": ratio_with_ci(sums, "claims", "expected"),
           "fit_rows": int(len(fit)), "refit_rows": REFIT_ROWS, "refits": [], "bundle_features": bundle["features"]}
    for k in range(N_REFITS):
        rng = np.random.default_rng(1000 + k)
        boot = fit.iloc[rng.integers(0, len(fit), REFIT_ROWS)]
        g = fit_gbm(boot.assign(y=boot["y_gap"]), use=USE, leaves=LEAVES, seed=k)
        out["refits"].append({"seed": k, **summarise_model(ev, g(ev))})
        print(f"refit {k}: pooled {out['refits'][-1]['pooled']:.3f}, offered {out['refits'][-1]['share_offered']:.3f}", flush=True)
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / "bootstrap.json").write_text(json.dumps(out, indent=1, default=float))
    return out


# ---- 2 to 4. report -----------------------------------------------------------------------------------------------

def cap_grid(df: pd.DataFrame) -> dict:
    out = {}
    tot = df["weight"].sum()
    for lr in LOSS_RATIOS:
        for cap in CAPS:
            m = offered(df, cap, lr)
            on = df[m]
            r = ratio(on)
            out[f"lr{lr:.2f}_cap{cap:.2f}"] = {"loss_ratio_target": lr, "cap": cap, "share_offered": float(on["weight"].sum() / tot),
                                                "offered_ratio": r, "offered_realized_loss_ratio": lr * r,
                                                "mean_price": float(np.average(on["p"] * on["claim_cost"] / lr, weights=on["weight"]))}
    return out


def exposure(df: pd.DataFrame) -> dict:
    out = {}
    sold = df[offered(df, WTP_CAP)]
    for name, d in (("all_overnight_risk", df), (f"offered_within_{WTP_CAP:.0%}_cap", sold)):
        wk = weekly_loss_ratio(d)
        mo = weekly_loss_ratio(d.assign(week=d["ym"]))
        out[name] = {"weeks": int(len(wk)), "mean": float(wk.mean()), "sd": float(wk.std()), "p95": float(wk.quantile(0.95)),
                     "max": float(wk.max()), "weeks_above_100pct": int((wk > 1).sum()), "weeks_above_target_plus_20pts": int((wk > TARGET_LR + 0.2).sum()),
                     "worst_month": float(mo.max()), "monthly": {k: float(v) for k, v in mo.items()},
                     "stop_loss_cost_per_premium": {f"attach_{a:.0%}": stop_loss_cost(wk, a) for a in (0.9, 1.0)},
                     "worst_hub_week": {h: float(weekly_loss_ratio(g).max()) for h, g in d.groupby("hub")}}
    return out


def mct_table(frames: dict) -> dict:
    out = {}
    for mct, df in frames.items():
        cell = lambda g: {"connections": int(len(g)), "realized_over_target": ratio(g), "mean_p": float(np.average(g["p"], weights=g["weight"])),
                          "gap_miss_rate": float(np.average(g["y_gap"], weights=g["weight"])),
                          "share_offered_5pct": float(g["weight"][offered(g, WTP_CAP)].sum() / g["weight"].sum()),
                          "share_below_45min": float((g["slack_min"] < 45).mean())}
        out[str(mct)] = {"all": cell(df), "by_hub": by_hub(df, cell)}
    return out


def run_report() -> dict:
    frames = {m: load_frame(m) for m in MCTS}
    f45 = frames[45]
    res = {"window": f"{FIRST} to {LAST}", "status": "development orientation on spent months, not validation",
           "rows_45": int(len(f45)), "cap_grid": cap_grid(f45), "exposure": exposure(f45), "mct": mct_table(frames)}
    boot = CACHE / "bootstrap.json"
    if boot.exists():
        b = json.loads(boot.read_text())
        pooled = np.array([r["pooled"] for r in b["refits"]])
        off = np.array([r["share_offered"] for r in b["refits"]])
        orat = np.array([r["offered_ratio"] for r in b["refits"]])
        res["bootstrap"] = {"frozen": b["frozen"], "frozen_weekly_bootstrap_ci": b["frozen_weekly_bootstrap_ci"], "refits": len(pooled),
                            "pooled_mean": float(pooled.mean()), "pooled_sd": float(pooled.std(ddof=1)), "pooled_min": float(pooled.min()), "pooled_max": float(pooled.max()),
                            "share_offered_sd": float(off.std(ddof=1)), "share_offered_min": float(off.min()), "share_offered_max": float(off.max()),
                            "offered_ratio_mean": float(orat.mean()), "offered_ratio_sd": float(orat.std(ddof=1)),
                            "refit_rows": b["refit_rows"], "fit_rows": b["fit_rows"]}
    OUT.write_text(json.dumps(res, indent=1, default=float))
    return res


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    if mode == "frames":
        CACHE.mkdir(parents=True, exist_ok=True)
        for m in (int(x) for x in sys.argv[2:]) or MCTS:
            build_frame(m).to_parquet(CACHE / f"eval_mct{m}.parquet", index=False)
    elif mode == "bootstrap":
        run_bootstrap()
    elif mode == "report":
        run_report()
