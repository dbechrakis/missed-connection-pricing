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


def test_every_prediction_in_the_four_documents_is_on_the_scoreboard_and_nothing_has_been_read():
    status = json.loads((ROOT / "results" / "prereg_status.json").read_text(encoding="utf-8"))
    on_board = {e["id"]: e for e in status["expectations"]}
    for e in on_board.values():
        text = (ROOT / e["document"]).read_text(encoding="utf-8")
        assert re.search(rf"^\| {e['id']} \|", text, flags=re.M), (e["id"], e["document"])
    in_docs = set()
    for doc in {e["document"] for e in on_board.values()}:
        in_docs |= set(re.findall(r"^\| ([EAVL]\d) \|", (ROOT / doc).read_text(encoding="utf-8"), flags=re.M))
    assert in_docs == set(on_board) and len(on_board) == 19
    assert all(e["status"] == "pending" and e["result"] is None for e in on_board.values())
    assert (ROOT / "SCOREBOARD.md").read_text(encoding="utf-8") == grade.render(status)


def test_apply_marks_pass_and_fail_and_leaves_ungraded_rows_pending():
    status = json.loads((ROOT / "results" / "prereg_status.json").read_text(encoding="utf-8"))
    out = grade.apply(status, grade.grade_v4(v4_result(v3=0.70, v4=0.56)))
    by = {e["id"]: e["status"] for e in out["expectations"]}
    assert by["L2"] == "fail" and by["L1"] == "pass" and by["E1"] == "pending" and by["V1"] == "pending"
