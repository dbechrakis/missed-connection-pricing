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
