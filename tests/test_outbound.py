"""Onward cancellations the gap cover leaves out, on a toy table with known answers."""
import pytest

from mcp.outbound import NOT_AIRLINE, summarise


def rows():
    # (hub, month, kind, weight): gap misses and onward cancellations by BTS code
    return [("ATL", "2026-01", "gap_miss", 100.0), ("ATL", "2026-01", "B", 30.0), ("ATL", "2026-01", "A", 50.0),
            ("ORD", "2026-02", "gap_miss", 50.0), ("ORD", "2026-02", "C", 20.0), ("ORD", "2026-02", "D", 5.0)]


def test_only_weather_air_traffic_and_security_cancellations_are_gaps_the_airline_does_not_pay():
    assert NOT_AIRLINE == ("B", "C", "D")
    s = summarise(rows())
    assert s["gap_miss_weight"] == 150.0
    assert s["cancelled_weight_by_code"] == {"A": 50.0, "B": 30.0, "C": 20.0, "D": 5.0}
    assert s["extra_over_gap_miss"] == pytest.approx(55 / 150)             # 30 + 20 + 5 over 150
    assert s["airline_coded_over_gap_miss"] == pytest.approx(50 / 150)     # the airline pays for these: not part of the extra


def test_by_hub_and_by_month_split_the_same_events():
    s = summarise(rows())
    assert s["by_hub"]["ATL"]["extra_over_gap_miss"] == pytest.approx(30 / 100)
    assert s["by_hub"]["ORD"]["extra_over_gap_miss"] == pytest.approx(25 / 50)
    assert s["by_month"]["2026-02"]["extra"] == 25.0 and s["by_month"]["2026-01"]["gap_miss"] == 100.0
