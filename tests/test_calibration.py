"""Calibration policies: hand-computed factors, and the property that matters, that they only use the months given."""
import numpy as np
import pytest

from mcp.calibration import make_calibrator, month_stats, window


def stats(month, hubs, y, w, p):
    return month_stats(month, hubs, y, w, p)


def test_level_global_factor_by_hand():
    # observed rate 0.2, predicted mean 0.1 -> factor 2
    s = stats("2025-04", ["A"] * 4, [1, 0, 0, 0], [1, 1, 1, 1], [0.1] * 4)   # observed 0.25
    s2 = stats("2025-05", ["A"] * 4, [0, 0, 0, 0], [1, 1, 1, 1], [0.1] * 4)  # observed 0.0
    f = make_calibrator("level_global", 2, [s, s2])                            # observed 0.125 / 0.1
    assert f(np.array([0.1]), ["A"])[0] == pytest.approx(0.125)


def test_level_hub_uses_each_hubs_own_factor_and_falls_back_for_an_unseen_hub():
    s = stats("2025-04", ["A", "A", "B", "B"], [1, 1, 0, 0], [1, 1, 1, 1], [0.25] * 4)
    f = make_calibrator("level_hub", 1, [s])
    out = f(np.array([0.1, 0.1, 0.1]), ["A", "B", "C"])
    assert out[0] == pytest.approx(0.1 * 4.0)        # hub A: observed 1.0 / predicted 0.25
    assert out[1] == pytest.approx(0.0)              # hub B: observed 0
    assert out[2] == pytest.approx(0.1 * 2.0)        # unseen hub C: global factor 0.5/0.25


def test_calibrated_probability_stays_within_zero_and_one():
    s = stats("2025-04", ["A"] * 2, [1, 1], [1, 1], [0.01, 0.01])
    assert make_calibrator("level_global", 1, [s])(np.array([0.9]), ["A"])[0] == 1.0


def test_window_keeps_only_the_last_k_months():
    ms = [stats(f"2025-0{m}", ["A"], [1], [1], [0.5]) for m in range(4, 9)]
    assert [s.month for s in window(ms, 3)] == ["2025-06", "2025-07", "2025-08"]
    assert len(window(ms, 99)) == 5 and window([], 3) == []


def test_policy_uses_only_the_months_it_is_given_no_look_ahead():
    # April is bad (observed 1.0), May is good (observed 0.0). A policy handed only April must
    # scale up; handed only May it must scale to zero. Nothing else can leak in.
    apr = stats("2025-04", ["A"] * 2, [1, 1], [1, 1], [0.5, 0.5])
    may = stats("2025-05", ["A"] * 2, [0, 0], [1, 1], [0.5, 0.5])
    assert make_calibrator("level_global", 1, [apr])(np.array([0.4]), ["A"])[0] == pytest.approx(0.8)
    assert make_calibrator("level_global", 1, [may])(np.array([0.4]), ["A"])[0] == pytest.approx(0.0)
    # k=1 over [apr, may] picks the later one only
    assert make_calibrator("level_global", 1, [apr, may])(np.array([0.4]), ["A"])[0] == pytest.approx(0.0)
    assert make_calibrator("level_global", 2, [apr, may])(np.array([0.4]), ["A"])[0] == pytest.approx(0.4)


def test_none_and_empty_history_are_the_identity():
    p = np.array([0.1, 0.3])
    assert make_calibrator("none", 3, [])(p, ["A", "A"]).tolist() == p.tolist()
    assert make_calibrator("iso_global", 3, [])(p, ["A", "A"]).tolist() == p.tolist()


def test_isotonic_is_monotone_and_recovers_a_calibrated_model():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.02, 0.4, 200_000)
    y = (rng.random(p.size) < p).astype(float)
    f = make_calibrator("iso_global", 1, [stats("2025-04", ["A"] * p.size, y, np.ones(p.size), p)])
    grid = np.linspace(0.03, 0.38, 50)
    out = f(grid, ["A"] * 50)
    assert (np.diff(out) >= -1e-12).all()
    assert np.abs(out - grid).max() < 0.03          # already calibrated, so it should change little


def test_isotonic_fixes_a_level_shift():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.05, 0.2, 100_000)
    y = (rng.random(p.size) < p * 1.5).astype(float)          # reality is 50% riskier than the model says
    f = make_calibrator("iso_global", 1, [stats("2025-04", ["A"] * p.size, y, np.ones(p.size), p)])
    assert f(np.array([0.1]), ["A"])[0] == pytest.approx(0.15, abs=0.01)
