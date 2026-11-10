"""v5.1: the v5 self-transfer cover, refitted on months known at booking and scaled by a recent level.

Exactly as PREREGISTRATION_V5_1_LEVEL.md fixes it. For travel month m the table is v5's cell table fitted on
January 2024 to m - 5 (the newest month BTS has published when a self-transfer is sold), and its probability is
multiplied by a level L(m), one of five declared candidates, chosen by pooled log loss over July 2025 to August 2026.

    python -m mcp.v5_1 select      walk forward over the 14 development months, writes results/v5_1_selection.json
    python -m mcp.v5_1 freeze      the chosen prices for September to November 2026, models/v5_1_prices.json
    python -m mcp.v5_1 holdout     reads September to November 2026 once (refuses a second run)
"""
from __future__ import annotations

import argparse
import hashlib
import json

import numpy as np
import pandas as pd

from mcp import v5
from mcp.ingest import ROOT

SELECTION = ROOT / "results" / "v5_1_selection.json"
PRICES = ROOT / "models" / "v5_1_prices.json"
HOLDOUT_RESULT = ROOT / "results" / "v5_1_holdout.json"
LAG = 5
CANDIDATES = ("none", "last12", "last6", "season", "last12_by_gap")      # the order is the simplicity order for ties
DEV_TARGETS = ("2025-07", "2026-08")
DEV_DATA = ("2024-01", "2026-08")
NEXT = ("2026-09", "2026-11")
SHORT_GAP = 150
P_MAX = 0.999


