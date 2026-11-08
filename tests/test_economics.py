"""The attach-rate arithmetic, on numbers that can be checked by hand."""
import math

import pytest

from mcp.economics import break_even_attach, margin_per_policy, profit


def test_margin_is_what_is_left_after_claims_and_the_agencys_costs():
    assert margin_per_policy(10.0, 0.65, 0.20) == pytest.approx(1.5)
    assert margin_per_policy(10.0, 0.80, 0.30) == pytest.approx(-1.0)              # a loss ratio plus costs above 100% loses money


def test_profit_scales_with_offers_and_attach():
    assert profit(100_000, 0.05, 10.0, 0.65, 0.20) == pytest.approx(100_000 * 0.05 * 1.5)
    assert profit(200_000, 0.05, 10.0, 0.65, 0.20) == pytest.approx(2 * profit(100_000, 0.05, 10.0, 0.65, 0.20))


def test_break_even_attach_inverts_profit_and_is_infinite_when_each_policy_loses():
    a = break_even_attach(100_000, 3_750.0, 10.0, 0.65, 0.20)
    assert a == pytest.approx(0.025) and profit(100_000, a, 10.0, 0.65, 0.20) == pytest.approx(3_750.0)
    assert math.isinf(break_even_attach(100_000, 1_000.0, 10.0, 0.80, 0.30))
