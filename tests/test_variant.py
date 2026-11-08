"""The v3 switch must never redirect a frozen v1 path, and v3 must never share a file with v1."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROBE = """
import json, sys
sys.path.insert(0, 'src')
import mcp.ingest as i, mcp.connections as c, mcp.features as f, mcp.pricing as p, mcp.causes as k
print(json.dumps({'ontime': i.OUT.name, 'raw': i.RAW.name, 'connections': c.OUT.name, 'weighted': c.WEIGHTED.name,
                  'weights': c.WEIGHTS.name, 'features': f.OUT.name, 'severity': p.SEVERITY.name, 'db1b_carrier': i.DB1B_CARRIER,
                  'causes': k.RESULTS.name, 'first_columns': list(i.ACTIVE_COLUMNS)[:2]}))
"""


def paths(variant=None):
    env = {k: v for k, v in os.environ.items() if k != "MCP_VARIANT"}
    if variant:
        env["MCP_VARIANT"] = variant
    r = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_default_is_the_frozen_v1_population():
    p = paths()
    assert p == {"ontime": "ontime", "raw": "ontime", "connections": "connections", "weighted": "connections_weighted",
                 "weights": "route_weights.parquet", "features": "features", "severity": "severity.parquet",
                 "db1b_carrier": "RPCarrier", "causes": "causes.json", "first_columns": ["FlightDate", "Reporting_Airline"]}


def test_v3_uses_its_own_files_and_the_marketing_network():
    v1, v3 = paths(), paths("v3")
    assert v3["first_columns"] == ["FlightDate", "Marketing_Airline_Network"] and v3["db1b_carrier"] == "TkCarrier"
    assert v3["raw"] == "marketing"
    for key in ("ontime", "connections", "weighted", "weights", "features", "severity", "causes"):
        assert v3[key] != v1[key], key                     # never the same file as v1


def test_an_unknown_variant_is_refused():
    env = {**os.environ, "MCP_VARIANT": "v9"}
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0,'src'); import mcp.variant"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "MCP_VARIANT" in r.stderr
