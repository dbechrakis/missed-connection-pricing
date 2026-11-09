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


def test_audit_numbers_in_validation_memo_brief_readme_and_demo_match_the_results():
    import re
    a = json.loads((ROOT / "results" / "v3_audit.json").read_text())
    roll = json.loads((ROOT / "results" / "v3_rolling.json").read_text())
    sold, every = roll["sold_within_cap"], roll["all_overnight_risk"]
    m = {k: v["all"]["realized_over_target"] for k, v in a["mct"].items()}
    bm = {k: v["all_buffer"]["realized_over_target"] for k, v in a["mct"].items()}
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    val = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    memo = (ROOT / "docs" / "decision-memo.md").read_text(encoding="utf-8")
    brief = (ROOT / "docs" / "product-brief.md").read_text(encoding="utf-8")
    n = roll["months"]
    # the sold view, from the 26-month backtest, is the one quoted everywhere
    for text in (readme, memo, brief):
        assert f"{sold['pooled_loss_ratio']:.0%}" in text, text[:40]
        assert f"{sold['months_loss_ratio_above_100']} of {n} months above 100%" in text
        assert f"{sold['weeks_above_100']} of {sold['weeks']} weeks above 100%" in text
    for text in (memo, brief):
        assert f"{sold['stop_loss_cost_per_premium']['attach_100%']:.1%}" in text and f"{sold['stop_loss_cost_per_premium']['attach_90%']:.1%}" in text
    assert f"{sold['learning']['weeks']:.0f} weeks" in memo and f"{sold['learning']['weeks']:.0f} weeks" in brief and f"{sold['learning']['weeks']:.0f} weeks" in readme
    # the minimum connection time, as is and told the buffer
    sec = val[val.index("### 5G."):]
    assert f"**{m['60']:.2f}**" in sec and f"**{bm['35']:.2f}**" in sec and f"**{bm['60']:.2f}**" in sec
    for text in (readme, memo):
        assert f"{m['60']:.2f}" in text and f"{m['35']:.2f}" in text and f"{bm['60']:.2f}" in text
    assert max(bm.values()) - min(bm.values()) < 0.03                      # told the buffer, the minimum no longer matters
    # the refit bootstrap
    b = a["bootstrap"]
    assert b["refits"] == 8 and f"{b['pooled_sd']:.4f}" in sec and f"{b['pooled_min']:.3f} to {b['pooled_max']:.3f}" in sec
    assert b["pooled_max"] - b["pooled_min"] < 0.03
    # the six-month sold view stays in 5G, where it was measured
    s6 = a["exposure"]["offered_within_5%_cap"]
    assert f"**{s6['mean']:.0%}**" in sec and f"**{s6['worst_month']:.0%}** (July)" in sec and f"**{s6['weeks_above_100pct']} of {s6['weeks']}**" in sec
    # the demo file carries the same summaries
    demo = json.loads(re.sub(r"^window\.PRICES_V3 = |;\s*$", "", (ROOT / "site" / "prices_v3.js").read_text(encoding="utf-8")))["audit"]
    assert demo["rolling"]["loss_ratio"] == sold["pooled_loss_ratio"] and demo["rolling"]["months_above_100"] == sold["months_loss_ratio_above_100"]
    assert demo["mct_realized_over_target"] == m and demo["mct_buffer_realized_over_target"] == bm
    assert "1.54" in (ROOT / "PREREGISTRATION_2026H2_V3.md").read_text(encoding="utf-8")        # V2 as frozen is about all connections
    assert f"{every['ratio_sd']:.2f}" in val and "0.197" in val


def test_5h_5i_5j_numbers_match_the_results():
    val = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    comm = json.loads((ROOT / "results" / "commitments_v3.json").read_text())["unnamed_airlines_committed"]
    outb = json.loads((ROOT / "results" / "outbound_v3.json").read_text())
    cov = json.loads((ROOT / "results" / "coverage_v3.json").read_text())
    roll = json.loads((ROOT / "results" / "v3_rolling.json").read_text())
    eco = json.loads((ROOT / "results" / "economics_v3.json").read_text())
    h = val[val.index("### 5H."):]
    assert f"**{comm['overall']['own_commitment']:.1%}**" in h and f"{comm['overall']['uniform_rule']:.1%}" in h
    assert f"**{outb['extra_over_gap_miss']:.1%} more events**" in h and f"**{cov['passengers_on_routes_with_a_modelled_pairing']:.1%}**" in h
    assert f"{cov['pairings']['miss_rate_unrouted']:.2%} against {cov['pairings']['miss_rate_routed']:.2%}" in h
    assert all(not v["airline_commits_to_hotel"] for k, v in comm["by_carrier"].items() if k == "F9")
    hy = roll["by_hub_year_ratio"]["ORD"]
    assert f"Chicago ran {hy['2024']:.2f} in 2024, {hy['2025']:.2f} in 2025 and {hy['2026']:.2f} in 2026" in h
    assert f"**{eco['price_per_policy']:.2f}**" in h.replace("**$", "**") and f"**{eco['realized_loss_ratio_sold']:.0%}**" in h
    assert eco["margin_per_policy"]["expense_30%"] < 0 < eco["margin_per_policy"]["expense_20%"]


def test_readme_limits_table_has_every_limit_with_a_status_and_the_counts_are_right():
    import re
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    sec = text[text.index("## What this does **not** show"):text.index("## How it was validated")]
    rows = re.findall(r"^\| (\d+) \| (.+?) \| \*\*(Closed|Reduced|Open)\*\* \|", sec, flags=re.M)
    assert [int(r[0]) for r in rows] == list(range(1, 15))
    counts = {s: sum(1 for r in rows if r[2] == s) for s in ("Closed", "Reduced", "Open")}
    assert counts == {"Closed": 5, "Reduced": 7, "Open": 2}
    assert "**5 are closed**" in sec and "**7 are reduced**" in sec and "**2 are open**" in sec and "Of the 14 limits" in sec
    assert "agency-inputs.md" in sec


