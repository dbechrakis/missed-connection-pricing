"""The v3 pre-registered test: its two arms and its arithmetic, on a toy table with known answers."""
import numpy as np
import pandas as pd
import pytest

from mcp.holdout_v3 import arms, summarise
from mcp.v3 import TARGET_LR, price


def toy():
    # two hubs, two weeks; ATL claims exactly what was expected, ORD twice as much; one row has no overnight (cost 0)
    return pd.DataFrame({
        "week": ["w1", "w1", "w2", "w2", "w2"], "month": ["2026-09"] * 5, "hub": ["ATL", "ATL", "ORD", "ORD", "ORD"],
        "weight": [1.0, 1.0, 1.0, 1.0, 1.0], "fare": [400.0] * 5,
        "y_gap": [1, 0, 1, 0, 1], "claim_cost": [200.0, 200.0, 200.0, 200.0, 0.0],
        "p_primary": [0.5, 0.5, 0.25, 0.25, 0.9]})


def test_arms_are_the_frozen_pick_and_the_declared_hub_level():
    assert arms({"policy": "none", "k": 0}) == {"primary": ("none", 0), "hub_level": ("level_hub", 6)}


def test_realized_over_target_is_claims_over_expected_claims_cost_weighted():
    r = summarise(toy(), "primary")
    # claims 200 + 200 = 400 (the cost-0 row pays nothing); expected 200 + 100 = 300
    assert r["overall"]["ratio"] == pytest.approx(400 / 300)
    assert r["by_hub"]["ATL"]["ratio"] == pytest.approx(1.0)
    assert r["by_hub"]["ORD"]["ratio"] == pytest.approx(2.0)
    assert r["monthly"]["2026-09"] == pytest.approx(400 / 300)


def test_price_is_expected_payout_over_target_loss_ratio_and_the_cap_filters_on_it():
    assert price([0.5], [200.0])[0] == pytest.approx(100 / TARGET_LR)
    r = summarise(toy(), "primary")
    # prices: ATL 153.8 (38% of fare), ORD 76.9 (19%): above every cap, so nothing is offered
    assert all(v["share_of_overnight_offered"] == 0 for v in r["offered_within_cap"].values())
    cheap = toy().assign(p_primary=[0.05, 0.05, 0.05, 0.05, 0.05])   # price 15.4 = 3.8% of fare: within 5% and 7%, not 3%
    off = summarise(cheap, "primary")["offered_within_cap"]
    assert off["0.03"]["share_of_overnight_offered"] == 0
    assert off["0.05"]["share_of_overnight_offered"] == pytest.approx(1.0)
    assert np.isnan(off["0.03"]["realized_over_target"]["ratio"])
