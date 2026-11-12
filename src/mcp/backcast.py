"""The v6 backcast: the gap cover's pricing procedure on January 2019 to December 2023, exactly as pre-registered.

PREREGISTRATION_V6_BACKCAST.md and its addendum fix everything below before any 2018 to 2023 outcome exists. This module
is the only code that may read the 2018 to 2023 files (`tests/test_hist.py` guards it).

The procedure is `mcp.v3_rolling`'s: quarterly blocks, each fitted only on months before the block, each month priced by a
model that has not seen it. Two arms: A fits on all earlier months from January 2018, B on the trailing 24 months.

    # 1. the sample check, on seen months, before anything of 2018 to 2023 is read (MCP_VARIANT=v3)
    cd src && MCP_VARIANT=v3 python -m mcp.backcast sample-check 0.20
    # 2. the build and the run, outcome rates never printed (MCP_VARIANT=hist)
    MCP_VARIANT=hist python -m mcp.backcast run A       # about an hour; resumes where it stopped
    MCP_VARIANT=hist python -m mcp.backcast run B
    # 3. the single read, which refuses a second run
    MCP_VARIANT=hist python -m mcp.backcast read
"""
from __future__ import annotations

import json
import sys

import duckdb
import numpy as np
import pandas as pd

from mcp import features as F
from mcp import level as L
from mcp import risk
from mcp import v3_loading as VL
from mcp.connections import ROOT, WEIGHTED
from mcp.model import fit_gbm
from mcp.pricing import SEVERITY
from mcp.v2 import FEATURE_SETS, LEAVES
from mcp.v3 import TARGET_LR, WTP_CAP, claim_cost, gap_label_sql, gsa_table, labels, month_file, month_predicate
from mcp.v3_rolling import ROW_COLS, aggregate, monthly
from mcp.variant import HIST, VARIANT

DATA = ROOT / "data" / "parquet" / "hist_backcast"
RESULT = ROOT / "results" / "backcast.json"
SAMPLE_CHECK = ROOT / "results" / "sample_check.json"
SEVERITY_FULL = SEVERITY.with_name(f"severity_full_{'hist' if HIST else 'v3'}.parquet")
SOURCE_GLOB = (WEIGHTED / "mct=45" / "year=*" / "*.parquet").as_posix()
FIT_ROWS = 3_000_000
USE = FEATURE_SETS["v1 set"]
HIST_FIT_START = "2018-01"
SCORED = ("2019-01", "2023-12")
PANDEMIC = ("2020-03", "2021-06")
TRAILING_MONTHS = 24
SAMPLE_TOLERANCE = 0.02


def quarter_blocks(first: str, last: str) -> list[tuple[str, str]]:
    out, (y, m) = [], (int(first[:4]), int(first[5:]))
    while f"{y}-{m:02d}" <= last:
        e = (y * 12 + m - 1) + 2
        out.append((f"{y}-{m:02d}", f"{e // 12}-{e % 12 + 1:02d}"))
        y, m = (y + 1, 1) if m >= 10 else (y, m + 3)
    return out


HIST_BLOCKS = quarter_blocks(*SCORED)


def shift(ym: str, k: int) -> str:
    n = int(ym[:4]) * 12 + int(ym[5:]) - 1 + k
    return f"{n // 12}-{n % 12 + 1:02d}"


def is_pandemic(ym: str) -> bool:
    return PANDEMIC[0] <= ym <= PANDEMIC[1]


def fit_bounds(arm: str, block_start: str, fit_start: str) -> tuple[str, str]:
    """First month (inclusive) and the block start (exclusive) of the months a block's model is fitted on."""
    if arm == "A":
        return fit_start, block_start
    if arm == "B":
        return max(fit_start, shift(block_start, -TRAILING_MONTHS)), block_start
    raise ValueError(arm)


def window(col: str, start: str, end: str) -> str:
    return f"({col} >= TIMESTAMP '{start}-01' AND {col} < TIMESTAMP '{end}-01')"


