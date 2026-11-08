"""DB1B route extraction and weight normalisation, on hand-built Coupon/Market CSVs."""
import duckdb
import pytest

from mcp.connections import weighted_sql
from mcp.ingest import db1b_routes_sql

COUPON_HDR = "ItinID,MktID,SeqNum,Origin,Dest,Break,RPCarrier,Extra,"
MARKET_HDR = "ItinID,MktID,MktCoupons,Passengers,MktFare,BulkFare,Extra,"


def coupon(mkt, seq, o, d, carrier="DL", brk=""):
    return f"1,{mkt},{seq},{o},{d},{brk},{carrier},x,"


def market(mkt, coupons=2, pax=1, fare=200, bulk=0):
    return f"1,{mkt},{coupons},{pax},{fare},{bulk},x,"


def routes(tmp_path, coupons, markets):
    c, m = tmp_path / "c.csv", tmp_path / "m.csv"
    c.write_text("\n".join([COUPON_HDR, *coupons]) + "\n")
    m.write_text("\n".join([MARKET_HDR, *markets]) + "\n")
    con = duckdb.connect()
    cur = con.execute(db1b_routes_sql(c.as_posix(), m.as_posix(), "2024Q1"))
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def test_basic_hub_connection(tmp_path):
    r = routes(tmp_path, [coupon(1, 1, "RDU", "CLT"), coupon(1, 2, "CLT", "LAS")], [market(1, pax=2, fare=300)])
    assert len(r) == 1
    assert (r[0]["origin"], r[0]["hub"], r[0]["destination"]) == ("RDU", "CLT", "LAS")
    assert r[0]["passengers"] == 2 and r[0]["fare_mean"] == 300


def test_fare_is_passenger_weighted(tmp_path):
    cs = [coupon(1, 1, "RDU", "CLT"), coupon(1, 2, "CLT", "LAS"),
          coupon(2, 1, "RDU", "CLT"), coupon(2, 2, "CLT", "LAS")]
    r = routes(tmp_path, cs, [market(1, pax=1, fare=100), market(2, pax=3, fare=200)])
    assert r[0]["passengers"] == 4 and r[0]["fare_mean"] == pytest.approx(175)


@pytest.mark.parametrize("cs,mk", [
    ([coupon(1, 1, "RDU", "MIA"), coupon(1, 2, "MIA", "LAS")], [market(1)]),                    # non-hub stop
    ([coupon(1, 1, "RDU", "CLT", "DL"), coupon(1, 2, "CLT", "LAS", "AA")], [market(1)]),        # carrier change
    ([coupon(1, 1, "RDU", "CLT", brk="A"), coupon(1, 2, "CLT", "LAS")], [market(1)]),           # trip break, not a connection
    ([coupon(1, 1, "RDU", "CLT"), coupon(1, 2, "CLT", "RDU")], [market(1)]),                    # A-H-A turnaround
    ([coupon(1, 1, "RDU", "CLT"), coupon(1, 2, "CLT", "LAS")], [market(1, coupons=3)]),         # not a one-stop market
    ([coupon(1, 1, "RDU", "CLT"), coupon(1, 2, "CLT", "LAS")], [market(1, bulk=1)]),            # bulk fare
    ([coupon(1, 1, "RDU", "CLT"), coupon(1, 2, "CLT", "LAS")], [market(1, fare=1)]),            # placeholder fare
    ([coupon(1, 1, "RDU", "CLT"), coupon(1, 2, "CLT", "LAS")], [market(1, fare=9000)]),         # outlier fare
    ([coupon(1, 2, "RDU", "CLT"), coupon(1, 3, "CLT", "LAS")], [market(1)]),                    # not seq 1 -> 2
])
def test_excluded_cases(tmp_path, cs, mk):
    assert routes(tmp_path, cs, mk) == []


def test_weights_split_route_passengers_across_pairings(tmp_path):
    # Route has 100 passengers and 4 scheduled pairings -> 25 each, summing back to 100.
    con = duckdb.connect()
    con.execute("CREATE TABLE k AS SELECT 'DL' carrier,'RDU' origin,'CLT' hub,'LAS' destination,'ok' status, "
                "i AS slack_min, TIMESTAMP '2025-03-10 12:00' + to_minutes(i) AS out_sched_dep FROM range(4) t(i)")
    con.execute("CREATE TABLE w AS SELECT 'DL' carrier,'RDU' origin,'CLT' hub,'LAS' destination,"
                "100.0 passengers, 250.0 fare_mean")
    k, w = tmp_path / "k.parquet", tmp_path / "w.parquet"
    con.execute(f"COPY k TO '{k.as_posix()}' (FORMAT parquet)")
    con.execute(f"COPY w TO '{w.as_posix()}' (FORMAT parquet)")
    rows = con.execute(weighted_sql(k.as_posix(), w.as_posix())).fetchall()
    assert len(rows) == 4
    weights = [r[-2] for r in rows]
    assert weights == [25.0] * 4 and sum(weights) == 100.0


def test_weight_split_is_per_month_and_ignores_other_months(tmp_path):
    # March has 4 pairings, April has 1. Each month's weights sum to the route's 100 passengers,
    # and adding April rows must not change March's weights (no look-ahead into later months).
    con = duckdb.connect()
    con.execute("CREATE TABLE k AS SELECT 'DL' carrier,'RDU' origin,'CLT' hub,'LAS' destination,'ok' status, "
                "i AS slack_min, TIMESTAMP '2025-03-10 12:00' + to_minutes(i) AS out_sched_dep FROM range(4) t(i)")
    con.execute("CREATE TABLE w AS SELECT 'DL' carrier,'RDU' origin,'CLT' hub,'LAS' destination,"
                "100.0 passengers, 250.0 fare_mean")
    w = tmp_path / "w.parquet"
    con.execute(f"COPY w TO '{w.as_posix()}' (FORMAT parquet)")
    march_only = tmp_path / "k1.parquet"
    con.execute(f"COPY k TO '{march_only.as_posix()}' (FORMAT parquet)")
    con.execute("INSERT INTO k VALUES ('DL','RDU','CLT','LAS','ok', 9, TIMESTAMP '2025-04-10 12:00')")
    both = tmp_path / "k2.parquet"
    con.execute(f"COPY k TO '{both.as_posix()}' (FORMAT parquet)")
    q = lambda f: dict((r[-3].month, r[-2]) for r in con.execute(weighted_sql(f.as_posix(), w.as_posix())).fetchall())
    assert q(march_only) == {3: 25.0}
    assert q(both) == {3: 25.0, 4: 100.0}
