"""A model of the claims level, so that a price can follow a level that moves.

Season 2, WP1 (docs/season2-plan.md). Every repair so far treated the ratio of realized to expected claims as a constant
to be estimated late. Here the monthly log ratio z_t = log(claims / expected claims) is a series with a slowly moving
level, and each candidate forecasts z for month t from the months that would be known when month t is priced.

Known months. A month s is known when pricing month t if s <= t - lag. The lag is 2 for the gap cover (a month is
published about two months late, and v3 uses a one-month booking lag on top) and 5 for self-transfers (v5.1).

Candidates, fixed before any result is read (`CANDIDATES`):

    none          level 1 (z = 0). What v3 and v5.1 use. Its predictive variance is the mean squared z of the known months.
    last12        the mean of the last 12 known months.
    cred          Buhlmann-Straub credibility across hubs: each hub's recent mean shrunk toward the all-hub recent mean.
                  Needs a panel (several hubs), so it is run by `walk_forward_panel` only.
    local         a local-level state-space model (random walk plus noise) by Kalman filter, forecast `lag` months ahead.
                  Its one free ratio of variances is chosen by maximum likelihood on the known months only.
    local_season  `local` plus a month-of-year effect shrunk toward zero. Used only when at least SEASON_MIN_MONTHS (48)
                  months are known, and otherwise it IS `local`, which `used` records month by month. The primary candidate.

Every forecast is a normal distribution for z (a lognormal for the ratio), so scores and intervals are in log space.
Nothing here reads a month later than t - lag. tests/test_level.py changes later months and checks nothing moves.

    cd src && python -m mcp.level dev      # orientation run on the 26 development months, writes results/level_dev.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from mcp.risk import crps_normal, interval_coverage, log_score_normal, normal_interval

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ("none", "last12", "cred", "local", "local_season")
MIN_HISTORY = 6                 # known months needed before any forecast is made
SEASON_MIN_MONTHS = 48          # four years
RECENT = 12
SD_FLOOR = 0.05                 # a forecast is never sharper than 5% on the ratio
Q_GRID = np.logspace(-3, 1, 41)  # signal to noise ratios tried by the local-level likelihood
LEVEL = 0.90
LAGS = {"gap_cover": 2, "self_transfer": 5}


# ---- the local-level model -----------------------------------------------------------------------------------

def _filter(z: np.ndarray, q: float) -> dict:
    """Kalman filter of z_t = mu_t + e_t, mu_{t+1} = mu_t + h_t, with var(h)/var(e) = q and a diffuse start.
    Variances are in units of var(e). Returns the filtered level and its variance, and the concentrated log likelihood."""
    n = len(z)
    m = np.empty(n)
    P = np.empty(n)
    m[0], P[0] = z[0], 1.0
    sum_v2f, sum_logf = 0.0, 0.0
    for t in range(1, n):
        Pp = P[t - 1] + q
        F = Pp + 1.0
        v = z[t] - m[t - 1]
        m[t] = m[t - 1] + Pp / F * v
        P[t] = Pp / F
        sum_v2f += v * v / F
        sum_logf += math.log(F)
    s2 = max(sum_v2f / (n - 1), 1e-12)
    return {"m": m, "P": P, "q": q, "s2": s2, "loglik": -0.5 * ((n - 1) * math.log(s2) + sum_logf)}


def fit_local(z: np.ndarray) -> dict:
    """The local-level fit with q chosen on the grid by maximum likelihood."""
    z = np.asarray(z, float)
    best = None
    for q in Q_GRID:
        f = _filter(z, float(q))
        if best is None or f["loglik"] > best["loglik"]:
            best = f
    return best


def smooth_local(fit: dict) -> np.ndarray:
    """Fixed-interval (Rauch-Tung-Striebel) smoothed level, from a filter result."""
    m, P, q = fit["m"], fit["P"], fit["q"]
    s = m.copy()
    for t in range(len(m) - 2, -1, -1):
        J = P[t] / (P[t] + q)
        s[t] = m[t] + J * (s[t + 1] - m[t])
    return s


def _season_effects(z: np.ndarray, moy: np.ndarray, iterations: int = 6) -> tuple[np.ndarray, dict, np.ndarray, float]:
    """Backfit a local level and 12 month-of-year effects shrunk toward zero.
    Returns the effects, the final local fit on the de-seasonalised series, the counts per month and kappa."""
    counts = np.bincount(moy, minlength=12).astype(float)
    kappa = 10.0
    # Start from the raw month-of-year means about the overall mean. Starting from zero fails: a local level fitted to a
    # seasonal series follows the season, leaves no residual, and the effects then shrink to zero and stay there.
    gamma = np.zeros(12)
    for k in range(12):
        if counts[k] > 0:
            gamma[k] = (z[moy == k] - z.mean()).mean()
    for _ in range(iterations):
        fit = fit_local(z - gamma[moy])
        resid = z - smooth_local(fit)
        present = counts > 0
        means = np.zeros(12)
        for k in range(12):
            if counts[k] > 0:
                means[k] = resid[moy == k].mean()
        s2 = fit["s2"]
        spread = float(np.var(means[present], ddof=1)) if present.sum() > 1 else 0.0
        tau2 = max(spread - s2 / max(counts[present].mean(), 1.0), 1e-4)
        kappa = float(min(max(s2 / tau2, 0.5), 100.0))
        gamma = np.where(present, counts / (counts + kappa) * means, 0.0)
        gamma[present] -= gamma[present].mean()
    return gamma, fit, counts, kappa


# ---- forecasts of one month from known months ----------------------------------------------------------------

def _sd(var: float) -> float:
    return max(math.sqrt(max(var, 0.0)), SD_FLOOR)


def forecast(z_known, method: str, h: int, moy_known=None, moy_target: int | None = None) -> tuple[float, float, str]:
    """Mean and variance of z for the month `h` steps after the last known one, and the method actually used."""
    z = np.asarray(z_known, float)
    n = len(z)
    if n < MIN_HISTORY:
        raise ValueError(f"need at least {MIN_HISTORY} known months, got {n}")
    if method == "none":
        return 0.0, max(float(np.mean(z ** 2)), SD_FLOOR ** 2), "none"
    if method == "last12":
        w = z[-RECENT:]
        return float(w.mean()), max(float(w.var(ddof=1)) * (1 + 1 / len(w)), SD_FLOOR ** 2), "last12"
    if method == "local" or (method == "local_season" and (n < SEASON_MIN_MONTHS or moy_known is None)):
        fit = fit_local(z)
        var = fit["s2"] * (fit["P"][-1] + h * fit["q"] + 1.0)
        return float(fit["m"][-1]), max(var, SD_FLOOR ** 2), "local"
    if method == "local_season":
        moy = np.asarray(moy_known, int)
        gamma, fit, counts, kappa = _season_effects(z, moy)
        k = int(moy_target)
        var = fit["s2"] * (fit["P"][-1] + h * fit["q"] + 1.0) + fit["s2"] / (counts[k] + kappa)
        return float(fit["m"][-1] + gamma[k]), max(var, SD_FLOOR ** 2), "local_season"
    raise ValueError(f"unknown method {method!r}")


def month_of_year(months) -> np.ndarray:
    """0 to 11 from labels such as '2025-07'."""
    return np.array([int(str(m)[5:7]) - 1 for m in months])


def walk_forward(z, months, lag: int, method: str, min_history: int = MIN_HISTORY) -> dict:
    """For each month t, the forecast made from months s <= t - lag only. Months with too little history are NaN."""
    z = np.asarray(z, float)
    T = len(z)
    moy = month_of_year(months)
    mu, var = np.full(T, np.nan), np.full(T, np.nan)
    used = [None] * T
    for t in range(T):
        n_known = t - lag + 1
        if n_known < max(min_history, MIN_HISTORY):
            continue
        mu[t], var[t], used[t] = forecast(z[:n_known], method, lag, moy[:n_known], int(moy[t]))
    return {"mu": mu, "var": var, "used": used}


def credibility_panel(window: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Buhlmann-Straub across the columns (hubs) of a window of months. Returns the credibility-weighted level of each
    hub, its predictive variance, the credibility factor Z and the all-hub level."""
    n, H = window.shape
    recent = window.mean(axis=0)
    epv = float(np.mean(window.var(axis=0, ddof=1)))              # expected process variance (within a hub)
    vhm = max(float(recent.var(ddof=1)) - epv / n, 0.0) if H > 1 else 0.0   # variance of hypothetical means (between hubs)
    Z = 0.0 if vhm <= 0 else n / (n + epv / vhm)
    collective = float(recent.mean())
    level = Z * recent + (1 - Z) * collective
    var = np.full(H, max(epv + (1 - Z) * vhm, SD_FLOOR ** 2))
    return level, var, float(Z), collective


