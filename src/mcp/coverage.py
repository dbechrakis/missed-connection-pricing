"""How much of real hub traffic the synthetic connections represent, and whether the part without a ticket-sample route
behaves differently.

Two separate questions, both answerable with data already on disk:

  1. Passenger coverage. The DB1B ticket sample says how many passengers really flew each (airline, origin, hub,
     destination) route on one ticket with a stop at one of the five hubs. What share of those passengers is on a route
     that has at least one scheduled pairing in our connections? The rest are real itineraries we do not model.
  2. Pairing coverage. Of the scheduled pairings we build, what share sits on a route with ticket-sample passengers
     (those get a weight and are used), and do the others miss at a different rate? They are dropped, so a difference
     would bias the headline.

    cd src && MCP_VARIANT=v3 python -m mcp.coverage        # writes results/coverage_v3.json
"""
from __future__ import annotations

import json

import duckdb

from mcp.connections import ROOT, WEIGHTED
from mcp.variant import sfx

CONNECTIONS = (ROOT / "data" / "parquet" / sfx("connections") / "mct=45" / "year=2026" / "*.parquet").as_posix()
ROUTES = (ROOT / "data" / "parquet" / "db1b" / f"{sfx('route_weights')}.parquet").as_posix()
RESULTS = ROOT / "results" / f"{sfx('coverage')}.json"
MONTHS = ("2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08")


def share(num: float, den: float) -> float:
    return num / den if den else float("nan")


def main() -> None:
    con = duckdb.connect()
    w = (WEIGHTED / "mct=45" / "year=2026" / "*.parquet").as_posix()
    # 1. passengers: routes with at least one pairing in the 2026 schedule we scored
    con.execute(f"""CREATE TABLE sched AS SELECT DISTINCT carrier, origin, hub, destination FROM read_parquet('{CONNECTIONS}') WHERE status = 'ok'""")
    pax = con.execute(f"""
        SELECT r.carrier, sum(r.passengers) AS pax, sum(r.passengers) FILTER (WHERE s.carrier IS NOT NULL) AS pax_with_pairing
        FROM read_parquet('{ROUTES}') r LEFT JOIN sched s USING (carrier, origin, hub, destination) GROUP BY 1""").fetchall()
    total = sum(p for _, p, _ in pax)
    by_carrier = {c: {"share_of_ticket_sample": p / total, "share_with_a_modelled_pairing": share(q or 0.0, p)} for c, p, q in pax}
    covered = sum(q or 0.0 for _, _, q in pax)
    # 2. pairings, and miss rate with and without a ticket-sample route (March to August 2026)
    con.execute(f"""CREATE TABLE rm AS SELECT carrier, origin, hub, destination, date_trunc('month', out_sched_dep) AS ym FROM read_parquet('{w}') GROUP BY ALL""")
    rows = con.execute(f"""
        SELECT rm.carrier IS NOT NULL AS routed, count(*) AS n, avg(k.missed::INT) AS miss_rate
        FROM read_parquet('{CONNECTIONS}') k
        LEFT JOIN rm ON rm.carrier = k.carrier AND rm.origin = k.origin AND rm.hub = k.hub AND rm.destination = k.destination
                    AND rm.ym = date_trunc('month', k.out_sched_dep)
        WHERE k.status = 'ok' AND k.out_sched_dep >= TIMESTAMP '2026-03-01' AND k.out_sched_dep < TIMESTAMP '2026-09-01'
        GROUP BY 1""").fetchall()
    d = {bool(r): (n, m) for r, n, m in rows}
    n_all = sum(n for n, _ in d.values())
    out = {"window": "ticket sample 2024 Q1 to 2025 Q2; pairings March to August 2026, minimum connection time 45",
           "passengers_on_routes_with_a_modelled_pairing": covered / total, "by_ticketing_carrier": by_carrier,
           "pairings": {"share_on_a_ticket_sample_route": d[True][0] / n_all, "miss_rate_routed": d[True][1], "miss_rate_unrouted": d[False][1],
                        "difference_points": 100 * (d[False][1] - d[True][1]), "count_routed": d[True][0], "count_unrouted": d[False][0]}}
    RESULTS.write_text(json.dumps(out, indent=1))
    print(f"{out['passengers_on_routes_with_a_modelled_pairing']:.1%} of ticket-sample hub passengers are on a route with a modelled pairing")
    print(f"{out['pairings']['share_on_a_ticket_sample_route']:.1%} of pairings are on a ticket-sample route; miss rate {d[True][1]:.2%} routed vs {d[False][1]:.2%} not "
          f"({out['pairings']['difference_points']:+.2f} points)")
    print({c: f"{v['share_of_ticket_sample']:.1%} of sample, {v['share_with_a_modelled_pairing']:.0%} covered" for c, v in by_carrier.items()})


if __name__ == "__main__":
    main()
