"""v3: overnight gap cover on marketing-network connections, with sourced costs. Run with MCP_VARIANT=v3.

What changed from v1/v2, and why (docs/decisions.md, VALIDATION.md Part 5):
  population  connections within the same MARKETING network (how tickets are sold), not the reporting airline
  product     PARAMETRIC OVERNIGHT GAP COVER: pays the GSA hotel + meals rate for the hub and month when a connection
              is missed, the next flight to the destination is the next day, and BTS does NOT code the inbound
              problem to the airline. Airlines already cover hotels for disruptions they cause (DOT dashboard), so
              this pays only in the gap, and every condition can be checked from public data.
  label       y_gap = missed AND inbound cause is not 'carrier' (strict, checkable reading)
  cost        GSA lodging (hub ZIP, month) + M&IE, instead of an invented $180
  selection   the v2 rule (pooled log loss, ties to the simpler policy), candidates incl. per-hub calibration,
              evaluated walk-forward WITH a one-month booking lag, because that is how it would run

    MCP_VARIANT=v3 python -m mcp.v3 select      walk-forward selection on Oct 2025 to Aug 2026 (development data)
    MCP_VARIANT=v3 python -m mcp.v3 fit         final GBMs (gap and any-miss) on Jan 2024 to Feb 2026, calibration
                                                statistics on Mar to Aug 2026, saved for the pre-registered test
"""
from __future__ import annotations

import json
import sys

import duckdb
import joblib
import numpy as np
import pandas as pd

from mcp import features as F
from mcp.calibration import known_months, make_calibrator, month_stats
from mcp.causes import inbound_cause_sql
from mcp.connections import ROOT, WEIGHTED
from mcp.costs import RESULTS as GSA_RESULTS
from mcp.costs import overnight_cost
from mcp.model import EPS, fit_gbm
from mcp.pricing import SEVERITY
from mcp.split import where
from mcp.v2 import CANDIDATES, FEATURE_SETS, LEAVES, SIMPLICITY, TOLERANCE
from mcp.variant import MARKETING

SEVERITY_FULL = SEVERITY.with_name("severity_full_v3.parquet")
# Development files. From September 2026 on, files in year=2026 belong to the pre-registered NEXT window: they are
# excluded not by this glob but by every predicate used with it (V3_SFIT and V3_FIT end before March 2026, and scored
# months are named explicitly up to August 2026). tests/test_v3.py checks the module never names the NEXT window.
DEV_GLOB = (WEIGHTED / "mct=45" / "year=202[456]" / "*.parquet").as_posix()
SELECTION = ROOT / "results" / "v3_selection.json"
DEV_RESULTS = ROOT / "results" / "v3_dev.json"
BUNDLE = ROOT / "models" / "pmiss_v3.joblib"
STATE = ROOT / "models" / "v3_state.json"
LAG = 1                          # booking lead: month m is priced from months up to m-2
SEL_ROWS, EVAL_FRAC = 5_000_000, 0.10
FIRST_OOS = "2025-07"            # first month after V3_SFIT: calibrators may use months from here on
TARGET_LR = 0.65


def gsa_table() -> dict:
    raw = json.loads(GSA_RESULTS.read_text())["rates"]
    return {h: {int(fy): {**p, "lodging": {int(m): v for m, v in p["lodging"].items()}} for fy, p in v.items()} for h, v in raw.items()}


def claim_cost(df: pd.DataFrame, table: dict) -> np.ndarray:
    """The gap cover's payout if a claim is triggered: GSA lodging + M&IE for the hub and month, only for connections
    whose next flight is the next day (no overnight, no payout)."""
    ym = df["out_sched_dep"]
    cost = np.array([overnight_cost(table, h, y, m) for h, y, m in zip(df["hub"], ym.dt.year, ym.dt.month)])
    return cost * df["overnight"].to_numpy()


