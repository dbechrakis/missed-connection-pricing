"""Monthly recalibration and drift monitoring: the operating policy from docs/product-brief.md as runnable code.

Each month, with the outcomes of the months that are known:
  1. price the new month with a calibrator built only from earlier months (optionally lagged for the booking lead),
  2. report drift: observed against expected misses by hub and by week, flagging weeks that breach the pause threshold,
  3. only then add the month to the state, so it can inform the next month and never itself.

The core, `step`, is a pure function (a scored month and the state in, a report and the new state out) so the
"a month never sees itself or the future" property is unit-tested. `main` wires it to the pipeline's files.

    python -m mcp.monitor --month 2026-08                  score one month, print the drift report, update the state
    python -m mcp.monitor --replay 2026-01 2026-08         rebuild the state month by month (development data only)

The replay reads 2026 months that are already spent as a test; it is an operational dry run, not a validation.
Months from September 2026 on are the pre-registered next test window (PREREGISTRATION_2026H2.md) and are refused
unless --accept-preregistration is passed.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from mcp.calibration import MonthStats, known_months, make_calibrator, month_index, month_stats
from mcp.connections import ROOT
from mcp.experiment import pause_threshold

STATE = ROOT / "models" / "v2_state.json"
MONITORING = ROOT / "config" / "monitoring.yaml"
REPORTS = ROOT / "results" / "monitor"
LEVEL_BAND = 0.10          # overall realized/expected outside 1 +- band: recalibrate (the brief's +-10% band; an assumption)
HUB_BAND = 0.20            # one hub outside 1 +- band: review that hub
NEXT_WINDOW_START = "2026-09"


# ---- state ----------------------------------------------------------------------------------------

def stats_to_json(s: MonthStats) -> dict:
    return {"month": s.month, "hub": {h: list(v) for h, v in s.hub.items()}, "hist": [a.tolist() for a in s.hist]}


def stats_from_json(d: dict) -> MonthStats:
    return MonthStats(d["month"], {h: tuple(v) for h, v in d["hub"].items()}, tuple(np.array(a) for a in d["hist"]))


def save_state(stats: list[MonthStats], path=STATE) -> None:
    path.write_text(json.dumps([stats_to_json(s) for s in sorted(stats, key=lambda s: s.month)]), encoding="utf-8")


def load_state(path=STATE) -> list[MonthStats]:
    return [stats_from_json(d) for d in json.loads(path.read_text(encoding="utf-8"))]


# ---- drift ----------------------------------------------------------------------------------------

def drift_report(df, label: str, cfg: dict, cv_week: float, cv_claim: float, policies_per_week: float | None = None) -> dict:
    """Observed against expected claims for one priced month. `df` needs hub, week, y, weight, overnight and p
    (the probability the month was priced with). Ratios are claims over expected claims, cost-weighted, so
    1.0 is on target; the weekly flag threshold is the brief's pause rule (volume-aware when volume is given)."""
    c = cfg["rebooking_cost"] + cfg["overnight_cost"] * df["overnight"].to_numpy()
    w, y, p = df["weight"].to_numpy(), df["y"].to_numpy(), df["p"].to_numpy()
    d = df.assign(_claim=w * y * c, _exp=w * p * c, _w=w, _y=w * y, _p=w * p)

    def ratio(g):
        return float(g["_claim"].sum() / g["_exp"].sum())

    overall = ratio(d)
    by_hub = {h: ratio(g) for h, g in d.groupby("hub")}
    sums = {"claims": float(d["_claim"].sum()), "expected": float(d["_exp"].sum()),
            "claims_by_hub": {h: float(g["_claim"].sum()) for h, g in d.groupby("hub")},
            "expected_by_hub": {h: float(g["_exp"].sum()) for h, g in d.groupby("hub")}}
    weekly = {wk: ratio(g) for wk, g in d.groupby("week")}
    thr = pause_threshold(cv_week, cv_claim, policies_per_week or 1e12)
    flagged = sorted(wk for wk, r in weekly.items() if r > thr)
    actions = []
    if abs(overall - 1) > LEVEL_BAND:
        actions.append(f"recalibrate: overall realized/expected {overall:.2f} is outside 1 +- {LEVEL_BAND:.0%}")
    actions += [f"review hub {h}: realized/expected {r:.2f} is outside 1 +- {HUB_BAND:.0%}" for h, r in sorted(by_hub.items())
                if abs(r - 1) > HUB_BAND]
    consecutive = any(month_flag_run(weekly, thr))
    if consecutive:
        actions.append("pause review: two flagged weeks in a row")
    return {"month": label, "observed_rate": float(d["_y"].sum() / d["_w"].sum()), "predicted_rate": float(d["_p"].sum() / d["_w"].sum()),
            "realized_over_expected": overall, "by_hub": by_hub, "weekly": weekly, "flag_threshold": thr,
            "flagged_weeks": flagged, "actions": actions or ["hold: within band"], **sums}


