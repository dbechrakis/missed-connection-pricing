"""mcp.capital against cases with a known answer."""
import numpy as np
import pytest

from mcp import capital as K

WEEKS = np.datetime64("2023-01-02") + 7 * np.arange(156)


def test_a_book_with_no_variance_is_priced_at_expected_claims_over_one_minus_expenses():
    expected = np.full(156, 1000.0)
    claims = expected.copy()
    out = K.solve(claims, expected, WEEKS, attach=None, coc=0.10, expense=0.0, n_sim=50)
    assert out["pi"] == pytest.approx(1.0, abs=2e-3)                       # premium equals claims: a loss ratio of 100%
    assert out["loading_vs_current"] == pytest.approx(0.65, abs=2e-3)
    assert K.solve(claims, expected, WEEKS, expense=0.30, n_sim=50)["pi"] == pytest.approx(1 / 0.70, abs=3e-3)


def test_the_solution_balances_the_equation_and_more_variance_costs_more():
    rng = np.random.default_rng(0)
    expected = np.full(156, 1000.0)
    calm = expected * np.exp(rng.normal(0, 0.1, 156))
    wild = expected * np.exp(rng.normal(0, 0.5, 156))
    a, b = K.solve(calm, expected, WEEKS, n_sim=300), K.solve(wild, expected, WEEKS, n_sim=300)
    assert abs(a["residual"]) < 5e-3 and abs(b["residual"]) < 5e-3
    assert b["pi"] > a["pi"] and b["terms"]["capital_margin"] > a["terms"]["capital_margin"]


def test_capital_costs_more_at_a_higher_cost_of_capital_and_a_stop_loss_trades_capital_for_its_price():
    rng = np.random.default_rng(1)
    expected = np.full(156, 1000.0)
    claims = expected * np.exp(rng.normal(0, 0.5, 156))
    lo, hi = K.solve(claims, expected, WEEKS, coc=0.06, n_sim=300), K.solve(claims, expected, WEEKS, coc=0.15, n_sim=300)
    assert hi["pi"] > lo["pi"]
    sl = K.solve(claims, expected, WEEKS, attach=1.0, coc=0.10, n_sim=300)
    free = K.solve(claims, expected, WEEKS, attach=None, coc=0.10, n_sim=300)
    assert sl["terms"]["stop_loss_cost"] > 0 and sl["terms"]["capital_margin"] < free["terms"]["capital_margin"]


def test_a_stop_loss_cost_is_its_burning_cost_per_unit_of_premium():
    expected = np.full(156, 1000.0)
    claims = expected * np.where(np.arange(156) % 4 == 0, 3.0, 0.5)
    c = K.components(1.0, claims, expected, WEEKS, 1.0, 0.1, 0.95, 50, 4, 0)
    assert c["stop_loss_cost"] == pytest.approx(np.mean(np.maximum(claims / expected - 1.0, 0)))
    assert c["retained_loss_ratio"] == pytest.approx(np.mean(np.minimum(claims / expected, 1.0)))


def test_diversification_is_one_for_identical_hubs_and_near_a_square_root_for_independent_ones():
    rng = np.random.default_rng(2)
    base = rng.normal(1, 0.3, 400)
    same = K.diversification({h: base for h in "ABCDE"})
    assert same["ratio"] == pytest.approx(1.0) and same["mean_pairwise_correlation"] == pytest.approx(1.0)
    ind = K.diversification({h: rng.normal(1, 0.3, 4000) for h in "ABCDE"})
    assert ind["ratio"] == pytest.approx(1 / np.sqrt(5), abs=0.03) and abs(ind["mean_pairwise_correlation"]) < 0.05


def test_no_premium_balances_an_impossible_book():
    expected = np.full(156, 1000.0)
    with pytest.raises(ValueError):
        K.solve(expected * 1e6, expected, WEEKS, n_sim=20, hi=2.0)
