"""mcp.risk against closed forms, and against the project's own published stop-loss figures."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mcp import risk

ROOT = Path(__file__).resolve().parents[1]


def test_normal_quantile_and_scores_match_known_values():
    assert risk.norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-5)
    assert risk.norm_ppf(0.5) == pytest.approx(0.0, abs=1e-9)
    # CRPS of N(0, 1) at its own mean is (sqrt(2) - 1) / sqrt(pi)
    assert risk.crps_normal(0.0, 0.0, 1.0) == pytest.approx((math.sqrt(2) - 1) / math.sqrt(math.pi), abs=1e-9)
    assert risk.crps_normal(0.0, 0.0, 2.0) == pytest.approx(2 * (math.sqrt(2) - 1) / math.sqrt(math.pi), abs=1e-9)
    assert risk.log_score_normal(0.0, 0.0, 1.0) == pytest.approx(0.5 * math.log(2 * math.pi), abs=1e-12)


def test_crps_equals_its_sample_definition():
    """CRPS = E|X - y| - 0.5 E|X - X'| for X ~ N(mu, sd^2), estimated by simulation."""
    rng = np.random.default_rng(1)
    x, x2 = rng.normal(0.3, 0.7, 400_000), rng.normal(0.3, 0.7, 400_000)
    y = 1.1
    sample = np.abs(x - y).mean() - 0.5 * np.abs(x - x2).mean()
    assert float(risk.crps_normal(y, 0.3, 0.7)) == pytest.approx(sample, abs=0.004)


def test_crps_rewards_a_calibrated_forecast_over_an_overconfident_one():
    rng = np.random.default_rng(2)
    y = rng.normal(0, 1, 20_000)
    assert risk.crps_normal(y, 0, 1.0).mean() < risk.crps_normal(y, 0, 0.3).mean()
    assert risk.crps_normal(y, 0, 1.0).mean() < risk.crps_normal(y, 0.8, 1.0).mean()
    with pytest.raises(ValueError):
        risk.crps_normal(0.0, 0.0, 0.0)


def test_normal_interval_covers_its_nominal_share():
    rng = np.random.default_rng(3)
    y = rng.normal(2.0, 0.5, 100_000)
    lo, hi = risk.normal_interval(np.full(len(y), 2.0), np.full(len(y), 0.5), 0.90)
    assert risk.interval_coverage(y, lo, hi) == pytest.approx(0.90, abs=0.004)


def test_stop_loss_cost_matches_the_lognormal_closed_form():
    mu, sigma, a = -0.2, 0.4, 1.0
    rng = np.random.default_rng(4)
    x = np.exp(rng.normal(mu, sigma, 600_000))
    d1 = (mu + sigma ** 2 - math.log(a)) / sigma
    d2 = d1 - sigma
    exact = math.exp(mu + sigma ** 2 / 2) * float(risk._Phi(d1)) - a * float(risk._Phi(d2))
    assert risk.stop_loss_cost(x, a) == pytest.approx(exact, abs=0.002)
    assert risk.stop_loss_cost([0.5, 0.7], 1.0) == 0.0
    assert risk.stop_loss_cost([1.5, 0.5], 1.0) == pytest.approx(0.25)


