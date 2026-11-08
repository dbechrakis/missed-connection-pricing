"""H2 2025 backtest. The ONLY module allowed to read the test window. Protocol: VALIDATION.md Part 1.

Pricing is fixed before this runs (models/pmiss.joblib, config/pricing.yaml). For every test
connection we compute what each pricing schedule would have charged and what the connection
actually cost (rebooking, plus overnight if the next flight is the next day, only if it was missed).

    realized loss ratio = sum(claims) / sum(premiums)
    realized / target   = sum(w b y c) / sum(w b p c)     for a schedule priced at p c / target

`b` is the purchase weight. Who buys is unknown, so b = p_iso ** theta for a grid of theta
(0 = nobody self-selects) and results are shown as a curve, never at one chosen theta.

Run:  python -m mcp.backtest        (from src/)
"""
from __future__ import annotations

import json

import duckdb
import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from mcp.connections import ROOT, WEIGHTED  # noqa: E402
from mcp.features import OUT, create_stats, feature_sql  # noqa: E402
from mcp.model import bucket_of, ece, fit_rates, cells, reliability, EPS  # noqa: E402
from mcp.pricing import MODEL, SEVERITY, load_config, price, expected_cost  # noqa: E402
from mcp.split import where  # noqa: E402

THETAS = (0.0, 0.5, 1.0, 2.0)
MODELS = ("baseline", "gbm_raw", "gbm_iso")
HIST_BINS = 2000          # fine histogram of predictions: exact enough to rebuild Brier-style cell metrics
FIG = ROOT / "docs" / "figures"
RESULTS = ROOT / "results" / "backtest.json"


# ---- pure aggregation (tested on synthetic data) -----------------------------------------------

def _tag(theta: float) -> str:
    return f"{theta:g}"


def aggregate(df: pd.DataFrame, cfg: dict, models=MODELS, product: str = "gbm_iso", buy: str = "gbm_iso") -> dict:
    """One month of scored connections -> additive sums (so months can simply be added).

    Required columns: y, weight, overnight, fare, hub, bucket, week, month, and p_<model> for each model.
    `product` is the model whose price decides who is offered; `buy` is the model whose probability
    drives the purchase weight (both default to the calibrated GBM).
    """
    c = cfg["rebooking_cost"] + cfg["overnight_cost"] * df["overnight"].to_numpy()
    w, y = df["weight"].to_numpy(), df["y"].to_numpy()
    lr = cfg["target_loss_ratio"]
    prices = {m: df[f"p_{m}"].to_numpy() * c / lr for m in models}
    offered = prices[product] <= cfg["wtp_cap_pct"] * df["fare"].to_numpy()
    p_buy = df[f"p_{buy}"].to_numpy()

    base = pd.DataFrame({"week": df["week"].to_numpy(), "hub": df["hub"].to_numpy(), "bucket": df["bucket"].to_numpy(),
                         "month": df["month"].to_numpy(), "offered": offered})
    for th in THETAS:
        wb = w * (p_buy**th if th else 1.0)
        t = _tag(th)
        base[f"W{t}"] = wb
        base[f"claim{t}"] = wb * y * c
        for m in models:
            base[f"prem_{m}{t}"] = wb * prices[m]
    # calibration material (weighted by passengers only: the purchase weight is a pricing-comparison device)
    base["w"], base["wy"] = w, w * y
    for m in models:
        base[f"wp_{m}"] = w * df[f"p_{m}"].to_numpy()
    sums = base.groupby(["week", "hub", "bucket", "month", "offered"], as_index=False).sum()

    hist = {}
    for m in models:
        p = np.clip(df[f"p_{m}"].to_numpy(), 0, 1)
        idx = np.minimum((p * HIST_BINS).astype(int), HIST_BINS - 1)
        pc = np.clip(p, EPS, 1 - EPS)
        hist[m] = {"W": np.bincount(idx, w, HIST_BINS), "Wy": np.bincount(idx, w * y, HIST_BINS),
                   "Wp": np.bincount(idx, w * p, HIST_BINS),
                   "brier": float(np.sum(w * (y - p) ** 2)),
                   "logloss": float(-np.sum(w * (y * np.log(pc) + (1 - y) * np.log(1 - pc))))}
    return {"sums": sums, "hist": hist}


