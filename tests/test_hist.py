"""The 2018 to 2023 plumbing: per-year route weights, the GSA master files, and the variant switch. No network, no data."""
import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from mcp import gsa_hist, ingest
from mcp.connections import weighted_sql

ROOT = Path(__file__).resolve().parents[1]


def test_the_hist_variant_has_its_own_suffix_and_leaves_v1_and_v3_alone():
    code = "from mcp.variant import sfx, HIST, MARKETING, VARIANT; print(VARIANT, HIST, MARKETING, sfx('connections'), sfx('severity'))"
    for variant, expect in (("hist", "hist True True connections_hist severity_hist"), ("v3", "v3 False True connections_v3 severity_v3"),
                            ("v1", "v1 False False connections severity")):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT / "src", env={**os.environ, "MCP_VARIANT": variant})
        assert out.stdout.strip() == expect, (variant, out.stdout, out.stderr)
    bad = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT / "src", env={**os.environ, "MCP_VARIANT": "v9"})
    assert bad.returncode != 0 and "must be v1, v3 or hist" in bad.stderr


def test_the_sealed_window_readers_refuse_the_hist_variant():
    for mod in ("holdout_v3", "holdout_v4"):
        text = (ROOT / "src" / "mcp" / f"{mod}.py").read_text(encoding="utf-8")
        assert 'assert VARIANT == "v3"' in text and "assert MARKETING" not in text


def _routes(tmp_path, rows):
    d = tmp_path / "routes" / "year=2018"
    d.mkdir(parents=True)
    pd.DataFrame(rows, columns=["quarter", "carrier", "origin", "hub", "destination", "passengers", "n_markets", "fare_mean"]).to_parquet(d / "q.parquet")
    return tmp_path


def test_route_weights_by_year_pool_the_four_quarters_of_a_year_and_apply_to_the_next_year(tmp_path):
    rows = [("2018Q1", "AA", "BOS", "ORD", "LAX", 10, 1, 100.0), ("2018Q2", "AA", "BOS", "ORD", "LAX", 30, 1, 200.0),
            ("2018Q3", "AA", "BOS", "ORD", "LAX", 20, 1, 100.0), ("2018Q4", "AA", "BOS", "ORD", "LAX", 40, 1, 100.0),
            ("2019Q1", "AA", "BOS", "ORD", "LAX", 5, 1, 50.0)]
    out_dir = _routes(tmp_path, rows)
    n = ingest.build_route_weights_by_year(out_dir=out_dir, quarters=("2018Q1", "2018Q2", "2018Q3", "2018Q4", "2019Q1"))
    assert n == 2
    w = pd.read_parquet(out_dir / "route_weights.parquet").sort_values("weight_year")
    assert w["weight_year"].tolist() == [2019, 2020]                      # 2018 passengers price 2019, 2019 passengers price 2020
    assert w["passengers"].tolist() == [100, 5]
    assert w["fare_mean"].iloc[0] == pytest.approx((10 * 100 + 30 * 200 + 20 * 100 + 40 * 100) / 100)


def test_a_connection_takes_the_weight_of_the_year_it_departs_in_and_never_a_later_one(tmp_path):
    conns = pd.DataFrame({"carrier": ["AA"] * 3, "origin": ["BOS"] * 3, "hub": ["ORD"] * 3, "destination": ["LAX"] * 3, "status": ["ok"] * 3,
                          "out_sched_dep": pd.to_datetime(["2019-03-04 10:00", "2019-03-04 11:00", "2020-03-04 10:00"])})
    weights = pd.DataFrame({"carrier": ["AA"] * 2, "origin": ["BOS"] * 2, "hub": ["ORD"] * 2, "destination": ["LAX"] * 2,
                            "weight_year": [2019, 2020], "passengers": [100.0, 7.0], "fare_mean": [150.0, 999.0]})
    conns.to_parquet(tmp_path / "c.parquet")
    weights.to_parquet(tmp_path / "w.parquet")
    sql = weighted_sql((tmp_path / "c.parquet").as_posix(), (tmp_path / "w.parquet").as_posix(), by_year=True)
    got = duckdb.connect().execute(sql).fetchdf().sort_values("out_sched_dep")
    assert got["fare_mean"].tolist() == [150.0, 150.0, 999.0]
    assert got["weight"].tolist() == [50.0, 50.0, 7.0]                     # 2019: split over two pairings in the month, 2020: one
    plain = duckdb.connect().execute(weighted_sql((tmp_path / "c.parquet").as_posix(), (tmp_path / "w.parquet").as_posix(), by_year=False)).fetchdf()
    assert len(plain) == 6                                                  # without the year join a route would match both years


def test_gsa_seasons_cover_the_year_and_wrap_past_december():
    rows = [{"begin": "October 1", "end": "October 31", "lodging": 166}, {"begin": "November 1", "end": "August 31", "lodging": 148},
            {"begin": "September 1", "end": "September 30", "lodging": 166}]
    m = gsa_hist.lodging_by_month(rows)
    assert m[10] == 166 and m[9] == 166 and m[12] == 148 and m[1] == 148 and m[8] == 148 and len(m) == 12
    assert gsa_hist.lodging_by_month([{"begin": None, "end": float("nan"), "lodging": 127}]) == {m: 127.0 for m in range(1, 13)}
    with pytest.raises(ValueError):
        gsa_hist.lodging_by_month([{"begin": "January 1", "end": "June 30", "lodging": 100}])


def test_hub_rates_pick_the_hubs_destination_and_refuse_ambiguous_meals_rates():
    recs = []
    for st, dest, lod, mie in (("GA", "Atlanta", 163, 74), ("IL", "Chicago", 218, 79), ("TX", "Dallas", 154, 69), ("CO", "Denver / Aurora", 199, 79),
                               ("NC", "Charlotte", 129, 69), ("GA", "Savannah", 300, 80)):
        recs.append({"state": st, "dest": dest, "county": "x", "begin": None, "end": None, "lodging": lod, "mie": mie})
    r = gsa_hist.hub_rates(recs)
    assert r["ATL"]["lodging"][5] == 163.0 and r["ORD"]["mie"] == 79.0 and set(r) == set(gsa_hist.HUB_DESTINATION)
    with pytest.raises(ValueError):
        gsa_hist.hub_rates(recs + [{**recs[0], "mie": 99}])
    with pytest.raises(ValueError):
        gsa_hist.hub_rates(recs[:4])


def test_the_hubs_destinations_are_the_ones_the_2024_pages_return_and_every_hist_year_is_cached():
    raw = ROOT / "data" / "external" / "gsa"
    for hub, (state, dest) in gsa_hist.HUB_DESTINATION.items():
        zip_code = gsa_hist.HUB_ZIP[hub]
        fy24 = json.loads((raw / f"{zip_code}_FY2024_page.json").read_text(encoding="utf-8"))
        assert fy24["city"] == dest, (hub, fy24["city"])
        for fy in gsa_hist.FILES:
            rec = json.loads((raw / f"{zip_code}_FY{fy}_page.json").read_text(encoding="utf-8"))
            assert sorted(int(k) for k in rec["lodging"]) == list(range(1, 13)) and rec["mie"] > 0 and rec["city"] == dest
            assert 100 <= min(rec["lodging"].values()) <= max(rec["lodging"].values()) <= 300
