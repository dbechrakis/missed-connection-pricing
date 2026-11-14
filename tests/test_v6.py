"""v6: the frozen multipliers, the seasonal price arithmetic, and the grading rules of PREREGISTRATION_V6_FORWARD.md."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mcp import grade
from mcp import v6

ROOT = Path(__file__).resolve().parents[1]


def test_the_frozen_multipliers_are_the_ones_the_pre_registration_hashes():
    raw = (ROOT / "models" / "v6_season.json").read_bytes()
    text = (ROOT / "PREREGISTRATION_V6_FORWARD.md").read_text(encoding="utf-8")
    assert hashlib.sha256(raw).hexdigest() in text
    s = v6.load_season()
    assert sorted(s["multiplier"]) == [f"{m:02d}" for m in range(1, 13)] and s["kappa"] == 1.0
    assert v6.multiplier("2027-06") == s["multiplier"]["06"] > 1.2 and v6.multiplier("2026-11") < 0.75 and 0.9 < v6.multiplier("2027-03") < 1.1
    # the multiplier is exp(grand mean + shrunk deviation), as the file says
    for m, mult in s["multiplier"].items():
        assert mult == pytest.approx(math.exp(s["grand_mean_log_ratio"] + s["effects_log"][m]), abs=1e-4)


def test_the_bands_and_the_autumn_prediction_in_the_document_match_the_code():
    text = (ROOT / "PREREGISTRATION_V6_FORWARD.md").read_text(encoding="utf-8")
    s = v6.load_season()
    assert (v6.SIGMA, v6.RHO) == (s["residual_sd_leave_one_year_out"], s["residual_lag1_autocorrelation"]) == (grade.SIGMA_FORWARD, grade.RHO_FORWARD)
    assert f"{v6.band_half_width(3):.3f}" in text and "1 ± 0.287" in text
    mean = sum(s["multiplier"][m] for m in ("09", "10", "11")) / 3
    lo, hi = mean * (1 - v6.band_half_width(3)), mean * (1 + v6.band_half_width(3))
    assert f"{mean:.3f}" in text and f"{lo:.3f} to {hi:.3f}" in text.replace("**", "")
    assert v6.WINDOWS == {"spring2027": ("2027-03", "2027-05"), "summer2027": ("2027-06", "2027-08")} and v6.FRAC == 0.20 and v6.SHARE_BAND == grade.SHARE_FORWARD == (0.20, 0.55)
    assert "2026-09" not in Path(v6.__file__).read_text(encoding="utf-8")


def _rows(months=("2027-06", "2027-07", "2027-08"), n=500, seed=0, ratio=1.3, cost=250.0):
    """Connections whose true miss rate is `ratio` times the model's p, with fares that let about half pass the cap."""
    rng = np.random.default_rng(seed)
    parts = []
    for ym in months:
        p = rng.uniform(0.01, 0.06, n)
        y = (rng.random(n) < np.clip(p * ratio, 0, 1)).astype(float)
        parts.append(pd.DataFrame({"ym": ym, "weight": rng.uniform(5, 15, n), "p": p, "y_gap": y, "claim_cost": cost, "fare": rng.uniform(150, 900, n)}))
    return pd.concat(parts, ignore_index=True)


def test_the_monthly_table_prices_with_the_multiplier_and_takes_the_ratio_against_the_unadjusted_expected_claims():
    season = {"multiplier": {"06": 2.0, "07": 1.0, "08": 0.5}}
    rows = _rows(n=2000)
    t = v6.monthly_table(rows, season)
    g = rows[rows["ym"] == "2027-06"]
    claims, expected = (g["weight"] * g["y_gap"] * g["claim_cost"]).sum(), (g["weight"] * g["p"] * g["claim_cost"]).sum()
    assert t["2027-06"]["ratio"] == pytest.approx(claims / expected) and t["2027-06"]["multiplier"] == 2.0
    # a dearer price lets fewer connections through the cap, a cheaper one more
    assert t["2027-06"]["share_sold"] < t["2027-07"]["share_sold"] < t["2027-08"]["share_sold"]
    price = 2.0 * g["p"] * g["claim_cost"] / v6.TARGET_LR
    sold = price <= v6.WTP_CAP * g["fare"]
    assert t["2027-06"]["sold_loss_ratio"] == pytest.approx((g["weight"] * g["y_gap"] * g["claim_cost"])[sold].sum() / (g["weight"] * price)[sold].sum())


