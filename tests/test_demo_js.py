"""Runs the demo page's own script against every control combination (needs Node, which CI has)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "demo_harness.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def run(html: Path):
    r = subprocess.run([NODE, str(HARNESS), str(html), str(ROOT / "site" / "prices.js")],
                       capture_output=True, text=True, timeout=120)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


def test_every_control_combination_renders_without_errors():
    code, out = run(ROOT / "site" / "index.html")
    assert out["errors"] == [], out["errors"]
    assert code == 0 and out["checks"] >= 900          # 25 hub-airline options x 12 connection times x 3 scenarios, plus the initial render


def test_slider_range_matches_the_data():
    _, out = run(ROOT / "site" / "index.html")
    prices = json.loads((ROOT / "site" / "prices.js").read_text(encoding="utf-8")[len("window.PRICES = "):].rstrip().rstrip(";"))
    assert out["slider"]["min"] == prices["buckets"][0] and out["slider"]["max"] == prices["buckets"][-1]
    assert out["slider"]["value"] == prices["buckets"][0]


def test_the_harness_catches_the_original_slider_bug(tmp_path):
    # the page as first shipped: slider ran to 225 while the data stops at 210, and crashed at the end
    bad = tmp_path / "index.html"
    bad.write_text((ROOT / "site" / "index.html").read_text(encoding="utf-8").replace('max="210"', 'max="225"'), encoding="utf-8")
    code, out = run(bad)
    assert code != 0 and out["errors"]
