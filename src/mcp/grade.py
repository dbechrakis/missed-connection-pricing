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
import math
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


def grade_v5(res: dict) -> dict:
    """S1 to S5 from results/v5_holdout.json (written by mcp.v5 holdout), thresholds as in PREREGISTRATION_V5_SELF_TRANSFER.md."""
    m = res["primary"]
    cap, ratio = m["cap"]["0.10"]["realized_over_target"], m["realized_over_target"]
    s3 = m["s3_rates_90_vs_165"]
    return {
        "S1": {"pass": 0.85 <= ratio <= 1.15, "value": f"realized/target {ratio:.3f} [{m['interval_95'][0]:.2f}, {m['interval_95'][1]:.2f}] against 0.85 to 1.15"},
        "S2": {"pass": 0.20 <= m["share_of_misses_by_cancellation_or_diversion"] <= 0.50,
               "value": f"{m['share_of_misses_by_cancellation_or_diversion']:.1%} of misses after a cancellation or diversion"},
        "S3": {"pass": all(a > b for a, b in s3.values()),
               "value": "miss rate 90 to 104 min against 165 to 179 min: " + ", ".join(f"{h} {a:.1%}/{b:.1%}" for h, (a, b) in s3.items())},
        "S4": {"pass": 0.08 <= m["monthly_sd"] <= 0.35, "value": f"monthly sd {m['monthly_sd']:.2f}"},
        "S5": {"pass": cap > ratio, "value": f"within the 10% cap {cap:.3f}, all {ratio:.3f}"},
    }


def grade_v5_1(res: dict) -> dict:
    """R1 to R5 from results/v5_1_holdout.json (written by mcp.v5_1 holdout), thresholds as in PREREGISTRATION_V5_1_LEVEL.md."""
    r, g = res["v5_1"], res["grades"]
    return {
        "R1": {"pass": g["R1"], "value": f"realized/target {r['realized_over_target']:.3f} [{r['interval_95'][0]:.2f}, {r['interval_95'][1]:.2f}] against 0.85 to 1.15"},
        "R2": {"pass": g["R2"], "value": f"v5.1 {r['realized_over_target']:.3f}, frozen v5 {res['v5_frozen']['realized_over_target']:.3f}"},
        "R3": {"pass": g["R3"], "value": "monthly " + ", ".join(f"{m} {v:.2f}" for m, v in r["monthly"].items())},
        "R4": {"pass": g["R4"], "value": f"{res['share_of_misses_by_cancellation_or_diversion']:.1%} of misses after a cancellation or diversion"},
        "R5": {"pass": g["R5"], "value": f"long gaps {r['long_gaps']:.3f}, short gaps {r['short_gaps']:.3f}"},
    }


def grade_v5_2(res: dict) -> dict:
    """W1 to W5 from results/v5_2_holdout.json (written by mcp.v5_2 holdout), thresholds as in PREREGISTRATION_V5_2_LOADING.md."""
    r, g = res["loaded"], res["grades"]
    return {
        "W1": {"pass": g["W1"], "value": f"loaded {r['realized_over_target']:.3f} [{r['interval_95'][0]:.2f}, {r['interval_95'][1]:.2f}] against 0.85 to 1.15"},
        "W2": {"pass": g["W2"], "value": f"loaded {r['realized_over_target']:.3f}, unloaded {res['unloaded']['realized_over_target']:.3f}"},
        "W3": {"pass": g["W3"], "value": "monthly " + ", ".join(f"{m} {v:.2f}" for m, v in r["monthly"].items())},
        "W4": {"pass": g["W4"], "value": "within the cap " + ", ".join(f"{m} {v:.0%}" for m, v in r["share_within_cap"].items())},
        "W5": {"pass": g["W5"], "value": f"{res['share_of_misses_by_cancellation_or_diversion']:.1%} of misses after a cancellation or diversion"},
    }


# ---- season 2: the backcast and the coding audit (written before 2018 to 2023 is downloaded) -------------------------
B_SIGMA, B_RHO = 0.241, 0.70     # spread and lag-1 autocorrelation of the 26 development monthly ratios (PREREGISTRATION_V6_BACKCAST.md, section 6)
B2_BAND = (0.19, 0.33)           # 95% chi-square interval for an sd of 0.241 from 26 months
B4_BAND = (0.09, 0.44)           # exact 95% interval for 6 of 26 months above a 100% loss ratio
B5_POINTS = 0.03
C_POINTS = 3.0


