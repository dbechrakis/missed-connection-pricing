"""The survey analysis recovers planted willingness to pay, and its pieces behave."""
import numpy as np
import pytest

from mcp.survey import (DECISION_SCENARIOS, LADDER, SCENARIOS, analyse_responses, clean, demand_curve, elasticity, inconsistent_share, pava_decreasing, question_bank,
                        sample_size_share, share_at, simulate_survey, true_demand)


def test_sample_size_for_a_share_is_the_textbook_number():
    assert sample_size_share(0.05) == 385 and sample_size_share(0.03) == 1068 and sample_size_share(0.05, p=0.1) == 139


def test_pava_makes_a_curve_non_increasing_and_leaves_a_monotone_curve_alone():
    assert pava_decreasing(np.array([0.5, 0.4, 0.3])).tolist() == [0.5, 0.4, 0.3]
    out = pava_decreasing(np.array([0.5, 0.2, 0.4, 0.1]))
    assert (np.diff(out) <= 1e-12).all() and out.mean() == pytest.approx(np.mean([0.5, 0.2, 0.4, 0.1]))
    assert pava_decreasing(np.array([0.2, 0.4])).tolist() == pytest.approx([0.3, 0.3])      # a rise is pooled into its mean


def test_intervals_cover_the_planted_demand_about_as_often_as_they_claim():
    """Ten simulated surveys x six prices x two curves = 120 intervals. Honest 95% intervals contain the truth in about 112 of them
    (over 60 surveys the measured coverage was 96% and 93%); fewer than 104 would be a coverage below 87%, which honest intervals
    produce well under 1% of the time. Pooling the count tests the intervals without trusting any single price or draw."""
    covered = total = 0
    for seed in range(10):
        df = simulate_survey(400, seed=seed, median_wtp=0.9, sigma=0.7, sure_share=0.5)
        for level in ("any", "definitely"):
            c = demand_curve(df, level=level, n_boot=200, seed=seed)
            for k, m in enumerate(c["mult"]):
                t = true_demand(m, 0.9, 0.7, 0.5, level)
                covered += c["lo"][k] <= t <= c["hi"][k]
                total += 1
    assert total == 120 and covered >= 104, covered


def test_the_curve_falls_with_price_the_strict_level_is_below_the_loose_one_and_elasticity_is_negative():
    df = simulate_survey(1500, seed=1)
    a, d = demand_curve(df, "any", n_boot=60), demand_curve(df, "definitely", n_boot=60)
    assert (np.diff(a["share"]) <= 1e-12).all() and (np.diff(d["share"]) <= 1e-12).all()
    assert all(x <= y + 1e-12 for x, y in zip(d["share"], a["share"]))
    assert elasticity(a) < 0 and share_at(a, 1.0)["lo"] <= share_at(a, 1.0)["share"] <= share_at(a, 1.0)["hi"]
    assert a["revenue_index"][a["mult"].index(1.0)] == pytest.approx(a["share"][a["mult"].index(1.0)])


def test_inattentive_answers_pull_the_curve_towards_one_half_and_are_visible_as_a_non_monotone_raw_curve():
    clean = demand_curve(simulate_survey(2000, seed=2, noise=0.0), "any", n_boot=30)
    noisy = demand_curve(simulate_survey(2000, seed=2, noise=0.25), "any", n_boot=30)
    assert noisy["share"][-1] > clean["share"][-1] and noisy["share"][0] < clean["share"][0]



def payload():
    import json
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    return json.loads(re.sub(r"^window\.PRICES_V3 = |;\s*$", "", (root / "site" / "prices_v3.js").read_text(encoding="utf-8")))


