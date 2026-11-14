"""mcp.level: each candidate recovers what was planted, none reads a month later than t - lag, and the intervals cover."""
import json
from pathlib import Path

import numpy as np
import pytest

from mcp import level as L

ROOT = Path(__file__).resolve().parents[1]


def months(n, start=(2018, 1)):
    y, m = start
    out = []
    for i in range(n):
        k = y * 12 + (m - 1) + i
        out.append(f"{k // 12}-{k % 12 + 1:02d}")
    return out


# ---- the filter ----------------------------------------------------------------------------------------------

def test_a_local_level_with_no_drift_is_the_running_mean():
    rng = np.random.default_rng(0)
    z = rng.normal(0.2, 0.1, 30)
    f = L._filter(z, 0.0)
    assert f["m"][-1] == pytest.approx(z.mean(), abs=1e-12)
    assert f["P"][-1] == pytest.approx(1 / len(z), abs=1e-12)        # variance of the mean, in units of var(e)


def test_a_large_drift_ratio_follows_the_last_observation():
    z = np.array([0.0, 0.1, 0.0, 0.3, 0.2, 0.5, 0.4])
    f = L._filter(z, 1e6)
    assert f["m"][-1] == pytest.approx(z[-1], abs=1e-3)


def test_maximum_likelihood_picks_small_drift_for_noise_and_large_drift_for_a_random_walk():
    rng = np.random.default_rng(1)
    noise = rng.normal(0.1, 0.2, 80)
    walk = np.cumsum(rng.normal(0, 0.2, 80)) + rng.normal(0, 0.02, 80)
    assert L.fit_local(noise)["q"] < 0.05
    assert L.fit_local(walk)["q"] > 2.0


# ---- planted structure ---------------------------------------------------------------------------------------

def test_every_candidate_recovers_a_planted_level_and_none_does_not():
    rng = np.random.default_rng(2)
    z = 0.3 + rng.normal(0, 0.05, 40)
    mo = months(40)
    for method in ("last12", "local"):
        wf = L.walk_forward(z, mo, lag=2, method=method)
        assert np.nanmean(wf["mu"][-10:]) == pytest.approx(0.3, abs=0.04), method
    wf = L.walk_forward(z, mo, lag=2, method="none")
    assert np.nanmax(np.abs(wf["mu"])) == 0.0


def test_local_follows_a_trend_better_than_a_twelve_month_mean():
    rng = np.random.default_rng(3)
    z = 0.015 * np.arange(60) + rng.normal(0, 0.03, 60)
    mo = months(60)
    err = {}
    for method in ("last12", "local"):
        wf = L.walk_forward(z, mo, lag=2, method=method)
        err[method] = np.nanmean(np.abs(z - wf["mu"])[20:])
    assert err["local"] < 0.6 * err["last12"]


def test_local_season_finds_a_planted_seasonal_pattern_once_it_has_four_years():
    rng = np.random.default_rng(4)
    n = 120
    mo = months(n)
    moy = L.month_of_year(mo)
    season = 0.30 * np.sin(2 * np.pi * (moy - 2) / 12)
    z = 0.05 + season + rng.normal(0, 0.08, n)
    wf_s = L.walk_forward(z, mo, lag=2, method="local_season")
    wf_l = L.walk_forward(z, mo, lag=2, method="local")
    # before 48 known months it is the local level, and says so
    assert set(wf_s["used"][8:49]) == {"local"}
    assert set(wf_s["used"][52:]) == {"local_season"}
    late = slice(60, n)
    assert np.mean(np.abs(z - wf_s["mu"])[late]) < 0.75 * np.mean(np.abs(z - wf_l["mu"])[late])
    gamma, _, _, _ = L._season_effects(z[:96], moy[:96])
    assert np.corrcoef(gamma, 0.30 * np.sin(2 * np.pi * (np.arange(12) - 2) / 12))[0, 1] > 0.95
    assert abs(gamma.mean()) < 1e-9                                    # the level, not the season, carries the mean


def test_the_seasonal_effects_are_shrunk_toward_zero_when_there_is_no_season():
    rng = np.random.default_rng(5)
    z = 0.1 + rng.normal(0, 0.15, 96)
    gamma, _, _, _ = L._season_effects(z, L.month_of_year(months(96)))
    assert np.abs(gamma).max() < 0.08


def test_credibility_trusts_real_hub_differences_and_pools_pure_noise():
    rng = np.random.default_rng(6)
    window = np.array([-0.2, -0.1, 0.0, 0.1, 0.25]) + rng.normal(0, 0.02, (12, 5))       # hubs truly differ
    level, var, Z, collective = L.credibility_panel(window)
    assert Z > 0.9 and np.allclose(level, window.mean(axis=0), atol=0.03)
    noise = rng.normal(0.1, 0.2, (12, 5))                                                 # hubs the same, only noise
    level, var, Z, collective = L.credibility_panel(noise)
    assert Z < 0.3
    assert level.std() < noise.mean(axis=0).std()                                          # pulled together


