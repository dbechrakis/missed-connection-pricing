"""Build the data file for the static demo (site/prices.js).

The demo is the frozen v1 model: month-free by construction (v1 has no seasonal term) and validated on
the clean 2026 holdout. Every number on the page comes from this file, which is built from the project's
own results, so nothing on the page is typed by hand.

Per (hub, carrier, 15-minute slack bucket) it stores passenger-weighted means over the development
connections: P(miss), the fare, and for three cases (the next flight is "typical", same day, next day)
the price and the share of connections that are offerable under the willingness-to-pay cap.

Run:  python -m mcp.demo        (from src/)
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd

from mcp.connections import ROOT
from mcp.features import OUT
from mcp.model import BUCKET_MIN, N_BUCKETS, bucket_of
from mcp.pricing import MODEL, load_config, load_guards, score

SITE = ROOT / "site"
MIN_CELL_ROWS = 100          # fewer sampled connections than this: the cell is omitted, the page falls back
MIN_CARRIER_ROWS = 3000      # a carrier needs this many sampled connections at a hub to be listed


def build_cells(df: pd.DataFrame, cfg: dict, guards: dict) -> list[dict]:
    """Weighted cell means for the page. `df` needs hub, carrier, slack_min, p, overnight, fare, weight."""
    p = np.maximum(df["p"].to_numpy(), guards["min_p_miss"])
    lr, cap = cfg["target_loss_ratio"], cfg["wtp_cap_pct"]
    fare = df["fare"].to_numpy()
    cost_same, cost_next = cfg["rebooking_cost"], cfg["rebooking_cost"] + cfg["overnight_cost"]
    cost_typ = cfg["rebooking_cost"] + cfg["overnight_cost"] * df["overnight"].to_numpy()
    price = {"typical": p * cost_typ / lr, "same": p * cost_same / lr, "next": p * cost_next / lr}
    d = pd.DataFrame({"hub": df["hub"].to_numpy(), "carrier": df["carrier"].to_numpy(),
                      "bucket": bucket_of(df["slack_min"]), "w": df["weight"].to_numpy(),
                      "p": df["p"].to_numpy(), "fare": fare, "ov": df["overnight"].to_numpy()})
    for k, v in price.items():
        d[f"price_{k}"] = v
        d[f"offer_{k}"] = (v <= cap * fare).astype(float)
    cols = ["p", "fare", "ov"] + [f"{a}_{k}" for k in price for a in ("price", "offer")]

    def agg(g):
        w = g["w"].to_numpy()
        out = {c: float(np.average(g[c], weights=w)) for c in cols}
        out["n"] = int(len(g))
        return pd.Series(out)

    rows = []
    for carrier_label, frame in (("ALL", d), *[(c, g) for c, g in d.groupby("carrier")]):
        grouped = frame.groupby(["hub", "bucket"]) if carrier_label == "ALL" else frame.groupby(["hub", "bucket"])
        for (hub, b), g in grouped:
            if len(g) < MIN_CELL_ROWS:
                continue
            r = agg(g).to_dict()
            r.update(hub=hub, carrier=carrier_label, slack=int(45 + BUCKET_MIN * b))
            rows.append(r)
    # keep a carrier only if it has enough connections at that hub overall
    big = d.groupby(["hub", "carrier"]).size()
    keep = {(h, c) for (h, c), n in big.items() if n >= MIN_CARRIER_ROWS}
    return [r for r in rows if r["carrier"] == "ALL" or (r["hub"], r["carrier"]) in keep]


def validation_block() -> dict:
    h = json.loads((ROOT / "results" / "holdout.json").read_text())
    b = json.loads((ROOT / "results" / "backtest.json").read_text())
    cfg = load_config()
    lr = cfg["target_loss_ratio"]

    def ratio(x):
        return {"loss_ratio": x["ratio"] * lr, "lo": x["lo"] * lr, "hi": x["hi"] * lr}

    return {
        "holdout": {"window": "Jan to Aug 2026", "connections": h["rows"]["scored"],
                    "observed_miss": h["scores"]["v1_iso"]["observed"],
                    "baseline": ratio(h["overall"]["baseline"]["0"]), "v1": ratio(h["overall"]["v1_iso"]["0"]),
                    "v2_rolling": ratio(h["overall"]["v2_rolling"]["0"]),
                    "by_hub_v1": {hub: v["v1_iso"]["ratio"] for hub, v in h["by_hub"].items()},
                    "v1_level": {"predicted": h["scores"]["v1_iso"]["mean_pred"], "observed": h["scores"]["v1_iso"]["observed"]},
                    "flat_theta0": h["flat_pricing"]["flat_train"]["0"]["ratio"],
                    "flat_theta1": h["flat_pricing"]["flat_train"]["1"]["ratio"],
                    "tiered_theta1": h["overall"]["v1_iso"]["1"]["ratio"]},
        "h2_2025": {"connections": b["rows"]["scored"], "v1": ratio(b["overall"]["gbm_iso"]["0"])},
        "target": lr,
    }


def main() -> None:
    cfg, guards = load_config(), load_guards()
    df = pd.read_parquet(OUT / "PRICING_TRAIN.parquet")
    df["p"] = score(df, joblib.load(MODEL))
    cells = build_cells(df, cfg, guards)
    payload = {
        "assumptions": {"rebooking_cost": cfg["rebooking_cost"], "overnight_cost": cfg["overnight_cost"],
                        "target_loss_ratio": cfg["target_loss_ratio"], "wtp_cap_pct": cfg["wtp_cap_pct"],
                        "min_p_miss": guards["min_p_miss"]},
        "validation": validation_block(),
        "hubs": sorted({c["hub"] for c in cells}),
        "carriers": {h: sorted({c["carrier"] for c in cells if c["hub"] == h and c["carrier"] != "ALL"})
                     for h in sorted({c["hub"] for c in cells})},
        "buckets": [45 + BUCKET_MIN * i for i in range(N_BUCKETS)],
        "cells": [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in c.items()} for c in cells],
    }
    SITE.mkdir(exist_ok=True)
    (SITE / "prices.js").write_text("window.PRICES = " + json.dumps(payload, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"{len(cells)} cells, {sum(len(v) for v in payload['carriers'].values())} hub-carrier pairs, "
          f"{(SITE / 'prices.js').stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
