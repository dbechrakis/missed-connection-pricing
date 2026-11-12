"""The technical price of a cover whose claims move together: expected claims, a stop-loss, a capital margin and expenses.

Season 2, WP5 (docs/season2-plan.md). Everything is per unit of expected claims. A weekly series gives r_w, realized over
expected claims of week w. A premium of pi per unit of expected claims gives a weekly loss ratio LR_w = r_w / pi.

    pi * (1 - expense) = retained loss ratio * pi + stop-loss cost * pi + capital margin * pi          (per unit expected claims, divided by pi)

or, in premium units, 1 - expense = E[min(LR, a)] + E[(LR - a)+] + margin, where `a` is the weekly attachment of a
stop-loss (no attachment: nothing ceded). The stop-loss cost is its burning cost on the record, the margin is a cost of
capital on the tail value at risk of the annual retained loss ratio beyond its mean, the annual distribution comes from a
season block bootstrap of the weekly record (`mcp.risk`). The unknown pi is found by bisection. The loading is pi
relative to the price of the project's products, expected claims over the 65% target loss ratio.

Nothing is fitted to the record except pi. The record is short, so the answer is development evidence, and a 1-in-100 year
cannot be read from it: `mcp.risk` reports 1-in-10 and 1-in-20 with their intervals.
"""
from __future__ import annotations

import numpy as np

from mcp import risk

TARGET_LR = 0.65
CURRENT_PI = 1 / TARGET_LR           # the price of the existing products per unit of expected claims


def retained_and_ceded(lr: np.ndarray, attach: float | None) -> tuple[np.ndarray, np.ndarray]:
    lr = np.asarray(lr, float)
    if attach is None:
        return lr, np.zeros_like(lr)
    return np.minimum(lr, attach), np.maximum(lr - attach, 0.0)


def components(pi: float, claims, expected, week_start, attach, coc, level, n_sim, block, seed) -> dict:
    """The three terms of the equation at a trial premium pi, per unit of premium."""
    claims, expected = np.asarray(claims, float), np.asarray(expected, float)
    premium = pi * expected
    ret, ced = retained_and_ceded(claims / premium, attach)
    w = premium / premium.sum()
    retained_lr, ceded_cost = float((w * ret).sum()), float((w * ced).sum())
    ret_claims = ret * premium
    ced_claims = ced * premium
    sim = risk.season_block_bootstrap_years(ret_claims, premium, week_start, n_sim=n_sim, block=block, seed=seed)["annual_loss_ratio"]
    cap = risk.capital_margin(sim, level=level, cost_of_capital=coc)
    return {"retained_loss_ratio": retained_lr, "stop_loss_cost": ceded_cost, "capital": cap["capital_per_premium"],
            "capital_margin": cap["margin_per_premium"], "annual_var": cap["var"], "annual_tvar": cap["tvar"], "annual_mean": cap["mean"]}


def solve(claims, expected, week_start, attach: float | None = None, coc: float = 0.10, level: float = 0.95, expense: float = 0.0,
          n_sim: int = 2000, block: int = 4, seed: int = 0, lo: float = 0.3, hi: float = 8.0, tol: float = 1e-4) -> dict:
    """The premium per unit of expected claims at which premium net of expenses equals retained claims, the stop-loss cost
    and the capital margin. Returns pi, the loading against the existing price (1 / 65%), and the terms."""
    def gap(pi: float) -> float:
        c = components(pi, claims, expected, week_start, attach, coc, level, n_sim, block, seed)
        return (1 - expense) - (c["retained_loss_ratio"] + c["stop_loss_cost"] + c["capital_margin"])
    if gap(lo) > 0 or gap(hi) < 0:
        raise ValueError("no premium between the bounds balances the book")
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if gap(mid) < 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    pi = 0.5 * (lo + hi)
    c = components(pi, claims, expected, week_start, attach, coc, level, n_sim, block, seed)
    return {"pi": pi, "loading_vs_current": pi / CURRENT_PI, "expense": expense, "attach": attach, "coc": coc, "level": level,
            "terms": c, "residual": gap(pi)}


def diversification(weekly_by_hub: dict) -> dict:
    """How much of the weekly risk is shared between hubs. `weekly_by_hub` maps a hub to an array of its weekly
    realized/expected ratios (equal length, same weeks). Returns the correlation matrix, the standard deviation of the
    pooled ratio (equal expected claims) and the mean single-hub standard deviation. A ratio near 1 means no diversification."""
    hubs = sorted(weekly_by_hub)
    X = np.column_stack([np.asarray(weekly_by_hub[h], float) for h in hubs])
    corr = np.corrcoef(X, rowvar=False)
    pooled = X.mean(axis=1)
    single = X.std(axis=0, ddof=1)
    return {"hubs": hubs, "correlation": corr.tolist(), "mean_pairwise_correlation": float((corr.sum() - len(hubs)) / (len(hubs) * (len(hubs) - 1))),
            "sd_pooled": float(pooled.std(ddof=1)), "sd_single_mean": float(single.mean()), "ratio": float(pooled.std(ddof=1) / single.mean())}
