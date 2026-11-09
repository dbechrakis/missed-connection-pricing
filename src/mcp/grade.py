"""How the pre-registered predictions for September to November 2026 will be judged, written before the data exists.

A prediction is only as honest as its grading. These functions grade the v3 expectations (V1 to V6 of
`PREREGISTRATION_2026H2_V3.md`) and the v4 expectations (L1 to L4 of `PREREGISTRATION_2026H2_V4.md`) from the result files
the tested code writes, with the thresholds copied from those documents, so nobody has to decide afterwards what counts as a pass.
The original expectations (E1 to E6) and the monitoring addendum (A1 to A3) are graded by hand, as the documents say, and stay
"pending" here until then. Standard library only, so it runs anywhere.

    python -m mcp.grade            # grades whatever result files exist, updates results/prereg_status.json and SCOREBOARD.md
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "results" / "prereg_status.json"
SCOREBOARD = ROOT / "SCOREBOARD.md"
SIGMA = 0.197                    # the standard deviation fixed in the v3 pre-registration (11 months of development data)
BREAK_EVEN = 1.54                # as written in the v3 pre-registration (V2): 'above 1.54 (= 1 / 0.65, a loss ratio of 100%)'


def grade_v3(res: dict) -> dict:
    """V1 to V6 from results/holdout_v3_next.json (written by mcp.holdout_v3)."""
    n = len(res["months_evaluated"])
    primary = res["results"]["primary"]
    ratio = primary["overall"]["ratio"]
    band = 2 * SIGMA / n ** 0.5
    cap = primary["offered_within_cap"]["0.05"]
    dev = lambda arm: max(abs(v["ratio"] - 1) for v in res["results"][arm]["by_hub"].values())
    gap, reach = res["gap_share_of_overnight_misses"], cap["share_of_overnight_offered"]
    worst = max(primary["monthly"].values())
    return {
        "V1": {"pass": abs(ratio - 1) <= band, "value": f"{ratio:.3f} against 1 ± {band:.3f} (n = {n}); with the 0.24 spread seen over 26 months: 1 ± {2 * 0.241 / n ** 0.5:.3f}"},
        "V2": {"pass": worst <= BREAK_EVEN, "value": f"worst month {worst:.3f} against {BREAK_EVEN:.2f}"},
        "V3": {"pass": cap["realized_over_target"]["ratio"] > ratio, "value": f"within the cap {cap['realized_over_target']['ratio']:.3f}, all {ratio:.3f}"},
        "V4": {"pass": dev("hub_level") < dev("primary"), "value": f"worst hub deviation: hub_level {dev('hub_level'):.3f}, primary {dev('primary'):.3f}"},
        "V5": {"pass": 0.70 <= gap <= 0.90, "value": f"{gap:.1%} of overnight misses in the gap"},
        "V6": {"pass": 0.25 <= reach <= 0.55, "value": f"{reach:.1%} of overnight-risk connections within the cap"},
    }


def grade_v4(res: dict) -> dict:
    """L1 to L4 from results/holdout_v4_next.json (written by mcp.holdout_v4)."""
    p = res["pooled_loss_ratio"]
    shares = [m["v4_share_sold"] for m in res["monthly"].values()]
    weeks = res["weeks_above_100"]["v4"]
    return {
        "L1": {"pass": res["improvement_points"] >= 3.0 and res["v4_below_v3_in_every_month"], "value": f"{res['improvement_points']:.1f} points lower than v3; below v3 in every month: {res['v4_below_v3_in_every_month']}"},
        "L2": {"pass": 0.25 <= p["v4"] <= 0.55, "value": f"v4 sold loss ratio {p['v4']:.1%} (v3 price {p['v3']:.1%})"},
        "L3": {"pass": all(0.28 <= s <= 0.42 for s in shares), "value": "share sold by month " + ", ".join(f"{s:.1%}" for s in shares)},
        "L4": {"pass": weeks <= 1, "value": f"{weeks} of {res['weeks']} weeks above 100%"},
    }


def render(status: dict) -> str:
    """SCOREBOARD.md from the status file: one row per pre-registered prediction."""
    icon = {"pending": "pending", "pass": "**passed**", "fail": "**failed**"}
    rows = "\n".join(f"| {e['id']} | {e['claim']} | [{e['tag']}]({e['document']}) | {icon[e['status']]} | {e['result'] or ''} |" for e in status["expectations"])
    done = sum(1 for e in status["expectations"] if e["status"] != "pending")
    return f"""# Scoreboard: every pre-registered prediction and how it turned out

Each prediction was written, hashed and tagged **before** its data existed, so each is judged by the rule it was written with. Nothing here is edited by hand once a result is in: `python -m mcp.grade` grades from the result files with thresholds copied from the documents (`src/mcp/grade.py`), except E1 to E6 and A1 to A3, which their documents say are graded by hand.

**{done} of {len(status['expectations'])} graded.** {status['when']}

| # | Prediction | Document (tag) | Status | Result |
| --- | --- | --- | --- | --- |
{rows}

**How the read happens.** A weekly scheduled job on the author's machine checks that BTS has published September, October and November 2026, and only then runs the four tests once, in the pre-registered order, grades them with the rules above and commits the results to a local branch. It never pushes, never changes a model or a threshold, and never runs twice. The author reviews and publishes.

A failed prediction is reported as prominently as a passed one, in the same commit as the result. The calm-season warning in `PREREGISTRATION_2026H2_V4.md` applies: September to November is the easiest part of the year for this cover, so passing says little about summer.
"""


def load() -> dict:
    return json.loads(STATUS.read_text(encoding="utf-8"))


def apply(status: dict, grades: dict) -> dict:
    for e in status["expectations"]:
        if e["id"] in grades:
            e["status"] = "pass" if grades[e["id"]]["pass"] else "fail"
            e["result"] = grades[e["id"]]["value"]
    return status


def main() -> None:
    status = load()
    for name, grader in (("holdout_v3_next.json", grade_v3), ("holdout_v4_next.json", grade_v4)):
        path = ROOT / "results" / name
        if path.exists():
            apply(status, grader(json.loads(path.read_text(encoding="utf-8"))))
    STATUS.write_text(json.dumps(status, indent=1, ensure_ascii=False) + chr(10), encoding="utf-8", newline=chr(10))
    SCOREBOARD.write_text(render(status), encoding="utf-8", newline=chr(10))
    print(render(status).split("| # |")[0].strip().splitlines()[-1])


if __name__ == "__main__":
    main()
