"""mcp.coding_audit on planted effects: it finds a real fall, finds nothing in noise, adjusts for conditions, and reads no sealed month."""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mcp import coding_audit as C

ROOT = Path(__file__).resolve().parents[1]


def months(first="2018-01", last="2026-08"):
    out, (y, m) = [], (int(first[:4]), int(first[5:]))
    while f"{y}-{m:02d}" <= last:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def panel(effect=0.0, weather_slope=0.0, seed=0, break_ym="2022-09", airlines=("AA", "DL", "UA"), n=600, noise=0.01):
    rng = np.random.default_rng(seed)
    rows = []
    for a_i, a in enumerate(airlines):
        for ym in months():
            if C.is_pandemic(ym):
                continue
            weather = float(np.clip(rng.normal(0.4, 0.15), 0, 1))
            share = 0.30 + 0.03 * a_i + weather_slope * (weather - 0.4) + (effect / 100 if ym >= break_ym else 0) + rng.normal(0, noise)
            rows.append({"carrier": a, "ym": ym, "n": n, "share": share, "weather": weather, "faa": float(rng.random() < 0.3), "w": float(n)})
    return pd.DataFrame(rows)


def test_a_planted_fall_in_the_carrier_share_is_recovered_with_an_interval_that_excludes_zero():
    p = panel(effect=-6.0)
    est = C.post_effect(p, "2022-09")
    assert est == pytest.approx(-6.0, abs=0.7)
    lo, hi = C.bootstrap_ci(p, "2022-09", ("weather", "faa"), n_boot=300)
    assert lo < est < hi and hi < 0


def test_noise_gives_no_effect_and_an_interval_around_zero():
    p = panel(effect=0.0, seed=3)
    est = C.post_effect(p, "2022-09")
    lo, hi = C.bootstrap_ci(p, "2022-09", ("weather", "faa"), n_boot=300)
    assert abs(est) < 0.8 and lo < 0 < hi


def test_adjusting_for_weather_removes_a_fall_that_the_weather_explains():
    """A month stormier after the break lowers the carrier share by itself. Without the covariate it looks like a fall in coding."""
    rng = np.random.default_rng(4)
    p = panel(weather_slope=-0.5, seed=4)
    p["weather"] = np.where(p["ym"] >= "2022-09", np.clip(p["weather"] + 0.25, 0, 1), p["weather"])
    p["share"] = 0.30 + 0.03 * p["carrier"].map({"AA": 0, "DL": 1, "UA": 2}) - 0.5 * (p["weather"] - 0.4) + rng.normal(0, 0.01, len(p))
    assert C.post_effect(p, "2022-09", covariates=()) < -9.0                       # unadjusted: a large fall
    assert abs(C.post_effect(p, "2022-09", covariates=("weather", "faa"))) < 1.0     # adjusted: none


def test_the_placebo_break_finds_nothing_when_the_series_has_no_trend():
    p = panel(effect=-6.0)                                                          # the real break is September 2022
    q = p[(p["ym"] >= C.PLACEBO_WINDOW[0]) & (p["ym"] <= C.PLACEBO_WINDOW[1])]
    assert abs(C.post_effect(q, C.PLACEBO_BREAK)) < 0.8


def test_difference_in_differences_uses_the_comparison_airline_as_the_counterfactual():
    p = panel(effect=-6.0, airlines=("AA", "DL", "F9"))
    p.loc[p["carrier"] == "F9", "share"] += 0.06 * (p.loc[p["carrier"] == "F9", "ym"] >= "2022-09")    # the comparison moved too
    assert C.post_effect(p, "2022-09", did_group=["AA", "DL"]) == pytest.approx(-6.0, abs=0.7)


def test_eligibility_needs_volume_in_both_periods():
    p = panel(n=600)
    small = p.copy()
    small.loc[(small["carrier"] == "UA") & (small["ym"] >= "2022-09"), "n"] = 1
    ps = {"Y1": small, "Y2": small.iloc[0:0]}
    assert C.eligible(ps, ("AA", "UA"), "2022-09", ("2018-01", "2026-08")) == ["AA"]
    assert C.eligible({"Y1": p, "Y2": p.iloc[0:0]}, ("AA", "UA"), "2022-09", ("2018-01", "2026-08")) == ["AA", "UA"]


def _flights():
    rows = []
    for ym, cancelled, code in (("2019-07", True, "A"), ("2019-07", True, "B"), ("2019-07", True, "C"), ("2019-07", True, "D"), ("2020-05", True, "A"), ("2019-07", False, None)):
        rows.append({"carrier": "AA", "flight_date": pd.Timestamp(f"{ym}-18"), "origin": "ORD", "dest": "LAX", "crs_dep_hhmm": 1400, "crs_arr_hhmm": 1600,
                     "cancelled": cancelled, "cancellation_code": code, "arr_delay_min": 200.0 if not cancelled else np.nan,
                     "delay_carrier_min": 120.0, "delay_weather_min": 80.0, "delay_nas_min": 0.0, "delay_security_min": 0.0, "delay_late_aircraft_min": 0.0,
                     "hub": "ORD", "hub_utc": pd.Timestamp(f"{ym}-18 19:00", tz="UTC"), "weather": 0.0, "faa": 0.0})
    return pd.DataFrame(rows)


