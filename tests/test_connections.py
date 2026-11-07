"""Label logic and pairing rules, on hand-built flights where the answer is known."""
import datetime as dt

import duckdb
import pytest

from mcp.connections import connections_sql

COLS = ["flight_date", "carrier", "flight_number", "origin", "dest", "crs_dep_hhmm",
        "crs_arr_hhmm", "crs_elapsed_min", "dep_delay_min", "arr_delay_min",
        "cancelled", "diverted"]


def flight(n, origin, dest, dep, arr, elapsed, dep_delay=0.0, arr_delay=0.0,
           cancelled=False, diverted=False, carrier="DL", date="2025-03-10"):
    if cancelled:
        dep_delay = arr_delay = None
    return (dt.date.fromisoformat(date), carrier, n, origin, dest, dep, arr, elapsed,
            dep_delay, arr_delay, cancelled, diverted)


def run(rows, mct=45, extra=180):
    con = duckdb.connect()
    con.execute("""CREATE TABLE flights (flight_date DATE, carrier VARCHAR, flight_number INTEGER,
        origin VARCHAR, dest VARCHAR, crs_dep_hhmm SMALLINT, crs_arr_hhmm SMALLINT,
        crs_elapsed_min DOUBLE, dep_delay_min DOUBLE, arr_delay_min DOUBLE,
        cancelled BOOLEAN, diverted BOOLEAN)""")
    con.executemany("INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return con.execute(connections_sql("flights", mct, extra)).fetchall(), con.description


def one(rows, **kw):
    out, desc = run(rows, **kw)
    names = [d[0] for d in desc]
    assert len(out) == 1, out
    return dict(zip(names, out[0]))


# Inbound ORD->ATL lands 10:00 (hub-local); outbound ATL->MIA departs 11:00 => slack 60.
# Chicago is 1h behind Atlanta: dep 08:00 CT, 1h50 elapsed => arr 10:50 ET? use explicit numbers:
# dep 0710 CT + 120 min elapsed + 1h tz shift = 1010 ET.
def pair(in_arr_delay=0.0, out_dep_delay=0.0, in_kw=None, out_kw=None):
    i = flight(1, "ORD", "ATL", 710, 1010, 120, arr_delay=in_arr_delay, **(in_kw or {}))
    o = flight(2, "ATL", "MIA", 1110, 1300, 110, dep_delay=out_dep_delay, **(out_kw or {}))
    return [i, o]


def test_on_time_is_not_missed():
    r = one(pair())
    assert r["slack_min"] == 60 and r["status"] == "ok" and r["missed"] is False


def test_timezone_shift_recovered_from_data():
    # ORD 0710 -> ATL 1010 local with 120 min elapsed implies +1h shift; slack to 1110 is 60.
    assert one(pair())["slack_min"] == 60


def test_late_inbound_misses_only_when_strictly_beyond_mct():
    # arrives 10:00+15 late = 10:15; +45 MCT = 11:00 == departure => still made
    assert one(pair(in_arr_delay=15))["missed"] is False
    # one more minute => 11:01 > 11:00 => missed
    assert one(pair(in_arr_delay=16))["missed"] is True


def test_outbound_delay_can_save_the_connection():
    assert one(pair(in_arr_delay=60, out_dep_delay=60))["missed"] is False


def test_inbound_cancelled_is_missed():
    r = one(pair(in_kw={"cancelled": True}))
    assert r["status"] == "ok" and r["missed"] is True


def test_inbound_diverted_is_missed():
    r = one(pair(in_kw={"diverted": True}))
    assert r["missed"] is True


def test_outbound_cancelled_is_excluded_not_missed():
    r = one(pair(out_kw={"cancelled": True}))
    assert r["status"] == "outbound_cancelled" and r["missed"] is False
    # even if the inbound was also cancelled: still not a missed connection
    r = one(pair(in_kw={"cancelled": True}, out_kw={"cancelled": True}))
    assert r["status"] == "outbound_cancelled" and r["missed"] is False


@pytest.mark.parametrize("out_dep,inside", [(1054, 0), (1055, 1), (1355, 1), (1356, 0)])
def test_slack_window_is_inclusive_45_to_225(out_dep, inside):
    # inbound sched arrival 10:10 ET; MCT 45 => window 10:55 .. 13:55 inclusive
    rows = [flight(1, "ORD", "ATL", 710, 1010, 120), flight(2, "ATL", "MIA", out_dep, 1700, 110)]
    assert len(run(rows)[0]) == inside


def test_below_mct_is_not_a_connection():
    assert run([flight(1, "ORD", "ATL", 710, 1010, 120), flight(2, "ATL", "MIA", 1054, 1300, 110)])[0] == []


def test_different_carrier_not_paired():
    rows = [flight(1, "ORD", "ATL", 710, 1010, 120), flight(2, "ATL", "MIA", 1110, 1300, 110, carrier="AA")]
    assert run(rows)[0] == []


def test_same_airport_roundtrip_not_paired():
    rows = [flight(1, "ORD", "ATL", 710, 1010, 120), flight(2, "ATL", "ORD", 1110, 1300, 120)]
    assert run(rows)[0] == []


def test_non_hub_connection_airport_not_paired():
    rows = [flight(1, "ORD", "MIA", 710, 1010, 120), flight(2, "MIA", "ATL", 1110, 1300, 110)]
    assert run(rows)[0] == []


def test_overnight_arrival_across_midnight():
    # Departs 2300 on the 10th, 120 min, same tz => lands 0100 on the 11th.
    # Outbound at 0200 on the 11th is slack 60 and must pair; same *calendar* flight_date does not.
    i = flight(1, "DFW", "ATL", 2300, 100, 120, date="2025-03-10")
    o = flight(2, "ATL", "MIA", 200, 400, 110, date="2025-03-11")
    r = one([i, o])
    assert r["slack_min"] == 60


def test_hhmm_2400_means_next_midnight():
    i = flight(1, "DFW", "ATL", 2400, 100, 60, date="2025-03-10")
    o = flight(2, "ATL", "MIA", 200, 400, 110, date="2025-03-11")
    assert one([i, o])["slack_min"] == 60


def test_mct_changes_label():
    rows = pair(in_arr_delay=20)  # arrives 10:20
    assert one(rows, mct=45)["missed"] is True    # 11:05 > 11:00
    assert one(rows, mct=35)["missed"] is False   # 10:55 <= 11:00
