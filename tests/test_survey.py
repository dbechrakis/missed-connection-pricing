"""The survey analysis recovers planted willingness to pay, and its pieces behave."""
import numpy as np
import pytest

from mcp.survey import LADDER, demand_curve, elasticity, pava_decreasing, sample_size_share, share_at, simulate_survey, true_demand


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
