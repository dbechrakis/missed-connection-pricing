"""Risk arithmetic for a book whose claims move together: stop-loss cost, annual tails, capital margin, and the scores
used to judge a predictive distribution. Pure numpy, no data access.

Season 2 (docs/season2-plan.md, WP1). The functions here carry no result of their own. `mcp.level` uses the scores to
judge level models, and a later package (WP5) feeds them the weekly series to price the weather risk.

Conventions. A loss ratio is claims divided by premium. A weekly series is a pandas Series or an array of weekly loss
ratios. "Per unit of premium" means divided by that period's premium, so a stop-loss at attachment `a` costs
mean(max(LR - a, 0)) per unit of premium when every period has the same premium.
"""
from __future__ import annotations

import math

import numpy as np

_ERF = np.frompyfunc(math.erf, 1, 1)


def _phi(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _Phi(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.array(_ERF(np.asarray(x, float) / math.sqrt(2)), dtype=float))


def norm_ppf(p: float) -> float:
    """Inverse normal CDF by bisection on erf. Accurate to 1e-12, and enough for the few quantiles needed here."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if 0.5 * (1.0 + math.erf(mid / math.sqrt(2))) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---- scores for a predictive distribution --------------------------------------------------------------------

def crps_normal(y, mu, sd) -> np.ndarray:
    """Continuous ranked probability score of a normal forecast N(mu, sd^2) against outcome y. Lower is better.
    Closed form: sd * (w * (2 Phi(w) - 1) + 2 phi(w) - 1 / sqrt(pi)), with w = (y - mu) / sd."""
    y, mu, sd = (np.asarray(a, float) for a in (y, mu, sd))
    if np.any(sd <= 0):
        raise ValueError("sd must be positive")
    w = (y - mu) / sd
    return sd * (w * (2 * _Phi(w) - 1) + 2 * _phi(w) - 1 / math.sqrt(math.pi))


def log_score_normal(y, mu, sd) -> np.ndarray:
    """Negative log density of N(mu, sd^2) at y. Lower is better."""
    y, mu, sd = (np.asarray(a, float) for a in (y, mu, sd))
    return 0.5 * math.log(2 * math.pi) + np.log(sd) + 0.5 * ((y - mu) / sd) ** 2


def interval_coverage(y, lo, hi) -> float:
    """Share of outcomes inside [lo, hi]."""
    y, lo, hi = (np.asarray(a, float) for a in (y, lo, hi))
    return float(np.mean((y >= lo) & (y <= hi)))


def normal_interval(mu, sd, level: float = 0.90) -> tuple[np.ndarray, np.ndarray]:
    z = norm_ppf(0.5 + level / 2)
    mu, sd = np.asarray(mu, float), np.asarray(sd, float)
    return mu - z * sd, mu + z * sd


# ---- stop-loss and tails -------------------------------------------------------------------------------------

def stop_loss_cost(loss_ratios, attach: float) -> float:
    """Expected excess of a period's loss ratio over `attach`, per unit of premium (equal premium per period)."""
    x = np.asarray(loss_ratios, float)
    return float(np.maximum(x - attach, 0.0).mean())


def aggregate_loss_ratio(claims, premium, groups) -> np.ndarray:
    """Loss ratio of each group (for example each month or each year) from period claims and premium, so that a
    period with more premium weighs more. Groups come back in sorted order."""
    claims, premium, groups = np.asarray(claims, float), np.asarray(premium, float), np.asarray(groups)
    keys = np.unique(groups)
    return np.array([claims[groups == k].sum() / premium[groups == k].sum() for k in keys])


def var_tvar(x, level: float = 0.95) -> tuple[float, float]:
    """Value at risk (the `level` quantile) and tail value at risk (the mean of the outcomes at or above it)."""
    x = np.sort(np.asarray(x, float))
    k = int(math.ceil(level * len(x))) - 1
    k = min(max(k, 0), len(x) - 1)
    var = float(x[k])
    return var, float(x[k:].mean())


def capital_margin(annual_loss_ratio, level: float = 0.95, cost_of_capital: float = 0.10) -> dict:
    """Margin per unit of premium that pays a cost of capital on the capital needed to survive to `level`.
    Capital is the tail value at risk of the annual loss ratio less its mean (what the premium does not cover in a bad
    year). The annual loss ratio is taken against the premium as priced, so the mean is not forced to a target."""
    x = np.asarray(annual_loss_ratio, float)
    var, tvar = var_tvar(x, level)
    capital = max(tvar - float(x.mean()), 0.0)
    return {"mean": float(x.mean()), "var": var, "tvar": tvar, "capital_per_premium": capital,
            "margin_per_premium": cost_of_capital * capital, "level": level, "cost_of_capital": cost_of_capital}


# ---- simulating years from a short weekly record -------------------------------------------------------------

def season_of_week(week_start) -> np.ndarray:
    """Calendar quarter (0 to 3) of each week start date, as a numpy array. Accepts datetime64, strings or pandas dates."""
    months = np.asarray(week_start, dtype="datetime64[D]").astype("datetime64[M]").astype(int) % 12
    return months // 3


def season_block_bootstrap_years(claims, premium, week_start, n_sim: int = 2000, block: int = 4, seed: int = 0) -> dict:
    """Simulated years of 52 weeks from a short weekly record.

    The weather is seasonal, so a simulated year is built quarter by quarter. For each of the four quarters it draws
    runs of `block` neighbouring weeks from the observed weeks of that quarter (any year), until 13 weeks are filled.
    Runs keep the week-to-week dependence that weather creates. A run never crosses a gap in the record.
    Returns the annual loss ratio of each simulated year and the weekly loss ratios, both against the premium drawn.
    """
    claims, premium = np.asarray(claims, float), np.asarray(premium, float)
    ws = np.asarray(week_start, dtype="datetime64[D]")
    order = np.argsort(ws)
    claims, premium, ws = claims[order], premium[order], ws[order]
    q = season_of_week(ws)
    # a run is `block` consecutive records that are all 7 days apart and all in the same quarter
    runs = {k: [] for k in range(4)}
    for i in range(len(ws) - block + 1):
        seg = ws[i:i + block]
        if np.all(np.diff(seg).astype(int) == 7) and len(set(q[i:i + block])) == 1:
            runs[int(q[i])].append(i)
    missing = [k for k, v in runs.items() if not v]
    if missing:
        raise ValueError(f"no run of {block} consecutive weeks in quarter(s) {missing}: the record is too short")
    rng = np.random.default_rng(seed)
    per_q = int(math.ceil(13 / block))
    annual = np.empty(n_sim)
    weekly = np.empty((n_sim, 13 * 4))
    for s in range(n_sim):
        c_all, p_all = [], []
        for k in range(4):
            starts = rng.choice(runs[k], per_q)
            c = np.concatenate([claims[i:i + block] for i in starts])[:13]
            p = np.concatenate([premium[i:i + block] for i in starts])[:13]
            c_all.append(c)
            p_all.append(p)
        c, p = np.concatenate(c_all), np.concatenate(p_all)
        annual[s] = c.sum() / p.sum()
        weekly[s] = c / p
    return {"annual_loss_ratio": annual, "weekly_loss_ratio": weekly}
