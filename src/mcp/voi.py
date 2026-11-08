"""Value of information: how much would knowing the day improve the prediction? (spec: nice-to-have)

The price is quoted at booking, so it may only use what is known then. Two things become known on the day:
how late the inbound flight left, and the weather at the hub. This module asks whether they improve P(miss)
enough to justify a second product, an alert to the traveller, and how many misses such an alert could catch.

Alert time, defined practically: ONE HOUR BEFORE the inbound flight's scheduled arrival at the hub. Then known:
  in_dep_delay_known  how late the inbound flight left, IF it had left by then; if it had not, only that it is at least
                      as late as the time already elapsed since its scheduled departure
  in_not_departed     1 if it had not left yet at the alert time
  wx_*                hub weather in the hour before that moment: thunder, snow, freezing, low visibility, strong wind, precip
Not used: the inbound's actual arrival delay (unknown until it lands), its final departure delay when that came after
the alert time (a first version of this analysis used it and overstated the value; see VALIDATION.md 4H), and anything
about the outbound flight.

Inbound flights that were cancelled are excluded: an alert for them is trivial (the connection is lost) and would
swamp the signal; their share of all misses is reported separately. Diversions happen in the air, so they stay.
Everything is on development data (fit on 2024, evaluated on Jan to Jun 2025); no sealed window is read.

Run:  python -m mcp.voi     (from src/; a few minutes; writes results/voi.json and docs/figures/voi.png)
"""
from __future__ import annotations

import json

import duckdb
import numpy as np

from mcp import features as F
from mcp.connections import ROOT, WEIGHTED
from mcp.ingest import HUBS
from mcp.split import where

RESULTS = ROOT / "results" / "voi.json"
FLIGHTS = (ROOT / "data" / "parquet" / "ontime" / "*" / "*.parquet").as_posix()
ASOS = (ROOT / "data" / "parquet" / "asos" / "hourly.parquet").as_posix()
TZ = {"ATL": "America/New_York", "CLT": "America/New_York", "ORD": "America/Chicago", "DFW": "America/Chicago",
      "DEN": "America/Denver"}
BOOKING = F.CATEGORICAL + ["slack_min", "out_hour", "out_dow", "in_arr_hour"] + F.ROUTE_HISTORY
DAY_OF_DELAY = ["in_dep_delay_known", "in_not_departed"]
DAY_OF_WEATHER = ["wx_thunder", "wx_snow", "wx_freezing", "wx_low_vis", "wx_high_wind", "wx_vis_min", "wx_wind_max", "wx_precip"]
FEATURE_SETS = {"booking time only": BOOKING,
                "+ inbound departure delay": BOOKING + DAY_OF_DELAY,
                "+ hub weather": BOOKING + DAY_OF_WEATHER,
                "+ both": BOOKING + DAY_OF_DELAY + DAY_OF_WEATHER}
# Columns that describe how the inbound flight actually ended; none may be a feature.
OUTCOME_COLUMNS = {"arr_delay_min", "arr_hhmm", "actual_elapsed_min", "in_cancelled", "in_diverted", "missed", "y"}


def weather_sql(asos: str = ASOS) -> str:
    """One row per hub and local clock hour: did anything bad happen during that hour."""
    tz = " ".join(f"WHEN '{h}' THEN '{z}'" for h, z in TZ.items())
    return f"""
    SELECT station AS hub,
           date_trunc('hour', timezone(CASE station {tz} END, timezone('UTC', obs_utc))) AS hr,
           bool_or(thunder)::INT AS wx_thunder, bool_or(snow)::INT AS wx_snow, bool_or(freezing)::INT AS wx_freezing,
           bool_or(low_vis)::INT AS wx_low_vis, bool_or(high_wind)::INT AS wx_high_wind,
           min(vis_mi) AS wx_vis_min, greatest(max(wind_kt), max(gust_kt)) AS wx_wind_max,
           COALESCE(sum(precip_1h_in), 0) AS wx_precip
    FROM read_parquet('{asos}') GROUP BY ALL"""


def dayof_sql(feature_query: str, flights: str = FLIGHTS) -> str:
    """Attach the day-of information to booking-time features (which must carry the connection keys)."""
    return f"""
    WITH f AS ({feature_query}),
    inbound AS (SELECT carrier, flight_date, flight_number, crs_dep_hhmm, origin, dest,
                       min(dep_delay_min) AS dep_delay, min(crs_elapsed_min) AS elapsed, bool_or(cancelled) AS cancelled
                FROM read_parquet('{flights}') GROUP BY ALL),
    wx AS ({weather_sql()})
    SELECT f.*,
           -- what is observable 60 minutes before scheduled arrival, i.e. (scheduled flight time - 60) minutes after scheduled departure
           CASE WHEN i.dep_delay <= i.elapsed - 60 THEN greatest(least(i.dep_delay, 300), -30)
                ELSE greatest(i.elapsed - 60, 0) END AS in_dep_delay_known,
           (i.dep_delay > i.elapsed - 60)::INT AS in_not_departed,
           i.cancelled AS in_was_cancelled,
           w.wx_thunder, w.wx_snow, w.wx_freezing, w.wx_low_vis, w.wx_high_wind, w.wx_vis_min, w.wx_wind_max, w.wx_precip
    FROM f
    LEFT JOIN inbound i ON i.carrier = f.carrier AND i.flight_date = f.in_flight_date AND i.flight_number = f.in_flight_number
                       AND i.crs_dep_hhmm = f.in_crs_dep_hhmm AND i.origin = f.origin AND i.dest = f.hub
    LEFT JOIN wx w ON w.hub = f.hub AND w.hr = date_trunc('hour', f.in_sched_arr - INTERVAL 1 HOUR)"""