def test_a_season_that_matches_the_truth_beats_a_constant_level_and_calibrates():
    season = {"multiplier": {"06": 1.3, "07": 1.3, "08": 1.3}}
    r = v6.analyse(_rows(n=20000, ratio=1.3), "summer2027", season)
    assert abs(r["pooled_adjusted_ratio"] - 1) < 0.05 and r["mae_season"] < r["mae_none"] and r["band_half_width"] == pytest.approx(v6.band_half_width(3))
    flat = v6.analyse(_rows(n=20000, ratio=1.0), "summer2027", season)
    assert flat["mae_season"] > flat["mae_none"]                              # a season that is not there does worse than a constant level


def test_the_forward_expectations_pass_and_fail_by_their_own_rules():
    ok = {"band_half_width": 0.287, "pooled_adjusted_ratio": 1.1, "mae_season": 0.10, "mae_none": 0.25, "share_sold_range": [0.3, 0.45],
          "months": {"2027-06": {"sold_loss_ratio": 0.8}, "2027-07": {"sold_loss_ratio": 1.0}, "2027-08": {"sold_loss_ratio": 0.6}}}
    g = grade.grade_forward(ok, "summer2027")
    assert set(g) == {"H1", "H2", "H3", "H4"} and all(v["pass"] for v in g.values())
    assert set(grade.grade_forward(ok, "spring2027")) == {"G1", "G2", "G3", "G4"}
    assert not grade.grade_forward({**ok, "pooled_adjusted_ratio": 1.3}, "summer2027")["H1"]["pass"]
    assert not grade.grade_forward({**ok, "mae_season": 0.3}, "summer2027")["H2"]["pass"]
    bad = {**ok, "months": {**ok["months"], "2027-07": {"sold_loss_ratio": 1.05}}}
    assert not grade.grade_forward(bad, "summer2027")["H3"]["pass"]
    assert not grade.grade_forward({**ok, "share_sold_range": [0.15, 0.45]}, "summer2027")["H4"]["pass"] and not grade.grade_forward({**ok, "share_sold_range": [0.3, 0.6]}, "summer2027")["H4"]["pass"]


def test_the_autumn_prediction_is_graded_from_the_v3_holdout_file():
    mk = lambda r: {"results": {"primary": {"overall": {"ratio": r}}}}
    assert grade.grade_autumn(mk(0.80))["Q1"]["pass"] and grade.grade_autumn(mk(0.55))["Q1"]["pass"] and grade.grade_autumn(mk(0.98))["Q1"]["pass"]
    assert not grade.grade_autumn(mk(0.50))["Q1"]["pass"] and not grade.grade_autumn(mk(1.05))["Q1"]["pass"]


def test_a_window_is_read_once(tmp_path, monkeypatch):
    monkeypatch.setattr(v6, "ROOT", tmp_path)
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "v6_forward_summer2027.json").write_text("{}")
    with pytest.raises(SystemExit):
        v6.read("summer2027")


