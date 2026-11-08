"""Demo data: the cell maths on a hand-built frame, and consistency of the shipped file."""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mcp.demo import MIN_CELL_ROWS, build_cells

ROOT = Path(__file__).resolve().parents[1]
CFG = {"rebooking_cost": 100, "overnight_cost": 100, "target_loss_ratio": 0.5, "wtp_cap_pct": 0.10}
GUARDS = {"min_p_miss": 0.01}


def frame(p, overnight, fare=1000.0, weight=1.0, n=MIN_CELL_ROWS * 40, slack=50, carrier="DL", hub="ATL"):
    return pd.DataFrame({"hub": hub, "carrier": carrier, "slack_min": slack, "p": p, "overnight": overnight,
                         "fare": fare, "weight": weight}, index=range(n))


def cell(df, **kw):
    cells = build_cells(df, CFG, GUARDS)
    return next(c for c in cells if c["carrier"] == kw.get("carrier", "ALL") and c["hub"] == "ATL")


def test_prices_by_hand_for_the_three_cases():
    c = cell(frame(0.10, 0))
    assert c["price_same"] == pytest.approx(0.10 * 100 / 0.5)       # 20
    assert c["price_next"] == pytest.approx(0.10 * 200 / 0.5)       # 40
    assert c["price_typical"] == pytest.approx(0.10 * 100 / 0.5)    # these connections would not overnight


def test_typical_price_follows_each_connections_own_overnight_flag():
    df = frame(0.10, 0)
    df.loc[: len(df) // 2 - 1, "overnight"] = 1                      # half overnight
    assert cell(df)["price_typical"] == pytest.approx((20 + 40) / 2)


def test_offer_share_is_the_share_of_connections_under_the_cap():
    df = frame(0.10, 0)
    df["fare"] = [150.0] * (len(df) // 2) + [250.0] * (len(df) - len(df) // 2)   # cap = 15 or 25; price 20
    assert cell(df)["offer_same"] == pytest.approx(0.5)              # only the 250-fare half is offerable


def test_the_floor_replaces_a_zero_probability():
    c = cell(frame(0.0, 0))
    assert c["price_same"] == pytest.approx(0.01 * 100 / 0.5)
    assert c["p"] == 0.0                                             # the shown probability is the model's, the price uses the floor


def test_weights_are_passenger_weights_not_row_counts():
    df = frame(0.10, 0)
    df.loc[: len(df) // 2 - 1, "p"] = 0.30
    df["weight"] = [3.0] * (len(df) // 2) + [1.0] * (len(df) - len(df) // 2)
    assert cell(df)["p"] == pytest.approx((0.30 * 3 + 0.10 * 1) / 4)


def test_thin_cells_are_dropped_and_thin_carriers_not_listed():
    big = frame(0.1, 0, n=MIN_CELL_ROWS * 40)
    thin = frame(0.1, 0, n=MIN_CELL_ROWS - 1, carrier="ZZ", slack=100)
    cells = build_cells(pd.concat([big, thin], ignore_index=True), CFG, GUARDS)
    assert not any(c["carrier"] == "ZZ" for c in cells)
    assert not any(c["slack"] == 100 for c in cells)


# ---- the shipped file ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def prices():
    path = ROOT / "site" / "prices.js"
    if not path.exists():
        pytest.skip("site/prices.js not built")
    return json.loads(re.sub(r"^window\.PRICES = |;\s*$", "", path.read_text(encoding="utf-8")))


def test_shipped_cells_are_valid_probabilities_and_prices(prices):
    for c in prices["cells"]:
        assert 0 < c["p"] < 1 and c["fare"] > 0
        for k in ("typical", "same", "next"):
            assert c[f"price_{k}"] > 0 and 0 <= c[f"offer_{k}"] <= 1
        assert c["price_same"] <= c["price_typical"] + 1e-6 <= c["price_next"] + 2e-6


def test_shipped_miss_probability_falls_with_connection_time_for_every_hub(prices):
    for hub in prices["hubs"]:
        pts = sorted((c["slack"], c["p"]) for c in prices["cells"] if c["hub"] == hub and c["carrier"] == "ALL")
        assert pts[0][1] > pts[-1][1] * 3                            # tight is much riskier than loose


def test_shipped_numbers_match_the_results_files(prices):
    h = json.loads((ROOT / "results" / "holdout.json").read_text())
    assert prices["validation"]["holdout"]["v1"]["loss_ratio"] == pytest.approx(h["overall"]["v1_iso"]["0"]["ratio"] * 0.65)
    assert prices["assumptions"]["target_loss_ratio"] == 0.65


def test_every_listed_carrier_has_an_all_carrier_fallback_in_its_hub(prices):
    for hub, cs in prices["carriers"].items():
        assert cs and any(c["hub"] == hub and c["carrier"] == "ALL" for c in prices["cells"])