def month_flag_run(weekly: dict, thr: float):
    """Yield True for each pair of consecutive weeks (in date order) that are both above the threshold."""
    ws = [weekly[k] for k in sorted(weekly)]
    for a, b in zip(ws, ws[1:]):
        yield a > thr and b > thr


# ---- the rolling rule (bands sized from 2025 data; see mcp.bands and VALIDATION.md 4J) --------------------------

def band(sigma: float, k: int, z: float) -> float:
    """Half-width around 1 for a rolling k-month ratio whose monthly spread is sigma (same formula as mcp.bands)."""
    return float(z * sigma / np.sqrt(k))


def load_monitoring(path=MONITORING) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))["monitoring"]


def rolling_check(history: list[dict], mon: dict) -> dict:
    """Alert when the realized/expected ratio over the last `window_months` months is outside 1 +- z x sigma / sqrt(window).

    `history` is the reports up to and including the current month; ratios are claims over expected claims summed over
    the window (claim-weighted, not an average of ratios). With fewer months than the window there is no alert."""
    k = mon["window_months"]
    hist = sorted(history, key=lambda r: r["month"])[-k:]
    if len(hist) < k:
        return {"status": "building history", "months": [h["month"] for h in hist], "actions": []}
    b_all = band(mon["sigma_overall"], k, mon["z"])
    b_hub = band(mon["sigma_hub"], k, mon["z"])
    ratio = sum(h["claims"] for h in hist) / sum(h["expected"] for h in hist)
    hubs = {hub: sum(h["claims_by_hub"].get(hub, 0.0) for h in hist) / sum(h["expected_by_hub"][hub] for h in hist)
            for hub in hist[-1]["expected_by_hub"]}
    actions = []
    if abs(ratio - 1) > b_all:
        actions.append(f"recalibrate: rolling {k}-month realized/expected {ratio:.2f} is outside 1 +- {b_all:.2f}")
    actions += [f"review hub {h}: rolling {k}-month realized/expected {r:.2f} is outside 1 +- {b_hub:.2f}"
                for h, r in sorted(hubs.items()) if abs(r - 1) > b_hub]
    return {"status": "checked", "months": [h["month"] for h in hist], "ratio": float(ratio), "band": b_all,
            "by_hub": {h: float(r) for h, r in hubs.items()}, "band_hub": b_hub, "actions": actions}


# ---- the monthly step -------------------------------------------------------------------------------

def step(df, label: str, state: list[MonthStats], policy: str, k: int, cfg: dict, cv_week: float, cv_claim: float,
         lag: int = 0, policies_per_week: float | None = None, history: list[dict] | None = None, monitoring: dict | None = None):
    """Price `label` from the months already known, report drift, and return the report and the new state.

    `df` needs hub, week, y, weight, overnight and p_raw (the uncalibrated model probability). The month's own
    outcomes enter the state only after its report is produced, so it cannot inform its own price."""
    if any(s.month == label for s in state):
        raise ValueError(f"{label} is already in the state")
    known = known_months(state, label, lag)
    cal = make_calibrator(policy, k, known)
    priced = df.assign(p=cal(df["p_raw"].to_numpy(), df["hub"].to_numpy()))
    report = drift_report(priced, label, cfg, cv_week, cv_claim, policies_per_week)
    if monitoring is not None:
        # the rolling rule replaces the single-month bands; the old verdict is kept for comparison
        roll = rolling_check(list(history or []) + [report], monitoring)
        report["legacy_single_month_actions"] = report["actions"]
        keep = [a for a in report["actions"] if a.startswith("pause review")]
        report["rolling"] = roll
        base = roll["actions"] or (["hold: within the rolling band"] if roll["status"] == "checked" else ["hold: building history"])
        report["actions"] = base + keep                # a weekly pause review adds to the verdict, it never replaces it
    report.update(known_months_used=[s.month for s in sorted(known, key=lambda s: s.month)[-k:]] if known else [], lag=lag)
    new = list(state) + [month_stats(label, df["hub"], df["y"], df["weight"], df["p_raw"])]
    return report, new