def binomial_central_range(n: int, p: float = 0.90, tail: float = 0.025) -> tuple[int, int]:
    """Smallest k with P(X <= k) >= tail, and smallest k with P(X <= k) >= 1 - tail, for X ~ Binomial(n, p)."""
    cdf, lo, hi = 0.0, None, None
    for k in range(n + 1):
        cdf += math.comb(n, k) * p ** k * (1 - p) ** (n - k)
        if lo is None and cdf >= tail:
            lo = k
        if hi is None and cdf >= 1 - tail:
            hi = k
            break
    return lo, hi


def b1_band(n: int) -> float:
    return 2 * B_SIGMA / math.sqrt(n * (1 - B_RHO) / (1 + B_RHO))


def grade_backcast(res: dict) -> dict:
    """B1 to B8 from results/backcast.json (written by mcp.backcast), thresholds as in PREREGISTRATION_V6_BACKCAST.md.
    B9 and B10 are reported without a prediction and stay pending. Months are the scored months outside the pandemic.

    Expected keys: n_months; gap.{pooled_ratio_all, monthly_ratio_all, pooled_ratio_sold, monthly_sold_loss_ratio,
    sold_loss_ratio_unloaded, sold_loss_ratio_loaded}; level.{months_scored, crps.{none,last12,local}, interval_hits};
    self_transfer.{ratio_unloaded, ratio_loaded}. B6 and B7 are on the `local` level model (PREREGISTRATION_V6_BACKCAST_ADDENDUM.md)."""
    g, lv, st = res["gap"], res["level"], res["self_transfer"]
    n = res["n_months"]
    band = b1_band(n)
    ratios = list(g["monthly_ratio_all"].values())
    mean = sum(ratios) / len(ratios)
    sd = math.sqrt(sum((r - mean) ** 2 for r in ratios) / (len(ratios) - 1))
    lrs = list(g["monthly_sold_loss_ratio"].values())
    above = sum(1 for x in lrs if x > 1.0) / len(lrs)
    lo, hi = binomial_central_range(lv["months_scored"])
    c = lv["crps"]
    gain = g["sold_loss_ratio_unloaded"] - g["sold_loss_ratio_loaded"]
    return {
        "B1": {"pass": abs(g["pooled_ratio_all"] - 1) <= band, "value": f"{g['pooled_ratio_all']:.3f} against 1 ± {band:.3f} (n = {n})"},
        "B2": {"pass": B2_BAND[0] <= sd <= B2_BAND[1], "value": f"monthly sd {sd:.3f} against {B2_BAND[0]:.2f} to {B2_BAND[1]:.2f}"},
        "B3": {"pass": g["pooled_ratio_sold"] > g["pooled_ratio_all"], "value": f"within the cap {g['pooled_ratio_sold']:.3f}, all {g['pooled_ratio_all']:.3f}"},
        "B4": {"pass": B4_BAND[0] <= above <= B4_BAND[1], "value": f"{above:.1%} of months above a 100% loss ratio as sold, against {B4_BAND[0]:.0%} to {B4_BAND[1]:.0%}"},
        "B5": {"pass": gain >= B5_POINTS, "value": f"loading lowers the sold loss ratio by {gain * 100:.1f} points ({g['sold_loss_ratio_unloaded']:.1%} to {g['sold_loss_ratio_loaded']:.1%})"},
        "B6": {"pass": c["local"] < c["none"] and c["local"] < c["last12"],
               "value": f"CRPS local {c['local']:.3f}, none {c['none']:.3f}, last12 {c['last12']:.3f} over {lv['months_scored']} months"},
        "B7": {"pass": lo <= lv["interval_hits"] <= hi, "value": f"{lv['interval_hits']} of {lv['months_scored']} months inside the 90% interval, range {lo} to {hi}"},
        "B8": {"pass": abs(st["ratio_loaded"] - 1) < abs(st["ratio_unloaded"] - 1), "value": f"loaded {st['ratio_loaded']:.3f}, unloaded {st['ratio_unloaded']:.3f}"},
    }


