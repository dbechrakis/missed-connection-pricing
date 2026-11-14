"""mcp.schedule_features on a hand-built timetable: the counts, the padding, and that nothing about the day can enter."""
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from mcp import grade
from mcp import schedule_features as S

ROOT = Path(__file__).resolve().parents[1]


def flights():
    """Flights into and out of ORD on one day. Times are local clock times, every airport in the same zone (elapsed = clock difference)."""
    rows = []
    def add(carrier, num, origin, dest, dep, arr, date="2019-05-06", cancelled=False, actual=None, delay=0.0):
        el = (arr // 100 * 60 + arr % 100) - (dep // 100 * 60 + dep % 100)
        rows.append({"carrier": carrier, "flight_number": num, "flight_date": pd.Timestamp(date), "origin": origin, "dest": dest, "crs_dep_hhmm": dep, "crs_arr_hhmm": arr,
                     "crs_elapsed_min": float(el), "actual_elapsed_min": None if cancelled else float(el if actual is None else actual),
                     "dep_delay_min": delay, "arr_delay_min": delay, "cancelled": cancelled, "diverted": False})
    add("AA", 1, "BOS", "ORD", 800, 1005)             # arrives 10:05, in the 10:00 quarter-hour
    add("UA", 2, "LGA", "ORD", 810, 1010)             # 10:10, same quarter-hour, another network
    add("DL", 3, "ATL", "ORD", 830, 1014, cancelled=True)   # cancelled, still scheduled into the same quarter-hour
    add("AA", 4, "BOS", "ORD", 900, 1105)             # 11:05
    add("AA", 5, "ORD", "LAX", 1200, 1400)            # leaves 12:00
    add("UA", 6, "ORD", "SFO", 1210, 1500)            # 12:10, same quarter-hour
    add("AA", 7, "ORD", "LAX", 1300, 1500)            # 13:00
    for d in range(1, 26):                              # history of the BOS to ORD leg in April: scheduled 125, flown in 110
        add("AA", 1, "BOS", "ORD", 800, 1005, date=f"2019-04-{d:02d}", actual=110.0)
    return pd.DataFrame(rows)


def setup(fl, fit_pred="flight_date < DATE '2019-05-01'"):
    con = duckdb.connect()
    con.register("flights", fl)
    con.execute(f"CREATE TABLE slots AS {S.slot_counts_sql('flights', hubs=('ORD',))}")
    con.execute(f"CREATE TABLE leg_hist AS {S.leg_history_sql('flights', fit_pred)}")
    return con


def frame():
    return pd.DataFrame({"hub": ["ORD", "ORD"], "carrier": ["AA", "AA"], "origin": ["BOS", "BOS"], "in_flight_date": pd.to_datetime(["2019-05-06"] * 2),
                         "in_flight_number": [1, 4], "in_crs_dep_hhmm": [800, 900], "in_sched_arr": pd.to_datetime(["2019-05-06 10:05", "2019-05-06 11:05"]),
                         "out_sched_dep": pd.to_datetime(["2019-05-06 12:00", "2019-05-06 13:00"]), "keep": ["first", "second"]})


def test_the_counts_include_other_networks_and_cancelled_flights_and_the_padding_is_scheduled_minus_the_median_flown():
    out = S.attach(setup(flights()), frame())
    assert out["keep"].tolist() == ["first", "second"]                    # order and other columns are kept
    assert out["hub_arr_15"].tolist() == [3.0, 1.0]                       # AA, UA and the cancelled DL flight share 10:00 to 10:14
    assert out["hub_dep_15"].tolist() == [2.0, 1.0]
    assert out["in_block_pad"].tolist() == [15.0, 15.0]                   # scheduled 125 minutes, the leg's median in the fit window 110


def test_a_leg_with_too_little_history_has_no_padding_value():
    fl = flights()
    fl = fl[~((fl["flight_date"] < "2019-05-01") & (fl["flight_date"] > "2019-04-10"))]      # ten history flights only
    out = S.attach(setup(fl), frame())
    assert out["in_block_pad"].isna().all() and S.MIN_LEG_FLIGHTS == 20


def test_nothing_about_the_day_of_travel_can_change_a_feature():
    """Leakage test: rewrite every actual time, delay and cancellation on and after the fit window's end. No feature moves."""
    fl = flights()
    base = S.attach(setup(fl), frame())
    later = fl["flight_date"] >= "2019-05-01"
    fl2 = fl.copy()
    fl2.loc[later, "actual_elapsed_min"] = 999.0
    fl2.loc[later, ["dep_delay_min", "arr_delay_min"]] = 480.0
    fl2.loc[later, "cancelled"] = True
    alt = S.attach(setup(fl2), frame())
    pd.testing.assert_frame_equal(base, alt)
    src = Path(S.__file__).read_text(encoding="utf-8")
    assert "sched_arr" in src and "sched_dep" in src and "act_arr" not in src and "arr_delay" not in src


def test_history_after_the_fit_window_does_not_enter_the_padding():
    fl = flights()
    extra = fl[fl["flight_date"] < "2019-05-01"].copy()
    extra["flight_date"] = extra["flight_date"] + pd.Timedelta(days=60)                         # June: after the fit window
    extra["actual_elapsed_min"] = 60.0
    out = S.attach(setup(pd.concat([fl, extra], ignore_index=True)), frame())
    assert out["in_block_pad"].tolist() == [15.0, 15.0]


def test_weighted_log_loss_matches_a_hand_calculation():
    assert S.weighted_log_loss([1, 0], [0.5, 0.5], [1, 3]) == pytest.approx(np.log(2))
    assert S.weighted_log_loss([1, 0], [0.9, 0.2], [2, 1]) == pytest.approx(-(2 * np.log(0.9) + np.log(0.8)) / 3)


def test_the_expectation_is_graded_by_the_tie_band_the_document_states():
    text = (ROOT / "PREREGISTRATION_V6_SCHEDULE.md").read_text(encoding="utf-8")
    assert "Gain ≤ 0.0002" in text and S.TIE_BAND == 0.0002 and S.FIT == ("2018-01", "2023-01") and S.TEST == ("2023-01", "2023-12") and S.FRAC == 0.20
    for f in S.FEATURES:
        assert f"`{f}`" in text
    assert grade.grade_schedule({"gain": 0.0001, "gain_pct": 0.05, "seed_difference": 0.00005})["X1"]["pass"]
    assert not grade.grade_schedule({"gain": 0.0003, "gain_pct": 0.15, "seed_difference": 0.00005})["X1"]["pass"]
    assert grade.grade_schedule({"gain": -0.001, "gain_pct": -0.4, "seed_difference": 0.0})["X1"]["pass"]


def test_part_7h_quotes_the_numbers_in_the_results_file_and_the_failure_is_graded():
    import json
    d = json.loads((ROOT / "results" / "schedule_features.json").read_text(encoding="utf-8"))
    text = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7H."):]
    ll = d["log_loss"]
    for label, key, diff in (("Base (v1 feature set)", "base", None), ("Base, another random seed", "base_seed1", abs(ll["base"] - ll["base_seed1"])),
                             ("Base plus `hub_arr_15` alone", "only_hub_arr_15", d["gain_each_alone"]["hub_arr_15"]),
                             ("Base plus `hub_dep_15` alone", "only_hub_dep_15", d["gain_each_alone"]["hub_dep_15"]),
                             ("Base plus `in_block_pad` alone", "only_in_block_pad", d["gain_each_alone"]["in_block_pad"]),
                             ("**Base plus all three**", "all", d["gain"])):
        row = [l for l in part.splitlines() if l.startswith(f"| {label} |")][0]
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[1].strip("*") == f"{ll[key]:.6f}", row
        assert cells[2].strip("*") == ("" if diff is None else f"{diff:.6f}"), row
    assert f"**{d['gain']:.5f}**" in part and f"{d['gain_pct']:.2f}% of the base" in part and f"{d['seed_difference']:.6f}" in part
    assert f"{d['ratio']['base']:.3f} to {d['ratio']['all']:.3f}" in part and f"{d['fit_rows']:,}" in part and f"{d['test_rows']:,}" in part
    assert d["gain"] > S.TIE_BAND and not grade.grade_schedule(d)["X1"]["pass"]
    assert d["gain"] / d["seed_difference"] == pytest.approx(3.4, abs=0.1) and "about three times" in part
