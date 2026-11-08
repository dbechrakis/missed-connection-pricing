"""Leakage tests (spec: Validation, 'Leakage tests στο CI'): features are booking-time only and
historical statistics never contain the row's own outcome or anything after the FIT window."""
import datetime as dt

import duckdb
import pytest

from mcp.features import (CATEGORICAL, CLIMATOLOGY, FEATURES, FORBIDDEN, K, ROUTE_HISTORY, SCHEDULE,
                          create_stats, feature_sql)

FIT_FLIGHTS = "flight_date < DATE '2024-03-01'"   # toy FIT = Jan + Feb 2024
FIT_ASOS = "obs_utc < TIMESTAMP '2024-03-01'"


def test_no_feature_is_an_outcome_column():
    assert not set(FEATURES) & FORBIDDEN
    assert set(FEATURES) == set(CATEGORICAL + SCHEDULE + ROUTE_HISTORY + CLIMATOLOGY)


def test_feature_sql_emits_exactly_the_features_plus_label_weight_and_date():
    con = duckdb.connect()
    con.execute("CREATE TABLE k AS SELECT 'ATL' hub,'DL' carrier,'ORD' origin, 60 slack_min, "
                "TIMESTAMP '2024-05-01 10:00' out_sched_dep, TIMESTAMP '2024-05-01 09:00' in_sched_arr, "
                "DATE '2024-05-01' in_flight_date, true missed, 1.0 weight")
    con.execute("CREATE TABLE f (carrier VARCHAR, origin VARCHAR, dest VARCHAR, flight_date DATE, "
                "cancelled BOOLEAN, diverted BOOLEAN, arr_delay_min DOUBLE)")
    con.execute("INSERT INTO f VALUES ('DL','ORD','ATL',DATE '2024-01-10',false,false,5.0)")
    con.execute("CREATE TABLE a (station VARCHAR, obs_utc TIMESTAMP, thunder BOOLEAN, snow BOOLEAN, "
                "low_vis BOOLEAN, high_wind BOOLEAN)")
    con.execute("INSERT INTO a VALUES ('ATL', TIMESTAMP '2024-05-02', false,false,false,false)")
    _stats(con, tmp=None)
    cur = con.execute(feature_sql("k", "true"))
    cols = [d[0] for d in cur.description]
    assert set(cols) == set(FEATURES) | {"y", "weight", "out_sched_dep"}


def _stats(con, tmp):
    # create_stats reads Parquet paths; give it the toy tables via temp files.
    import os
    import tempfile
    d = tempfile.mkdtemp()
    fp, ap = os.path.join(d, "f.parquet").replace("\\", "/"), os.path.join(d, "a.parquet").replace("\\", "/")
    con.execute(f"COPY f TO '{fp}' (FORMAT parquet)")
    con.execute(f"COPY a TO '{ap}' (FORMAT parquet)")
    create_stats(con, flights=fp, asos=ap, fit_flights=FIT_FLIGHTS, fit_asos=FIT_ASOS, hubs=("ATL",))


def toy(extra_flights=(), extra_asos=()):
    """Route ORD->ATL on DL. Jan: two flights 100 min late. Feb: two on time."""
    con = duckdb.connect()
    con.execute("CREATE TABLE f (carrier VARCHAR, origin VARCHAR, dest VARCHAR, flight_date DATE, "
                "cancelled BOOLEAN, diverted BOOLEAN, arr_delay_min DOUBLE)")
    rows = [("DL", "ORD", "ATL", dt.date(2024, 1, d), False, False, 100.0) for d in (5, 6)]
    rows += [("DL", "ORD", "ATL", dt.date(2024, 2, d), False, False, 0.0) for d in (5, 6)]
    con.executemany("INSERT INTO f VALUES (?,?,?,?,?,?,?)", rows + list(extra_flights))
    con.execute("CREATE TABLE a (station VARCHAR, obs_utc TIMESTAMP, thunder BOOLEAN, snow BOOLEAN, "
                "low_vis BOOLEAN, high_wind BOOLEAN)")
    arows = [("ATL", dt.datetime(2024, 1, 5, h), True, False, False, False) for h in (1, 2)]
    con.executemany("INSERT INTO a VALUES (?,?,?,?,?,?)", arows + list(extra_asos))
    _stats(con, None)
    # one connection row per inbound month: Jan (FIT), Feb (FIT), Apr (after FIT)
    con.execute("CREATE TABLE k (hub VARCHAR, carrier VARCHAR, origin VARCHAR, slack_min INT, "
                "out_sched_dep TIMESTAMP, in_sched_arr TIMESTAMP, in_flight_date DATE, missed BOOLEAN, weight DOUBLE)")
    for m in (1, 2, 4):
        con.execute(f"INSERT INTO k VALUES ('ATL','DL','ORD',60,TIMESTAMP '2024-{m:02d}-20 10:00',"
                    f"TIMESTAMP '2024-{m:02d}-20 09:00',DATE '2024-{m:02d}-20',false,1.0)")
    return con


def delay_by_month(con):
    rows = con.execute(f"SELECT month, in_delay_mean, in_late15 FROM ({feature_sql('k', 'true')}) ORDER BY month").fetchall()
    return {m: (d, l) for m, d, l in rows}


def test_fit_rows_leave_their_own_month_out():
    # totals over FIT: sum delay 200 over 4 flights, prior delay = 50.
    # A January row must not see January's two 100-minute delays: (0 + K*50) / (2 + K).
    got = delay_by_month(toy())
    assert got[1][0] == pytest.approx((0 + K * 50) / (2 + K))
    # February row leaves out February (delay 0): (200 + K*50) / (2 + K)
    assert got[2][0] == pytest.approx((200 + K * 50) / (2 + K))


def test_rows_after_fit_use_the_full_fit_history():
    assert delay_by_month(toy())[4][0] == pytest.approx((200 + K * 50) / (4 + K))


def test_late_flight_share_is_leave_one_month_out_too():
    got = delay_by_month(toy())
    # 2 of 4 FIT flights are >=15 min late, prior 0.5. January row excludes both late ones.
    assert got[1][1] == pytest.approx((0 + K * 0.5) / (2 + K))


def test_statistics_ignore_flights_after_the_fit_window():
    # A disastrous April flight (5 hours late) must not move any statistic: stats are FIT-only.
    base = delay_by_month(toy())
    bad = delay_by_month(toy(extra_flights=[("DL", "ORD", "ATL", dt.date(2024, 4, 1), False, False, 300.0)]))
    assert base == bad


def test_cancellations_are_not_counted_as_delay_but_as_cancel_rate():
    con = toy(extra_flights=[("DL", "ORD", "ATL", dt.date(2024, 2, 7), True, False, None)])
    row = con.execute(f"SELECT in_cancel FROM ({feature_sql('k', 'true')}) WHERE month = 4").fetchone()
    # 1 cancelled of 5 FIT flights, prior 1/5: (1 + K*0.2) / (5 + K)
    assert row[0] == pytest.approx((1 + K * 0.2) / (5 + K))


def test_climatology_comes_from_fit_months_only():
    con = toy(extra_asos=[("ATL", dt.datetime(2024, 4, 5, h), True, True, True, True) for h in range(10)])
    # April observations are after FIT; the April row must see no April weather -> NULL, not 100%.
    assert con.execute(f"SELECT thunder FROM ({feature_sql('k', 'true')}) WHERE month = 4").fetchone()[0] is None
    # January row sees January's FIT thunder share (2 of 2 observations).
    assert con.execute(f"SELECT thunder FROM ({feature_sql('k', 'true')}) WHERE month = 1").fetchone()[0] == 1.0
