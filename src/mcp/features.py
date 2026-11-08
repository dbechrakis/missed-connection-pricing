"""Booking-time features only. Spec: Method 4.

A price is quoted when the passenger books, days or weeks before the flight. So a feature may
use the schedule (hub, carrier, slack, hour, weekday, month) and *history that existed then*.
It may not use anything about the day itself: the inbound flight's actual arrival, cancellation
or diversion, the outbound's actual departure, or that day's weather. Those belong to a separate
day-of product (spec: nice-to-have, value of information).

Historical statistics are computed on the FIT window only (2024), never on VALID or TEST.
For the rows that are *in* FIT, a statistic must not contain that row's own outcome, or the model
would learn from its own labels and over-trust the feature on new data. So for FIT rows each
route's statistic is computed leaving out that row's calendar month (leave-one-month-out).
Rows after FIT use the full FIT history. See docs/decisions.md.

Run:  python -m mcp.features            (from src/)
"""
from __future__ import annotations

import duckdb

from mcp.connections import ROOT, WEIGHTED
from mcp.ingest import HUBS
from mcp.split import where

FLIGHTS = (ROOT / "data" / "parquet" / "ontime" / "*" / "*.parquet").as_posix()
ASOS = (ROOT / "data" / "parquet" / "asos" / "hourly.parquet").as_posix()
OUT = ROOT / "data" / "parquet" / "features"

K = 30.0  # shrinkage: a route with few flights is pulled toward the all-route FIT average

CATEGORICAL = ["hub", "carrier"]
SCHEDULE = ["slack_min", "out_hour", "out_dow", "month", "in_arr_hour"]
ROUTE_HISTORY = ["in_delay_mean", "in_late15", "in_cancel"]
CLIMATOLOGY = ["thunder", "snow", "low_vis", "high_wind"]
FEATURES = CATEGORICAL + SCHEDULE + ROUTE_HISTORY + CLIMATOLOGY

# Columns that exist in the connection table but describe the day itself. A feature list
# containing any of these is leakage. tests/test_features.py enforces it.
FORBIDDEN = {"missed", "status", "in_cancelled", "in_diverted", "out_cancelled", "out_diverted",
             "in_act_arr", "out_act_dep", "weight", "fare_mean", "y"}

# The windows below are the default build sizes (rows sampled per window).
SAMPLE_ROWS = {"FIT": 4_000_000, "VALID1": 2_000_000, "VALID2": 3_000_000}


def create_stats(con, flights: str = FLIGHTS, asos: str = ASOS, fit_flights: str | None = None,
                 fit_asos: str | None = None, hubs=HUBS) -> None:
    """Build the FIT-only lookup tables: leg_month, leg_tot, prior, clim."""
    fit_flights = fit_flights or where("FIT", "flight_date")
    fit_asos = fit_asos or where("FIT", "obs_utc")
    hub_list = ", ".join(f"'{h}'" for h in hubs)
    comp = "NOT cancelled AND NOT diverted AND arr_delay_min IS NOT NULL"
    con.execute(f"""
      CREATE OR REPLACE TABLE leg_month AS
      SELECT carrier, origin, dest, date_trunc('month', flight_date)::DATE AS ym,
             count(*) AS n_all, sum((cancelled OR diverted)::INT) AS n_bad,
             count(*) FILTER (WHERE {comp}) AS n_comp,
             COALESCE(sum(greatest(least(arr_delay_min, 180), -30)) FILTER (WHERE {comp}), 0) AS s_delay,
             COALESCE(sum((arr_delay_min >= 15)::INT) FILTER (WHERE {comp}), 0) AS s_late
      FROM read_parquet('{flights}')
      WHERE dest IN ({hub_list}) AND {fit_flights}
      GROUP BY carrier, origin, dest, ym""")
    con.execute("""
      CREATE OR REPLACE TABLE leg_tot AS
      SELECT carrier, origin, dest, sum(n_all) n_all, sum(n_bad) n_bad, sum(n_comp) n_comp,
             sum(s_delay) s_delay, sum(s_late) s_late
      FROM leg_month GROUP BY carrier, origin, dest""")
    con.execute("""
      CREATE OR REPLACE TABLE prior AS
      SELECT sum(s_delay) / sum(n_comp) AS delay, sum(s_late) / sum(n_comp) AS late,
             sum(n_bad) / sum(n_all) AS bad FROM leg_tot""")
    con.execute(f"""
      CREATE OR REPLACE TABLE clim AS
      SELECT station AS hub, month(obs_utc) AS month, avg(thunder::INT) AS thunder, avg(snow::INT) AS snow,
             avg(low_vis::INT) AS low_vis, avg(high_wind::INT) AS high_wind
      FROM read_parquet('{asos}') WHERE {fit_asos} GROUP BY station, month""")


