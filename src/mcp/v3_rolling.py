"""v3 rolling-origin backtest: 26 out-of-sample months instead of six (development data, July 2024 to August 2026).

The frozen v3 model was scored on March to August 2026 only. That is six months, and months are what the weather moves
together, so six months say little about how wide the swings really are or how long a loss ratio takes to learn. Here the
same specification (v1 features, no recalibration, the gap label) is refitted at nine origins, each trained only on data
before the block it then scores, so every one of the 26 months is out of sample for the model that priced it.

    cd src
    MCP_VARIANT=v3 python -m mcp.v3_rolling run         # about 90 minutes; resumes where it stopped
    MCP_VARIANT=v3 python -m mcp.v3_rolling report      # writes results/v3_rolling.json

What this is not: a clean test. The specification was chosen on October 2025 to August 2026, so those months are not
independent of the choice (the choice is one of 20 candidates, but it is a choice). The pre-registered September to
December 2026 window is never read: every window below ends by August 2026.
"""
from __future__ import annotations

import json
import sys

import duckdb
import numpy as np
import pandas as pd

from mcp import features as F
from mcp.connections import ROOT
from mcp.model import fit_gbm
from mcp.v2 import FEATURE_SETS, LEAVES
from mcp.v3 import DEV_GLOB, EVAL_FRAC, TARGET_LR, WTP_CAP, claim_cost, frame_sql, gsa_table, labels, month_file, month_predicate, price
from mcp.variant import MARKETING

OUT = ROOT / "results" / "v3_rolling_weeks.csv"
RESULTS = ROOT / "results" / "v3_rolling.json"
FIT_START = "2024-01-01"
BLOCKS = [("2024-07", "2024-09"), ("2024-10", "2024-12"), ("2025-01", "2025-03"), ("2025-04", "2025-06"), ("2025-07", "2025-09"),
          ("2025-10", "2025-12"), ("2026-01", "2026-03"), ("2026-04", "2026-06"), ("2026-07", "2026-08")]
FIT_ROWS = 3_000_000
USE = FEATURE_SETS["v1 set"]


def window(col: str, start: str, end: str) -> str:
    return f"({col} >= TIMESTAMP '{start}' AND {col} < TIMESTAMP '{end}')"


def aggregate(df: pd.DataFrame, p: str = "p") -> pd.DataFrame:
    """Weekly sums by hub and by whether the connection would be sold (price within the cap), for overnight-risk rows:
    claims = weight x outcome x payout, expected = weight x probability x payout, premium = expected / target loss ratio."""
    sold = price(df[p], df["claim_cost"]) <= WTP_CAP * df["fare"]
    g = df.assign(sold=sold.to_numpy(), claims=df["weight"] * df["y_gap"] * df["claim_cost"], expected=df["weight"] * df[p] * df["claim_cost"],
                  w=df["weight"])
    s = g.groupby(["ym", "week", "hub", "sold"])[["claims", "expected", "w"]].sum().reset_index()
    s["premium"] = s["expected"] / TARGET_LR
    return s


ROW_COLS = ["ym", "week", "hub", "carrier", "slack_min", "fare", "weight", "y", "y_gap", "claim_cost", "p"]


