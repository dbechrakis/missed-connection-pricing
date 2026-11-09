"""The demand experiment, written before it runs: the analysis, a decision rule, and a simulator that checks the analysis.

Nobody has bought this cover, so demand cannot be measured from public data. What can be done in advance is to fix, before
any customer is shown an offer, exactly how the experiment will be analysed and what each result will mean. This module is
that analysis. It takes one row per traveller shown the offer (or in the no-offer control) and returns:

  attach rate         by price arm, with Wilson intervals
  price response      the logit coefficient on log price shown (about the elasticity of the attach rate when attach is small)
  self-selection      the coefficient on log model risk with the price shown held fixed (theta: do riskier connections buy
                      more, beyond price); the net tilt of buyers toward risk at the prices actually charged (theta plus
                      the price response, because the price rises with risk); and the realized / expected claims among
                      buyers over the same among everyone shown, with a weekly block bootstrap (buyers who know more than
                      the model show up here)

Why theta needs the price shown, not just the price arm. The price is the model's risk times the payout, times the arm's
multiplier, so a traveller who reacts to price also reacts to risk. A regression on the arm multiplier alone returns
theta + elasticity, not theta: with an elasticity of -1.5 a true theta of +0.5 reads as -1.0. With the price shown held fixed,
only the arm multipliers move price independently of risk, so theta is identified from them alone and needs far more
travellers than the net tilt (`mcp.experiment.n_theta_beyond_price`).
  message effect      the odds ratio of the outcome-led wording against the benefit-led one, price held fixed
  guardrail           booking conversion of travellers shown the offer against the no-offer control
  margin per offer    attach rate x (price - payout), per price arm

`simulate` generates travellers with planted answers, so a test can check that the analysis recovers them. It does not say
what real travellers do; it says the analysis would find it if they did.

    from mcp.demand import analyse, decide, simulate
    result = analyse(simulate(400_000, seed=1))
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TARGET_LR = 0.65


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return float(c - h), float(c + h)


def logit_fit(X: np.ndarray, y: np.ndarray, iters: int = 60) -> dict:
    """Logistic regression by iteratively reweighted least squares, with standard errors from the information matrix."""
    X, y = np.asarray(X, float), np.asarray(y, float)
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        eta = np.clip(X @ beta, -30, 30)
        mu = 1 / (1 + np.exp(-eta))
        w = np.maximum(mu * (1 - mu), 1e-9)
        z = eta + (y - mu) / w
        A = X.T @ (X * w[:, None]) + 1e-9 * np.eye(X.shape[1])
        new = np.linalg.solve(A, X.T @ (w * z))
        if np.max(np.abs(new - beta)) < 1e-9:
            beta = new
            break
        beta = new
    eta = np.clip(X @ beta, -30, 30)
    mu = 1 / (1 + np.exp(-eta))
    w = np.maximum(mu * (1 - mu), 1e-9)
    cov = np.linalg.inv(X.T @ (X * w[:, None]) + 1e-9 * np.eye(X.shape[1]))
    return {"beta": beta, "se": np.sqrt(np.diag(cov))}


def ratio_of_claims(df: pd.DataFrame) -> float:
    """Realized / model-expected payouts, cost-weighted."""
    e = float((df["weight"] * df["p"] * df["claim_cost"]).sum())
    return float((df["weight"] * df["y_gap"] * df["claim_cost"]).sum() / e) if e > 0 else float("nan")


def adverse_selection(shown: pd.DataFrame, n_boot: int = 400, seed: int = 0) -> dict:
    """Realized/expected among buyers over the same among everyone shown, with a weekly block bootstrap. 1.0 means buyers are
    no riskier than the model expects; above 1.0 they know something the price does not."""
    buyers = shown[shown["purchased"] == 1]
    point = ratio_of_claims(buyers) / ratio_of_claims(shown)
    weeks = shown["week"].unique()
    by_week = {w: g for w, g in shown.groupby("week")}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(weeks, len(weeks))
        s = pd.concat([by_week[w] for w in pick], ignore_index=True)
        b = s[s["purchased"] == 1]
        if len(b):
            boots.append(ratio_of_claims(b) / ratio_of_claims(s))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"ratio": float(point), "lo": float(lo), "hi": float(hi), "buyers": int(len(buyers))}


def analyse(df: pd.DataFrame, n_boot: int = 400) -> dict:
    """The pre-specified analysis. Columns: shown (bool), arm_price (multiplier of the model price, NaN in the control), message
    ('benefit' or 'outcome'), purchased (0/1), booked (0/1), p (model probability), claim_cost, y_gap (realized outcome, known for
    everyone from public flight data), weight, week, price (what was charged)."""
    shown = df[df["shown"]].copy()
    out = {"travellers_shown": int(len(shown)), "control": int((~df["shown"]).sum())}
    arms = {}
    for m, g in shown.groupby("arm_price"):
        k, n = float(g["purchased"].sum()), float(len(g))
        lo, hi = wilson(k, n)
        pay = float((g["weight"] * g["y_gap"] * g["claim_cost"])[g["purchased"] == 1].sum() / max(g["weight"][g["purchased"] == 1].sum(), 1e-9))
        price = float(g["price"][g["purchased"] == 1].mean()) if k else float("nan")
        arms[f"{m:g}"] = {"n": int(n), "attach": k / n, "lo": lo, "hi": hi, "mean_price_bought": price, "payout_per_policy": pay,
                          "margin_per_offer": (k / n) * (price - pay) if k else 0.0}
    out["by_price_arm"] = arms
    lp = np.log(shown["p"]) - np.log(shown["p"]).mean()
    lprice = np.log(shown["price"]) - np.log(shown["price"]).mean()
    msg = (shown["message"] == "outcome").astype(float)
    y = shown["purchased"].to_numpy()
    interval = lambda b, s: {"beta": float(b), "lo": float(b - 1.96 * s), "hi": float(b + 1.96 * s)}
    # theta beyond price: the price the traveller saw is held fixed
    f = logit_fit(np.column_stack([np.ones(len(shown)), lprice, lp, msg]), y)
    out["logit"] = {n: interval(b, s) for n, b, s in zip(("intercept", "log_price", "log_risk", "message_outcome"), f["beta"], f["se"])}
    # the net tilt of buyers toward risk at the prices charged (theta + price response), with the randomised arm as the price term
    g = logit_fit(np.column_stack([np.ones(len(shown)), np.log(shown["arm_price"]), lp, msg]), y)
    out["logit"]["log_risk_net"] = interval(g["beta"][2], g["se"][2])
    out["adverse_selection"] = adverse_selection(shown, n_boot=n_boot)
    offered = df[df["shown"]]
    ctrl = df[~df["shown"]]
    if len(ctrl):
        a, b = offered["booked"].mean(), ctrl["booked"].mean()
        se = np.sqrt(a * (1 - a) / len(offered) + b * (1 - b) / len(ctrl))
        out["guardrail_conversion"] = {"offer": float(a), "control": float(b), "diff": float(a - b), "lo": float(a - b - 1.96 * se), "hi": float(a - b + 1.96 * se)}
    return out


def decide(result: dict, min_attach: float, max_theta: float, max_adverse: float, min_conversion_diff: float, at_price: str = "1") -> dict:
    """The pre-registered go/no-go. Every threshold is an argument, because it comes from the agency's own costs
    (see economics.py), not from this project. Each test is conservative: it uses the interval end that is worse for the cover."""
    arm = result["by_price_arm"][at_price]
    tests = {"attach_at_model_price": arm["lo"] >= min_attach,
             "self_selection_theta_ok": result["logit"]["log_risk"]["hi"] <= max_theta,
             "adverse_selection_ok": result["adverse_selection"]["hi"] <= max_adverse,
             "booking_conversion_ok": result.get("guardrail_conversion", {"lo": 0.0})["lo"] >= min_conversion_diff}
    tests["go"] = all(tests.values())
    return tests


def oracle_adverse_selection(df: pd.DataFrame) -> float:
    """The answer the analysis should find, from the simulator's true probabilities instead of realized outcomes: expected
    true / model claims among buyers over the same among everyone shown."""
    shown = df[df["shown"]]
    buyers = shown[shown["purchased"] == 1]
    ratio = lambda d: float((d["weight"] * d["p_true"] * d["claim_cost"]).sum() / (d["weight"] * d["p"] * d["claim_cost"]).sum())
    return ratio(buyers) / ratio(shown)


def simulate(n: int, seed: int = 0, base_attach: float = 0.05, elasticity: float = -1.5, theta: float = 0.5, theta_hidden: float = 0.5,
             kappa: float = 0.3, message_effect: float = 0.15, conversion: float = 0.30, conversion_effect: float = 0.0, control_share: float = 0.10) -> pd.DataFrame:
    """Travellers with planted answers: attach falls with the price shown at `elasticity` (the price rises with risk, so the net
    tilt toward risk is theta + elasticity), rises with model risk beyond price at `theta`, with a hidden
    risk factor (spread kappa) at `theta_hidden` (so buyers realize exp(kappa x theta_hidden) times the expected claims), and
    rises by `message_effect` on the logit scale for the outcome-led wording."""
    rng = np.random.default_rng(seed)
    p = np.clip(np.exp(rng.normal(np.log(0.06), 0.8, n)), 0.003, 0.5)
    u = rng.normal(size=n)
    claim_cost = np.full(n, 250.0)
    shown = rng.uniform(size=n) >= control_share
    mult = rng.choice([0.8, 1.0, 1.25], n)
    msg = np.where(rng.uniform(size=n) < 0.5, "benefit", "outcome")
    price = mult * p * claim_cost / TARGET_LR
    lp = np.log(p) - np.log(p).mean()
    lprice = np.log(price) - np.log(price).mean()          # travellers react to the price they see, which rises with risk
    eta = np.log(base_attach / (1 - base_attach)) + elasticity * lprice + theta * lp + theta_hidden * u + message_effect * (msg == "outcome")
    purchased = (rng.uniform(size=n) < 1 / (1 + np.exp(-eta))) & shown
    p_true = np.minimum(0.95, p * np.exp(kappa * u - kappa ** 2 / 2))
    y = (rng.uniform(size=n) < p_true).astype(int)
    booked = (rng.uniform(size=n) < conversion + conversion_effect * shown).astype(int)
    return pd.DataFrame({"shown": shown, "arm_price": np.where(shown, mult, np.nan), "message": np.where(shown, msg, None), "purchased": purchased.astype(int),
                         "booked": booked, "p": p, "claim_cost": claim_cost, "y_gap": y, "p_true": p_true, "weight": 1.0, "week": rng.integers(0, 20, n).astype(str), "price": price})
