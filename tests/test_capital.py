"""mcp.capital against cases with a known answer."""
import numpy as np
import pytest

from mcp import capital as K

WEEKS = np.datetime64("2023-01-02") + 7 * np.arange(156)


def test_a_book_with_no_variance_is_priced_at_expected_claims_over_one_minus_expenses():
    expected = np.full(156, 1000.0)
    claims = expected.copy()
    out = K.solve(claims, expected, WEEKS, attach=None, coc=0.10, expense=0.0, n_sim=50)
    assert out["pi"] == pytest.approx(1.0, abs=2e-3)                       # premium equals claims: a loss ratio of 100%
    assert out["loading_vs_current"] == pytest.approx(0.65, abs=2e-3)
    assert K.solve(claims, expected, WEEKS, expense=0.30, n_sim=50)["pi"] == pytest.approx(1 / 0.70, abs=3e-3)


def test_the_solution_balances_the_equation_and_more_variance_costs_more():
    rng = np.random.default_rng(0)
    expected = np.full(156, 1000.0)
    calm = expected * np.exp(rng.normal(0, 0.1, 156))
    wild = expected * np.exp(rng.normal(0, 0.5, 156))
    a, b = K.solve(calm, expected, WEEKS, n_sim=300), K.solve(wild, expected, WEEKS, n_sim=300)
    assert abs(a["residual"]) < 5e-3 and abs(b["residual"]) < 5e-3
    assert b["pi"] > a["pi"] and b["terms"]["capital_margin"] > a["terms"]["capital_margin"]


def test_capital_costs_more_at_a_higher_cost_of_capital_and_a_stop_loss_trades_capital_for_its_price():
    rng = np.random.default_rng(1)
    expected = np.full(156, 1000.0)
    claims = expected * np.exp(rng.normal(0, 0.5, 156))
    lo, hi = K.solve(claims, expected, WEEKS, coc=0.06, n_sim=300), K.solve(claims, expected, WEEKS, coc=0.15, n_sim=300)
    assert hi["pi"] > lo["pi"]
    sl = K.solve(claims, expected, WEEKS, attach=1.0, coc=0.10, n_sim=300)
    free = K.solve(claims, expected, WEEKS, attach=None, coc=0.10, n_sim=300)
    assert sl["terms"]["stop_loss_cost"] > 0 and sl["terms"]["capital_margin"] < free["terms"]["capital_margin"]


def test_a_stop_loss_cost_is_its_burning_cost_per_unit_of_premium():
    expected = np.full(156, 1000.0)
    claims = expected * np.where(np.arange(156) % 4 == 0, 3.0, 0.5)
    c = K.components(1.0, claims, expected, WEEKS, 1.0, 0.1, 0.95, 50, 4, 0)
    assert c["stop_loss_cost"] == pytest.approx(np.mean(np.maximum(claims / expected - 1.0, 0)))
    assert c["retained_loss_ratio"] == pytest.approx(np.mean(np.minimum(claims / expected, 1.0)))


def test_diversification_is_one_for_identical_hubs_and_near_a_square_root_for_independent_ones():
    rng = np.random.default_rng(2)
    base = rng.normal(1, 0.3, 400)
    same = K.diversification({h: base for h in "ABCDE"})
    assert same["ratio"] == pytest.approx(1.0) and same["mean_pairwise_correlation"] == pytest.approx(1.0)
    ind = K.diversification({h: rng.normal(1, 0.3, 4000) for h in "ABCDE"})
    assert ind["ratio"] == pytest.approx(1 / np.sqrt(5), abs=0.03) and abs(ind["mean_pairwise_correlation"]) < 0.05


def test_no_premium_balances_an_impossible_book():
    expected = np.full(156, 1000.0)
    with pytest.raises(ValueError):
        K.solve(expected * 1e6, expected, WEEKS, n_sim=20, hi=2.0)


