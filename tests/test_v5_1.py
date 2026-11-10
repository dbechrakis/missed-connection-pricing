"""v5.1: the windows known at booking, the level candidates, and the single read, on hand-built frames."""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mcp import v5_1

ROOT = Path(__file__).resolve().parents[1]


def test_month_shifts_cross_year_boundaries():
    assert v5_1.shift("2026-09", -5) == "2026-04" and v5_1.shift("2025-02", -3) == "2024-11" and v5_1.shift("2024-12", 1) == "2025-01"


def test_every_window_ends_at_the_newest_month_known_at_booking():
    assert v5_1.window("2026-09", "last12") == [f"2025-{m:02d}" for m in range(5, 13)] + [f"2026-{m:02d}" for m in range(1, 5)]
    assert v5_1.window("2026-09", "last6") == ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04"]
    assert v5_1.window("2026-09", "season") == ["2025-08", "2025-09", "2025-10"]
    assert v5_1.window("2026-09", "none") == []
    for c in v5_1.CANDIDATES[1:]:
        for ym in ("2025-07", "2026-01", "2026-11"):
            assert max(v5_1.window(ym, c)) <= v5_1.shift(ym, -v5_1.LAG)


def frame(n=6000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"ym": rng.choice(["2025-01", "2025-02"], n), "slack_min": rng.integers(90, 300, n)})
    df["missed"] = (rng.uniform(size=n) < np.where(df["slack_min"] < 150, 0.2, 0.05)).astype(int)
    return df


def test_the_level_is_realized_over_expected_and_by_gap_splits_it():
    df = frame()
    p = np.full(len(df), df["missed"].mean() / 2)               # a table that under-predicts by half
    assert v5_1.level(df, p, ["2025-01", "2025-02"], "last12")["all"] == pytest.approx(2.0)
    by = v5_1.level(df, np.where(df["slack_min"] < 150, 0.1, 0.05), ["2025-01", "2025-02"], "last12_by_gap")
    assert by["short"] == pytest.approx(2.0, rel=0.1) and by["long"] == pytest.approx(1.0, rel=0.15)
    assert v5_1.level(df, p, [], "none") == {"all": 1.0}


def test_a_level_never_pushes_a_probability_to_one():
    df = frame(10)
    assert v5_1.apply_level(df, np.full(10, 0.6), {"all": 3.0}).max() == v5_1.P_MAX


def test_the_window_is_read_once(tmp_path, monkeypatch):
    done = tmp_path / "v5_1_holdout.json"
    done.write_text("{}")
    monkeypatch.setattr(v5_1, "HOLDOUT_RESULT", done)
    with pytest.raises(SystemExit, match="read once"):
        v5_1.holdout()


def test_the_module_matches_the_preregistration():
    text = (ROOT / "PREREGISTRATION_V5_1_LEVEL.md").read_text(encoding="utf-8")
    assert v5_1.LAG == 5 and "**m − 5**" in text
    assert v5_1.CANDIDATES == tuple(re.findall(r"^\| `(\w+)` \|", text, flags=re.M))
    assert v5_1.DEV_TARGETS == ("2025-07", "2026-08") and v5_1.NEXT == ("2026-09", "2026-11")
    assert "**September to November 2026**, read **once**" in text and v5_1.SHORT_GAP == 150


def test_the_frozen_prices_are_the_ones_recorded_before_the_window_exists():
    import hashlib
    import json
    digest = hashlib.sha256((ROOT / "models" / "v5_1_prices.json").read_bytes()).hexdigest()
    assert digest == "ac3b9e0ca54454821e972233fe1d8f511160c5a90c82b08fff69dde6201dac19"
    assert digest in (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    frozen = json.loads((ROOT / "models" / "v5_1_prices.json").read_text())
    chosen = json.loads((ROOT / "results" / "v5_1_selection.json").read_text())["chosen"]
    assert frozen["candidate"] == chosen and set(frozen["months"]) == {"2026-09", "2026-10", "2026-11"}
    assert all(m["fitted_through"] <= v5_1.shift(ym, -5) for ym, m in frozen["months"].items())
