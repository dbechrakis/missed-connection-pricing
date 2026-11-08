"""Monthly recalibration and drift: hand-built months with known answers."""
import numpy as np
import pandas as pd
import pytest

from mcp.calibration import month_stats
from mcp.monitor import (STATE, drift_report, load_state, main, months_between, save_state, stats_from_json,
                         stats_to_json, step)

CFG = {"rebooking_cost": 100, "overnight_cost": 0}


def month(rate, p=0.10, hub="ATL", n=1000, weeks=("2026-03-02", "2026-03-09")):
    rows = []
    for wk in weeks:
        y = np.zeros(n)
        y[: int(rate * n)] = 1
        rows.append(pd.DataFrame({"hub": hub, "week": wk, "y": y, "weight": 1.0, "overnight": 0.0, "p_raw": p}))
    return pd.concat(rows, ignore_index=True)


def known(label, rate, p=0.10, hub="ATL"):
    df = month(rate, p, hub)
    return month_stats(label, df["hub"], df["y"], df["weight"], df["p_raw"])


def run(df, label, state, policy="level_global", k=1, **kw):
    return step(df, label, state, policy, k, CFG, cv_week=0.26, cv_claim=4.0, **kw)


def test_state_round_trips_through_json(tmp_path):
    s = [known("2026-01", 0.12), known("2026-02", 0.08)]
    save_state(s, tmp_path / "s.json")
    back = load_state(tmp_path / "s.json")
    assert [b.month for b in back] == ["2026-01", "2026-02"]
    for a, b in zip(s, back):
        assert a.hub == b.hub and all(np.allclose(x, y) for x, y in zip(a.hist, b.hist))
    assert stats_from_json(stats_to_json(s[0])).month == "2026-01"


def test_months_between_crosses_a_year_boundary():
    assert list(months_between("2025-11", "2026-02")) == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_the_month_is_priced_from_earlier_months_only_and_enters_the_state_afterwards():
    state = [known("2026-01", 0.20)]                       # January ran at twice the model's 10%
    report, new = run(month(0.10), "2026-02", state)       # February matches the model
    # priced with the January factor 2.0 -> predicted 20% while 10% happened: realized/expected 0.5
    assert report["realized_over_expected"] == pytest.approx(0.5)
    assert report["known_months_used"] == ["2026-01"]
    assert [s.month for s in new] == ["2026-01", "2026-02"]   # added only after the report


def test_a_month_cannot_calibrate_itself():
    # an empty state means no calibration: the raw probability is the price, whatever the month did
    report, _ = run(month(0.30), "2026-02", [])
    assert report["realized_over_expected"] == pytest.approx(3.0)


def test_booking_lead_lag_skips_the_most_recent_known_month():
    state = [known("2026-01", 0.20), known("2026-02", 0.05)]
    r0, _ = run(month(0.10), "2026-03", state)             # uses February: factor 0.5
    r1, _ = run(month(0.10), "2026-03", state, lag=1)      # skips February, uses January: factor 2.0
    assert r0["realized_over_expected"] == pytest.approx(2.0) and r1["realized_over_expected"] == pytest.approx(0.5)
    assert r1["known_months_used"] == ["2026-01"] and r1["lag"] == 1


def test_a_month_already_in_the_state_is_refused():
    with pytest.raises(ValueError):
        run(month(0.10), "2026-01", [known("2026-01", 0.1)])


def test_drift_report_flags_a_miscalibrated_hub_and_the_overall_level():
    df = pd.concat([month(0.10, hub="ATL"), month(0.20, hub="ORD")], ignore_index=True).assign(p=0.10)
    r = drift_report(df, "2026-03", CFG, 0.26, 4.0)
    assert r["by_hub"]["ATL"] == pytest.approx(1.0) and r["by_hub"]["ORD"] == pytest.approx(2.0)
    assert any("review hub ORD" in a for a in r["actions"]) and not any("review hub ATL" in a for a in r["actions"])
    assert any("recalibrate" in a for a in r["actions"])        # overall 1.5, outside +-10%


def test_on_target_month_says_hold():
    r = drift_report(month(0.10).assign(p=0.10), "2026-03", CFG, 0.26, 4.0)
    assert r["actions"] == ["hold: within band"] and r["flagged_weeks"] == []


def test_two_flagged_weeks_in_a_row_trigger_a_pause_review():
    bad = pd.concat([month(0.30, weeks=("2026-03-02",)), month(0.30, weeks=("2026-03-09",))], ignore_index=True).assign(p=0.10)
    r = drift_report(bad, "2026-03", CFG, 0.26, 4.0)
    assert r["flagged_weeks"] == ["2026-03-02", "2026-03-09"] and any("pause review" in a for a in r["actions"])
    one = pd.concat([month(0.30, weeks=("2026-03-02",)), month(0.10, weeks=("2026-03-09",))], ignore_index=True).assign(p=0.10)
    assert not any("pause review" in a for a in drift_report(one, "2026-03", CFG, 0.26, 4.0)["actions"])