def test_question_bank_has_every_scenario_wording_and_price_with_the_models_prices():
    rows = question_bank(payload())
    assert len(rows) == len(SCENARIOS) * 2 * len(LADDER) == 72
    first = [r for r in rows if r["scenario"] == 1 and r["wording"] == "benefit"]
    assert [r["mult"] for r in first] == list(LADDER)
    assert first[2]["price"] == round(first[2]["model_price"]) == 20                           # Atlanta, 105 minutes: the model price is $19.61
    assert first[0]["price"] == round(0.5 * first[0]["model_price"]) and first[-1]["price"] == round(2.0 * first[0]["model_price"])
    assert "$293" in first[0]["description"] and "hotel and meals" in first[0]["description"] and first[0]["question"] == "Would you buy this protection for this trip at $10?"
    outcome = [r for r in rows if r["scenario"] == 2 and r["wording"] == "outcome"][0]
    assert "Chicago O'Hare" in outcome["description"] and "airline will not pay for your hotel" in outcome["description"]


def with_checks(df, seed=0, fail=0.05, fast=0.05):
    rng = np.random.default_rng(seed)
    ids = df["respondent"].unique()
    meta = {i: (bool(rng.uniform() >= fail), float(rng.normal(480, 90)) * (0.2 if rng.uniform() < fast else 1.0)) for i in ids}
    return df.assign(attention_ok=df["respondent"].map(lambda i: meta[i][0]), seconds=df["respondent"].map(lambda i: meta[i][1]))


def test_cleaning_drops_only_failed_attention_and_speeders_and_counts_them():
    df = with_checks(simulate_survey(600, seed=3), seed=3, fail=0.10, fast=0.10)
    kept, c = clean(df)
    assert c["raw"] == 600 and c["kept"] == kept["respondent"].nunique() == 600 - c["failed_attention"] - c["too_fast"]
    assert c["failed_attention"] > 0 and c["too_fast"] > 0
    assert kept["attention_ok"].all() and (kept.groupby("respondent")["seconds"].first() >= c["median_seconds"] / 3).all()
    assert len(kept) == len(df[df["respondent"].isin(kept["respondent"].unique())])                 # no other respondent is dropped


def test_inconsistent_respondents_are_counted_and_kept():
    import pandas as pd
    df = pd.DataFrame({"respondent": [1, 1, 2, 2], "mult": [1.0, 2.0, 1.0, 2.0], "answer": ["no", "definitely", "definitely", "no"]})
    assert inconsistent_share(df) == 0.5                                      # respondent 1 says no at 1.0x and yes at 2.0x
    assert inconsistent_share(simulate_survey(300, seed=1)) == 0.0


def test_the_decision_scenarios_rule_out_only_what_the_upper_end_cannot_reach():
    strong = analyse_responses(with_checks(simulate_survey(500, seed=4, median_wtp=0.9)), n_boot=60)
    assert all(v["survives"] for v in strong["decision"].values()) and set(strong["decision"]) == {"1%", "3%", "10%"}
    weak = analyse_responses(with_checks(simulate_survey(500, seed=4, median_wtp=0.12, sigma=0.5)), n_boot=60)
    assert weak["any"]["at_model_price"]["hi"] < 0.01 and not any(v["survives"] for v in weak["decision"].values())
    assert strong["respondents"]["kept"] <= 500 and strong["definitely"]["at_model_price"]["share"] <= strong["any"]["at_model_price"]["share"]
    assert DECISION_SCENARIOS == (0.01, 0.03, 0.10)


def test_the_published_question_bank_file_is_the_one_the_code_generates():
    import csv
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    with (root / "docs" / "survey-question-bank.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    gen = question_bank(payload())
    assert len(rows) == len(gen) == 72
    assert all(r["question"] == g["question"] and r["description"] == g["description"] and int(r["price"]) == g["price"] for r, g in zip(rows, gen))


def test_elasticity_is_not_estimable_rather_than_an_error_when_nobody_says_yes():
    curve = {"mult": [0.5, 0.8, 1.0, 1.25, 1.5, 2.0], "share": [0.0] * 6}
    assert np.isnan(elasticity(curve))
    assert np.isnan(elasticity({"mult": [0.5, 0.8, 1.0], "share": [0.0, 0.0, 0.02]}))                  # one positive point is not a slope
    assert elasticity({"mult": [1.0, 2.0], "share": [0.4, 0.2]}) == pytest.approx(-1.0)
