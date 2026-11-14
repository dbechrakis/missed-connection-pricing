"""mcp.clear_day_counts on hand-built flights: the window, both ends, and the gate."""
import json
from pathlib import Path

import pandas as pd

from mcp import clear_day_counts as K

ROOT = Path(__file__).resolve().parents[1]


def flight(origin="ATL", dest="ORD", dep="2024-05-06 12:00", arr="2024-05-06 14:00"):
    return {"origin": origin, "dest": dest, "dep_utc": pd.Timestamp(dep, tz="UTC"), "arr_utc": pd.Timestamp(arr, tz="UTC")}


def hour(station, text):
    return (station, pd.Timestamp(text, tz="UTC"))


def test_a_flight_with_no_adverse_hour_at_either_end_is_clear():
    assert K.clear_mask(pd.DataFrame([flight()]), set(), {}).tolist() == [True]


def test_an_adverse_hour_within_three_hours_of_either_scheduled_time_makes_it_not_clear_and_four_hours_does_not():
    df = pd.DataFrame([flight(), flight(), flight(), flight()])
    adverse = {hour("ATL", "2024-05-06 09:00"), hour("ORD", "2024-05-06 17:00"), hour("ATL", "2024-05-06 08:00"), hour("ORD", "2024-05-06 18:00")}
    only_edges = K.clear_mask(df.iloc[:1], {hour("ATL", "2024-05-06 08:00")}, {})
    assert only_edges.tolist() == [True]
    assert K.clear_mask(df.iloc[:1], {hour("ATL", "2024-05-06 09:00")}, {}).tolist() == [False]
    assert K.clear_mask(df.iloc[:1], {hour("ORD", "2024-05-06 17:00")}, {}).tolist() == [False]
    assert K.clear_mask(df.iloc[:1], {hour("ORD", "2024-05-06 18:00")}, {}).tolist() == [True]
    assert adverse


def test_weather_at_the_wrong_airport_does_not_count_for_that_end():
    assert K.clear_mask(pd.DataFrame([flight()]), {hour("ORD", "2024-05-06 09:00")}, {}).tolist() == [True]
    assert K.clear_mask(pd.DataFrame([flight()]), {hour("ATL", "2024-05-06 18:00")}, {}).tolist() == [True]
    assert K.clear_mask(pd.DataFrame([flight()]), {hour("DEN", "2024-05-06 12:00")}, {}).tolist() == [True]


def test_the_summary_counts_clear_flights_by_airline_quarter_and_applies_the_gate():
    rows = [{"carrier": "AA", "ym": "2024-02", "clear": True}] * 120 + [{"carrier": "AA", "ym": "2024-02", "clear": False}] * 30
    rows += [{"carrier": "DL", "ym": "2024-05", "clear": True}] * 40
    out = K.summarise(pd.DataFrame(rows))
    assert out["clear_flights"] == 160 and out["cancelled_hub_to_hub_flights"] == 190
    assert out["per_airline"]["AA"] == {"quarters": 1, "quarters_with_enough": 1, "clear_flights": 120, "cancelled_flights": 150}
    assert out["airline_quarters_with_enough_committing"] == 1 and out["gate_passed"] is False


def test_part_7m_quotes_the_numbers_in_the_counts_file():
    d = json.loads((ROOT / "results" / "clear_day_counts.json").read_text(encoding="utf-8"))
    text = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7M."):]
    assert f"{d['cancelled_hub_to_hub_flights']:,}" in part and f"{d['clear_flights']:,}" in part and f"{100 * d['clear_share']:.1f}%" in part
    assert str(d["airline_quarters_with_enough_committing"]) in part and str(d["min_airline_quarters"]) in part
    assert d["gate_passed"] is False
    for carrier in ("AA", "DL", "UA", "WN"):
        x = d["per_airline"][carrier]
        row = [l for l in part.splitlines() if l.startswith(f"| {carrier} |")][0]
        assert [c.strip() for c in row.strip("|").split("|")][1:] == [str(x["quarters"]), str(x["cancelled_flights"]), f"{x['clear_flights']:,}", str(x["quarters_with_enough"])]
