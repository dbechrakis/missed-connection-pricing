"""Baseline P(miss) and the metrics every later model is judged by.

Baseline = weighted miss rate per (hub, slack bucket), fit on FIT (2024) and scored on
VALID (Jan-Jun 2025). TEST is never read here. Spec: Method 5, Validation.

Every metric is passenger-weighted: the weight is the DB1B route weight from
connections.weighted_sql, so a connection on a busy route matters more than a rare pairing.

Run:  python -m mcp.model            (from src/)
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np

from mcp.connections import ROOT, WEIGHTED
from mcp.split import where

BUCKET_MIN = 15      # slack bucket width
N_BUCKETS = 12       # 45..225 in 15-minute steps; the last bucket absorbs slack == 225
EPS = 1e-6           # clip for log loss: a cell with zero observed misses must not give log(0)
RESULTS = ROOT / "results" / "baseline.json"


def cells(window: str, mct: int = 45, hubs: tuple | None = None) -> dict[str, np.ndarray]:
    """Weighted counts per (hub, slack bucket) in one window.

    Returns arrays hub, bucket, W (total weight), Wy (weight of missed), n (rows).
    A cell is all we need for any model whose prediction is constant within it, and the
    metrics below are exact on cells (no row-level data has to leave DuckDB).
    """
    glob = (WEIGHTED / f"mct={mct}" / "*" / "*.parquet").as_posix()
    rows = duckdb.connect().execute(
        f"""
        SELECT hub, least((slack_min - mct_min) // {BUCKET_MIN}, {N_BUCKETS - 1}) AS bucket,
               sum(weight) AS W, sum(weight * missed::INT) AS Wy, count(*) AS n
        FROM read_parquet('{glob}')
        WHERE {where(window)}
        GROUP BY ALL ORDER BY hub, bucket
        """
    ).fetchall()
    return {k: np.array(v) for k, v in zip(["hub", "bucket", "W", "Wy", "n"], zip(*rows))}


def fit_rates(c: dict, by: tuple[str, ...]) -> dict:
    """Weighted miss rate per group of the keys in `by` ('hub', 'bucket'; () = one flat rate)."""
    num, den = {}, {}
    for i in range(len(c["W"])):
        key = tuple(c[k][i] for k in by)
        num[key] = num.get(key, 0.0) + c["Wy"][i]
        den[key] = den.get(key, 0.0) + c["W"][i]
    return {k: num[k] / den[k] for k in num}


def predict(rates: dict, c: dict, by: tuple[str, ...]) -> np.ndarray:
    flat = sum(rates.values()) / len(rates)  # only used for an unseen group; none occur on this data
    return np.array([rates.get(tuple(c[k][i] for k in by), flat) for i in range(len(c["W"]))])


# ---- metrics: exact for predictions that are constant within a cell -------------------------

def brier(W, Wy, p) -> float:
    """Weighted mean squared error of the probability: lower is better, 0 is perfect."""
    return float(np.sum(Wy * (1 - p) ** 2 + (W - Wy) * p**2) / np.sum(W))


def log_loss(W, Wy, p) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.sum(Wy * np.log(p) + (W - Wy) * np.log(1 - p)) / np.sum(W))


def ece(W, Wy, p, bins: int = 10) -> float:
    """Expected calibration error, equal-weight bins by predicted probability.

    Cells are sorted by p and cut into `bins` groups of equal total weight; ECE is the
    weight-averaged |observed rate - mean prediction| over the groups. Equal-frequency bins
    because p lives in [0, 0.3]: equal-width bins would leave most of them empty.
    """
    order = np.argsort(p, kind="stable")
    W, Wy, p = W[order], Wy[order], p[order]
    edges = np.searchsorted(np.cumsum(W) / np.sum(W), np.linspace(0, 1, bins + 1)[1:-1], side="right")
    total, err = np.sum(W), 0.0
    for idx in np.split(np.arange(len(W)), edges):
        if len(idx) == 0:
            continue
        w = W[idx].sum()
        err += w * abs(Wy[idx].sum() / w - np.average(p[idx], weights=W[idx]))
    return float(err / total)


def reliability(W, Wy, p, bins: int = 10) -> list[tuple[float, float, float]]:
    """(mean predicted, observed rate, weight) per equal-weight bin, for the diagram."""
    order = np.argsort(p, kind="stable")
    W, Wy, p = W[order], Wy[order], p[order]
    edges = np.searchsorted(np.cumsum(W) / np.sum(W), np.linspace(0, 1, bins + 1)[1:-1], side="right")
    out = []
    for idx in np.split(np.arange(len(W)), edges):
        if len(idx):
            w = W[idx].sum()
            out.append((float(np.average(p[idx], weights=W[idx])), float(Wy[idx].sum() / w), float(w)))
    return out


def score(c: dict, p: np.ndarray) -> dict:
    return {"brier": brier(c["W"], c["Wy"], p), "log_loss": log_loss(c["W"], c["Wy"], p),
            "ece": ece(c["W"], c["Wy"], p)}


MODELS = {  # name -> grouping keys. Each row adds one idea to the one above it.
    "flat": (),
    "hub only": ("hub",),
    "slack only": ("bucket",),
    "hub x slack (baseline)": ("hub", "bucket"),
}


def run() -> dict:
    fit, valid = cells("FIT"), cells("VALID")
    out = {"fit_rows": int(fit["n"].sum()), "valid_rows": int(valid["n"].sum()),
           "fit_miss_rate": float(fit["Wy"].sum() / fit["W"].sum()),
           "valid_miss_rate": float(valid["Wy"].sum() / valid["W"].sum()), "models": {}}
    flat_brier = None
    for name, by in MODELS.items():
        rates = fit_rates(fit, by)
        res = score(valid, predict(rates, valid, by))
        flat_brier = flat_brier if flat_brier is not None else res["brier"]
        res["brier_skill_vs_flat"] = 1 - res["brier"] / flat_brier
        out["models"][name] = res
    rates = fit_rates(fit, ("hub", "bucket"))
    out["baseline_rates"] = {f"{h}|{int(b)}": r for (h, b), r in sorted(rates.items())}
    return out


def baseline_main() -> None:
    res = run()
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(res, indent=2))
    print(f"fit miss rate {res['fit_miss_rate']:.2%}   valid miss rate {res['valid_miss_rate']:.2%}")
    print(f"{'model':26s} {'brier':>9s} {'logloss':>9s} {'ECE':>8s} {'skill':>7s}")
    for name, m in res["models"].items():
        print(f"{name:26s} {m['brier']:9.5f} {m['log_loss']:9.5f} {m['ece']:8.5f} {m['brier_skill_vs_flat']:7.1%}")


# =============================================================================================
# Step 5: logistic regression, gradient boosting, isotonic calibration
# =============================================================================================
import sys  # noqa: E402

import joblib  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

from mcp import features as F  # noqa: E402

MODELS_DIR = ROOT / "models"
RESULTS_MODELS = ROOT / "results" / "models.json"
CALIB_SPLIT = "2025-05-16"  # splits VALID2 into an isotonic-fit half and an honest evaluation half


def load(name: str, rows: int | None = None) -> pd.DataFrame:
    df = pd.read_parquet(F.OUT / f"{name}.parquet")
    return df.sample(n=rows, random_state=0) if rows and rows < len(df) else df


def rowscore(y, w, p) -> dict:
    """Weighted Brier / log loss / ECE from rows (the cell formulas with one row per cell)."""
    y, w, p = np.asarray(y, float), np.asarray(w, float), np.asarray(p, float)
    return {"brier": brier(w, w * y, p), "log_loss": log_loss(w, w * y, p), "ece": ece(w, w * y, p),
            "mean_pred": float(np.average(p, weights=w)), "observed": float(np.average(y, weights=w))}


def norm(w):
    """Passenger weights rescaled to mean 1: only relative size matters, and a sane scale keeps
    the regulariser's strength meaningful."""
    w = np.asarray(w, float)
    return w / w.mean()


def bucket_of(slack) -> np.ndarray:
    return np.minimum((np.asarray(slack) - 45) // BUCKET_MIN, N_BUCKETS - 1)


def baseline_rows(df: pd.DataFrame, rates: dict) -> np.ndarray:
    flat = float(np.mean(list(rates.values())))
    return np.array([rates.get((h, b), flat) for h, b in zip(df["hub"], bucket_of(df["slack_min"]))])


def fit_logistic(df: pd.DataFrame, use=F.FEATURES):
    """Logistic regression: one-hots for schedule categories, scaled numerics for the rest.
    The interpretable benchmark the boosting model has to beat."""
    cat = [c for c in ["hub", "carrier", "out_hour", "out_dow", "month"] if c in use]
    num = [c for c in use if c not in cat and c != "slack_min"] + ["slack_min"]

    def design(x):
        return x.assign(slack_bucket=bucket_of(x["slack_min"]))[cat + ["slack_bucket"] + num]

    pre = ColumnTransformer([("c", OneHotEncoder(handle_unknown="ignore"), cat + ["slack_bucket"]),
                             ("n", StandardScaler(), num)])
    m = make_pipeline(pre, LogisticRegression(C=1.0, max_iter=400))
    m.fit(design(df), df["y"], logisticregression__sample_weight=norm(df["weight"]))
    return lambda x: m.predict_proba(design(x))[:, 1]


def _codes(df, cats):
    out = df.copy()
    for c, levels in cats.items():
        out[c] = out[c].map({lvl: i for i, lvl in enumerate(levels)}).fillna(-1).astype("int16")
    return out


def fit_gbm(df: pd.DataFrame, use=F.FEATURES, leaves=31, seed=0):
    """Histogram gradient boosting, early stopping on a random 10% of FIT.
    Categoricals are integer codes learned on FIT; an unseen level becomes 'missing' (-1)."""
    use = list(use)
    cats = {c: sorted(df[c].unique()) for c in F.CATEGORICAL if c in use}
    m = HistGradientBoostingClassifier(
        max_leaf_nodes=leaves, learning_rate=0.1, max_iter=400, min_samples_leaf=500,
        l2_regularization=1.0, categorical_features=[c in cats for c in use], early_stopping=True,
        validation_fraction=0.1, n_iter_no_change=15, random_state=seed)
    m.fit(_codes(df[use], cats), df["y"], sample_weight=norm(df["weight"]))

    def predict(x):
        return m.predict_proba(_codes(x[use], cats))[:, 1]

    predict.n_iter, predict.model, predict.cats, predict.use = m.n_iter_, m, cats, use
    return predict


def calibrate(p_fit, y, w, p_eval, y_eval, w_eval) -> dict:
    """Isotonic regression fit on one half of VALID2, scored on the later half."""
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(p_fit, y, sample_weight=norm(w))
    return {"before": rowscore(y_eval, w_eval, p_eval), "after": rowscore(y_eval, w_eval, iso.predict(p_eval))}


def _fmt(d) -> str:
    return (f"brier {d['brier']:.5f}  logloss {d['log_loss']:.5f}  ECE {d['ece']:.5f}  "
            f"pred {d['mean_pred']:.4f} obs {d['observed']:.4f}")


def models_main() -> None:
    fit, v1, v2 = load("FIT"), load("VALID1"), load("VALID2")
    base_rates = fit_rates(cells("FIT"), ("hub", "bucket"))
    out: dict = {"rows": {"FIT": len(fit), "VALID1": len(v1), "VALID2": len(v2)}}

    # ---- model selection on VALID1 --------------------------------------------------------
    sel = {"baseline hub x slack": rowscore(v1["y"], v1["weight"], baseline_rows(v1, base_rates))}
    print("fitting logistic ...", flush=True)
    lr = fit_logistic(fit)
    sel["logistic"] = rowscore(v1["y"], v1["weight"], lr(v1))
    gbms = {}
    for leaves in (15, 63):
        print(f"fitting GBM leaves={leaves} ...", flush=True)
        g = fit_gbm(fit, leaves=leaves)
        gbms[leaves] = g
        sel[f"gbm leaves={leaves}"] = rowscore(v1["y"], v1["weight"], g(v1))
        sel[f"gbm leaves={leaves}"]["trees"] = int(g.n_iter)
    best = min(gbms, key=lambda k: sel[f"gbm leaves={k}"]["brier"])
    out["selection_valid1"], out["best_leaves"] = sel, int(best)
    gbm = gbms[best]

    # ---- ablations on VALID1 (1.5M-row sample of FIT so each fit is quick and comparable) --
    small = fit.sample(n=1_500_000, random_state=1)
    groups = {"all features": F.FEATURES,
              "no route history": [f for f in F.FEATURES if f not in F.ROUTE_HISTORY],
              "no climatology": [f for f in F.FEATURES if f not in F.CLIMATOLOGY],
              "schedule only": F.CATEGORICAL + F.SCHEDULE,
              "hub + slack only": ["hub", "slack_min"]}
    abl = {}
    for name, use in groups.items():
        print(f"ablation: {name} ...", flush=True)
        abl[name] = rowscore(v1["y"], v1["weight"], fit_gbm(small, use=use, leaves=best)(v1))
    out["ablation_valid1"] = abl

    # ---- calibration on VALID2: isotonic fit Apr 1 - May 15, scored May 16 - Jun 30 --------
    p2 = gbm(v2)
    first = (v2["out_sched_dep"] < CALIB_SPLIT).to_numpy()
    y2, w2 = v2["y"].to_numpy(), v2["weight"].to_numpy()
    out["calibration_valid2_second_half"] = {
        "gbm": calibrate(p2[first], y2[first], w2[first], p2[~first], y2[~first], w2[~first]),
        "baseline": rowscore(y2[~first], w2[~first], baseline_rows(v2[~first], base_rates)),
        "logistic": rowscore(y2[~first], w2[~first], lr(v2[~first])),
    }
    out["drift"] = {"FIT_observed": float(np.average(fit["y"], weights=fit["weight"])),
                    "VALID1": {"observed": sel["baseline hub x slack"]["observed"],
                               "gbm_pred": float(np.average(gbm(v1), weights=v1["weight"]))},
                    "VALID2": {"observed": float(np.average(y2, weights=w2)),
                               "gbm_pred": float(np.average(p2, weights=w2))}}

    # ---- final calibrator on all of VALID2, then save -------------------------------------
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(p2, y2, sample_weight=norm(w2))
    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump({"gbm": gbm.model, "cats": gbm.cats, "features": gbm.use, "isotonic": iso, "leaves": int(best)},
                MODELS_DIR / "pmiss.joblib")
    RESULTS_MODELS.write_text(json.dumps(out, indent=2))

    print("\n== VALID1 (Jan-Mar 2025, model selection) ==")
    for k, v in sel.items():
        print(f"{k:24s} {_fmt(v)}")
    print("\n== ablations on VALID1 (GBM, 1.5M fit rows) ==")
    for k, v in abl.items():
        print(f"{k:24s} {_fmt(v)}")
    c = out["calibration_valid2_second_half"]
    print("\n== VALID2 second half (May 16 - Jun 30): calibration ==")
    for k, v in (("baseline", c["baseline"]), ("logistic", c["logistic"]),
                 ("gbm raw", c["gbm"]["before"]), ("gbm + isotonic", c["gbm"]["after"])):
        print(f"{k:24s} {_fmt(v)}")
    print("\ndrift:", json.dumps(out["drift"], indent=1))


# ---------------------------------------------------------------------------------------------
# Final model: choose the feature set on VALID1, refit on FIT + VALID1, calibrate on VALID2
# ---------------------------------------------------------------------------------------------
FINAL_RESULTS = ROOT / "results" / "final_model.json"


def final_main() -> None:
    fit, v1, v2 = load("FIT"), load("VALID1"), load("VALID2")
    base_rates = fit_rates(cells("FIT"), ("hub", "bucket"))
    leaves = json.loads(RESULTS_MODELS.read_text())["best_leaves"]
    S, H, R = F.SCHEDULE, F.CATEGORICAL, F.ROUTE_HISTORY
    candidates = {
        "hub + slack": ["hub", "slack_min"],
        "hub + slack + route history": ["hub", "slack_min"] + R,
        "hub + slack + hour + weekday": ["hub", "slack_min", "out_hour", "out_dow"],
        "hub + carrier + slack + hour + weekday + arrival hour": H + ["slack_min", "out_hour", "out_dow", "in_arr_hour"],
        "no month (all else)": [f for f in F.FEATURES if f not in ("month",) + tuple(F.CLIMATOLOGY)],
        "all features": F.FEATURES,
    }
    # ---- 1. choose on VALID1, fits on the same 1.5M FIT sample for a like-for-like comparison
    small = fit.sample(n=1_500_000, random_state=1)
    scores = {}
    for name, use in candidates.items():
        print(f"candidate: {name} ...", flush=True)
        scores[name] = rowscore(v1["y"], v1["weight"], fit_gbm(small, use=use, leaves=leaves)(v1))
    ref = rowscore(v1["y"], v1["weight"], baseline_rows(v1, base_rates))
    chosen = min(scores, key=lambda k: scores[k]["brier"])
    use = candidates[chosen]

    # ---- 2. refit on FIT + VALID1 (2024 through March 2025), isotonic on VALID2 first half
    train = pd.concat([fit, v1], ignore_index=True)
    print(f"refit '{chosen}' on {len(train):,} rows (FIT + VALID1) ...", flush=True)
    gbm_all = fit_gbm(train, use=use, leaves=leaves)
    gbm_fit = fit_gbm(fit, use=use, leaves=leaves)
    first = (v2["out_sched_dep"] < CALIB_SPLIT).to_numpy()
    y2, w2 = v2["y"].to_numpy(), v2["weight"].to_numpy()
    second = {}
    for label, g in (("fit only", gbm_fit), ("fit + valid1", gbm_all)):
        p2 = g(v2)
        c = calibrate(p2[first], y2[first], w2[first], p2[~first], y2[~first], w2[~first])
        second[label] = {"raw": c["before"], "isotonic": c["after"]}
    second["baseline"] = rowscore(y2[~first], w2[~first], baseline_rows(v2[~first], base_rates))

    # ---- 3. final calibrator on all of VALID2 for the model fit through March 2025
    p2_all = gbm_all(v2)
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(p2_all, y2, sample_weight=norm(w2))
    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump({"gbm": gbm_all.model, "cats": gbm_all.cats, "features": gbm_all.use, "isotonic": iso,
                 "leaves": int(leaves), "chosen": chosen}, MODELS_DIR / "pmiss.joblib")
    out = {"valid1_reference_baseline": ref, "valid1_candidates": scores, "chosen": chosen,
           "valid2_second_half": second}
    FINAL_RESULTS.write_text(json.dumps(out, indent=2))

    print("\n== VALID1 candidates (GBM, 1.5M fit rows) ==")
    print(f"{'baseline hub x slack':56s} {_fmt(ref)}")
    for k, v in scores.items():
        print(f"{k:56s} {_fmt(v)}{'   <- chosen' if k == chosen else ''}")
    print("\n== VALID2 second half (May 16 - Jun 30) ==")
    print(f"{'baseline':36s} {_fmt(second['baseline'])}")
    for label in ("fit only", "fit + valid1"):
        print(f"{'gbm ' + label + ', raw':36s} {_fmt(second[label]['raw'])}")
        print(f"{'gbm ' + label + ' + isotonic':36s} {_fmt(second[label]['isotonic'])}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    {"baseline": baseline_main, "models": models_main, "final": final_main}[mode]()