def run_block(con, start: str, end: str, table: dict, arm: str, fit_start: str, frac: float, rows_dir) -> pd.DataFrame:
    a, b = fit_bounds(arm, start, fit_start)
    F.create_stats(con, fit_flights=window("flight_date", a, b), fit_asos=window("obs_utc", a, b))
    src = f"read_parquet('{SOURCE_GLOB}')"
    pred = window("r.out_sched_dep", a, b)
    (total,) = con.execute(f"SELECT count(*) FROM {src} r WHERE {pred}").fetchone()
    frame = lambda s, p, f: con.execute(gap_label_sql(F.feature_sql(s, p, f, SEVERITY_FULL.as_posix(), with_keys=True))).fetchdf()
    fit = frame(src, pred, min(1.0, FIT_ROWS / total))
    g = fit_gbm(fit.assign(y=fit["y_gap"]), use=USE, leaves=LEAVES)
    parts = []
    for y, m, lab in labels(start, end):
        df = frame(f"read_parquet('{month_file(y, m)}')", month_predicate(y, m), frac)
        df = df[df["overnight"].notna() & df["fare"].notna()]
        df = df[df["overnight"] == 1].copy()
        df["p"] = g(df)
        df["claim_cost"] = claim_cost(df, table)
        day = df["out_sched_dep"].dt.normalize()
        df["week"] = (day - pd.to_timedelta(df["out_sched_dep"].dt.day_of_week, unit="D")).astype(str)
        df["ym"] = lab
        parts.append(aggregate(df))
        rows_dir.mkdir(parents=True, exist_ok=True)
        df[ROW_COLS].to_parquet(rows_dir / f"{lab}.parquet", index=False)
        print(f"  {lab}: {len(df):,} overnight-risk connections, fitted on {a} to {shift(b, -1)} ({len(fit):,} rows)", flush=True)     # counts only
    return pd.concat(parts, ignore_index=True)


def run(arm: str, blocks=None, fit_start: str = HIST_FIT_START, frac: float = 0.20, out=None) -> pd.DataFrame:
    """Every block of one arm, saved as it goes. Prints counts and fitted windows, never an outcome rate."""
    assert VARIANT == "hist" or out is not None, "run with MCP_VARIANT=hist"
    out = out or DATA
    blocks = blocks or HIST_BLOCKS
    weeks_path, rows_dir = out / f"weeks_{arm}.csv", out / f"rows_{arm}"
    done = pd.read_csv(weeks_path) if weeks_path.exists() else pd.DataFrame()
    have = set(done["ym"]) if len(done) else set()
    table, con = gsa_table(), duckdb.connect()
    for start, end in blocks:
        if all(lab in have for _, _, lab in labels(start, end)):
            print(f"block {start} to {end}: already done", flush=True)
            continue
        print(f"block {start} to {end}, arm {arm}", flush=True)
        done = pd.concat([done, run_block(con, start, end, table, arm, fit_start, frac, rows_dir)], ignore_index=True)
        out.mkdir(parents=True, exist_ok=True)
        done.to_csv(weeks_path, index=False)
    return done


# ---- the sample check on months that were already seen --------------------------------------------------------

def pooled(weeks: pd.DataFrame, sold: bool) -> float:
    m = monthly(weeks, sold)
    return float(m["claims"].sum() / m["expected"].sum())


def sample_check(frac: float) -> dict:
    """The gap cover's 26 development months rebuilt at `frac` must reproduce the published pooled ratios of
    results/v3_rolling.json within SAMPLE_TOLERANCE. Reads only months that were already seen."""
    from mcp.v3_rolling import BLOCKS
    assert VARIANT == "v3", "run with MCP_VARIANT=v3: this check uses only the 2024 to 2026 months already seen"
    out = DATA / f"sample_check_{int(round(frac * 100))}"
    weeks = run("A", blocks=BLOCKS, fit_start="2024-01", frac=frac, out=out)
    pub = json.loads((ROOT / "results" / "v3_rolling.json").read_text(encoding="utf-8"))
    res = {"fraction": frac, "tolerance": SAMPLE_TOLERANCE, "months": int(weeks["ym"].nunique()),
           "published": {"all_overnight_risk": pub["all_overnight_risk"]["pooled_ratio"], "sold_within_cap": pub["sold_within_cap"]["pooled_ratio"]},
           "rebuilt": {"all_overnight_risk": pooled(weeks, False), "sold_within_cap": pooled(weeks, True)}}
    res["difference"] = {k: res["rebuilt"][k] - res["published"][k] for k in res["rebuilt"]}
    res["passed"] = all(abs(d) <= SAMPLE_TOLERANCE for d in res["difference"].values())
    res["status"] = "sample check on the 26 development months of 2024 to 2026, before any 2018 to 2023 outcome was read"
    SAMPLE_CHECK.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return res


