"""mcp.trigger on hand-built connections: the window, the overlaps and the basis-risk measures."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from mcp import trigger as T


def conn(hub="ORD", sched="2024-07-18 14:20", delay=60.0, cancelled=False, cause="weather", weight=10.0, cost=200.0, ym="2024-07"):
    return {"hub": hub, "in_sched_arr": pd.Timestamp(sched), "arr_delay_min": delay, "in_cancelled": cancelled, "in_diverted": False,
            "cause": cause, "weight": weight, "cost": cost, "ym": ym}


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_the_window_runs_from_three_hours_before_scheduled_arrival_to_actual_arrival():
    w = T.window_utc(pd.DataFrame([conn(), conn(delay=-10.0), conn(cancelled=True, delay=np.nan), conn(hub="DEN")]))
    assert w["w_start"].iloc[0] == pd.Timestamp("2024-07-18 16:20", tz="UTC")                  # 14:20 Chicago summer time is 19:20 UTC
    assert w["w_end"].iloc[0] == pd.Timestamp("2024-07-18 20:20", tz="UTC")                    # an hour late
    assert w["w_end"].iloc[1] == pd.Timestamp("2024-07-18 19:20", tz="UTC")                    # early arrivals do not shorten it
    assert w["w_end"].iloc[2] == pd.Timestamp("2024-07-18 22:20", tz="UTC")                    # cancelled: three hours after the schedule
    assert w["w_start"].iloc[3] == pd.Timestamp("2024-07-18 17:20", tz="UTC")                  # Denver is an hour behind Chicago in UTC terms


def test_overlap_is_true_when_a_program_meets_the_window_at_any_point():
    iv = [(utc("2024-07-18T18:00:00"), utc("2024-07-18T19:00:00")), (utc("2024-07-19T10:00:00"), utc("2024-07-19T11:00:00"))]
    starts = pd.Series(pd.to_datetime(["2024-07-18T16:00", "2024-07-18T18:30", "2024-07-18T19:00", "2024-07-18T19:01", "2024-07-18T09:00", "2024-07-19T05:00"], utc=True))
    ends = pd.Series(pd.to_datetime(["2024-07-18T17:59", "2024-07-18T18:40", "2024-07-18T21:00", "2024-07-18T21:00", "2024-07-19T10:30", "2024-07-19T09:59"], utc=True))
    assert T.overlaps(iv, starts, ends).tolist() == [False, True, True, False, True, False]
    assert not T.overlaps([], starts, ends).any()


def _asos(hours):
    rows = []
    for h in pd.date_range("2024-07-18 00:00", "2024-07-22 23:00", freq="h"):
        rows.append({"station": "ORD", "obs_utc": h, "thunder": h in hours, "snow": False, "freezing": False, "low_vis": False, "high_wind": False})
    return pd.DataFrame(rows)


def test_weather_overlap_counts_adverse_hours_inside_the_window_only():
    cum = T.adverse_hours(_asos({pd.Timestamp("2024-07-18 18:00")}))
    d = T.window_utc(pd.DataFrame([conn(delay=0.0), conn(sched="2024-07-18 18:00", delay=0.0), conn(sched="2024-07-19 12:00", delay=0.0)]))
    # windows (UTC): 16:20 to 19:20, 20:00 to 23:00 (18:00 Chicago is 23:00 UTC; window 20:00 to 23:00), 14:00 to 17:00 the next day
    assert T.weather_overlap(d, cum).tolist() == [True, False, False]


def test_a_window_outside_the_weather_record_is_never_a_match():
    cum = T.adverse_hours(_asos({pd.Timestamp("2024-07-18 18:00")}))
    d = T.window_utc(pd.DataFrame([conn(sched="2030-01-01 12:00", delay=0.0)]))
    assert not T.weather_overlap(d, cum).any()


def test_basis_risk_measures_on_a_toy_book():
    rows = [conn(cause="weather", sched="2024-07-18 14:20", ym="2024-07"),       # in a program, not the airline's: gap claim, paid by T1
            conn(cause="carrier", sched="2024-07-18 14:20", ym="2024-07"),       # in a program but coded to the airline: T1 pays, the cover would not
            conn(cause="nas", sched="2024-07-20 14:20", ym="2024-08"),           # a gap claim with no program and no weather: neither trigger pays
            conn(cause="weather", sched="2024-07-21 14:20", ym="2024-08")]       # a gap claim in bad weather only: T2 pays, T1 does not
    programs = [{"element": "ORD", "kind": "gs", "period": ["2024-07-18T16:30:00+00:00", "2024-07-18T18:00:00+00:00"], "cnx": False, "proposed": False,
                 "carrier_specific": False, "send": "07/18/24 16:00"}]
    asos = _asos({pd.Timestamp("2024-07-21 20:00")})
    r = T.evaluate(pd.DataFrame(rows), programs, asos)
    assert r["gap_share_of_missed_overnight"] == pytest.approx(0.75)
    assert r["T1"]["coverage"] == pytest.approx(1 / 3) and r["T1"]["leakage"] == pytest.approx(0.5) and r["T1"]["ratio"] == pytest.approx(2 / 3)
    assert r["T2"]["coverage"] == pytest.approx(2 / 3) and r["T2"]["ratio"] == pytest.approx(1.0)
    assert r["months"] == 2 and r["T1"]["share_of_missed_overnight_paid"] == pytest.approx(0.5)


def test_the_definitions_are_the_ones_the_module_states():
    assert T.WINDOW_BEFORE_H == 3 and T.CANCELLED_AFTER_H == 3 and T.ADVERSE == ("thunder", "snow", "freezing", "low_vis", "high_wind")
    text = open(T.__file__, encoding="utf-8").read()
    assert "fixed here, before any is scored" in text and "2026-09" not in text
    assert T.pandemic_free(pd.DataFrame({"ym": ["2020-02", "2020-03", "2021-06", "2021-07"]}))["ym"].tolist() == ["2020-02", "2021-07"]
