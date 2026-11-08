"""The serving core: one function that turns (hub, airline, connection time, what happens if missed) into a quote.

The demo page, the command-line tool (`mcp.score`) and the API (`mcp.api`) all use the same table, `site/prices.js`,
which `mcp.demo` builds from the results files. There is deliberately no second copy of the prices.

What it serves is the frozen v1 model's price table: month-free, validated on the 2026 holdout. It does not
re-score a connection live; the table is passenger-weighted means over development connections. See
docs/product-brief.md for the operating policy (monthly recalibration) and what is not covered.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from mcp.connections import ROOT

PRICES = ROOT / "site" / "prices.js"
MODELS = {"v1": ROOT / "models" / "pmiss.joblib", "v2": ROOT / "models" / "pmiss_v2.joblib"}
NEXT_FLIGHT = ("typical", "same", "next")
OFFER_AT, REFUSE_AT = 0.9, 0.1       # same thresholds as the demo page (tests/test_service.py checks they match)
MIN_SLACK, MAX_SLACK = 45, 225       # the range the connections were built over: [MCT, MCT + 180]

CAVEATS = (
    "Connections are synthetic same-airline pairings, weighted by real route traffic; they are not observed itineraries.",
    "Costs, the target loss ratio and the price cap are assumptions, not company data.",
    "Demand is untested: an airline usually rebooks a missed connection on one ticket for free.",
    "No seasonal term. The probabilities are one model's level (calibrated on spring 2025).",
)


class QuoteError(ValueError):
    """The request cannot be priced (unknown hub or airline, connection time out of range)."""


def load_payload(path: Path = PRICES) -> dict:
    text = path.read_text(encoding="utf-8")
    return json.loads(re.sub(r"^window\.PRICES = |;\s*$", "", text))


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class PriceService:
    def __init__(self, payload: dict):
        self.payload = payload
        self.assumptions = payload["assumptions"]
        self.validation = payload["validation"]
        self._cells = {(c["hub"], c["carrier"], c["slack"]): c for c in payload["cells"]}
        self.hubs = list(payload["hubs"])
        self.carriers = {h: list(cs) for h, cs in payload["carriers"].items()}

    @classmethod
    def from_site(cls, path: Path = PRICES) -> "PriceService":
        return cls(load_payload(path))

    @staticmethod
    def bucket(slack_min: int) -> int:
        """Start of the 15-minute bucket (the last bucket is 210 to 225 minutes inclusive)."""
        if not MIN_SLACK <= slack_min <= MAX_SLACK:
            raise QuoteError(f"connection time must be between {MIN_SLACK} and {MAX_SLACK} minutes, got {slack_min}")
        return min(45 + 15 * ((slack_min - 45) // 15), 210)

    def quote(self, hub: str, slack_min: int, carrier: str | None = None, next_flight: str = "typical") -> dict:
        if hub not in self.hubs:
            raise QuoteError(f"unknown hub {hub!r}; available: {', '.join(self.hubs)}")
        if next_flight not in NEXT_FLIGHT:
            raise QuoteError(f"next_flight must be one of {', '.join(NEXT_FLIGHT)}")
        carrier = (carrier or "ALL").upper()
        if carrier != "ALL" and carrier not in self.carriers.get(hub, []):
            raise QuoteError(f"airline {carrier!r} is not listed at {hub}; available: {', '.join(self.carriers.get(hub, []))}")
        b = self.bucket(slack_min)
        cell = self._cells.get((hub, carrier, b))
        fallback = cell is None
        if fallback:
            cell = self._cells[(hub, "ALL", b)]
        price, share = cell[f"price_{next_flight}"], cell[f"offer_{next_flight}"]
        decision = "offer" if share >= OFFER_AT else "do_not_offer" if share <= REFUSE_AT else "offer_selectively"
        A = self.assumptions
        return {
            "hub": hub, "airline": "ALL" if fallback else carrier, "connection_minutes": slack_min,
            "bucket": f"{b}-{b + 14}" if b < 210 else "210-225",
            "next_flight": next_flight,
            "p_miss": cell["p"], "expected_claim_cost": round(price * A["target_loss_ratio"], 2),
            "price": round(price, 2), "average_fare": round(cell["fare"], 2),
            "price_share_of_fare": round(price / cell["fare"], 4),
            "share_within_price_cap": round(share, 4), "decision": decision,
            "used_all_airlines_fallback": fallback and carrier != "ALL",
            "sampled_connections": int(cell["n"]),
            "model": {"name": "v1 (frozen)", "validated_loss_ratio_2026": round(self.validation["holdout"]["v1"]["loss_ratio"], 4),
                      "target_loss_ratio": A["target_loss_ratio"]},
            "assumptions": {k: A[k] for k in ("rebooking_cost", "overnight_cost", "target_loss_ratio", "wtp_cap_pct", "min_p_miss")},
            "caveats": list(CAVEATS),
        }

    def provenance(self) -> dict:
        """What is being served and how to verify it: artefact hashes and the validated headline."""
        v = self.validation
        return {"model": "v1 (frozen)", "artefact_sha256": {k: sha256(p) for k, p in MODELS.items()},
                "holdout": {"window": v["holdout"]["window"], "connections": v["holdout"]["connections"],
                            "v1_loss_ratio": v["holdout"]["v1"], "target": v["target"]},
                "assumptions": self.assumptions}
