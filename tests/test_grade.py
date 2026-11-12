"""The graders for the pre-registered predictions, on toy results that pass and fail, and the scoreboard's consistency."""
import json
import re
from pathlib import Path

from mcp import grade

ROOT = Path(__file__).resolve().parents[1]


def v3_result(ratio=1.05, months=("2026-09", "2026-10", "2026-11"), worst=1.2, cap_ratio=1.15, hub_primary=0.30, hub_level=0.10, gap=0.80, reach=0.40):
    by_hub = lambda d: {h: {"ratio": 1 + d} for h in ("ATL", "CLT")}
    monthly = {m: ratio for m in months[:-1]}
    monthly[months[-1]] = worst
    return {"months_evaluated": list(months), "gap_share_of_overnight_misses": gap,
            "results": {"primary": {"overall": {"ratio": ratio}, "monthly": monthly, "by_hub": by_hub(hub_primary),
                                    "offered_within_cap": {"0.05": {"share_of_overnight_offered": reach, "realized_over_target": {"ratio": cap_ratio}}}},
                        "hub_level": {"by_hub": by_hub(hub_level)}}}


def test_v3_graders_pass_a_result_inside_every_band_and_fail_each_one_outside_it():
    ok = grade.grade_v3(v3_result())
    assert all(g["pass"] for g in ok.values()) and set(ok) == {"V1", "V2", "V3", "V4", "V5", "V6"}
    band = 2 * 0.197 / 3 ** 0.5
    assert not grade.grade_v3(v3_result(ratio=1 + band + 0.01))["V1"]["pass"] and grade.grade_v3(v3_result(ratio=1 + band - 0.01))["V1"]["pass"]
    assert not grade.grade_v3(v3_result(worst=1.5401))["V2"]["pass"] and grade.grade_v3(v3_result(worst=1.54))["V2"]["pass"]
    assert not grade.grade_v3(v3_result(cap_ratio=1.0))["V3"]["pass"]
    assert not grade.grade_v3(v3_result(hub_level=0.40))["V4"]["pass"]
    assert not grade.grade_v3(v3_result(gap=0.65))["V5"]["pass"] and not grade.grade_v3(v3_result(gap=0.95))["V5"]["pass"]
    assert not grade.grade_v3(v3_result(reach=0.20))["V6"]["pass"] and not grade.grade_v3(v3_result(reach=0.60))["V6"]["pass"]


def v4_result(v3=0.42, v4=0.36, shares=(0.35, 0.36, 0.34), weeks=0, every=True):
    return {"pooled_loss_ratio": {"v3": v3, "v4": v4}, "improvement_points": 100 * (v3 - v4), "v4_below_v3_in_every_month": every,
            "monthly": {f"2026-{m}": {"v4_share_sold": s} for m, s in zip((9, 10, 11), shares)}, "weeks": 13, "weeks_above_100": {"v3": 0, "v4": weeks}}


def test_v4_graders_use_the_thresholds_of_the_preregistration():
    assert all(g["pass"] for g in grade.grade_v4(v4_result()).values())
    assert not grade.grade_v4(v4_result(v3=0.38, v4=0.36))["L1"]["pass"]                 # only 2 points
    assert not grade.grade_v4(v4_result(every=False))["L1"]["pass"]
    assert not grade.grade_v4(v4_result(v4=0.56))["L2"]["pass"] and not grade.grade_v4(v4_result(v4=0.24))["L2"]["pass"]
    assert not grade.grade_v4(v4_result(shares=(0.35, 0.27, 0.34)))["L3"]["pass"] and not grade.grade_v4(v4_result(shares=(0.35, 0.43, 0.34)))["L3"]["pass"]
    assert grade.grade_v4(v4_result(weeks=1))["L4"]["pass"] and not grade.grade_v4(v4_result(weeks=2))["L4"]["pass"]


