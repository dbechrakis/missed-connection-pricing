"""The demo's risk section is built from the results files, has no script, and cannot drift from them."""
import json
import re
from pathlib import Path

import pandas as pd

from mcp import demo_risk as D

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "site" / "index.html").read_text(encoding="utf-8")


def block():
    return PAGE[PAGE.index(D.BEGIN):PAGE.index(D.END) + len(D.END)]


def test_the_page_carries_the_block_once_and_it_equals_what_the_code_builds():
    assert PAGE.count(D.BEGIN) == 1 and PAGE.count(D.END) == 1
    assert D.apply(PAGE) == PAGE                                        # rebuilding changes nothing
    assert block().rstrip() == D.section().rstrip()


def test_the_block_has_no_script_and_sits_inside_the_main_element_before_the_footer():
    assert "<script" not in block() and "onclick" not in block().lower()
    assert PAGE.index("<main>") < PAGE.index(D.BEGIN) < PAGE.index("<footer>") < PAGE.index("</main>")
    assert PAGE.count('<script src="prices.js"></script>') == 1 and PAGE.count('<script src="prices_v3.js"></script>') == 1       # the page's own scripts are untouched


def test_every_dot_is_a_month_of_the_record_and_the_numbers_in_the_text_are_the_results():
    ratio = D.monthly_ratio()
    b = block()
    dots = re.findall(r'<circle cx="[\d.]+" cy="[\d.]+" r="3.6" fill="([^"]+)"><title>(\d{4}-\d{2}): ([\d.]+)</title>', b)
    assert len(dots) == len(ratio) == 70
    assert all(abs(float(v) - ratio[m]) < 0.006 for _, m, v in dots)
    red = [m for c, m, _ in dots if "chart-cap" in c]
    assert red and all(m[5:7] in ("06", "07", "08") for m in red) and len(red) == sum(1 for m in ratio.index if m[5:7] in ("06", "07", "08"))
    assert not any("2020-0" in m and m >= "2020-03" for _, m, _ in dots) and not any(m in ("2021-03", "2021-05") for _, m, _ in dots)      # pandemic months are absent
    summers = [v for m, v in ratio.items() if m[5:7] in ("06", "07", "08")]
    assert f"{min(summers):.2f} to {max(summers):.2f}" in b and f"({len(ratio)} months" in b
    risk = json.loads((ROOT / "results" / "risk_v6.json").read_text(encoding="utf-8"))["sold_within_cap"]
    assert f"{risk['weekly_loss_ratio']['weeks_above_100']} of {risk['weeks']} weeks as sold" in b and f"{100 * risk['stop_loss_at_current_price']['attach_100%']:.1f}% of premium" in b
    season = json.loads((ROOT / "models" / "v6_season.json").read_text(encoding="utf-8"))["multiplier"]
    assert f"{min(season.values()):.2f} to {max(season.values()):.2f}" in b
    rows = re.findall(r"<tr><td>(\d+)%</td><td>([\d.]+)</td><td>([\d.]+)</td><td>([\d.]+)</td></tr>", b)
    assert [r[0] for r in rows] == ["10", "25", "35"]
    allv = json.loads((ROOT / "results" / "risk_v6.json").read_text(encoding="utf-8"))["all_overnight_risk"]
    for e, a, s, sl in rows:
        assert a == f"{allv['grid'][f'expense{e}_attachnone_coc10']['loading_vs_current']:.2f}" and s == f"{risk['grid'][f'expense{e}_attachnone_coc10']['loading_vs_current']:.2f}"
        assert sl == f"{risk['grid'][f'expense{e}_attach100_coc10']['loading_vs_current']:.2f}"


def test_the_chart_keeps_every_point_inside_the_drawing():
    for m in re.finditer(r'<circle cx="([\d.]+)" cy="([\d.]+)"', block()):
        assert 0 <= float(m.group(1)) <= D.W and 0 <= float(m.group(2)) <= D.H
    assert D._y(5.0) == D._y(D.Y_MAX) and D._y(0.0) == D._y(D.Y_MIN)