def run_block(con, start: str, end: str, table: dict, rows_dir=None) -> pd.DataFrame:
    fit_end = f"{start}-01"
    F.create_stats(con, fit_flights=window("flight_date", FIT_START, fit_end), fit_asos=window("obs_utc", FIT_START, fit_end))
    src = f"read_parquet('{DEV_GLOB}')"
    pred = window("r.out_sched_dep", FIT_START, fit_end)
    (total,) = con.execute(f"SELECT count(*) FROM {src} r WHERE {pred}").fetchone()
    fit = con.execute(frame_sql(src, pred, min(1.0, FIT_ROWS / total))).fetchdf()
    g = fit_gbm(fit.assign(y=fit["y_gap"]), use=USE, leaves=LEAVES)
    parts = []
    for y, m, lab in labels(start, end):
        df = con.execute(frame_sql(f"read_parquet('{month_file(y, m)}')", month_predicate(y, m), EVAL_FRAC)).fetchdf()
        df = df[df["overnight"].notna() & df["fare"].notna()]
        df = df[df["overnight"] == 1].copy()
        df["p"] = g(df)
        df["claim_cost"] = claim_cost(df, table)
        day = df["out_sched_dep"].dt.normalize()
        df["week"] = (day - pd.to_timedelta(df["out_sched_dep"].dt.day_of_week, unit="D")).astype(str)
        df["ym"] = lab
        parts.append(aggregate(df))
        if rows_dir is not None:                       # the connections themselves, for work that needs more than weekly sums
            rows_dir.mkdir(parents=True, exist_ok=True)
            df[ROW_COLS].to_parquet(rows_dir / f"{lab}.parquet", index=False)
        print(f"  {lab}: {len(df):,} overnight-risk connections, fitted on {fit_end[:7]} and earlier ({len(fit):,} rows)", flush=True)
    return pd.concat(parts, ignore_index=True)


ROWS = ROOT / "data" / "parquet" / "audit_v3" / "rolling_rows"


def run_rows() -> None:
    """The same nine refits, saving each month's overnight-risk connections (a 10% sample) with the model's probability.
    Needed to fit and judge a price loading on rows; leaves the weekly results untouched."""
    assert MARKETING, "run with MCP_VARIANT=v3"
    table, con = gsa_table(), duckdb.connect()
    for start, end in BLOCKS:
        months = [lab for _, _, lab in labels(start, end)]
        if all((ROWS / f"{m}.parquet").exists() for m in months):
            print(f"block {start} to {end}: already saved", flush=True)
            continue
        print(f"block {start} to {end}", flush=True)
        run_block(con, start, end, table, rows_dir=ROWS)


def run() -> None:
    assert MARKETING, "run with MCP_VARIANT=v3"
    table = gsa_table()
    done = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame()
    have = set(done["ym"]) if len(done) else set()
    con = duckdb.connect()
    for start, end in BLOCKS:
        months = [lab for _, _, lab in labels(start, end)]
        if all(m in have for m in months):
            print(f"block {start} to {end}: already done", flush=True)
            continue
        print(f"block {start} to {end}", flush=True)
        done = pd.concat([done, run_block(con, start, end, table)], ignore_index=True)
        done.to_csv(OUT, index=False)


# ---- analysis (pure functions, tested on toy tables) --------------------------------------------------------------

def monthly(weeks: pd.DataFrame, sold_only: bool) -> pd.DataFrame:
    d = weeks[weeks["sold"]] if sold_only else weeks
    s = d.groupby("ym")[["claims", "expected", "premium"]].sum()
    s["ratio"] = s["claims"] / s["expected"]
    s["loss_ratio"] = s["claims"] / s["premium"]
    return s


def weekly(weeks: pd.DataFrame, sold_only: bool) -> pd.Series:
    d = weeks[weeks["sold"]] if sold_only else weeks
    s = d.groupby("week")[["claims", "premium"]].sum()
    return (s["claims"] / s["premium"]).sort_index()


def block_bootstrap_mean(x: np.ndarray, block: int = 3, n_boot: int = 4000, seed: int = 0) -> tuple[float, float]:
    """95% interval for the mean of a series whose neighbours are related, from resampling runs of `block` months."""
    x = np.asarray(x, float)
    n = len(x)
    block = max(1, min(block, n))                     # a series shorter than one block is resampled month by month
    starts = np.arange(n - block + 1)
    rng = np.random.default_rng(seed)
    k = int(np.ceil(n / block))
    means = np.array([np.concatenate([x[s:s + block] for s in rng.choice(starts, k)])[:n].mean() for _ in range(n_boot)])
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def weeks_to_learn(lr: pd.Series, half_width: float = 0.10) -> dict:
    """Weeks of experience before the average weekly loss ratio is known to +-`half_width` of itself, allowing for
    neighbouring weeks being related (AR(1) variance inflation), from the weekly series."""
    x = lr.to_numpy(float)
    mu, sd = x.mean(), x.std(ddof=1)
    rho = float(np.corrcoef(x[:-1], x[1:])[0, 1]) if len(x) > 3 else 0.0
    rho = max(min(rho, 0.9), 0.0)
    infl = (1 + rho) / (1 - rho)
    n = (1.96 * sd / (half_width * mu)) ** 2 * infl
    return {"weeks_independent": float((1.96 * sd / (half_width * mu)) ** 2), "autocorrelation": rho, "weeks": float(n), "mean": float(mu), "sd": float(sd)}


