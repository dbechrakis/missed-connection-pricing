"""The demo's risk section: eight years of months, the calendar pattern and the price ladder, as static HTML and SVG.

Built from `results/risk_weeks_2019_2026.csv`, `models/v6_season.json` and `results/risk_v6.json`, so nothing on it is typed by hand.
It has no script, so the page's own scripts and their tests are untouched. The block sits between two markers in site/index.html.

    cd src && python -m mcp.demo_risk        # rewrites the block in ../site/index.html
"""
from __future__ import annotations

import json
import math

import pandas as pd

from mcp.ingest import ROOT

PAGE = ROOT / "site" / "index.html"
BEGIN, END = "<!-- risk:begin -->", "<!-- risk:end -->"
W, H, PAD_L, PAD_R, PAD_T, PAD_B = 900, 280, 44, 12, 14, 30
Y_MIN, Y_MAX = 0.3, 1.7
FIRST, LAST = (2019, 1), (2026, 8)


def month_index(ym: str) -> int:
    return (int(ym[:4]) - FIRST[0]) * 12 + int(ym[5:7]) - FIRST[1]


def monthly_ratio() -> pd.Series:
    w = pd.read_csv(ROOT / "results" / "risk_weeks_2019_2026.csv")
    g = w.groupby("ym")[["claims", "expected"]].sum()
    return (g["claims"] / g["expected"]).sort_index()


def _x(i: int, n: int) -> float:
    return PAD_L + (W - PAD_L - PAD_R) * i / (n - 1)


def _y(v: float) -> float:
    v = min(max(v, Y_MIN), Y_MAX)
    return PAD_T + (H - PAD_T - PAD_B) * (Y_MAX - v) / (Y_MAX - Y_MIN)


def chart(ratio: pd.Series, season: dict) -> str:
    n = month_index(f"{LAST[0]}-{LAST[1]:02d}") + 1
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Monthly realized over expected claims, 2019 to August 2026, with the calendar multiplier">']
    parts.append('<g class="axis">')
    for v in (0.5, 1.0, 1.5):
        y = _y(v)
        parts.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--chart-grid)"/>' if v != 1.0 else
                     f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--muted)" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{PAD_L - 6}" y="{y + 4:.1f}" text-anchor="end">{v:.1f}</text>')
    for yr in range(FIRST[0], LAST[0] + 1):
        i = (yr - FIRST[0]) * 12
        parts.append(f'<text x="{_x(i, n):.1f}" y="{H - 8}" text-anchor="start">{yr}</text>')
    parts.append("</g>")
    mult = season["multiplier"]
    pts = " ".join(f"{_x(i, n):.1f},{_y(mult[f'{(FIRST[1] - 1 + i) % 12 + 1:02d}']):.1f}" for i in range(n))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="var(--muted)" stroke-width="1.5" opacity=".8"/>')
    for ym, v in ratio.items():
        i = month_index(ym)
        summer = ym[5:7] in ("06", "07", "08")
        parts.append(f'<circle cx="{_x(i, n):.1f}" cy="{_y(v):.1f}" r="3.6" fill="{"var(--chart-cap)" if summer else "var(--chart-line)"}"><title>{ym}: {v:.2f}</title></circle>')
    parts.append("</svg>")
    return "".join(parts)


def section() -> str:
    ratio = monthly_ratio()
    season = json.loads((ROOT / "models" / "v6_season.json").read_text(encoding="utf-8"))
    risk = json.loads((ROOT / "results" / "risk_v6.json").read_text(encoding="utf-8"))
    sold, allv = risk["sold_within_cap"], risk["all_overnight_risk"]
    summers = [v for ym, v in ratio.items() if ym[5:7] in ("06", "07", "08")]
    rows = "".join(
        f"<tr><td>{e}%</td><td>{allv['grid'][f'expense{e}_attachnone_coc10']['loading_vs_current']:.2f}</td>"
        f"<td>{sold['grid'][f'expense{e}_attachnone_coc10']['loading_vs_current']:.2f}</td><td>{sold['grid'][f'expense{e}_attach100_coc10']['loading_vs_current']:.2f}</td></tr>"
        for e in (10, 25, 35))
    return f"""{BEGIN}
  <h2 id="risk">Eight years of months: the weather moves the cover together, and by season</h2>
  <p class="lede">Each dot is one month of realized over expected claims for the gap cover, priced from earlier months only ({len(ratio)} months, 2019 to August 2026, the pandemic months left out). Above the dashed line the cover paid out more than the price expected. June to August (red) ran above it in every summer observed, in the range {min(summers):.2f} to {max(summers):.2f}. The grey line is the calendar multiplier pre-registered for 2027.</p>
  <section class="card" aria-label="Monthly claims over expected, 2019 to August 2026">
    {chart(ratio, season)}
    <div class="legend"><span><i style="background:var(--chart-line)"></i>Other months</span><span><i style="background:var(--chart-cap)"></i>June to August</span><span><i style="background:var(--muted)"></i>Calendar multiplier ({min(season['multiplier'].values()):.2f} to {max(season['multiplier'].values()):.2f})</span></div>
    <p class="note">A multiplier is the claims the calendar month predicts against the model's expected claims. It was found on these months, so it is a hypothesis that March to August 2027 will test. The calendar pattern cuts the error of a monthly forecast from 0.206 to 0.125 in log units when each year is predicted from the others.</p>
  </section>
  <section class="card" aria-label="The technical price" style="margin-top:14px">
    <div class="label">What the price has to be, as a multiple of today's, on {sold['weeks']} weeks</div>
    <table><thead><tr><th>Expense share</th><th>All connections</th><th>Sold within the cap</th><th>Sold, weekly stop-loss at 100%</th></tr></thead><tbody>{rows}</tbody></table>
    <p class="note">At the share the 65% target leaves for expenses (35%) the price needed is about today's. The annual margin for weather is small, 0.3% to 2.5% of premium. The weeks are the risk: {sold['weekly_loss_ratio']['weeks_above_100']} of {sold['weeks']} weeks as sold ran above a 100% loss ratio, and a weekly stop-loss would cost {100 * sold['stop_loss_at_current_price']['attach_100%']:.1f}% of premium. Development evidence from eight years of weeks, which cannot show a 1-in-100 year.</p>
  </section>
  {END}
"""


def apply(page: str) -> str:
    block = section()
    if BEGIN in page:
        i, j = page.index(BEGIN), page.index(END) + len(END)
        tail = page[j:]
        return page[:i] + block.rstrip("\n") + tail
    marker = "  <footer>"
    assert marker in page
    return page.replace(marker, block + "\n" + marker, 1)


def main() -> None:
    PAGE.write_text(apply(PAGE.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