def test_every_prediction_in_the_nine_documents_is_on_the_scoreboard_and_only_v5_and_the_forecast_test_have_been_read():
    status = json.loads((ROOT / "results" / "prereg_status.json").read_text(encoding="utf-8"))
    on_board = {e["id"]: e for e in status["expectations"]}
    for e in on_board.values():
        text = (ROOT / e["document"]).read_text(encoding="utf-8")
        assert re.search(rf"^\| {e['id']} \|", text, flags=re.M), (e["id"], e["document"])
    in_docs = set()
    for doc in {e["document"] for e in on_board.values()}:
        in_docs |= set(re.findall(r"^\| ([EAVLSRWBCF]\d+) \|", (ROOT / doc).read_text(encoding="utf-8"), flags=re.M))
    assert in_docs == set(on_board) and len(on_board) == 48
    assert all(e["status"] == "pending" and e["result"] is None for k, e in on_board.items() if not k.startswith(("S", "F")) and k != "C1")
    v5 = grade.grade_v5(json.loads((ROOT / "results" / "v5_holdout.json").read_text(encoding="utf-8")))
    assert all(on_board[k]["status"] == ("pass" if g["pass"] else "fail") and on_board[k]["result"] == g["value"] for k, g in v5.items())
    fc = grade.grade_forecast(json.loads((ROOT / "results" / "forecast.json").read_text(encoding="utf-8")))
    assert all(on_board[k]["status"] == ("pass" if g["pass"] else "fail") and on_board[k]["result"] == g["value"] for k, g in fc.items())
    ca = grade.grade_coding(json.loads((ROOT / "results" / "coding_audit.json").read_text(encoding="utf-8")))
    assert set(ca) == {"C1"} and on_board["C1"]["status"] == "fail" and on_board["C2"]["status"] == "pending"
    assert (ROOT / "SCOREBOARD.md").read_text(encoding="utf-8") == grade.render(status)


def test_apply_marks_pass_and_fail_and_leaves_ungraded_rows_pending():
    status = json.loads((ROOT / "results" / "prereg_status.json").read_text(encoding="utf-8"))
    out = grade.apply(status, grade.grade_v4(v4_result(v3=0.70, v4=0.56)))
    by = {e["id"]: e["status"] for e in out["expectations"]}
    assert by["L2"] == "fail" and by["L1"] == "pass" and by["E1"] == "pending" and by["V1"] == "pending"


# ---- season 2: the backcast and the coding audit ----------------------------------------------------------------

def backcast_result(**over):
    r = {"n_months": 44,
         "gap": {"pooled_ratio_all": 1.05, "monthly_ratio_all": {f"m{i}": 1.0 + (0.2 if i % 2 else -0.2) for i in range(44)}, "pooled_ratio_sold": 1.15,
                 "monthly_sold_loss_ratio": {f"m{i}": (1.1 if i < 8 else 0.7) for i in range(44)},
                 "sold_loss_ratio_unloaded": 0.77, "sold_loss_ratio_loaded": 0.70},
         "level": {"months_scored": 37, "crps": {"none": 0.20, "last12": 0.19, "local": 0.15}, "interval_hits": 33},
         "self_transfer": {"ratio_unloaded": 1.20, "ratio_loaded": 1.03}}
    for k, v in over.items():
        r[k].update(v) if isinstance(v, dict) else r.update({k: v})
    return r


def test_the_backcast_bands_are_the_ones_the_document_states_and_derive_from_the_development_numbers():
    text = (ROOT / "PREREGISTRATION_V6_BACKCAST.md").read_text(encoding="utf-8")
    assert f"{grade.b1_band(44):.3f}" in text and "0.241" in text and "0.70" in text
    assert f"{grade.B2_BAND[0]:.2f} to {grade.B2_BAND[1]:.2f}" in text
    assert f"{grade.B4_BAND[0]:.0%} to {grade.B4_BAND[1]:.0%}" in text
    assert "at least 3.0 points" in text and grade.B5_POINTS == 0.03
    # the development numbers the bands come from are in the committed results
    dev = json.loads((ROOT / "results" / "v3_rolling.json").read_text(encoding="utf-8"))
    a, sold = dev["all_overnight_risk"], dev["sold_within_cap"]
    assert round(a["ratio_sd"], 3) == grade.B_SIGMA and sold["months_loss_ratio_above_100"] == 6 and len(sold["monthly_loss_ratio"]) == 26
    x = list(a["monthly_ratio"].values())
    import numpy as np
    assert round(float(np.corrcoef(x[:-1], x[1:])[0, 1]), 2) == grade.B_RHO


def test_binomial_range_and_the_chi_square_and_clopper_pearson_bands_match_scipy():
    from scipy import stats
    for n in (23, 37, 44, 48):
        assert grade.binomial_central_range(n) == (int(stats.binom.ppf(0.025, n, 0.9)), int(stats.binom.ppf(0.975, n, 0.9)))
    assert round(0.241 * (25 / stats.chi2.ppf(0.975, 25)) ** 0.5, 2) == grade.B2_BAND[0]
    assert round(0.241 * (25 / stats.chi2.ppf(0.025, 25)) ** 0.5, 2) == grade.B2_BAND[1]
    assert round(float(stats.beta.ppf(0.025, 6, 21)), 2) == grade.B4_BAND[0] and round(float(stats.beta.ppf(0.975, 7, 20)), 2) == grade.B4_BAND[1]


