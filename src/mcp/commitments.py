"""Which airlines already pay for the hotel, and what that does to the gap the cover pays in.

The gap cover assumes the airline pays the hotel when it causes the disruption, so the cover pays only for
disruptions that are not coded to the airline. The US DOT's Airline Customer Service Dashboard lists, airline by
airline, whether each commits to a free hotel after an overnight controllable delay. As read on 9 November 2026, every
listed airline does except **Frontier**, which flies at Denver, one of the five hubs (data/external/dot/).

For an airline that does not commit, a missed connection that ends in a night away is a gap whatever its cause, so the
right trigger is "any miss", not "a miss not caused by the airline". This module measures how much that changes the
share of overnight misses the cover would pay for, carrier by carrier. It does not change the frozen v3 model or its
pre-registered test, which use the single rule for every airline.

    cd src && MCP_VARIANT=v3 python -m mcp.commitments       # writes results/commitments.json
"""
from __future__ import annotations

import json

import duckdb

from mcp.causes import cause_sql
from mcp.connections import ROOT, WEIGHTED
from mcp.ingest import HUBS
from mcp.variant import sfx

COMMITMENTS = ROOT / "data" / "external" / "dot" / "hotel_commitments.json"
RESULTS = ROOT / "results" / f"{sfx('commitments')}.json"


def load_commitments() -> dict:
    """{iata: True/False} for every airline named on the page; the unattributed row is not included."""
    rows = json.loads(COMMITMENTS.read_text(encoding="utf-8"))["rows"]
    return {r["iata"]: r["committed"] == "yes" for r in rows if r["iata"]}


def carrier_gap(rows: list[tuple], committed: dict, unknown_as: bool = True) -> dict:
    """From (carrier, cause, weight) rows of overnight misses: per carrier, its weight, the share of its misses caused
    by the airline, and the share the cover would pay for under that airline's own commitment (the whole miss if the
    airline does not commit to a hotel; the part not coded to the airline if it does). `unknown_as` is the assumption
    for an airline the page does not name."""
    tot = {}
    for car, cause, w in rows:
        a = tot.setdefault(car, {"weight": 0.0, "carrier_caused": 0.0})
        a["weight"] += w
        a["carrier_caused"] += w if cause == "carrier" else 0.0
    grand = sum(a["weight"] for a in tot.values())
    out = {}
    for car, a in sorted(tot.items()):
        status = committed.get(car, unknown_as)
        gap = 1.0 if not status else 1.0 - a["carrier_caused"] / a["weight"]
        out[car] = {"share_of_overnight_misses": a["weight"] / grand, "airline_commits_to_hotel": status,
                    "named_on_dot_page": car in committed, "carrier_caused_share": a["carrier_caused"] / a["weight"],
                    "gap_share_under_own_commitment": gap, "gap_share_uniform_rule": 1.0 - a["carrier_caused"] / a["weight"]}
    overall = {"uniform_rule": sum(v["share_of_overnight_misses"] * v["gap_share_uniform_rule"] for v in out.values()),
               "own_commitment": sum(v["share_of_overnight_misses"] * v["gap_share_under_own_commitment"] for v in out.values())}
    return {"by_carrier": out, "overall": overall}


def main() -> None:
    committed = load_commitments()
    con = duckdb.connect()
    glob = (WEIGHTED / "mct=45" / "*" / "*.parquet").as_posix()
    sev = (ROOT / "data" / "parquet" / "severity" / f"{sfx('severity_full')}.parquet").as_posix()
    con.execute(f"CREATE TABLE m AS {cause_sql(f'read_parquet({chr(39)}{glob}{chr(39)})')}")
    con.execute(f"""CREATE TABLE mo AS SELECT m.*, s.overnight FROM m LEFT JOIN read_parquet('{sev}') s
                    ON s.carrier = m.carrier AND s.flight_date = m.out_flight_date AND s.flight_number = m.out_flight_number
                   AND s.crs_dep_hhmm = m.out_crs_dep_hhmm""")
    out = {"source": "data/external/dot/hotel_commitments.json", "window": "January 2024 to August 2026, overnight misses, minimum connection time 45"}
    rows = con.execute("SELECT carrier, cause, weight FROM mo WHERE overnight").fetchall()
    # an airline the page does not name (Spirit is not confirmed) is shown both ways
    out["unnamed_airlines_committed"] = carrier_gap(rows, committed, unknown_as=True)
    out["unnamed_airlines_not_committed"] = carrier_gap(rows, committed, unknown_as=False)
    out["by_hub"] = {}
    for h in HUBS:
        r = con.execute(f"SELECT carrier, cause, weight FROM mo WHERE overnight AND hub = '{h}'").fetchall()
        out["by_hub"][h] = carrier_gap(r, committed, True)["overall"]
    RESULTS.write_text(json.dumps(out, indent=1))
    u = out["unnamed_airlines_committed"]
    print(f"gap share of overnight misses: uniform rule {u['overall']['uniform_rule']:.1%}, under each airline's own commitment {u['overall']['own_commitment']:.1%}")
    for car, v in u["by_carrier"].items():
        print(f"  {car}: {v['share_of_overnight_misses']:.1%} of overnight misses, commits={v['airline_commits_to_hotel']} (named={v['named_on_dot_page']}), "
              f"carrier-caused {v['carrier_caused_share']:.1%}, gap {v['gap_share_under_own_commitment']:.1%}")
    print("by hub:", {h: f"{v['uniform_rule']:.1%} -> {v['own_commitment']:.1%}" for h, v in out["by_hub"].items()})
    n = out["unnamed_airlines_not_committed"]["overall"]
    print(f"if the unnamed airlines do not commit either: {n['own_commitment']:.1%}")


if __name__ == "__main__":
    main()