def walk_forward_panel(Z, months, lag: int, method: str, min_history: int = MIN_HISTORY) -> dict:
    """`walk_forward` for a panel (months x hubs). `cred` uses all hubs together, the others each hub alone."""
    Z = np.asarray(Z, float)
    T, H = Z.shape
    if method != "cred":
        runs = [walk_forward(Z[:, h], months, lag, method, min_history) for h in range(H)]
        return {"mu": np.column_stack([r["mu"] for r in runs]), "var": np.column_stack([r["var"] for r in runs]),
                "used": [[r["used"][t] for r in runs] for t in range(T)]}
    mu, var = np.full((T, H), np.nan), np.full((T, H), np.nan)
    z_cred = np.full(T, np.nan)
    for t in range(T):
        n_known = t - lag + 1
        if n_known < max(min_history, MIN_HISTORY):
            continue
        window = Z[max(0, n_known - RECENT):n_known]
        mu[t], var[t], z_cred[t], _ = credibility_panel(window)
    return {"mu": mu, "var": var, "credibility": z_cred, "used": [["cred"] * H if not np.isnan(z_cred[t]) else [None] * H for t in range(T)]}


# ---- scoring a method's forecasts ----------------------------------------------------------------------------

def score(z, mu, var, level: float = LEVEL) -> dict:
    """Scores over the months that have a forecast. CRPS and log score are in log-ratio units, lower is better."""
    z, mu, var = (np.asarray(a, float).ravel() for a in (z, mu, var))
    ok = ~np.isnan(mu)
    sd = np.sqrt(var[ok])
    lo, hi = normal_interval(mu[ok], sd, level)
    return {"n": int(ok.sum()), "crps": float(crps_normal(z[ok], mu[ok], sd).mean()), "log_score": float(log_score_normal(z[ok], mu[ok], sd).mean()),
            "mae_log": float(np.abs(z[ok] - mu[ok]).mean()), "bias_log": float((z[ok] - mu[ok]).mean()),
            "coverage": interval_coverage(z[ok], lo, hi), "nominal": level, "mean_width_log": float((hi - lo).mean())}


