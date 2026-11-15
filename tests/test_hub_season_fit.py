"""The hierarchical model on synthetic panels of the same shape (VALIDATION.md 7O). Skipped without PyMC, run by the `bayes` CI job."""
import json

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pymc")

from mcp import hub_season as H  # noqa: E402
from mcp import hub_season_fit as F  # noqa: E402

HUBS = ["ATL", "CLT", "DEN", "DFW", "ORD"]
SHORT = {"chains": 2, "tune": 600, "draws": 600}


def simulate(departure_scale: float, shock_scale: float = 0.0, noise: float = 0.06, seed: int = 0, years: int = 8):
    """A panel with known truth: z = shared calendar + hub departure + shared monthly shock + noise, and a function that draws a new year."""
    rng = np.random.default_rng(seed)
    shared = rng.normal(0, 0.25, 12)
    shared -= shared.mean()
    dep = {h: rng.normal(0, departure_scale, 12) for h in HUBS}
    dep = {h: d - d.mean() for h, d in dep.items()}

    def year(y: int, rng_) -> pd.DataFrame:
        rows = []
        for m in range(1, 13):
            shock = rng_.normal(0, shock_scale)
            for h in HUBS:
                truth = shared[m - 1] + dep[h][m - 1]
                rows.append({"hub": h, "ym": f"{y}-{m:02d}", "z": truth + shock + rng_.normal(0, noise), "truth": truth})
        return pd.DataFrame(rows)

    panel = pd.concat([year(2010 + i, rng) for i in range(years)], ignore_index=True)
    panel["year"] = panel["ym"].str[:4].astype(int)
    panel["month"] = panel["ym"].str[5:7]
    panel["claims"] = np.exp(panel["z"])
    panel["expected"] = 1.0
    return panel, year


def posterior_scales(panel, **kwargs):
    idata = F.fit(panel, seed=1, **{**SHORT, **kwargs})
    return idata, F.summarise(idata, panel, seed=1)


def test_hub_departures_of_scale_point_two_are_found():
    panel, _ = simulate(0.2, shock_scale=0.05, seed=1)
    _, summary = posterior_scales(panel)
    assert 0.1 < summary["scales"]["tau_d"]["q50"] < 0.3
    est = np.array([summary["multipliers"][h][m]["mean"] for h in HUBS for m in F.MONTHS])
    truth = panel[panel["year"] == 2010].set_index(["hub", "month"])["truth"]
    truth = np.exp(np.array([truth[(h, m)] for h in HUBS for m in F.MONTHS]))
    assert np.corrcoef(est, truth)[0, 1] > 0.8


def test_no_departures_gives_a_small_scale_and_the_pooled_prediction():
    panel, _ = simulate(0.0, shock_scale=0.05, seed=2)
    _, summary = posterior_scales(panel)
    assert summary["scales"]["tau_d"]["q50"] < 0.05
    targets = panel[panel["year"] == 2010][["hub", "ym"]]
    pooled = H.candidate_pooled(panel, targets).set_index(["hub", "ym"])["mean"]
    hier = np.array([summary["predictive"][h][ym[5:7]]["mean"] for h, ym in zip(targets["hub"], targets["ym"], strict=True)])
    assert np.mean(np.abs(hier - pooled.to_numpy())) < 0.03


def coverage(summary, key, new_years, truth_fn) -> float:
    inside = []
    for new in new_years:
        for m, g in new.groupby(new["ym"].str[5:7]):
            if key == "hub_month":
                for _, row in g.iterrows():
                    p = summary["predictive"][row["hub"]][m]
                    inside.append(abs(row["z"] - p["mean"]) <= 1.6449 * p["sd"])
            else:
                p = summary["predictive_all_hubs"][m]
                inside.append(abs(g["z"].mean() - p["mean"]) <= 1.6449 * p["sd"])
    return float(np.mean(inside))


def test_the_shared_monthly_shock_is_what_keeps_the_interval_of_the_hub_average_honest():
    shock = 0.25
    panel, new_year = simulate(0.05, shock_scale=shock, noise=0.05, seed=3, years=10)
    rng = np.random.default_rng(99)
    new_years = [new_year(2030 + i, rng) for i in range(300)]
    _, with_e = posterior_scales(panel)
    assert 0.80 <= coverage(with_e, "hub_month", new_years, None) <= 0.97
    assert 0.80 <= coverage(with_e, "all_hubs", new_years, None) <= 0.97
    idata = F.fit(panel, seed=1, shared_shock=False, **SHORT)
    without_e = F.summarise(idata, panel, seed=1, shared_shock=False)
    assert coverage(without_e, "all_hubs", new_years, None) < 0.75


def test_the_summary_round_trips_through_the_numpy_scorer(tmp_path):
    panel, _ = simulate(0.1, shock_scale=0.05, seed=4, years=6)
    for year in (2010, 2011):
        result = F.fit_fold(panel, year, **SHORT)
        F.write(result, tmp_path)
        assert json.loads((tmp_path / f"{year}.json").read_text(encoding="utf-8"))["fold"] == year
    two = panel[panel["year"].isin([2010, 2011])]
    predictions = H.leave_one_year_out_panel(two, H.candidate_hier_from_fits(tmp_path), min_months=10)
    scores = H.score(predictions, two)
    assert scores["pooled"]["n"] == 120 and np.isfinite(scores["pooled"]["crps"]) and 0 <= scores["pooled"]["coverage"] <= 1
