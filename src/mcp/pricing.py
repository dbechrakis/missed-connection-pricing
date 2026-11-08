"""Severity, expected cost, price and the offer decision. Spec: Method 6-8.

    expected cost = P(miss) x (rebooking cost + overnight cost x overnight)
    price         = expected cost / target loss ratio
    offer         = price <= WTP cap x fare

`overnight` is whether the *next* scheduled same-carrier flight H->B leaves on a later date
and at least `min_overnight_wait_min` later, so the passenger needs a hotel. It is a property
of the schedule, known at booking, so the price can depend on it per connection. Where a
cell mixes connections, the price is the average of the per-connection prices.

Costs, loss ratio and the WTP cap are ASSUMPTIONS from config/pricing.yaml. Severity is a lower
bound: we cannot see seat availability on the next flight (spec: limits).

Run:  python -m mcp.pricing        (from src/)
"""
from __future__ import annotations

import json

import duckdb
import joblib
import numpy as np
import pandas as pd
import yaml

from mcp.connections import ROOT
from mcp.features import FLIGHTS, build
from mcp.ingest import HUBS
from mcp.model import BUCKET_MIN, N_BUCKETS, bucket_of, _codes

CONFIG = ROOT / "config" / "pricing.yaml"
SEVERITY = ROOT / "data" / "parquet" / "severity" / "severity.parquet"
MODEL = ROOT / "models" / "pmiss.joblib"
RESULTS = ROOT / "results"


def load_config(path=CONFIG) -> dict:
    return yaml.safe_load(path.read_text())["pricing"]


# ---- severity -------------------------------------------------------------------------------

def severity_sql(flights: str, min_wait: int, hubs=HUBS) -> str:
    """For every flight leaving a hub: minutes until the next scheduled same-carrier flight to
    the same destination, and whether that makes a missed connection an overnight.

    The next flight is the next *distinct* scheduled departure time strictly after this one
    (two flights at the same minute are not each other's fallback). Cancelled flights stay in
    the schedule: at booking time they were scheduled, and severity is a lower bound anyway.
    A flight with no later departure in the data (only the last days of 2025) counts as overnight.
    """
    hub_list = ", ".join(f"'{h}'" for h in hubs)
    return f"""
    WITH f AS (
      SELECT carrier, flight_date, flight_number, crs_dep_hhmm, origin, dest,
             flight_date::TIMESTAMP + to_minutes((crs_dep_hhmm // 100) * 60 + crs_dep_hhmm % 100) AS sched_dep
      FROM read_parquet('{flights}')
      WHERE origin IN ({hub_list}) AND crs_dep_hhmm IS NOT NULL
    ),
    nxt AS (
      SELECT carrier, origin, dest, sched_dep,
             lead(sched_dep) OVER (PARTITION BY carrier, origin, dest ORDER BY sched_dep) AS next_dep
      FROM (SELECT DISTINCT carrier, origin, dest, sched_dep FROM f)
    )
    SELECT f.carrier, f.flight_date, f.flight_number, f.crs_dep_hhmm,
           date_diff('minute', f.sched_dep, n.next_dep) AS wait_min,
           (n.next_dep IS NULL
            OR (n.next_dep::DATE > f.sched_dep::DATE
                AND date_diff('minute', f.sched_dep, n.next_dep) >= {min_wait})) AS overnight
    FROM f JOIN nxt n ON n.carrier = f.carrier AND n.origin = f.origin
                     AND n.dest = f.dest AND n.sched_dep = f.sched_dep
    """


def build_severity(cfg: dict | None = None, flights: str = FLIGHTS, out=SEVERITY) -> int:
    cfg = cfg or load_config()
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"COPY ({severity_sql(flights, cfg['min_overnight_wait_min'])}) TO '{out.as_posix()}' "
                f"(FORMAT parquet, COMPRESSION zstd)")
    (n,) = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()
    return n


# ---- price and decision ---------------------------------------------------------------------

def expected_cost(p, overnight, cfg: dict):
    """Expected claim cost per protected connection."""
    return np.asarray(p) * (cfg["rebooking_cost"] + cfg["overnight_cost"] * np.asarray(overnight))


def price(p, overnight, cfg: dict):
    """Premium that would run at the target loss ratio if p were exactly right."""
    return expected_cost(p, overnight, cfg) / cfg["target_loss_ratio"]


def offer(prices, fares, cfg: dict):
    """Offer protection only while it costs no more than the WTP cap share of the fare."""
    return np.asarray(prices) <= cfg["wtp_cap_pct"] * np.asarray(fares)


# ---- scoring and the price table --------------------------------------------------------------

