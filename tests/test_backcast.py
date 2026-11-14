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
        B.fit_bounds("Z", "2021-07", "2018-01")


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


def test_part_7b_quotes_the_numbers_in_the_results_file():
    import json
    d = json.loads((ROOT / "results" / "backcast.json").read_text(encoding="utf-8"))
    text = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7B."):text.index("### 7C.")] if "### 7C." in text else text[text.index("### 7B."):]
    g, a, lv, st = d["gap"], d["arm_B"], d["level"], d["self_transfer"]
    assert d["n_months"] == 44 and "**44 months**" in part and len(B.scored_months()) == 60
    for needle in (f"**{g['pooled_ratio_all']:.3f}**", f"**{__import__('statistics').stdev(g['monthly_ratio_all'].values()):.3f}**", f"{g['pooled_ratio_sold']:.3f} as sold, {g['pooled_ratio_all']:.3f} all",
                   f"{100 * g['sold_loss_ratio_unloaded']:.1f}% to {100 * g['sold_loss_ratio_loaded']:.1f}%", f"{lv['crps']['local']:.3f}, against {lv['crps']['none']:.3f} and {lv['crps']['last12']:.3f}",
                   f"{lv['interval_hits']} of {lv['months_scored']} months", f"loaded {st['ratio_loaded']:.3f}, unloaded {st['ratio_unloaded']:.3f}",
                   f"ran {a['pooled_ratio_all']:.3f} on all connections and **{a['pooled_ratio_sold']:.3f} as sold**", f"{a['weeks_above_100_sold']} of {a['weeks']} weeks above 100%",
                   f"{g['weeks_above_100_sold']} of {g['weeks']} weeks were above 100%", f"{100 * a['sold_loss_ratio_unloaded']:.1f}% ({100 * a['sold_loss_ratio_loaded']:.1f}% loaded)"):
        assert needle in part, needle
    share = sum(1 for v in g["monthly_sold_loss_ratio"].values() if v > 1) / len(g["monthly_sold_loss_ratio"])
    assert f"{100 * share:.1f}% (1 of 44 months)" in part
    lam = list(g["loading_lambda"].values())
    assert f"mean {sum(lam) / len(lam):.2f}, from {min(lam):.2f} to {max(lam):.2f}" in part
    for hub in ("ATL", "CLT", "DEN", "DFW", "ORD"):
        row = [l for l in part.splitlines() if l.startswith(f"| {hub} |")][0]
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[1:] == [f"{d['by_hub_year'][hub][y]:.2f}" for y in ("2019", "2020", "2021", "2022", "2023")], row
    lc = d["level_change"]
    assert f"+{lc['largest_12_month_change']:.3f}" in part and f"{lc['development_2024_2026']['largest_12_month_change']:.3f}".replace("-", "−") in part
    assert f"{d['pandemic_months']['pooled_ratio_all']:.3f}" in part and d["level"]["local_season_active_months"] == []
    from mcp import grade
    graded = grade.grade_backcast(d)
    assert [k for k, v in graded.items() if v["pass"]] == ["B1", "B2", "B7"]
    w = pd.read_csv(ROOT / "results" / "backcast_weeks_A.csv")
    w = w[~w["ym"].map(B.is_pandemic)]
    wk = w[w["sold"]].groupby("week")[["claims", "premium"]].sum()
    lr = wk["claims"] / wk["premium"]
    assert len(lr) == g["weeks"] == 192 and int((lr > 1).sum()) == g["weeks_above_100_sold"] and f"worst week {100 * lr.max():.0f}%" in part