def repriced_ratio(claims, expected, mu, var) -> dict:
    """What the realized/expected ratio would have been had the expected claims been multiplied by the forecast level
    exp(mu + var / 2), the mean of the lognormal. Over months that have a forecast. 1.0 would be exactly on target."""
    claims, expected, mu, var = (np.asarray(a, float).ravel() for a in (claims, expected, mu, var))
    ok = ~np.isnan(mu)
    unadjusted = claims[ok].sum() / expected[ok].sum()
    adjusted = claims[ok].sum() / (expected[ok] * np.exp(mu[ok] + var[ok] / 2)).sum()
    return {"unadjusted": float(unadjusted), "repriced": float(adjusted), "months": int(ok.sum())}


def conformal_coverage(z, mu, lag: int, level: float = LEVEL, min_errors: int = 6) -> dict:
    """Adaptive split-conformal comparator for the normal intervals. For month t the half-width is the empirical
    `level` quantile of |z_s - mu_s| over the months s <= t - lag that already had a forecast, so it uses only what is
    known at pricing time. Months with fewer than `min_errors` such errors get no interval."""
    z, mu = np.asarray(z, float), np.asarray(mu, float)
    hits, widths = [], []
    for t in range(len(z)):
        if np.isnan(mu[t]):
            continue
        s = np.arange(0, t - lag + 1)
        err = np.abs(z[s] - mu[s])
        err = err[~np.isnan(err)]
        if len(err) < min_errors:
            continue
        k = min(int(math.ceil((len(err) + 1) * level)), len(err))
        q = float(np.sort(err)[k - 1])
        hits.append(abs(z[t] - mu[t]) <= q)
        widths.append(2 * q)
    return {"n": len(hits), "coverage": float(np.mean(hits)) if hits else None, "mean_width_log": float(np.mean(widths)) if widths else None}


