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


def test_model_slack_expresses_the_gap_above_the_minimum_on_the_scale_the_model_was_built_on():
    from mcp.v3 import TRAINED_MCT, VALIDATED_MCT, model_slack
    assert TRAINED_MCT == 45 and VALIDATED_MCT == (35, 60)
    assert model_slack(70, 60) == 55                      # a 10-minute buffer is what the model knows as a 55-minute gap
    assert model_slack(45, 45) == 45                      # the trained minimum changes nothing
    assert model_slack(50, 35) == 60                      # a shorter minimum makes the same gap safer
    assert model_slack([60, 90], 45).tolist() == [60, 90]


def test_rolling_analysis_functions_on_a_toy_series():
    import numpy as np
    import pandas as pd
    from mcp.v3_rolling import block_bootstrap_mean, monthly, weeks_to_learn, weekly
    w = pd.DataFrame({"ym": ["m1", "m1", "m2", "m2"], "week": ["a", "b", "c", "d"], "hub": ["ATL"] * 4, "sold": [True, False, True, True],
                      "claims": [10.0, 5.0, 30.0, 10.0], "expected": [8.0, 5.0, 20.0, 10.0], "premium": [10.0, 8.0, 20.0, 10.0], "w": [1.0] * 4})
    m = monthly(w, sold_only=False)
    assert m.loc["m1", "ratio"] == pytest.approx(15 / 13) and m.loc["m2", "loss_ratio"] == pytest.approx(40 / 30)
    assert monthly(w, sold_only=True).loc["m1", "ratio"] == pytest.approx(10 / 8)               # only the sold row
    assert weekly(w, sold_only=True).to_dict() == {"a": 1.0, "c": 1.5, "d": 1.0}
    lo, hi = block_bootstrap_mean(np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0]), block=2)
    assert lo == hi == 1.0                                                                       # no variation, no interval
    L = weeks_to_learn(pd.Series([0.5, 1.0, 0.5, 1.0, 0.5, 1.0, 0.5, 1.0]))
    assert L["mean"] == pytest.approx(0.75) and L["weeks"] >= L["weeks_independent"] > 0


def test_rolling_report_has_hub_and_year_splits(tmp_path, monkeypatch):
    import pandas as pd
    from mcp import v3_rolling as R
    w = pd.DataFrame({"ym": ["2025-01", "2025-01", "2026-01", "2026-01"], "week": ["a", "a", "b", "b"], "hub": ["ATL", "ORD", "ATL", "ORD"],
                      "sold": [True, True, True, True], "claims": [10.0, 30.0, 10.0, 10.0], "expected": [10.0, 20.0, 10.0, 20.0],
                      "premium": [15.0, 30.0, 15.0, 30.0], "w": [1.0] * 4})
    path = tmp_path / "w.csv"; w.to_csv(path, index=False)
    monkeypatch.setattr(R, "OUT", path); monkeypatch.setattr(R, "RESULTS", tmp_path / "r.json")
    r = R.report()
    assert r["by_hub_year_ratio"]["ORD"] == {"2025": pytest.approx(1.5), "2026": pytest.approx(0.5)}
    assert r["by_hub_pooled_ratio"]["ATL"] == pytest.approx(1.0) and r["by_hub_months_above_1"]["ORD"] == 1