def gap_label_sql(feature_query: str, flights: str | None = None) -> str:
    """Add the inbound cause and the gap label to any feature query that carries the connection keys:
    y_gap = 1 when the connection was missed AND BTS does not code the inbound problem to the airline."""
    ic = inbound_cause_sql(flights) if flights else inbound_cause_sql()
    return f"""
    WITH f AS ({feature_query}), ic AS ({ic})
    SELECT f.*, COALESCE(ic.cause, 'unattributed') AS cause,
           (f.y = 1 AND COALESCE(ic.cause, 'unattributed') <> 'carrier')::INT AS y_gap
    FROM f LEFT JOIN ic ON ic.carrier = f.carrier AND ic.flight_date = f.in_flight_date AND ic.flight_number = f.in_flight_number
                       AND ic.crs_dep_hhmm = f.in_crs_dep_hhmm AND ic.origin = f.origin AND ic.dest = f.hub"""


def frame_sql(source: str, predicate: str, frac: float) -> str:
    """Booking-time features + the gap label + severity for connections in `source`."""
    return gap_label_sql(F.feature_sql(source, predicate, frac, SEVERITY_FULL.as_posix(), with_keys=True))


def month_file(y: int, m: int) -> str:
    return (WEIGHTED / "mct=45" / f"year={y}" / f"month={m:02d}.parquet").as_posix()


def month_predicate(y: int, m: int) -> str:
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"(r.out_sched_dep >= TIMESTAMP '{y}-{m:02d}-01' AND r.out_sched_dep < TIMESTAMP '{ny}-{nm:02d}-01')"


def labels(start: str, end: str):
    y, m = int(start[:4]), int(start[5:])
    while f"{y}-{m:02d}" <= end:
        yield y, m, f"{y}-{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def pick(rows: list[dict]) -> dict:
    """The v2 rule, unchanged: lowest pooled log loss; within TOLERANCE, the simpler policy, then the longer window."""
    best = min(r["log_loss"] for r in rows)
    tied = [r for r in rows if r["log_loss"] <= best + TOLERANCE]
    return min(tied, key=lambda r: (SIMPLICITY[r["policy"]], -r["k"], r["log_loss"]))


def walk_forward(months: dict, stats: list, eval_labels: list[str], label: str = "y_gap", lag: int = LAG) -> list[dict]:
    """Each evaluation month priced with a calibrator from months known `lag` months before it; pooled scores.
    Also the realized/target ratio of the gap cover (claims over expected claims, cost-weighted, overnight rows only)."""
    out = []
    for policy, k in CANDIDATES:
        w_tot = ll = brier = claims = expected = 0.0
        hub_ce: dict = {}
        for mo in eval_labels:
            df = months[mo]
            cal = make_calibrator(policy, k, known_months(stats, mo, lag))
            p = cal(df["p"].to_numpy(), df["hub"].to_numpy())
            y, w, c = df[label].to_numpy(), df["weight"].to_numpy(), df["claim_cost"].to_numpy()
            pc = np.clip(p, EPS, 1 - EPS)
            w_tot += w.sum()
            ll += float(-np.sum(w * (y * np.log(pc) + (1 - y) * np.log(1 - pc))))
            brier += float(np.sum(w * (y - p) ** 2))
            claims += float(np.sum(w * y * c))
            expected += float(np.sum(w * p * c))
            for h in np.unique(df["hub"]):
                mk = (df["hub"] == h).to_numpy()
                a = hub_ce.get(h, [0.0, 0.0])
                hub_ce[h] = [a[0] + float(np.sum((w * y * c)[mk])), a[1] + float(np.sum((w * p * c)[mk]))]
        out.append({"policy": policy, "k": k, "log_loss": ll / w_tot, "brier": brier / w_tot,
                    "realized_over_target": claims / expected if expected else float("nan"),
                    "by_hub": {h: v[0] / v[1] for h, v in hub_ce.items() if v[1]}})
    return out


def _score_months(con, g, start: str, end: str, table: dict) -> dict:
    months = {}
    for y, m, lab in labels(start, end):
        df = con.execute(frame_sql(f"read_parquet('{month_file(y, m)}')", month_predicate(y, m), EVAL_FRAC)).fetchdf()
        df = df[df["overnight"].notna() & df["fare"].notna()].copy()
        df["p"] = g(df)
        df["claim_cost"] = claim_cost(df, table)
        months[lab] = df
    return months