def test_panels_use_the_right_denominators_and_drop_the_pandemic_months(monkeypatch):
    monkeypatch.setattr(C, "MIN_DENOMINATOR", 1)
    ps = C.panels(_flights())
    y1, y2 = ps["Y1"], ps["Y2"]
    assert len(y1) == 1 and y1.iloc[0]["n"] == 4 and y1.iloc[0]["share"] == pytest.approx(0.25)    # A, B, C, D cancelled: all four rows are cancelled flights
    assert len(y2) == 1 and y2.iloc[0]["share"] == pytest.approx(120 / 200)                        # carrier minutes over the five causes


def test_hub_hour_converts_the_scheduled_time_at_the_hub_to_utc_with_daylight_saving():
    df = pd.DataFrame({"origin": ["ORD", "LAX", "DEN", "ATL"], "dest": ["LAX", "ATL", "LAX", "LAX"], "flight_date": pd.to_datetime(["2019-07-18", "2019-01-18", "2019-07-18", "2019-01-18"]),
                       "crs_dep_hhmm": [1400, 900, 1000, 800], "crs_arr_hhmm": [1600, 1700, 1200, 1000]})
    out = C.hub_hour(df)
    assert out["hub"].tolist() == ["ORD", "ATL", "DEN", "ATL"]
    assert out["hub_utc"].iloc[0] == pd.Timestamp("2019-07-18 19:00", tz="UTC")      # Chicago, CDT
    assert out["hub_utc"].iloc[1] == pd.Timestamp("2019-01-18 22:00", tz="UTC")      # arrival at Atlanta 17:00 EST
    assert out["hub_utc"].iloc[2] == pd.Timestamp("2019-07-18 16:00", tz="UTC")      # Denver, MDT
    assert out["hub_utc"].iloc[3] == pd.Timestamp("2019-01-18 13:00", tz="UTC")


def test_conditions_join_weather_by_hub_and_hour_and_faa_by_interval():
    flights = C.hub_hour(pd.DataFrame({"origin": ["ORD", "ORD"], "dest": ["LAX", "LAX"], "flight_date": pd.to_datetime(["2019-07-18", "2019-07-18"]),
                                       "crs_dep_hhmm": [1400, 1700], "crs_arr_hhmm": [1600, 1900]}))
    asos = pd.DataFrame({"station": ["ORD", "ORD"], "obs_utc": pd.to_datetime(["2019-07-18 19:15", "2019-07-18 22:15"]),
                         "thunder": [True, False], "snow": [False, False], "freezing": [False, False], "low_vis": [False, False], "high_wind": [False, False]})
    prog = [{"element": "ORD", "kind": "gs", "period": ["2019-07-18T21:59:00+00:00", "2019-07-18T23:30:00+00:00"], "cnx": False, "proposed": False, "carrier_specific": False, "send": "07/18/19 21:50"}]
    out = C.add_conditions(flights, asos, prog)
    assert out["weather"].tolist() == [1.0, 0.0] and out["faa"].tolist() == [0.0, 1.0]
    assert C.add_conditions(flights, asos, None)["faa"].tolist() == [0.0, 0.0]


def test_nothing_from_september_2026_is_read_and_the_audit_is_read_once(tmp_path, monkeypatch):
    assert C.LAST_DATE == "2026-09-01" and "flight_date < DATE" in Path(C.__file__).read_text(encoding="utf-8")
    assert C.BREAK == "2022-09" and C.SENSITIVITY_BREAKS == ("2022-06", "2023-01") and C.PLACEBO_BREAK == "2019-09" and C.MATERIAL_POINTS == 3.0
    fake = tmp_path / "coding_audit.json"
    fake.write_text("{}")
    monkeypatch.setattr(C, "RESULT", fake)
    with pytest.raises(SystemExit):
        C.read()


def test_the_pre_registration_states_the_constants_the_code_uses():
    text = (ROOT / "PREREGISTRATION_V6_CODING.md").read_text(encoding="utf-8")
    for needle in ("1 September 2022", "1 June 2022", "1 January 2023", "1 September 2019", "200 flights", "1,000 cancelled", "2,000 draws", "seed 0", "4.1%"):
        assert needle in text, needle
    assert round(C.MATERIAL_POINTS / (100 * C.GAP_SHARE_STRICT), 3) == 0.041
    assert C.MIN_DENOMINATOR == 200 and C.MIN_VOLUME == 1000 and C.N_BOOT == 2000 and C.SEED == 0