def test_the_exploratory_arms_leave_the_pandemic_out_of_the_fit_and_do_not_change_the_pre_registered_ones():
    assert B.fit_window("A", "c", "2018-01", "2022-01") == B.window("c", "2018-01", "2022-01") == B.fit_window("B", "c", "2018-01", "2022-01")
    w = B.fit_window("C", "c", "2018-01", "2022-01")
    assert "NOT (c >= TIMESTAMP '2020-03-01' AND c < TIMESTAMP '2021-07-01')" in w and w.startswith("((c >= TIMESTAMP '2018-01-01'")
    assert B.fit_bounds("C", "2022-01", "2018-01") == ("2018-01", "2022-01")
    # D reaches back until it holds 24 months that are not pandemic months: 6 of 2021, 14 of 2019-01..2020-02, 4 more of 2018
    a, b = B.fit_bounds("D", "2022-01", "2018-01")
    months, m = [], a
    while m < b:
        months.append(m)
        m = B.shift(m, 1)
    assert sum(1 for x in months if not B.is_pandemic(x)) == 24 and a == "2018-09"
    assert B.fit_bounds("D", "2019-04", "2018-01") == ("2018-01", "2019-04") == B.fit_bounds("B", "2019-04", "2018-01")
    assert B.fit_bounds("D", "2020-01", "2018-01") == B.fit_bounds("B", "2020-01", "2018-01")          # no pandemic month yet: the same window


def test_arm_summary_reports_the_pooled_ratios_the_sold_loss_ratio_and_the_yearly_sold_over_all_ratio():
    w = _weeks(seed=1)
    r = B.arm_summary(w)
    assert r["months"] == 44 and r["weeks"] > 0
    allw = w[~w["ym"].map(B.is_pandemic)]
    assert r["pooled_ratio_all"] == pytest.approx(allw["claims"].sum() / allw["expected"].sum())
    sold = allw[allw["sold"]]
    assert r["pooled_ratio_sold"] == pytest.approx(sold["claims"].sum() / sold["expected"].sum())
    assert r["sold_loss_ratio"] == pytest.approx(sold["claims"].sum() / sold["premium"].sum())
    assert set(r["sold_over_all_by_year"]) == {"2019", "2020", "2021", "2022", "2023"}
    with_pandemic = pd.concat([w, w.assign(ym="2020-05", claims=w["claims"] * 50)])
    assert B.arm_summary(with_pandemic)["pooled_ratio_all"] == pytest.approx(r["pooled_ratio_all"])          # pandemic months are left out


def test_part_7i_quotes_the_numbers_in_the_results_file_and_the_pre_registered_arms_are_unchanged():
    import json
    d = json.loads((ROOT / "results" / "backcast_arms.json").read_text(encoding="utf-8"))
    bc = json.loads((ROOT / "results" / "backcast.json").read_text(encoding="utf-8"))
    text = (ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7I."):]
    assert d["A"]["pooled_ratio_all"] == pytest.approx(bc["gap"]["pooled_ratio_all"]) and d["B"]["pooled_ratio_sold"] == pytest.approx(bc["arm_B"]["pooled_ratio_sold"])
    for arm in "ABCD":
        row = [l for l in part.splitlines() if l.startswith(f"| {arm} | ") and "%" in l][0]
        cells = [c.strip() for c in row.strip("|").split("|")]
        x = d[arm]
        assert cells[2:] == [f"{x['pooled_ratio_all']:.3f}", f"{x['pooled_ratio_sold']:.3f}", f"{100 * x['sold_loss_ratio']:.1f}%", str(x["weeks_above_100_sold"])], row
        yr = [l for l in part.splitlines() if l.startswith(f"| {arm} | ") and "%" not in l][0]
        assert [c.strip() for c in yr.strip("|").split("|")][1:] == [f"{d[arm]['sold_over_all_by_year'][y]:.2f}" for y in ("2019", "2020", "2021", "2022", "2023")], yr
    assert d["C"]["pooled_ratio_sold"] > 1.0 > d["A"]["pooled_ratio_sold"] and all(d[a]["weeks_above_100_sold"] >= 41 for a in "BCD")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "VALIDATION.md` 7I" in readme and "winner's curse looks like a young model's problem" not in readme
