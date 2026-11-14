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


# ---- the run on the 2019 to 2026 weekly record -----------------------------------------------------------------------

EXPENSES, ATTACHMENTS, COCS = (0.10, 0.25, 0.35), (None, 1.0, 1.2), (0.06, 0.10, 0.15)


def weekly_record(weeks, sold: bool) -> dict:
    """Weekly claims and expected claims (all hubs together) from rows with columns week, hub, sold, claims, expected."""
    d = weeks[weeks["sold"]] if sold else weeks
    g = d.groupby("week")[["claims", "expected"]].sum().sort_index()
    return {"week": np.array(g.index, dtype="datetime64[D]"), "claims": g["claims"].to_numpy(float), "expected": g["expected"].to_numpy(float)}


def run(weeks, current_price_per_policy: float, n_sim: int = 2000) -> dict:
    """The technical price on a weekly record: a grid of expense ratios, attachments and costs of capital, the tail of the annual loss ratio at
    the existing price, and the diversification between hubs. `weeks` has the columns week, hub, sold, claims, expected."""
    out = {}
    for view, sold in (("all_overnight_risk", False), ("sold_within_cap", True)):
        rec = weekly_record(weeks, sold)
        pooled_lr0 = float(rec["claims"].sum() / (rec["expected"].sum() * CURRENT_PI))
        grid = {}
        for e in EXPENSES:
            for att in ATTACHMENTS:
                for coc in COCS:
                    s = solve(rec["claims"], rec["expected"], rec["week"], attach=att, coc=coc, expense=e, n_sim=n_sim)
                    key = f"expense{int(e * 100)}_attach{'none' if att is None else int(att * 100)}_coc{int(coc * 100)}"
                    grid[key] = {"loading_vs_current": s["loading_vs_current"], "pi": s["pi"], **{k: v for k, v in s["terms"].items() if k in ("retained_loss_ratio", "stop_loss_cost", "capital_margin")}}
        tails = []
        for seed in range(10):
            sim = risk.season_block_bootstrap_years(rec["claims"], rec["expected"] * CURRENT_PI, rec["week"], n_sim=n_sim, block=4, seed=seed)["annual_loss_ratio"]
            tails.append({"var90": float(np.percentile(sim, 90)), "var95": float(np.percentile(sim, 95)), "mean": float(sim.mean())})
        by_hub = weeks[weeks["sold"]] if sold else weeks
        piv = by_hub.groupby(["week", "hub"])[["claims", "expected"]].sum().reset_index()
        ratio = (piv["claims"] / piv["expected"]).groupby([piv["week"], piv["hub"]]).first().unstack("hub").dropna()
        weekly_lr = rec["claims"] / (rec["expected"] * CURRENT_PI)
        out[view] = {"weeks": int(len(rec["week"])), "pooled_loss_ratio_at_current_price": pooled_lr0, "grid": grid,
                     "annual_loss_ratio_at_current_price": {"var90_mean": float(np.mean([t["var90"] for t in tails])), "var90_range": [min(t["var90"] for t in tails), max(t["var90"] for t in tails)],
                                                            "var95_mean": float(np.mean([t["var95"] for t in tails])), "var95_range": [min(t["var95"] for t in tails), max(t["var95"] for t in tails)],
                                                            "mean": float(np.mean([t["mean"] for t in tails]))},
                     "weekly_loss_ratio": {"weeks_above_100": int((weekly_lr > 1).sum()), "worst": float(weekly_lr.max())},
                     "stop_loss_at_current_price": {f"attach_{a:.0%}": risk.stop_loss_cost(weekly_lr, a) for a in (0.9, 1.0, 1.2)},
                     "diversification": diversification({h: ratio[h].to_numpy() for h in ratio.columns}),
                     "economics": economics(pooled_lr0, current_price_per_policy)}
    return out


def economics(pooled_lr_at_current: float, price_per_policy: float) -> dict:
    """Margin per policy sold, per the loading that would be needed, under the expense ratios of the grid, using the sold book's
    realized loss ratio at the existing price and its average premium per policy. A loading raises premium and leaves claims where
    they are (the connections that pass the cap are held fixed, which flatters the price: fewer would pass)."""
    out = {}
    claims = pooled_lr_at_current * price_per_policy
    for lam in (1.0, 1.16, 1.25, 1.5):
        prem = lam * price_per_policy
        out[f"loading_{lam:.2f}"] = {f"expense{int(e * 100)}": prem - claims - e * prem for e in EXPENSES}
    return out


# ---- would more hubs buy safety? (optional item 3 of the plan, answered by arithmetic) ----------------------------------

def more_hubs_projection(mean_correlation: float, n_now: int = 5, candidates=(5, 10, 15, 30)) -> dict:
    """The weekly spread of an equally spread book of n hubs relative to one hub, if every pair of hubs has the same correlation and
    the same spread: sqrt((1 + (n - 1) rho) / n). It falls toward sqrt(rho) and cannot go below it."""
    ratio = lambda n: float(np.sqrt((1 + (n - 1) * mean_correlation) / n))
    return {"mean_correlation": mean_correlation, "floor": float(np.sqrt(mean_correlation)),
            "ratio_by_hubs": {str(n): ratio(n) for n in candidates},
            "reduction_vs_now": {str(n): 1 - ratio(n) / ratio(n_now) for n in candidates if n != n_now}}


