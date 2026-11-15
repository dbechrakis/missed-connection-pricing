"""A season by hub (VALIDATION.md 7O, exploratory, on months already seen). Numpy only.

The panel is the log ratio of realized to expected claims by hub and month. Three numpy candidates and the scorer for the hierarchical
candidate of `mcp.hub_season_fit` live here, so that the main test suite never imports PyMC.

    cd src
    python -m mcp.hub_season dev      # the three numpy candidates, written to results/hub_season_dev.json
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from mcp import risk
from mcp.capital import without_pandemic
from mcp.connections import ROOT
from mcp.v6 import fit_season

WEEKS = ROOT / "results" / "risk_weeks_2019_2026.csv"
DEV = ROOT / "results" / "hub_season_dev.json"
FITS = ROOT / "results" / "hub_season_fits"
MIN_MONTHS = 10
MIN_GAIN = 0.005
CANDIDATES = ("none", "pooled", "by_hub", "hier")
FROZEN = ROOT / "models" / "v7_hub_season.json"
FORWARD_MONTHS = ("03", "04", "05", "06", "07", "08")


def hub_month_panel(weeks: pd.DataFrame) -> pd.DataFrame:
    """One row per hub and month outside the pandemic: claims and expected summed over weeks and over both values of `sold`, and
    z = log(claims / expected)."""
    g = without_pandemic(weeks).groupby(["hub", "ym"])[["claims", "expected"]].sum().reset_index()
    g["z"] = np.log(g["claims"] / g["expected"])
    g["year"] = g["ym"].str[:4].astype(int)
    g["month"] = g["ym"].str[5:7]
    return g.sort_values(["hub", "ym"]).reset_index(drop=True)


def all_hub_series(panel: pd.DataFrame) -> pd.Series:
    """The monthly log ratio over all hubs, the series the frozen calendar was fitted on."""
    g = panel.groupby("ym")[["claims", "expected"]].sum()
    return np.log(g["claims"] / g["expected"])


def folds(panel: pd.DataFrame, min_months: int = MIN_MONTHS) -> list[int]:
    months = panel.groupby("year")["ym"].nunique()
    return [int(y) for y in months.index[months >= min_months]]


def _spread(residuals: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(residuals))))


def candidate_none(train: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """z = 0. The spread is the root mean square of z in the fitting years."""
    sd = _spread(train["z"].to_numpy())
    return targets[["hub", "ym"]].assign(mean=0.0, sd=sd)


def candidate_pooled(train: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """The frozen rule: one calendar for all hubs, deviations shrunk by n over n plus 1, refitted on the other years. The spread is the
    root mean square residual of the hub panel in the fitting years."""
    season = fit_season(all_hub_series(train))
    level = lambda month: season["mu"] + season["effects"][month]  # noqa: E731
    fitted = train["month"].map(level).to_numpy(float)
    sd = _spread(train["z"].to_numpy() - fitted)
    mean = targets["ym"].str[5:7].map(level).to_numpy(float)
    return targets[["hub", "ym"]].assign(mean=mean, sd=sd)


def candidate_by_hub(train: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """Each hub's own twelve monthly means, no pooling across hubs, the same shrinkage within the hub."""
    fits = {hub: fit_season(g.set_index("ym")["z"]) for hub, g in train.groupby("hub")}
    level = lambda hub, month: fits[hub]["mu"] + fits[hub]["effects"][month]  # noqa: E731
    fitted = np.array([level(h, m) for h, m in zip(train["hub"], train["month"], strict=True)])
    sd = _spread(train["z"].to_numpy() - fitted)
    mean = np.array([level(h, ym[5:7]) for h, ym in zip(targets["hub"], targets["ym"], strict=True)])
    return targets[["hub", "ym"]].assign(mean=mean, sd=sd)


NUMPY_CANDIDATES = {"none": candidate_none, "pooled": candidate_pooled, "by_hub": candidate_by_hub}


def leave_one_year_out_panel(panel: pd.DataFrame, candidate, min_months: int = MIN_MONTHS) -> pd.DataFrame:
    """For each fold year, the candidate's prediction of that year's hub-months from the other years. The candidate receives only the
    hub and month of the targets, never their values."""
    out = []
    for year in folds(panel, min_months):
        train = panel[panel["year"] != year]
        targets = panel.loc[panel["year"] == year, ["hub", "ym"]]
        pred = candidate(train, targets)
        out.append(pred.assign(year=year))
    return pd.concat(out, ignore_index=True)