# ---- the single read ------------------------------------------------------------------------------------------

def scored_months() -> list[str]:
    out, (y, m) = [], (int(SCORED[0][:4]), int(SCORED[0][5:]))
    while f"{y}-{m:02d}" <= SCORED[1]:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def monthly_series(weeks: pd.DataFrame, sold: bool, by_hub: bool = False):
    """Monthly claims and expected claims over the scored calendar, NaN for months without weeks (the pandemic months are
    removed before this is called)."""
    cal = scored_months()
    d = weeks[weeks["sold"]] if sold else weeks
    if by_hub:
        g = d.groupby(["ym", "hub"])[["claims", "expected"]].sum().reset_index()
        c = g.pivot(index="ym", columns="hub", values="claims").reindex(cal)
        e = g.pivot(index="ym", columns="hub", values="expected").reindex(cal)
        return c, e
    g = d.groupby("ym")[["claims", "expected"]].sum().reindex(cal)
    return g["claims"], g["expected"]


def level_results(weeks: pd.DataFrame) -> dict:
    """The level candidates on the pooled monthly series, scored over the months that have a forecast from `none`,
    `last12` and `local` (the months of expectations B6 and B7)."""
    cal = scored_months()
    c, e = monthly_series(weeks, False)
    z = np.log(c.to_numpy() / e.to_numpy())
    wf = {m: L.walk_forward(z, cal, L.LAGS["gap_cover"], m) for m in ("none", "last12", "local", "local_season")}
    ok = np.ones(len(cal), bool)
    for m in ("none", "last12", "local"):
        ok &= ~np.isnan(wf[m]["mu"])
    ok &= ~np.isnan(z)
    out = {"months_scored": int(ok.sum()), "months": [cal[i] for i in np.flatnonzero(ok)], "crps": {}, "coverage": {}, "repriced": {}}
    for m, w in wf.items():
        mask = ok if m != "local_season" else ok & ~np.array([u is None for u in w["used"]])
        s = L.score(np.where(mask, z, np.nan), w["mu"], w["var"])
        out["crps"][m], out["coverage"][m] = s["crps"], s["coverage"]
        out["repriced"][m] = L.repriced_ratio(np.where(mask, c.to_numpy(), np.nan), e.to_numpy(), w["mu"], w["var"])
    lo, hi = risk.normal_interval(wf["local"]["mu"][ok], np.sqrt(wf["local"]["var"][ok]), L.LEVEL)
    out["interval_hits"] = int(((z[ok] >= lo) & (z[ok] <= hi)).sum())
    out["local_season_active_months"] = [cal[i] for i, u in enumerate(wf["local_season"]["used"]) if u == "local_season"]
    return out


def level_change_report(weeks: pd.DataFrame) -> dict:
    """B10, reported without a prediction: the 12-month level (log of claims over expected, all overnight-risk connections)
    wherever all 12 months are observed, and the largest change between two such windows ending 12 months apart."""
    cal = scored_months()
    c, e = monthly_series(weeks, False)
    lvl = {}
    for i, m in enumerate(cal):
        w = cal[max(0, i - 11):i + 1]
        if len(w) == 12 and not c.loc[w].isna().any():
            lvl[m] = float(np.log(c.loc[w].sum() / e.loc[w].sum()))
    pairs = [(m, shift(m, -12)) for m in lvl if shift(m, -12) in lvl]
    changes = {m: lvl[m] - lvl[p] for m, p in pairs}
    dev = json.loads((ROOT / "results" / "v3_rolling.json").read_text(encoding="utf-8"))["all_overnight_risk"]["monthly_ratio"]
    dm = sorted(dev)
    dl = {dm[i]: float(np.log(np.mean(list(dev.values())[i - 11:i + 1]))) for i in range(11, len(dm))}
    dchg = {m: dl[m] - dl[shift(m, -12)] for m in dl if shift(m, -12) in dl}
    return {"windows": lvl, "largest_12_month_change": max(changes.values(), key=abs) if changes else None, "changes": changes,
            "development_2024_2026": {"largest_12_month_change": max(dchg.values(), key=abs) if dchg else None, "changes": dchg,
                                      "note": "the development level is the mean of the monthly ratios, as the committed results hold no claims and expected sums by month"},
            "note": "the pre-registration asks for the change over any earlier 24 months; with 16 pandemic months removed no two valid windows are 24 months apart, so windows ending 12 months apart are used"}


