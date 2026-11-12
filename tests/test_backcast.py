"""mcp.backcast and mcp.backcast_st on hand-built tables: the windows, the pandemic rule, no look-ahead, and the guard that
only these modules may name the 2018 to 2023 files."""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mcp import backcast as B
from mcp import backcast_st as S
from mcp import v5

ROOT = Path(__file__).resolve().parents[1]


def test_quarterly_blocks_cover_the_scored_window_once():
    b = B.HIST_BLOCKS
    assert len(b) == 20 and b[0] == ("2019-01", "2019-03") and b[-1] == ("2023-10", "2023-12")
    flat = []
    for s, e in b:
        m = s
        while m <= e:
            flat.append(m)
            m = B.shift(m, 1)
    assert flat == B.scored_months() and len(set(flat)) == 60


def test_shift_and_the_pandemic_window():
    assert B.shift("2019-01", -1) == "2018-12" and B.shift("2023-12", 1) == "2024-01" and B.shift("2020-03", 24) == "2022-03"
    pandemic = [m for m in B.scored_months() if B.is_pandemic(m)]
    assert len(pandemic) == 16 and pandemic[0] == "2020-03" and pandemic[-1] == "2021-06"


def test_arm_a_fits_on_everything_before_and_arm_b_on_the_trailing_24_months():
    assert B.fit_bounds("A", "2021-07", "2018-01") == ("2018-01", "2021-07")
    assert B.fit_bounds("B", "2021-07", "2018-01") == ("2019-07", "2021-07")
    assert B.fit_bounds("B", "2019-04", "2018-01") == ("2018-01", "2019-04")          # less than 24 months exist: what there is
    with pytest.raises(ValueError):
        B.fit_bounds("C", "2021-07", "2018-01")


def _weeks(seed=0, drift=0.0):
    rng = np.random.default_rng(seed)
    rows = []
    for i, ym in enumerate(B.scored_months()):
        if B.is_pandemic(ym):
            continue
        for hub in ("ATL", "ORD"):
            for sold in (False, True):
                e = 1000.0 * (1 + 0.1 * sold)
                rows.append({"ym": ym, "week": f"{ym}-01", "hub": hub, "sold": sold, "expected": e, "claims": e * float(np.exp(rng.normal(drift, 0.2))),
                             "w": 10.0, "premium": e / 0.65})
    return pd.DataFrame(rows)


def test_level_results_score_the_months_that_have_a_forecast_from_every_candidate():
    r = B.level_results(_weeks())
    assert 30 <= r["months_scored"] <= 37 and set(r["crps"]) == {"none", "last12", "local", "local_season"}
    assert all(m not in r["months"] for m in B.scored_months() if B.is_pandemic(m))
    assert r["months"][0] >= "2019-08"                                         # six observed months, then two months of lag
    assert 0 <= r["interval_hits"] <= r["months_scored"]
    assert r["local_season_active_months"] == []                               # 44 observed months never reach 48


def test_the_level_forecasts_do_not_read_later_months():
    w = _weeks()
    base = B.level_results(w)
    w2 = w.copy()
    w2.loc[w2["ym"] >= "2023-01", "claims"] *= 5.0
    alt = B.level_results(w2)
    cut = [m for m in base["months"] if m < "2023-03"]                          # months priced before 2023-01 is known (lag 2)
    assert cut and base["months"][:len(cut)] == alt["months"][:len(cut)]


def test_level_change_report_uses_only_valid_twelve_month_windows():
    r = B.level_change_report(_weeks())
    valid_ends = set(r["windows"])
    assert "2019-12" in valid_ends and "2022-06" in valid_ends and "2020-12" not in valid_ends and "2021-06" not in valid_ends


# ---- self-transfers ------------------------------------------------------------------------------------------------

def _frames(seed=0, months=None):
    rng = np.random.default_rng(seed)
    months = months or S.calendar("2018-01", "2019-12")
    out = {}
    for ym in months:
        n = 400
        df = pd.DataFrame({"hub": rng.choice(["ATL", "ORD"], n), "in_carrier": rng.choice(["AA", "DL", "UA"], n), "bucket": rng.choice([90, 105, 120], n),
                           "band": rng.choice([0, 1, 2, 3], n), "payout": rng.uniform(100, 300, n)})
        df["missed"] = (rng.random(n) < 0.1 + 0.02 * (df["bucket"] == 90)).astype(int)
        out[ym] = df
    return out


