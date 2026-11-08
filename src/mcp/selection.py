"""Adverse selection on information the price does not have (exploratory; the missing half of the θ story).

The backtest's θ curve lets buyers select on the *model's own* probability. A calibrated model cannot lose
to that by construction, so that curve shows the machinery works, not that tiering is safe. Real adverse
selection is buyers knowing something the pricer does not: their inbound is on a small aircraft out of a
storm city, they have heard of a delay, they have hidden slack in their plans.

Model of that. Each connection has a *hidden* risk factor m = exp(kappa x u - kappa^2 / 2), u ~ N(0, 1), so
E[m] = 1 and the model is right on average. The true miss probability is p x m. Buyers weight their purchase
by their true risk to the power theta. The price is set from p only. Then, with b = (p m)^theta,

    realized / target (tiered) = sum(w b p m c) / sum(w b p c)  =  E[m^(theta+1)] / E[m^theta]  =  exp(theta x kappa^2)

independent of p. A flat price also suffers from selection on p itself and is worse by about exp(theta x sigma^2),
sigma being the spread of log P(miss) across connections.

The closed form is exact for an unlimited sample and no cap on probabilities. Two things pull a finite simulation
below it: heavy tails (E[m^3] is dominated by rare large draws) and the cap p x m <= 1; both matter only for
large kappa x theta, and the closed form then overstates exposure.

kappa cannot be measured from public data: it is how much risk buyers can see that the model cannot.
This module therefore reports the exposure as a table over kappa, never at one chosen value, and gives
the empirical floor on kappa that the holdout implies (how much the model's own errors vary by month).

Run:  python -m mcp.selection      (from src/; development data only, writes results/selection_private_info.json)
"""
from __future__ import annotations

import json

import numpy as np

from mcp.connections import ROOT

RESULTS = ROOT / "results" / "selection_private_info.json"
KAPPAS = (0.1, 0.25, 0.5, 1.0)
THETAS = (0.5, 1.0, 2.0)


def closed_form(kappa: float, theta: float) -> float:
    """Tiered realized/target when buyers select on hidden risk: exp(theta x kappa^2)."""
    return float(np.exp(theta * kappa**2))


def simulate(p, w, cost, kappa: float, thetas=THETAS, seed: int = 0) -> dict:
    """Monte Carlo on a real set of connections (p = model probability, w = weights, cost = claim cost).

    Returns realized/target for the tiered price (priced from p) and for a flat price, both relative
    to what they would earn if nobody selected. The flat price is the average expected cost over all connections.
    """
    p, w, cost = (np.asarray(a, float) for a in (p, w, cost))
    rng = np.random.default_rng(seed)
    m = np.exp(kappa * rng.standard_normal(p.size) - kappa**2 / 2)
    p_true = np.minimum(p * m, 1.0)
    out = {}
    base_flat = np.sum(w * p * cost) / np.sum(w)                       # the flat price a no-selection actuary sets
    for th in thetas:
        b = w * p_true**th
        claims = np.sum(b * p_true * cost)
        out[th] = {"tiered": float(claims / np.sum(b * p * cost)),
                   "flat": float(claims / (base_flat * np.sum(b)))}
    return out


def empirical_kappa_floor() -> dict:
    """How much the model's own error varies in the clean 2026 holdout, by month and by hub.
    It is only a floor on the hidden dispersion: it counts what is visible after the fact in coarse groups."""
    h = json.loads((ROOT / "results" / "holdout.json").read_text())
    months = [h["by_month"][k] for k in sorted(h["by_month"], key=int)]
    by_month = np.log([m["observed"] / m["pred_v1_iso"] for m in months])
    by_hub = np.log([v["v1_iso"]["ratio"] for v in h["by_hub"].values()])
    return {"sd_log_ratio_by_month": float(by_month.std(ddof=1)), "sd_log_ratio_by_hub": float(by_hub.std(ddof=1))}


def figure(res: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.alpha": 0.25, "figure.dpi": 130, "font.size": 10})
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    th = [float(t) for t in res["table"]["0.5"]]
    style = {"0.25": "#56B4E9", "0.5": "#0072B2"}
    for k, c in style.items():
        ax.plot(th, [r["tiered"] for r in res["table"][k].values()], marker="o", lw=2, color=c,
                label=f"priced per connection, hidden risk spread {k}")
        ax.plot(th, [r["flat"] for r in res["table"][k].values()], marker="s", lw=2, ls="--", color="#D55E00" if k == "0.5" else "#E69F00",
                label=f"one flat price, hidden risk spread {k}")
    ax.axhline(1, color="k", lw=1, ls=":")
    ax.set(xlabel="How strongly buyers favour the connections they know are riskier (θ)", ylabel="Realized ÷ target loss ratio",
           title="Selection on information the price does not have (simulated)", xticks=th)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(ROOT / "docs" / "figures" / "selection_private_info.png")
    plt.close(fig)


def main() -> None:
    import joblib
    import pandas as pd

    from mcp.features import OUT
    from mcp.pricing import MODEL, load_config, load_guards, score

    cfg, guards = load_config(), load_guards()
    df = pd.read_parquet(OUT / "PRICING_TRAIN.parquet")
    p = np.maximum(score(df, joblib.load(MODEL)), guards["min_p_miss"])
    cost = cfg["rebooking_cost"] + cfg["overnight_cost"] * df["overnight"].to_numpy()
    w = df["weight"].to_numpy()
    sigma = float(np.sqrt(np.cov(np.log(p), aweights=w)))
    res = {"sigma_log_p": sigma, "empirical_kappa_floor": empirical_kappa_floor(), "table": {}}
    for k in KAPPAS:
        sim = simulate(p, w, cost, k)
        res["table"][str(k)] = {str(th): {"closed_form_tiered": closed_form(k, th), "tiered": sim[th]["tiered"], "flat": sim[th]["flat"]}
                                for th in THETAS}
    RESULTS.write_text(json.dumps(res, indent=2))
    figure(res)
    print("sd of log P(miss) across connections:", round(sigma, 3), "| model error spread (months, hubs):",
          {k: round(v, 3) for k, v in res["empirical_kappa_floor"].items()})
    print(f"{'kappa':>6} {'theta':>6} {'tiered (sim)':>13} {'exp(theta*kappa^2)':>19} {'flat (sim)':>11}")
    for k, rows in res["table"].items():
        for th, r in rows.items():
            print(f"{k:>6} {th:>6} {r['tiered']:13.3f} {r['closed_form_tiered']:19.3f} {r['flat']:11.3f}")


if __name__ == "__main__":
    main()
