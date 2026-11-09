"""v5 self-transfer pairings, label and table, on hand-built flights and frames where the answer is known."""
import json
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from mcp import v5
from tests.test_connections import flight

ROOT = Path(__file__).resolve().parents[1]


def run(rows, t_min=90):
    con = duckdb.connect()
    con.execute("""CREATE TABLE flights (flight_date DATE, carrier VARCHAR, flight_number INTEGER,
        origin VARCHAR, dest VARCHAR, crs_dep_hhmm SMALLINT, crs_arr_hhmm SMALLINT,
        crs_elapsed_min DOUBLE, dep_delay_min DOUBLE, arr_delay_min DOUBLE,
        cancelled BOOLEAN, diverted BOOLEAN)""")
    con.executemany("INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return con.execute(v5.pairs_sql("flights", t_min, frac=1.0)).fetchdf()


def trip(in_arr_delay=0.0, out_dep_delay=0.0, out_carrier="UA", out_dep=1210, in_kw=None, out_kw=None, extra=()):
    """ORD -> ATL on DL lands 10:10 hub time. ATL -> MIA on another network departs at out_dep."""
    i = flight(1, "ORD", "ATL", 710, 1010, 120, arr_delay=in_arr_delay, carrier="DL", **(in_kw or {}))
    hh, mm = divmod(out_dep, 100)
    arr = (hh + 2) * 100 + mm
    o = flight(2, "ATL", "MIA", out_dep, arr, 120, dep_delay=out_dep_delay, carrier=out_carrier, **(out_kw or {}))
    return [i, o, *extra]


def test_only_pairs_of_different_networks_are_built():
    assert len(run(trip(out_carrier="DL"))) == 0
    r = run(trip())
    assert len(r) == 1 and r.loc[0, "in_carrier"] == "DL" and r.loc[0, "out_carrier"] == "UA"


def test_the_gap_window_is_90_to_300_minutes_whatever_the_minimum():
    assert len(run(trip(out_dep=1130))) == 0                  # 80 minutes
    assert run(trip(out_dep=1140)).loc[0, "slack_min"] == 90
    assert len(run(trip(out_dep=1510))) == 1 and len(run(trip(out_dep=1520))) == 0
    assert len(run(trip(out_dep=1140), t_min=60)) == 1        # the window does not move with T


def test_a_miss_needs_arrival_plus_t_strictly_after_departure():
    assert run(trip(in_arr_delay=30)).loc[0, "missed"] == 0   # 10:40 + 90 = 12:10, departs 12:10: made
    assert run(trip(in_arr_delay=31)).loc[0, "missed"] == 1
    assert run(trip(in_arr_delay=31), t_min=120).loc[0, "missed"] == 1
    assert run(trip(in_arr_delay=0), t_min=120).loc[0, "missed"] == 0   # 10:10 + 120 = 12:10: made
    assert run(trip(in_arr_delay=1), t_min=120).loc[0, "missed"] == 1


def test_any_cause_counts_and_a_cancelled_inbound_is_a_miss_by_cancellation():
    r = run(trip(in_kw={"cancelled": True})).loc[0]
    assert r["missed"] == 1 and r["missed_by_cancellation"] == 1 and r["status"] == "ok"
    assert run(trip(in_arr_delay=60)).loc[0, "missed_by_cancellation"] == 0


def test_a_cancelled_outbound_is_excluded_not_a_claim():
    assert run(trip(out_kw={"cancelled": True})).loc[0, "status"] == "outbound_cancelled"


def test_overnight_only_when_no_later_departure_to_the_destination_that_day():
    later = flight(3, "ATL", "MIA", 1900, 2100, 120, carrier="AA")
    assert run(trip()).loc[0, "overnight"] == 1
    r = run(trip(extra=[later]))
    assert r.loc[r["out_carrier"] == "UA", "overnight"].iloc[0] == 0


def test_the_hash_sample_is_deterministic_and_roughly_the_stated_share():
    rows = [flight(i, "ORD", "ATL", 710, 1010, 120, carrier="DL") for i in range(1, 41)]
    rows += [flight(100 + j, "ATL", "MIA", 1210, 1410, 120, carrier="UA") for j in range(1, 41)]
    con = duckdb.connect()
    con.execute("""CREATE TABLE flights (flight_date DATE, carrier VARCHAR, flight_number INTEGER, origin VARCHAR,
        dest VARCHAR, crs_dep_hhmm SMALLINT, crs_arr_hhmm SMALLINT, crs_elapsed_min DOUBLE, dep_delay_min DOUBLE,
        arr_delay_min DOUBLE, cancelled BOOLEAN, diverted BOOLEAN)""")
    con.executemany("INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    a = con.execute(v5.pairs_sql("flights", 90, frac=0.25)).fetchdf()
    b = con.execute(v5.pairs_sql("flights", 90, frac=0.25)).fetchdf()
    assert a.equals(b) and 0.15 * 1600 < len(a) < 0.35 * 1600


def cells_frame(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"hub": rng.choice(["ATL", "ORD"], n), "in_carrier": rng.choice(["DL", "UA", "AA"], n),
                       "bucket": rng.choice([90, 105, 120], n), "band": rng.integers(0, 4, n)})
    p = 0.05 + 0.10 * (df["bucket"] == 90) + 0.05 * (df["hub"] == "ORD")
    df["missed"] = (rng.uniform(size=n) < p).astype(int)
    df["payout"] = 300.0
    return df


def test_shrinkage_runs_from_raw_cells_to_the_hub_by_gap_prior():
    df = cells_frame()
    raw, full = v5.fit_table(df, 0), v5.fit_table(df, 1e9)
    key = "ATL|DL|90|0"
    g = df[(df.hub == "ATL") & (df.in_carrier == "DL") & (df.bucket == 90) & (df.band == 0)]
    assert raw["cells"][key] == pytest.approx(g["missed"].mean())
    assert full["cells"][key] == pytest.approx(full["prior"]["ATL|90"], abs=1e-6)


def test_unseen_cells_fall_back_to_the_prior_then_the_hub():
    t = v5.fit_table(cells_frame(), 50)
    new = pd.DataFrame({"hub": ["ATL", "ORD"], "in_carrier": ["B6", "B6"], "bucket": [90, 285], "band": [0, 0]})
    p = v5.score(new, t)
    assert p[0] == pytest.approx(t["prior"]["ATL|90"]) and p[1] == pytest.approx(t["hub"]["ORD"])


def test_realized_over_target_is_one_when_the_prices_are_the_true_rates():
    df = cells_frame(200_000, seed=1)
    true = 0.05 + 0.10 * (df["bucket"] == 90) + 0.05 * (df["hub"] == "ORD")
    assert v5.realized_over_target(df, true.to_numpy()) == pytest.approx(1.0, abs=0.03)


def test_the_holdout_refuses_a_second_read(tmp_path, monkeypatch):
    done = tmp_path / "v5_holdout.json"
    done.write_text("{}")
    monkeypatch.setattr(v5, "HOLDOUT_RESULT", done)
    with pytest.raises(SystemExit, match="read once"):
        v5.holdout()


def test_the_module_matches_the_preregistration():
    text = (ROOT / "PREREGISTRATION_V5_SELF_TRANSFER.md").read_text(encoding="utf-8")
    assert v5.T_MIN == 90 and (v5.GAP_LO, v5.GAP_HI) == (90, 300) and v5.TARGET_LR == 0.65 and v5.CAP == 0.10
    assert v5.K_GRID == (0, 50, 200, 1000) and v5.WINDOWS["SEALED"] == ("2026-01", "2026-08")
    assert "**January to August 2026**" in text and "{0, 50, 200, 1000}" in text and "T = 90 minutes" in text
    for s, lo, hi in (("S1", "0.85", "1.15"), ("S2", "20%", "50%"), ("S4", "0.08", "0.35")):
        assert re.search(rf"\| {s} \|.*{re.escape(lo)}.*{re.escape(hi)}", text), s


def test_weights_and_payout_overrides_enter_the_ratio():
    df = cells_frame(1000, seed=2)
    p = np.full(len(df), df["missed"].mean())
    assert v5.realized_over_target(df, p) == pytest.approx(1.0)
    w = np.where(df["bucket"] == 90, 10.0, 1.0)
    assert v5.realized_over_target(df, p, weight=w) > 1.0          # weighting toward the riskier bucket
    assert v5.realized_over_target(df, p, payout=np.full(len(df), 7.0)) == pytest.approx(1.0)


def test_the_frozen_table_is_the_one_recorded_before_the_holdout():
    import hashlib
    table = ROOT / "models" / "v5_table.json"
    digest = hashlib.sha256(table.read_bytes()).hexdigest()
    assert digest == "154b580d86094700a8307520334f0d948bf3c4e84c940b31d4787380bf7519d1"
    assert digest in (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    t = json.loads(table.read_text())
    assert t["k"] == json.loads((ROOT / "results" / "v5_selection.json").read_text())["chosen_k"] == 1000
    assert t["fitted_on"] == list(v5.WINDOWS["FINAL"])


def test_the_readme_quotes_the_holdout_as_read():
    r = json.loads((ROOT / "results" / "v5_holdout.json").read_text())
    m, text = r["primary"], (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"**{m['realized_over_target']:.2f}**" in text and f"[{m['interval_95'][0]:.2f}, {m['interval_95'][1]:.2f}]" in text
    assert r["grades"] == {"S1": False, "S2": True, "S3": True, "S4": True, "S5": True} and "**S1 failed**" in text
    assert f"{m['monthly_sd']:.2f}" in text and r["table_sha256"] in (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    sens = r["sensitivity"]["t_min"]
    assert f"{sens['120']['realized_over_target']:.2f}" in text and f"{sens['60']['realized_over_target']:.2f}" in text