# ---- no look-ahead -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("method", ["none", "last12", "local", "local_season"])
@pytest.mark.parametrize("lag", [2, 5])
def test_a_forecast_never_reads_a_month_later_than_t_minus_lag(method, lag):
    rng = np.random.default_rng(7)
    n = 80
    mo = months(n)
    z = rng.normal(0.1, 0.2, n)
    base = L.walk_forward(z, mo, lag, method)
    for cut in (10, 30, 60):
        z2 = z.copy()
        z2[cut:] += rng.normal(3.0, 1.0, n - cut)                   # rewrite everything from month `cut` on
        alt = L.walk_forward(z2, mo, lag, method)
        safe = slice(0, cut + lag)                                   # months t with t - lag < cut see none of it
        assert np.array_equal(base["mu"][safe], alt["mu"][safe], equal_nan=True)
        assert np.array_equal(base["var"][safe], alt["var"][safe], equal_nan=True)


@pytest.mark.parametrize("lag", [2, 5])
def test_the_credibility_panel_never_reads_a_later_month_either(lag):
    rng = np.random.default_rng(8)
    Z = rng.normal(0.1, 0.2, (50, 5))
    mo = months(50)
    base = L.walk_forward_panel(Z, mo, lag, "cred")
    Z2 = Z.copy()
    Z2[30:] += 4.0
    alt = L.walk_forward_panel(Z2, mo, lag, "cred")
    assert np.array_equal(base["mu"][:30 + lag], alt["mu"][:30 + lag], equal_nan=True)


def test_no_forecast_is_made_before_enough_months_are_known():
    z = np.zeros(20)
    wf = L.walk_forward(z, months(20), lag=5, method="local")
    first = int(np.argmax(~np.isnan(wf["mu"])))
    assert first == L.MIN_HISTORY - 1 + 5                            # six known months, five months before pricing
    with pytest.raises(ValueError):
        L.forecast(z[:3], "local", 2)
    with pytest.raises(ValueError):
        L.forecast(z[:10], "mystery", 2)


# ---- scores and intervals ------------------------------------------------------------------------------------

def test_local_intervals_cover_about_their_nominal_share_over_many_series():
    """Coverage judged over many simulated series, not one seed. A local level with known noise is the true model here."""
    rng = np.random.default_rng(9)
    hits, total = 0, 0
    for _ in range(50):
        eta = rng.normal(0, 0.06, 40).cumsum()
        z = eta + rng.normal(0, 0.15, 40)
        wf = L.walk_forward(z, months(40), lag=2, method="local")
        s = L.score(z, wf["mu"], wf["var"], 0.90)
        hits += s["coverage"] * s["n"]
        total += s["n"]
    assert 0.80 <= hits / total <= 0.97


def test_a_constant_level_model_undercovers_when_the_level_drifts():
    """The check has teeth: `none` should fail where a random-walk level is the truth."""
    rng = np.random.default_rng(10)
    hits, total = 0, 0
    for _ in range(40):
        z = rng.normal(0, 0.1, 40).cumsum() * 0.5 + rng.normal(0, 0.05, 40)
        wf = L.walk_forward(z, months(40), lag=2, method="local")
        s = L.score(z, wf["mu"], wf["var"], 0.90)
        wn = L.walk_forward(z, months(40), lag=2, method="none")
        sn = L.score(z, wn["mu"], wn["var"], 0.90)
        assert s["crps"] <= sn["crps"] * 1.2
        hits += s["coverage"] * s["n"]
        total += s["n"]
    assert hits / total > 0.75


def test_score_ignores_months_without_a_forecast():
    z = np.array([0.0, 0.1, 0.2, 0.3])
    mu = np.array([np.nan, np.nan, 0.2, 0.3])
    var = np.array([np.nan, np.nan, 0.01, 0.01])
    s = L.score(z, mu, var)
    assert s["n"] == 2 and s["mae_log"] == 0.0 and s["coverage"] == 1.0


def test_repriced_ratio_is_one_when_the_forecast_is_exact():
    claims = np.array([120.0, 80.0, 100.0])
    expected = np.array([100.0, 100.0, 100.0])
    mu = np.log(claims / expected)
    r = L.repriced_ratio(claims, expected, mu, np.zeros(3))
    assert r["repriced"] == pytest.approx(1.0) and r["unadjusted"] == pytest.approx(1.0)
    r = L.repriced_ratio(claims, expected, np.array([np.nan, 0.1, 0.1]), np.array([np.nan, 0, 0]))
    assert r["months"] == 2 and r["unadjusted"] == pytest.approx(180 / 200)


