"""v5.2: the frozen loading and table match the pre-registration, and the window is read once."""
import hashlib
import json
from pathlib import Path

import pytest

from mcp import v5_2

ROOT = Path(__file__).resolve().parents[1]


def test_the_frozen_prices_are_the_ones_recorded_before_the_window_exists():
    digest = hashlib.sha256((ROOT / "models" / "v5_2_prices.json").read_bytes()).hexdigest()
    assert digest == "56180af9135ae112c9ab97a7d78bf8e6d0c63ea59f0dbeb4943321895ace697b"
    assert digest in (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    frozen = json.loads((ROOT / "models" / "v5_2_prices.json").read_text())
    assert frozen["lambda"] == v5_2.LAMBDA == 1.16 and frozen["k"] == 1000 and frozen["table"]["fitted_on"] == ["2024-01", "2026-08"]


def test_the_module_matches_the_preregistration():
    text = (ROOT / "PREREGISTRATION_V5_2_LOADING.md").read_text(encoding="utf-8")
    assert "**Loading: λ = 1.16**" in text and "**January 2024 to August 2026**" in text and "**December 2026 to February 2027**, read **once**" in text
    assert v5_2.WINDOW == ("2026-12", "2027-02") and v5_2.REACH == (0.65, 0.85) and "**65% to 85%**" in text


def test_the_window_is_read_once(tmp_path, monkeypatch):
    done = tmp_path / "v5_2_holdout.json"
    done.write_text("{}")
    monkeypatch.setattr(v5_2, "HOLDOUT_RESULT", done)
    with pytest.raises(SystemExit, match="read once"):
        v5_2.holdout()