def report() -> dict:
    w = pd.read_csv(OUT)
    out = {"months": int(w["ym"].nunique()), "first": w["ym"].min(), "last": w["ym"].max(), "status": "development backtest, not a clean test"}
    for name, sold in (("all_overnight_risk", False), ("sold_within_cap", True)):
        m = monthly(w, sold)
        wk = weekly(w, sold)
        sel = w[w["sold"]] if sold else w
        d_prem, d_w = float(sel["premium"].sum()), float(sel["w"].sum())
        lo, hi = block_bootstrap_mean(m["ratio"].to_numpy())
        out[name] = {"monthly_ratio": {k: float(v) for k, v in m["ratio"].items()}, "monthly_loss_ratio": {k: float(v) for k, v in m["loss_ratio"].items()},
                     "ratio_mean": float(m["ratio"].mean()), "ratio_sd": float(m["ratio"].std(ddof=1)), "ratio_min": float(m["ratio"].min()), "ratio_max": float(m["ratio"].max()),
                     "months_loss_ratio_above_100": int((m["loss_ratio"] > 1).sum()), "months_ratio_above_1p54": int((m["ratio"] > 1 / TARGET_LR).sum()),
                     "pooled_ratio": float(m["claims"].sum() / m["expected"].sum()), "pooled_loss_ratio": float(m["claims"].sum() / m["premium"].sum()),
                     "mean_price_sold" if sold else "mean_price_all": float(d_prem / d_w), "ratio_mean_block_bootstrap_95": [lo, hi],
                     "t_interval_95": [float(m["ratio"].mean() - 2.06 * m["ratio"].std(ddof=1) / np.sqrt(len(m))), float(m["ratio"].mean() + 2.06 * m["ratio"].std(ddof=1) / np.sqrt(len(m)))],
                     "weeks": int(len(wk)), "weekly_loss_ratio_mean": float(wk.mean()), "weekly_loss_ratio_p95": float(wk.quantile(0.95)), "weekly_loss_ratio_max": float(wk.max()),
                     "weeks_above_100": int((wk > 1).sum()), "learning": weeks_to_learn(wk),
                     "stop_loss_cost_per_premium": {f"attach_{a:.0%}": float(np.maximum(wk.to_numpy() - a, 0).mean()) for a in (0.9, 1.0)}}
    h = w.assign(year=w["ym"].str[:4]).groupby(["hub", "year"])[["claims", "expected"]].sum()
    out["by_hub_year_ratio"] = {hub: {y: float(r["claims"] / r["expected"]) for y, r in g.droplevel(0).iterrows()} for hub, g in h.groupby(level=0)}
    hm = w.groupby(["hub", "ym"])[["claims", "expected"]].sum()
    out["by_hub_months_above_1"] = {hub: int(((g["claims"] / g["expected"]) > 1).sum()) for hub, g in hm.groupby(level=0)}
    out["by_hub_pooled_ratio"] = {hub: float(g["claims"].sum() / g["expected"].sum()) for hub, g in hm.groupby(level=0)}
    sold_share = w[w["sold"]].groupby("ym")["w"].sum() / w.groupby("ym")["w"].sum()
    out["share_sold"] = {"mean": float(sold_share.mean()), "min": float(sold_share.min()), "max": float(sold_share.max())}
    RESULTS.write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "report"
    {"run": run, "rows": run_rows}.get(mode, report)()