def test_run_on_planted_panels_gives_the_contract_the_grader_reads():
    from mcp import grade
    y = panel(effect=-6.0, airlines=("AA", "DL", "UA", "F9"))
    res = C.run({"Y1": y, "Y2": y.copy()}, ("weather", "faa"), n_boot=40)
    assert res["airlines"] == ["AA", "DL", "UA"] and res["difference_in_differences"] is not None
    assert set(res["primary"]) == {"Y1", "Y2"} and "effect" in res["placebo"]["Y1"]
    g = grade.grade_coding(res)
    assert g["C1"]["pass"] and not g["C2"]["pass"]                      # no placebo effect; the planted fall is a real one


def test_part_7e_quotes_the_numbers_in_the_results_file():
    import json
    d = json.loads((ROOT / "results" / "coding_audit.json").read_text(encoding="utf-8"))
    text = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7E."):]
    sign = lambda x: f"{x:+.1f}".replace("-", "−")
    for label, block in (("Placebo, break 1 September 2019", d["placebo"]), ("Break 1 September 2022", d["primary"]),
                         ("Break 1 June 2022", d["sensitivity_breaks"]["2022-06"]), ("Break 1 January 2023", d["sensitivity_breaks"]["2023-01"]),
                         ("Committing airlines against Frontier", d["difference_in_differences"])):
        for y in ("Y1", "Y2"):
            row = [l for l in part.splitlines() if l.startswith(f"| {label} | {y} |")][0]
            cells = [c.strip() for c in row.strip("|").split("|")]
            e, (lo, hi) = block[y]["effect"], block[y]["ci"]
            assert cells[2] == sign(e) and cells[3] == f"{sign(lo)} to {sign(hi)}" and cells[4] == str(block[y]["airline_months"]), row
    for a, name in (("AA", "American"), ("DL", "Delta"), ("UA", "United"), ("WN", "Southwest")):
        assert f"{name} {sign(d['per_airline'][a]['Y1']['effect'])} and {sign(d['per_airline'][a]['Y2']['effect'])}".replace("+", "+").replace("−", "−") in part.replace("+", "+")
    from mcp import grade
    g = grade.grade_coding(d)
    assert not g["C1"]["pass"] and "C2" not in g                           # the placebo failed, so the effect is not graded
    m = d["materiality"]["claims_increase_at_estimate"]
    assert f"{100 * m['Y1']:.1f}% (Y1) and {100 * m['Y2']:.1f}% (Y2)" in part


def test_the_placebo_distribution_peaks_at_a_planted_step_and_a_larger_real_effect_falls_outside_it():
    p = panel(effect=10.0, break_ym="2019-09", seed=3)
    dist = C.placebo_distribution({"Y1": p, "Y2": p}, ("weather", "faa"))
    d = dist["Y1"]
    assert d["n_breaks"] > 20
    best = max(d["breaks"], key=lambda b: d["breaks"][b]["effect"])
    assert best == "2019-09" and d["breaks"]["2019-09"]["effect"] == pytest.approx(10.0, abs=0.7)
    assert all(v["effect"] < 10.0 for b, v in d["breaks"].items() if b != "2019-09")
    placed = C.place_real_estimates(dist, {"Y1": {"effect": -30.0}, "Y2": {"effect": 0.5 * (d["p2_5"] + d["p97_5"])}})
    assert placed["Y1"]["outside_central_95"] and placed["Y1"]["share_of_fake_at_or_below"] == 0.0 and not placed["Y2"]["outside_central_95"]


def test_a_fake_break_needs_eight_observed_months_on_each_side_and_pandemic_months_do_not_count():
    p = panel()
    b = C.fake_breaks(p)
    assert b[0] == "2018-09" and b[-1] == "2022-01"
    assert "2020-04" not in b and all("2018-01" <= x <= "2022-08" for x in b)
    assert min(sum(m < x for m in set(p["ym"]) if m >= "2018-01") for x in b) >= 8


def test_part_7l_quotes_the_numbers_in_the_placebo_distribution_file():
    import json
    d = json.loads((ROOT / "results" / "coding_placebo_distribution.json").read_text(encoding="utf-8"))
    real = json.loads((ROOT / "results" / "coding_audit.json").read_text(encoding="utf-8"))["primary"]
    text = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7L."):]
    for key, name in (("Y1", "Y1, cancellations"), ("Y2", "Y2, long delays")):
        x, r = d["distribution"][key], d["real_in_distribution"][key]
        assert r["real_effect"] == pytest.approx(real[key]["effect"])
        row = [l for l in part.splitlines() if l.startswith(f"| {name} |")][0]
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[1:] == [str(x["n_breaks"]), f"{x['p2_5']:+.1f} to {x['p97_5']:+.1f}", f"{x['min']:+.1f} to {x['max']:+.1f}",
                             f"{r['real_effect']:+.1f}", f"{100 * r['share_of_fake_at_or_below']:.0f}%"]
        assert r["outside_central_95"] and r["real_effect"] < x["min"]
    assert d["distribution"]["Y2"]["min"] > 0
