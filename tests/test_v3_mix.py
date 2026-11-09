"""The itinerary-mix sensitivity: the weights, and that a different mix changes the numbers it should."""
import numpy as np
import pandas as pd
import pytest

from mcp.v3_mix import SCENARIOS, mix_factor, reweight, summarise


def test_mix_factors_are_the_stated_functions_of_the_buffer():
    b = np.array([0.0, 30.0, 60.0])
    assert mix_factor(b, "equal").tolist() == [1.0, 1.0, 1.0]
    assert mix_factor(b, "prefer_short_60") == pytest.approx(np.exp(-b / 60))
    assert mix_factor(b, "prefer_short_30") == pytest.approx(np.exp(-b / 30))
    assert mix_factor(b, "prefer_long_60") == pytest.approx(np.exp(b / 60))
    assert mix_factor(np.array([0.0, 14.0, 15.0]), "avoid_minimum").tolist() == [0.5, 0.5, 1.0]
    with pytest.raises(ValueError):
        mix_factor(b, "nonsense")


def month(seed):
    rng = np.random.default_rng(seed)
    n = 4000
    slack = rng.integers(45, 225, n)
    p = np.clip(0.30 * np.exp(-(slack - 45) / 50), 0.01, 0.5)
    return pd.DataFrame({"p": p, "y_gap": (rng.uniform(size=n) < p).astype(int), "slack_min": slack, "claim_cost": 250.0,
                         "fare": 400.0, "weight": 1.0, "week": rng.integers(0, 4, n).astype(str)})


def test_reweighting_by_buffer_moves_the_average_gap_and_leaves_a_calibrated_model_calibrated():
    months = {f"2025-0{i}": month(i) for i in range(1, 5)}
    eq, short, long = (summarise(months, s) for s in ("equal", "prefer_short_30", "prefer_long_60"))
    assert short["mean_slack"] < eq["mean_slack"] < long["mean_slack"]
    for s in (eq, short, long):
        assert s["all_ratio"] == pytest.approx(1.0, abs=0.08)           # the model is calibrated at every buffer, so any mix is
    assert reweight(months["2025-01"], "equal")["weight"].equals(months["2025-01"]["weight"])
    assert set(SCENARIOS) == {"equal", "prefer_short_60", "prefer_short_30", "avoid_minimum", "prefer_long_60"}