# ---- wiring to the pipeline's files (not unit-tested; exercised by the replay) --------------------------

def score_month(label: str, v2: dict):
    """The raw v2 probability for one month of connections, with severity, from the weighted connection files."""
    import duckdb
    import pandas as pd

    from mcp import features as F
    from mcp.holdout import SEVERITY_FULL, month_path, predict
    from mcp.split import where
    from mcp.v2 import month_predicate

    y, m = int(label[:4]), int(label[5:])
    con = duckdb.connect()
    F.create_stats(con, fit_flights=where("V2_FIT", "flight_date"), fit_asos=where("V2_FIT", "obs_utc"))
    df = con.execute(F.feature_sql(f"read_parquet('{month_path(m, y)}')", month_predicate(y, m), 1.0,
                                   SEVERITY_FULL.as_posix())).fetchdf()
    df = df[df["overnight"].notna() & df["fare"].notna()].copy()
    df["p_raw"] = predict(v2, df)
    day = df["out_sched_dep"].dt.normalize()
    df["week"] = (day - pd.to_timedelta(df["out_sched_dep"].dt.day_of_week, unit="D")).astype(str)
    return df


def months_between(a: str, b: str):
    i = month_index(a)
    while i <= month_index(b):
        yield f"{(i - 1) // 12}-{(i - 1) % 12 + 1:02d}"
        i += 1


def main(argv=None) -> int:
    import joblib

    from mcp.holdout import V2_BUNDLE
    from mcp.pricing import load_config

    p = argparse.ArgumentParser(description="Monthly recalibration and drift report.")
    p.add_argument("--month")
    p.add_argument("--replay", nargs=2, metavar=("FROM", "TO"))
    p.add_argument("--lag", type=int, default=0, help="booking-lead lag in months (default 0)")
    p.add_argument("--accept-preregistration", action="store_true")
    p.add_argument("--dry", action="store_true", help="do not overwrite the saved state")
    p.add_argument("--legacy-bands", action="store_true", help="use the original single-month +-10%%/+-20%% bands")
    a = p.parse_args(argv)
    months = [a.month] if a.month else list(months_between(*a.replay)) if a.replay else []
    if not months:
        p.error("give --month or --replay")
    if any(m >= NEXT_WINDOW_START for m in months) and not a.accept_preregistration:
        print(f"refused: {NEXT_WINDOW_START} onward is the pre-registered next test window. Read PREREGISTRATION_2026H2.md first, "
              "then pass --accept-preregistration.", file=sys.stderr)
        return 2
    cfg, v2 = load_config(), joblib.load(V2_BUNDLE)
    design = json.loads((ROOT / "results" / "experiment_design.json").read_text())["inputs"]
    state = load_state() if (STATE.exists() and not a.replay) else list(v2["cal_stats"])
    REPORTS.mkdir(parents=True, exist_ok=True)
    mon = None if a.legacy_bands or not MONITORING.exists() else load_monitoring()
    history = [json.loads(f.read_text()) for f in sorted(REPORTS.glob("*.json")) if f.stem < months[0] and "claims" in json.loads(f.read_text())]
    for label in months:
        df = score_month(label, v2)
        report, state = step(df, label, state, v2["policy"], v2["k"], cfg, design["cv_week_ratio"],
                             design["cv_claim_per_policy"], lag=a.lag, history=history, monitoring=mon)
        history.append(report)
        (REPORTS / f"{label}.json").write_text(json.dumps(report, indent=2))
        print(f"{label}: realized/expected {report['realized_over_expected']:.3f}  hubs "
              + " ".join(f"{h} {r:.2f}" for h, r in sorted(report['by_hub'].items())) + f"  -> {'; '.join(report['actions'])}", flush=True)
    if a.dry:
        print("dry run: state not saved")
        return 0
    save_state(state)
    print(f"state saved: {len(state)} months through {max(s.month for s in state)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
