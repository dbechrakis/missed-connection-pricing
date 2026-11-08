"""Severity (next flight, overnight), price maths and the offer rule, with hand-computed values."""
import datetime as dt

import duckdb
import numpy as np
import pandas as pd
import pytest

from mcp.pricing import cutoffs, expected_cost, load_config, offer, price, severity_sql

CFG = {"rebooking_cost": 75, "overnight_cost": 180, "target_loss_ratio": 0.65, "wtp_cap_pct": 0.10,
       "min_overnight_wait_min": 240}


# ---- price maths ------------------------------------------------------------------------------

def test_expected_cost_by_hand():
    assert expected_cost(0.2, 0, CFG) == pytest.approx(15.0)          # 0.2 x 75
    assert expected_cost(0.2, 1, CFG) == pytest.approx(51.0)          # 0.2 x (75 + 180)


def test_price_divides_by_target_loss_ratio():
    assert price(0.2, 1, CFG) == pytest.approx(51.0 / 0.65)
    assert price(0.2, 0, CFG) == pytest.approx(15.0 / 0.65)


def test_price_rises_with_probability_and_with_overnight():
    p = np.array([0.05, 0.10, 0.20])
    assert (np.diff(price(p, 0, CFG)) > 0).all()
    assert (price(p, 1, CFG) > price(p, 0, CFG)).all()


def test_zero_probability_costs_nothing():
    assert price(0.0, 1, CFG) == 0.0


def test_offer_rule_boundary_is_inclusive():
    assert offer(10.0, 100.0, CFG)            # exactly 10% of the fare
    assert not offer(10.01, 100.0, CFG)
    assert offer(np.array([5.0, 20.0]), np.array([100.0, 100.0]), CFG).tolist() == [True, False]


def test_loss_ratio_sensitivity_direction():
    # a stricter (lower) target loss ratio means a higher price
    assert price(0.1, 1, {**CFG, "target_loss_ratio": 0.55}) > price(0.1, 1, CFG)


def test_default_config_loads_with_every_parameter_and_sensitivity():
    cfg = load_config()
    for k in ("rebooking_cost", "overnight_cost", "target_loss_ratio", "wtp_cap_pct", "min_overnight_wait_min"):
        assert k in cfg
        assert cfg[k] in cfg["sensitivity"].get(k, [cfg[k]])         # the default is one of the tested values


# ---- cut-off ------------------------------------------------------------------------------------

def frame(ps):
    return pd.DataFrame({"hub": "A", "bucket": range(len(ps)), "p": ps, "overnight": 0, "fare": 100.0, "weight": 1.0})


def test_cutoff_is_first_bucket_from_which_everything_after_is_offerable():
    # offerable when price <= 10, i.e. p <= 10 x 0.65 / 75 = 0.0867
    assert cutoffs(frame([0.30, 0.20, 0.05, 0.02]), CFG) == {"A": 45 + 15 * 2}


def test_cutoff_ignores_an_early_pass_followed_by_a_later_failure():
    # bucket 1 passes but bucket 2 fails again: the sellable zone only starts after the last failure
    assert cutoffs(frame([0.30, 0.05, 0.20, 0.02]), CFG) == {"A": 45 + 15 * 3}


# ---- severity -----------------------------------------------------------------------------------

def severity(rows, min_wait=240):
    con = duckdb.connect()
    con.execute("CREATE TABLE f (carrier VARCHAR, flight_date DATE, flight_number INT, crs_dep_hhmm SMALLINT, "
                "origin VARCHAR, dest VARCHAR)")
    con.executemany("INSERT INTO f VALUES (?,?,?,?,?,?)", rows)
    path = "sev_toy.parquet"
    import os
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), path).replace("\\", "/")
    con.execute(f"COPY f TO '{path}' (FORMAT parquet)")
    cur = con.execute(severity_sql(path, min_wait, hubs=("ATL",)))
    names = [d[0] for d in cur.description]
    return {(r[names.index("flight_number")]): dict(zip(names, r)) for r in cur.fetchall()}


D10, D11 = dt.date(2025, 3, 10), dt.date(2025, 3, 11)


def test_next_flight_same_day_is_not_overnight():
    s = severity([("DL", D10, 1, 800, "ATL", "MIA"), ("DL", D10, 2, 1200, "ATL", "MIA"),
                  ("DL", D10, 3, 2000, "ATL", "MIA")])
    assert s[1]["wait_min"] == 240 and s[1]["overnight"] is False
    assert s[2]["wait_min"] == 480 and s[2]["overnight"] is False


def test_last_flight_of_the_day_is_overnight():
    s = severity([("DL", D10, 1, 1200, "ATL", "MIA"), ("DL", D10, 2, 2000, "ATL", "MIA"),
                  ("DL", D11, 3, 900, "ATL", "MIA")])
    assert s[2]["wait_min"] == 13 * 60 and s[2]["overnight"] is True


def test_short_wait_across_midnight_is_not_overnight():
    # 23:30 then 00:20 next day: later date but only 50 minutes, so no hotel
    s = severity([("DL", D10, 1, 2330, "ATL", "MIA"), ("DL", D11, 2, 20, "ATL", "MIA")])
    assert s[1]["wait_min"] == 50 and s[1]["overnight"] is False


def test_only_same_carrier_and_same_destination_count():
    s = severity([("DL", D10, 1, 800, "ATL", "MIA"), ("AA", D10, 2, 900, "ATL", "MIA"),
                  ("DL", D10, 3, 850, "ATL", "LAX"), ("DL", D10, 4, 1600, "ATL", "MIA")])
    assert s[1]["wait_min"] == 8 * 60          # DL ATL-MIA next is 16:00, not AA's 09:00 or the LAX flight


def test_flights_at_the_same_minute_are_not_each_others_fallback():
    s = severity([("DL", D10, 1, 1200, "ATL", "MIA"), ("DL", D10, 2, 1200, "ATL", "MIA"),
                  ("DL", D10, 3, 1500, "ATL", "MIA")])
    assert s[1]["wait_min"] == 180 and s[2]["wait_min"] == 180


def test_no_later_flight_in_the_data_counts_as_overnight():
    s = severity([("DL", D10, 1, 800, "ATL", "MIA")])
    assert s[1]["overnight"] is True and s[1]["wait_min"] is None


def test_overnight_threshold_is_a_parameter():
    rows = [("DL", D10, 1, 2000, "ATL", "MIA"), ("DL", D11, 2, 100, "ATL", "MIA")]   # 5h wait, next date
    assert severity(rows, min_wait=240)[1]["overnight"] is True
    assert severity(rows, min_wait=360)[1]["overnight"] is False


# ---- guard: a calibrator's zero must never become a $0 price ----------------------------------

def test_floor_turns_a_zero_probability_into_a_positive_price():
    from mcp.pricing import load_guards
    g = load_guards()
    assert price(0.0, 0, CFG) == 0.0                                   # without the guard, the defect
    assert price(0.0, 0, CFG, g) == pytest.approx(g["min_p_miss"] * 75 / 0.65)


def test_floor_does_not_touch_probabilities_above_it():
    from mcp.pricing import load_guards
    g = load_guards()
    p = np.array([0.02, 0.1, 0.4])
    assert price(p, 1, CFG, g) == pytest.approx(price(p, 1, CFG))


def test_guard_floor_is_below_every_validated_bucket_rate_so_it_only_catches_the_tail():
    from mcp.pricing import load_guards
    assert 0 < load_guards()["min_p_miss"] < 0.02                      # the lowest slack-bucket miss rate was ~2.7%