def score(predictions: pd.DataFrame, panel: pd.DataFrame, level: float = 0.90) -> dict:
    """Mean absolute error, ranked probability score and coverage of the central interval, pooled and per fold. Log-ratio units."""
    merged = predictions.merge(panel[["hub", "ym", "z"]], on=["hub", "ym"], how="left")
    if merged["z"].isna().any():
        raise ValueError("a prediction has no observed month")

    def one(g: pd.DataFrame) -> dict:
        lo, hi = risk.normal_interval(g["mean"], g["sd"], level)
        return {"n": int(len(g)), "mae": float(np.mean(np.abs(g["z"] - g["mean"]))),
                "crps": float(np.mean(risk.crps_normal(g["z"], g["mean"], g["sd"]))), "coverage": risk.interval_coverage(g["z"], lo, hi)}

    per_fold = {str(y): one(g) for y, g in merged.groupby("year")}
    return {"pooled": one(merged), "per_fold": per_fold}


def earns_its_place(scores_a: dict, scores_b: dict, min_gain: float = MIN_GAIN) -> dict:
    """A earns its place over B if its ranked probability score is lower in at least all folds but one and the mean gain is above
    `min_gain`. Each argument is the `per_fold` part of `score`."""
    keys = sorted(scores_a)
    if keys != sorted(scores_b):
        raise ValueError("the two score tables cover different folds")
    gains = [scores_b[k]["crps"] - scores_a[k]["crps"] for k in keys]
    wins = int(sum(g > 0 for g in gains))
    mean_gain = float(np.mean(gains))
    return {"folds": len(keys), "folds_won": wins, "mean_gain": mean_gain, "earns_its_place": bool(wins >= len(keys) - 1 and mean_gain > min_gain)}


def load_hier(fold: int, directory=None) -> dict:
    return json.loads(((directory or FITS) / f"{fold}.json").read_text(encoding="utf-8"))


