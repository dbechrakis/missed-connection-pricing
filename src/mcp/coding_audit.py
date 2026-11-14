"""The coding audit: did airlines change how they code delays once a code decided who pays for the hotel?

PREREGISTRATION_V6_CODING.md fixes everything here before any pre-2024 cause-code series was loaded. Outcomes are shares
of carrier-coded events by airline and month, adjusted for conditions the airline does not write: hub weather (ASOS) and
FAA ground stops and ground delay programs. The break is 1 September 2022. It is read once.

    cd src
    python -m mcp.coding_audit            # reads results/ once, refuses a second run

Outcomes, per marketing airline and month, at the five hubs:
    Y1  of cancellations coded carrier, weather or national air system (A, B, C), the share coded carrier (A).
    Y2  of the delay minutes of flights that arrived 180 or more minutes late, the share coded to carrier delay.
Covariates, per airline and month: the share of the airline's flights in that outcome's denominator that were at the hub
under adverse weather (thunder, snow, freezing weather, visibility under one mile, wind of 25 knots or gust of 35) in the hour
of the flight's scheduled time at the hub, and the share under a ground stop or ground delay program written by the FAA.
(The pre-registration says "flight-hours"; each flight's own hub hour is the reading used, so that the covariate can differ
between airlines in the same month.)
Model: weighted least squares of the share on airline effects, month-of-year effects, the two covariates and `post`.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from mcp import faa
from mcp.ingest import HUBS, ROOT

RESULT = ROOT / "results" / "coding_audit.json"
GATE = ROOT / "data" / "external" / "faa" / "gate.json"
FLIGHT_DIRS = (ROOT / "data" / "parquet" / "ontime_hist", ROOT / "data" / "parquet" / "ontime_v3")
ASOS_FILE = ROOT / "data" / "parquet" / "asos" / "hourly_hist.parquet"
FIRST, LAST_DATE = "2018-01-01", "2026-09-01"            # flight dates below LAST_DATE: nothing from September 2026 on is read
COMMITTING = ("AA", "DL", "UA", "WN", "AS", "B6", "G4", "HA")   # named as committing to a hotel in data/external/dot/hotel_commitments.json
COMPARISON = "F9"
PANDEMIC = ("2020-03", "2021-06")
BREAK, SENSITIVITY_BREAKS = "2022-09", ("2022-06", "2023-01")
PLACEBO_BREAK, PLACEBO_WINDOW = "2019-09", ("2018-01", "2020-02")
MIN_DENOMINATOR = 200            # an airline-month needs this many flights in the outcome's denominator
MIN_VOLUME = 1000                # an airline needs this many cancelled or 3-hour-late flights in each of the two periods
MATERIAL_POINTS = 3.0
GAP_SHARE_STRICT = 0.725         # share of misses in the gap, strict reading (VALIDATION.md 5A)
N_BOOT, SEED = 2000, 0
TZ = {"ATL": "America/New_York", "CLT": "America/New_York", "ORD": "America/Chicago", "DFW": "America/Chicago", "DEN": "America/Denver"}


def is_pandemic(ym: str) -> bool:
    return PANDEMIC[0] <= ym <= PANDEMIC[1]


def quarter_of(ym: str) -> str:
    return f"{ym[:4]}Q{(int(ym[5:]) - 1) // 3 + 1}"


# ---- the flights, with their hub hour and conditions -----------------------------------------------------------------

def load_flights() -> pd.DataFrame:
    """Cancelled flights coded A, B or C, and flights that arrived 180 or more minutes late, 2018 to August 2026."""
    import duckdb
    parts = [f"SELECT carrier, flight_date, origin, dest, crs_dep_hhmm, crs_arr_hhmm, cancelled, cancellation_code, arr_delay_min, "
             f"delay_carrier_min, delay_weather_min, delay_nas_min, delay_security_min, delay_late_aircraft_min "
             f"FROM read_parquet('{(d / '*' / '*.parquet').as_posix()}') WHERE flight_date >= DATE '{FIRST}' AND flight_date < DATE '{LAST_DATE}'"
             for d in FLIGHT_DIRS if d.exists()]
    sql = "SELECT * FROM (" + " UNION ALL ".join(parts) + ") WHERE (cancelled AND cancellation_code IN ('A', 'B', 'C')) " \
          "OR (NOT cancelled AND arr_delay_min >= 180)"
    df = duckdb.connect().execute(sql).fetchdf()
    return df.drop_duplicates(subset=["carrier", "flight_date", "origin", "dest", "crs_dep_hhmm", "crs_arr_hhmm"])


def hub_hour(df: pd.DataFrame) -> pd.DataFrame:
    """The hub, and the UTC hour of the flight's scheduled time at the hub (departure if it leaves a hub, else arrival)."""
    out = df.copy()
    dep_hub = out["origin"].isin(HUBS)
    out["hub"] = np.where(dep_hub, out["origin"], out["dest"])
    hhmm = np.where(dep_hub, out["crs_dep_hhmm"], out["crs_arr_hhmm"])
    minutes = (hhmm // 100) * 60 + hhmm % 100
    local = pd.to_datetime(out["flight_date"]) + pd.to_timedelta(minutes, unit="m")
    utc = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    for hub, tz in TZ.items():
        m = (out["hub"] == hub).to_numpy()
        if m.any():
            utc[m] = local[m].dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    out["hub_utc"] = utc
    out["hub_hour_utc"] = utc.dt.floor("h")
    return out


def add_conditions(df: pd.DataFrame, asos: pd.DataFrame, programs: list[dict] | None) -> pd.DataFrame:
    """`weather` (any adverse flag at the hub in the hour) and `faa` (an FAA program in effect at the hub at the time)."""
    a = asos.copy()
    a["hour"] = pd.to_datetime(a["obs_utc"]).dt.floor("h").dt.tz_localize("UTC")
    a["adverse"] = a[["thunder", "snow", "freezing", "low_vis", "high_wind"]].any(axis=1)
    hours = a.groupby(["station", "hour"])["adverse"].max().rename("weather").reset_index()
    out = df.merge(hours, left_on=["hub", "hub_hour_utc"], right_on=["station", "hour"], how="left").drop(columns=["station", "hour"])
    out["weather"] = out["weather"].fillna(False).astype(float)
    if programs is None:
        out["faa"] = 0.0
    else:
        iv = faa.active_intervals(programs)
        out["faa"] = 0.0
        for hub, spans in iv.items():
            m = (out["hub"] == hub) & out["hub_utc"].notna()
            if m.any() and spans:
                out.loc[m, "faa"] = faa.covered(spans, out.loc[m, "hub_utc"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()).astype(float)
    return out


# ---- the airline-month panels ---------------------------------------------------------------------------------------

def panels(df: pd.DataFrame) -> dict:
    """{'Y1': panel, 'Y2': panel}; each row is an airline-month with `share`, `n` (flights), `w` (the weight), and covariates."""
    d = df.assign(ym=pd.to_datetime(df["flight_date"]).dt.strftime("%Y-%m"))
    d = d[~d["ym"].map(is_pandemic)]
    c = d[d["cancelled"].astype(bool)]
    y1 = c.assign(a=(c["cancellation_code"] == "A").astype(float)).groupby(["carrier", "ym"]).agg(
        n=("a", "size"), share=("a", "mean"), weather=("weather", "mean"), faa=("faa", "mean")).reset_index()
    y1["w"] = y1["n"]
    late = d[~d["cancelled"].astype(bool)].copy()
    cols = ["delay_carrier_min", "delay_weather_min", "delay_nas_min", "delay_security_min", "delay_late_aircraft_min"]
    late["tot"] = late[cols].fillna(0).sum(axis=1)
    late = late[late["tot"] > 0]
    late["car"] = late["delay_carrier_min"].fillna(0)
    g = late.groupby(["carrier", "ym"]).agg(n=("tot", "size"), tot=("tot", "sum"), car=("car", "sum"), weather=("weather", "mean"), faa=("faa", "mean")).reset_index()
    g["share"] = g["car"] / g["tot"]
    g["w"] = g["tot"]
    y2 = g[["carrier", "ym", "n", "share", "weather", "faa", "w"]]
    return {"Y1": y1[y1["n"] >= MIN_DENOMINATOR].reset_index(drop=True), "Y2": y2[y2["n"] >= MIN_DENOMINATOR].reset_index(drop=True)}


def eligible(panel_set: dict, airlines, break_ym: str, window: tuple[str, str]) -> list[str]:
    """Airlines with at least MIN_VOLUME cancelled or 3-hour-late flights both before and after the break, inside the window."""
    out = []
    for a in airlines:
        pre = post = 0
        for p in panel_set.values():
            q = p[(p["carrier"] == a) & (p["ym"] >= window[0]) & (p["ym"] <= window[1])]
            pre += int(q.loc[q["ym"] < break_ym, "n"].sum())
            post += int(q.loc[q["ym"] >= break_ym, "n"].sum())
        if pre >= MIN_VOLUME and post >= MIN_VOLUME:
            out.append(a)
    return out


# ---- the regression -------------------------------------------------------------------------------------------------

def design(p: pd.DataFrame, break_ym: str, covariates: tuple[str, ...], did_group=None, airlines=None) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    airlines = airlines or sorted(p["carrier"].unique())
    cols, names = [], []
    for a in airlines:
        cols.append((p["carrier"] == a).to_numpy(float))
        names.append(f"airline_{a}")
    moy = p["ym"].str[5:].astype(int).to_numpy()
    for m in range(2, 13):
        cols.append((moy == m).astype(float))
        names.append(f"month_{m}")
    for c in covariates:
        cols.append(p[c].to_numpy(float))
        names.append(c)
    post = (p["ym"] >= break_ym).to_numpy(float)
    if did_group is not None:
        cols.append(post)
        names.append("post_all")
        cols.append(post * p["carrier"].isin(did_group).to_numpy(float))
        names.append("post")
    else:
        cols.append(post)
        names.append("post")
    return np.column_stack(cols), p["share"].to_numpy(float), p["w"].to_numpy(float), names


def post_effect(p: pd.DataFrame, break_ym: str, covariates=("weather", "faa"), did_group=None) -> float:
    """The coefficient of `post`, in percentage points, from weighted least squares."""
    X, y, w, names = design(p, break_ym, covariates, did_group)
    sw = np.sqrt(w)
    beta = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0]
    return float(100 * beta[names.index("post")])


def bootstrap_ci(p: pd.DataFrame, break_ym: str, covariates, did_group=None, n_boot: int = N_BOOT, seed: int = SEED) -> list[float]:
    """95% interval from resampling calendar quarters (all airlines of a quarter together)."""
    q = p["ym"].map(quarter_of)
    quarters = sorted(q.unique())
    groups = {k: p[q == k] for k in quarters}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        draw = rng.choice(len(quarters), len(quarters))
        b = pd.concat([groups[quarters[i]] for i in draw], ignore_index=True)
        if (b["ym"] >= break_ym).nunique() < 2:
            continue
        out.append(post_effect(b, break_ym, covariates, did_group))
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]


