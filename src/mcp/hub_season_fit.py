"""The hierarchical model of a season by hub (VALIDATION.md 7O). This module imports PyMC and is not part of the main test suite.

Fit it in its own environment (`requirements-bayes.txt`, `.venv-bayes`). It writes posterior summaries as JSON. The numpy scorer in
`mcp.hub_season` reads them.

    cd src
    ../.venv-bayes/bin/python -m mcp.hub_season_fit prior       # prior predictive check, before any fit on data
    ../.venv-bayes/bin/python -m mcp.hub_season_fit dev         # every fold and the full record, written to results/hub_season_fits/
    ../.venv-bayes/bin/python -m mcp.hub_season_fit sensitivity # the same at other prior scales of the hub departures
"""
from __future__ import annotations

import hashlib
import json
import sys
from importlib import metadata

import arviz as az
import numpy as np
import pandas as pd
import pymc as pm

from mcp import hub_season as H

SEED = 20261115
CHAINS, TUNE, DRAWS = 4, 2000, 2000
TARGET_ACCEPT = 0.95
RAISED_TARGET_ACCEPT = 0.99
TAU_D_SCALE = 0.1
RHAT_MAX, ESS_MIN = 1.01, 400
MONTHS = [f"{m:02d}" for m in range(1, 13)]
SCALES = ("tau_a", "tau_s", "tau_d", "tau_e", "nu", "sigma")


def index_panel(panel: pd.DataFrame) -> dict:
    hubs = sorted(panel["hub"].unique())
    yms = sorted(panel["ym"].unique())
    return {"hubs": hubs, "yms": yms, "h": panel["hub"].map({h: i for i, h in enumerate(hubs)}).to_numpy(),
            "t": panel["ym"].map({y: i for i, y in enumerate(yms)}).to_numpy(), "m": panel["month"].map({m: i for i, m in enumerate(MONTHS)}).to_numpy(),
            "z": panel["z"].to_numpy(float), "month_of_t": np.array([int(y[5:7]) - 1 for y in yms])}


def build_model(panel: pd.DataFrame, tau_d_scale: float = TAU_D_SCALE, observed: bool = True, shared_shock: bool = True) -> pm.Model:
    """The model of the plan, section 4.2, in the non-centred form. a, s and d are centred in the draw, so that s sums to zero over the
    months and d sums to zero within a hub."""
    d = index_panel(panel)
    n_h, n_t = len(d["hubs"]), len(d["yms"])
    with pm.Model() as model:
        mu = pm.Normal("mu", 0.0, 0.3)
        tau_a = pm.HalfNormal("tau_a", 0.2)
        tau_s = pm.HalfNormal("tau_s", 0.3)
        tau_d = pm.HalfNormal("tau_d", tau_d_scale)
        tau_e = pm.HalfNormal("tau_e", 0.2)
        nu = pm.Gamma("nu", 2.0, 0.1)
        sigma = pm.HalfNormal("sigma", 0.3)
        a_raw = pm.Normal("a_raw", 0.0, 1.0, shape=n_h)
        s_raw = pm.Normal("s_raw", 0.0, 1.0, shape=12)
        d_raw = pm.Normal("d_raw", 0.0, 1.0, shape=(n_h, 12))
        e_raw = pm.Normal("e_raw", 0.0, 1.0, shape=n_t)
        a = pm.Deterministic("a", tau_a * a_raw)
        s = pm.Deterministic("s", tau_s * (s_raw - s_raw.mean()))
        dep = pm.Deterministic("d", tau_d * (d_raw - d_raw.mean(axis=1, keepdims=True)))
        e = pm.Deterministic("e", tau_e * e_raw)
        mean = mu + a[d["h"]] + s[d["m"]] + dep[d["h"], d["m"]] + (e[d["t"]] if shared_shock else 0.0)
        pm.StudentT("z", nu=nu, mu=mean, sigma=sigma, observed=d["z"] if observed else None, shape=len(d["z"]))
    return model


