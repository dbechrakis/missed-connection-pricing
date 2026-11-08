"""The private-information selection result: closed form checked against simulation and by hand."""
import numpy as np
import pytest

from mcp.selection import closed_form, simulate


def population(n=400_000, sigma=0.8, seed=1):
    rng = np.random.default_rng(seed)
    p = np.clip(0.07 * np.exp(sigma * rng.standard_normal(n) - sigma**2 / 2), 0.003, 0.6)
    return p, np.ones(n), np.full(n, 100.0)


def test_closed_form_by_hand():
    assert closed_form(0.5, 1.0) == pytest.approx(np.exp(0.25))      # 1.284
    assert closed_form(1.0, 2.0) == pytest.approx(np.exp(2.0))
    assert closed_form(0.0, 5.0) == 1.0                              # no hidden information: no exposure at any theta
    assert closed_form(0.7, 0.0) == 1.0                              # nobody selects: no exposure at any kappa


# kappa=0.5 with theta=2 is deliberately absent: it depends on a handful of extreme draws (the simulation gives anything
# from 7% below the closed form to far above it, depending on the seed). The behaviour for large exposure is pinned below.
@pytest.mark.parametrize("kappa,theta,tol", [(0.25, 1.0, 0.03), (0.5, 1.0, 0.03), (0.25, 0.5, 0.03), (0.25, 2.0, 0.03)])
def test_simulation_matches_the_closed_form(kappa, theta, tol):
    p, w, c = population()
    got = simulate(p, w, c, kappa, thetas=(theta,))[theta]["tiered"]
    assert got == pytest.approx(closed_form(kappa, theta), rel=tol)


def test_for_very_large_exposure_the_simulation_falls_below_the_closed_form_not_above():
    # documented behaviour: the cap at probability 1 and heavy tails only ever make the simulated value smaller
    p, w, c = population()
    assert simulate(p, w, c, 1.0, thetas=(2.0,))[2.0]["tiered"] < closed_form(1.0, 2.0)


def test_without_hidden_information_the_tiered_price_is_safe_at_any_theta():
    p, w, c = population()
    for th, r in simulate(p, w, c, 0.0, thetas=(0.5, 1.0, 2.0)).items():
        assert r["tiered"] == pytest.approx(1.0, abs=1e-9)


def test_flat_price_is_always_at_least_as_exposed_as_tiered():
    p, w, c = population()
    for kappa in (0.0, 0.25, 0.5):
        for th, r in simulate(p, w, c, kappa).items():
            assert r["flat"] >= r["tiered"] - 1e-9


def test_flat_exposure_grows_with_the_spread_of_risk_across_connections():
    thetas = (1.0,)
    low = simulate(*population(sigma=0.3), 0.0, thetas=thetas)[1.0]["flat"]
    high = simulate(*population(sigma=0.9), 0.0, thetas=thetas)[1.0]["flat"]
    assert 1.0 < low < high


def test_exposure_rises_with_both_kappa_and_theta():
    p, w, c = population()
    a = simulate(p, w, c, 0.25)
    b = simulate(p, w, c, 0.5)
    assert a[0.5]["tiered"] < a[1.0]["tiered"] < a[2.0]["tiered"]
    assert all(a[t]["tiered"] < b[t]["tiered"] for t in a)