def test_var_and_tvar_of_a_normal():
    rng = np.random.default_rng(5)
    x = rng.normal(0, 1, 400_000)
    var, tvar = risk.var_tvar(x, 0.95)
    assert var == pytest.approx(1.6449, abs=0.02)
    assert tvar == pytest.approx(2.0627, abs=0.03)          # phi(1.6449) / 0.05
    v, t = risk.var_tvar([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9)
    assert (v, t) == (9.0, 9.5)


def test_capital_margin_is_the_cost_of_the_tail_beyond_the_mean():
    x = np.array([0.6, 0.6, 0.6, 0.6, 1.6])
    m = risk.capital_margin(x, level=0.9, cost_of_capital=0.10)       # the 90% tail of five years is the worst one
    assert m["mean"] == pytest.approx(0.8)
    assert m["tvar"] == pytest.approx(1.6)
    assert m["capital_per_premium"] == pytest.approx(0.8)
    assert m["margin_per_premium"] == pytest.approx(0.08)


def test_aggregate_loss_ratio_weighs_by_premium():
    lr = risk.aggregate_loss_ratio([10, 30, 5], [10, 10, 100], ["a", "a", "b"])
    assert lr.tolist() == [2.0, 0.05]                        # a: 40 / 20, b: 5 / 100, sorted by key


def test_season_of_week_is_the_calendar_quarter():
    q = risk.season_of_week(["2024-01-01", "2024-03-25", "2024-04-01", "2024-07-08", "2024-12-30"])
    assert q.tolist() == [0, 0, 1, 2, 3]


def _weekly(n_weeks=156, seed=0):
    start = np.datetime64("2023-01-02")
    ws = start + 7 * np.arange(n_weeks)
    rng = np.random.default_rng(seed)
    premium = rng.uniform(90, 110, n_weeks)
    return ws, premium


def test_season_bootstrap_draws_each_quarter_only_from_that_quarter():
    ws, premium = _weekly()
    q = risk.season_of_week(ws)
    claims = premium * np.where(q == 2, 2.0, 0.5)             # the third quarter is a bad one, always
    sim = risk.season_block_bootstrap_years(claims, premium, ws, n_sim=50, block=4, seed=1)
    w = sim["weekly_loss_ratio"]
    assert w.shape == (50, 52)
    assert np.allclose(w[:, 26:39], 2.0) and np.allclose(w[:, :13], 0.5) and np.allclose(w[:, 39:], 0.5)
    # 39 weeks at 0.5 and 13 at 2.0, premium-weighted: always close to (39 * 0.5 + 13 * 2.0) / 52 = 0.875
    assert np.all(np.abs(sim["annual_loss_ratio"] - 0.875) < 0.03)


def test_season_bootstrap_mean_matches_the_record_and_is_seeded():
    ws, premium = _weekly(seed=3)
    rng = np.random.default_rng(9)
    claims = premium * rng.lognormal(-0.05, 0.3, len(ws))
    a = risk.season_block_bootstrap_years(claims, premium, ws, n_sim=3000, block=4, seed=7)["annual_loss_ratio"]
    b = risk.season_block_bootstrap_years(claims, premium, ws, n_sim=3000, block=4, seed=7)["annual_loss_ratio"]
    assert np.array_equal(a, b)
    assert a.mean() == pytest.approx(claims.sum() / premium.sum(), abs=0.02)


def test_season_bootstrap_never_crosses_a_gap_and_rejects_a_short_record():
    ws, premium = _weekly(n_weeks=40)                         # 40 weeks cannot hold every quarter
    with pytest.raises(ValueError):
        risk.season_block_bootstrap_years(premium, premium, ws, n_sim=5, block=4)
    ws, premium = _weekly(n_weeks=156)
    keep = np.ones(len(ws), bool)
    keep[::2] = False                                          # every other week missing: no run of consecutive weeks
    with pytest.raises(ValueError):
        risk.season_block_bootstrap_years(premium[keep], premium[keep], ws[keep], n_sim=5, block=2)


def test_stop_loss_reproduces_the_published_weekly_figures():
    """The same function on the committed weekly series gives the numbers v3_rolling published."""
    w = pd.read_csv(ROOT / "results" / "v3_rolling_weeks.csv")
    pub = json.loads((ROOT / "results" / "v3_rolling.json").read_text())
    for name, sold in (("all_overnight_risk", False), ("sold_within_cap", True)):
        d = w[w["sold"]] if sold else w
        s = d.groupby("week")[["claims", "premium"]].sum()
        lr = (s["claims"] / s["premium"]).sort_index()
        for a in (0.9, 1.0):
            assert risk.stop_loss_cost(lr, a) == pytest.approx(pub[name]["stop_loss_cost_per_premium"][f"attach_{a:.0%}"], rel=1e-9)
