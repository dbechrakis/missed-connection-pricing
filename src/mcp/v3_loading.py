"""A price loading for the selection effect: the cover as sold ran a 75% loss ratio against a 65% target.

The cover is offered only where its price is within 5% of the fare. Choosing connections for a low price is choosing the
ones the model rates safest, which are partly the ones it under-rates (the winner's curse), so the connections that pass
the cap run worse than the model expects: realized/expected 1.15 over 26 backtest months. A loading is a factor lambda
>= 1 on the premium. It does two things at once: it raises the price, and it changes which connections pass the cap, so
the right lambda is a fixed point, not the ratio measured under the old cap:

    lambda = realized / expected, measured on the connections that pass the cap *at that lambda*.

At that point the premium collected on the offered connections equals what the model expects them to cost, divided by the
target loss ratio, and the realized loss ratio is the target. It is fitted on earlier months and judged on later ones,
with the booking lag the cover would have: month m is priced from months up to m-2.

What a loading cannot do is remove the bad months. It sets the average; weather moves a whole month at once, so the
spread around the average is a matter for an exposure cap or reinsurance, not for the price.

    cd src
    MCP_VARIANT=v3 python -m mcp.v3_loading            # needs `python -m mcp.v3_rolling rows`; writes results/v3_loading.json
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from mcp.connections import ROOT
from mcp.v3 import TARGET_LR, WTP_CAP
from mcp.v3_rolling import ROWS

RESULTS = ROOT / "results" / "v3_loading.json"
GRID = np.round(np.arange(1.0, 2.0001, 0.01), 2)
LAG, MIN_MONTHS = 1, 6


def month_index(label: str) -> int:
    return int(label[:4]) * 12 + int(label[5:]) - 1


def sold(df: pd.DataFrame, lam: float, cap: float = WTP_CAP) -> pd.Series:
    """Connections whose premium, loaded by `lam`, is within `cap` of the fare."""
    return lam * df["p"] * df["claim_cost"] / TARGET_LR <= cap * df["fare"]


def measure(df: pd.DataFrame, lam: float) -> dict:
    """What a book sold at loading `lam` earns on `df`: realized/expected on what passes the cap, the loss ratio on the
    premium actually charged, and the share of connections that pass."""
    s = df[sold(df, lam)]
    exp = float((s["weight"] * s["p"] * s["claim_cost"]).sum())
    claims = float((s["weight"] * s["y_gap"] * s["claim_cost"]).sum())
    prem = lam * exp / TARGET_LR
    return {"lam": lam, "ratio": claims / exp if exp else float("nan"), "loss_ratio": claims / prem if prem else float("nan"),
            "share_sold": float(s["weight"].sum() / df["weight"].sum()), "claims": claims, "premium": prem}


def arrays(df: pd.DataFrame, cap: float = WTP_CAP) -> tuple:
    """Per connection: the largest loading at which it still passes the cap (premium lam*p*cost/target <= cap*fare gives
    lam <= cap*fare*target/(p*cost)), the claims it brings and the claims the model expects of it."""
    c = df["claim_cost"].to_numpy(float)
    p = df["p"].to_numpy(float)
    w = df["weight"].to_numpy(float)
    return cap * df["fare"].to_numpy(float) * TARGET_LR / (p * c), w * df["y_gap"].to_numpy(float) * c, w * p * c


def fit_lambda_arrays(t: np.ndarray, claims: np.ndarray, exp: np.ndarray, grid=GRID) -> float:
    """Exact and fast: sort by the threshold once; the offered set at loading lam is every connection with threshold >= lam, so
    its claims and expected claims are cumulative sums. Smallest lam in `grid` at which the loss ratio is at most the target."""
    order = np.argsort(-t)
    ts, cc, ce = t[order], np.cumsum(claims[order]), np.cumsum(exp[order])
    for lam in grid:
        k = int(np.searchsorted(-ts, -lam, side="right"))          # how many connections have threshold >= lam
        if k and cc[k - 1] <= TARGET_LR * lam * ce[k - 1] / TARGET_LR:
            return float(lam)
    return float(grid[-1])


def fit_lambda(df: pd.DataFrame, grid=GRID) -> float:
    """The smallest loading in `grid` at which the offered connections realize the target loss ratio on `df`; 1.0 if the
    unloaded price already does, the largest value if none does."""
    return fit_lambda_arrays(*arrays(df), grid=grid)


def load_months(rows_dir=ROWS) -> dict:
    return {f.stem: pd.read_parquet(f) for f in sorted(rows_dir.glob("*.parquet"))}


def rolling(months: dict, lag: int = LAG, min_months: int = MIN_MONTHS, window: int | None = None) -> pd.DataFrame:
    """For each month with at least `min_months` of earlier history (months up to m - 1 - lag), the loading fitted on that
    history (all of it, or only its last `window` months), and what the month earned with and without it."""
    labels = sorted(months)
    arr = {lab: arrays(months[lab]) for lab in labels}
    out = []
    for lab in labels:
        hist = [h for h in labels if month_index(h) <= month_index(lab) - 1 - lag]
        if len(hist) < min_months:
            continue
        hist = hist[-window:] if window else hist
        lam = fit_lambda_arrays(*(np.concatenate([arr[h][k] for h in hist]) for k in range(3)))
        base, loaded = measure(months[lab], 1.0), measure(months[lab], lam)
        out.append({"ym": lab, "lam": lam, "history_months": len(hist), **{f"base_{k}": v for k, v in base.items() if k != "lam"},
                    **{f"loaded_{k}": v for k, v in loaded.items() if k != "lam"}})
    return pd.DataFrame(out)


def weekly_loss_ratio(df: pd.DataFrame, lam: float) -> pd.Series:
    s = df[sold(df, lam)]
    g = s.assign(c=s["weight"] * s["y_gap"] * s["claim_cost"], e=s["weight"] * s["p"] * s["claim_cost"]).groupby("week")[["c", "e"]].sum()
    return g["c"] / (lam * g["e"] / TARGET_LR)


FROZEN = ROOT / "models" / "v4_loading.json"


def frozen_summary(months: dict, lam: float) -> dict:
    """What the frozen loading does on the development months it was fitted on (in-sample by construction for the pooled
    level; the paired comparison with the unloaded price and the seasonal figures are what the pre-registration uses)."""
    labs = sorted(months)
    base = {m: measure(months[m], 1.0) for m in labs}
    load = {m: measure(months[m], lam) for m in labs}
    pool = lambda d, ms: sum(d[m]["claims"] for m in ms) / sum(d[m]["premium"] for m in ms)
    blocks = [labs[i:i + 3] for i in range(len(labs) - 2)]
    gain = [100 * (pool(base, b) - pool(load, b)) for b in blocks]
    allrows = pd.concat(months.values(), ignore_index=True)
    wk, wb = weekly_loss_ratio(allrows, lam), weekly_loss_ratio(allrows, 1.0)
    seasonal = {}
    for y in sorted({m[:4] for m in labs}):
        ms = [f"{y}-{k:02d}" for k in (9, 10, 11)]
        if all(m in months for m in ms):
            rows = pd.concat([months[m] for m in ms], ignore_index=True)
            wl, wu = weekly_loss_ratio(rows, lam), weekly_loss_ratio(rows, 1.0)
            seasonal[y] = {"loaded_loss_ratio": pool(load, ms), "unloaded_loss_ratio": pool(base, ms), "share_sold": float(np.mean([load[m]["share_sold"] for m in ms])),
                           "weeks": int(len(wl)), "weeks_above_100_loaded": int((wl > 1).sum()), "weeks_above_100_unloaded": int((wu > 1).sum()),
                           "worst_week_loaded": float(wl.max()), "worst_week_unloaded": float(wu.max())}
    shares = [load[m]["share_sold"] for m in labs]
    return {"lambda": lam, "months": len(labs), "pooled_loss_ratio_unloaded": pool(base, labs), "pooled_loss_ratio_loaded": pool(load, labs),
            "months_above_100_unloaded": int(sum(base[m]["loss_ratio"] > 1 for m in labs)), "months_above_100_loaded": int(sum(load[m]["loss_ratio"] > 1 for m in labs)),
            "weeks": int(len(wk)), "weeks_above_100_unloaded": int((wb > 1).sum()), "weeks_above_100_loaded": int((wk > 1).sum()),
            "worst_week_unloaded": float(wb.max()), "worst_week_loaded": float(wk.max()),
            "share_sold_monthly": {"mean": float(np.mean(shares)), "min": float(np.min(shares)), "max": float(np.max(shares))},
            "unloaded_share_sold_mean": float(np.mean([base[m]["share_sold"] for m in labs])),
            "three_month_blocks": {"n": len(blocks), "loaded_below_unloaded": int(sum(g > 0 for g in gain)), "gain_points_mean": float(np.mean(gain)), "gain_points_min": float(np.min(gain)),
                                   "loaded_loss_ratio_p5_p50_p95": [float(x) for x in np.percentile([pool(load, b) for b in blocks], [5, 50, 95])]},
            "september_to_november": seasonal}


def freeze(months: dict) -> dict:
    """Write the artefact the pre-registered test will load: one number, the rule that produced it and the data it came from."""
    lam = fit_lambda(pd.concat(months.values(), ignore_index=True))
    art = {"lambda": lam, "cap": WTP_CAP, "target_loss_ratio": TARGET_LR, "model": "models/pmiss_v3.joblib (frozen, unchanged)",
           "rule": "smallest loading in 1.00..2.00 (step 0.01) at which the connections whose loaded premium is within the cap realize the target loss ratio",
           "fitted_on": f"{min(months)} to {max(months)}: {len(months)} months of a rolling-origin backtest (10% sample of overnight-risk connections)"}
    FROZEN.write_text(json.dumps(art, indent=1) + chr(10), encoding="utf-8", newline=chr(10))
    return art


def main() -> None:
    months = load_months()
    r = rolling(months)
    pooled = lambda p: float(r[f"{p}_claims"].sum() / r[f"{p}_premium"].sum())
    out = {"months_tested": int(len(r)), "first": r["ym"].min(), "last": r["ym"].max(), "lag": LAG, "min_history_months": MIN_MONTHS,
           "status": "development: lambda fitted on earlier months and judged on later ones; not a clean test",
           "unloaded": {"loss_ratio": pooled("base"), "months_above_100": int((r["base_loss_ratio"] > 1).sum()), "share_sold_mean": float(r["base_share_sold"].mean())},
           "loaded": {"loss_ratio": pooled("loaded"), "months_above_100": int((r["loaded_loss_ratio"] > 1).sum()), "share_sold_mean": float(r["loaded_share_sold"].mean())},
           "lambda": {"mean": float(r["lam"].mean()), "min": float(r["lam"].min()), "max": float(r["lam"].max()), "last": float(r["lam"].iloc[-1])},
           "monthly": {row["ym"]: {"lam": row["lam"], "base_loss_ratio": row["base_loss_ratio"], "loaded_loss_ratio": row["loaded_loss_ratio"],
                                   "loaded_share_sold": row["loaded_share_sold"]} for _, row in r.iterrows()}}
    allrows = pd.concat(months.values(), ignore_index=True)
    out["lambda_all_months"] = fit_lambda(allrows)
    out["all_months_at_that_lambda"] = measure(allrows, out["lambda_all_months"])
    out["frozen"] = frozen_summary(months, out["lambda_all_months"])
    out["windows"] = {str(w): float(rolling(months, window=w).pipe(lambda r: r.loaded_claims.sum() / r.loaded_premium.sum())) for w in (None, 12, 9, 6)}
    RESULTS.write_text(json.dumps(out, indent=1, default=float))
    print(f"{out['months_tested']} months tested ({out['first']} to {out['last']}): loss ratio {out['unloaded']['loss_ratio']:.1%} -> {out['loaded']['loss_ratio']:.1%}; "
          f"months above 100%: {out['unloaded']['months_above_100']} -> {out['loaded']['months_above_100']}; share sold {out['unloaded']['share_sold_mean']:.1%} -> {out['loaded']['share_sold_mean']:.1%}")
    print(f"lambda: mean {out['lambda']['mean']:.2f}, range {out['lambda']['min']:.2f} to {out['lambda']['max']:.2f}; fitted on all months {out['lambda_all_months']:.2f}")


if __name__ == "__main__":
    import sys
    if "freeze" in sys.argv:
        print(freeze(load_months()))
    else:
        main()
