"""Hotel commitments by airline and what they do to the gap, on a toy table with known answers."""
import json
from pathlib import Path

import pytest

from mcp.commitments import COMMITMENTS, carrier_gap, load_commitments


def toy():
    # AA: 4 weight, 1 carrier-caused. F9: 2 weight, 1 carrier-caused. XX (unnamed): 4 weight, 2 carrier-caused
    return [("AA", "carrier", 1.0), ("AA", "weather", 3.0), ("F9", "carrier", 1.0), ("F9", "nas", 1.0),
            ("XX", "carrier", 2.0), ("XX", "weather", 2.0)]


def test_a_committed_airline_pays_for_its_own_causes_and_an_uncommitted_one_does_not():
    r = carrier_gap(toy(), {"AA": True, "F9": False}, unknown_as=True)
    assert r["by_carrier"]["AA"]["gap_share_under_own_commitment"] == pytest.approx(0.75)   # weather 3 of 4
    assert r["by_carrier"]["F9"]["gap_share_under_own_commitment"] == pytest.approx(1.0)    # the whole miss is a gap
    assert r["by_carrier"]["F9"]["gap_share_uniform_rule"] == pytest.approx(0.5)
    assert r["by_carrier"]["XX"]["named_on_dot_page"] is False and r["by_carrier"]["XX"]["gap_share_under_own_commitment"] == pytest.approx(0.5)


def test_overall_gap_is_the_weighted_mix_and_the_unnamed_airline_is_shown_both_ways():
    c = {"AA": True, "F9": False}
    yes, no = carrier_gap(toy(), c, True)["overall"], carrier_gap(toy(), c, False)["overall"]
    assert yes["uniform_rule"] == pytest.approx((4 * 0.75 + 2 * 0.5 + 4 * 0.5) / 10) == no["uniform_rule"]
    assert yes["own_commitment"] == pytest.approx((4 * 0.75 + 2 * 1.0 + 4 * 0.5) / 10)
    assert no["own_commitment"] == pytest.approx((4 * 0.75 + 2 * 1.0 + 4 * 1.0) / 10)


def test_the_dated_dot_table_is_kept_and_frontier_is_the_one_named_airline_that_does_not_commit():
    raw = json.loads(Path(COMMITMENTS).read_text(encoding="utf-8"))
    assert raw["read_on"] == "2026-11-09" and len(raw["rows"]) == 10
    assert load_commitments()["F9"] is False
    assert [k for k, v in load_commitments().items() if not v] == ["F9"]
    assert sum(1 for r in raw["rows"] if r["carrier"] is None) == 1          # the unattributed row is recorded, not guessed
