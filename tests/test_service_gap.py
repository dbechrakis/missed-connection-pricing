"""The gap-cover quote served by the API equals what the demo page shows, for every control combination, and refuses
what the page refuses. The page's own script is driven by tests/demo_gap_harness.js (needs Node, which CI has)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mcp.api import app
from mcp.service import QuoteError
from mcp.service_gap import GapCoverService, bucket_for

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
SVC = GapCoverService.from_site()
TITLES = {"offer": "Offer", "offer_selectively": "Offer on some connections only", "do_not_offer": "Do not offer"}


def money(text: str) -> float:
    return float(text.replace("$", "").replace(",", ""))


@pytest.fixture(scope="module")
def page():
    if NODE is None:
        pytest.skip("node not installed")
    r = subprocess.run([NODE, str(ROOT / "tests" / "demo_gap_harness.js"), str(ROOT / "site" / "index.html"),
                        str(ROOT / "site" / "prices.js"), str(ROOT / "site" / "prices_v3.js")],
                       capture_output=True, text=True, timeout=300)
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_the_api_quotes_what_the_demo_page_shows_for_every_control_combination(page):
    assert page["errors"] == []
    compared = refused = 0
    for row in page["rows"]:
        if row["slack"] < row["mct"]:
            assert row["title"] == "Not bookable"
            with pytest.raises(QuoteError, match="shorter than this airline's"):
                SVC.quote(row["hub"], row["slack"], row["month"], row["mct"])
            refused += 1
            continue
        q = SVC.quote(row["hub"], row["slack"], row["month"], row["mct"])
        shown = money(row["price"])
        step = 1.0 if shown >= 100 else 0.01
        assert abs(q["price"] - shown) <= step / 2 + 0.006, row
        assert abs(q["p_overnight_gap"] * 100 - float(row["p"].rstrip("%"))) <= 0.051, row
        assert q["payout"] == money(row["cost"]), row
        assert TITLES[q["decision"]] == row["title"], row
        compared += 1
    assert compared > 10_000 and refused > 0


def test_the_minimum_connection_time_shifts_the_bucket_the_way_validation_5g_describes():
    assert bucket_for(55) == 45 and bucket_for(60) == 60 and bucket_for(400) == 210
    base = SVC.quote("ORD", 90, SVC.months[0], 45)
    later = SVC.quote("ORD", 105, SVC.months[0], 60)              # the same 45-minute buffer at a 60-minute airport
    assert later["bucket"] == base["bucket"] and later["price"] == base["price"]
    assert later["price_loaded"] == pytest.approx(base["price"] * 1.16, abs=0.01)


def test_the_endpoint_validates_and_matches_the_service():
    client = TestClient(app)
    month = SVC.months[2]
    r = client.get("/gap-quote", params={"hub": "dfw", "minutes": 75, "month": month, "mct": 50})
    assert r.status_code == 200 and r.json() == json.loads(json.dumps(SVC.quote("DFW", 75, month, 50)))
    assert r.json()["share_within_price_cap_unloaded"] <= 1 and "unloaded" in " ".join(r.json()["caveats"])
    for bad in ({"hub": "JFK", "minutes": 90, "month": month}, {"hub": "ORD", "minutes": 90, "month": "2030-01"},
                {"hub": "ORD", "minutes": 90, "month": month, "mct": 70}, {"hub": "ORD", "minutes": 40, "month": month, "mct": 45},
                {"hub": "ORD", "minutes": 400, "month": month}):
        assert client.get("/gap-quote", params=bad).status_code == 422, bad
    meta = client.get("/gap-cover").json()
    assert meta["loading"] == 1.16 and meta["months"] == SVC.months and re.match(r"\d{4}-\d{2}", meta["months"][0])