def _weeks_frame(n=156, seed=3):
    import pandas as pd
    rng = np.random.default_rng(seed)
    rows = []
    for i, w in enumerate(WEEKS[:n]):
        for hub in ("ATL", "ORD", "DEN"):
            for sold in (False, True):
                e = 1000.0 * (1 + 0.2 * sold)
                rows.append({"week": str(w), "hub": hub, "sold": sold, "expected": e, "claims": e * float(np.exp(rng.normal(0.0, 0.3)))})
    return pd.DataFrame(rows)


def test_the_weekly_record_pools_hubs_and_the_run_returns_the_grid_the_documents_quote(monkeypatch):
    monkeypatch.setattr(K, "EXPENSES", (0.25,))
    monkeypatch.setattr(K, "ATTACHMENTS", (None, 1.0))
    monkeypatch.setattr(K, "COCS", (0.10,))
    w = _weeks_frame()
    rec = K.weekly_record(w, sold=True)
    assert len(rec["week"]) == 156 and rec["expected"][0] == pytest.approx(3 * 1200.0)
    r = K.run(w, 10.0, n_sim=40)
    for view in ("all_overnight_risk", "sold_within_cap"):
        v = r[view]
        assert set(v["grid"]) == {"expense25_attachnone_coc10", "expense25_attach100_coc10"} and v["weeks"] == 156
        assert 0 < v["diversification"]["ratio"] < 1 and v["annual_loss_ratio_at_current_price"]["var95_mean"] > v["annual_loss_ratio_at_current_price"]["mean"]


def test_economics_raises_premium_and_leaves_claims():
    e = K.economics(0.75, 10.0)
    assert e["loading_1.00"]["expense10"] == pytest.approx(10 - 7.5 - 1.0)
    assert e["loading_1.16"]["expense25"] == pytest.approx(11.6 - 7.5 - 0.25 * 11.6)