def estimate(panel_set: dict, airlines: list[str], break_ym: str, window: tuple[str, str], covariates, did_group=None, n_boot: int = N_BOOT) -> dict:
    out = {}
    for name, p in panel_set.items():
        q = p[p["carrier"].isin(airlines) & (p["ym"] >= window[0]) & (p["ym"] <= window[1])].reset_index(drop=True)
        out[name] = {"effect": post_effect(q, break_ym, covariates, did_group), "ci": bootstrap_ci(q, break_ym, covariates, did_group, n_boot),
                     "airline_months": int(len(q)), "flights": int(q["n"].sum())}
    return out


def faa_usable() -> bool:
    """The advisories are used only if the plan's gate was passed (90 of 100 hand-checked programs). Otherwise weather only."""
    return GATE.exists() and bool(json.loads(GATE.read_text(encoding="utf-8")).get("passed"))


def run(panel_set: dict, covariates: tuple[str, ...], n_boot: int = N_BOOT) -> dict:
    """The pre-registered analysis on prepared panels."""
    full = ("2018-01", "2026-08")
    committing = eligible(panel_set, COMMITTING, BREAK, full)
    placebo_air = eligible(panel_set, COMMITTING, PLACEBO_BREAK, PLACEBO_WINDOW)
    res = {"airlines": committing, "placebo_airlines": placebo_air, "covariates": list(covariates), "break": BREAK, "placebo_break": PLACEBO_BREAK,
           "primary": estimate(panel_set, committing, BREAK, full, covariates, n_boot=n_boot),
           "placebo": estimate(panel_set, placebo_air, PLACEBO_BREAK, PLACEBO_WINDOW, covariates, n_boot=n_boot),
           "sensitivity_breaks": {b: estimate(panel_set, committing, b, full, covariates, n_boot=n_boot) for b in SENSITIVITY_BREAKS},
           "per_airline": {a: estimate(panel_set, [a], BREAK, full, covariates, n_boot=0 if n_boot == 0 else min(n_boot, 500)) for a in committing}}
    both = committing + ([COMPARISON] if COMPARISON in panel_set["Y1"]["carrier"].unique() else [])
    res["difference_in_differences"] = (estimate(panel_set, both, BREAK, full, covariates, did_group=committing, n_boot=n_boot) if COMPARISON in both else None)
    est = res["primary"]
    res["materiality"] = {"points": MATERIAL_POINTS, "gap_share_strict": GAP_SHARE_STRICT,
                          "claims_increase_if_fall_of_threshold": MATERIAL_POINTS / (100 * GAP_SHARE_STRICT),
                          "claims_increase_at_estimate": {k: -v["effect"] / (100 * GAP_SHARE_STRICT) for k, v in est.items()}}
    return res


