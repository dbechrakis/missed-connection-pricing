"""Command-line quotes: python -m mcp.score --hub ORD --airline UA --minutes 60 --next-flight next
                       python -m mcp.score --gap --hub ORD --minutes 90 --month 2026-12 --mct 60   (the gap cover)

Prints what the demo page shows. Exit code 2 if the request cannot be priced.
"""
from __future__ import annotations

import argparse
import json
import sys

from mcp.service import NEXT_FLIGHT, PriceService, QuoteError
from mcp.service_gap import TRAINED_MCT, GapCoverService

TEXT = {
    "offer": "OFFER protection",
    "offer_selectively": "OFFER SELECTIVELY (only some connections like this fit the price cap)",
    "do_not_offer": "DO NOT OFFER (warn the traveller or show a longer connection)",
}


def render(q: dict) -> str:
    A = q["assumptions"]
    lines = [
        f"{q['hub']} {q['airline']} connection of {q['connection_minutes']} min (bucket {q['bucket']}), if missed the next flight is: {q['next_flight']}",
        f"  chance it is missed      {q['p_miss']:.1%}   (about 1 in {round(1 / q['p_miss'])})",
        f"  expected claim cost      ${q['expected_claim_cost']:.2f}",
        f"  price                    ${q['price']:.2f}   = {q['price_share_of_fare']:.1%} of a ${q['average_fare']:.0f} average fare",
        f"  within the {A['wtp_cap_pct']:.0%} price cap     {q['share_within_price_cap']:.0%} of connections like this",
        f"  decision                 {TEXT[q['decision']]}",
    ]
    if q["used_all_airlines_fallback"]:
        lines.append("  note: too few connections for this airline here; figures are for all airlines at the hub")
    lines.append(f"  model: {q['model']['name']}, ran a {q['model']['validated_loss_ratio_2026']:.1%} loss ratio against a "
                 f"{A['target_loss_ratio']:.0%} target on Jan to Aug 2026 data. Assumptions: ${A['rebooking_cost']} to rebook, "
                 f"${A['overnight_cost']} more if the next flight is the next day. Prices are illustrative.")
    return "\n".join(lines)


def render_gap(q: dict) -> str:
    A = q["assumptions"]
    return "\n".join([
        f"{q['hub']} gap cover, {q['connection_minutes']} min connection at a {q['minimum_connection_minutes']}-min minimum "
        f"({q['buffer_minutes']} min buffer), {q['month']}",
        f"  chance of an overnight miss not coded to the airline   {q['p_overnight_gap']:.1%}",
        f"  payout (GSA hotel and meals)                           ${q['payout']:.0f}",
        f"  price                                                  ${q['price']:.2f}   = {q['price_share_of_fare']:.1%} of a ${q['average_fare']:.0f} average fare",
        f"  price with the pre-registered loading ({q['loading']:.2f})           ${q['price_loaded']:.2f}",
        f"  within the {A['price_cap_share_of_fare']:.0%} cap (unloaded price)                  {q['share_within_price_cap_unloaded']:.0%} of connections like this",
        f"  decision                                               {TEXT[q['decision']]}",
        "  " + q["caveats"][1],
    ])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Price one connection from the frozen v1 table.")
    p.add_argument("--hub", required=True)
    p.add_argument("--minutes", type=int, required=True, help="scheduled time between the flights, 45 to 225")
    p.add_argument("--airline", default=None, help="two-letter code, e.g. UA; default is all airlines at the hub")
    p.add_argument("--next-flight", default="typical", choices=NEXT_FLIGHT)
    p.add_argument("--json", action="store_true", help="print the full quote as JSON")
    p.add_argument("--gap", action="store_true", help="price the gap cover (v3) instead of the original cover")
    p.add_argument("--month", default=None, help="gap cover: month of travel, YYYY-MM")
    p.add_argument("--mct", type=int, default=TRAINED_MCT, help="gap cover: the airline's minimum connection time")
    a = p.parse_args(argv)
    if a.gap:
        svc = GapCoverService.from_site()
        try:
            q = svc.quote(a.hub.upper(), a.minutes, a.month or svc.months[0], a.mct)
        except QuoteError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(json.dumps(q, indent=1) if a.json else render_gap(q))
        return 0
    try:
        q = PriceService.from_site().quote(a.hub.upper(), a.minutes, a.airline, a.next_flight)
    except QuoteError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(q, indent=2) if a.json else render(q))
    return 0


if __name__ == "__main__":
    sys.exit(main())
