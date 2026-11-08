"""Why connections are missed, and which misses the airline already pays for.

US airlines commit, on the DOT Airline Customer Service Dashboard, to rebook and to cover meals and hotels when a
disruption is within their control (crew, maintenance, their own operations). They do not for weather or the air
traffic system. So the protection product has unique value only in the gap: misses the airline is not responsible for.

BTS reports causes for every inbound flight:
  cancelled  cancellation_code  A carrier, B weather, C national air system (NAS: air traffic control, volume,
                                 non-extreme weather), D security
  late       minutes attributed to carrier, weather, NAS, security and late-arriving aircraft, reported only for
             flights 15+ minutes late; the dominant cause is the one with the most minutes
  diverted   no cause reported

"Airline-controllable" is reported two ways, because late-arriving aircraft is ambiguous (it is often the airline's own
earlier delay passed on, but BTS does not say): STRICT = carrier only; BROAD = carrier + late-arriving aircraft.
A miss after a small delay (under 15 minutes, no cause reported) is 'unattributed'.

Run:  python -m mcp.causes      (from src/; writes results/causes.json)
"""
from __future__ import annotations

import json

import duckdb

from mcp.connections import ROOT, WEIGHTED
from mcp.ingest import HUBS
from mcp.variant import sfx

FLIGHTS = (ROOT / "data" / "parquet" / sfx("ontime") / "*" / "*.parquet").as_posix()
RESULTS = ROOT / "results" / f"{sfx('causes')}.json"
CATEGORIES = ("carrier", "late_aircraft", "weather", "nas", "security", "diverted", "unattributed")


def inbound_cause_sql(flights: str = FLIGHTS) -> str:
    """Every flight into a hub with its cause category (or 'none' if it was on time and not cancelled or diverted).
    One row per (carrier, date, flight number, scheduled departure, origin, destination)."""
    hub_list = ", ".join(f"'{h}'" for h in HUBS)
    return f"""
    SELECT carrier, flight_date, flight_number, crs_dep_hhmm, origin, dest,
      CASE
        WHEN cancelled THEN CASE code WHEN 'A' THEN 'carrier' WHEN 'B' THEN 'weather' WHEN 'C' THEN 'nas'
                                      WHEN 'D' THEN 'security' ELSE 'unattributed' END
        WHEN diverted THEN 'diverted'
        WHEN greatest(COALESCE(c, 0), COALESCE(w, 0), COALESCE(n, 0), COALESCE(s, 0), COALESCE(l, 0)) = 0 THEN 'unattributed'
        WHEN COALESCE(c, 0) >= greatest(COALESCE(w, 0), COALESCE(n, 0), COALESCE(s, 0), COALESCE(l, 0)) THEN 'carrier'
        WHEN COALESCE(l, 0) >= greatest(COALESCE(w, 0), COALESCE(n, 0), COALESCE(s, 0)) THEN 'late_aircraft'
        WHEN COALESCE(w, 0) >= greatest(COALESCE(n, 0), COALESCE(s, 0)) THEN 'weather'
        WHEN COALESCE(n, 0) >= COALESCE(s, 0) THEN 'nas'
        ELSE 'security' END AS cause
    FROM (SELECT carrier, flight_date, flight_number, crs_dep_hhmm, origin, dest,
                 any_value(cancelled) AS cancelled, any_value(cancellation_code) AS code, any_value(diverted) AS diverted,
                 any_value(delay_carrier_min) AS c, any_value(delay_weather_min) AS w, any_value(delay_nas_min) AS n,
                 any_value(delay_security_min) AS s, any_value(delay_late_aircraft_min) AS l
          FROM read_parquet('{flights}') WHERE dest IN ({hub_list}) GROUP BY ALL)"""


def cause_sql(connections: str, flights: str = FLIGHTS) -> str:
    """One row per missed connection with the cause category of its inbound flight."""
    return f"""
    WITH k AS (SELECT * FROM {connections} WHERE status = 'ok' AND missed),
    i AS ({inbound_cause_sql(flights)})
    SELECT k.hub, k.carrier, k.out_sched_dep, k.weight, k.out_flight_date, k.out_flight_number, k.out_crs_dep_hhmm,
           COALESCE(i.cause, 'unattributed') AS cause
    FROM k LEFT JOIN i
      ON i.carrier = k.carrier AND i.flight_date = k.in_flight_date AND i.flight_number = k.in_flight_number
     AND i.crs_dep_hhmm = k.in_crs_dep_hhmm AND i.origin = k.origin AND i.dest = k.hub"""


def shares(rows: list[tuple]) -> dict:
    """Weighted share of each cause, and the two controllable definitions, from (cause, weight) pairs."""
    tot = sum(w for _, w in rows)
    s = {c: sum(w for k, w in rows if k == c) / tot for c in CATEGORIES}
    s["controllable_strict"] = s["carrier"]
    s["controllable_broad"] = s["carrier"] + s["late_aircraft"]
    s["gap_strict"] = 1 - s["controllable_strict"]           # what the airline does not pay for, strict reading
    s["gap_broad"] = 1 - s["controllable_broad"]
    return s


def main() -> None:
    con = duckdb.connect()
    glob = (WEIGHTED / "mct=45" / "*" / "*.parquet").as_posix()
    sev = (ROOT / "data" / "parquet" / "severity" / f"{sfx('severity_full')}.parquet").as_posix()
    con.execute(f"CREATE TABLE m AS {cause_sql(f'read_parquet({chr(39)}{glob}{chr(39)})')}")
    con.execute(f"""CREATE TABLE mo AS SELECT m.*, s.overnight FROM m LEFT JOIN read_parquet('{sev}') s
                    ON s.carrier = m.carrier AND s.flight_date = m.out_flight_date AND s.flight_number = m.out_flight_number
                   AND s.crs_dep_hhmm = m.out_crs_dep_hhmm""")
    out = {"definition": __doc__.split("Run:")[0].strip()}
    all_rows = con.execute("SELECT cause, weight FROM mo").fetchall()
    out["all_misses"] = shares(all_rows)
    out["overnight_misses"] = shares(con.execute("SELECT cause, weight FROM mo WHERE overnight").fetchall())
    out["by_hub"] = {h: shares(con.execute(f"SELECT cause, weight FROM mo WHERE hub = '{h}'").fetchall()) for h in HUBS}
    out["by_year"] = {y: shares(con.execute(f"SELECT cause, weight FROM mo WHERE year(out_sched_dep) = {y}").fetchall()) for y in (2024, 2025, 2026)}
    out["rows"] = len(all_rows)
    RESULTS.write_text(json.dumps(out, indent=2))
    a, o = out["all_misses"], out["overnight_misses"]
    print(f"{out['rows']:,} weighted missed connections, Jan 2024 to Aug 2026")
    print("cause shares (all misses):     " + "  ".join(f"{c} {a[c]:.1%}" for c in CATEGORIES))
    print("cause shares (overnight misses): " + "  ".join(f"{c} {o[c]:.1%}" for c in CATEGORIES))
    print(f"gap the airline does not pay for: strict {a['gap_strict']:.1%}, broad {a['gap_broad']:.1%}; "
          f"overnight misses: strict {o['gap_strict']:.1%}, broad {o['gap_broad']:.1%}")
    for h, s in out["by_hub"].items():
        print(f"  {h}: gap strict {s['gap_strict']:.1%}, broad {s['gap_broad']:.1%}, weather {s['weather']:.1%}, nas {s['nas']:.1%}")


if __name__ == "__main__":
    main()
