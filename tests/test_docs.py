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


# ---- the pre-registration for the next test window --------------------------------------------------------

def test_preregistration_hashes_match_the_frozen_files():
    import hashlib
    text = (ROOT / "PREREGISTRATION_2026H2.md").read_text(encoding="utf-8")
    for rel in ("models/pmiss.joblib", "models/pmiss_v2.joblib", "models/v2_state.json", "config/pricing.yaml", "config/guards.yaml"):
        h = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        assert h in text, f"{rel} no longer matches the hash in PREREGISTRATION_2026H2.md"


def test_preregistration_commands_and_flags_exist():
    text = (ROOT / "PREREGISTRATION_2026H2.md").read_text(encoding="utf-8")
    holdout = (ROOT / "src" / "mcp" / "holdout.py").read_text(encoding="utf-8")
    for flag in ("--next",):
        assert flag in text and flag in holdout
    for cmd in re.findall(r"python -m (mcp\.\w+)", text):
        importlib.import_module(cmd)


def test_preregistration_window_is_the_one_in_the_code_and_starts_after_everything_used():
    from mcp.split import WINDOWS
    text = (ROOT / "PREREGISTRATION_2026H2.md").read_text(encoding="utf-8")
    assert WINDOWS["NEXT"] == ("2026-09-01", "2027-01-01") and "1 September to 31 December 2026" in text


def test_readme_points_to_the_preregistration():
    assert "PREREGISTRATION_2026H2.md" in README


def test_day_of_numbers_in_the_readme_match_the_value_of_information_results():
    v = json.loads((ROOT / "results" / "voi.json").read_text())["sets"]
    d, b = v["+ inbound departure delay"], v["booking time only"]
    for needle in (f"**{d['brier_improvement']:.0%}**", f"**{d['top5']['misses_caught']:.0%}**", f"**{d['top5']['precision']:.0%}**",
                   f"{b['top5']['misses_caught']:.0%} at {b['top5']['precision']:.0%}"):
        assert needle in README, needle
    assert v["+ hub weather"]["brier_improvement"] < 0.01          # "hub weather adds under 1%"


