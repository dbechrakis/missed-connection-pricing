"""Backtest accounting on synthetic data with answers worked out by hand. The real test window is
never read here: these tests are what stop us tuning on it."""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mcp.backtest import MODELS, THETAS, aggregate, analyse, merge, ratio_with_ci

ROOT = Path(__file__).resolve().parents[1]
CFG = {"rebooking_cost": 100, "overnight_cost": 0, "target_loss_ratio": 0.5, "wtp_cap_pct": 1.0}


def frame(p_groups, rates, n=1000, weeks=("2025-07-07", "2025-07-14")):
    """Equal-weight groups with predicted probability p and an observed miss rate exactly `rate`."""
    rows = []
    for g, (p, rate) in enumerate(zip(p_groups, rates)):
        for wk in weeks:
            y = np.zeros(n)
            y[: int(round(rate * n))] = 1
            rows.append(pd.DataFrame({"y": y, "weight": 1.0, "overnight": 0.0, "fare": 1000.0, "hub": "ATL",
                                      "bucket": g, "week": wk, "month": 7,
                                      **{f"p_{m}": p for m in MODELS}}))
    return pd.concat(rows, ignore_index=True)


def run(df, flat_train=100.0):
    return analyse(merge([aggregate(df, CFG)]), CFG, flat_train)


def test_perfectly_calibrated_tiered_pricing_is_on_target_at_every_theta():
    res = run(frame([0.1, 0.3], [0.1, 0.3]))
    for th in THETAS:
        assert res["overall"]["gbm_iso"][f"{th:g}"]["ratio"] == pytest.approx(1.0, abs=1e-9)


def test_a_model_that_under_predicts_by_half_runs_at_double_the_target():
    res = run(frame([0.05, 0.15], [0.1, 0.3]))
    assert res["overall"]["gbm_iso"]["0"]["ratio"] == pytest.approx(2.0)


def test_flat_oracle_is_on_target_at_theta_zero_and_deteriorates_with_selection_by_hand():
    # two equal groups, p = observed = 0.1 and 0.3. theta=0: avg claim rate 0.2.
    # theta=1: purchase weight p -> avg claim rate (0.1*0.1 + 0.3*0.3)/(0.1+0.3) = 0.25. ratio 0.25/0.2 = 1.25
    res = run(frame([0.1, 0.3], [0.1, 0.3]))
    fo = res["flat_pricing"]["flat_oracle"]
    assert fo["0"]["ratio"] == pytest.approx(1.0)
    assert fo["1"]["ratio"] == pytest.approx(1.25)
    assert fo["2"]["ratio"] > fo["1"]["ratio"] > fo["0.5"]["ratio"] > 1.0     # monotone in theta


def test_flat_oracle_price_is_claims_over_loss_ratio_times_weight():
    res = run(frame([0.1, 0.3], [0.1, 0.3]))
    # average claim cost 0.2 x 100 = 20, divided by target LR 0.5 = 40
    assert res["flat"]["oracle_price"] == pytest.approx(40.0)


def test_flat_train_price_off_level_shows_up_directly():
    res = run(frame([0.1, 0.3], [0.1, 0.3]), flat_train=20.0)       # half the right price
    assert res["flat_pricing"]["flat_train"]["0"]["ratio"] == pytest.approx(2.0)


def test_overnight_claims_raise_cost_and_price_together_so_the_ratio_is_unchanged():
    cfg = {**CFG, "overnight_cost": 300}
    df = frame([0.1, 0.3], [0.1, 0.3]).assign(overnight=lambda d: (d["bucket"] == 0).astype(float))
    res = analyse(merge([aggregate(df, cfg)]), cfg, 100.0)
    assert res["overall"]["gbm_iso"]["0"]["ratio"] == pytest.approx(1.0)


def test_cost_scale_does_not_change_the_headline_ratio():
    df = frame([0.05, 0.15], [0.1, 0.3])
    a = analyse(merge([aggregate(df, CFG)]), CFG, 100.0)["overall"]["gbm_iso"]["0"]["ratio"]
    cfg2 = {**CFG, "rebooking_cost": 999}
    b = analyse(merge([aggregate(df, cfg2)]), cfg2, 100.0)["overall"]["gbm_iso"]["0"]["ratio"]
    assert a == pytest.approx(b)


def test_months_add_up_exactly():
    df = frame([0.1, 0.3], [0.1, 0.3])
    whole = merge([aggregate(df, CFG)])["sums"]["claim0"].sum()
    halves = merge([aggregate(df.iloc[: len(df) // 2], CFG), aggregate(df.iloc[len(df) // 2:], CFG)])["sums"]["claim0"].sum()
    assert whole == pytest.approx(halves)


def test_offer_rule_uses_the_calibrated_price_and_wtp_cap():
    df = frame([0.1, 0.3], [0.1, 0.3])
    cfg = {**CFG, "wtp_cap_pct": 0.05}     # price = p*100/0.5 = 20 or 60; cap 5% x 1000 = 50
    s = aggregate(df, cfg)["sums"]
    assert set(s.loc[s["offered"], "bucket"]) == {0} and set(s.loc[~s["offered"], "bucket"]) == {1}


def test_bootstrap_interval_contains_the_point_and_shrinks_with_more_weeks():
    wk = [f"w{i:02d}" for i in range(20)]
    rng = np.random.default_rng(0)
    sums = pd.DataFrame({"week": wk, "claim": rng.uniform(90, 110, 20), "den": 100.0})
    r = ratio_with_ci(sums, "claim", "den")
    assert r["lo"] <= r["ratio"] <= r["hi"]
    assert r["hi"] - r["lo"] < 0.2


def test_histogram_metrics_match_direct_computation():
    df = frame([0.1, 0.3], [0.12, 0.28])
    res = run(df)
    p, y, w = df["p_gbm_iso"].to_numpy(), df["y"].to_numpy(), df["weight"].to_numpy()
    assert res["scores"]["gbm_iso"]["brier"] == pytest.approx(np.average((y - p) ** 2, weights=w))


# ---- the guard: only this backtest reads the test window --------------------------------------

def test_only_backtest_py_reads_the_test_window_and_only_once():
    reads = {}
    for path in [*(ROOT / "src" / "mcp").glob("*.py"), *(ROOT / "notebooks").glob("*.py")]:
        if path.name == "split.py":
            continue
        n = len(re.findall(r"""where\(\s*["']TEST["']|cells\(\s*["']TEST["']""", path.read_text(encoding="utf-8")))
        if n:
            reads[path.name] = n
    assert reads == {"backtest.py": 1}, reads
