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


if __name__ == "__main__":
    res = run()
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(res, indent=2))
    print(f"fit miss rate {res['fit_miss_rate']:.2%}   valid miss rate {res['valid_miss_rate']:.2%}")
    print(f"{'model':26s} {'brier':>9s} {'logloss':>9s} {'ECE':>8s} {'skill':>7s}")
    for name, m in res["models"].items():
        print(f"{name:26s} {m['brier']:9.5f} {m['log_loss']:9.5f} {m['ece']:8.5f} {m['brier_skill_vs_flat']:7.1%}")
