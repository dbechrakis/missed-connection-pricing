"""The audit's arithmetic, on toy tables with known answers."""
import numpy as np
import pandas as pd
import pytest

from mcp.v3_audit import by_hub, offered, ratio, stop_loss_cost, weekly_loss_ratio


def toy():
    return pd.DataFrame({
        "hub": ["ATL", "ATL", "ORD", "ORD"], "week": ["w1", "w1", "w2", "w2"], "ym": ["m1"] * 4,
        "weight": [1.0, 1.0, 2.0, 1.0], "fare": [300.0, 300.0, 400.0, 400.0], "claim_cost": [200.0, 200.0, 250.0, 250.0],
        "p": [0.05, 0.20, 0.10, 0.10], "y_gap": [0, 1, 1, 0]})


def test_ratio_is_realized_over_expected_payout_cost_weighted():
    # claims: 200*1 (ATL row 2) + 250*2 (ORD row 1) = 700; expected: 10 + 40 + 50 + 25 = 125 x 1 ... computed below
    exp = 1 * 0.05 * 200 + 1 * 0.20 * 200 + 2 * 0.10 * 250 + 1 * 0.10 * 250
    assert ratio(toy()) == pytest.approx((200 + 500) / exp)
    assert ratio(toy()[toy()["hub"] == "ATL"]) == pytest.approx(200 / (10 + 40))


def test_offered_applies_the_cap_to_premium_and_the_loss_ratio_moves_it():
    d = toy()
    # premium = p * cost / lr: 0.05*200/0.65 = 15.4 (5.1% of 300), 0.20*200/0.65 = 61.5, 0.10*250/0.65 = 38.5 (9.6% of 400)
    assert offered(d, 0.10).tolist() == [True, False, True, True]
    assert offered(d, 0.05).tolist() == [False, False, False, False]
    assert offered(d, 0.05, loss_ratio=0.75).tolist() == [True, False, False, False]      # a higher loss ratio means a cheaper price


def test_weekly_loss_ratio_is_claims_over_premium_per_week():
    lr = weekly_loss_ratio(toy())
    assert lr["w1"] == pytest.approx(200 / ((10 + 40) / 0.65))
    assert lr["w2"] == pytest.approx(500 / ((50 + 25) / 0.65))


def test_stop_loss_cost_is_the_average_excess_over_the_attachment():
    lr = pd.Series([0.5, 0.9, 1.3, 1.1])
    assert stop_loss_cost(lr, 1.0) == pytest.approx((0 + 0 + 0.3 + 0.1) / 4)
    assert stop_loss_cost(lr, 2.0) == 0.0


def test_by_hub_splits_by_hub():
    r = by_hub(toy(), ratio)
    assert set(r) == {"ATL", "ORD"} and r["ATL"] == pytest.approx(4.0)
