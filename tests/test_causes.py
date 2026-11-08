"""Cause attribution of missed connections, on hand-built flights with known answers."""
import datetime as dt

import duckdb
import pytest

from mcp.causes import CATEGORIES, cause_sql, shares


def run(inbound_rows, tmp_path):
    """Each inbound row: (code, cancelled, diverted, carrier_min, weather_min, nas_min, security_min, late_aircraft_min)."""
    con = duckdb.connect()
    con.execute("CREATE TABLE f (carrier VARCHAR, flight_date DATE, flight_number INT, crs_dep_hhmm SMALLINT, origin VARCHAR, dest VARCHAR, "
                "cancelled BOOLEAN, cancellation_code VARCHAR, diverted BOOLEAN, delay_carrier_min DOUBLE, delay_weather_min DOUBLE, "
                "delay_nas_min DOUBLE, delay_security_min DOUBLE, delay_late_aircraft_min DOUBLE)")
    con.execute("CREATE TABLE k (carrier VARCHAR, hub VARCHAR, origin VARCHAR, in_flight_date DATE, in_flight_number INT, in_crs_dep_hhmm SMALLINT, "
                "out_sched_dep TIMESTAMP, out_flight_date DATE, out_flight_number INT, out_crs_dep_hhmm SMALLINT, status VARCHAR, missed BOOLEAN, weight DOUBLE)")
    for i, (code, canc, div, c, w, n, s, l) in enumerate(inbound_rows):
        con.execute("INSERT INTO f VALUES ('DL', DATE '2025-03-10', ?, 800, 'MIA', 'ATL', ?, ?, ?, ?, ?, ?, ?, ?)", [i, canc, code, div, c, w, n, s, l])
        con.execute("INSERT INTO k VALUES ('DL', 'ATL', 'MIA', DATE '2025-03-10', ?, 800, TIMESTAMP '2025-03-10 12:00', DATE '2025-03-10', ?, 1200, 'ok', true, 1.0)", [i, 1000 + i])
    path = (tmp_path / "f.parquet").as_posix()
    con.execute(f"COPY f TO '{path}' (FORMAT parquet)")
    return [r[0] for r in con.execute(f"SELECT cause FROM ({cause_sql('k', path)}) ORDER BY out_flight_number").fetchall()]


def test_cancellation_codes_map_to_causes(tmp_path):
    rows = [(c, True, False, None, None, None, None, None) for c in ("A", "B", "C", "D")]
    assert run(rows, tmp_path) == ["carrier", "weather", "nas", "security"]


def test_a_late_flight_takes_its_dominant_cause(tmp_path):
    rows = [(None, False, False, 40, 10, 0, 0, 0),       # carrier dominates
            (None, False, False, 0, 5, 50, 0, 0),        # nas
            (None, False, False, 10, 0, 0, 0, 60),       # late aircraft
            (None, False, False, 0, 30, 20, 0, 0)]       # weather
    assert run(rows, tmp_path) == ["carrier", "nas", "late_aircraft", "weather"]


def test_ties_go_to_the_airline_never_to_the_gap(tmp_path):
    # conservative: when carrier minutes tie with weather, count it as the airline's (shrinks the product's claimed gap)
    assert run([(None, False, False, 20, 20, 0, 0, 0)], tmp_path) == ["carrier"]


def test_small_delays_and_diversions(tmp_path):
    rows = [(None, False, False, None, None, None, None, None),   # late under 15 min: no cause reported
            (None, False, True, None, None, None, None, None)]    # diverted
    assert run(rows, tmp_path) == ["unattributed", "diverted"]


def test_shares_and_the_two_controllable_definitions():
    s = shares([("carrier", 2.0), ("late_aircraft", 1.0), ("weather", 1.0)])
    assert s["carrier"] == pytest.approx(0.5) and s["late_aircraft"] == pytest.approx(0.25)
    assert s["controllable_strict"] == pytest.approx(0.5) and s["controllable_broad"] == pytest.approx(0.75)
    assert s["gap_strict"] == pytest.approx(0.5) and s["gap_broad"] == pytest.approx(0.25)
    assert sum(s[c] for c in CATEGORIES) == pytest.approx(1.0)