def prior_predictive(panel: pd.DataFrame, draws: int = 1000, seed: int = SEED) -> dict:
    """Draw panels from the priors and report the 5% to 95% range of the simulated z. The plan expects roughly minus 1 to plus 1."""
    model = build_model(panel, observed=False)
    with model:
        idata = pm.sample_prior_predictive(draws=draws, random_seed=seed)
    z = idata.prior["z"].to_numpy().ravel()
    q = np.quantile(z, [0.05, 0.5, 0.95])
    return {"draws": draws, "z_q05": float(q[0]), "z_q50": float(q[1]), "z_q95": float(q[2]), "z_min": float(z.min()), "z_max": float(z.max())}


def fit(panel: pd.DataFrame, seed: int = SEED, tau_d_scale: float = TAU_D_SCALE, target_accept: float = TARGET_ACCEPT,
        chains: int = CHAINS, tune: int = TUNE, draws: int = DRAWS, shared_shock: bool = True):
    model = build_model(panel, tau_d_scale, shared_shock=shared_shock)
    with model:
        return pm.sample(draws=draws, tune=tune, chains=chains, target_accept=target_accept, random_seed=seed, progressbar=False,
                         idata_kwargs={"log_likelihood": False})


def diagnostics(idata, chains: int = CHAINS) -> dict:
    names = ["mu", *SCALES[:4], "nu", "sigma", "a", "s", "d", "e"]
    rhat = az.rhat(idata, var_names=names)
    ess_b = az.ess(idata, var_names=names, method="bulk")
    ess_t = az.ess(idata, var_names=names, method="tail")
    div = int(idata.sample_stats["diverging"].to_numpy().sum())
    mx = lambda ds: float(max(np.nanmax(ds[v].to_numpy()) for v in ds.data_vars))  # noqa: E731
    mn = lambda ds: float(min(np.nanmin(ds[v].to_numpy()) for v in ds.data_vars))  # noqa: E731
    out = {"rhat_max": mx(rhat), "ess_bulk_min": mn(ess_b), "ess_tail_min": mn(ess_t), "divergences": div, "chains": chains}
    out["passed"] = bool(out["rhat_max"] < RHAT_MAX and out["ess_bulk_min"] > ESS_MIN and out["ess_tail_min"] > ESS_MIN and div == 0)
    return out


def _q(x: np.ndarray) -> dict:
    return {"mean": float(np.mean(x)), "q05": float(np.quantile(x, 0.05)), "q50": float(np.quantile(x, 0.5)), "q95": float(np.quantile(x, 0.95))}


def summarise(idata, panel: pd.DataFrame, seed: int, frozen_pooled: dict | None = None, rng_seed: int | None = None,
              shared_shock: bool = True) -> dict:
    """Posterior summaries: the multiplier exp(mu + a + s + d) of each hub and calendar month, the scales, and the predictive mean and
    standard deviation of z for each hub and calendar month of a new year, with a fresh shock e and a fresh residual."""
    d = index_panel(panel)
    post = idata.posterior
    flat = lambda name: post[name].stack(sample=("chain", "draw")).transpose("sample", ...).to_numpy()  # noqa: E731
    mu, a, s, dep = flat("mu"), flat("a"), flat("s"), flat("d")
    tau_e, nu, sigma = flat("tau_e"), flat("nu"), flat("sigma")
    rng = np.random.default_rng(seed if rng_seed is None else rng_seed)
    n = len(mu)
    level = mu[:, None, None] + a[:, :, None] + s[:, None, :] + dep
    e_new = rng.normal(0.0, 1.0, size=(n, 1, 1)) * tau_e[:, None, None] * (1.0 if shared_shock else 0.0)
    eps = rng.standard_t(nu[:, None, None], size=(n, len(d["hubs"]), 12)) * sigma[:, None, None]
    predictive = level + e_new + eps
    out = {"multipliers": {}, "predictive": {}, "prob_d_positive": {}, "prob_above_pooled": {}}
    all_hubs = predictive.mean(axis=1)
    out["predictive_all_hubs"] = {m: {"mean": float(all_hubs[:, j].mean()), "sd": float(all_hubs[:, j].std(ddof=1))} for j, m in enumerate(MONTHS)}
    for i, hub in enumerate(d["hubs"]):
        out["multipliers"][hub] = {m: _q(np.exp(level[:, i, j])) for j, m in enumerate(MONTHS)}
        out["predictive"][hub] = {m: {"mean": float(predictive[:, i, j].mean()), "sd": float(predictive[:, i, j].std(ddof=1))} for j, m in enumerate(MONTHS)}
        out["prob_d_positive"][hub] = {m: float((dep[:, i, j] > 0).mean()) for j, m in enumerate(MONTHS)}
        if frozen_pooled is not None:
            out["prob_above_pooled"][hub] = {m: float((np.exp(level[:, i, j]) > frozen_pooled[m]).mean()) for j, m in enumerate(MONTHS)}
    out["scales"] = {name: _q(flat(name)) for name in SCALES}
    return out


