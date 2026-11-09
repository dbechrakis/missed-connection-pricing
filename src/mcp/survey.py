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