def test_part_7g_quotes_the_numbers_in_the_results_file_and_reproduces_the_frozen_file():
    d = json.loads((ROOT / "results" / "v6_season_dev.json").read_text(encoding="utf-8"))
    a = v6.load_season()
    text = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7G."):]
    assert d["months"] == 70 and d["fit"]["mu"] == pytest.approx(a["grand_mean_log_ratio"], abs=1e-6)
    assert all(d["fit"]["effects"][m] == pytest.approx(a["effects_log"][m], abs=1e-6) for m in a["effects_log"])
    loyo = d["leave_one_year_out"]["1.0"]
    assert loyo["residual_sd"] == pytest.approx(a["residual_sd_leave_one_year_out"], abs=5e-5) and round(loyo["residual_lag1_autocorrelation"], 3) == a["residual_lag1_autocorrelation"]
    sign = lambda x: f"{x:+.2f}".replace("-", "−")
    row = [l for l in part.splitlines() if l.startswith("| Mean log ratio |")][0]
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[1:] == [sign(d["calendar_month_mean_log_ratio"][f"{m:02d}"]["mean"]) for m in range(1, 13)]
    row = [l for l in part.splitlines() if l.startswith("| Observed months |")][0]
    assert [c.strip() for c in row.strip("|").split("|")][1:] == [str(d["calendar_month_mean_log_ratio"][f"{m:02d}"]["n"]) for m in range(1, 13)]
    assert f"**{loyo['mae_season']:.3f}**" in part and f"**{loyo['mae_none']:.3f}**" in part and f"{loyo['mae_constant_level']:.3f} with a constant level" in part
    assert f"{d['leave_one_year_out']['2.0']['mae_season']:.3f} at κ = 2" in part and f"{d['leave_one_year_out']['4.0']['mae_season']:.3f} at κ = 4" in part
    for s in d["summers"]:
        assert f"{s['start'][:4]} {s['ratio_all']:.2f} and {s['sold_loss_ratio']:.0%}" in part
    assert sum(1 for s in d["summers"] if s["sold_loss_ratio"] > 1) == 2 and len(d["summers"]) == 5 and all(1.19 <= s["ratio_all"] < 1.425 for s in d["summers"])


def test_the_season_functions_recover_a_planted_pattern():
    rng = np.random.default_rng(0)
    idx = [f"{y}-{m:02d}" for y in range(2019, 2026) for m in range(1, 13)]
    plant = {m: 0.3 * np.sin(2 * np.pi * (m - 3) / 12) for m in range(1, 13)}
    z = pd.Series([plant[int(i[5:])] + rng.normal(0, 0.05) for i in idx], index=idx)
    fit = v6.fit_season(z, 1.0)
    assert all(abs(fit["effects"][f"{m:02d}"] - (plant[m] - np.mean(list(plant.values())))) < 0.06 for m in range(1, 13))
    r = v6.leave_one_year_out(z)
    assert r["mae_season"] < 0.5 * r["mae_none"] and r["months"] == 84 and r["residual_sd"] < 0.1


def test_the_forward_test_waits_for_the_scheduled_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(v6, "ROOT", tmp_path)
    monkeypatch.setattr("mcp.variant.VARIANT", "v3")
    (tmp_path / "results").mkdir()
    assert not v6.scheduled_reads_done(tmp_path)
    for name in v6.SCHEDULED_READS[:-1]:
        (tmp_path / "results" / name).write_text("{}")
    assert not v6.scheduled_reads_done(tmp_path)
    with pytest.raises(SystemExit, match="scheduled reads"):
        v6.run("spring2027")
    (tmp_path / "results" / v6.SCHEDULED_READS[-1]).write_text("{}")
    assert v6.scheduled_reads_done(tmp_path)
    monkeypatch.setattr(v6.B, "run", lambda *a, **k: None)
    v6.run("spring2027")
    with pytest.raises(SystemExit, match="scheduled reads"):
        monkeypatch.setattr(v6, "scheduled_reads_done", lambda root=None: False)
        v6.read("summer2027")


def test_the_loaded_series_multiplies_the_price_and_reapplies_the_cap_without_touching_the_pre_registered_table():
    season = {"multiplier": {f"{m:02d}": 1.0 for m in range(1, 13)}}
    rows = pd.DataFrame({"ym": ["2027-06"] * 2, "weight": [1.0, 1.0], "p": [0.05, 0.05], "claim_cost": [100.0, 100.0], "y_gap": [0.0, 1.0], "fare": [160.0, 200.0]})
    price = 0.05 * 100.0 / v6.TARGET_LR
    assert price <= v6.WTP_CAP * 160.0 < 1.10 * price
    assert v6.monthly_table(rows, season)["2027-06"]["share_sold"] == 1.0
    loaded = v6.loaded_table(rows, season, 1.10)["2027-06"]
    assert loaded["share_sold"] == pytest.approx(0.5)
    assert loaded["sold_loss_ratio"] == pytest.approx(100.0 / (1.10 * price))
    assert v6.LOADING == 1.10