def input_sha256() -> str:
    return hashlib.sha256(H.WEEKS.read_bytes()).hexdigest()


def run_fit(panel: pd.DataFrame, label, seed: int = SEED, tau_d_scale: float = TAU_D_SCALE, frozen_pooled: dict | None = None,
            chains: int = CHAINS, tune: int = TUNE, draws: int = DRAWS) -> dict:
    """One fit with the settings of the plan. If the diagnostics fail, target_accept is raised once to 0.99. A second failure is reported
    in the output and not hidden, and no prior is changed."""
    accept = TARGET_ACCEPT
    idata = fit(panel, seed, tau_d_scale, accept, chains, tune, draws)
    diag = diagnostics(idata, chains)
    if not diag["passed"]:
        accept = RAISED_TARGET_ACCEPT
        idata = fit(panel, seed, tau_d_scale, accept, chains, tune, draws)
        diag = diagnostics(idata, chains)
    out = {"fold": label, "seed": seed, "tau_d_prior_scale": tau_d_scale, "target_accept": accept, "chains": chains, "tune": tune, "draws": draws,
           "n_train_hub_months": int(len(panel)), "diagnostics": diag,
           "versions": {k: metadata.version(k) for k in ("pymc", "pytensor", "arviz", "numpy", "pandas")}, "input_sha256": input_sha256()}
    out.update(summarise(idata, panel, seed, frozen_pooled))
    return out


def fit_fold(panel: pd.DataFrame, held_out_year: int, **kwargs) -> dict:
    return run_fit(panel[panel["year"] != held_out_year].reset_index(drop=True), held_out_year, **kwargs)


def write(result: dict, directory) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{result['fold']}.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")


PRIOR_PREDICTIVE_LIMIT = 3.0
SENSITIVITY = (0.05, 0.2)
SENSITIVITY_FILE = H.ROOT / "results" / "hub_season_sensitivity.json"


def frozen_pooled() -> dict:
    return json.loads((H.ROOT / "models" / "v6_season.json").read_text(encoding="utf-8"))["multiplier"]


def fit_all(panel: pd.DataFrame, directory, tau_d_scale: float = TAU_D_SCALE) -> None:
    """Every fold and the full record. Stops, after writing the failing fit, when a fit still fails its checks at target_accept 0.99."""
    for year in H.folds(panel):
        result = fit_fold(panel, year, tau_d_scale=tau_d_scale, frozen_pooled=frozen_pooled())
        write(result, directory)
        print(year, result["diagnostics"], flush=True)
        if not result["diagnostics"]["passed"]:
            raise SystemExit(f"the fit of fold {year} failed its checks at target_accept {result['target_accept']}: stop and report")
    result = run_fit(panel, "full", tau_d_scale=tau_d_scale, frozen_pooled=frozen_pooled())
    write(result, directory)
    print("full", result["diagnostics"], flush=True)
    if not result["diagnostics"]["passed"]:
        raise SystemExit("the full-record fit failed its checks at target_accept 0.99: stop and report")