def feature_sql(source: str, window_pred: str, frac: float = 1.0) -> str:
    """Features for the connections in `source` (a table/view/subquery) inside `window_pred`.

    Returns FEATURES + y + weight. `y` and `weight` are the label and DB1B weight, not features.
    `frac` keeps a deterministic hash-based fraction of rows (stable across threads and reruns).
    """
    keep = f"AND (hash(r.carrier, r.in_flight_date, r.in_flight_number, r.in_crs_dep_hhmm, r.out_flight_date, r.out_flight_number, r.out_crs_dep_hhmm) % 1000000) < {int(frac * 1_000_000)}" if frac < 1 else ""
    sub = lambda col: f"(COALESCE(t.{col}, 0) - COALESCE(m.{col}, 0))"  # leave-one-month-out when m exists
    return f"""
    SELECT r.hub, r.carrier, r.slack_min,
           hour(r.out_sched_dep) AS out_hour, dayofweek(r.out_sched_dep) AS out_dow,
           month(r.out_sched_dep) AS month, hour(r.in_sched_arr) AS in_arr_hour,
           ({sub("s_delay")} + {K} * p.delay) / ({sub("n_comp")} + {K}) AS in_delay_mean,
           ({sub("s_late")} + {K} * p.late) / ({sub("n_comp")} + {K}) AS in_late15,
           ({sub("n_bad")} + {K} * p.bad) / ({sub("n_all")} + {K}) AS in_cancel,
           c.thunder, c.snow, c.low_vis, c.high_wind,
           r.missed::INT AS y, r.weight, r.out_sched_dep
    FROM {source} r
    LEFT JOIN leg_tot t ON t.carrier = r.carrier AND t.origin = r.origin AND t.dest = r.hub
    LEFT JOIN leg_month m ON m.carrier = r.carrier AND m.origin = r.origin AND m.dest = r.hub
                         AND m.ym = date_trunc('month', r.in_flight_date)::DATE
    LEFT JOIN clim c ON c.hub = r.hub AND c.month = month(r.out_sched_dep)
    CROSS JOIN prior p
    WHERE {window_pred} {keep}
    """


def build(window: str, n_rows: int) -> int:
    """Sample ~n_rows connections from one window and write their features to Parquet."""
    con = duckdb.connect()
    create_stats(con)
    glob = (WEIGHTED / "mct=45" / "*" / "*.parquet").as_posix()
    src = f"read_parquet('{glob}')"
    (total,) = con.execute(f"SELECT count(*) FROM {src} WHERE {where(window)}").fetchone()
    frac = min(1.0, n_rows / total)
    out = OUT / f"{window}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY ({feature_sql(src, where(window, 'r.out_sched_dep'), frac)}) TO '{out.as_posix()}' "
                f"(FORMAT parquet, COMPRESSION zstd)")
    (n,) = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()
    print(f"{window}: {total:,} connections -> sampled {n:,} ({frac:.1%})")
    return n


if __name__ == "__main__":
    for w, n in SAMPLE_ROWS.items():
        build(w, n)