def test_the_table_from_monthly_statistics_equals_mcp_v5_fit_table():
    fr = _frames()
    stats = {m: S.month_stats(d) for m, d in fr.items()}
    for k in (0, 50, 1000):
        a = S.table_from_stats(pd.concat(stats.values()), k)
        b = v5.fit_table(pd.concat(fr.values()), k)
        assert a["cells"].keys() == b["cells"].keys() and a["prior"].keys() == b["prior"].keys()
        assert all(a["cells"][c] == pytest.approx(b["cells"][c], abs=1e-12) for c in a["cells"])
        assert all(a["hub"][h] == pytest.approx(b["hub"][h], abs=1e-12) for h in a["hub"])


def test_the_self_transfer_walk_forward_never_uses_an_outcome_from_the_last_five_months():
    fr = _frames()
    stats = {m: S.month_stats(d) for m, d in fr.items()}
    scored = S.calendar("2019-01", "2019-12")
    base = S.walk_forward(stats, lambda ym: fr[ym], scored, pandemic=lambda m: False)
    fr2 = {m: d.copy() for m, d in fr.items()}
    for m in ("2019-07", "2019-08", "2019-09", "2019-10", "2019-11", "2019-12"):
        fr2[m]["missed"] = 1 - fr2[m]["missed"]                                  # every outcome from July on flipped
    st2 = {m: S.month_stats(d) for m, d in fr2.items()}
    alt = S.walk_forward(st2, lambda ym: fr2[ym], scored, pandemic=lambda m: False)
    same = [m for m in base["monthly_ratio"] if m <= "2019-06"]
    assert same and all(base["monthly_ratio"][m] == alt["monthly_ratio"][m] for m in same)
    # a month's own outcomes do change its own ratio, and the loading of July uses nothing from after February
    assert base["monthly_ratio"]["2019-12"] != alt["monthly_ratio"]["2019-12"]
    assert base["loading"].get("2019-07") == alt["loading"].get("2019-07")


def test_the_self_transfer_walk_forward_skips_pandemic_months_and_needs_six_fit_months():
    fr = _frames(months=S.calendar("2018-01", "2019-12"))
    stats = {m: S.month_stats(d) for m, d in fr.items()}
    res = S.walk_forward(stats, lambda ym: fr[ym], S.calendar("2018-01", "2019-12"), pandemic=lambda m: "2019-03" <= m <= "2019-04")
    assert "2019-03" not in res["monthly_ratio"] and "2019-04" not in res["monthly_ratio"]
    assert min(res["monthly_ratio"]) == "2018-11"                              # six months (2018-01 to 2018-06) known five months earlier
    assert res["months_compared"] < res["months_scored"]                       # the first three scored months have no loading


def test_the_loading_is_the_pooled_ratio_of_scored_months_at_least_five_months_back():
    fr = _frames()
    stats = {m: S.month_stats(d) for m, d in fr.items()}
    res = S.walk_forward(stats, lambda ym: fr[ym], S.calendar("2019-01", "2019-12"), pandemic=lambda m: False)
    first = min(res["loading"])
    scored = sorted(res["monthly_ratio"])
    assert first > scored[2]
    assert all(v > 0 for v in res["loading"].values())


# ---- only these modules may name the historical files ---------------------------------------------------------------

def test_only_the_backcast_modules_name_the_historical_data():
    allowed = {"backcast.py", "backcast_st.py", "variant.py", "ingest.py", "costs.py", "features.py", "connections.py", "gsa_hist.py", "faa.py", "grade.py",
               "coding_audit.py", "trigger.py"}       # the coding audit has its own pre-registration; the trigger reads the backcast years only after the backcast was read
    for f in (ROOT / "src" / "mcp").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        if f.name in allowed:
            continue
        assert not re.search(r"hist_backcast|ontime_hist|connections_weighted_hist|asos_hist|hourly_hist|gsa_costs_hist", text), f.name
    for name in ("backcast.py", "backcast_st.py"):
        t = (ROOT / "src" / "mcp" / name).read_text(encoding="utf-8")
        assert "2024-09" not in t and "2026-09" not in t and "year=2026" not in t        # the sealed window is never named