def run_dev() -> dict:
    panel = H.hub_month_panel(pd.read_csv(H.WEEKS))
    prior = prior_predictive(panel)
    if prior["z_q05"] < -PRIOR_PREDICTIVE_LIMIT or prior["z_q95"] > PRIOR_PREDICTIVE_LIMIT:
        raise SystemExit(f"the priors span {prior['z_q05']:.2f} to {prior['z_q95']:.2f} in z: stop and report")
    fit_all(panel, H.FITS)
    result = H.dev(pd.read_csv(H.WEEKS), with_hier=True)
    result["prior_predictive"] = prior
    return result


def run_sensitivity() -> dict:
    panel = H.hub_month_panel(pd.read_csv(H.WEEKS))
    out = {}
    for scale in SENSITIVITY:
        directory = H.FITS / f"prior_{scale}"
        fit_all(panel, directory, tau_d_scale=scale)
        scores = H.score(H.leave_one_year_out_panel(panel, H.candidate_hier_from_fits(directory)), panel)
        pooled = H.score(H.leave_one_year_out_panel(panel, H.candidate_pooled), panel)
        full = json.loads((directory / "full.json").read_text(encoding="utf-8"))
        out[str(scale)] = {"tau_d": full["scales"]["tau_d"], "hier": scores, "earns_its_place_vs_pooled": H.earns_its_place(scores["per_fold"], pooled["per_fold"])}
    return out


ARM_C_FILE = H.ROOT / "results" / "backcast_weeks_C.csv"
ARM_C_OUT = H.ROOT / "results" / "hub_season_arm_c.json"


def arm_c_weeks() -> pd.DataFrame:
    """The record of 7J under arm C: the arm C backcast weeks outside the pandemic followed by the development weeks."""
    from mcp.capital import arm_record
    base = pd.read_csv(H.WEEKS)
    development = base[base["source"] == "development_2024_2026"]
    return arm_record(pd.read_csv(ARM_C_FILE), development)


def run_robustness() -> dict:
    """The comparison of section 5 on the arm C record. Reports whether the verdict changes. It chooses nothing."""
    weeks = arm_c_weeks()
    panel = H.hub_month_panel(weeks)
    directory = H.FITS / "arm_c"
    fit_all(panel, directory)
    arm_hash = hashlib.sha256(ARM_C_FILE.read_bytes()).hexdigest()
    for path in directory.glob("*.json"):
        fit = json.loads(path.read_text(encoding="utf-8"))
        fit["input_sha256_arm_c"] = arm_hash
        path.write_text(json.dumps(fit, indent=1) + "\n", encoding="utf-8", newline="\n")
    candidates = {**H.NUMPY_CANDIDATES, "hier": H.candidate_hier_from_fits(directory)}
    scores = {name: H.score(H.leave_one_year_out_panel(panel, fn), panel) for name, fn in candidates.items()}
    return {"record": "arm C backcast weeks outside the pandemic, then the development weeks", "folds": H.folds(panel), "scores": scores,
            "verdicts": {"hier_vs_pooled": H.earns_its_place(scores["hier"]["per_fold"], scores["pooled"]["per_fold"]),
                         "by_hub_vs_pooled": H.earns_its_place(scores["by_hub"]["per_fold"], scores["pooled"]["per_fold"])},
            "tau_d": json.loads((directory / "full.json").read_text(encoding="utf-8"))["scales"]["tau_d"]}


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "prior":
        print(json.dumps(prior_predictive(H.hub_month_panel(pd.read_csv(H.WEEKS))), indent=1))
    elif cmd == "dev":
        result = run_dev()
        H.DEV.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(result["verdicts"], indent=1))
    elif cmd == "sensitivity":
        result = run_sensitivity()
        SENSITIVITY_FILE.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({k: v["earns_its_place_vs_pooled"] for k, v in result.items()}, indent=1))
    elif cmd == "robustness":
        result = run_robustness()
        ARM_C_OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(result["verdicts"], indent=1))
    else:
        raise SystemExit("usage: python -m mcp.hub_season_fit prior | dev | sensitivity | robustness")


if __name__ == "__main__":
    main()