def read() -> dict:
    if RESULT.exists():
        raise SystemExit("results/coding_audit.json exists: the coding audit is read once (PREREGISTRATION_V6_CODING.md section 8)")
    import duckdb
    flights = hub_hour(load_flights())
    asos = duckdb.connect().execute(f"SELECT * FROM read_parquet('{ASOS_FILE.as_posix()}')").fetchdf()
    programs = faa.programs("2018-01", "2026-08") if faa_usable() else None
    panel_set = panels(add_conditions(flights, asos, programs))
    covariates = ("weather", "faa") if programs is not None else ("weather",)
    res = run(panel_set, covariates)
    res["status"] = "the coding audit, read once"
    res["faa_used"] = programs is not None
    RESULT.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return res


PLACEBO_DISTRIBUTION = ROOT / "results" / "coding_placebo_distribution.json"
MIN_MONTHS_EACH_SIDE = 8
PRE_PERIOD = ("2018-01", "2022-08")


def fake_breaks(panel: pd.DataFrame, window: tuple[str, str] = PRE_PERIOD, min_months: int = MIN_MONTHS_EACH_SIDE) -> list[str]:
    """Months inside the window at which a fake break leaves at least `min_months` observed months on each side. Pandemic months are not in
    the panels, so they are not counted."""
    months = sorted(m for m in panel["ym"].unique() if window[0] <= m <= window[1])
    return [b for b in months if sum(m < b for m in months) >= min_months and sum(m >= b for m in months) >= min_months]


