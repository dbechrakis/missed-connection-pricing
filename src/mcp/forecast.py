"""What a late buyer can know: weather forecasts as issued, and a rule for when to stop selling (WP7).

PREREGISTRATION_V6_FORECAST.md fixes everything here before any forecast was joined to a connection. Forecasts come from the
Open-Meteo Previous Runs API: the value for an hour as the forecast issued d days earlier said it. Features at lead d are
the maxima over the hub hours from one hour before to three hours after the inbound flight's scheduled arrival.

    cd src
    python -m mcp.forecast download                   # five hubs, 1 February 2024 to 31 August 2026, into data/raw/forecast
    MCP_VARIANT=v3 python -m mcp.forecast read        # fits, scores the test window once, grades; refuses a second run
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from mcp.ingest import ROOT

RAW = ROOT / "data" / "raw" / "forecast"
RESULT = ROOT / "results" / "forecast.json"
HUB_XY = {"ATL": (33.6407, -84.4277), "ORD": (41.9742, -87.9073), "DFW": (32.8998, -97.0403), "DEN": (39.8561, -104.6737), "CLT": (35.2140, -80.9431)}
TZ = {"ATL": "America/New_York", "CLT": "America/New_York", "ORD": "America/Chicago", "DFW": "America/Chicago", "DEN": "America/Denver"}
START, END = "2024-02-01", "2026-08-31"
FIT_WINDOW, TEST_WINDOW = ("2024-02-01", "2025-09-01"), ("2025-09-01", "2026-09-01")     # half open; nothing from September 2026 on
LEADS = (1, 2, 3, 5, 7)
VARS = ("precipitation", "snowfall", "wind_gusts_10m", "weather_code")
THUNDER, WINTRY = {95, 96, 99}, {56, 57, 66, 67, 71, 72, 73, 74, 75, 77, 85, 86}
FEATURES = ("fc_precip", "fc_snow", "fc_gust", "fc_thunder", "fc_wintry")
BEFORE, AFTER = 1, 3              # hours around the scheduled arrival
FIT_ROWS, EVAL_FRAC = 3_000_000, 0.10
RULE_RATIO, RULE_LEAD = 1.5, 3
SHARES, THETAS = (0.10, 0.20, 0.30), (0.0, 1.0)
GATE_PCT = 1.0
URL = "https://previous-runs-api.open-meteo.com/v1/forecast"


def column(var: str, lead: int) -> str:
    return f"{var}_previous_day{lead}"


def download(hubs=HUB_XY) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for hub, (lat, lon) in hubs.items():
        path = RAW / f"{hub}.parquet"
        if path.exists():
            continue
        cols = ",".join(column(v, d) for v in VARS for d in LEADS)
        q = {"latitude": lat, "longitude": lon, "hourly": cols, "start_date": START, "end_date": END, "timezone": "UTC"}
        for attempt in range(5):                       # the service resets long requests now and then
            try:
                with urllib.request.urlopen(urllib.request.Request(URL + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "research-script (public data)"}), timeout=300) as r:
                    h = json.loads(r.read().decode("utf-8"))["hourly"]
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(10 * (attempt + 1))
        df = pd.DataFrame(h).rename(columns={"time": "hour_utc"})
        df["hour_utc"] = pd.to_datetime(df["hour_utc"])
        df["hub"] = hub
        df.to_parquet(path, index=False)
        print(f"{hub}: {len(df):,} hours, first non-null per column checked at read", flush=True)
        time.sleep(2)


def window_features(wx: pd.DataFrame, lead: int) -> pd.DataFrame:
    """Per hub and hour t: the maxima over hours t - BEFORE to t + AFTER of the forecasts issued `lead` days earlier. Built
    from forecast columns only, so nothing observed on the day can enter."""
    out = []
    n = BEFORE + AFTER + 1
    for hub, g in wx.sort_values(["hub", "hour_utc"]).groupby("hub"):
        g = g.set_index("hour_utc")
        full = g.reindex(pd.date_range(g.index.min(), g.index.max(), freq="h"))
        code = full[column("weather_code", lead)]
        f = pd.DataFrame({"fc_precip": full[column("precipitation", lead)], "fc_snow": full[column("snowfall", lead)], "fc_gust": full[column("wind_gusts_10m", lead)],
                          "fc_thunder": code.isin(THUNDER).astype(float).where(code.notna()), "fc_wintry": code.isin(WINTRY).astype(float).where(code.notna())})
        f = f.rolling(n, min_periods=n).max().shift(-AFTER)           # the window ending AFTER hours later, moved back to t
        f["hub"] = hub
        f.index.name = "hour_utc"
        out.append(f.reset_index())
    return pd.concat(out, ignore_index=True)


def arrival_hour_utc(df: pd.DataFrame) -> pd.Series:
    """The UTC hour of each connection's scheduled inbound arrival (a naive local time at the hub)."""
    utc = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    local = pd.to_datetime(df["in_sched_arr"])
    for hub, tz in TZ.items():
        m = (df["hub"] == hub).to_numpy()
        if m.any():
            utc[m] = local[m].dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    return utc.dt.floor("h").dt.tz_localize(None)


