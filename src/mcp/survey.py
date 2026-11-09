"""A stated-demand survey for the gap cover: a price ladder, and the analysis written before any respondent answers.

The pricing experiment (`mcp.demand`) needs a live product and real traffic. A survey needs neither, so it can give a first,
cheap read of demand within weeks: each respondent is shown a described connection and the cover at several prices, set as
multiples of the model price for that connection, and says whether they would buy. This module analyses the answers.

What a survey can and cannot say. Stated intent overstates purchase (the hypothetical-bias problem), so the instrument records
how sure the answer is and the analysis reports two curves: "definitely" only (a lower bound on stated demand) and "definitely or
probably" (an upper bound). Neither is the attach rate. The experiment measures the link between them; until then the stated
share is an order-of-magnitude check on the economics, not a forecast.

    from mcp.survey import demand_curve, elasticity, simulate_survey
    curve = demand_curve(df, level="definitely")       # df: one row per respondent x price shown
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LADDER = (0.5, 0.8, 1.0, 1.25, 1.5, 2.0)          # multiples of the model price, shown in a random order to each respondent
LEVELS = {"definitely": {"definitely"}, "any": {"definitely", "probably"}}


def sample_size_share(margin: float = 0.05, p: float = 0.5, z: float = 1.96) -> int:
    """Respondents needed to know a share to within +-`margin` (the worst case is p = 0.5: 385 for +-5 points)."""
    return int(np.ceil(z * z * p * (1 - p) / (margin * margin)))


def pava_decreasing(y: np.ndarray, w: np.ndarray | None = None) -> np.ndarray:
    """Pool-adjacent-violators: the closest non-increasing sequence to `y` (a demand curve cannot rise with price)."""
    y = np.asarray(y, float)
    w = np.ones_like(y) if w is None else np.asarray(w, float)
    blocks = [[v, wt, 1] for v, wt in zip(y, w)]
    out: list[list[float]] = []
    for b in blocks:
        out.append(b)
        while len(out) > 1 and out[-2][0] < out[-1][0]:             # a rise: merge the two blocks into their weighted mean
            v2, w2, n2 = out.pop()
            v1, w1, n1 = out.pop()
            out.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, n1 + n2])
    return np.concatenate([[v] * int(n) for v, _, n in out])


def share_yes(df: pd.DataFrame, level: str) -> pd.Series:
    yes = df["answer"].isin(LEVELS[level])
    return yes.groupby(df["mult"]).mean().sort_index()


def demand_curve(df: pd.DataFrame, level: str = "definitely", n_boot: int = 400, seed: int = 0) -> dict:
    """Share who would buy at each price multiple, made non-increasing, with a 95% interval from resampling respondents (so a
    respondent's several answers stay together)."""
    ids = df["respondent"].unique()
    by = {i: g for i, g in df.groupby("respondent")}
    pt = share_yes(df, level)
    mults = pt.index.to_numpy()
    mono = pava_decreasing(pt.to_numpy())
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        s = pd.concat([by[i] for i in rng.choice(ids, len(ids))], ignore_index=True)
        boots.append(pava_decreasing(share_yes(s, level).reindex(mults).fillna(0.0).to_numpy()))
    lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
    return {"level": level, "respondents": int(len(ids)), "mult": [float(m) for m in mults], "share": [float(x) for x in mono], "lo": [float(x) for x in lo],
            "hi": [float(x) for x in hi], "raw_share": [float(x) for x in pt.to_numpy()], "revenue_index": [float(m * s) for m, s in zip(mults, mono)]}


def elasticity(curve: dict) -> float:
    """Slope of log share on log price multiple over the points with a positive share: about the price elasticity of stated demand."""
    m, s = np.array(curve["mult"]), np.array(curve["share"])
    keep = s > 0
    if keep.sum() < 2:                      # nobody (or almost nobody) says yes: the slope cannot be estimated, and the cover is ruled out anyway
        return float("nan")
    return float(np.polyfit(np.log(m[keep]), np.log(s[keep]), 1)[0])


def share_at(curve: dict, mult: float = 1.0) -> dict:
    i = curve["mult"].index(mult)
    return {"share": curve["share"][i], "lo": curve["lo"][i], "hi": curve["hi"][i]}


def simulate_survey(n: int, seed: int = 0, median_wtp: float = 0.9, sigma: float = 0.7, sure_share: float = 0.5, noise: float = 0.0) -> pd.DataFrame:
    """Respondents with planted willingness to pay (log-normal around `median_wtp` times the model price). A respondent says yes at
    every price up to their willingness to pay; `sure_share` of them say "definitely" and the rest "probably". `noise` flips a
    fraction of answers, as inattentive respondents would."""
    rng = np.random.default_rng(seed)
    wtp = median_wtp * np.exp(sigma * rng.normal(size=n))
    sure = rng.uniform(size=n) < sure_share
    rows = []
    for i in range(n):
        for m in rng.permutation(LADDER):
            yes = wtp[i] >= m
            if rng.uniform() < noise:
                yes = not yes
            rows.append((i, float(m), ("definitely" if sure[i] else "probably") if yes else "no"))
    return pd.DataFrame(rows, columns=["respondent", "mult", "answer"])


def true_demand(mult: float, median_wtp: float = 0.9, sigma: float = 0.7, sure_share: float = 0.5, level: str = "any") -> float:
    """The planted answer: the share whose willingness to pay is at least `mult` (times `sure_share` for the 'definitely' curve)."""
    from math import erf, log, sqrt
    z = (log(mult) - log(median_wtp)) / sigma
    s = 0.5 * (1 - erf(z / sqrt(2)))
    return s if level == "any" else s * sure_share


# ---- the question bank, the pre-specified cleaning, and the analysis of a real export ------------------------------------------

SCENARIOS = (("ATL", 105), ("ORD", 120), ("DFW", 135), ("DEN", 105), ("CLT", 150), ("ATL", 150))     # fixed in docs/survey-instrument.md
HUB_NAMES = {"ATL": "Atlanta", "ORD": "Chicago O'Hare", "DFW": "Dallas-Fort Worth", "DEN": "Denver", "CLT": "Charlotte"}
WORDINGS = {
    "benefit": "Imagine you could add protection to this trip. If you miss your connection and the delay is not the airline's responsibility, you get ${payout} toward a hotel and meals.",
    "outcome": "Imagine you could add protection to this trip. If a delay leaves you stuck overnight at {airport} and the airline will not pay for your hotel, you are covered for ${payout}.",
}
QUESTION = "Would you buy this protection for this trip at ${price}?"
ANSWERS = ("Definitely would", "Probably would", "Probably would not", "Definitely would not")
ANSWER_CODE = {"Definitely would": "definitely", "Probably would": "probably", "Probably would not": "no", "Definitely would not": "no"}
MIN_TIME_FRACTION = 1 / 3                       # respondents faster than this share of the median completion time are dropped
DECISION_SCENARIOS = (0.01, 0.03, 0.10)          # attach rates the cover might need (docs/experiment-plan.md); each is reported, none is chosen afterwards


def question_bank(payload: dict, month: str = "2027-01") -> list[dict]:
    """Every question a respondent can be shown: 6 connections x 2 wordings x 6 price multiples, with the price in dollars. `payload` is the
    demo's price table (site/prices_v3.js). The model price is chance of a gap night x the government hotel-and-meals rate / 0.65."""
    rows = []
    cells = {(c["hub"], c["slack"]): c for c in payload["cells"]}
    for sid, (hub, slack) in enumerate(SCENARIOS, start=1):
        c = cells[(hub, slack)]
        cost = c["months"][month]["cost"]
        model_price = c["p"] * cost / payload["assumptions"]["target_loss_ratio"]
        for wording, text in WORDINGS.items():
            for mult in LADDER:
                price = round(model_price * mult)
                rows.append({"scenario": sid, "hub": hub, "scheduled_gap_min": slack, "fare": round(c["fare"]), "payout": round(cost), "model_price": round(model_price, 2),
                             "wording": wording, "mult": mult, "price": price,
                             "description": text.format(payout=round(cost), airport=HUB_NAMES[hub]), "question": QUESTION.format(price=price)})
    return rows


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """The exclusions fixed before fielding: fail the attention check, or finish faster than a third of the median time. Nothing else is
    dropped. `df` has one row per respondent x price with columns respondent, answer, mult, attention_ok, seconds."""
    per = df.groupby("respondent").agg(attention_ok=("attention_ok", "first"), seconds=("seconds", "first"))
    median = float(per["seconds"].median())
    failed = ~per["attention_ok"].astype(bool)
    fast = per["seconds"] < MIN_TIME_FRACTION * median
    drop = per.index[failed | fast]
    kept = df[~df["respondent"].isin(drop)].copy()
    return kept, {"raw": int(len(per)), "failed_attention": int(failed.sum()), "too_fast": int((fast & ~failed).sum()), "kept": int(len(per) - len(drop)), "median_seconds": median}


def inconsistent_share(df: pd.DataFrame) -> float:
    """Share of respondents who say yes at a higher price and no at a lower one. Kept in the analysis and reported."""
    bad = 0
    for _, g in df.groupby("respondent"):
        g = g.sort_values("mult")
        yes = g["answer"].isin(LEVELS["any"]).to_numpy()
        bad += bool(any(yes[j] and not yes[i] for i in range(len(yes)) for j in range(i + 1, len(yes))))
    return bad / df["respondent"].nunique()


def analyse_responses(df: pd.DataFrame, n_boot: int = 400) -> dict:
    """The pre-registered analysis of a real export (docs/survey-instrument.md): clean, then both demand curves, the elasticity, the share at
    the model price by wording, and which of the pre-declared attach-rate scenarios the upper end of the 'any' interval at 1.0x clears."""
    kept, counts = clean(df)
    out = {"respondents": counts, "inconsistent_share": inconsistent_share(kept)}
    for level in ("definitely", "any"):
        c = demand_curve(kept, level=level, n_boot=n_boot)
        out[level] = {"curve": c, "elasticity": elasticity(c), "at_model_price": share_at(c, 1.0)}
    if "wording" in kept.columns:
        out["by_wording"] = {w: share_at(demand_curve(g, level="definitely", n_boot=n_boot), 1.0) for w, g in kept.groupby("wording")}
    hi = out["any"]["at_model_price"]["hi"]
    out["decision"] = {f"{a:.0%}": {"upper_end_of_any_share_at_model_price": hi, "survives": bool(hi >= a)} for a in DECISION_SCENARIOS}
    return out


def main(argv: list[str]) -> None:
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    if argv[:1] == ["design"]:
        import csv
        import re
        payload = json.loads(re.sub(r"^window\.PRICES_V3 = |;\s*$", "", (root / "site" / "prices_v3.js").read_text(encoding="utf-8")))
        rows = question_bank(payload)
        out = root / "docs" / "survey-question-bank.csv"
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator=chr(10))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {out.name}: {len(rows)} questions")
    elif argv[:1] == ["analyse"] and len(argv) == 2:
        res = analyse_responses(pd.read_csv(argv[1]))
        (root / "results" / "survey_results.json").write_text(json.dumps(res, indent=1, default=float))
        c = res["respondents"]
        print(f"{c['kept']} of {c['raw']} respondents kept; at the model price: definitely {res['definitely']['at_model_price']['share']:.1%}, any {res['any']['at_model_price']['share']:.1%}; "
              + ", ".join(f"{k}: {'survives' if v['survives'] else 'ruled out'}" for k, v in res["decision"].items()))
    else:
        print("usage: python -m mcp.survey design | analyse responses.csv")


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])

