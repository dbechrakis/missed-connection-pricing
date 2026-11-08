"""The serving layer: one table, three front ends (page, command line, API) that must agree."""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mcp import score
from mcp.api import app
from mcp.service import MAX_SLACK, MIN_SLACK, OFFER_AT, REFUSE_AT, PriceService, QuoteError, sha256

ROOT = Path(__file__).resolve().parents[1]
svc = PriceService.from_site()
client = TestClient(app)


def test_bucket_boundaries():
    assert [svc.bucket(m) for m in (45, 59, 60, 224, 225)] == [45, 45, 60, 210, 210]
    for bad in (44, 226, 0, -5):
        with pytest.raises(QuoteError):
            svc.bucket(bad)


def test_quote_matches_the_table_cell_it_comes_from():
    cell = next(c for c in svc.payload["cells"] if c["hub"] == "ORD" and c["carrier"] == "UA" and c["slack"] == 60)
    q = svc.quote("ORD", 70, "ua", "next")                        # 70 minutes is in the 60-74 bucket; airline code is case-insensitive
    assert q["p_miss"] == cell["p"] and q["price"] == round(cell["price_next"], 2)
    assert q["expected_claim_cost"] == pytest.approx(cell["price_next"] * 0.65, abs=0.01)
    assert q["bucket"] == "60-74" and q["airline"] == "UA"


def test_price_rises_with_the_chance_of_missing_and_with_an_overnight():
    tight, loose = svc.quote("DFW", 45), svc.quote("DFW", 200)
    assert tight["p_miss"] > loose["p_miss"] * 3 and tight["price"] > loose["price"] * 3
    assert svc.quote("ATL", 90, next_flight="next")["price"] > svc.quote("ATL", 90, next_flight="same")["price"]


def test_decision_follows_the_declared_thresholds():
    for hub in svc.hubs:
        for m in range(MIN_SLACK, MAX_SLACK + 1, 15):
            q = svc.quote(hub, m)
            s = q["share_within_price_cap"]
            want = "offer" if s >= OFFER_AT else "do_not_offer" if s <= REFUSE_AT else "offer_selectively"
            assert q["decision"] == want


def test_the_thresholds_match_the_demo_pages_own_code():
    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assert f"share >= {OFFER_AT}" in html and f"share <= {REFUSE_AT}" in html


def test_unknown_inputs_are_refused_with_a_reason():
    with pytest.raises(QuoteError, match="unknown hub"):
        svc.quote("JFK", 60)
    with pytest.raises(QuoteError, match="not listed at"):
        svc.quote("CLT", 60, "UA")                                # United is not at Charlotte in the table
    with pytest.raises(QuoteError, match="next_flight"):
        svc.quote("CLT", 60, next_flight="tomorrow")


def test_every_hub_and_airline_in_the_table_can_be_quoted():
    for hub, cs in svc.carriers.items():
        for c in [None, *cs]:
            assert svc.quote(hub, 100, c)["price"] > 0


# ---- the API ------------------------------------------------------------------------------------

def test_api_quote_equals_the_core_quote():
    r = client.get("/quote", params={"hub": "ord", "minutes": 60, "airline": "UA", "next_flight": "next"})
    assert r.status_code == 200
    assert r.json() == json.loads(json.dumps(svc.quote("ORD", 60, "UA", "next")))


def test_api_validates_inputs():
    assert client.get("/quote", params={"hub": "ORD", "minutes": 30}).status_code == 422
    assert client.get("/quote", params={"hub": "ORD", "minutes": 300}).status_code == 422
    assert client.get("/quote", params={"hub": "ORD", "minutes": 60, "next_flight": "tomorrow"}).status_code == 422
    r = client.get("/quote", params={"hub": "XXX", "minutes": 60})
    assert r.status_code == 422 and "unknown hub" in r.json()["detail"]
    assert client.get("/quote", params={"hub": "ORD"}).status_code == 422                 # minutes is required


def test_api_health_hubs_and_model():
    assert client.get("/health").json()["status"] == "ok"
    h = client.get("/hubs").json()
    assert set(h["hubs"]) == {"ATL", "CLT", "DEN", "DFW", "ORD"} and h["connection_minutes"] == {"min": 45, "max": 225}
    m = client.get("/model").json()
    assert m["holdout"]["target"] == 0.65 and "v1" in m["artefact_sha256"]


def test_model_endpoint_reports_the_hashes_frozen_in_the_validation_document():
    text = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    m = client.get("/model").json()["artefact_sha256"]
    if m["v1"] is None:
        pytest.skip("model artefacts not present")
    assert m["v1"] in text and m["v2"] in text


def test_quote_carries_its_caveats_and_assumptions():
    q = client.get("/quote", params={"hub": "ATL", "minutes": 90}).json()
    assert any("Demand is untested" in c for c in q["caveats"]) and q["assumptions"]["wtp_cap_pct"] == 0.1


# ---- the command line ---------------------------------------------------------------------------

def test_cli_prints_a_readable_quote(capsys):
    assert score.main(["--hub", "ORD", "--airline", "UA", "--minutes", "60", "--next-flight", "next"]) == 0
    out = capsys.readouterr().out
    assert "ORD UA connection of 60 min" in out and "price" in out and "decision" in out


def test_cli_json_matches_the_core(capsys):
    assert score.main(["--hub", "atl", "--minutes", "100", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == json.loads(json.dumps(svc.quote("ATL", 100)))


def test_cli_exit_code_two_on_an_invalid_request(capsys):
    assert score.main(["--hub", "ORD", "--minutes", "10"]) == 2
    assert "error" in capsys.readouterr().err


def test_sha256_of_a_missing_file_is_none(tmp_path):
    assert sha256(tmp_path / "nope.bin") is None
