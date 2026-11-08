"""The monitoring config must be exactly what was derived from 2025, with no 2026 data, and reproducible on any OS."""
import json
from pathlib import Path

import pytest
import yaml

from mcp import bands, monitor

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "monitoring.yaml"
DERIVED = ROOT / "results" / "monitoring_bands.json"


def test_config_values_are_the_derived_values():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))["monitoring"]
    d = json.loads(DERIVED.read_text())
    assert cfg["sigma_overall"] == round(d["sigma_overall"], 4) and cfg["sigma_hub"] == round(d["sigma_hub"], 4)
    assert cfg["window_months"] == d["window_months"] == 3 and cfg["z"] == d["z"] == 2.0


def test_derivation_used_only_the_2025_walk_forward():
    d = json.loads(DERIVED.read_text())
    assert d["n_months"] == 6 and d["n_hub_months"] == 30                      # Jul to Dec 2025, five hubs
    assert "2025" in d["derived_from"] and "2026" not in d["derived_from"]
    assert "2026" not in CFG.read_text(encoding="utf-8").replace("2026 plays no part", "")


def test_the_bands_follow_the_stated_formula():
    d = json.loads(DERIVED.read_text())
    assert d["band_overall"] == pytest.approx(2.0 * d["sigma_overall"] / 3 ** 0.5)
    assert d["band_hub"] == pytest.approx(2.0 * d["sigma_hub"] / 3 ** 0.5)
    assert d["band_hub"] > d["band_overall"]                                   # a single hub is noisier than the whole


def test_one_copy_of_the_band_formula():
    assert bands.band is monitor.band


def test_config_is_stored_with_unix_line_endings_so_its_hash_is_the_same_everywhere():
    assert b"\r" not in CFG.read_bytes()
