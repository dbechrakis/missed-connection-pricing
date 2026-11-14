"""v6: the gap cover with a seasonal price, on March to August 2027 (PREREGISTRATION_V6_FORWARD.md).

The price is the v3 procedure's (arm A of `mcp.backcast`: refitted at the block start on all months from January 2024) times a
frozen month multiplier (`models/v6_season.json`). The ratio of realized to expected claims is taken against the expected claims
without the multiplier, so the multiplier is a prediction of it.

    cd src
    MCP_VARIANT=v3 python -m mcp.v6 run spring2027       # refits and scores the block, prints counts only
    MCP_VARIANT=v3 python -m mcp.v6 read spring2027      # the single read of the window, refuses a second run
    MCP_VARIANT=v3 python -m mcp.v6 run summer2027 && MCP_VARIANT=v3 python -m mcp.v6 read summer2027
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from mcp import backcast as B
from mcp.connections import ROOT
from mcp.v3 import TARGET_LR, WTP_CAP

SEASON = ROOT / "models" / "v6_season.json"
WINDOWS = {"spring2027": ("2027-03", "2027-05"), "summer2027": ("2027-06", "2027-08")}
FIT_START = "2024-01"
FRAC = 0.20
SHARE_BAND = (0.20, 0.55)
SIGMA, RHO = 0.1585, 0.423
LOADING = 1.10                  # PREREGISTRATION_V6_FORWARD_ADDENDUM.md: a second series, reported without an expectation


def load_season() -> dict:
    return json.loads(SEASON.read_text(encoding="utf-8"))


def multiplier(ym: str, season: dict | None = None) -> float:
    return float((season or load_season())["multiplier"][ym[5:7]])


def band_half_width(n_months: int = 3, sigma: float = SIGMA, rho: float = RHO) -> float:
    """2 sigma over the square root of the effective number of months (months are related with lag-1 correlation rho)."""
    return 2 * sigma / np.sqrt(n_months * (1 - rho) / (1 + rho))


def monthly_table(rows: pd.DataFrame, season: dict) -> dict:
    """Per month of `rows` (the overnight-risk connections of one window with the model's probability): the realized/expected ratio
    against the model's own expected claims, the seasonal price's sold loss ratio and share sold."""
    out = {}
    for ym, g in rows.groupby("ym"):
        mult = multiplier(ym, season)
        w, p, c, y = g["weight"].to_numpy(float), g["p"].to_numpy(float), g["claim_cost"].to_numpy(float), g["y_gap"].to_numpy(float)
        claims, expected = float((w * y * c).sum()), float((w * p * c).sum())
        price = mult * p * c / TARGET_LR
        sold = price <= WTP_CAP * g["fare"].to_numpy(float)
        prem = float((w * price)[sold].sum())
        out[ym] = {"ratio": claims / expected, "z": float(np.log(claims / expected)), "multiplier": mult,
                   "sold_loss_ratio": float((w * y * c)[sold].sum() / prem) if prem else None, "share_sold": float(w[sold].sum() / w.sum()),
                   "claims": claims, "expected": expected}
    return out


def loaded_table(rows: pd.DataFrame, season: dict, loading: float = LOADING) -> dict:
    """Per month, the sold loss ratio and the share sold when the seasonal price is multiplied by a fixed loading and the cap is applied to
    the loaded price. Reported without an expectation (PREREGISTRATION_V6_FORWARD_ADDENDUM.md)."""
    out = {}
    for ym, g in rows.groupby("ym"):
        w, p, c, y = g["weight"].to_numpy(float), g["p"].to_numpy(float), g["claim_cost"].to_numpy(float), g["y_gap"].to_numpy(float)
        price = loading * multiplier(ym, season) * p * c / TARGET_LR
        sold = price <= WTP_CAP * g["fare"].to_numpy(float)
        prem = float((w * price)[sold].sum())
        out[ym] = {"sold_loss_ratio": float((w * y * c)[sold].sum() / prem) if prem else None, "share_sold": float(w[sold].sum() / w.sum())}
    return out


def analyse(rows: pd.DataFrame, window: str, season: dict | None = None) -> dict:
    season = season or load_season()
    m = monthly_table(rows, season)
    months = sorted(m)
    c = sum(m[k]["claims"] for k in months)
    adj = sum(m[k]["expected"] * m[k]["multiplier"] for k in months)
    err_s = float(np.mean([abs(m[k]["z"] - np.log(m[k]["multiplier"])) for k in months]))
    err_n = float(np.mean([abs(m[k]["z"]) for k in months]))
    return {"window": window, "months": m, "pooled_adjusted_ratio": c / adj, "pooled_unadjusted_ratio": c / sum(m[k]["expected"] for k in months),
            "mae_season": err_s, "mae_none": err_n, "band_half_width": float(band_half_width(len(months))),
            "months_above_100_sold": int(sum(1 for k in months if (m[k]["sold_loss_ratio"] or 0) > 1.0)),
            "share_sold_range": [min(m[k]["share_sold"] for k in months), max(m[k]["share_sold"] for k in months)]}


SCHEDULED_READS = ("holdout_v3_next.json", "holdout_v4_next.json", "v5_2_holdout.json")


def scheduled_reads_done(root=None) -> bool:
    """True when the scheduled reads of the sealed months (v3 and v4 on September to November 2026, v5.2 on its window) have written their
    results. The forward test refits on months from January 2024 through the block start, which include those months, so it waits for them."""
    base = root or ROOT
    return all((base / "results" / name).exists() for name in SCHEDULED_READS)


def require_scheduled_reads() -> None:
    if not scheduled_reads_done():
        raise SystemExit("the scheduled reads of v3, v4 and v5.2 have not all written their results (" + ", ".join(SCHEDULED_READS) + "): the forward test must not touch the months they read first")


def run(window: str) -> None:
    from mcp.variant import VARIANT
    assert VARIANT == "v3", "run with MCP_VARIANT=v3"
    require_scheduled_reads()
    out = B.DATA / "v6_forward" / window
    B.run("A", blocks=[WINDOWS[window]], fit_start=FIT_START, frac=FRAC, out=out)


def read(window: str) -> dict:
    result = ROOT / "results" / f"v6_forward_{window}.json"
    if result.exists():
        raise SystemExit(f"{result.name} exists: each window is read once (PREREGISTRATION_V6_FORWARD.md section 6)")
    require_scheduled_reads()
    rows_dir = B.DATA / "v6_forward" / window / "rows_A"
    rows = pd.concat([pd.read_parquet(f) for f in sorted(rows_dir.glob("*.parquet"))], ignore_index=True)
    res = analyse(rows, window)
    res["loaded"] = {"loading": LOADING, "months": loaded_table(rows, load_season())}
    result.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return res


# ---- the exploratory analysis behind the multipliers (seen data, VALIDATION.md 7G) ----------------------------------------

def monthly_log_ratio(weeks: pd.DataFrame) -> pd.Series:
    """Log of realized over expected claims by month, all overnight-risk connections, from weekly rows (ym, claims, expected)."""
    g = weeks.groupby("ym")[["claims", "expected"]].sum()
    return np.log(g["claims"] / g["expected"])


def fit_season(z: pd.Series, kappa: float = 1.0) -> dict:
    """Grand mean and per-calendar-month shrunk deviations of a monthly log ratio series (index 'YYYY-MM')."""
    mu = float(z.mean())
    m = z.index.str[5:7].astype(int)
    g = pd.DataFrame({"z": z.to_numpy(), "m": m}).groupby("m")["z"].agg(["sum", "count"])
    eff = (g["sum"] - g["count"] * mu) / (g["count"] + kappa)
    return {"mu": mu, "effects": {f"{k:02d}": float(eff.get(k, 0.0)) for k in range(1, 13)}, "counts": {f"{k:02d}": int(g["count"].get(k, 0)) for k in range(1, 13)}}


def leave_one_year_out(z: pd.Series, kappa: float = 1.0) -> dict:
    """Each year's months predicted from a season fitted on the other years. Returns the mean absolute error of the log ratio with the
    season, with a constant level (the other years' mean) and with none (level 1), and the residuals."""
    years = z.index.str[:4]
    res, err_s, err_c, err_n = {}, [], [], []
    for y in sorted(set(years)):
        fit = fit_season(z[years != y], kappa)
        for ym, v in z[years == y].items():
            pred = fit["mu"] + fit["effects"][ym[5:7]]
            res[ym] = float(v - pred)
            err_s.append(abs(v - pred))
            err_c.append(abs(v - fit["mu"]))
            err_n.append(abs(v))
    r = pd.Series(res).sort_index()
    nxt = lambda m: f"{(int(m[:4]) * 12 + int(m[5:])) // 12}-{(int(m[:4]) * 12 + int(m[5:])) % 12 + 1:02d}"
    pairs = [(r[m], r[nxt(m)]) for m in r.index if nxt(m) in r.index]
    rho = float(np.corrcoef(*zip(*pairs))[0, 1])
    return {"mae_season": float(np.mean(err_s)), "mae_constant_level": float(np.mean(err_c)), "mae_none": float(np.mean(err_n)), "months": int(len(r)),
            "residual_sd": float(r.std(ddof=1)), "residual_lag1_autocorrelation": rho}


def three_month_blocks(weeks: pd.DataFrame, first_month: str = "06") -> pd.DataFrame:
    """Realized/expected on all connections, and the sold loss ratio at the existing price, for every run of three consecutive
    observed months that starts in `first_month` (June to August by default)."""
    all_m = weeks.groupby("ym")[["claims", "expected", "premium"]].sum()
    sold_m = weeks[weeks["sold"]].groupby("ym")[["claims", "premium"]].sum()
    nxt = lambda m, k: f"{(int(m[:4]) * 12 + int(m[5:]) - 1 + k) // 12}-{(int(m[:4]) * 12 + int(m[5:]) - 1 + k) % 12 + 1:02d}"
    rows = []
    for m in all_m.index:
        blk = [nxt(m, i) for i in range(3)]
        if m[5:7] == first_month and all(b in all_m.index for b in blk) and all(b in sold_m.index for b in blk):
            a, s = all_m.loc[blk], sold_m.loc[blk]
            rows.append({"start": m, "ratio_all": float(a["claims"].sum() / a["expected"].sum()), "sold_loss_ratio": float(s["claims"].sum() / s["premium"].sum())})
    return pd.DataFrame(rows)


def season_report() -> dict:
    weeks = pd.read_csv(ROOT / "results" / "risk_weeks_2019_2026.csv")
    z = monthly_log_ratio(weeks)
    fit = fit_season(z)
    out = {"status": "exploratory, on the 70 months already seen (VALIDATION.md 7G)", "months": int(len(z)), "calendar_month_mean_log_ratio": {},
           "leave_one_year_out": {str(k): leave_one_year_out(z, k) for k in (0.0, 1.0, 2.0, 4.0)}, "fit": fit,
           "summers": three_month_blocks(weeks).round(6).to_dict("records")}
    for m in range(1, 13):
        sel = z[z.index.str[5:7].astype(int) == m]
        out["calendar_month_mean_log_ratio"][f"{m:02d}"] = {"mean": float(sel.mean()), "n": int(len(sel))}
    (ROOT / "results" / "v6_season_dev.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    if sys.argv[1] == "season":
        season_report()
    else:
        {"run": run, "read": read}[sys.argv[1]](sys.argv[2])