def arm_results(weeks: pd.DataFrame, rows_dir) -> dict:
    w = weeks[~weeks["ym"].map(is_pandemic)]
    mm_all, mm_sold = monthly(w, False), monthly(w, True)
    months = {f.stem: pd.read_parquet(f) for f in sorted(rows_dir.glob("*.parquet")) if not is_pandemic(f.stem)}
    roll = VL.rolling(months, lag=VL.LAG, min_months=VL.MIN_MONTHS)
    pool = lambda p: float(roll[f"{p}_claims"].sum() / roll[f"{p}_premium"].sum())
    return {"n_months": int(len(mm_all)), "pooled_ratio_all": float(mm_all["claims"].sum() / mm_all["expected"].sum()),
            "pooled_ratio_sold": float(mm_sold["claims"].sum() / mm_sold["expected"].sum()),
            "monthly_ratio_all": {k: float(v) for k, v in mm_all["ratio"].items()}, "monthly_ratio_sold": {k: float(v) for k, v in mm_sold["ratio"].items()},
            "monthly_sold_loss_ratio": {k: float(v) for k, v in mm_sold["loss_ratio"].items()},
            "sold_loss_ratio_unloaded": pool("base"), "sold_loss_ratio_loaded": pool("loaded"), "loading_months": int(len(roll)),
            "loading_lambda": {k: float(v) for k, v in zip(roll["ym"], roll["lam"])},
            "weeks_above_100_sold": int((risk_weekly(w, True) > 1).sum()), "weeks": int(risk_weekly(w, True).shape[0])}


def risk_weekly(weeks: pd.DataFrame, sold: bool) -> pd.Series:
    d = weeks[weeks["sold"]] if sold else weeks
    s = d.groupby("week")[["claims", "premium"]].sum()
    return (s["claims"] / s["premium"]).sort_index()


def pandemic_report(weeks: pd.DataFrame) -> dict:
    w = weeks[weeks["ym"].map(is_pandemic)]
    if w.empty:
        return {}
    m = monthly(w, False)
    return {"months": int(len(m)), "pooled_ratio_all": float(m["claims"].sum() / m["expected"].sum()), "monthly_ratio_all": {k: float(v) for k, v in m["ratio"].items()}}


def by_hub_year(weeks: pd.DataFrame) -> dict:
    w = weeks[~weeks["ym"].map(is_pandemic)].assign(year=lambda d: d["ym"].str[:4])
    g = w.groupby(["hub", "year"])[["claims", "expected"]].sum()
    return {h: {y: float(r["claims"] / r["expected"]) for y, r in sub.droplevel(0).iterrows()} for h, sub in g.groupby(level=0)}


def read() -> dict:
    assert VARIANT == "hist", "run with MCP_VARIANT=hist"
    if RESULT.exists():
        raise SystemExit("results/backcast.json exists: the backcast is read once (PREREGISTRATION_V6_BACKCAST.md section 8)")
    A, B = pd.read_csv(DATA / "weeks_A.csv"), pd.read_csv(DATA / "weeks_B.csv")
    wa = A[~A["ym"].map(is_pandemic)]
    res = {"status": "the v6 backcast, read once", "scored": list(SCORED), "pandemic": list(PANDEMIC), "n_months": int(wa["ym"].nunique()),
           "gap": {**arm_results(A, DATA / "rows_A")}, "level": level_results(wa), "arm_B": arm_results(B, DATA / "rows_B"),
           "by_hub_year": by_hub_year(A), "pandemic_months": pandemic_report(A), "level_change": level_change_report(wa)}
    res["gap"]["pooled_ratio_all_by_arm"] = {"A": res["gap"]["pooled_ratio_all"], "B": res["arm_B"]["pooled_ratio_all"]}
    st = DATA / "self_transfer.json"
    if st.exists():
        res["self_transfer"] = json.loads(st.read_text(encoding="utf-8"))
    RESULT.write_text(json.dumps(res, indent=1, default=float) + "\n", encoding="utf-8", newline="\n")
    return res


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "run":
        run(sys.argv[2])
    elif cmd == "sample-check":
        print(sample_check(float(sys.argv[2])))
    elif cmd == "read":
        read()