def test_pricing_config_hash_is_reproducible_on_any_operating_system():
    import hashlib
    h = hashlib.sha256((ROOT / "config" / "pricing.yaml").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert h == "75e1db9fda3e188955a0201ea9a29ae317c88deec5619395cfe2bfd89a9e8979"
    assert h in (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    assert h in (ROOT / "PREREGISTRATION_2026H2.md").read_text(encoding="utf-8")


# ---- the addendum -------------------------------------------------------------------------------------------

def test_addendum_hash_and_parameters_match_the_monitoring_config():
    import hashlib
    import yaml
    text = (ROOT / "PREREGISTRATION_2026H2_ADDENDUM.md").read_text(encoding="utf-8")
    raw = (ROOT / "config" / "monitoring.yaml").read_bytes()
    assert hashlib.sha256(raw).hexdigest() in text
    cfg = yaml.safe_load(raw)["monitoring"]
    assert f"{cfg['sigma_overall']:.3f}" in text and f"{cfg['sigma_hub']:.3f}" in text and cfg["window_months"] == 3 and cfg["z"] == 2.0


def test_addendum_states_the_limit_that_the_quiet_costs_sensitivity_and_that_it_was_not_blind():
    text = (ROOT / "PREREGISTRATION_2026H2_ADDENDUM.md").read_text(encoding="utf-8")
    assert "Not blind" in text and "costs sensitivity" in text and "A1" in text and "A3" in text


def test_addendum_commands_exist():
    text = (ROOT / "PREREGISTRATION_2026H2_ADDENDUM.md").read_text(encoding="utf-8")
    src = (ROOT / "src" / "mcp" / "monitor.py").read_text(encoding="utf-8")
    for flag in ("--accept-preregistration", "--dry", "--legacy-bands", "--replay"):
        assert flag in text and flag in src


# ---- the v3 pre-registration ----------------------------------------------------------------------------------

def test_v3_preregistration_freezes_the_artefacts_the_test_will_use():
    import hashlib
    text = (ROOT / "PREREGISTRATION_2026H2_V3.md").read_text(encoding="utf-8")
    for rel in ("models/pmiss_v3.joblib", "models/v3_state.json", "results/gsa_costs.json"):
        raw = (ROOT / rel).read_bytes()
        raw = raw if rel.endswith(".joblib") else raw.replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() in text, rel


def test_v3_preregistration_numbers_match_the_development_results():
    import numpy as np
    from mcp.v3 import TARGET_LR, WTP_CAP
    text = (ROOT / "PREREGISTRATION_2026H2_V3.md").read_text(encoding="utf-8")
    r = np.array(list(json.loads((ROOT / "results" / "v3_robustness.json").read_text())[
        "all       v1 set          none         k=0"]["months"].values()))
    sigma = r.std(ddof=1)
    assert f"σ = {sigma:.3f}" in text
    assert f"n = 3: {1 - 2 * sigma / 3 ** 0.5:.2f} to {1 + 2 * sigma / 3 ** 0.5:.2f}" in text
    assert f"n = 4: {1 - sigma:.2f} to {1 + sigma:.2f}" in text
    assert f"{1 / TARGET_LR:.2f}" in text and WTP_CAP == 0.05 and "5% of the average fare" in text
    dev = json.loads((ROOT / "results" / "v3_dev.json").read_text())["results"]["primary"]
    assert f"**{dev['overall']['ratio']:.2f}**" in text
    assert f"**{dev['offered_within_cap']['0.05']['realized_over_target']['ratio']:.2f}**" in text
    sel = json.loads((ROOT / "results" / "v3_selection.json").read_text())["chosen"]
    assert sel["policy"] == "none" and sel["features"] == "v1 set"


def test_readme_and_validation_v3_numbers_match_the_results():
    val = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    c = json.loads((ROOT / "results" / "causes_v3.json").read_text())
    a, o = c["all_misses"], c["overnight_misses"]
    for needle in (f"{a['carrier']:.1%}", f"{a['late_aircraft']:.1%}", f"**{a['gap_broad']:.1%} to {a['gap_strict']:.1%}**"):
        assert needle in README, needle
    for needle in (f"**{a['gap_strict']:.1%}**", f"**{a['gap_broad']:.1%}**", f"{o['gap_strict']:.1%} and {o['gap_broad']:.1%}",
                   f"{a['weather']:.1%} | {o['weather']:.1%}"):
        assert needle in val, needle
    dev = json.loads((ROOT / "results" / "v3_dev.json").read_text())["results"]["primary"]
    assert f"**{dev['overall']['ratio']:.2f}** × target" in README
    assert f"{dev['offered_within_cap']['0.05']['share_of_overnight_offered']:.0%} of overnight-risk" in README
    assert f"${dev['mean_price_overnight']:.2f}" in val
    rates = json.loads((ROOT / "results" / "gsa_costs.json").read_text())["rates"]
    nights = [sum(v[fy]["lodging"].values()) / 12 + v[fy]["mie"] for v in rates.values() for fy in v]
    assert f"${min(nights):.0f} to ${max(nights):.0f}" in README
    assert f"{100 * (1 - 180 / min(nights)):.0f} to {100 * (1 - 180 / max(nights)):.0f}% too low" in README


def test_decision_memo_numbers_match_the_results():
    memo = (ROOT / "docs" / "decision-memo.md").read_text(encoding="utf-8")
    c = json.loads((ROOT / "results" / "causes_v3.json").read_text())
    a, o = c["all_misses"], c["overnight_misses"]
    for needle in (f"**{a['carrier']:.1%}**", f"**{a['late_aircraft']:.1%}**", f"**{a['gap_broad']:.1%} to {a['gap_strict']:.1%}**",
                   f"{o['gap_strict']:.1%} of the overnight", f"Dallas, {c['by_hub']['DFW']['weather']:.0%} of misses from weather",
                   f"Chicago, {c['by_hub']['ORD']['nas']:.0%} from air traffic"):
        assert needle in memo, needle
    dev = json.loads((ROOT / "results" / "v3_dev.json").read_text())["results"]["primary"]
    m = dev["monthly"].values()
    assert f"**{min(m):.2f} to {max(m):.2f} times**" in memo
    assert f"**${dev['mean_price_overnight']:.0f}**" in memo
    assert f"**{dev['offered_within_cap']['0.05']['share_of_overnight_offered']:.0%}**" in memo
    cap = dev["offered_within_cap"]["0.05"]["realized_over_target"]["ratio"]
    assert f"**{cap / dev['overall']['ratio'] - 1:.0%} worse**" in memo
    assert "**60.5%**" in memo and "117%" in memo and "68.2%" in memo