# ---- metrics -----------------------------------------------------------------------------------------

def capture_at(y, w, p, top: float) -> dict:
    """If we alert the `top` share of connections (by weight) with the highest P(miss): the share of all misses
    that are inside the alert, and the miss rate among the alerted (precision)."""
    y, w, p = (np.asarray(a, float) for a in (y, w, p))
    order = np.argsort(-p, kind="stable")
    cw = np.cumsum(w[order]) / w.sum()
    inside = order[cw <= top]
    caught = float((w[inside] * y[inside]).sum() / (w * y).sum())
    precision = float((w[inside] * y[inside]).sum() / w[inside].sum())
    return {"top_share": top, "misses_caught": caught, "precision": precision, "lift": caught / top}


def auc(y, w, p) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(np.asarray(y), np.asarray(p), sample_weight=np.asarray(w)))


# ---- the analysis --------------------------------------------------------------------------------------

def build_frame(window: str, n_rows: int):
    con = duckdb.connect()
    F.create_stats(con)                                   # route history from 2024, as for v1
    glob = (WEIGHTED / "mct=45" / "*" / "*.parquet").as_posix()
    src = f"read_parquet('{glob}')"
    (total,) = con.execute(f"SELECT count(*) FROM {src} WHERE {where(window)}").fetchone()
    q = F.feature_sql(src, where(window, "r.out_sched_dep"), min(1.0, n_rows / total), None, with_keys=True)
    df = con.execute(dayof_sql(q)).fetchdf()
    return df[df["in_was_cancelled"] != True].copy()      # noqa: E712  (cancelled inbound flights are excluded by design)


def cause_of_misses() -> dict:
    """What a miss is made of, on development data: inbound cancelled, inbound diverted, or arrived late."""
    con = duckdb.connect()
    glob = (WEIGHTED / "mct=45" / "*" / "*.parquet").as_posix()
    row = con.execute(f"""
      SELECT sum(weight * (in_cancelled)::INT), sum(weight * (in_diverted AND NOT in_cancelled)::INT),
             sum(weight * (NOT in_cancelled AND NOT in_diverted)::INT)
      FROM read_parquet('{glob}') WHERE missed AND {where('TRAIN')}""").fetchone()
    tot = sum(row)
    return {"inbound_cancelled": row[0] / tot, "inbound_diverted": row[1] / tot, "inbound_arrived_late": row[2] / tot}


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from mcp.model import brier, fit_gbm, log_loss, norm

    fit, valid = build_frame("FIT", 3_000_000), build_frame("VALID", 2_000_000)
    print(f"fit {len(fit):,} rows, evaluation {len(valid):,} rows (inbound cancellations excluded)", flush=True)
    for cols in FEATURE_SETS.values():
        assert not set(cols) & OUTCOME_COLUMNS, "an outcome column leaked into the features"
    res = {"alert_time": "one hour before the inbound flight's scheduled arrival", "rows": {"fit": len(fit), "eval": len(valid)},
           "causes_of_misses": cause_of_misses(), "sets": {}}
    y, w = valid["y"].to_numpy(), valid["weight"].to_numpy()
    for name, cols in FEATURE_SETS.items():
        print("fitting:", name, flush=True)
        g = fit_gbm(fit, use=cols, leaves=15)
        p = g(valid)
        res["sets"][name] = {"brier": brier(w, w * y, p), "log_loss": log_loss(w, w * y, p), "auc": auc(y, w, p),
                             "top5": capture_at(y, w, p, 0.05), "top10": capture_at(y, w, p, 0.10),
                             "observed_miss_rate": float((w * y).sum() / w.sum())}
    base = res["sets"]["booking time only"]
    for v in res["sets"].values():
        v["brier_improvement"] = 1 - v["brier"] / base["brier"]
        v["log_loss_improvement"] = 1 - v["log_loss"] / base["log_loss"]
    RESULTS.write_text(json.dumps(res, indent=2))

    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
                         "figure.dpi": 130, "font.size": 10})
    fig, ax = plt.subplots(1, 2, figsize=(10.4, 3.9))
    names = list(res["sets"])
    cols = ["#9ab", "#56B4E9", "#E69F00", "#0072B2"]
    ax[0].bar(range(len(names)), [res["sets"][n]["auc"] for n in names], color=cols)
    ax[0].set(xticks=range(len(names)), xticklabels=[n.replace(" ", "\n", 1) for n in names], ylabel="AUC (1 = perfect, 0.5 = chance)",
              title="How well each information set ranks risk", ylim=(0.5, max(res["sets"][n]["auc"] for n in names) + 0.04))
    ax[0].tick_params(axis="x", labelsize=7)
    ax[1].bar(range(len(names)), [res["sets"][n]["top5"]["misses_caught"] * 100 for n in names], color=cols)
    ax[1].set(xticks=range(len(names)), xticklabels=[n.replace(" ", "\n", 1) for n in names], ylabel="Share of all misses caught (%)",
              title="Alerting the riskiest 5% of connections")
    ax[1].tick_params(axis="x", labelsize=7)
    fig.tight_layout()
    fig.savefig(ROOT / "docs" / "figures" / "voi.png")
    print(json.dumps({"causes": res["causes_of_misses"], **{n: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items() if k in ("brier", "log_loss", "auc", "brier_improvement")} | {"top5_caught": round(s["top5"]["misses_caught"], 3), "top5_precision": round(s["top5"]["precision"], 3)} for n, s in res["sets"].items()}}, indent=1))


if __name__ == "__main__":
    main()
