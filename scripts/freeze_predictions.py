"""Write the golden predictions of every frozen model on fixed synthetic rows (tests/fixtures/frozen_predictions.json).

Run once, under requirements.lock, whenever a frozen model is created. tests/test_frozen_models.py then fails if any
installed library makes a frozen model load differently or predict differently, before a pre-registered read relies on it.
    PYTHONPATH=src python scripts/freeze_predictions.py
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from mcp.pricing import _codes

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "frozen_predictions.json"
MODELS = {"models/pmiss.joblib": ("gbm",), "models/pmiss_v2.joblib": ("gbm",), "models/pmiss_v3.joblib": ("gbm_gap", "gbm_any")}
N_ROWS = 300


def rows(bundle: dict, n: int = N_ROWS, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cols = {"hub": rng.choice(bundle["cats"]["hub"], n), "carrier": rng.choice(bundle["cats"]["carrier"], n),
            "slack_min": rng.integers(45, 300, n), "out_hour": rng.integers(5, 23, n), "out_dow": rng.integers(0, 7, n),
            "in_arr_hour": rng.integers(5, 23, n), "in_delay_mean": rng.normal(12, 8, n), "in_late15": rng.uniform(0.05, 0.4, n),
            "in_cancel": rng.uniform(0, 0.05, n), "month": rng.integers(1, 13, n)}
    return pd.DataFrame(cols)[bundle["features"]]


def predictions(path: str, keys: tuple[str, ...]) -> dict:
    bundle = joblib.load(ROOT / path)
    x = _codes(rows(bundle), bundle["cats"])
    out = {k: bundle[k].predict_proba(x)[:, 1].tolist() for k in keys}
    if "isotonic" in bundle:
        out["isotonic"] = bundle["isotonic"].predict(np.asarray(out["gbm"])).tolist()
    return out


if __name__ == "__main__":
    golden = {"scikit-learn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__,
              "rows": N_ROWS, "predictions": {p: predictions(p, k) for p, k in MODELS.items()}}
    OUT.write_text(json.dumps(golden) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} under scikit-learn {sklearn.__version__}")