def test_each_backcast_expectation_passes_and_fails_on_its_own_rule():
    ok = grade.grade_backcast(backcast_result())
    assert all(ok[k]["pass"] for k in ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8")), ok
    assert set(ok) == {f"B{i}" for i in range(1, 9)}                                  # B9 and B10 are graded by hand
    bad = lambda **o: grade.grade_backcast(backcast_result(**o))
    assert not bad(gap={"pooled_ratio_all": 1.20})["B1"]["pass"] and bad(gap={"pooled_ratio_all": 1.16})["B1"]["pass"]
    assert not bad(gap={"pooled_ratio_sold": 1.0})["B3"]["pass"]
    assert not bad(gap={"monthly_sold_loss_ratio": {f"m{i}": 0.7 for i in range(44)}})["B4"]["pass"]       # none above 100%: below 9%
    assert not bad(gap={"sold_loss_ratio_loaded": 0.75})["B5"]["pass"] and bad(gap={"sold_loss_ratio_loaded": 0.74})["B5"]["pass"]
    assert not bad(level={"crps": {"none": 0.10, "last12": 0.19, "local": 0.15}})["B6"]["pass"]
    lo, hi = grade.binomial_central_range(37)
    assert not bad(level={"interval_hits": lo - 1})["B7"]["pass"] and bad(level={"interval_hits": lo})["B7"]["pass"] and not bad(level={"interval_hits": hi + 1 if hi < 37 else -1})["B7"]["pass"]
    assert not bad(self_transfer={"ratio_loaded": 1.30})["B8"]["pass"]


def test_the_coding_audit_does_not_grade_the_effect_when_the_placebo_fails():
    ok = {"placebo": {"Y1": {"effect": 1.0}, "Y2": {"effect": -2.0}}, "primary": {"Y1": {"effect": -1.0}, "Y2": {"effect": 0.5}}}
    g = grade.grade_coding(ok)
    assert g["C1"]["pass"] and g["C2"]["pass"]
    assert not grade.grade_coding({**ok, "primary": {"Y1": {"effect": -3.5}, "Y2": {"effect": 0.5}}})["C2"]["pass"]
    broken = grade.grade_coding({**ok, "placebo": {"Y1": {"effect": 4.0}, "Y2": {"effect": 0.0}}})
    assert not broken["C1"]["pass"] and "C2" not in broken


def test_the_addendum_reason_is_arithmetic_that_can_be_checked():
    """48 known months can never be reached: 60 scored months less the 16 pandemic months leaves 44."""
    from datetime import date
    months = [(y, m) for y in range(2019, 2024) for m in range(1, 13)]
    pandemic = [(y, m) for y, m in months if date(2020, 3, 1) <= date(y, m, 1) <= date(2021, 6, 1)]
    assert len(months) == 60 and len(pandemic) == 16 and len(months) - len(pandemic) == 44 < 48
    text = (ROOT / "PREREGISTRATION_V6_BACKCAST_ADDENDUM.md").read_text(encoding="utf-8")
    assert "**44** observed months" in text and "16 of 60" in text
    status = json.loads((ROOT / "results" / "prereg_status.json").read_text(encoding="utf-8"))
    rows = {e["id"]: e for e in status["expectations"]}
    assert rows["B6"]["document"] == rows["B7"]["document"] == "PREREGISTRATION_V6_BACKCAST_ADDENDUM.md"
    assert "local_season" not in grade.grade_backcast.__doc__.split("B6 and B7")[0].split("level.")[1]


def test_the_forecast_expectations_are_graded_by_the_rules_the_document_states():
    base = {"gain_pct": {"1": 3.0, "2": 2.0, "3": 1.5, "5": 0.8, "7": 0.4}, "gate_passed": True,
            "rule": {"s20_theta1": {"weeks_above_100_with_rule": 9, "weeks_above_100_without_rule": 14}}}
    g = grade.grade_forecast(base)
    assert g["F1"]["pass"] and g["F2"]["pass"]
    assert not grade.grade_forecast({**base, "gain_pct": {**base["gain_pct"], "7": 1.2}})["F1"]["pass"]
    assert not grade.grade_forecast({**base, "gain_pct": {**base["gain_pct"], "1": 0.3}})["F1"]["pass"]
    assert not grade.grade_forecast({**base, "rule": {"s20_theta1": {"weeks_above_100_with_rule": 14, "weeks_above_100_without_rule": 14}}})["F2"]["pass"]
    null = grade.grade_forecast({**base, "gate_passed": False})
    assert "F2" not in null and "F1" in null
    text = (ROOT / "PREREGISTRATION_V6_FORECAST.md").read_text(encoding="utf-8")
    for needle in ("1 February 2024", "1 September 2025 to 31 August 2026", "1.5 times", "10%, 20%, 30%", "under 1% at every lead", "lead 3"):
        assert needle in text, needle
