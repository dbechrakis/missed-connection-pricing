"""v3: the gap label, the payout, the booking-lag walk-forward and the guard on the next window."""
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from mcp import v2, v3
from mcp.calibration import month_stats

ROOT = Path(__file__).resolve().parents[1]


# ---- the gap label -------------------------------------------------------------------------------------

def _label(rows, tmp_path):
    """rows: (missed, cancelled, code, diverted, carrier_min, weather_min, nas_min, late_aircraft_min) per connection."""
    con = duckdb.connect()
    con.execute("CREATE TABLE fl (carrier VARCHAR, flight_date DATE, flight_number INT, crs_dep_hhmm SMALLINT, origin VARCHAR, dest VARCHAR, "
                "cancelled BOOLEAN, cancellation_code VARCHAR, diverted BOOLEAN, delay_carrier_min DOUBLE, delay_weather_min DOUBLE, "
                "delay_nas_min DOUBLE, delay_security_min DOUBLE, delay_late_aircraft_min DOUBLE)")
    feats = []
    for i, (missed, canc, code, div, c, w, n, l) in enumerate(rows):
        con.execute("INSERT INTO fl VALUES ('UA', DATE '2026-03-10', ?, 800, 'MIA', 'ORD', ?, ?, ?, ?, ?, ?, NULL, ?)", [i, canc, code, div, c, w, n, l])
        feats.append(f"SELECT {i} AS id, 'UA' AS carrier, 'ORD' AS hub, 'MIA' AS origin, DATE '2026-03-10' AS in_flight_date, "
                     f"{i} AS in_flight_number, 800 AS in_crs_dep_hhmm, {int(missed)} AS y")
    path = (tmp_path / "fl.parquet").as_posix()
    con.execute(f"COPY fl TO '{path}' (FORMAT parquet)")
    q = v3.gap_label_sql(" UNION ALL ".join(feats), flights=path)
    return [(r[0], r[1]) for r in con.execute(f"SELECT y_gap, cause FROM ({q}) ORDER BY id").fetchall()]


def test_gap_label_pays_only_when_missed_and_not_the_airlines_fault(tmp_path):
    rows = [(True, False, None, False, 60, 0, 0, 0),     # missed, airline's fault: no payout
            (True, False, None, False, 0, 60, 0, 0),     # missed, weather: payout
            (True, True, "C", False, None, None, None, None),   # missed, cancelled by air traffic control: payout
            (True, False, None, False, 0, 0, 0, 60),     # missed, late-arriving aircraft: payout (strict reading)
            (False, False, None, False, 0, 60, 0, 0),    # weather-delayed but made it: no payout
            (True, False, None, False, None, None, None, None)]   # small delay, no cause reported: payout
    assert _label(rows, tmp_path) == [(0, "carrier"), (1, "weather"), (1, "nas"), (1, "late_aircraft"), (0, "weather"), (1, "unattributed")]


# ---- the payout -------------------------------------------------------------------------------------------

TABLE = {"ORD": {2026: {"lodging": {m: 200.0 for m in range(1, 13)} | {4: 234.0}, "mie": 92.0}},
         "CLT": {2026: {"lodging": {m: 131.0 for m in range(1, 13)}, "mie": 80.0}}}


def test_claim_cost_is_the_sourced_night_for_overnights_and_zero_otherwise():
    df = pd.DataFrame({"hub": ["ORD", "ORD", "CLT"], "overnight": [1, 0, 1],
                       "out_sched_dep": pd.to_datetime(["2026-04-10 21:00", "2026-04-10 12:00", "2026-02-01 22:00"])})
    assert v3.claim_cost(df, TABLE).tolist() == [234 + 92, 0.0, 131 + 80]


# ---- walk-forward with a booking lag -----------------------------------------------------------------------

def _month(rate, p=0.1, n=1000):
    y = np.zeros(n)
    y[: int(rate * n)] = 1
    return pd.DataFrame({"y_gap": y, "weight": 1.0, "hub": "ORD", "p": p, "claim_cost": 300.0})


def test_with_a_one_month_lag_the_previous_month_is_not_used():
    months = {"2025-10": _month(0.30), "2025-11": _month(0.10), "2025-12": _month(0.10)}
    stats = [month_stats(k, d["hub"], d["y_gap"], d["weight"], d["p"]) for k, d in months.items()]
    res = {(r["policy"], r["k"]): r for r in v3.walk_forward(months, stats, ["2025-12"], lag=1)}
    # December, lag 1: only October is known (factor 3.0) -> predicted 0.30 against 0.10 observed -> 1/3
    assert res[("level_global", 1)]["realized_over_target"] == pytest.approx(1 / 3)
    res0 = {(r["policy"], r["k"]): r for r in v3.walk_forward(months, stats, ["2025-12"], lag=0)}
    assert res0[("level_global", 1)]["realized_over_target"] == pytest.approx(1.0)      # with no lag November (factor 1) is used


def test_a_month_never_calibrates_itself_even_without_a_lag():
    months = {"2025-12": _month(0.50)}
    stats = [month_stats("2025-12", months["2025-12"]["hub"], months["2025-12"]["y_gap"], months["2025-12"]["weight"], months["2025-12"]["p"])]
    for r in v3.walk_forward(months, stats, ["2025-12"], lag=0):
        assert r["realized_over_target"] == pytest.approx(5.0)      # no earlier month: the raw 0.1 against 0.5 observed


# ---- the selection rule is v2's, unchanged -----------------------------------------------------------------

def test_v3_uses_exactly_the_v2_selection_rule_and_candidates():
    rows = [{"policy": "iso_global", "k": 6, "log_loss": 0.2900}, {"policy": "level_global", "k": 6, "log_loss": 0.2901},
            {"policy": "level_hub", "k": 3, "log_loss": 0.2950}]
    assert v3.pick(rows) == v2.pick(rows) and v3.pick(rows)["policy"] == "level_global"
    assert ("level_hub", 3) in v2.CANDIDATES          # per-hub calibration is a candidate, as the review asked


# ---- the next window is not touched ----------------------------------------------------------------------------

def test_v3_never_names_the_next_window_or_a_month_after_august_2026():
    text = (ROOT / "src" / "mcp" / "v3.py").read_text(encoding="utf-8")
    assert not re.search(r"""where\(\s*["']NEXT["']""", text)
    assert not re.search(r"2026-(09|1[0-2])|2027-", text.replace("2026-09-01", ""))   # the only such date is the V3_SEVAL end
    assert '"2026-08"' in text


def test_v3_windows_end_before_the_next_window():
    from mcp.split import WINDOWS
    for k in ("V3_SFIT", "V3_SEVAL", "V3_FIT", "V3_CAL"):
        assert WINDOWS[k][1] <= WINDOWS["NEXT"][0], k
    assert WINDOWS["V3_FIT"][1] == WINDOWS["V3_CAL"][0]                  # calibration months are out-of-sample for the GBM
