"""The 2026 holdout (Jan-Aug 2026). The ONLY module allowed to read this window. Protocol: VALIDATION.md Part 3.

Five prices are computed for every 2026 connection, all from information available before 2026:

  baseline    hub x slack rate fitted on 2024
  v1_raw      v1 GBM, no calibration           (frozen, Part 1 hashes)
  v1_iso      v1 as shipped: GBM + isotonic fitted on Apr-Jun 2025
  v2_static   v2 GBM (fit through Sep 2025) + the calibrator built from Oct-Dec 2025; nothing from 2026
  v2_rolling  the same GBM; the calibrator is re-fitted each month on the chosen window of *earlier*
              months, which from February on includes earlier 2026 months (walk-forward)

Everything else follows the H2 2025 backtest (realized / target, theta curve, weekly block bootstrap).

Run:  python -m mcp.holdout        (from src/)
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

from mcp import features as F  # noqa: E402
from mcp.backtest import THETAS, _tag, aggregate, analyse, merge  # noqa: E402
from mcp.calibration import make_calibrator, month_stats  # noqa: E402
from mcp.connections import ROOT, WEIGHTED  # noqa: E402
from mcp.model import _codes, bucket_of, cells, fit_rates  # noqa: E402
from mcp.pricing import load_config  # noqa: E402
from mcp.split import where  # noqa: E402
from mcp.v2 import BUNDLE as V2_BUNDLE  # noqa: E402

MODELS = ("baseline", "v1_raw", "v1_iso", "v2_static", "v2_rolling")
PRODUCT = "v2_rolling"           # decides who is offered and drives the purchase weight (same for every model)
SEVERITY_FULL = ROOT / "data" / "parquet" / "severity" / "severity_full.parquet"
V1_BUNDLE = ROOT / "models" / "pmiss.joblib"
RESULTS = ROOT / "results" / "holdout.json"
FIG = ROOT / "docs" / "figures"
KEYS = ["carrier", "in_flight_date", "in_flight_number", "in_crs_dep_hhmm", "out_flight_date",
        "out_flight_number", "out_crs_dep_hhmm", "origin", "destination"]
LABEL = {"baseline": "baseline 2024", "v1_raw": "v1 raw", "v1_iso": "v1 (as shipped)", "v2_static": "v2 static",
         "v2_rolling": "v2 rolling", "flat_train": "flat, training average", "flat_oracle": "flat, hindsight oracle"}
COL = {"baseline": "#888888", "v1_raw": "#E69F00", "v1_iso": "#D55E00", "v2_static": "#56B4E9",
       "v2_rolling": "#0072B2", "flat_train": "#009E73", "flat_oracle": "#CC79A7"}


def month_path(month: int) -> str:
    return (WEIGHTED / "mct=45" / "year=2026" / f"month={month:02d}.parquet").as_posix()


def predict(bundle: dict, df: pd.DataFrame) -> np.ndarray:
    return bundle["gbm"].predict_proba(_codes(df[bundle["features"]], bundle["cats"]))[:, 1]


def run() -> dict:
    cfg = load_config()
    v1, v2 = joblib.load(V1_BUNDLE), joblib.load(V2_BUNDLE)
    base_rates = pd.DataFrame([(h, int(b), r) for (h, b), r in fit_rates(cells("FIT"), ("hub", "bucket")).items()],
                              columns=["hub", "bucket", "p_baseline"])
    train = pd.read_parquet(F.OUT / "PRICING_TRAIN.parquet", columns=["y", "weight", "overnight"])
    flat_train = float(np.average(train["y"] * (cfg["rebooking_cost"] + cfg["overnight_cost"] * train["overnight"]),
                                  weights=train["weight"]) / cfg["target_loss_ratio"])

    con1, con2 = duckdb.connect(), duckdb.connect()
    F.create_stats(con1)                                                           # v1: route history from 2024
    F.create_stats(con2, fit_flights=where("V2_FIT", "flight_date"), fit_asos=where("V2_FIT", "obs_utc"))
    # The single place the holdout window is read:
    predicate = where("HOLDOUT", "r.out_sched_dep")

    known = list(v2["cal_stats"])                  # Oct-Dec 2025 months, out-of-sample for the v2 GBM
    static_cal = make_calibrator(v2["policy"], v2["k"], known)
    parts, kept, dropped, month_rows = [], 0, 0, {}
    for month in range(1, 9):
        src = f"read_parquet('{month_path(month)}')"
        df = con1.execute(F.feature_sql(src, predicate, 1.0, SEVERITY_FULL.as_posix(), with_keys=True)).fetchdf()
        d2 = con2.execute(F.feature_sql(src, predicate, 1.0, None, with_keys=True)).fetchdf()
        bad = df["overnight"].isna() | df["fare"].isna()
        total = len(df)
        df = df[~bad].copy()
        dropped += int(bad.sum())
        d2["p_v2_raw"] = predict(v2, d2)
        df = df.merge(d2[KEYS + ["p_v2_raw"]], on=KEYS, how="left", validate="one_to_one")
        assert df["p_v2_raw"].notna().all(), "v1 and v2 frames did not match row for row"
        df["bucket"] = bucket_of(df["slack_min"])
        df = df.merge(base_rates, on=["hub", "bucket"], how="left")
        raw1 = predict(v1, df)
        df["p_v1_raw"], df["p_v1_iso"] = raw1, v1["isotonic"].predict(raw1)
        hubs = df["hub"].to_numpy()
        df["p_v2_static"] = static_cal(df["p_v2_raw"].to_numpy(), hubs)
        label = f"2026-{month:02d}"
        df["p_v2_rolling"] = make_calibrator(v2["policy"], v2["k"], known)(df["p_v2_raw"].to_numpy(), hubs)
        day = df["out_sched_dep"].dt.normalize()
        df["week"] = (day - pd.to_timedelta(df["out_sched_dep"].dt.day_of_week, unit="D")).astype(str)
        df["month"] = df["out_sched_dep"].dt.month
        parts.append(aggregate(df, cfg, MODELS, product=PRODUCT, buy=PRODUCT))
        # only now does this month's outcome become 'known' to the rolling policy, for the NEXT month
        known.append(month_stats(label, df["hub"], df["y"], df["weight"], df["p_v2_raw"]))
        kept += len(df)
        print(f"{label}: {len(df):,} connections scored (dropped {int(bad.sum())})", flush=True)
    res = analyse(merge(parts, MODELS), cfg, flat_train, MODELS, PRODUCT)
    res["rows"] = {"scored": kept, "dropped_missing_severity_or_fare": dropped}
    res["v2"] = {"feature_set": v2["feature_set"], "policy": v2["policy"], "k": v2["k"]}
    return res


def figures(res: dict) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.alpha": 0.25, "figure.dpi": 130, "font.size": 10})
    hubs = sorted(res["by_hub"])
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x, width = np.arange(len(hubs)), 0.16
    for i, m in enumerate(MODELS):
        ax.bar(x + (i - 2) * width, [res["by_hub"][h][m]["ratio"] for h in hubs], width, color=COL[m], label=LABEL[m],
               yerr=[[res["by_hub"][h][m]["ratio"] - res["by_hub"][h][m]["lo"] for h in hubs],
                     [res["by_hub"][h][m]["hi"] - res["by_hub"][h][m]["ratio"] for h in hubs]] if m == PRODUCT else None,
               capsize=3)
    ax.axhline(1, color="k", lw=1, ls="--")
    ax.set(xticks=x, xticklabels=hubs, ylabel="Realized ÷ target loss ratio", title="2026 holdout by hub (1.0 = on target)")
    ax.legend(frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.1), fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "holdout_by_hub.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4))
    th = [float(_tag(t)) for t in THETAS]
    series = {**{m: res["overall"][m] for m in ("v1_iso", "v2_static", "v2_rolling")}, **res["flat_pricing"]}
    for name, ser in series.items():
        ax.plot(th, [ser[_tag(t)]["ratio"] for t in THETAS], marker="o", lw=2, color=COL[name], label=LABEL[name])
    ax.axhline(1, color="k", lw=1, ls="--")
    ax.set(xlabel="Adverse selection strength θ (0 = buyers ignore risk)", ylabel="Realized ÷ target loss ratio",
           title="2026: tiered pricing vs flat as buyers self-select")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "holdout_vs_selection.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    mo = sorted(res["by_month"], key=int)
    xs = [int(m) for m in mo]
    ax.plot(xs, [res["by_month"][m]["observed"] * 100 for m in mo], marker="o", color="k", lw=2, label="observed")
    for m in ("v1_iso", "v2_static", "v2_rolling"):
        ax.plot(xs, [res["by_month"][k][f"pred_{m}"] * 100 for k in mo], marker="o", lw=2, color=COL[m], label=LABEL[m])
    ax.set(xlabel="Month of 2026", ylabel="Missed connections (%)", title="Level check: observed vs predicted, 2026")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "holdout_level.png"); plt.close(fig)


def main() -> None:
    res = run()
    RESULTS.write_text(json.dumps(res, indent=2, default=float))
    figures(res)
    print("\nrealized / target at theta=0 (1.0 = on target):")
    for m in MODELS:
        r = res["overall"][m]["0"]
        print(f"  {m:11s} {r['ratio']:.3f} [{r['lo']:.3f}, {r['hi']:.3f}]")


if __name__ == "__main__":
    main()
