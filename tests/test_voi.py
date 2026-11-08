"""Value-of-information maths and joins, on hand-built data."""
import datetime as dt

import duckdb
import numpy as np
import pytest

from mcp import voi
from mcp.voi import DAY_OF_DELAY, DAY_OF_WEATHER, FEATURE_SETS, OUTCOME_COLUMNS, auc, capture_at


def test_no_feature_set_contains_an_outcome_column():
    for name, cols in FEATURE_SETS.items():
        assert not set(cols) & OUTCOME_COLUMNS, name


def test_day_of_sets_extend_the_booking_set_and_nothing_else():
    base = set(FEATURE_SETS["booking time only"])
    assert set(FEATURE_SETS["+ both"]) == base | set(DAY_OF_DELAY) | set(DAY_OF_WEATHER)
    assert set(FEATURE_SETS["+ inbound departure delay"]) == base | set(DAY_OF_DELAY)


def test_capture_by_hand():
    # 10 connections of equal weight, risk scores 0.9 .. 0.0; misses at the two highest scores and one low one
    p = np.linspace(0.9, 0.0, 10)
    y = np.array([1, 1, 0, 0, 0, 0, 0, 1, 0, 0])
    top20 = capture_at(y, np.ones(10), p, 0.2)             # alert the top 2: both are misses
    assert top20["misses_caught"] == pytest.approx(2 / 3) and top20["precision"] == 1.0 and top20["lift"] == pytest.approx((2 / 3) / 0.2)
    top50 = capture_at(y, np.ones(10), p, 0.5)             # top 5: still the same two
    assert top50["misses_caught"] == pytest.approx(2 / 3) and top50["precision"] == pytest.approx(2 / 5)


def test_capture_is_weighted():
    p, y = np.array([0.9, 0.1]), np.array([1, 1])
    w = np.array([1.0, 9.0])
    assert capture_at(y, w, p, 0.1)["misses_caught"] == pytest.approx(0.1)       # the top 10% of weight is the first row only


