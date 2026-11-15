"""The hub-month panel, the numpy candidates and the rule for earning a place (VALIDATION.md 7O)."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mcp import hub_season as H
from mcp.v6 import fit_season

ROOT = Path(__file__).resolve().parents[1]
HUBS = ["ATL", "CLT", "DEN", "DFW", "ORD"]


def synthetic_weeks(departure_scale: float, noise: float = 0.06, seed: int = 0, years=range(2019, 2027)) -> pd.DataFrame:
    """Weekly rows (one per hub, month, sold) built so that each hub-month ratio is exp(shared calendar + hub departure + noise)."""
    rng = np.random.default_rng(seed)
    shared = rng.normal(0, 0.25, 12)
    shared -= shared.mean()
    departures = {h: (lambda d: d - d.mean())(rng.normal(0, departure_scale, 12)) for h in HUBS}
    rows = []
    for y in years:
        for m in range(1, 13):
            ym = f"{y}-{m:02d}"
            if ym >= "2020-03" and ym <= "2021-06":
                continue
            shock = rng.normal(0, 0.03)
            for h in HUBS:
                z = shared[m - 1] + departures[h][m - 1] + shock + rng.normal(0, noise)
                expected = 1000.0
                for sold in (False, True):
                    rows.append({"ym": ym, "week": f"{ym}-01", "hub": h, "sold": sold, "claims": expected * np.exp(z) / 2, "expected": expected / 2})
    return pd.DataFrame(rows)


def test_the_panel_sums_to_the_frozen_calendar_to_six_decimals():
    weeks = pd.read_csv(H.WEEKS)
    panel = H.hub_month_panel(weeks)
    assert panel["ym"].nunique() == 70 and len(panel) == 350 and sorted(panel["hub"].unique()) == HUBS
    frozen = json.loads((ROOT / "models" / "v6_season.json").read_text(encoding="utf-8"))
    fit = fit_season(H.all_hub_series(panel))
    for month, value in frozen["effects_log"].items():
        assert fit["effects"][month] == pytest.approx(value, abs=1e-6)
    assert fit["mu"] == pytest.approx(frozen["grand_mean_log_ratio"], abs=1e-6)


def test_no_pandemic_month_is_in_the_panel_and_folds_need_ten_months():
    panel = H.hub_month_panel(pd.read_csv(H.WEEKS))
    assert not ((panel["ym"] >= "2020-03") & (panel["ym"] <= "2021-06")).any()
    assert H.folds(panel) == [2019, 2022, 2023, 2025]


def evaluate(weeks: pd.DataFrame) -> dict:
    panel = H.hub_month_panel(weeks)
    return {name: H.score(H.leave_one_year_out_panel(panel, fn), panel) for name, fn in H.NUMPY_CANDIDATES.items()}


def test_pooled_beats_by_hub_with_one_shared_calendar_and_loses_with_strong_hub_departures():
    shared = evaluate(synthetic_weeks(0.0))
    assert shared["pooled"]["pooled"]["crps"] < shared["by_hub"]["pooled"]["crps"]
    assert shared["pooled"]["pooled"]["crps"] < shared["none"]["pooled"]["crps"]
    split = evaluate(synthetic_weeks(0.4))
    assert split["by_hub"]["pooled"]["crps"] < split["pooled"]["pooled"]["crps"]


@pytest.mark.parametrize("name", sorted(H.NUMPY_CANDIDATES))
def test_changing_the_held_out_year_cannot_change_its_prediction(name):
    weeks = synthetic_weeks(0.2, seed=3)
    panel = H.hub_month_panel(weeks)
    before = H.leave_one_year_out_panel(panel, H.NUMPY_CANDIDATES[name])
    changed = panel.copy()
    mask = changed["year"] == 2022
    changed.loc[mask, "z"] += 5.0
    changed.loc[mask, "claims"] *= 100.0
    after = H.leave_one_year_out_panel(changed, H.NUMPY_CANDIDATES[name])
    pd.testing.assert_frame_equal(before[before["year"] == 2022], after[after["year"] == 2022])
    other = before["year"] != 2022
    assert not np.allclose(before.loc[other, "mean"], after.loc[other, "mean"]) or name == "none"


def table(crps_a, crps_b):
    return ({str(i): {"crps": a} for i, a in enumerate(crps_a)}, {str(i): {"crps": b} for i, b in enumerate(crps_b)})


def test_earns_its_place_on_three_hand_written_tables():
    a, b = table([0.10, 0.10, 0.10, 0.10], [0.12, 0.12, 0.12, 0.12])
    assert H.earns_its_place(a, b)["earns_its_place"]
    a, b = table([0.10, 0.10, 0.10, 0.13], [0.12, 0.12, 0.12, 0.12])
    one_loss = H.earns_its_place(a, b)
    assert one_loss["folds_won"] == 3 and one_loss["earns_its_place"] is (one_loss["mean_gain"] > 0.005)
    a, b = table([0.10, 0.10, 0.13, 0.13], [0.12, 0.12, 0.12, 0.12])
    assert not H.earns_its_place(a, b)["earns_its_place"]
    a, b = table([0.119, 0.119, 0.119, 0.119], [0.12, 0.12, 0.12, 0.12])
    assert not H.earns_its_place(a, b)["earns_its_place"]
    with pytest.raises(ValueError):
        H.earns_its_place({"1": {"crps": 0.1}}, {"2": {"crps": 0.1}})


def test_scoring_matches_the_closed_forms_and_refuses_unknown_months():
    panel = pd.DataFrame({"hub": ["ATL"], "ym": ["2019-01"], "z": [0.0], "year": [2019]})
    pred = pd.DataFrame({"hub": ["ATL"], "ym": ["2019-01"], "mean": [0.0], "sd": [1.0], "year": [2019]})
    s = H.score(pred, panel)
    assert s["pooled"]["mae"] == 0.0 and s["pooled"]["coverage"] == 1.0
    assert s["pooled"]["crps"] == pytest.approx(2 * 0.3989422804 - 1 / np.sqrt(np.pi), abs=1e-6)
    with pytest.raises(ValueError):
        H.score(pred.assign(ym="2019-02"), panel)


def test_the_committed_development_results_cover_the_three_numpy_candidates():
    result = json.loads((ROOT / "results" / "hub_season_dev.json").read_text(encoding="utf-8"))
    assert {"none", "pooled", "by_hub"} <= set(result["scores"])
    assert result["n_folds"] == len(result["folds"]) == 4 and result["hub_months"] == 350
