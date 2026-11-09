"""The v3 demo table: overnight rows only, price = p x GSA cost / target, share within the cap per month."""
import numpy as np
import pandas as pd
import pytest

from mcp.v3 import DEMO_MONTHS, TARGET_LR, WTP_CAP, demo_cells


def test_demo_cells_use_only_overnight_rows_and_the_month_cost():
    table = {"ORD": {2027: {"lodging": {m: 100.0 for m in range(1, 13)}, "mie": 50.0}}}
    df = pd.DataFrame({"hub": ["ORD"] * 4, "slack_min": [50, 55, 50, 120], "overnight": [1, 1, 0, 1],
                       "fare": [400.0, 400.0, 400.0, 400.0], "weight": [1.0, 3.0, 1.0, 1.0], "p": [0.04, 0.2, 0.9, 0.1]})
    cells = {c["slack"]: c for c in demo_cells(df, table)}
    assert set(cells) == {45, 120}                                        # the overnight=0 row is dropped
    c = cells[45]
    assert c["p"] == pytest.approx((0.04 + 3 * 0.2) / 4) and c["n"] == 2
    jan = c["months"]["2027-01"]
    assert jan["cost"] == 150.0
    # prices: 0.04*150/0.65 = 9.2 (within 5% of 400 = 20), 0.2*150/0.65 = 46 (not): weight 1 of 4
    assert jan["within_cap"] == pytest.approx(0.25)
    assert 0.04 * 150 / TARGET_LR <= WTP_CAP * 400 < 0.2 * 150 / TARGET_LR
    assert len(DEMO_MONTHS) == 12 and DEMO_MONTHS[0] == (2026, 10) and DEMO_MONTHS[-1] == (2027, 9)


def test_the_published_v3_demo_file_matches_the_development_results_and_the_page_loads_it():
    import json
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    d = json.loads(re.sub(r"^window\.PRICES_V3 = |;\s*$", "", (root / "site" / "prices_v3.js").read_text(encoding="utf-8")))
    dev = json.loads((root / "results" / "v3_dev.json").read_text())["results"]["primary"]
    assert d["dev"]["ratio"]["ratio"] == pytest.approx(dev["overall"]["ratio"])
    assert d["months"] == [f"{y}-{m:02d}" for y, m in DEMO_MONTHS]
    assert {c["hub"] for c in d["cells"]} == {"ATL", "CLT", "DEN", "DFW", "ORD"} and len(d["cells"]) == 60
    assert all(0 <= v["within_cap"] <= 1 for c in d["cells"] for v in c["months"].values())
    page = (root / "site" / "index.html").read_text(encoding="utf-8")
    assert '<script src="prices_v3.js"></script>' in page and 'toLocaleString("en-US")' in page and "toLocaleString()" not in page


def test_product_brief_gap_cover_ranges_match_the_demo_file():
    import json
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    d = json.loads(re.sub(r"^window\.PRICES_V3 = |;\s*$", "", (root / "site" / "prices_v3.js").read_text(encoding="utf-8")))
    brief = (root / "docs" / "product-brief.md").read_text(encoding="utf-8")
    rng = lambda s, f: [f(c, v) for c in d["cells"] if c["slack"] == s for v in c["months"].values()]
    price = lambda c, v: c["p"] * v["cost"] / TARGET_LR
    lo, hi = rng(210, price), rng(45, price)
    assert f"${min(lo):.0f} to ${max(lo):.0f} for long" in brief and f"${min(hi):.0f} to ${max(hi):.0f} for the tightest" in brief
    fit = rng(210, lambda c, v: v["within_cap"])
    assert f"{min(fit):.0%} to {max(fit):.0%} of the time" in brief


def test_the_demo_leads_with_the_gap_cover_and_its_strip_is_filled_from_the_results():
    import json
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    page = (root / "site" / "index.html").read_text(encoding="utf-8")
    d = json.loads(re.sub(r"^window\.PRICES_V3 = |;\s*$", "", (root / "site" / "prices_v3.js").read_text(encoding="utf-8")))["audit"]
    assert page.index('id="found"') < page.index('id="gap-cover"') < page.index('id="blanket"') < page.index("What this does not tell you")
    for ident in ("f-gap", "f-sold", "f-load", "f-months", "g-mct", "g-sold", "mct-note", "banner", "m-price"):
        assert f'id="{ident}"' in page, ident
    causes = json.loads((root / "results" / "causes_v3.json").read_text())["all_misses"]
    loading = json.loads((root / "results" / "v3_loading.json").read_text())
    assert d["gap_shares"]["strict"] == causes["gap_strict"] and d["gap_shares"]["broad"] == causes["gap_broad"]
    assert d["loading"]["lambda"] == loading["frozen"]["lambda"] == 1.16
    assert d["loading"]["loaded_loss_ratio_out_of_sample"] == loading["loaded"]["loss_ratio"]
    assert "SCOREBOARD.md" in page and "decision-memo.md" in page