def grade_coding(res: dict) -> dict:
    """C1 and C2 from results/coding_audit.json (written by mcp.coding_audit), as in PREREGISTRATION_V6_CODING.md.
    Effects are in percentage points, negative meaning a fall in the carrier-coded share. If C1 fails, C2 is not graded."""
    pl, pr = res["placebo"], res["primary"]
    c1 = all(abs(pl[k]["effect"]) <= C_POINTS for k in ("Y1", "Y2"))
    out = {"C1": {"pass": c1, "value": f"placebo effects Y1 {pl['Y1']['effect']:+.1f}, Y2 {pl['Y2']['effect']:+.1f} points against ± {C_POINTS:.0f}"}}
    if c1:
        out["C2"] = {"pass": all(pr[k]["effect"] > -C_POINTS for k in ("Y1", "Y2")),
                     "value": f"effects Y1 {pr['Y1']['effect']:+.1f}, Y2 {pr['Y2']['effect']:+.1f} points against a fall of {C_POINTS:.0f}"}
    return out


def grade_forecast(res: dict) -> dict:
    """F1 and F2 from results/forecast.json (written by mcp.forecast), thresholds as in PREREGISTRATION_V6_FORECAST.md.
    F2 is graded only if the gate passed (a gain of 1% or more at some lead)."""
    g = res["gain_pct"]
    out = {"F1": {"pass": g["1"] > g["7"] and g["7"] < 1.0, "value": f"gain at lead 1 {g['1']:.2f}%, at lead 7 {g['7']:.2f}%"}}
    if res["gate_passed"]:
        w = res["rule"]["s20_theta1"]
        out["F2"] = {"pass": w["weeks_above_100_with_rule"] < w["weeks_above_100_without_rule"],
                     "value": f"weeks above 100% as sold: {w['weeks_above_100_with_rule']} with the rule, {w['weeks_above_100_without_rule']} without"}
    return out


def render(status: dict) -> str:
    """SCOREBOARD.md from the status file: one row per pre-registered prediction."""
    icon = {"pending": "pending", "pass": "**passed**", "fail": "**failed**"}
    rows = "\n".join(f"| {e['id']} | {e['claim']} | [{e['tag']}]({e['document']}) | {icon[e['status']]} | {e['result'] or ''} |" for e in status["expectations"])
    done = sum(1 for e in status["expectations"] if e["status"] != "pending")
    return f"""# Scoreboard: every pre-registered prediction and how it turned out

Each prediction was written, hashed and tagged **before** its data existed, so each is judged by the rule it was written with. Nothing here is edited by hand once a result is in: `python -m mcp.grade` grades from the result files with thresholds copied from the documents (`src/mcp/grade.py`), except E1 to E6, A1 to A3, B9, B10 and the sizes of F3, which their documents say are graded by hand.

**{done} of {len(status['expectations'])} graded.** {status['when']}

| # | Prediction | Document (tag) | Status | Result |
| --- | --- | --- | --- | --- |
{rows}

**How the read happens.** A weekly scheduled job on the author's machine checks that BTS has published September, October and November 2026, and only then runs the four tests once, in the pre-registered order, grades them with the rules above and commits the results to a local branch. It never pushes, never changes a model or a threshold, and never runs twice. The author reviews and publishes. v3 and v4 are judged on these three months only. For E1 to E6 and A1 to A3, `PREREGISTRATION_2026H2.md` allows one final read with December once it is published. It was decided before any of the data existed that this read will be run, once, and reported next to the first (`VALIDATION.md` 5M).

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
    for name, grader in (("holdout_v3_next.json", grade_v3), ("holdout_v4_next.json", grade_v4), ("v5_holdout.json", grade_v5),
                         ("v5_1_holdout.json", grade_v5_1),
                         ("v5_2_holdout.json", grade_v5_2), ("backcast.json", grade_backcast), ("coding_audit.json", grade_coding), ("forecast.json", grade_forecast)):
        path = ROOT / "results" / name
        if path.exists():
            apply(status, grader(json.loads(path.read_text(encoding="utf-8"))))
    STATUS.write_text(json.dumps(status, indent=1, ensure_ascii=False) + chr(10), encoding="utf-8", newline=chr(10))
    SCOREBOARD.write_text(render(status), encoding="utf-8", newline=chr(10))
    print(render(status).split("| # |")[0].strip().splitlines()[-1])


if __name__ == "__main__":
    main()