def test_market_evidence_note_says_what_was_not_found():
    text = (ROOT / "docs" / "market-evidence.md").read_text(encoding="utf-8")
    for needle in ("4% to 10% of trip cost", "about 25% of the ticket", "Not found.", "remains an assumption", "no number is quoted", "not a measurement"):
        assert needle in text, needle
    assert "Hopper" not in text                        # a figure from a page that could not be opened is not used


def test_the_first_read_of_the_v3_test_is_fixed_in_advance_and_documented_in_the_same_way_everywhere():
    for rel in ("docs/decisions.md", "docs/decision-memo.md", "VALIDATION.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "before any of the data exists" in text and "November" in text, rel
    assert "python -m mcp.holdout_v3 9 10 11" in (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    assert "python -m mcp.holdout_v3 9 10 11" in (ROOT / "README.md").read_text(encoding="utf-8")


# ---- the v4 pre-registration ----------------------------------------------------------------------------------

def test_v4_preregistration_freezes_the_artefacts_and_its_numbers_match_the_development_results():
    import hashlib
    text = (ROOT / "PREREGISTRATION_2026H2_V4.md").read_text(encoding="utf-8")
    for rel in ("models/pmiss_v3.joblib", "models/v4_loading.json", "results/gsa_costs.json"):
        raw = (ROOT / rel).read_bytes()
        raw = raw if rel.endswith(".joblib") else raw.replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() in text, rel
    assert hashlib.sha256((ROOT / "models" / "pmiss_v3.joblib").read_bytes()).hexdigest() == "339d3ad170cb2b67bd785533efed934beaf106b75b862844e6313ac4950c9107"   # unchanged since v3
    d = json.loads((ROOT / "results" / "v3_loading.json").read_text())
    f, sn = d["frozen"], d["frozen"]["september_to_november"]
    assert d["lambda_all_months"] == f["lambda"] == json.loads((ROOT / "models" / "v4_loading.json").read_text())["lambda"] == 1.16 and "1.16" in text
    for needle in (f"{d['unloaded']['loss_ratio']:.1%} to {d['loaded']['loss_ratio']:.1%}", f"{f['pooled_loss_ratio_loaded']:.1%}", f"{f['pooled_loss_ratio_unloaded']:.0%}",
                   f"{sn['2024']['unloaded_loss_ratio']:.1%}", f"{sn['2025']['unloaded_loss_ratio']:.1%}", f"{sn['2024']['loaded_loss_ratio']:.1%}", f"{sn['2025']['loaded_loss_ratio']:.1%}",
                   f"{f['share_sold_monthly']['min']:.1%} to {f['share_sold_monthly']['max']:.1%}", f"{f['three_month_blocks']['gain_points_mean']:.1f} on average",
                   f"{f['weeks_above_100_loaded']} of {f['weeks']} weeks", f"{d['windows']['12']:.1%}", f"{d['windows']['9']:.1%}", f"{d['windows']['6']:.1%}"):
        assert needle in text, needle
    assert sn["2024"]["weeks_above_100_loaded"] == 0 and sn["2025"]["weeks_above_100_loaded"] == 0 and "None of the 27 weeks" in text
    assert sn["2024"]["weeks"] + sn["2025"]["weeks"] == 27
    # the bands sit around the development values they are based on
    assert 0.25 < min(sn["2024"]["loaded_loss_ratio"], sn["2025"]["loaded_loss_ratio"]) and max(sn["2024"]["loaded_loss_ratio"], sn["2025"]["loaded_loss_ratio"]) < 0.55
    assert 0.28 < f["share_sold_monthly"]["min"] and f["share_sold_monthly"]["max"] < 0.42
    assert f["three_month_blocks"]["gain_points_min"] > 3.0 and "at least 3.0 points" in text
    assert "calm season" in text and "Passing this test does not show" in text


def test_the_experiment_plan_and_its_code_agree():
    plan = (ROOT / "docs" / "experiment-plan.md").read_text(encoding="utf-8")
    from mcp import demand
    for name in ("analyse", "decide", "simulate"):
        assert hasattr(demand, name) and name in plan
    assert "ten independent simulated experiments" in plan and "about 200 weeks" in plan


def test_the_survey_instrument_matches_the_demo_prices_and_the_code():
    import re
    from mcp.survey import LADDER, sample_size_share
    text = (ROOT / "docs" / "survey-instrument.md").read_text(encoding="utf-8")
    d = json.loads(re.sub(r"^window\.PRICES_V3 = |;\s*$", "", (ROOT / "site" / "prices_v3.js").read_text(encoding="utf-8")))
    for hub, slack in (("ATL", 105), ("ORD", 120), ("DFW", 135), ("DEN", 105), ("CLT", 150), ("ATL", 150)):
        c = next(x for x in d["cells"] if x["hub"] == hub and x["slack"] == slack)
        m = c["months"]["2027-01"]
        assert f"${c['p'] * m['cost'] / 0.65:.2f}" in text and f"${m['cost']:.0f}" in text and f"${c['fare']:.0f}" in text, (hub, slack)
    assert LADDER == (0.5, 0.8, 1.0, 1.25, 1.5, 2.0) and "0.5×, 0.8×, 1.0×, 1.25×, 1.5×, 2×" in text
    assert f"**{sample_size_share(0.05)}**" in text and f"**{sample_size_share(0.03):,}**" in text
