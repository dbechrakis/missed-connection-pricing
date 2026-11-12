"""mcp.forecast: the window features are built from forecast columns only, the rule arithmetic, and the lead structure."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mcp import forecast as FC

ROOT = Path(__file__).resolve().parents[1]


def _wx(hours=48, seed=0, extra_observed=False):
    rng = np.random.default_rng(seed)
    t = pd.date_range("2025-03-01", periods=hours, freq="h")
    d = {"hour_utc": t, "hub": "ORD"}
    for lead in FC.LEADS:
        d[FC.column("precipitation", lead)] = rng.random(hours)
        d[FC.column("snowfall", lead)] = rng.random(hours) * 0.1
        d[FC.column("wind_gusts_10m", lead)] = rng.random(hours) * 50
        d[FC.column("weather_code", lead)] = rng.choice([0, 3, 61, 95, 73], hours)
    df = pd.DataFrame(d)
    if extra_observed:
        df["precipitation"] = rng.random(hours) * 100             # what actually happened on the day
        df["weather_code"] = 99
    return df


def test_the_window_covers_one_hour_before_to_three_hours_after_each_hour():
    wx = _wx()
    f = FC.window_features(wx, 3).set_index("hour_utc")
    col = wx.set_index("hour_utc")[FC.column("precipitation", 3)]
    t = pd.Timestamp("2025-03-01 10:00")
    assert f.loc[t, "fc_precip"] == pytest.approx(col.loc[t - pd.Timedelta(hours=1):t + pd.Timedelta(hours=3)].max())
    assert np.isnan(f["fc_precip"].iloc[0]) and np.isnan(f["fc_precip"].iloc[-1])     # the edges lack a full window


def test_thunder_and_wintry_flags_follow_the_weather_codes():
    wx = _wx()
    wx[FC.column("weather_code", 1)] = 0
    wx.loc[10, FC.column("weather_code", 1)] = 95
    wx.loc[30, FC.column("weather_code", 1)] = 73
    f = FC.window_features(wx, 1).set_index("hour_utc")
    t = wx["hour_utc"]
    assert f.loc[t[10 - 3], "fc_thunder"] == 1.0 and f.loc[t[10 + 1], "fc_thunder"] == 1.0 and f.loc[t[10 + 2], "fc_thunder"] == 0.0
    assert f.loc[t[30], "fc_wintry"] == 1.0 and f.loc[t[30], "fc_thunder"] == 0.0


def test_observed_weather_cannot_enter_a_forecast_feature():
    """Leakage test: rewriting the observed columns of the day changes no feature at any lead."""
    a, b = _wx(extra_observed=False), _wx(extra_observed=True)
    for lead in FC.LEADS:
        pd.testing.assert_frame_equal(FC.window_features(a, lead), FC.window_features(b, lead))
    src = Path(FC.__file__).read_text(encoding="utf-8")
    assert "previous_day" in src and "def window_features" in src


def test_features_at_each_lead_use_that_leads_columns():
    wx = _wx()
    wx[FC.column("precipitation", 7)] = 0.0
    wx[FC.column("precipitation", 1)] = 5.0
    assert FC.window_features(wx, 7)["fc_precip"].max() == 0.0 and FC.window_features(wx, 1)["fc_precip"].max() == 5.0


def test_arrival_hour_is_utc_with_daylight_saving_and_features_attach_by_hub_and_hour():
    df = pd.DataFrame({"hub": ["ORD", "DEN", "ATL"], "in_sched_arr": pd.to_datetime(["2025-07-01 14:20", "2025-07-01 14:20", "2025-01-10 14:20"])})
    h = FC.arrival_hour_utc(df)
    assert h.tolist() == [pd.Timestamp("2025-07-01 19:00"), pd.Timestamp("2025-07-01 20:00"), pd.Timestamp("2025-01-10 19:00")]
    feats = pd.DataFrame({"hub": ["ORD"], "hour_utc": [pd.Timestamp("2025-07-01 19:00")], "fc_precip": [4.2]})
    out = FC.attach(df, feats)
    assert out["fc_precip"].iloc[0] == 4.2 and out["fc_precip"].iloc[1:].isna().all() and len(out) == 3


def _book(n=400, seed=0):
    rng = np.random.default_rng(seed)
    pb = rng.uniform(0.01, 0.05, n)
    ratio = np.where(rng.random(n) < 0.15, rng.uniform(1.6, 4.0, n), rng.uniform(0.7, 1.3, n))
    y = (rng.random(n) < pb * ratio).astype(float)
    return pd.DataFrame({"weight": rng.uniform(5, 15, n), "y_gap": y, "claim_cost": 250.0, "fare": 300.0, "p_base": pb, "p_fc": pb * ratio,
                         "week": [f"2025-{1 + (i // 40) % 9:02d}-01" for i in range(n)]})


def test_the_rule_removes_only_late_buyers_with_a_ratio_above_the_threshold():
    book = _book()
    r = FC.rule_outcome(book, 0.2, 1.0, cap=0.5, target=0.65)
    assert 0 < r["share_of_sales_lost"] < 0.2 and r["with_rule"]["weight"] < r["without_rule"]["weight"]
    none = FC.rule_outcome(book.assign(p_fc=book["p_base"]), 0.2, 1.0, cap=0.5, target=0.65)          # no forecast signal: the rule never fires
    assert none["share_of_sales_lost"] == 0.0 and none["with_rule"] == none["without_rule"]
    zero = FC.rule_outcome(book, 0.0, 1.0, cap=0.5, target=0.65)                                         # nobody books late: the rule has nothing to act on
    assert zero["with_rule"]["loss_ratio"] == pytest.approx(zero["without_rule"]["loss_ratio"])


def test_the_rule_lowers_the_loss_ratio_when_the_forecast_is_informative_and_late_buyers_select_on_it():
    book = _book(4000, seed=1)
    r = FC.rule_outcome(book, 0.3, 1.0, cap=0.5, target=0.65)
    assert r["with_rule"]["loss_ratio"] < r["without_rule"]["loss_ratio"]
    flat = FC.rule_outcome(book, 0.3, 0.0, cap=0.5, target=0.65)
    assert (r["without_rule"]["loss_ratio"] - r["with_rule"]["loss_ratio"]) > 0 and flat["share_of_sales_lost"] > 0


def test_gain_is_a_percentage_of_the_base_loss():
    assert FC.gain_pct(0.25, 0.2475) == pytest.approx(1.0)
    assert FC.gain_pct(0.25, 0.26) < 0


def test_the_windows_and_the_rule_are_the_ones_the_pre_registration_states():
    text = (ROOT / "PREREGISTRATION_V6_FORECAST.md").read_text(encoding="utf-8")
    assert FC.FIT_WINDOW == ("2024-02-01", "2025-09-01") and FC.TEST_WINDOW == ("2025-09-01", "2026-09-01")
    assert FC.LEADS == (1, 2, 3, 5, 7) and FC.RULE_RATIO == 1.5 and FC.RULE_LEAD == 3 and FC.SHARES == (0.10, 0.20, 0.30) and FC.THETAS == (0.0, 1.0)
    assert FC.GATE_PCT == 1.0 and (FC.BEFORE, FC.AFTER) == (1, 3)
    for hub, (lat, lon) in FC.HUB_XY.items():
        assert f"{lat}" in text and f"{abs(lon)}" in text, hub
    assert "2026-09" not in Path(FC.__file__).read_text(encoding="utf-8").replace("2026-09-01", "")
