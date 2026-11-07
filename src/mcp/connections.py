"""Synthetic same-carrier connections at the 5 hubs, plus the "missed" label.

Everything here is a modelling assumption, not an observed passenger itinerary:
we pair every inbound A->H with every outbound H->B of the same carrier whose
scheduled slack falls in [MCT, MCT + extra]. Spec: docs/spec.md, Method 1-2.

Run:  python -m mcp.connections          (from src/)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import yaml

from mcp.ingest import HUBS, ROOT

SRC = ROOT / "data" / "parquet" / "ontime"
OUT = ROOT / "data" / "parquet" / "connections"
CONFIG = ROOT / "config" / "pricing.yaml"

# Status values. Only 'ok' rows enter model training; the rest are counted
# and reported separately (spec: outbound cancellation is NOT a missed connection).
OK = "ok"
OUTBOUND_CANCELLED = "outbound_cancelled"
MISSING_TIME = "missing_time"


def connections_sql(flights: str, mct: int, extra: int, hubs=HUBS) -> str:
    """SQL producing one row per synthetic connection.

    `flights` is a table/view with the schema written by ingest.py.
    """
    hub_list = ", ".join(f"'{h}'" for h in hubs)
    return f"""
    WITH t AS (
      SELECT *,
        -- hhmm -> minutes since midnight. 2400 becomes 1440, i.e. next midnight.
        (crs_dep_hhmm // 100) * 60 + crs_dep_hhmm % 100 AS dep_clock,
        (crs_arr_hhmm // 100) * 60 + crs_arr_hhmm % 100 AS arr_clock,
        flight_date::TIMESTAMP
          + to_minutes((crs_dep_hhmm // 100) * 60 + crs_dep_hhmm % 100) AS sched_dep
      FROM {flights}
      WHERE crs_dep_hhmm IS NOT NULL AND crs_arr_hhmm IS NOT NULL
    ),
    f AS (
      SELECT *,
        -- Timezone difference recovered from the data: arrival clock minus
        -- departure clock minus scheduled elapsed time is the tz shift mod 1 day.
        -- US shifts are within +-6h, so folding into (-720, 720] is unambiguous
        -- and we need no airport timezone table.
        sched_dep + to_minutes(
          crs_elapsed_min::INTEGER
          + ((((arr_clock - (dep_clock % 1440) - crs_elapsed_min::INTEGER) % 1440) + 1440 + 720) % 1440 - 720)
        ) AS sched_arr
      FROM t
      WHERE crs_elapsed_min IS NOT NULL
    ),
    legs AS (
      SELECT *,
        -- Actual times = scheduled + reported delay. Avoids re-deriving the date
        -- rollover from the actual hhmm fields. NULL when cancelled / no data.
        sched_dep + to_minutes(round(dep_delay_min)::INTEGER) AS act_dep,
        sched_arr + to_minutes(round(arr_delay_min)::INTEGER) AS act_arr
      FROM f
    ),
    pairs AS (
      SELECT
        i.carrier, i.dest AS hub, i.origin AS origin, o.dest AS destination,
        i.flight_date AS in_flight_date, i.flight_number AS in_flight_number,
        i.crs_dep_hhmm AS in_crs_dep_hhmm,
        o.flight_date AS out_flight_date, o.flight_number AS out_flight_number,
        o.crs_dep_hhmm AS out_crs_dep_hhmm,
        i.sched_arr AS in_sched_arr, o.sched_dep AS out_sched_dep,
        date_diff('minute', i.sched_arr, o.sched_dep) AS slack_min,
        i.cancelled AS in_cancelled, i.diverted AS in_diverted,
        o.cancelled AS out_cancelled, o.diverted AS out_diverted,
        i.act_arr AS in_act_arr, o.act_dep AS out_act_dep
      FROM legs i
      JOIN legs o
        ON  i.carrier = o.carrier          -- same carrier only (spec scope)
        AND i.dest = o.origin              -- inbound lands where outbound departs
        AND i.sched_arr::DATE = o.sched_dep::DATE   -- same (hub-local) day
        AND o.sched_dep >= i.sched_arr + to_minutes({mct})
        AND o.sched_dep <= i.sched_arr + to_minutes({mct + extra})
      WHERE i.dest IN ({hub_list})
        AND i.origin <> o.dest             -- drop A->H->A turnarounds
    )
    SELECT * EXCLUDE (in_act_arr, out_act_dep),
      {mct} AS mct_min,
      CASE
        WHEN out_cancelled THEN '{OUTBOUND_CANCELLED}'
        WHEN NOT out_cancelled AND out_act_dep IS NULL THEN '{MISSING_TIME}'
        WHEN NOT in_cancelled AND NOT in_diverted AND in_act_arr IS NULL THEN '{MISSING_TIME}'
        ELSE '{OK}'
      END AS status,
      -- Missed: inbound never arrives at the hub, or arrives too late.
      -- Strict '>' : arriving exactly MCT before departure is still a make.
      (NOT out_cancelled AND out_act_dep IS NOT NULL
        AND (in_cancelled OR in_diverted
             OR (in_act_arr IS NOT NULL AND in_act_arr + to_minutes({mct}) > out_act_dep))
      ) AS missed
    FROM pairs
    """


def build(mct: int, extra: int, start: str = "2024-01", end: str = "2025-12"):
    """Write connections for one MCT, one file per month of the connection date."""
    con = duckdb.connect()
    con.execute(f"CREATE VIEW flights AS SELECT * FROM read_parquet('{(SRC / '*' / '*.parquet').as_posix()}')")
    base = OUT / f"mct={mct}"
    for y, m in _months(start, end):
        first = f"{y}-{m:02d}-01"
        # Flights from the neighbouring days can pair across a month boundary
        # (a flight on the 31st lands on the 1st only if it crosses midnight).
        con.execute(f"""
          CREATE OR REPLACE TEMP VIEW month_flights AS
          SELECT * FROM flights
          WHERE flight_date BETWEEN DATE '{first}' - INTERVAL 1 DAY
                                AND DATE '{first}' + INTERVAL 1 MONTH
        """)
        out = base / f"year={y}" / f"month={m:02d}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"""
          COPY (SELECT * FROM ({connections_sql('month_flights', mct, extra)})
                WHERE out_sched_dep >= TIMESTAMP '{first}'
                  AND out_sched_dep <  TIMESTAMP '{first}' + INTERVAL 1 MONTH)
          TO '{out.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
        """)
        n, miss = con.execute(
            f"SELECT count(*), sum(missed::INT) FROM '{out.as_posix()}' WHERE status='{OK}'"
        ).fetchone()
        print(f"mct={mct} {y}-{m:02d}: {n:,} ok connections, miss rate {miss / n:.2%}")


def _months(start, end):
    from mcp.ingest import months
    return months(start, end)


if __name__ == "__main__":
    cfg = yaml.safe_load(CONFIG.read_text())["connections"]
    p = argparse.ArgumentParser()
    p.add_argument("--mct", type=int, nargs="*", default=[cfg["mct_min"]])
    p.add_argument("--start", default="2024-01")
    p.add_argument("--end", default="2025-12")
    a = p.parse_args()
    for mct in a.mct:
        build(mct, cfg["max_extra_slack_min"], a.start, a.end)


WEIGHTS = ROOT / "data" / "parquet" / "db1b" / "route_weights.parquet"


def weighted_sql(connections_glob: str, weights_path: str = WEIGHTS.as_posix()) -> str:
    """Connections joined to DB1B route weights, with a per-connection weight.

    A route (carrier, A, hub, B) has many scheduled pairings; giving each one the
    route's full passenger count would count a busy route once per pairing. So the
    route's passengers are split evenly across its pairings: weights then sum to
    the route's passengers, and a route with 40 pairings counts as much as one with 4.
    Connections on routes absent from DB1B are dropped (reported as coverage).
    """
    return f"""
    SELECT k.*, w.passengers / count(*) OVER (
             PARTITION BY k.carrier, k.origin, k.hub, k.destination) AS weight,
           w.fare_mean
    FROM read_parquet('{connections_glob}') k
    JOIN read_parquet('{weights_path}') w
      ON k.carrier = w.carrier AND k.origin = w.origin
     AND k.hub = w.hub AND k.destination = w.destination
    WHERE k.status = '{OK}'
    """