def run_selection() -> dict:
    assert MARKETING, "run with MCP_VARIANT=v3"
    table = gsa_table()
    con = duckdb.connect()
    F.create_stats(con, fit_flights=where("V3_SFIT", "flight_date"), fit_asos=where("V3_SFIT", "obs_utc"))
    src = f"read_parquet('{DEV_GLOB}')"
    (total,) = con.execute(f"SELECT count(*) FROM {src} WHERE {where('V3_SFIT')}").fetchone()
    fit = con.execute(frame_sql(src, where("V3_SFIT", "r.out_sched_dep"), min(1.0, SEL_ROWS / total))).fetchdf()
    print(f"V3_SFIT: {len(fit):,} rows; gap-miss rate {np.average(fit['y_gap'], weights=fit['weight']):.2%}, "
          f"any-miss rate {np.average(fit['y'], weights=fit['weight']):.2%}", flush=True)
    eval_labels = [lab for _, _, lab in labels("2025-10", "2026-08")]
    rows = []
    for name, use in FEATURE_SETS.items():
        print(f"fitting gap model: {name} ...", flush=True)
        g = fit_gbm(fit.assign(y=fit["y_gap"]), use=use, leaves=LEAVES)
        months = _score_months(con, g, FIRST_OOS, "2026-08", table)
        stats = [month_stats(lab, df["hub"], df["y_gap"], df["weight"], df["p"]) for lab, df in months.items()]
        for r in walk_forward(months, stats, eval_labels):
            rows.append({**r, "features": name})
    chosen = pick(rows)
    SELECTION.write_text(json.dumps({"rule": "lowest pooled log loss of the gap label, walk-forward Oct 2025 to Aug 2026, one-month lag; "
                                             "within 0.0002, the simpler policy then the longer window",
                                     "candidates": rows, "chosen": chosen}, indent=2))
    print("\nwalk-forward Oct 2025 to Aug 2026, gap label, one-month lag (lower log loss is better)")
    for r in sorted(rows, key=lambda r: r["log_loss"])[:12]:
        print(f"  {r['features']:15s} {r['policy']:13s} k={r['k']}  logloss {r['log_loss']:.5f}  brier {r['brier']:.5f}  "
              f"realized/target {r['realized_over_target']:.3f}" + ("  <- chosen" if r is chosen else ""))
    return chosen


def fit_final(chosen: dict) -> None:
    assert MARKETING, "run with MCP_VARIANT=v3"
    table = gsa_table()
    con = duckdb.connect()
    F.create_stats(con, fit_flights=where("V3_FIT", "flight_date"), fit_asos=where("V3_FIT", "obs_utc"))
    src = f"read_parquet('{DEV_GLOB}')"
    (total,) = con.execute(f"SELECT count(*) FROM {src} WHERE {where('V3_FIT')}").fetchone()
    fit = con.execute(frame_sql(src, where("V3_FIT", "r.out_sched_dep"), min(1.0, SEL_ROWS / total))).fetchdf()
    use = FEATURE_SETS[chosen["features"]]
    print(f"V3_FIT: {len(fit):,} rows; fitting gap and any-miss models ({chosen['features']}) ...", flush=True)
    g_gap = fit_gbm(fit.assign(y=fit["y_gap"]), use=use, leaves=LEAVES)
    g_any = fit_gbm(fit, use=use, leaves=LEAVES)
    # a data-derived probability floor, as in v1: the observed gap-miss rate of the 2% lowest raw predictions
    raw = g_gap(fit)
    low = raw <= np.quantile(raw, 0.02)
    floor = float(np.average(fit["y_gap"][low], weights=fit["weight"][low]))
    months = _score_months(con, g_gap, "2026-03", "2026-08", table)
    cal_stats = [month_stats(lab, df["hub"], df["y_gap"], df["weight"], df["p"]) for lab, df in months.items()]
    joblib.dump({"gbm_gap": g_gap.model, "gbm_any": g_any.model, "cats": g_gap.cats, "features": g_gap.use,
                 "policy": chosen["policy"], "k": chosen["k"], "lag": LAG, "cal_stats": cal_stats, "floor": floor,
                 "feature_set": chosen["features"], "leaves": LEAVES, "target_loss_ratio": TARGET_LR}, BUNDLE)
    from mcp.monitor import save_state
    save_state(cal_stats, STATE)
    print(f"saved {BUNDLE.name} and {STATE.name}; probability floor {floor:.4f}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "select"
    if mode == "select":
        run_selection()
    elif mode == "fit":
        fit_final(json.loads(SELECTION.read_text())["chosen"])