def shift(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    n = y * 12 + (m - 1) + k
    return f"{n // 12}-{n % 12 + 1:02d}"


def window(ym: str, candidate: str) -> list[str]:
    """The months a candidate's level is learned from, for travel month ym."""
    if candidate == "none":
        return []
    if candidate in ("last12", "last12_by_gap"):
        return [shift(ym, -k) for k in range(16, LAG - 1, -1)]
    if candidate == "last6":
        return [shift(ym, -k) for k in range(10, LAG - 1, -1)]
    if candidate == "season":
        return [shift(ym, -k) for k in (13, 12, 11)]
    raise ValueError(candidate)


def level(df: pd.DataFrame, p: np.ndarray, months: list[str], candidate: str) -> dict:
    """{'all': L} or {'short': L, 'long': L}: realized misses over the table's expected misses in those months."""
    if candidate == "none" or not months:
        return {"all": 1.0}
    inside = df["ym"].isin(months).to_numpy()
    ratio = lambda mask: float(df["missed"].to_numpy()[mask].sum() / p[mask].sum())
    if candidate == "last12_by_gap":
        short = (df["slack_min"] < SHORT_GAP).to_numpy()
        return {"short": ratio(inside & short), "long": ratio(inside & ~short)}
    return {"all": ratio(inside)}


def apply_level(df: pd.DataFrame, p: np.ndarray, lv: dict) -> np.ndarray:
    if "all" in lv:
        return np.minimum(p * lv["all"], P_MAX)
    short = (df["slack_min"] < SHORT_GAP).to_numpy()
    return np.minimum(p * np.where(short, lv["short"], lv["long"]), P_MAX)


def table_for(df: pd.DataFrame, ym: str, k: float) -> dict:
    """v5's cell table fitted on January 2024 to ym - 5."""
    return v5.fit_table(df[df["ym"] <= shift(ym, -LAG)], k)


def price_month(dev: pd.DataFrame, target: pd.DataFrame, ym: str, k: float, candidate: str) -> tuple[np.ndarray, dict, dict]:
    table = table_for(dev, ym, k)
    months = window(ym, candidate)
    known = dev[dev["ym"].isin(months)]
    lv = level(known, v5.score(known, table), months, candidate)
    return apply_level(target, v5.score(target, table), lv), lv, table


def select() -> dict:
    k = json.loads(v5.TABLE.read_text())["k"]
    dev, _ = v5.frame(v5.T_MIN, *DEV_DATA)
    dev = dev.reset_index(drop=True)
    targets = [f"{y}-{m:02d}" for y, m in v5.months(*DEV_TARGETS)]
    out = {}
    for c in CANDIDATES:
        ys, ps, claims, expected, levels = [], [], 0.0, 0.0, {}
        for ym in targets:
            t = dev[dev["ym"] == ym]
            p, lv, _ = price_month(dev, t, ym, k, c)
            ys.append(t["missed"].to_numpy())
            ps.append(p)
            claims += float((t["missed"] * t["payout"]).sum())
            expected += float((p * t["payout"].to_numpy()).sum())
            levels[ym] = lv
        out[c] = {"log_loss": v5.log_loss(np.concatenate(ys), np.concatenate(ps)), "realized_over_target": claims / expected, "levels": levels}
    best = min(r["log_loss"] for r in out.values())
    chosen = next(c for c in CANDIDATES if out[c]["log_loss"] <= best + v5.TOLERANCE)
    result = {"k": k, "lag_months": LAG, "targets": list(DEV_TARGETS), "candidates": out, "chosen": chosen,
              "status": "development walk-forward, July 2025 to August 2026; the January to August 2026 months were v5's spent holdout"}
    SELECTION.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return result


def freeze() -> str:
    sel = json.loads(SELECTION.read_text())
    dev, _ = v5.frame(v5.T_MIN, *DEV_DATA)
    dev = dev.reset_index(drop=True)
    months = {}
    for y, m in v5.months(*NEXT):
        ym = f"{y}-{m:02d}"
        table = table_for(dev, ym, sel["k"])
        w = window(ym, sel["chosen"])
        known = dev[dev["ym"].isin(w)]
        months[ym] = {"table": table, "level": level(known, v5.score(known, table), w, sel["chosen"]),
                      "fitted_through": shift(ym, -LAG), "level_months": w}
    PRICES.write_text(json.dumps({"candidate": sel["chosen"], "k": sel["k"], "months": months}, sort_keys=True) + "\n",
                      encoding="utf-8", newline="\n")
    return hashlib.sha256(PRICES.read_bytes()).hexdigest()


def holdout() -> dict:
    """The single read of September to November 2026, against the frozen v5 table on the same pairings."""
    if HOLDOUT_RESULT.exists():
        raise SystemExit(f"{HOLDOUT_RESULT.name} exists: the window has been read. It is read once.")
    frozen = json.loads(PRICES.read_text())
    df, counts = v5.frame(v5.T_MIN, *NEXT)
    df = df.reset_index(drop=True)
    p = np.empty(len(df))
    for ym, spec in frozen["months"].items():
        mask = (df["ym"] == ym).to_numpy()
        p[mask] = apply_level(df[mask], v5.score(df[mask], spec["table"]), spec["level"])
    p_v5 = v5.score(df, json.loads(v5.TABLE.read_text()))
    r51, r5 = v5.realized_over_target(df, p), v5.realized_over_target(df, p_v5)
    monthly = {ym: v5.realized_over_target(g, p[g.index.to_numpy()]) for ym, g in df.groupby("ym")}
    short = (df["slack_min"] < SHORT_GAP).to_numpy()
    r_short, r_long = v5.realized_over_target(df[short], p[short]), v5.realized_over_target(df[~short], p[~short])
    misses = df["missed"].sum()
    cancel = float(df["missed_by_cancellation"].sum() / misses) if misses else float("nan")
    lo, hi = v5.week_bootstrap(df, p)
    grades = {"R1": 0.85 <= r51 <= 1.15, "R2": abs(r51 - 1) < abs(r5 - 1), "R3": max(monthly.values()) <= 1.54,
              "R4": 0.20 <= cancel <= 0.50, "R5": abs(r_long - r_short) <= 0.15}
    out = {"prices_sha256": hashlib.sha256(PRICES.read_bytes()).hexdigest(), "counts": counts,
           "v5_1": {"realized_over_target": r51, "interval_95": [lo, hi], "monthly": monthly, "short_gaps": r_short, "long_gaps": r_long},
           "v5_frozen": {"realized_over_target": r5}, "share_of_misses_by_cancellation_or_diversion": cancel, "grades": grades}
    HOLDOUT_RESULT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["select", "freeze", "holdout"])
    a = p.parse_args(argv)
    if a.step == "select":
        r = select()
        print(json.dumps({c: {k: v for k, v in r["candidates"][c].items() if k != "levels"} for c in CANDIDATES} | {"chosen": r["chosen"]}, indent=1))
    elif a.step == "freeze":
        print("models/v5_1_prices.json sha256", freeze())
    else:
        print(json.dumps(holdout()["grades"], indent=1))


if __name__ == "__main__":
    main()
