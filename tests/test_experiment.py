"""Sample-size maths against textbook values worked out independently."""
import pytest

from mcp.experiment import n_slope, n_two_prop, weeks_for_ratio, z


def test_normal_quantiles():
    assert z(0.975) == pytest.approx(1.95996, abs=1e-4)
    assert z(0.80) == pytest.approx(0.84162, abs=1e-4)


def test_two_proportion_matches_the_standard_calculator_value():
    # 10% -> 12% (20% lift), alpha .05 two-sided, power .80: the usual answer is about 3,841 per arm
    assert n_two_prop(0.10, 0.20) == pytest.approx(3841, abs=2)


def test_two_proportion_matches_a_second_known_case():
    # 5% -> 6%: about 8,155 per arm by the same formula
    assert n_two_prop(0.05, 0.20) == pytest.approx(8155, abs=3)


def test_smaller_effects_and_rarer_events_need_more_people():
    assert n_two_prop(0.05, 0.10) > n_two_prop(0.05, 0.20) > n_two_prop(0.05, 0.30)
    assert n_two_prop(0.01, 0.20) > n_two_prop(0.05, 0.20) > n_two_prop(0.10, 0.20)


def test_slope_sample_size_by_hand():
    # ((1.95996 + 0.84162) / 0.5)^2 / (0.5^2 x 0.05 x 0.95) = 31.40 / 0.011875 = 2,644
    assert n_slope(sd_x=0.5, attach=0.05, effect=0.5) == pytest.approx(2644, abs=3)


def test_slope_needs_more_travellers_when_risk_varies_little_or_the_effect_is_small():
    assert n_slope(0.3, 0.05, 0.5) > n_slope(0.6, 0.05, 0.5)
    assert n_slope(0.5, 0.05, 0.25) == pytest.approx(4 * n_slope(0.5, 0.05, 0.5), rel=0.01)


def test_weeks_for_ratio_by_hand():
    # (1.96 x 0.25 / 0.10)^2 = 24.01 -> 25 weeks
    assert weeks_for_ratio(0.25, 0.10) == 25
    assert weeks_for_ratio(0.25, 0.20) == 7       # half the precision needs a quarter of the weeks


def test_weeks_do_not_depend_on_volume():
    import inspect
    assert "policies" not in inspect.signature(weeks_for_ratio).parameters


def test_small_books_need_more_weeks_and_big_books_converge_to_the_volume_free_answer():
    from mcp.experiment import weeks_for_ratio_at_volume
    few = weeks_for_ratio_at_volume(0.25, 4.0, 100, 0.10)
    many = weeks_for_ratio_at_volume(0.25, 4.0, 10_000_000, 0.10)
    assert few > weeks_for_ratio(0.25, 0.10)
    assert many == weeks_for_ratio(0.25, 0.10) == 25


def test_volume_noise_by_hand():
    # cv_total^2 = 0.25^2 + 4^2/1000 = 0.0625 + 0.016 = 0.0785 -> cv 0.28018; (1.96 x 0.28018 / 0.10)^2 = 30.2 -> 31
    from mcp.experiment import weeks_for_ratio_at_volume
    assert weeks_for_ratio_at_volume(0.25, 4.0, 1000, 0.10) == 31
