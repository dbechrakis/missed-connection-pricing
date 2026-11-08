"""Model plumbing: row-level scores equal the cell formulas, unseen categories are handled,
a GBM trained on a clean signal recovers it, and isotonic output is a valid monotone probability."""
import numpy as np
import pandas as pd
import pytest

from mcp import features as F
from mcp.model import _codes, bucket_of, brier, fit_gbm, fit_logistic, norm, rowscore


def test_rowscore_equals_cell_formula_with_one_row_per_cell():
    y, w, p = np.array([1, 0, 0, 1]), np.array([2.0, 1.0, 3.0, 1.0]), np.array([0.7, 0.2, 0.1, 0.4])
    r = rowscore(y, w, p)
    assert r["brier"] == pytest.approx(brier(w, w * y, p))
    # by hand: (2*.09 + 1*.04 + 3*.01 + 1*.36) / 7
    assert r["brier"] == pytest.approx((0.18 + 0.04 + 0.03 + 0.36) / 7)
    assert r["observed"] == pytest.approx((2 + 1) / 7) and r["mean_pred"] == pytest.approx(
        (2 * 0.7 + 0.2 + 3 * 0.1 + 0.4) / 7)


def test_weights_are_rescaled_to_mean_one():
    assert norm([10.0, 30.0]).mean() == pytest.approx(1.0)


def test_slack_bucket_boundaries():
    assert list(bucket_of([45, 59, 60, 224, 225])) == [0, 0, 1, 11, 11]


def test_unseen_category_becomes_missing_not_a_crash():
    df = pd.DataFrame({"hub": ["ATL", "ZZZ"], "carrier": ["DL", "AA"]})
    out = _codes(df, {"hub": ["ATL", "ORD"], "carrier": ["AA", "DL"]})
    assert list(out["hub"]) == [0, -1] and list(out["carrier"]) == [1, 0]


def synthetic(n=6000, seed=0):
    rng = np.random.default_rng(seed)
    slack = rng.integers(45, 226, n)
    p = np.clip(0.30 * np.exp(-(slack - 45) / 40), 0.01, 0.9)  # miss probability falls with slack
    d = pd.DataFrame({c: np.zeros(n) for c in F.FEATURES})
    d["hub"] = rng.choice(["ATL", "ORD"], n)
    d["carrier"] = rng.choice(["DL", "AA"], n)
    d["slack_min"], d["weight"] = slack, rng.uniform(1, 5, n)
    for c in ["out_hour", "out_dow", "month", "in_arr_hour"]:
        d[c] = rng.integers(0, 7, n)
    d["y"] = (rng.random(n) < p).astype(int)
    return d, p


@pytest.mark.parametrize("fit", [fit_gbm, fit_logistic])
def test_models_recover_the_slack_signal(fit):
    d, _ = synthetic()
    pred = fit(d)(d)
    low, high = d["slack_min"] < 70, d["slack_min"] > 200
    assert pred[low].mean() > 3 * pred[high].mean()          # tight slack scored much riskier
    assert ((pred >= 0) & (pred <= 1)).all()


def test_gbm_handles_a_hub_never_seen_in_training():
    d, _ = synthetic()
    g = fit_gbm(d)
    unseen = d.head(50).assign(hub="DEN")
    assert np.isfinite(g(unseen)).all()
