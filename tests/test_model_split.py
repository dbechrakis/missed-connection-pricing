"""Split windows, metric maths (checked against hand calculations) and a test-window guard."""
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from mcp.model import brier, ece, fit_rates, log_loss, predict
from mcp.split import WINDOWS, where

ROOT = Path(__file__).resolve().parents[1]


# ---- split ------------------------------------------------------------------------------

def d(s):
    return datetime.fromisoformat(s)


def test_windows_are_chronological_and_disjoint():
    f, v, t, te = (WINDOWS[k] for k in ("FIT", "VALID", "TRAIN", "TEST"))
    assert f[1] == v[0] and v[1] == te[0]            # contiguous, no gap, no overlap
    v1, v2 = WINDOWS["VALID1"], WINDOWS["VALID2"]
    assert v1[0] == v[0] and v1[1] == v2[0] and v2[1] == v[1]   # VALID = VALID1 then VALID2
    assert t == (f[0], v[1])                         # TRAIN is exactly FIT + VALID
    assert d(f[0]) < d(f[1]) < d(v[1]) < d(te[1])    # strictly increasing in time


def test_test_window_is_h2_2025():
    assert WINDOWS["TEST"] == ("2025-07-01", "2026-01-01")


def test_where_is_half_open():
    sql = where("FIT", "t")
    assert ">= TIMESTAMP '2024-01-01'" in sql and "< TIMESTAMP '2025-01-01'" in sql


def test_exploration_and_model_code_never_read_the_test_window():
    # Spec: "no feature reads ... stats from the test". The backtest (step 18) is the only
    # code allowed to touch TEST; until it exists, nothing may reference it.
    for path in [*(ROOT / "src" / "mcp").glob("*.py"), *(ROOT / "notebooks").glob("*.py")]:
        if path.name == "split.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"""where\(\s*["']TEST["']|cells\(\s*["']TEST["']""", text), path.name


# ---- metrics ----------------------------------------------------------------------------

W = np.array([100.0, 100.0])
Wy = np.array([10.0, 50.0])  # observed rates 10% and 50%


def test_brier_matches_hand_calculation():
    # cell 1, p=0.1: 10*(0.9)^2 + 90*(0.1)^2 = 8.1 + 0.9 = 9.0
    # cell 2, p=0.5: 50*(0.5)^2 + 50*(0.5)^2 = 25.0       -> 34 / 200 = 0.17
    assert brier(W, Wy, np.array([0.1, 0.5])) == pytest.approx(0.17)


def test_brier_of_certain_correct_prediction_is_zero():
    assert brier(np.array([5.0, 5.0]), np.array([5.0, 0.0]), np.array([1.0, 0.0])) == pytest.approx(0.0)


def test_log_loss_matches_hand_calculation():
    # cell 1: -(10 ln .1 + 90 ln .9) = 23.026 + 9.482 = 32.508 ; cell 2: -(100 ln .5) = 69.315
    assert log_loss(W, Wy, np.array([0.1, 0.5])) == pytest.approx((32.508 + 69.315) / 200, abs=1e-3)


def test_log_loss_finite_when_cell_has_no_misses():
    assert np.isfinite(log_loss(np.array([10.0]), np.array([0.0]), np.array([0.0])))


def test_ece_zero_when_calibrated_and_positive_when_not():
    p_ok = np.array([0.1, 0.5])
    assert ece(W, Wy, p_ok, bins=2) == pytest.approx(0.0)
    # predicting 0.3 and 0.3 is off by 0.2 in each bin -> ECE 0.2
    assert ece(W, Wy, np.array([0.3, 0.3]), bins=2) == pytest.approx(0.2)


def test_ece_is_weight_aware():
    # a tiny, badly calibrated cell barely moves a weighted ECE
    Wt, Wyt = np.array([1000.0, 1.0]), np.array([100.0, 1.0])
    assert ece(Wt, Wyt, np.array([0.1, 0.0]), bins=2) < 0.001


def test_fit_rates_is_weighted_not_a_mean_of_rates():
    c = {"hub": np.array(["A", "A"]), "bucket": np.array([0, 1]),
         "W": np.array([90.0, 10.0]), "Wy": np.array([9.0, 5.0])}
    # mean of cell rates would be (0.1 + 0.5)/2 = 0.3; the weighted rate is 14/100
    assert fit_rates(c, ("hub",))[("A",)] == pytest.approx(0.14)
    assert fit_rates(c, ())[()] == pytest.approx(0.14)


def test_predict_maps_each_cell_to_its_group_rate():
    c = {"hub": np.array(["A", "B"]), "bucket": np.array([0, 0]),
         "W": np.array([1.0, 1.0]), "Wy": np.array([0.2, 0.4])}
    rates = fit_rates(c, ("hub", "bucket"))
    assert list(predict(rates, c, ("hub", "bucket"))) == pytest.approx([0.2, 0.4])
