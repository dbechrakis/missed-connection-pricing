"""The v4 test: the arithmetic on a toy book, and the frozen artefact."""
import json

import numpy as np
import pandas as pd
import pytest

from mcp.holdout_v4 import SENSITIVITY, summarise
from mcp.v3_loading import FROZEN


def month(seed, under):
    rng = np.random.default_rng(seed)
    n = 30_000
    p = rng.uniform(0.01, 0.12, n)
    true = np.minimum(p * (1 + (under - 1) * (0.12 - p) / 0.11), 0.9)
    return pd.DataFrame({"p": p, "y_gap": (rng.uniform(size=n) < true).astype(int), "claim_cost": 250.0, "fare": 400.0, "weight": 1.0, "week": rng.integers(0, 4, n).astype(str)})


def test_the_loaded_price_beats_the_v3_price_where_the_model_under_prices_and_sells_less():
    months = {"2026-09": month(1, 1.5), "2026-10": month(2, 1.5), "2026-11": month(3, 1.5)}
    s = summarise(months, 1.25)
    assert s["pooled_loss_ratio"]["v4"] < s["pooled_loss_ratio"]["v3"] and s["improvement_points"] > 0
    assert s["v4_below_v3_in_every_month"]
    assert all(m["v4_share_sold"] < m["v3_share_sold"] for m in s["monthly"].values())
    assert set(s["sensitivity"]) == {f"{x:.2f}" for x in SENSITIVITY}
    assert s["sensitivity"]["1.00"]["loss_ratio"] == pytest.approx(s["pooled_loss_ratio"]["v3"], rel=0.02)


def test_the_frozen_loading_artefact_is_one_number_with_its_rule_and_its_data():
    a = json.loads(FROZEN.read_text(encoding="utf-8"))
    assert a["lambda"] == 1.16 and a["cap"] == 0.05 and a["target_loss_ratio"] == 0.65
    assert "pmiss_v3.joblib" in a["model"] and "26 months" in a["fitted_on"] and "target loss ratio" in a["rule"]
    assert b"\r" not in FROZEN.read_bytes()                                  # Unix line endings, so the hash is the same everywhere