def attach(df: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    d = df.assign(hour_utc=arrival_hour_utc(df))
    return d.merge(feats, on=["hub", "hour_utc"], how="left")


# ---- the sales rule ------------------------------------------------------------------------------------------------

def rule_outcome(df: pd.DataFrame, share_late: float, theta: float, cap: float, target: float, ratio: float = RULE_RATIO) -> dict:
    """The cover as sold within the cap at the booking-time price, for a book in which `share_late` of the sold weight books
    within three days and chooses connections in proportion to (p_forecast / p_booking)^theta, with and without the rule that
    stops selling to late buyers where that ratio exceeds `ratio`. Needs: weight, y_gap, claim_cost, fare, p_base, p_fc, week."""
    price = df["p_base"] * df["claim_cost"] / target
    sold = df[price <= cap * df["fare"]].copy()
    sold["price"] = price[sold.index]
    r = (sold["p_fc"] / sold["p_base"]).to_numpy()
    w = sold["weight"].to_numpy(float)
    late = share_late * w.sum() * (w * r ** theta) / (w * r ** theta).sum()
    early = (1 - share_late) * w
    out = {}
    for name, keep in (("without_rule", np.ones(len(sold), bool)), ("with_rule", r <= ratio)):
        wt = early + late * keep
        claims = wt * sold["y_gap"].to_numpy() * sold["claim_cost"].to_numpy()
        prem = wt * sold["price"].to_numpy()
        wk = pd.DataFrame({"week": sold["week"].to_numpy(), "c": claims, "p": prem}).groupby("week").sum()
        lr = wk["c"] / wk["p"]
        out[name] = {"loss_ratio": float(claims.sum() / prem.sum()), "weeks": int(len(lr)), "weeks_above_100": int((lr > 1).sum()), "weight": float(wt.sum())}
    out["share_of_sales_lost"] = 1 - out["with_rule"]["weight"] / out["without_rule"]["weight"]
    return out


def shift_month(ym: str, k: int) -> str:
    n = int(ym[:4]) * 12 + int(ym[5:]) - 1 + k
    return f"{n // 12}-{n % 12 + 1:02d}"


def gain_pct(base_ll: float, fc_ll: float) -> float:
    return 100 * (base_ll - fc_ll) / base_ll


def read(fit_window=FIT_WINDOW, test_window=TEST_WINDOW, dry_run: bool = False) -> dict:
    """Fit on February 2024 to August 2025, score September 2025 to August 2026 once. Needs MCP_VARIANT=v3 data.
    `dry_run` runs the same code on other windows of months already seen, writes nothing and does not count as the read."""
    import duckdb
    from mcp import features as F
    from mcp.model import fit_gbm
    from mcp.v2 import FEATURE_SETS, LEAVES
    from mcp.v3 import TARGET_LR, WTP_CAP, claim_cost, gap_label_sql, gsa_table, labels, month_file, month_predicate
    from mcp.v3 import SEVERITY_FULL
    from mcp.connections import WEIGHTED
    from mcp.variant import VARIANT
    assert VARIANT == "v3", "run with MCP_VARIANT=v3"
    if RESULT.exists() and not dry_run:
        raise SystemExit("results/forecast.json exists: the forecast test is read once (PREREGISTRATION_V6_FORECAST.md section 8)")
    wx = pd.concat([pd.read_parquet(RAW / f"{h}.parquet") for h in HUB_XY], ignore_index=True)
    feats = {d: window_features(wx, d) for d in LEADS}
    con, table = duckdb.connect(), gsa_table()
    a, b = fit_window
    F.create_stats(con, fit_flights=f"(flight_date >= DATE '{a}' AND flight_date < DATE '{b}')", fit_asos=f"(obs_utc >= TIMESTAMP '{a}' AND obs_utc < TIMESTAMP '{b}')")
    src = f"read_parquet('{(WEIGHTED / 'mct=45' / 'year=202[456]' / '*.parquet').as_posix()}')"
    pred = f"(r.out_sched_dep >= TIMESTAMP '{a}' AND r.out_sched_dep < TIMESTAMP '{b}')"
    frame = lambda s, p, f: con.execute(gap_label_sql(F.feature_sql(s, p, f, SEVERITY_FULL.as_posix(), with_keys=True))).fetchdf()
    (total,) = con.execute(f"SELECT count(*) FROM {src} r WHERE {pred}").fetchone()
    fit = frame(src, pred, min(1.0, FIT_ROWS / total))
    use = FEATURE_SETS["v1 set"]
    base = fit_gbm(fit.assign(y=fit["y_gap"]), use=use, leaves=LEAVES)
    base_other_seed = fit_gbm(fit.assign(y=fit["y_gap"]), use=use, leaves=LEAVES, seed=1)      # the spread two fits of the SAME information show: a noise floor for kappa
    models = {d: fit_gbm(attach(fit, feats[d]).assign(y=fit["y_gap"].to_numpy()), use=list(use) + list(FEATURES), leaves=LEAVES) for d in LEADS}
    per_month, keep = {}, []
    for y, m, lab in labels(test_window[0][:7], shift_month(test_window[1][:7], -1)):
        df = frame(f"read_parquet('{month_file(y, m)}')", month_predicate(y, m), EVAL_FRAC)
        df = df[df["overnight"].notna() & df["fare"].notna() & (df["overnight"] == 1)].copy()
        df["p_base"] = base(df)
        w, yv = df["weight"].to_numpy(float), df["y_gap"].to_numpy(float)
        ll = lambda p: float(-(w * (yv * np.log(np.clip(p, 1e-6, 1 - 1e-6)) + (1 - yv) * np.log(np.clip(1 - p, 1e-6, 1)))).sum())
        pb2 = base_other_seed(df)
        row = {"w": float(w.sum()), "base": ll(df["p_base"].to_numpy()),
               "noise": (float((w * np.log(pb2 / df["p_base"].to_numpy())).sum()), float((w * np.log(pb2 / df["p_base"].to_numpy()) ** 2).sum()))}
        for d in LEADS:
            x = attach(df, feats[d])
            p = models[d](x)
            row[f"fc{d}"] = ll(p)
            row[f"logratio{d}"] = (float((w * np.log(p / df["p_base"].to_numpy())).sum()), float((w * np.log(p / df["p_base"].to_numpy()) ** 2).sum()))
            if d == RULE_LEAD:
                df["p_fc"] = p
        per_month[lab] = row
        df["claim_cost"] = claim_cost(df, table)
        day = df["out_sched_dep"].dt.normalize()
        df["week"] = (day - pd.to_timedelta(df["out_sched_dep"].dt.day_of_week, unit="D")).astype(str)
        keep.append(df[["weight", "y_gap", "claim_cost", "fare", "p_base", "p_fc", "week"]])
        print(f"  {lab}: {len(df):,} connections scored", flush=True)
    tot = lambda k: sum(r[k] for r in per_month.values())
    wsum = tot("w")
    gains = {str(d): gain_pct(tot("base") / wsum, tot(f"fc{d}") / wsum) for d in LEADS}
    labs = sorted(per_month)
    rng = np.random.default_rng(0)
    ci = {}
    for d in LEADS:
        gs = []
        for _ in range(1000):
            pick = rng.choice(len(labs), len(labs))
            gs.append(gain_pct(sum(per_month[labs[i]]["base"] for i in pick), sum(per_month[labs[i]][f"fc{d}"] for i in pick)))
        ci[str(d)] = [float(np.percentile(gs, 2.5)), float(np.percentile(gs, 97.5))]
    kappa = {}
    for d in LEADS:
        m1 = sum(r[f"logratio{d}"][0] for r in per_month.values()) / wsum
        m2 = sum(r[f"logratio{d}"][1] for r in per_month.values()) / wsum
        kappa[str(d)] = float(np.sqrt(max(m2 - m1 ** 2, 0.0)))
    n1 = sum(r["noise"][0] for r in per_month.values()) / wsum
    n2 = sum(r["noise"][1] for r in per_month.values()) / wsum
    noise = float(np.sqrt(max(n2 - n1 ** 2, 0.0)))
    res = {"status": "the forecast test, read once", "fit": list(fit_window), "test": list(test_window), "months": len(labs), "gain_pct": gains, "gain_ci": ci,
           "kappa": kappa, "kappa_noise_floor": noise, "kappa_net_of_noise": {d: float(np.sqrt(max(k ** 2 - noise ** 2, 0.0))) for d, k in kappa.items()},
           "exposure_theta1": {d: float(np.exp(k ** 2)) for d, k in kappa.items()}, "gate_passed": any(g >= GATE_PCT for g in gains.values())}
    if res["gate_passed"]:
        allrows = pd.concat(keep, ignore_index=True)
        grid = {f"s{int(s * 100)}_theta{int(t)}": rule_outcome(allrows, s, t, WTP_CAP, TARGET_LR) for s in SHARES for t in THETAS}
        res["rule"] = grid
        a20 = grid["s20_theta1"]
        res["rule"]["s20_theta1"] = {**a20, "weeks_above_100_with_rule": a20["with_rule"]["weeks_above_100"], "weeks_above_100_without_rule": a20["without_rule"]["weeks_above_100"]}
    if not dry_run:
        RESULT.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return res


if __name__ == "__main__":
    if sys.argv[1] == "dry-run":                    # 2024-02 to 2025-02 fit, 2025-03 to 2025-05 test: months of the pre-registered fit window, not its test window
        print(json.dumps(read(("2024-02-01", "2025-03-01"), ("2025-03-01", "2025-06-01"), dry_run=True), indent=1)[:1500])
    else:
        {"download": download, "read": read}[sys.argv[1]]()