# ---- orientation run on the development months ---------------------------------------------------------------

def monthly_panel(weeks, sold_only: bool):
    """Monthly claims and expected claims by hub from the weekly backtest file (results/v3_rolling_weeks.csv)."""
    d = weeks[weeks["sold"]] if sold_only else weeks
    g = d.groupby(["ym", "hub"])[["claims", "expected"]].sum().reset_index()
    claims = g.pivot(index="ym", columns="hub", values="claims").sort_index()
    expected = g.pivot(index="ym", columns="hub", values="expected").sort_index()
    return claims, expected


def dev() -> dict:
    import pandas as pd
    weeks = pd.read_csv(ROOT / "results" / "v3_rolling_weeks.csv")
    lag = LAGS["gap_cover"]
    out = {"status": "development orientation on the 26 out-of-sample months of the gap cover, not a test",
           "lag_months": lag, "min_history": MIN_HISTORY, "candidates": list(CANDIDATES), "level": LEVEL,
           "self_transfer": "not run: the committed results hold no monthly series for the self-transfer walk-forward. It needs the pairings (WP3) and is graded as B8",
           "season_note": f"local_season needs {SEASON_MIN_MONTHS} known months, so every month here falls back to local"}
    for view, sold in (("all_overnight_risk", False), ("sold_within_cap", True)):
        claims, expected = monthly_panel(weeks, sold)
        months = list(claims.index)
        res = {"months": len(months), "first": months[0], "last": months[-1], "hubs": list(claims.columns)}
        pooled_c, pooled_e = claims.sum(axis=1).to_numpy(), expected.sum(axis=1).to_numpy()
        z_pool = np.log(pooled_c / pooled_e)
        Zp = np.log(claims.to_numpy() / expected.to_numpy())
        pooled, panel = {}, {}
        for method in CANDIDATES:
            if method != "cred":
                wf = walk_forward(z_pool, months, lag, method)
                s = score(z_pool, wf["mu"], wf["var"])
                s.update(repriced_ratio(pooled_c, pooled_e, wf["mu"], wf["var"]))
                s["conformal"] = conformal_coverage(z_pool, wf["mu"], lag)
                s["used"] = sorted({u for u in wf["used"] if u})
                pooled[method] = s
            wp = walk_forward_panel(Zp, months, lag, method)
            s = score(Zp, wp["mu"], wp["var"])
            s.update(repriced_ratio(claims.to_numpy(), expected.to_numpy(), wp["mu"], wp["var"]))
            s["used"] = sorted({u for row in wp["used"] for u in row if u})
            if method == "cred":
                zc = wp["credibility"]
                s["credibility_mean"] = float(np.nanmean(zc))
            panel[method] = s
        res["pooled_series"] = pooled
        res["hub_panel"] = panel
        res["best_by_crps"] = {"pooled": min(pooled, key=lambda k: pooled[k]["crps"]), "hub_panel": min(panel, key=lambda k: panel[k]["crps"])}
        out[view] = res
    path = ROOT / "results" / "level_dev.json"
    path.write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    {"dev": dev}[sys.argv[1] if len(sys.argv) > 1 else "dev"]()
