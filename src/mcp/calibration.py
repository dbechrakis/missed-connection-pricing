"""Calibration policies that only ever use *past* months. Developed for v2 (VALIDATION.md Part 3).

v1 calibrated once, on one quarter (Apr-Jun 2025), and carried that quarter's level into H2 2025.
A policy here is defined by what it is allowed to look at: the last `k` months of outcomes that
were already known when the prices are set. Month statistics are small additive summaries, so a
policy can be refit every month without keeping row-level data.

  none         raw model probability
  level_global p' = p x (observed / predicted) over the window, all hubs together
  level_hub    the same factor per hub (a hub with no data in the window falls back to the global factor)
  iso_global   isotonic regression fitted on the window

Level policies move the whole curve up or down and keep the model's shape; isotonic reshapes it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.isotonic import IsotonicRegression

HIST_BINS = 2000
POLICIES = ("none", "level_global", "level_hub", "iso_global")


@dataclass
class MonthStats:
    """Additive summary of one month of scored connections (weights are DB1B passenger weights)."""
    month: str
    hub: dict = field(default_factory=dict)      # hub -> (W, Wy, Wp)
    hist: tuple = None                           # (W, Wy, Wp) arrays over HIST_BINS prediction bins


def month_stats(month: str, hubs, y, w, p) -> MonthStats:
    hubs, y, w, p = np.asarray(hubs), np.asarray(y, float), np.asarray(w, float), np.asarray(p, float)
    by_hub = {h: (float(w[hubs == h].sum()), float((w * y)[hubs == h].sum()), float((w * p)[hubs == h].sum()))
              for h in np.unique(hubs)}
    idx = np.minimum((np.clip(p, 0, 1) * HIST_BINS).astype(int), HIST_BINS - 1)
    hist = (np.bincount(idx, w, HIST_BINS), np.bincount(idx, w * y, HIST_BINS), np.bincount(idx, w * p, HIST_BINS))
    return MonthStats(month, by_hub, hist)


def window(stats: list[MonthStats], k: int) -> list[MonthStats]:
    """The last k months by calendar order. If fewer than k exist, all of them."""
    return sorted(stats, key=lambda s: s.month)[-k:] if stats else []


def _factors(ws: list[MonthStats]) -> tuple[float, dict]:
    tot = {}
    for s in ws:
        for h, (W, Wy, Wp) in s.hub.items():
            a = tot.get(h, (0.0, 0.0))
            tot[h] = (a[0] + Wy, a[1] + Wp)
    gy, gp = sum(v[0] for v in tot.values()), sum(v[1] for v in tot.values())
    g = gy / gp if gp > 0 else 1.0
    return g, {h: (y / p if p > 0 else g) for h, (y, p) in tot.items()}


def make_calibrator(policy: str, k: int, stats: list[MonthStats]):
    """Return f(p, hubs) -> calibrated p, using only `stats` (the caller passes months already known)."""
    ws = window(stats, k)
    if policy == "none" or not ws:
        return lambda p, hubs: np.asarray(p, float)
    if policy == "level_global":
        g, _ = _factors(ws)
        return lambda p, hubs: np.clip(np.asarray(p, float) * g, 0.0, 1.0)
    if policy == "level_hub":
        g, per = _factors(ws)
        return lambda p, hubs: np.clip(np.asarray(p, float) * np.array([per.get(h, g) for h in np.asarray(hubs)]), 0.0, 1.0)
    if policy == "iso_global":
        W = sum(s.hist[0] for s in ws)
        Wy = sum(s.hist[1] for s in ws)
        Wp = sum(s.hist[2] for s in ws)
        keep = W > 0
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(Wp[keep] / W[keep], Wy[keep] / W[keep], sample_weight=W[keep])
        return lambda p, hubs: iso.predict(np.asarray(p, float))
    raise ValueError(policy)