def score(df: pd.DataFrame, bundle: dict) -> np.ndarray:
    """Calibrated P(miss) for rows with the model's feature columns."""
    use = bundle["features"]
    raw = bundle["gbm"].predict_proba(_codes(df[use], bundle["cats"]))[:, 1]
    return bundle["isotonic"].predict(raw)


def cutoffs(df: pd.DataFrame, cfg: dict, share: float = 0.5) -> dict:
    """Per hub, the shortest slack bucket from which at least `share` of (weighted) connections
    are offerable and stay offerable at every longer slack. Below it, 'do not sell'."""
    out = {}
    for hub, g in df.assign(offer=offer(price(df["p"], df["overnight"], cfg), df["fare"], cfg)).groupby("hub"):
        rate = g.groupby("bucket").apply(lambda x: np.average(x["offer"], weights=x["weight"]), include_groups=False)
        ok = rate >= share
        # the lowest bucket such that it and all longer buckets pass
        passing = [b for b in rate.index if ok[rate.index >= b].all()]
        out[hub] = int(45 + BUCKET_MIN * min(passing)) if passing else None
    return out


def main() -> None:
    cfg = load_config()
    print(f"severity rows: {build_severity(cfg):,}")
    build("TRAIN", 6_000_000, name="PRICING_TRAIN", severity=SEVERITY.as_posix())
    from mcp.features import OUT
    df = pd.read_parquet(OUT / "PRICING_TRAIN.parquet")
    bundle = joblib.load(MODEL)
    df["p"] = score(df, bundle)
    df["bucket"] = bucket_of(df["slack_min"])
    df["price"] = price(df["p"], df["overnight"], cfg)
    df["offer"] = offer(df["price"], df["fare"], cfg)
    w = df["weight"]

    summary = {
        "rows": len(df), "mean_p": float(np.average(df["p"], weights=w)), "observed": float(np.average(df["y"], weights=w)),
        "overnight_share_all": float(np.average(df["overnight"], weights=w)),
        "overnight_share_if_missed": float(np.average(df["overnight"], weights=w * df["y"])),
        "wait_min_median_if_missed": float(df.loc[df["y"] == 1, "wait_min"].median()),
        "mean_price": float(np.average(df["price"], weights=w)),
        "mean_fare": float(np.average(df["fare"], weights=w)),
        "offer_rate": float(np.average(df["offer"], weights=w)),
        "cutoff_min_slack_by_hub": cutoffs(df, cfg),
    }

    # Price table: hub x slack bucket x carrier x month. Month only enters through the schedule mix
    # (the model has no month feature), which is stated honestly in the README.
    grp = df.assign(wp=df["price"] * w, wf=df["fare"] * w, wo=df["overnight"] * w, wpm=df["p"] * w,
                    wof=df["offer"].astype(float) * w).groupby(["hub", "carrier", "bucket", "month"])
    t = grp.agg(weight=("weight", "sum"), n=("y", "size"), wp=("wp", "sum"), wf=("wf", "sum"),
                wo=("wo", "sum"), wpm=("wpm", "sum"), wof=("wof", "sum")).reset_index()
    t = t[t["n"] >= 30].assign(slack_from_min=lambda x: 45 + BUCKET_MIN * x["bucket"],
                               p_miss=lambda x: x["wpm"] / x["weight"], price=lambda x: x["wp"] / x["weight"],
                               fare=lambda x: x["wf"] / x["weight"], p_overnight=lambda x: x["wo"] / x["weight"],
                               offer_share=lambda x: x["wof"] / x["weight"])
    t = t[["hub", "carrier", "month", "slack_from_min", "p_miss", "p_overnight", "price", "fare", "offer_share", "n"]]
    RESULTS.mkdir(exist_ok=True)
    t.round(4).to_csv(RESULTS / "price_table.csv", index=False)

    # Sensitivity of the decision rule: vary one assumption at a time (others at default).
    sens = {}
    for key, values in cfg["sensitivity"].items():
        for v in values:
            c = {**cfg, key: v}
            sens[f"{key}={v}"] = {"offer_rate": float(np.average(offer(price(df["p"], df["overnight"], c), df["fare"], c), weights=w)),
                                  "cutoff_min_slack_by_hub": cutoffs(df, c)}
    (RESULTS / "pricing.json").write_text(json.dumps({"config": cfg, "summary": summary, "sensitivity": sens}, indent=2))
    print(json.dumps(summary, indent=1))
    for k, v in sens.items():
        print(f"{k:22s} offer {v['offer_rate']:.1%}  cutoffs {v['cutoff_min_slack_by_hub']}")


if __name__ == "__main__":
    main()
