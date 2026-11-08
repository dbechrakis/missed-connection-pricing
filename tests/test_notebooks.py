"""The notebooks run end to end from the published results and produce their figures."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script,figures", [
    ("02_model.py", ["model_feature_sets.png", "holdout_by_slack.png", "holdout_scores.png"]),
    ("03_pricing.py", ["price_curve.png", "cutoff_sensitivity.png"]),
])
def test_notebook_runs_and_writes_its_figures(tmp_path, script, figures):
    env = {**os.environ, "MCP_FIG_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, str(ROOT / "notebooks" / script)], capture_output=True, text=True, env=env, timeout=180)
    assert r.returncode == 0, r.stderr[-1500:]
    for f in figures:
        assert (tmp_path / f).stat().st_size > 5_000, f
    assert "nan" not in r.stdout.lower()