def merge(parts: list[dict], models=MODELS) -> dict:
    sums = pd.concat([p["sums"] for p in parts]).groupby(["week", "hub", "bucket", "month", "offered"], as_index=False).sum()
    hist = {}
    for m in models:
        hist[m] = {k: sum(p["hist"][m][k] for p in parts) for k in ("W", "Wy", "Wp", "brier", "logloss")}
    return {"sums": sums, "hist": hist}


def ratio_with_ci(sums: pd.DataFrame, num: str, den, n_boot: int = 2000, seed: int = 0, weeks=None) -> dict:
    """sum(num) / sum(den) with a 95% interval from resampling whole weeks."""
    den = [den] if isinstance(den, str) else den
    weekly = sums.assign(_den=sums[den].sum(axis=1)).groupby("week")[[num, "_den"]].sum()
    if weeks is not None:
        weekly = weekly.reindex(weeks, fill_value=0.0)
    a = weekly.to_numpy()
    point = a[:, 0].sum() / a[:, 1].sum() if a[:, 1].sum() > 0 else float("nan")
    idx = np.random.default_rng(seed).integers(0, len(a), (n_boot, len(a)))
    num, den_ = a[idx, 0].sum(1), a[idx, 1].sum(1)
    boot = np.where(den_ > 0, num / np.where(den_ > 0, den_, 1.0), np.nan)   # a draw of empty weeks has no ratio
    if not np.isfinite(point) or np.isnan(boot).all():
        return {"ratio": float("nan"), "lo": float("nan"), "hi": float("nan")}
    return {"ratio": float(point), "lo": float(np.nanpercentile(boot, 2.5)), "hi": float(np.nanpercentile(boot, 97.5))}


def analyse(parts_sum: dict, cfg: dict, flat_train: float, models=MODELS, product: str = "gbm_iso") -> dict:
    s, h = parts_sum["sums"], parts_sum["hist"]
    lr = cfg["target_loss_ratio"]
    weeks = sorted(s["week"].unique())
    out: dict = {"weeks": len(weeks)}

    # realized / target = claims / (premium x target). Premium columns already include the 1/LR.
    def rt(sub, th, model):  # point + CI
        t = _tag(th)
        sub = sub.assign(**{f"_p": sub[f"prem_{model}{t}"] * lr})
        return ratio_with_ci(sub, f"claim{t}", "_p", weeks=weeks)

    out["overall"] = {m: {_tag(th): rt(s, th, m) for th in THETAS} for m in models}
    # flat prices: one price for everybody
    W0, C0 = s["W0"].sum(), s["claim0"].sum()
    oracle = C0 / (lr * W0)
    out["flat"] = {"train_price": flat_train, "oracle_price": float(oracle), "tiered_mean_price_theta0": float(s[f"prem_{product}0"].sum() / W0)}
    flat = {}
    for name, price_ in (("flat_train", flat_train), ("flat_oracle", oracle)):
        flat[name] = {}
        for th in THETAS:
            t = _tag(th)
            sub = s.assign(_p=price_ * s[f"W{t}"] * lr)
            flat[name][t] = ratio_with_ci(sub, f"claim{t}", "_p", weeks=weeks)
    out["flat_pricing"] = flat

    out["by_hub"] = {hub: {m: rt(g, 0.0, m) for m in models} for hub, g in s.groupby("hub")}
    out["offered_only"] = {"share_of_weight": float(s.loc[s["offered"], "W0"].sum() / W0),
                           "gbm_iso_theta0": rt(s[s["offered"]], 0.0, product),
                           "not_offered_gbm_iso_theta0": rt(s[~s["offered"]], 0.0, product)}
    cols = ["w", "wy"] + [f"wp_{m}" for m in models]
    mo = s.groupby("month")[cols].sum()
    out["by_month"] = {int(m): {"observed": r.wy / r.w, **{f"pred_{k}": r[f"wp_{k}"] / r.w for k in models}} for m, r in mo.iterrows()}
    bk = s.groupby("bucket")[cols].sum()
    out["by_slack_bucket"] = {int(45 + 15 * b): {"observed": r.wy / r.w, **{f"pred_{k}": r[f"wp_{k}"] / r.w for k in models}}
                              for b, r in bk.iterrows()}

    out["scores"], out["reliability"] = {}, {}
    for m in models:
        W, Wy, Wp = h[m]["W"], h[m]["Wy"], h[m]["Wp"]
        keep = W > 0
        pbin = Wp[keep] / W[keep]
        out["scores"][m] = {"brier": h[m]["brier"] / W.sum(), "log_loss": h[m]["logloss"] / W.sum(),
                            "ece": ece(W[keep], Wy[keep], pbin), "mean_pred": float(Wp.sum() / W.sum()),
                            "observed": float(Wy.sum() / W.sum())}
        out["reliability"][m] = reliability(W[keep], Wy[keep], pbin)
    return out