def placebo_distribution(panel_set: dict, covariates: tuple[str, ...], airlines=COMMITTING, window: tuple[str, str] = PRE_PERIOD) -> dict:
    """The point estimate of the primary model for every fake break in the period before the real one, for each outcome. Fake breaks next to
    each other share their data, so the distribution is a reference for the size of change this design finds when nothing happened, and not
    a test."""
    out = {}
    for name, p in panel_set.items():
        rows = {}
        for b in fake_breaks(p, window):
            air = eligible(panel_set, airlines, b, window)
            q = p[p["carrier"].isin(air) & (p["ym"] >= window[0]) & (p["ym"] <= window[1])].reset_index(drop=True)
            if len(air) and q["ym"].nunique() > 1 and (q["ym"] >= b).any() and (q["ym"] < b).any():
                rows[b] = {"effect": post_effect(q, b, covariates), "airlines": air, "airline_months": int(len(q))}
        eff = np.array([v["effect"] for v in rows.values()])
        out[name] = {"breaks": rows, "n_breaks": int(len(eff)), "p2_5": float(np.percentile(eff, 2.5)), "p97_5": float(np.percentile(eff, 97.5)),
                     "min": float(eff.min()), "max": float(eff.max())}
    return out


def place_real_estimates(dist: dict, real: dict) -> dict:
    """For each outcome, the share of fake-break estimates at or below the real estimate and whether it lies outside the central 95%."""
    out = {}
    for name, d in dist.items():
        eff = np.array([v["effect"] for v in d["breaks"].values()])
        r = real[name]["effect"]
        out[name] = {"real_effect": r, "share_of_fake_at_or_below": float((eff <= r).mean()), "outside_central_95": bool(r < d["p2_5"] or r > d["p97_5"])}
    return out


def read_placebo() -> dict:
    if PLACEBO_DISTRIBUTION.exists():
        raise SystemExit("results/coding_placebo_distribution.json exists")
    import duckdb
    flights = hub_hour(load_flights())
    asos = duckdb.connect().execute(f"SELECT * FROM read_parquet('{ASOS_FILE.as_posix()}')").fetchdf()
    programs = faa.programs("2018-01", "2026-08") if faa_usable() else None
    panel_set = panels(add_conditions(flights, asos, programs))
    covariates = ("weather", "faa") if programs is not None else ("weather",)
    dist = placebo_distribution(panel_set, covariates)
    real = json.loads(RESULT.read_text(encoding="utf-8"))["primary"]
    res = {"status": "exploratory reference distribution of fake breaks, after the single read (VALIDATION.md 7L)", "window": list(PRE_PERIOD),
           "min_months_each_side": MIN_MONTHS_EACH_SIDE, "distribution": dist, "real_break": BREAK, "real_in_distribution": place_real_estimates(dist, real)}
    PLACEBO_DISTRIBUTION.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return res


if __name__ == "__main__":
    read_placebo() if sys.argv[1:] == ["placebo"] else read()