def yearly_loss_ratios(weeks, min_months: int = 10) -> dict:
    """The sold and all-connections loss ratio of each calendar year that has at least `min_months` observed months, at the existing
    price. A direct look at what the block bootstrap cannot carry: a level that differs from one year to the next."""
    w = weeks.assign(year=weeks["ym"].str[:4])
    months = w.groupby("year")["ym"].nunique()
    out = {}
    for y in months.index[months >= min_months]:
        g = w[w["year"] == y]
        s = g[g["sold"]]
        out[y] = {"months": int(months[y]), "all": float(g["claims"].sum() / g["premium"].sum()), "sold": float(s["claims"].sum() / s["premium"].sum())}
    sold = np.array([v["sold"] for v in out.values()])
    return {"years": out, "sold_mean": float(sold.mean()), "sold_sd": float(sold.std(ddof=1)) if len(sold) > 1 else None}


# ---- the same questions under each backcast arm (exploratory, VALIDATION.md 7J) -------------------------------------------

PANDEMIC = ("2020-03", "2021-06")
SUMMER = ("06", "07", "08")
ARMS = ("A", "B", "C", "D")


def without_pandemic(weeks):
    return weeks[~((weeks["ym"] >= PANDEMIC[0]) & (weeks["ym"] <= PANDEMIC[1]))]


def arm_record(arm_weeks, development_weeks):
    """The backcast weeks of one arm outside the pandemic months followed by the development weeks, the record of 7C under that arm."""
    import pandas as pd
    return pd.concat([without_pandemic(arm_weeks), development_weeks], ignore_index=True)


def reach_by_year(arm_weeks) -> dict:
    """Share of the weight of all overnight-risk connections that passes the cap, by calendar year, outside the pandemic months."""
    w = without_pandemic(arm_weeks)
    w = w.assign(year=w["ym"].str[:4])
    sold = w[w["sold"]].groupby("year")["w"].sum()
    total = w.groupby("year")["w"].sum()
    return {y: float(sold[y] / total[y]) for y in total.index}


def seasonal_sold(record, multiplier: dict) -> dict:
    """The sold loss ratio had each month's premium been multiplied by its seasonal multiplier, the cap not applied again: pooled, the number of
    months above 100% and the same for June to August."""
    s = record[record["sold"]].assign(m=lambda d: d["ym"].str[5:7])
    s = s.assign(prem2=s["premium"] * s["m"].map(multiplier))
    by_month = s.groupby("ym")[["claims", "premium", "prem2"]].sum()
    summer = by_month[by_month.index.str[5:7].isin(SUMMER)]
    return {"pooled_loss_ratio": float(by_month["claims"].sum() / by_month["prem2"].sum()), "months": int(len(by_month)),
            "months_above_100": int((by_month["claims"] / by_month["prem2"] > 1).sum()),
            "months_above_100_existing_price": int((by_month["claims"] / by_month["premium"] > 1).sum()),
            "summer_months": int(len(summer)), "summer_above_100": int((summer["claims"] / summer["prem2"] > 1).sum()),
            "summer_above_100_existing_price": int((summer["claims"] / summer["premium"] > 1).sum())}


def arm_summary_record(record, multiplier: dict) -> dict:
    from mcp import v6
    out = {}
    for view, sold in (("all", False), ("sold", True)):
        rec = weekly_record(record, sold)
        lr = rec["claims"] / (rec["expected"] * CURRENT_PI)
        out[view] = {"weeks": int(len(lr)), "pooled_loss_ratio": float(rec["claims"].sum() / (rec["expected"].sum() * CURRENT_PI)),
                     "weeks_above_100": int((lr > 1).sum()), "worst_week": float(lr.max()),
                     "loading_expense35": solve(rec["claims"], rec["expected"], rec["week"], expense=0.35)["loading_vs_current"],
                     "loading_expense35_attach100": solve(rec["claims"], rec["expected"], rec["week"], attach=1.0, expense=0.35)["loading_vs_current"]}
    z = v6.monthly_log_ratio(record)
    fit = v6.fit_season(z)
    loyo = v6.leave_one_year_out(z)
    out["season"] = {"multiplier": {k: float(np.exp(fit["mu"] + fit["effects"][k])) for k in fit["effects"]},
                     "mae_season": loyo["mae_season"], "mae_none": loyo["mae_none"], "months": loyo["months"]}
    out["at_frozen_multipliers_as_sold"] = seasonal_sold(record, multiplier)
    return out


def arm_sensitivity(root=None) -> dict:
    """Writes results/arm_sensitivity.json from the committed weekly files of the four backcast arms and the development weeks."""
    import json
    import pandas as pd
    from pathlib import Path
    root = Path(root) if root else Path(__file__).resolve().parents[2]
    record = pd.read_csv(root / "results" / "risk_weeks_2019_2026.csv")
    development = record[record["source"] != "backcast_2019_2023"]
    development = development[[c for c in development.columns if c != "source"]]
    multiplier = json.loads((root / "models" / "v6_season.json").read_text(encoding="utf-8"))["multiplier"]
    out = {"status": "exploratory, after the single read of the backcast (VALIDATION.md 7J)"}
    for arm in ARMS:
        weeks = pd.read_csv(root / "results" / f"backcast_weeks_{arm}.csv")
        out[arm] = {**arm_summary_record(arm_record(weeks, development), multiplier), "share_sold_by_year": reach_by_year(weeks)}
    (root / "results" / "arm_sensitivity.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    import sys
    if sys.argv[1] == "arms":
        arm_sensitivity()