def candidate_hier_from_fits(directory=None):
    """The hierarchical candidate, read from the posterior summaries of `mcp.hub_season_fit`. Each fit is for one held-out year and holds the
    mean and standard deviation of the predictive distribution of z for each hub and calendar month."""
    def candidate(train: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
        year = int(targets["ym"].iloc[0][:4])
        fit = load_hier(year, directory)
        mean = np.array([fit["predictive"][h][ym[5:7]]["mean"] for h, ym in zip(targets["hub"], targets["ym"], strict=True)])
        sd = np.array([fit["predictive"][h][ym[5:7]]["sd"] for h, ym in zip(targets["hub"], targets["ym"], strict=True)])
        return targets[["hub", "ym"]].assign(mean=mean, sd=sd)
    return candidate


def departures(fit: dict, level: float = 0.9) -> list[dict]:
    """Hub-months whose multiplier differs from the shared calendar with posterior probability above `level`, in either direction."""
    out = []
    for hub, months in fit["prob_d_positive"].items():
        for month, p in months.items():
            if p > level or p < 1 - level:
                out.append({"hub": hub, "month": month, "prob_above_shared": p, "multiplier": fit["multipliers"][hub][month]["mean"]})
    return out


def freeze_summary(fit: dict) -> dict:
    """The frozen forward predictor: for each hub and month of March to August, the predictive mean and standard deviation of z, and the
    posterior probability that the hub's multiplier is above the frozen pooled multiplier of `models/v6_season.json`."""
    hubs = sorted(fit["predictive"])
    return {"model": "hierarchical season by hub, VALIDATION.md 7O", "fitted_on": "2019-01 to 2026-08 outside the pandemic months, 350 hub-months",
            "seed": fit["seed"], "target_accept": fit["target_accept"], "tau_d_prior_scale": fit["tau_d_prior_scale"],
            "input_sha256": fit["input_sha256"], "versions": fit["versions"], "diagnostics": fit["diagnostics"], "scales": fit["scales"],
            "predictive": {h: {m: fit["predictive"][h][m] for m in FORWARD_MONTHS} for h in hubs},
            "prob_above_pooled": {h: {m: fit["prob_above_pooled"][h][m] for m in FORWARD_MONTHS} for h in hubs},
            "rule": "predictive of z = log(realized / expected claims) for a hub and a calendar month of a new year, including a fresh shared monthly shock and a fresh residual"}


def freeze() -> str:
    if FROZEN.exists():
        raise SystemExit(f"{FROZEN.name} exists and is frozen")
    FROZEN.write_text(json.dumps(freeze_summary(load_hier("full")), indent=1) + "\n", encoding="utf-8", newline="\n")
    import hashlib
    return hashlib.sha256(FROZEN.read_bytes()).hexdigest()


def dev(weeks: pd.DataFrame | None = None, with_hier: bool = False) -> dict:
    weeks = pd.read_csv(WEEKS) if weeks is None else weeks
    panel = hub_month_panel(weeks)
    candidates = dict(NUMPY_CANDIDATES)
    if with_hier:
        candidates["hier"] = candidate_hier_from_fits()
    scores = {name: score(leave_one_year_out_panel(panel, fn), panel) for name, fn in candidates.items()}
    out = {"data": "results/risk_weeks_2019_2026.csv, outside the pandemic months", "hubs": sorted(panel["hub"].unique()),
           "months": int(panel["ym"].nunique()), "hub_months": int(len(panel)), "folds": folds(panel), "n_folds": len(folds(panel)),
           "scores": scores,
           "verdicts": {"by_hub_vs_pooled": earns_its_place({k: v for k, v in scores["by_hub"]["per_fold"].items()}, scores["pooled"]["per_fold"])}}
    if with_hier:
        out["verdicts"]["hier_vs_pooled"] = earns_its_place(scores["hier"]["per_fold"], scores["pooled"]["per_fold"])
        full = load_hier("full")
        out["full_record"] = {"tau_d": full["scales"]["tau_d"], "scales": full["scales"], "diagnostics": full["diagnostics"],
                              "departures_above_0_9": departures(full), "n_departures_above_0_9": len(departures(full))}
    return out


def hub_month_table(rows: pd.DataFrame) -> pd.DataFrame:
    """Per hub and month of the rows of one v6 window, the realized and expected claims of `mcp.v6.monthly_table` and z = log of their ratio."""
    w, p, c, y = (rows[k].to_numpy(float) for k in ("weight", "p", "claim_cost", "y_gap"))
    frame = pd.DataFrame({"hub": rows["hub"].to_numpy(), "ym": rows["ym"].to_numpy(), "claims": w * y * c, "expected": w * p * c})
    g = frame.groupby(["hub", "ym"])[["claims", "expected"]].sum().reset_index()
    g["z"] = np.log(g["claims"] / g["expected"])
    return g


def predict_window(table: pd.DataFrame, season: dict, frozen: dict, pooled_sd: float) -> list[dict]:
    """The two frozen predictors for each hub-month of a window: `pooled` (the frozen multipliers, the same for every hub) and `hier`."""
    out = []
    for r in table.itertuples():
        month = r.ym[5:7]
        hier = frozen["predictive"][r.hub][month]
        out.append({"hub": r.hub, "ym": r.ym, "z": float(r.z), "pooled_mean": float(np.log(season["multiplier"][month])), "pooled_sd": pooled_sd,
                    "hier_mean": hier["mean"], "hier_sd": hier["sd"]})
    return out


def read(window: str) -> dict:
    """The single read of the hub-level forward test (PREREGISTRATION_V7_HUB_SEASON.md). It runs only after `mcp.v6 read` has written the result of
    the same window, and refuses a second run."""
    from mcp import v6
    result = ROOT / "results" / f"v7_hub_season_{window}.json"
    if result.exists():
        raise SystemExit(f"{result.name} exists: each window is read once (PREREGISTRATION_V7_HUB_SEASON_ADDENDUM.md section 1)")
    if not (ROOT / "results" / f"v6_forward_{window}.json").exists():
        raise SystemExit(f"results/v6_forward_{window}.json does not exist: the hub-level test never reads a window before v6 has (PREREGISTRATION_V7_HUB_SEASON.md section 5)")
    v6.require_scheduled_reads()
    from mcp import backcast as B
    rows_dir = B.DATA / "v6_forward" / window / "rows_A"
    rows = pd.concat([pd.read_parquet(f) for f in sorted(rows_dir.glob("*.parquet"))], ignore_index=True)
    panel = hub_month_panel(pd.read_csv(WEEKS))
    pooled_sd = float(candidate_pooled(panel, panel[["hub", "ym"]])["sd"].iloc[0])
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    out = {"window": window, "rows": predict_window(hub_month_table(rows), v6.load_season(), frozen, pooled_sd)}
    result.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if cmd == "freeze":
        print(freeze())
        return
    if cmd in ("read",) and len(sys.argv) > 2 and sys.argv[2] in ("spring2027", "summer2027"):
        read(sys.argv[2])
        return
    if cmd != "dev":
        raise SystemExit("usage: python -m mcp.hub_season dev | freeze | read spring2027 | read summer2027")
    result = dev(with_hier=FITS.exists() and any(FITS.glob("[0-9]*.json")))
    DEV.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result["verdicts"], indent=1))


if __name__ == "__main__":
    main()
