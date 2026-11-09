"""How much do the results depend on which connections travellers actually book?

The connections here are every scheduled same-airline pairing at a hub, each weighted by the route's real passenger count
split evenly over the route's pairings in a month. Real travellers do not choose evenly: published work on airline booking
data finds that some choose a longer connection voluntarily and value connections close to the minimum less (Theis, MIT
thesis, 2011), and booking systems show short connections first. Public data does not say how they choose, so this module
does not guess one answer. It re-weights the same connections under a range of stylised mixes and reports how far each
headline moves:

    equal            as modelled: every pairing of a route counts the same
    prefer_short_60  weight falls with the buffer above the minimum, e^(-buffer/60): short connections are booked more
    prefer_short_30  the same, steeper (e^(-buffer/30))
    avoid_minimum    connections within 15 minutes of the minimum are booked half as often (Theis's finding, stylised)
    prefer_long_60   weight rises with the buffer, e^(+buffer/60): the opposite stress

The aim is a range for each headline, not a better point estimate. If a conclusion survives every mix it does not depend on
the one the data cannot tell us.

    cd src && MCP_VARIANT=v3 python -m mcp.v3_mix        # needs `python -m mcp.v3_rolling rows`; writes results/v3_mix.json
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from mcp.connections import ROOT
from mcp.v3 import TARGET_LR, TRAINED_MCT
from mcp.v3_loading import load_months, measure

RESULTS = ROOT / "results" / "v3_mix.json"
SCENARIOS = ("equal", "prefer_short_60", "prefer_short_30", "avoid_minimum", "prefer_long_60")


def mix_factor(buffer: np.ndarray, scenario: str) -> np.ndarray:
    """Relative booking weight of a connection with `buffer` minutes above the minimum."""
    b = np.asarray(buffer, float)
    if scenario == "equal":
        return np.ones_like(b)
    if scenario == "prefer_short_60":
        return np.exp(-b / 60.0)
    if scenario == "prefer_short_30":
        return np.exp(-b / 30.0)
    if scenario == "avoid_minimum":
        return np.where(b < 15, 0.5, 1.0)
    if scenario == "prefer_long_60":
        return np.exp(b / 60.0)
    raise ValueError(scenario)


def reweight(df: pd.DataFrame, scenario: str, mct: int = TRAINED_MCT) -> pd.DataFrame:
    return df.assign(weight=df["weight"] * mix_factor(df["slack_min"] - mct, scenario))


def summarise(months: dict, scenario: str) -> dict:
    d = pd.concat([reweight(m, scenario) for m in months.values()], ignore_index=True)
    allr = measure(d, 1.0)
    # all overnight-risk connections: realized/expected with no cap
    exp = float((d["weight"] * d["p"] * d["claim_cost"]).sum())
    claims = float((d["weight"] * d["y_gap"] * d["claim_cost"]).sum())
    per_month = {}
    for lab, m in months.items():
        mm = measure(reweight(m, scenario), 1.0)
        per_month[lab] = mm["loss_ratio"]
    lr = np.array(list(per_month.values()))
    return {"all_ratio": claims / exp, "all_loss_ratio": TARGET_LR * claims / exp, "sold_ratio": allr["ratio"], "sold_loss_ratio": allr["loss_ratio"],
            "share_sold": allr["share_sold"], "months_sold_loss_above_100": int((lr > 1).sum()), "months": int(len(lr)),
            "mean_slack": float(np.average(d["slack_min"], weights=d["weight"]))}


def main() -> None:
    months = load_months()
    out = {"window": f"{min(months)} to {max(months)}", "status": "development; stylised mixes, not estimates of how travellers choose",
           "scenarios": {s: summarise(months, s) for s in SCENARIOS}}
    sold = [v["sold_loss_ratio"] for v in out["scenarios"].values()]
    allr = [v["all_loss_ratio"] for v in out["scenarios"].values()]
    out["range"] = {"sold_loss_ratio": [min(sold), max(sold)], "all_loss_ratio": [min(allr), max(allr)],
                    "sold_above_target_in_every_scenario": bool(all(x > TARGET_LR for x in sold))}
    RESULTS.write_text(json.dumps(out, indent=1))
    for s, v in out["scenarios"].items():
        print(f"{s:16s} all {v['all_loss_ratio']:.1%}  sold {v['sold_loss_ratio']:.1%}  share sold {v['share_sold']:.1%}  mean gap {v['mean_slack']:.0f} min  months sold >100%: {v['months_sold_loss_above_100']}/{v['months']}")


if __name__ == "__main__":
    main()
