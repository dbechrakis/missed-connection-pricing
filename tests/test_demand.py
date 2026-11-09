"""The experiment's analysis recovers answers planted in simulated travellers, and the decision rule is conservative."""
import numpy as np
import pytest

from mcp.demand import analyse, decide, logit_fit, oracle_adverse_selection, simulate, wilson


def test_wilson_interval_matches_a_known_case():
    lo, hi = wilson(5, 100)
    assert (lo, hi) == pytest.approx((0.0215, 0.1118), abs=1e-3)
    assert np.isnan(wilson(0, 0)[0])


def test_logit_fit_recovers_known_coefficients():
    rng = np.random.default_rng(0)
    X = np.column_stack([np.ones(100_000), rng.normal(size=100_000)])
    y = (rng.uniform(size=100_000) < 1 / (1 + np.exp(-(-1.0 + 0.8 * X[:, 1])))).astype(float)
    f = logit_fit(X, y)
    assert f["beta"] == pytest.approx([-1.0, 0.8], abs=0.04) and (f["se"] > 0).all() and f["se"].max() < 0.02


def covers(lo, hi, truth):
    return lo <= truth <= hi


def test_intervals_cover_the_planted_answers_about_as_often_as_they_claim():
    """Across many simulated experiments each 95% interval should contain the truth about 95% of the time. Counting coverage over
    ten independent experiments (at least 8 must cover; the chance of fewer than 8 if the intervals are honest is about 1%)
    tests the intervals without trusting any single draw."""
    hits = {"price": 0, "risk": 0, "message": 0, "adverse": 0}
    for seed in range(10):
        d = simulate(150_000, seed=seed, elasticity=-1.5, theta=0.5, theta_hidden=0.5, kappa=0.3, message_effect=0.15)
        r = analyse(d, n_boot=60)
        lg = r["logit"]
        hits["price"] += covers(lg["log_price"]["lo"], lg["log_price"]["hi"], -1.5)
        hits["risk"] += covers(lg["log_risk"]["lo"], lg["log_risk"]["hi"], 0.5)
        hits["message"] += covers(lg["message_outcome"]["lo"], lg["message_outcome"]["hi"], 0.15)
        hits["adverse"] += covers(r["adverse_selection"]["lo"], r["adverse_selection"]["hi"], oracle_adverse_selection(d))
    assert all(v >= 8 for v in hits.values()), hits


def test_attach_falls_with_price_and_adverse_selection_is_found_where_planted_and_absent_where_not():
    d = simulate(400_000, seed=3, theta_hidden=0.5, kappa=0.3)
    r = analyse(d, n_boot=100)
    assert r["by_price_arm"]["0.8"]["attach"] > r["by_price_arm"]["1"]["attach"] > r["by_price_arm"]["1.25"]["attach"]
    assert 1.05 < oracle_adverse_selection(d) < np.exp(0.15)                       # real, and weaker than the small-attach formula (saturation)
    none = oracle_adverse_selection(simulate(400_000, seed=3, theta_hidden=0.0))
    assert abs(none - 1.0) < 0.02


def test_the_guardrail_catches_an_offer_that_costs_bookings_and_stays_quiet_otherwise():
    quiet = analyse(simulate(300_000, seed=7, conversion_effect=0.0), n_boot=30)["guardrail_conversion"]
    assert quiet["lo"] < 0.0 < quiet["hi"]
    bad = analyse(simulate(300_000, seed=7, conversion_effect=-0.03), n_boot=30)["guardrail_conversion"]
    assert bad["hi"] < 0.0


def test_the_decision_rule_uses_the_unfavourable_end_of_each_interval():
    r = analyse(simulate(300_000, seed=5, base_attach=0.05, theta=0.2, theta_hidden=0.0), n_boot=60)
    ok = decide(r, min_attach=0.03, max_theta=0.6, max_adverse=1.15, min_conversion_diff=-0.01)
    assert ok["go"] and all(ok.values())
    assert not decide(r, min_attach=0.06, max_theta=0.6, max_adverse=1.15, min_conversion_diff=-0.01)["attach_at_model_price"]
    bad = analyse(simulate(300_000, seed=5, theta_hidden=2.0, kappa=0.5), n_boot=60)
    assert not decide(bad, 0.01, 5.0, 1.15, -0.05)["adverse_selection_ok"]