# ---- running it --------------------------------------------------------------------------------

def score_month(con, path: str, predicate: str, bundle: dict, base_rates: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Features, the three models' predictions, week and month for one month of connections.
    Returns (scored rows, rows dropped for missing severity or fare)."""
    from mcp.model import _codes
    df = con.execute(feature_sql(f"read_parquet('{path}')", predicate, 1.0, SEVERITY.as_posix())).fetchdf()
    bad = df["overnight"].isna() | df["fare"].isna()
    df = df[~bad].copy()
    df["bucket"] = bucket_of(df["slack_min"])
    df = df.merge(base_rates, on=["hub", "bucket"], how="left")
    raw = bundle["gbm"].predict_proba(_codes(df[bundle["features"]], bundle["cats"]))[:, 1]
    df["p_gbm_raw"], df["p_gbm_iso"] = raw, bundle["isotonic"].predict(raw)
    day = df["out_sched_dep"].dt.normalize()
    df["week"] = (day - pd.to_timedelta(df["out_sched_dep"].dt.day_of_week, unit="D")).astype(str)
    df["month"] = df["out_sched_dep"].dt.month
    return df, int(bad.sum())


def load_inputs(cfg: dict):
    bundle = joblib.load(MODEL)
    base_rates = pd.DataFrame([(h, int(b), r) for (h, b), r in fit_rates(cells("FIT"), ("hub", "bucket")).items()],
                              columns=["hub", "bucket", "p_baseline"])
    train = pd.read_parquet(OUT / "PRICING_TRAIN.parquet", columns=["y", "weight", "overnight"])
    flat_train = float(np.average(train["y"] * (cfg["rebooking_cost"] + cfg["overnight_cost"] * train["overnight"]),
                                  weights=train["weight"]) / cfg["target_loss_ratio"])
    con = duckdb.connect()
    create_stats(con)
    return bundle, base_rates, flat_train, con


def month_path(year: int, month: int) -> str:
    return (WEIGHTED / "mct=45" / f"year={year}" / f"month={month:02d}.parquet").as_posix()


def run(months=range(7, 13), predicate=None, year=2025) -> dict:
    cfg = load_config()
    bundle, base_rates, flat_train, con = load_inputs(cfg)
    # The single place the test window is read (unless a caller passes a different predicate):
    predicate = predicate or where("TEST", "r.out_sched_dep")
    parts, dropped, total = [], 0, 0
    for month in months:
        df, bad = score_month(con, month_path(year, month), predicate, bundle, base_rates)
        dropped, total = dropped + bad, total + len(df) + bad
        parts.append(aggregate(df, cfg))
        print(f"{year}-{month:02d}: {len(df):,} connections scored", flush=True)
    res = analyse(merge(parts), cfg, flat_train)
    res["rows"] = {"scored": total - dropped, "dropped_missing_severity_or_fare": dropped, "total": total}
    return res


def figures(res: dict) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.alpha": 0.25, "figure.dpi": 130, "font.size": 10})
    col = {"baseline": "#888888", "gbm_raw": "#E69F00", "gbm_iso": "#0072B2", "flat_train": "#D55E00", "flat_oracle": "#CC79A7"}
    # 1. realized / target by hub, theta 0
    hubs = sorted(res["by_hub"])
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(hubs))
    for i, m in enumerate(MODELS):
        r = [res["by_hub"][h][m]["ratio"] for h in hubs]
        err = None
        if m == "gbm_iso":
            err = [[res["by_hub"][h][m]["ratio"] - res["by_hub"][h][m]["lo"] for h in hubs],
                   [res["by_hub"][h][m]["hi"] - res["by_hub"][h][m]["ratio"] for h in hubs]]
        ax.bar(x + (i - 1) * 0.27, r, 0.27, yerr=err, color=col[m], capsize=3, label=m.replace("_", " "))
    ax.axhline(1, color="k", lw=1, ls="--")
    ax.set(xticks=x, xticklabels=hubs, ylabel="Realized ÷ target loss ratio", title="H2 2025 backtest by hub (1.0 = on target)")
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    fig.tight_layout(); fig.savefig(FIG / "backtest_by_hub.png"); plt.close(fig)
    # 2. versus theta
    fig, ax = plt.subplots(figsize=(7, 4))
    th = [float(t) for t in (_tag(t) for t in THETAS)]
    for name, series in (("gbm_iso", res["overall"]["gbm_iso"]), ("flat_train", res["flat_pricing"]["flat_train"]),
                         ("flat_oracle", res["flat_pricing"]["flat_oracle"])):
        ax.plot(th, [series[_tag(t)]["ratio"] for t in THETAS], marker="o", lw=2, color=col[name],
                label={"gbm_iso": "tiered (calibrated GBM)", "flat_train": "flat, from training average",
                       "flat_oracle": "flat, hindsight oracle"}[name])
    ax.axhline(1, color="k", lw=1, ls="--")
    ax.set(xlabel="Adverse selection strength θ (0 = buyers ignore risk)", ylabel="Realized ÷ target loss ratio",
           title="Tiered pricing holds up as buyers self-select; flat does not")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "backtest_vs_selection.png"); plt.close(fig)
    # 3. reliability on test
    fig, ax = plt.subplots(figsize=(4.8, 4.8))
    top = 0
    for m in MODELS:
        rel = res["reliability"][m]
        ax.plot([r[0] * 100 for r in rel], [r[1] * 100 for r in rel], marker="o", color=col[m], label=m.replace("_", " "))
        top = max(top, max(max(r[0], r[1]) for r in rel) * 100)
    ax.plot([0, top * 1.05], [0, top * 1.05], color="#888", ls="--", lw=1)
    ax.set(xlabel="Predicted P(miss) (%)", ylabel="Observed miss rate (%)", aspect="equal",
           title="Reliability on H2 2025 (equal-weight bins)")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "backtest_reliability.png"); plt.close(fig)
    # 4. level by month
    fig, ax = plt.subplots(figsize=(7, 3.8))
    mo = sorted(res["by_month"], key=int)
    xs = [int(m) for m in mo]
    ax.plot(xs, [res["by_month"][m]["observed"] * 100 for m in mo], marker="o", color="k", lw=2, label="observed")
    ax.plot(xs, [res["by_month"][m]["pred_gbm_iso"] * 100 for m in mo], marker="o", color=col["gbm_iso"], lw=2, label="predicted (calibrated)")
    ax.set(xlabel="Month of 2025", ylabel="Missed connections (%)", title="Level check: observed vs predicted by month")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "backtest_level.png"); plt.close(fig)


def main() -> None:
    res = run()
    RESULTS.write_text(json.dumps(res, indent=2, default=float))
    figures(res)
    o = res["overall"]
    print("\nrealized / target (1.0 = on target), theta=0:")
    for m in MODELS:
        r = o[m]["0"]
        print(f"  {m:10s} {r['ratio']:.3f}  [{r['lo']:.3f}, {r['hi']:.3f}]")
    print("scores:", json.dumps(res["scores"], indent=1))


if __name__ == "__main__":
    main()
