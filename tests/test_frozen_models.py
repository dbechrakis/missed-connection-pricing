"""The frozen models must load and predict exactly as they did when they were frozen.

The hash tests in test_docs.py prove the files are unchanged; they cannot prove that the installed libraries still read
them the same way. A pickled scikit-learn model can load under another version with only a warning and predict
differently. The pre-registered reads depend on these files, so this compares fresh predictions on fixed rows with the
golden ones written by scripts/freeze_predictions.py under requirements.lock.
"""
import json
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from freeze_predictions import MODELS, predictions  # noqa: E402

GOLDEN = json.loads((ROOT / "tests" / "fixtures" / "frozen_predictions.json").read_text())


def test_the_installed_scikit_learn_is_the_one_the_models_were_frozen_with():
    import sklearn
    assert sklearn.__version__ == GOLDEN["scikit-learn"], "install requirements.lock: the frozen models were built with it"


@pytest.mark.parametrize("path", sorted(MODELS))
def test_each_frozen_model_loads_without_a_version_warning_and_predicts_as_frozen(path):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        joblib.load(ROOT / path)
    fresh = predictions(path, MODELS[path])
    for key, golden in GOLDEN["predictions"][path].items():
        np.testing.assert_allclose(fresh[key], golden, rtol=0, atol=1e-10, err_msg=f"{path}:{key}")


def test_the_golden_rows_exercise_a_real_spread_of_risk():
    p = np.asarray(GOLDEN["predictions"]["models/pmiss_v3.joblib"]["gbm_gap"])
    assert len(p) == GOLDEN["rows"] and p.min() < p.max() / 5
