"""Guards for the 2026 holdout and the v2 development rules: no look-ahead, no early reads."""
import fnmatch
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mcp.calibration import month_stats
from mcp.v2 import CANDIDATES, DEV_GLOB, SIMPLICITY, pick, walk_forward

ROOT = Path(__file__).resolve().parents[1]
CFG = {"rebooking_cost": 100, "overnight_cost": 0, "target_loss_ratio": 0.5}


# ---- the holdout is read in exactly one place -------------------------------------------------

def test_only_holdout_py_reads_the_holdout_window_and_only_once():
    reads = {}
    for path in [*(ROOT / "src" / "mcp").glob("*.py"), *(ROOT / "notebooks").glob("*.py")]:
        if path.name == "split.py":
            continue
        n = len(re.findall(r"""where\(\s*["']HOLDOUT["']""", path.read_text(encoding="utf-8")))
        if n:
            reads[path.name] = n
    assert reads == {"holdout.py": 1}, reads


def test_v2_development_globs_cannot_match_a_2026_file():
    pattern = DEV_GLOB.rsplit("/", 2)[-2]                      # the year folder pattern
    assert fnmatch.fnmatch("year=2024", pattern) and fnmatch.fnmatch("year=2025", pattern)
    assert not fnmatch.fnmatch("year=2026", pattern)


def test_v2_module_never_names_the_holdout_window_or_2026_files():
    text = (ROOT / "src" / "mcp" / "v2.py").read_text(encoding="utf-8")
    assert "HOLDOUT" not in text.replace("(VALIDATION", "")  # only the docstring may mention it, and it does not
    assert not re.search(r"year=2026|month=0[1-8]\.parquet", text)


# ---- the selection rule as declared in advance -------------------------------------------------

def row(policy, k, ll):
    return {"policy": policy, "k": k, "log_loss": ll, "features": "x"}


def test_pick_takes_the_lowest_log_loss_when_clearly_better():
    assert pick([row("none", 0, 0.30), row("level_global", 3, 0.29)])["policy"] == "level_global"


def test_pick_breaks_ties_toward_the_simpler_policy_then_the_longer_window():
    rows = [row("iso_global", 6, 0.2900), row("level_hub", 3, 0.2901), row("level_global", 1, 0.2902), row("level_global", 6, 0.2901)]
    chosen = pick(rows)                       # all within 0.0002 of the best
    assert (chosen["policy"], chosen["k"]) == ("level_global", 6)


def test_a_candidate_outside_the_tolerance_is_not_rescued_by_being_simple():
    rows = [row("none", 0, 0.3000), row("iso_global", 6, 0.2900)]
    assert pick(rows)["policy"] == "iso_global"


def test_the_candidate_list_is_the_one_in_the_protocol():
    assert ("none", 0) in CANDIDATES
    assert {k for p, k in CANDIDATES if p == "level_global"} == {1, 2, 3, 6}
    assert {k for p, k in CANDIDATES if p == "level_hub"} == {1, 3, 6}
    assert {k for p, k in CANDIDATES if p == "iso_global"} == {3, 6}
    assert set(SIMPLICITY) == {"none", "level_global", "level_hub", "iso_global"}


# ---- walk-forward: a month never sees itself or the future ------------------------------------

def month_frame(rate, p=0.1, n=2000):
    y = np.zeros(n)
    y[: int(rate * n)] = 1
    return pd.DataFrame({"y": y, "weight": 1.0, "overnight": 0.0, "hub": "ATL", "p": p})


def build(rates):
    months = {f"2025-{m:02d}": month_frame(r) for m, r in rates.items()}
    stats = [month_stats(k, df["hub"], df["y"], df["weight"], df["p"]) for k, df in months.items()]
    return months, stats


def test_walk_forward_result_for_a_month_ignores_every_later_month():
    base_months, base_stats = build({6: 0.20, 7: 0.10})
    ext_months, ext_stats = build({6: 0.20, 7: 0.10, 8: 0.90, 9: 0.00})         # wild future months
    a = walk_forward(base_months, base_stats, CFG, ["2025-07"])
    b = walk_forward({k: v for k, v in ext_months.items()}, ext_stats, CFG, ["2025-07"])
    for ra, rb in zip(a, b):
        assert ra["log_loss"] == pytest.approx(rb["log_loss"]) and ra["brier"] == pytest.approx(rb["brier"])


def test_walk_forward_never_lets_a_month_calibrate_itself():
    # July is 5x riskier than the model says. A policy that peeked at July would be ~perfect for it;
    # one that only sees June (observed 0.1 = predicted) must leave July badly under-predicted.
    months, stats = build({6: 0.10, 7: 0.50})
    res = {(r["policy"], r["k"]): r for r in walk_forward(months, stats, CFG, ["2025-07"])}
    assert res[("level_global", 1)]["realized_over_target"] == pytest.approx(5.0)    # 0.5 observed / 0.1 predicted
    assert res[("none", 0)]["realized_over_target"] == pytest.approx(5.0)


def test_walk_forward_follows_the_level_when_the_past_month_shows_it():
    months, stats = build({6: 0.30, 7: 0.30})
    res = {(r["policy"], r["k"]): r for r in walk_forward(months, stats, CFG, ["2025-07"])}
    assert res[("level_global", 1)]["realized_over_target"] == pytest.approx(1.0)
    assert res[("none", 0)]["realized_over_target"] == pytest.approx(3.0)


# ---- the v1 / v2 frames are matched by key, never by row order --------------------------------------

def _frames(n=50):
    from mcp.holdout import KEYS
    base = pd.DataFrame({k: np.arange(n) + (i * 1000) for i, k in enumerate(KEYS)})
    base["p_v2_raw"] = np.linspace(0.01, 0.5, n)
    return base


def test_attach_v2_aligns_rows_even_when_the_second_frame_is_in_a_different_order():
    from mcp.holdout import attach_v2
    d2 = _frames()
    df = d2.drop(columns="p_v2_raw").assign(tag=np.arange(len(d2)))
    shuffled = d2.sample(frac=1.0, random_state=3).reset_index(drop=True)
    out = attach_v2(df, shuffled)
    assert (out["p_v2_raw"].to_numpy() == d2["p_v2_raw"].to_numpy()).all()       # row i still gets its own probability
    assert (out["tag"].to_numpy() == np.arange(len(d2))).all()


def test_attach_v2_fails_loudly_on_a_repeated_key_or_a_missing_connection():
    from mcp.holdout import attach_v2
    d2 = _frames()
    df = d2.drop(columns="p_v2_raw")
    with pytest.raises(Exception):
        attach_v2(df, pd.concat([d2, d2.iloc[[0]]], ignore_index=True))          # duplicate key
    with pytest.raises(AssertionError):
        attach_v2(df, d2.iloc[1:])                                                # one connection unmatched