def test_conformal_intervals_use_only_known_errors_and_cover():
    rng = np.random.default_rng(11)
    z = rng.normal(0, 0.2, 400)
    mu = np.zeros(400)
    c = L.conformal_coverage(z, mu, lag=2, level=0.9)
    assert 0.84 <= c["coverage"] <= 0.97
    # changing a month that is not yet known when month t is priced cannot change t's interval
    base = L.conformal_coverage(z[:50], mu[:50], lag=2)
    z2 = z[:50].copy()
    z2[-1] += 100.0
    alt = L.conformal_coverage(z2, mu[:50], lag=2)
    assert base["n"] == alt["n"]
    assert alt["coverage"] <= base["coverage"]                       # only the last month's own hit can change


# ---- the orientation run -------------------------------------------------------------------------------------

def test_the_orientation_results_exist_and_say_what_they_are():
    d = json.loads((ROOT / "results" / "level_dev.json").read_text())
    assert "not a test" in d["status"]
    assert d["lag_months"] == 2 and d["candidates"] == list(L.CANDIDATES)
    for view in ("all_overnight_risk", "sold_within_cap"):
        v = d[view]
        assert v["months"] == 26 and v["first"] == "2024-07" and v["last"] == "2026-08"
        # with 26 months the seasonal candidate can only be the local level, and the file must say so
        assert v["pooled_series"]["local_season"]["used"] == ["local"]
        assert v["hub_panel"]["local_season"]["used"] == ["local"]
        assert v["pooled_series"]["none"]["n"] == 19                 # 26 months, lag 2, six known months to start


def test_part_7a_quotes_the_numbers_in_the_results_file():
    d = json.loads((ROOT / "results" / "level_dev.json").read_text())
    text = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7A."):]
    rows = {"All, pooled": ("all_overnight_risk", "pooled_series"), "All, hub panel": ("all_overnight_risk", "hub_panel"),
            "Sold, pooled": ("sold_within_cap", "pooled_series"), "Sold, hub panel": ("sold_within_cap", "hub_panel")}
    checked = 0
    for line in part.splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 6 and cells[0] in rows and cells[1].strip("`") in L.CANDIDATES:
            view, series = rows[cells[0]]
            s = d[view][series][cells[1].strip("`")]
            assert cells[2] == f"{s['crps']:.3f}" and cells[3] == f"{s['coverage']:.2f}", line
            assert cells[4] == f"{s['unadjusted']:.3f}" and cells[5] == f"{s['repriced']:.3f}", line
            checked += 1
    assert checked == 14
    # the readings cited in the prose
    assert f"{d['all_overnight_risk']['hub_panel']['cred']['credibility_mean']:.2f} for all connections" in part
    assert f"{d['sold_within_cap']['hub_panel']['cred']['credibility_mean']:.2f} as sold" in part
    for view in ("all_overnight_risk", "sold_within_cap"):
        for series in ("pooled_series", "hub_panel"):
            best = min(d[view][series], key=lambda k: d[view][series][k]["crps"])
            assert best == "none", (view, series)                    # the first reading in 7A


# ---- months that were not observed ---------------------------------------------------------------------------

def test_a_missing_month_is_skipped_and_the_rest_is_seen_in_order():
    rng = np.random.default_rng(12)
    z = rng.normal(0.1, 0.2, 40)
    z[12:20] = np.nan                                                # eight months not observed
    mo = months(40)
    wf = L.walk_forward(z, mo, lag=2, method="local")
    t = 33
    known = [s for s in range(t - 1) if np.isfinite(z[s])]
    mu, var, used = L.forecast(z[known], "local", 2, L.month_of_year(mo)[known], int(L.month_of_year(mo)[t]))
    assert wf["mu"][t] == mu and wf["var"][t] == var
    first = int(np.argmax(~np.isnan(wf["mu"])))
    assert first == 7                                                # six observed months, then two months of lag


@pytest.mark.parametrize("method", ["none", "last12", "local"])
def test_missing_months_do_not_open_a_look_ahead(method):
    rng = np.random.default_rng(13)
    z = rng.normal(0.1, 0.2, 50)
    z[15:22] = np.nan
    base = L.walk_forward(z, months(50), 2, method)
    z2 = z.copy()
    z2[30:] += 5.0
    alt = L.walk_forward(z2, months(50), 2, method)
    assert np.array_equal(base["mu"][:32], alt["mu"][:32], equal_nan=True)


def test_scores_and_the_repriced_ratio_ignore_missing_outcomes():
    z = np.array([0.0, np.nan, 0.2, 0.3])
    mu = np.array([0.0, 0.1, 0.2, 0.3])
    var = np.full(4, 0.01)
    assert L.score(z, mu, var)["n"] == 3
    r = L.repriced_ratio(np.array([100.0, np.nan, 120.0]), np.array([100.0, 100.0, 100.0]), np.array([0.0, 0.0, 0.0]), np.zeros(3))
    assert r["months"] == 2 and r["unadjusted"] == pytest.approx(1.1)
    panel = np.random.default_rng(14).normal(0.1, 0.2, (30, 5))
    panel[10:14, 2] = np.nan
    wp = L.walk_forward_panel(panel, months(30), 2, "cred")
    assert np.isfinite(wp["mu"][20]).all() and np.isnan(wp["mu"][:7]).all()
