"""The README's commands must exist, and the numbers it quotes must match the results files.
Stops the front page from drifting away from the code and the validation."""
import importlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_every_python_m_command_in_the_readme_is_a_real_runnable_module():
    mods = set(re.findall(r"python -m (mcp\.\w+)", README))
    assert {"mcp.ingest", "mcp.connections", "mcp.holdout", "mcp.v2", "mcp.demo"} <= mods
    for m in mods:
        mod = importlib.import_module(m)
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert '__name__ == "__main__"' in src, f"{m} has no command-line entry point"


def test_cli_flags_used_in_the_readme_exist():
    flags = {"mcp.connections": ["--mct", "--weighted", "--no-build", "--start", "--end", "--quiet"],
             "mcp.ingest": ["--start", "--end", "--source"], "mcp.pricing": ["--full-severity"]}
    for m, fl in flags.items():
        src = Path(importlib.import_module(m).__file__).read_text(encoding="utf-8")
        for f in fl:
            assert f in src and f in README, (m, f)


def test_scripts_and_files_the_readme_points_to_exist():
    for rel in re.findall(r"\]\((?!http)([^)#]+)", README):
        assert (ROOT / rel).exists(), rel
    assert (ROOT / "scripts" / "download_data.sh").exists()


def test_headline_numbers_in_the_readme_match_the_holdout_results():
    h = json.loads((ROOT / "results" / "holdout.json").read_text())
    v1, v2 = h["overall"]["v1_iso"]["0"], h["overall"]["v2_rolling"]["0"]
    target = 0.65
    assert f"{v1['ratio'] * target * 100:.1f}%" in README
    assert f"{v2['ratio'] * target * 100:.1f}%" in README
    assert f"{h['overall']['baseline']['0']['ratio'] * target * 100:.1f}%" in README
    assert f"{h['flat_pricing']['flat_train']['0']['ratio'] * target * 100:.1f}%" in README
    assert f"{h['flat_pricing']['flat_train']['1']['ratio'] * target * 100:.0f}%" in README
    assert f"{h['rows']['scored'] / 1e6:.1f} million" in README


def test_cutoffs_in_the_readme_match_the_pricing_sensitivity():
    s = json.loads((ROOT / "results" / "pricing.json").read_text())["sensitivity"]
    base, strict = s["wtp_cap_pct=0.1"]["cutoff_min_slack_by_hub"], s["wtp_cap_pct=0.05"]["cutoff_min_slack_by_hub"]
    assert base["ATL"] == 45 and all(base[h] == 60 for h in ("DEN", "CLT", "DFW", "ORD"))
    assert min(strict.values()) == 60 and max(strict.values()) == 105    # README says 75 to 105 for the four hubs
    assert sorted(strict[h] for h in ("DEN", "CLT", "DFW", "ORD")) == [75, 90, 90, 105]
    assert "75 to 105 minutes" in README


def test_the_quoted_validation_windows_match_the_code():
    from mcp.split import WINDOWS
    assert WINDOWS["HOLDOUT"][0] == "2026-01-01" and WINDOWS["TEST"] == ("2025-07-01", "2026-01-01")
    assert "January to August 2026" in README and "July to December 2025" in README
