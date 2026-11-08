"""Onward flights cancelled for reasons that are not the airline's: the events the gap cover leaves out.

The v3 label counts a connection as missed only when the inbound flight arrived too late (or was cancelled or diverted).
Pairs whose *onward* flight was cancelled are excluded, so the cover pays nothing when a storm cancels the flight a
traveller was about to board. For an airline that is a controllable event only when BTS codes it to the airline (code A);
a weather (B), air-traffic (C) or security (D) cancellation leaves the traveller with a hotel night nobody pays for.

This module measures how large those events are next to the missed connections the cover does pay for, by hub and by
month, over the same connections and weights. It changes nothing in the frozen model or its pre-registered test.

    cd src && MCP_VARIANT=v3 python -m mcp.outbound        # writes results/outbound_v3.json
"""
from __future__ import annotations

import json

import duckdb

from mcp.causes import cause_sql
from mcp.connections import ROOT, WEIGHTED
from mcp.ingest import HUBS
from mcp.variant import sfx

CONNECTIONS = ROOT / "data" / "parquet" / sfx("connections") / "mct=45" / "*" / "*.parquet"
RESULTS = ROOT / "results" / f"{sfx('outbound')}.json"
NOT_AIRLINE = ("B", "C", "D")           # weather, national air system, security
FLIGHTS = (ROOT / "data" / "parquet" / sfx("ontime") / "*" / "*.parquet").as_posix()
SEVERITY = (ROOT / "data" / "parquet" / "severity" / f"{sfx('severity_full')}.parquet").as_posix()


def summarise(rows: list[tuple]) -> dict:
    """From (hub, month, kind, weight) rows with kind 'gap_miss' or the cancellation code A/B/C/D: totals, the share of the
    events a gap cover that also paid for non-airline onward cancellations would add, by hub and by month."""
    def total(sel):
        return sum(w for h, m, k, w in rows if sel(h, m, k))
    gap = total(lambda h, m, k: k == "gap_miss")
    by = {k: total(lambda h, m, kk, k=k: kk == k) for k in ("A", "B", "C", "D")}
    extra = sum(by[k] for k in NOT_AIRLINE)
    hubs = {h: {"gap_miss": total(lambda hh, m, k, h=h: hh == h and k == "gap_miss"),
                "extra": total(lambda hh, m, k, h=h: hh == h and k in NOT_AIRLINE)} for h in sorted({r[0] for r in rows})}
    months = {m: {"gap_miss": total(lambda h, mm, k, m=m: mm == m and k == "gap_miss"),
                  "extra": total(lambda h, mm, k, m=m: mm == m and k in NOT_AIRLINE)} for m in sorted({r[1] for r in rows})}
    for d in (hubs, months):
        for v in d.values():
            v["extra_over_gap_miss"] = v["extra"] / v["gap_miss"] if v["gap_miss"] else float("nan")
    return {"gap_miss_weight": gap, "cancelled_weight_by_code": by, "extra_over_gap_miss": extra / gap, "airline_coded_over_gap_miss": by["A"] / gap,
            "by_hub": hubs, "by_month": months}


def main() -> None:
    con = duckdb.connect()
    wglob = (WEIGHTED / "mct=45" / "*" / "*.parquet").as_posix()
    # the weight of a pairing is constant within its route and month (route passengers split over the pairings), so the
    # weight of a cancelled pairing is the weight its route-month gives its other pairings
    con.execute(f"""CREATE TABLE rw AS SELECT carrier, origin, hub, destination, date_trunc('month', out_sched_dep) AS ym, any_value(weight) AS weight
                    FROM read_parquet('{wglob}') GROUP BY ALL""")
    con.execute(f"""CREATE TABLE canc AS
        SELECT k.hub, strftime(date_trunc('month', k.out_sched_dep), '%Y-%m') AS month, f.code AS kind, rw.weight
        FROM read_parquet('{CONNECTIONS.as_posix()}') k
        JOIN (SELECT carrier, flight_date, flight_number, crs_dep_hhmm, origin, any_value(cancellation_code) AS code
              FROM read_parquet('{FLIGHTS}') WHERE cancelled GROUP BY ALL) f
          ON f.carrier = k.carrier AND f.flight_date = k.out_flight_date AND f.flight_number = k.out_flight_number
         AND f.crs_dep_hhmm = k.out_crs_dep_hhmm AND f.origin = k.hub
        JOIN read_parquet('{SEVERITY}') s ON s.carrier = k.carrier AND s.flight_date = k.out_flight_date
         AND s.flight_number = k.out_flight_number AND s.crs_dep_hhmm = k.out_crs_dep_hhmm AND s.overnight
        JOIN rw ON rw.carrier = k.carrier AND rw.origin = k.origin AND rw.hub = k.hub AND rw.destination = k.destination
         AND rw.ym = date_trunc('month', k.out_sched_dep)
        WHERE k.status = 'outbound_cancelled'""")
    con.execute(f"""CREATE TABLE gap AS
        SELECT m.hub, strftime(date_trunc('month', m.out_sched_dep), '%Y-%m') AS month, 'gap_miss' AS kind, m.weight
        FROM ({cause_sql(f"read_parquet('{wglob}')")}) m
        JOIN read_parquet('{SEVERITY}') s ON s.carrier = m.carrier AND s.flight_date = m.out_flight_date
         AND s.flight_number = m.out_flight_number AND s.crs_dep_hhmm = m.out_crs_dep_hhmm AND s.overnight
        WHERE m.cause <> 'carrier'""")
    rows = con.execute("SELECT hub, month, kind, sum(weight) FROM (SELECT * FROM canc UNION ALL SELECT * FROM gap) GROUP BY ALL").fetchall()
    out = {"window": "January 2024 to August 2026, overnight events only (a next-day next flight), minimum connection time 45", **summarise(rows)}
    RESULTS.write_text(json.dumps(out, indent=1))
    print(f"gap misses the cover pays for: {out['gap_miss_weight']:,.0f} weighted; onward cancellations by code: "
          + ", ".join(f"{k} {v:,.0f}" for k, v in out["cancelled_weight_by_code"].items()))
    print(f"non-airline onward cancellations add {out['extra_over_gap_miss']:.1%} to the events; airline-coded ones (the airline pays) {out['airline_coded_over_gap_miss']:.1%}")
    print("by hub:", {h: f"{v['extra_over_gap_miss']:.0%}" for h, v in out["by_hub"].items()})


if __name__ == "__main__":
    main()
