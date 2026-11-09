"""The gap cover (v3) as a quote: the product the decision memo recommends, served from the same table as the demo page.

`site/prices_v3.js` holds, per hub and connection-time bucket, the frozen v3 model's probability that a connection is
missed overnight for a reason not coded to the airline, the average fare, and per month the GSA hotel-and-meals payout
and the share of such connections whose price fits the 5% cap. This module reproduces the demo's arithmetic exactly
(tests/test_service_gap.py drives the page's own script through every control and compares):

    model minutes = scheduled minutes - (airline's minimum - 45)      the model was built with a 45-minute minimum
    bucket        = the 15-minute bucket of the model minutes, capped at 210
    price         = probability x payout / target loss ratio            (v3, the pre-registered primary arm)
    loaded price  = price x the frozen loading (1.16, v4)

The share within the cap is measured at the unloaded price. A loading raises every price, so fewer connections fit;
the table cannot say how many for one cell, and the quote says so rather than guessing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from mcp.service import OFFER_AT, REFUSE_AT, QuoteError

ROOT = Path(__file__).resolve().parents[2]
PRICES_V3 = ROOT / "site" / "prices_v3.js"
TRAINED_MCT = 45
MCT_OPTIONS = (35, 40, 45, 50, 55, 60)       # the range checked in VALIDATION.md 5G; outside it the re-expression is untested
MIN_MINUTES, MAX_MINUTES = 35, 240           # the demo slider's range

CAVEATS = (
    "Pays the GSA hotel-and-meals rate when the connection is missed, the next flight is the next day, and BTS does not code the inbound delay to the airline.",
    "Claims can only be settled once BTS publishes the month's cause codes, about two months later.",
    "Airlines code their own delay causes; a shift toward weather coding would raise payouts.",
    "Whole months have run 20% to 40% above or below the expected payout: the margin, not the model, carries that risk.",
    "The share within the cap is measured at the unloaded price; at the loaded price it is lower.",
    "Connections are synthetic pairings within a marketing network, weighted by real route traffic.",
)


def load_payload(path: Path = PRICES_V3) -> dict:
    return json.loads(re.sub(r"^window\.PRICES_V3 = |;\s*$", "", path.read_text(encoding="utf-8")))


def bucket_for(model_minutes: int) -> int:
    return min(210, 45 + 15 * ((model_minutes - 45) // 15))


class GapCoverService:
    def __init__(self, payload: dict):
        self.payload = payload
        self.hubs = list(payload["hubs"])
        self.months = list(payload["months"])
        self.assumptions = payload["assumptions"]
        self.loading = float(payload["audit"]["loading"]["lambda"])
        self._cells = {(c["hub"], c["slack"]): c for c in payload["cells"]}

    @classmethod
    def from_site(cls, path: Path = PRICES_V3) -> "GapCoverService":
        return cls(load_payload(path))

    def quote(self, hub: str, minutes: int, month: str, mct: int = TRAINED_MCT) -> dict:
        if hub not in self.hubs:
            raise QuoteError(f"unknown hub {hub!r}; one of {', '.join(self.hubs)}")
        if month not in self.months:
            raise QuoteError(f"month must be one of {self.months[0]} to {self.months[-1]}")
        if mct not in MCT_OPTIONS:
            raise QuoteError(f"minimum connection time must be one of {', '.join(map(str, MCT_OPTIONS))} minutes")
        if not MIN_MINUTES <= minutes <= MAX_MINUTES:
            raise QuoteError(f"connection time must be {MIN_MINUTES} to {MAX_MINUTES} minutes")
        buffer = minutes - mct
        if buffer < 0:
            raise QuoteError(f"a {minutes}-minute connection is shorter than this airline's {mct}-minute minimum and is not sold")
        model_minutes = minutes - (mct - TRAINED_MCT)
        bucket = bucket_for(model_minutes)
        cell = self._cells.get((hub, bucket))
        if cell is None:
            raise QuoteError("no data for this connection")
        m = cell["months"][month]
        target = self.assumptions["target_loss_ratio"]
        price = cell["p"] * m["cost"] / target
        share = m["within_cap"]
        decision = "offer" if share >= OFFER_AT else "do_not_offer" if share <= REFUSE_AT else "offer_selectively"
        gap = self.payload["gap"][hub]
        return {
            "product": "gap cover (v3)",
            "hub": hub, "month": month, "connection_minutes": minutes, "minimum_connection_minutes": mct,
            "buffer_minutes": buffer, "model_minutes": model_minutes, "bucket": bucket,
            "p_overnight_gap": cell["p"], "payout": m["cost"],
            "price": round(price, 2), "price_loaded": round(price * self.loading, 2), "loading": self.loading,
            "average_fare": round(cell["fare"], 2), "price_share_of_fare": round(price / cell["fare"], 4),
            "share_within_price_cap_unloaded": round(share, 4), "decision": decision,
            "share_of_misses_not_airline_coded": {"strict": round(gap["strict"], 4), "broad": round(gap["broad"], 4)},
            "sampled_connections": cell["n"],
            "assumptions": {"target_loss_ratio": target, "price_cap_share_of_fare": self.assumptions["wtp_cap"],
                            "trained_minimum_connection_minutes": TRAINED_MCT},
            "caveats": list(CAVEATS),
        }
