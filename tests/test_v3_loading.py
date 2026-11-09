"""The price loading: a fixed point between price and who passes the cap, fitted on earlier months only."""
import numpy as np
import pandas as pd
import pytest

from mcp.v3_loading import fit_lambda, measure, month_index, rolling, sold, weekly_loss_ratio


def book(n=2000, seed=0, under=1.4):
    """Connections whose true risk is `under` times what the model says, more so where the model says it is low."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.01, 0.12, n)
    true = np.minimum(p * (1 + (under - 1) * (0.12 - p) / 0.11), 0.9)
    return pd.DataFrame({"p": p, "y_gap": (rng.uniform(size=n) < true).astype(int), "claim_cost": 250.0, "fare": 400.0,
                         "weight": 1.0, "week": rng.integers(0, 8, n).astype(str)})


def test_a_higher_loading_prices_connections_out_of_the_cap():
    d = book()
    assert sold(d, 1.0).sum() > sold(d, 1.3).sum() > sold(d, 2.0).sum()
    # premium = lam * p * cost / 0.65; the cap is 5% of 400 = 20: p at most 0.052 at lam 1
    assert sold(d.assign(p=0.052), 1.0).all() and not sold(d.assign(p=0.053), 1.0).any()


def test_fit_lambda_reaches_the_target_loss_ratio_where_the_model_under_prices_and_is_one_where_it_does_not():
    d = book(n=60_000, under=1.5)
    assert measure(d, 1.0)["loss_ratio"] > 0.65
    lam = fit_lambda(d)
    assert lam > 1.0 and measure(d, lam)["loss_ratio"] <= 0.65 + 1e-9
    assert measure(d, round(lam - 0.01, 2))["loss_ratio"] > 0.65                     # the smallest loading that does it
    safe = book(n=60_000, under=1.0).assign(y_gap=lambda x: (np.random.default_rng(1).uniform(size=len(x)) < x["p"] * 0.7).astype(int))
    assert fit_lambda(safe) == 1.0                                                   # a model that over-prices needs no loading


def test_the_loading_reduces_the_share_sold_and_the_measure_is_consistent():
    d = book(n=60_000, under=1.5)
    a, b = measure(d, 1.0), measure(d, 1.4)
    assert b["share_sold"] < a["share_sold"]
    assert a["loss_ratio"] == pytest.approx(0.65 * a["ratio"])                       # at lam 1 the loss ratio is the ratio times the target
    assert b["loss_ratio"] == pytest.approx(0.65 * b["ratio"] / 1.4)


def test_rolling_uses_only_months_known_one_month_before_and_needs_enough_history():
    months = {f"2025-{m:02d}": book(seed=m, n=3000) for m in range(1, 11)}
    r = rolling(months, lag=1, min_months=6)
    assert r["ym"].tolist() == ["2025-08", "2025-09", "2025-10"]                      # month 8 uses months 1 to 6; lag 1 leaves month 7 out
    assert r.loc[r["ym"] == "2025-08", "history_months"].iloc[0] == 6
    assert month_index("2025-12") - month_index("2025-01") == 11


def test_weekly_loss_ratio_is_claims_over_loaded_premium():
    d = pd.DataFrame({"p": [0.05, 0.05], "y_gap": [1, 0], "claim_cost": [200.0, 200.0], "fare": [400.0, 400.0], "weight": [1.0, 1.0], "week": ["a", "a"]})
    w = weekly_loss_ratio(d, 1.0)
    assert w["a"] == pytest.approx(200 / (2 * 0.05 * 200 / 0.65))


def test_the_fast_fit_equals_the_brute_force_fit():
    from mcp.v3_loading import GRID
    d = book(n=40_000, under=1.5)
    brute = next((float(lam) for lam in GRID if measure(d, float(lam))["loss_ratio"] <= 0.65), float(GRID[-1]))
    assert fit_lambda(d) == brute