def test_part_7c_quotes_the_numbers_in_the_results_file():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    r = json.loads((root / "results" / "risk_v6.json").read_text(encoding="utf-8"))
    text = (root / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7C."):]
    a, s = r["all_overnight_risk"], r["sold_within_cap"]
    assert a["weeks"] == s["weeks"] == 306 and "**306 weeks**" in part
    pct = lambda x: f"{100 * x:.1f}%"
    for v in (a, s):
        assert pct(v["pooled_loss_ratio_at_current_price"]) in part
    assert f"{a['weekly_loss_ratio']['weeks_above_100']} of 306 | {s['weekly_loss_ratio']['weeks_above_100']} of 306" in part
    assert f"{100 * a['weekly_loss_ratio']['worst']:.0f}% | {100 * s['weekly_loss_ratio']['worst']:.0f}%" in part
    for v, other in ((a, "all"), (s, "sold")):
        q = v["annual_loss_ratio_at_current_price"]
    assert f"{pct(a['annual_loss_ratio_at_current_price']['mean'])}, {pct(a['annual_loss_ratio_at_current_price']['var90_mean'])}, {pct(a['annual_loss_ratio_at_current_price']['var95_mean'])}" in part
    assert f"{pct(s['annual_loss_ratio_at_current_price']['mean'])}, {pct(s['annual_loss_ratio_at_current_price']['var90_mean'])}, {pct(s['annual_loss_ratio_at_current_price']['var95_mean'])}" in part
    sl = lambda v: ", ".join(pct(v["stop_loss_at_current_price"][k]) for k in ("attach_90%", "attach_100%", "attach_120%"))
    assert sl(a) in part and sl(s) in part
    assert f"| {a['diversification']['ratio']:.2f} | {s['diversification']['ratio']:.2f} |" in part
    for e in (10, 25, 35):
        row = [l for l in part.splitlines() if l.startswith(f"| {e}% |")][0]
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[1] == f"{a['grid'][f'expense{e}_attachnone_coc10']['loading_vs_current']:.2f}" and cells[2] == f"{s['grid'][f'expense{e}_attachnone_coc10']['loading_vs_current']:.2f}"
        assert cells[3] == f"{s['grid'][f'expense{e}_attach100_coc10']['loading_vs_current']:.2f}", row
    caps = [g["capital_margin"] for v in (a, s) for g in v["grid"].values()]
    assert f"{100 * min(caps):.1f}% to {100 * max(caps):.1f}%" in part
    eco = s["economics"]
    assert f"${eco['loading_1.00']['expense25']:.2f} a policy" in part and f"${eco['loading_1.16']['expense25']:.2f}" in part and f"${eco['loading_1.16']['expense35']:.2f}" in part
    assert eco["loading_1.00"]["expense35"] < 0 and f"**−${abs(eco['loading_1.00']['expense35']):.2f}**" in part


def test_more_hubs_cannot_push_the_spread_below_the_square_root_of_the_correlation():
    p = K.more_hubs_projection(0.25, n_now=5, candidates=(1, 5, 10, 1000))
    assert p["ratio_by_hubs"]["1"] == pytest.approx(1.0) and p["ratio_by_hubs"]["5"] == pytest.approx(np.sqrt(0.4))
    assert p["floor"] == pytest.approx(0.5) and p["ratio_by_hubs"]["1000"] == pytest.approx(0.5, abs=0.001)
    assert K.more_hubs_projection(0.0, candidates=(4,))["ratio_by_hubs"]["4"] == pytest.approx(0.5)       # independent hubs: 1 / sqrt(n)
    assert K.more_hubs_projection(1.0, candidates=(4,))["ratio_by_hubs"]["4"] == pytest.approx(1.0)       # identical hubs: no gain


def test_yearly_loss_ratios_keep_only_years_with_enough_months():
    import pandas as pd
    rows = []
    for ym, lr in [(f"2019-{m:02d}", 0.7) for m in range(1, 13)] + [(f"2020-{m:02d}", 0.5) for m in (1, 2)] + [(f"2022-{m:02d}", 0.6) for m in range(1, 11)]:
        for sold in (False, True):
            rows.append({"ym": ym, "sold": sold, "premium": 100.0, "claims": 100.0 * lr * (1.1 if sold else 1.0)})
    r = K.yearly_loss_ratios(pd.DataFrame(rows))
    assert set(r["years"]) == {"2019", "2022"} and r["years"]["2019"]["months"] == 12
    assert r["years"]["2019"]["sold"] == pytest.approx(0.77) and r["years"]["2022"]["all"] == pytest.approx(0.6 * (1 + 1.1) / 2)
    assert r["sold_mean"] == pytest.approx((0.77 + 0.66) / 2)


def _weeks(arm_months, sold_weight=1.0, premium=100.0, claims=65.0):
    import pandas as pd
    rows = []
    for i, ym in enumerate(arm_months):
        for sold in (False, True):
            rows.append({"ym": ym, "week": f"{ym}-01", "hub": "ATL", "sold": sold, "claims": claims, "expected": 65.0, "w": 2.0 if not sold else sold_weight, "premium": premium})
    return pd.DataFrame(rows)


def test_the_pandemic_months_are_left_out_of_an_arms_record_and_reach_counts_only_scored_months():
    w = _weeks(["2019-05", "2020-02", "2020-03", "2021-06", "2021-07"], sold_weight=1.0)
    kept = K.without_pandemic(w)
    assert sorted(kept["ym"].unique()) == ["2019-05", "2020-02", "2021-07"]
    reach = K.reach_by_year(w)
    assert reach == {"2019": pytest.approx(1 / 3), "2020": pytest.approx(1 / 3), "2021": pytest.approx(1 / 3)}
    dev = _weeks(["2024-03"])
    assert sorted(K.arm_record(w, dev)["ym"].unique()) == ["2019-05", "2020-02", "2021-07", "2024-03"]


def test_the_seasonal_price_divides_claims_by_the_multiplied_premium_and_counts_months_above_100():
    import pandas as pd
    rec = pd.DataFrame({"ym": ["2025-06", "2025-06", "2025-11", "2025-11"], "sold": [True, True, True, True], "claims": [150.0, 150.0, 40.0, 40.0], "premium": [100.0, 100.0, 100.0, 100.0]})
    out = K.seasonal_sold(rec, {"06": 2.0, "11": 0.5})
    assert out["pooled_loss_ratio"] == pytest.approx(380 / (400 + 100))
    assert out["months_above_100_existing_price"] == 1 and out["months_above_100"] == 0
    assert out["summer_months"] == 1 and out["summer_above_100"] == 0 and out["summer_above_100_existing_price"] == 1


def test_part_7j_quotes_the_numbers_in_the_results_file():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    d = json.loads((root / "results" / "arm_sensitivity.json").read_text(encoding="utf-8"))
    text = (root / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7J."):]
    for arm in "ABCD":
        x = d[arm]
        sold_rows = [l for l in part.splitlines() if l.startswith(f"| {arm} | ") and "%" in l.split("|")[2]]
        cells = [c.strip() for c in sold_rows[0].strip().strip("|").split("|")]
        assert cells[1:] == [f"{100 * x['sold']['pooled_loss_ratio']:.1f}%", str(x["sold"]["weeks_above_100"]), f"{x['sold']['loading_expense35']:.3f}", f"{x['sold']['loading_expense35_attach100']:.3f}", f"{x['all']['loading_expense35']:.3f}"], sold_rows[0]
        reach = [l for l in part.splitlines() if l.startswith(f"| {arm} | 0.")][0]
        assert [c.strip() for c in reach.strip().strip("|").split("|")][1:] == [f"{x['share_sold_by_year'][y]:.3f}" for y in ("2019", "2020", "2021", "2022", "2023")], reach
        f = x["at_frozen_multipliers_as_sold"]
        fr = [l for l in part.splitlines() if l.startswith(f"| {arm} | ") and l.count("|") == 5 and l.split("|")[2].strip().isdigit()][0]
        assert [c.strip() for c in fr.strip().strip("|").split("|")][1:] == [str(f["months_above_100_existing_price"]), str(f["months_above_100"]), f"{100 * f['pooled_loss_ratio']:.1f}%"], fr
    assert d["B"]["sold"]["loading_expense35"] > 1.10 and d["A"]["sold"]["loading_expense35"] < 1.05
    for arm in "BCD":
        assert 1.10 <= round(d[arm]["sold"]["loading_expense35"], 2) <= 1.13


def _hedge_frames(h=0.5, noise=0.0, seed=0, later_shift=0.0):
    import pandas as pd
    rng = np.random.default_rng(seed)
    weeks = [str(d.date()) for d in pd.date_range("2022-01-03", periods=160, freq="7D")]
    x = rng.gamma(2.0, 0.1, 160)
    y = 0.4 + h * x + rng.normal(0, noise, 160)
    risk, trig = [], []
    for w, xv, yv in zip(weeks, x, y):
        late = later_shift if w >= K.HEDGE_SPLIT else 0.0
        risk.append({"week": w, "sold": True, "claims": (yv + late) * 100.0, "expected": 30.0, "premium": 100.0})
        risk.append({"week": w, "sold": False, "claims": 50.0, "expected": 70.0, "premium": 200.0})
        trig.append({"week": w, "t2": xv * 100.0})
    return pd.DataFrame(risk), pd.DataFrame(trig)


def test_the_hedge_ratio_is_recovered_and_a_perfect_index_removes_the_weekly_spread():
    risk, trig = _hedge_frames(h=0.5)
    table = K.hedge_table(risk, trig)
    assert table["x"].iloc[0] == pytest.approx(trig["t2"].iloc[0] / 100.0)
    fit = K.fit_hedge(table)
    assert fit["h"] == pytest.approx(0.5) and fit["cost_per_premium"] == pytest.approx(0.5 * fit["x_mean_fit"])
    later = K.apply_hedge(table, fit)
    assert later["sd_hedged"] == pytest.approx(0.0, abs=1e-9) and later["sd_remaining_share"] < 1e-6


def test_weeks_after_the_split_cannot_change_the_hedge_ratio_or_its_cost():
    risk, trig = _hedge_frames(h=0.5, noise=0.05)
    base = K.fit_hedge(K.hedge_table(risk, trig))
    risk2, trig2 = risk.copy(), trig.copy()
    risk2.loc[risk2["week"] >= K.HEDGE_SPLIT, "claims"] *= 3
    trig2.loc[trig2["week"] >= K.HEDGE_SPLIT, "t2"] *= 5
    assert K.fit_hedge(K.hedge_table(risk2, trig2)) == base


def test_a_level_shift_after_the_split_is_not_hedged_away():
    risk, trig = _hedge_frames(h=0.5, later_shift=0.2)
    table = K.hedge_table(risk, trig)
    later = K.apply_hedge(table, K.fit_hedge(table))
    assert later["pooled_hedged"] - later["net_paid_per_premium"] * 0 > 0.55 and later["pooled_unhedged"] - later["pooled_hedged"] == pytest.approx(later["net_paid_per_premium"])


def test_the_two_sources_of_the_weekly_record_are_on_the_scale_the_sampling_fractions_say():
    import pandas as pd
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    risk = pd.read_csv(root / "results" / "risk_weeks_2019_2026.csv")
    for name, source in (("2019_2023", "backcast_2019_2023"), ("2024_2026", "development_2024_2026")):
        t = pd.read_csv(root / "results" / f"trigger_weeks_{name}.csv").set_index("week")
        claims = risk[risk["source"] == source].groupby("week")["claims"].sum()
        j = t.join(claims, how="inner")
        assert j["gap"].sum() / j["claims"].sum() == pytest.approx(1 / K.SAMPLE_FRACTION[source], rel=0.02)


def test_part_7n_quotes_the_numbers_in_the_hedge_file():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    d = json.loads((root / "results" / "trigger_hedge.json").read_text(encoding="utf-8"))
    text = (root / "VALIDATION.md").read_text(encoding="utf-8")
    part = text[text.index("### 7N."):]
    f = d["fit"]
    assert f"The hedge ratio is {f['h']:.2f} and the cost is {100 * f['cost_per_premium']:.1f}% of premium" in part and f"({f['weeks_fit']} weeks" in part
    for name, x in (("2019 to 2023, where it was fitted", d["in_sample"]), ("July 2024 to August 2026, applied unchanged", d["later"])):
        row = [l for l in part.splitlines() if l.startswith(f"| {name} |")][0]
        assert [c.strip() for c in row.strip("|").split("|")][1:] == [str(x["weeks"]), f"{x['sd_unhedged']:.3f}", f"{x['sd_hedged']:.3f}", f"{100 * x['sd_remaining_share']:.0f}%",
                                                                       str(x["weeks_above_100_unhedged"]), str(x["weeks_above_100_hedged"]), f"{100 * x['worst_unhedged']:.0f}%",
                                                                       f"{100 * x['worst_hedged']:.0f}%", f"{100 * x['pooled_unhedged']:.1f}%", f"{100 * x['pooled_hedged']:.1f}%"]
    assert f"paid {100 * d['later']['net_paid_per_premium']:.1f} points" in part
    assert 0.6 < d["later"]["sd_remaining_share"] < 0.8 and d["later"]["weeks_above_100_hedged"] * 2 == d["later"]["weeks_above_100_unhedged"]
    recomputed = K.hedge_table(__import__("pandas").read_csv(root / "results" / "risk_weeks_2019_2026.csv"),
                               __import__("pandas").concat([__import__("pandas").read_csv(root / "results" / f"trigger_weeks_{n}.csv") for n in ("2019_2023", "2024_2026")]))
    assert K.fit_hedge(recomputed)["h"] == pytest.approx(f["h"])