def test_auc_perfect_and_chance():
    y = np.array([0, 0, 1, 1])
    assert auc(y, np.ones(4), np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert auc(y, np.ones(4), np.array([0.5, 0.5, 0.5, 0.5])) == 0.5


def test_weather_is_matched_by_local_hour_and_converts_from_utc(tmp_path):
    # 2024-03-10 15:30 UTC is 10:30 in Chicago (daylight time has just started) and 11:30 in Atlanta
    con = duckdb.connect()
    con.execute("CREATE TABLE a (station VARCHAR, obs_utc TIMESTAMP, vis_mi DOUBLE, wind_kt DOUBLE, gust_kt DOUBLE, precip_1h_in DOUBLE, "
                "thunder BOOLEAN, snow BOOLEAN, freezing BOOLEAN, low_vis BOOLEAN, high_wind BOOLEAN)")
    con.execute("INSERT INTO a VALUES ('ORD', TIMESTAMP '2024-03-10 15:30', 0.5, 12, 30, 0.2, true, false, false, true, false), "
                "('ATL', TIMESTAMP '2024-03-10 15:30', 10, 5, NULL, 0, false, false, false, false, false)")
    path = (tmp_path / "a.parquet").as_posix()
    con.execute(f"COPY a TO '{path}' (FORMAT parquet)")
    rows = {r[0]: r for r in con.execute(f"SELECT hub, hr, wx_thunder, wx_low_vis, wx_wind_max, wx_precip FROM ({voi.weather_sql(path)})").fetchall()}
    assert rows["ORD"][1] == dt.datetime(2024, 3, 10, 10, 0) and rows["ATL"][1] == dt.datetime(2024, 3, 10, 11, 0)
    assert rows["ORD"][2] == 1 and rows["ORD"][3] == 1 and rows["ORD"][4] == 30 and rows["ORD"][5] == pytest.approx(0.2)
    assert rows["ATL"][2] == 0 and rows["ATL"][4] == 5            # greatest ignores a missing gust


def test_dayof_join_uses_the_hour_before_scheduled_arrival_and_excludes_nothing_by_itself(tmp_path):
    con = duckdb.connect()
    con.execute("CREATE TABLE fl (carrier VARCHAR, flight_date DATE, flight_number INT, crs_dep_hhmm SMALLINT, origin VARCHAR, dest VARCHAR, "
                "dep_delay_min DOUBLE, crs_elapsed_min DOUBLE, cancelled BOOLEAN)")
    con.execute("INSERT INTO fl VALUES ('DL', DATE '2024-03-10', 7, 800, 'MIA', 'ORD', 400, 180, false)")   # 3h flight, 400 min late
    con.execute("CREATE TABLE a (station VARCHAR, obs_utc TIMESTAMP, vis_mi DOUBLE, wind_kt DOUBLE, gust_kt DOUBLE, precip_1h_in DOUBLE, "
                "thunder BOOLEAN, snow BOOLEAN, freezing BOOLEAN, low_vis BOOLEAN, high_wind BOOLEAN)")
    # storm in the Chicago hour 10:00-11:00 local; the inbound is scheduled to arrive at 11:15, so the hour before that is 10:15 -> hour 10
    con.execute("INSERT INTO a VALUES ('ORD', TIMESTAMP '2024-03-10 15:30', 1, 20, NULL, 0, true, false, false, false, false)")
    fp, ap = (tmp_path / "f.parquet").as_posix(), (tmp_path / "a.parquet").as_posix()
    con.execute(f"COPY fl TO '{fp}' (FORMAT parquet)")
    con.execute(f"COPY a TO '{ap}' (FORMAT parquet)")
    voi_sql = voi.dayof_sql("SELECT 'DL' AS carrier, 'ORD' AS hub, 'MIA' AS origin, DATE '2024-03-10' AS in_flight_date, 7 AS in_flight_number, "
                            "800 AS in_crs_dep_hhmm, TIMESTAMP '2024-03-10 11:15' AS in_sched_arr", flights=fp).replace(voi.ASOS, ap)
    row = con.execute(voi_sql).fetchdf().iloc[0]
    # at 60 minutes before arrival 120 minutes have passed since scheduled departure; the plane had not left, so only "at least 120" is known
    assert row["in_dep_delay_known"] == 120 and row["in_not_departed"] == 1
    assert row["wx_thunder"] == 1 and row["in_was_cancelled"] == False        # noqa: E712


def _known(dep_delay, elapsed, tmp_path):
    """in_dep_delay_known and in_not_departed for one inbound flight, through the real SQL."""
    con = duckdb.connect()
    con.execute("CREATE TABLE fl (carrier VARCHAR, flight_date DATE, flight_number INT, crs_dep_hhmm SMALLINT, origin VARCHAR, dest VARCHAR, "
                "dep_delay_min DOUBLE, crs_elapsed_min DOUBLE, cancelled BOOLEAN)")
    con.execute(f"INSERT INTO fl VALUES ('DL', DATE '2024-03-10', 7, 800, 'MIA', 'ORD', {dep_delay}, {elapsed}, false)")
    con.execute("CREATE TABLE a (station VARCHAR, obs_utc TIMESTAMP, vis_mi DOUBLE, wind_kt DOUBLE, gust_kt DOUBLE, precip_1h_in DOUBLE, "
                "thunder BOOLEAN, snow BOOLEAN, freezing BOOLEAN, low_vis BOOLEAN, high_wind BOOLEAN)")
    con.execute("INSERT INTO a VALUES ('ORD', TIMESTAMP '2024-03-10 15:30', 1, 20, NULL, 0, false, false, false, false, false)")
    fp, ap = (tmp_path / "f.parquet").as_posix(), (tmp_path / "a.parquet").as_posix()
    con.execute(f"COPY fl TO '{fp}' (FORMAT parquet)")
    con.execute(f"COPY a TO '{ap}' (FORMAT parquet)")
    sql = voi.dayof_sql("SELECT 'DL' AS carrier, 'ORD' AS hub, 'MIA' AS origin, DATE '2024-03-10' AS in_flight_date, 7 AS in_flight_number, "
                        "800 AS in_crs_dep_hhmm, TIMESTAMP '2024-03-10 11:15' AS in_sched_arr", flights=fp).replace(voi.ASOS, ap)
    row = con.execute(sql).fetchdf().iloc[0]
    return float(row["in_dep_delay_known"]), int(row["in_not_departed"])


def test_a_flight_that_left_before_the_alert_time_reveals_its_real_delay(tmp_path):
    assert _known(20, 180, tmp_path) == (20.0, 0)          # 3h flight, left 20 minutes late: 120 minutes have passed, it had gone
    assert _known(-12, 180, tmp_path) == (-12.0, 0)        # left early


def test_a_flight_that_had_not_left_reveals_only_the_time_already_elapsed(tmp_path):
    assert _known(400, 180, tmp_path) == (120.0, 1)        # not gone at the alert time: at least 120 minutes late
    assert _known(121, 180, tmp_path) == (120.0, 1)        # one minute past the cut: still unknown
    assert _known(120, 180, tmp_path) == (120.0, 0)        # left exactly at the cut: known


def test_the_final_delay_of_a_late_departure_cannot_leak_through(tmp_path):
    # two flights that both had not left at the alert time must look identical, whatever their final delay turned out to be
    assert _known(150, 180, tmp_path) == _known(900, 180, tmp_path)


def test_a_flight_shorter_than_the_alert_lead_has_nothing_to_reveal_yet(tmp_path):
    # a 50-minute flight: the alert time is 10 minutes BEFORE its scheduled departure
    assert _known(30, 50, tmp_path) == (0.0, 1)            # not departed, nothing yet known about lateness
    assert _known(-15, 50, tmp_path) == (-15.0, 0)         # left 15 minutes early, before the alert time: known