def test_a_small_book_needs_a_bigger_breach_to_be_flagged():
    df = month(0.17).assign(p=0.10)                         # ratio 1.7
    assert drift_report(df, "m", CFG, 0.26, 4.0)["flagged_weeks"]                          # large book: threshold 1.53
    assert not drift_report(df, "m", CFG, 0.26, 4.0, policies_per_week=100)["flagged_weeks"]   # 100 a week: threshold 1.96


def test_the_cli_refuses_the_preregistered_window_without_the_flag(capsys):
    assert main(["--month", "2026-09"]) == 2
    assert "pre-registered" in capsys.readouterr().err
    assert main(["--replay", "2026-08", "2026-10"]) == 2


def test_state_file_path_is_inside_the_models_folder():
    assert STATE.parent.name == "models"


# ---- the rolling rule -------------------------------------------------------------------------------------

from mcp.monitor import band, rolling_check

MON = {"window_months": 3, "z": 2.0, "sigma_overall": 0.15, "sigma_hub": 0.20}


def rep(month_label, claims, expected, hubs=None):
    hubs = hubs or {"ATL": (claims, expected)}
    return {"month": month_label, "claims": claims, "expected": expected,
            "claims_by_hub": {h: c for h, (c, e) in hubs.items()}, "expected_by_hub": {h: e for h, (c, e) in hubs.items()}}


def test_band_by_hand():
    assert band(0.15, 3, 2.0) == pytest.approx(2 * 0.15 / np.sqrt(3))          # 0.1732
    assert band(0.15, 1, 2.0) == pytest.approx(0.30)
    assert band(0.15, 12, 2.0) < band(0.15, 3, 2.0) < band(0.15, 1, 2.0)        # longer window, tighter band


def test_no_alert_while_history_builds():
    r = rolling_check([rep("2026-01", 300, 100), rep("2026-02", 300, 100)], MON)
    assert r["status"] == "building history" and r["actions"] == []


def test_one_noisy_month_does_not_fire_but_a_sustained_shift_does():
    quiet = [rep("2026-01", 100, 100), rep("2026-02", 100, 100)]
    assert rolling_check(quiet + [rep("2026-03", 130, 100)], MON)["actions"] == []       # window ratio 1.10 < 1.17
    fired = rolling_check([rep("2026-01", 125, 100), rep("2026-02", 125, 100), rep("2026-03", 125, 100)], MON)
    assert fired["ratio"] == pytest.approx(1.25) and any("recalibrate" in a for a in fired["actions"])


def test_the_window_is_claim_weighted_not_an_average_of_ratios():
    # ratios 2.0 (tiny month) and 1.0, 1.0 (big months): the average of ratios is 1.33, the claim-weighted ratio is 1.0073
    r = rolling_check([rep("2026-01", 2, 1), rep("2026-02", 500, 500), rep("2026-03", 500, 500)], MON)
    assert r["ratio"] == pytest.approx(1002 / 1001) and r["actions"] == []


def test_an_old_month_drops_out_of_the_window():
    hist = [rep("2026-01", 400, 100), rep("2026-02", 100, 100), rep("2026-03", 100, 100), rep("2026-04", 100, 100)]
    r = rolling_check(hist, MON)
    assert r["months"] == ["2026-02", "2026-03", "2026-04"] and r["ratio"] == pytest.approx(1.0) and r["actions"] == []


def test_hubs_use_their_own_wider_band():
    hubs = lambda a, o: {"ATL": (a, 100), "ORD": (o, 100)}
    ok = [rep(f"2026-0{i}", 0, 0, hubs(112, 112)) for i in (1, 2, 3)]
    # hub band = 2 x 0.20 / sqrt(3) = 0.231: a 1.12 ratio is inside it but would be outside the overall band 0.173
    r = rolling_check([{**h, "claims": 224, "expected": 200} for h in ok], MON)
    assert r["actions"] == [] or all("hub" not in a for a in r["actions"])
    bad = [rep(f"2026-0{i}", 0, 0, hubs(100, 150)) for i in (1, 2, 3)]
    r2 = rolling_check([{**h, "claims": 250, "expected": 200} for h in bad], MON)
    assert any("review hub ORD" in a for a in r2["actions"]) and not any("review hub ATL" in a for a in r2["actions"])


def test_step_with_the_rolling_rule_keeps_the_old_verdict_for_comparison_and_builds_history():
    state, history = [known("2026-01", 0.10)], []
    r1, state = run(month(0.30), "2026-02", state, history=history, monitoring=MON)       # a wild month, but no history yet
    history.append(r1)
    assert r1["rolling"]["status"] == "building history" and "hold: building history" in r1["actions"]
    assert any("recalibrate" in a for a in r1["legacy_single_month_actions"])              # the old bands would have fired
    assert r1["claims"] > 0 and r1["expected"] > 0 and "ATL" in r1["claims_by_hub"]


def test_without_a_monitoring_config_behaviour_is_unchanged():
    r, _ = run(month(0.30), "2026-02", [])
    assert "rolling" not in r and any("recalibrate" in a for a in r["actions"])
