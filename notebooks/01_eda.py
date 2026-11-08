# %% [markdown]
# # 01 — EDA: what drives a missed connection (train + validation months only)
#
# Plain `.py` with `# %%` cells: runs as a script (`python notebooks/01_eda.py`) and opens as a
# notebook in VS Code / Jupytext. Figures go to `docs/figures/`, numbers to `results/eda.json`.
#
# **Leakage rule:** every query is restricted with `split.where("TRAIN")` (Jan 2024 – Jun 2025).
# The test window (Jul – Dec 2025) is not read anywhere in this file.

# %%
import json
import sys
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mcp.connections import OUT, WEIGHTED, WEIGHTS  # noqa: E402
from mcp.model import cells, fit_rates, predict, reliability  # noqa: E402
from mcp.split import where  # noqa: E402

FIG = ROOT / "docs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
con = duckdb.connect()
W45 = (WEIGHTED / "mct=45" / "*" / "*.parquet").as_posix()
TRAIN = where("TRAIN")
HUBS = ["ATL", "CLT", "DEN", "DFW", "ORD"]
# One categorical palette (colour-blind safe, Okabe-Ito), one colour per hub in every figure.
COL = dict(zip(HUBS, ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00"]))
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.alpha": 0.25, "figure.dpi": 130, "font.size": 10})
facts: dict = {}


def q(sql):
    return con.execute(sql).fetchall()


# %% [markdown]
# ## 1. Miss rate by slack, per hub (passenger-weighted)
# The whole product rests on this curve falling with slack. A flat curve would mean there is
# nothing to price.

# %%
rows = q(f"""SELECT hub, (slack_min - 45) // 15 AS b, sum(weight*missed::INT)/sum(weight) AS r
             FROM read_parquet('{W45}') WHERE {TRAIN} GROUP BY ALL ORDER BY 1, 2""")
fig, ax = plt.subplots(figsize=(7, 4))
ends = {}
for h in HUBS:
    xs = [45 + 15 * b for hh, b, _ in rows if hh == h]
    ys = [r * 100 for hh, _, r in rows if hh == h]
    ax.plot(xs, ys, color=COL[h], lw=2)
    ends[h] = (xs[-1], ys[-1])
gap, last = 1.3, None  # nudge end labels apart (data units, %) so they stay readable
for h in sorted(HUBS, key=lambda k: ends[k][1]):
    y = ends[h][1] if last is None else max(ends[h][1], last + gap)
    ax.annotate(h, (ends[h][0], y), xytext=(5, 0), textcoords="offset points", color=COL[h], va="center")
    last = y
ax.set(xlabel="Scheduled slack (minutes, start of 15-min bucket)", ylabel="Missed connections (%)",
       title="Miss rate falls steeply with slack, at every hub")
ax.set_xlim(45, 235)
fig.tight_layout()
fig.savefig(FIG / "miss_by_slack.png")
facts["miss_by_slack_pct"] = {f"{h}|{45 + 15 * b}": round(r * 100, 2) for h, b, r in rows}

# %% [markdown]
# ## 2. Time of day of the outbound flight
# The last departures of the day cost far more when missed (severity, step 6), and delays
# accumulate through the day. Both argue for hour as a feature.

# %%
rows = q(f"""SELECT hour(out_sched_dep) h, sum(weight*missed::INT)/sum(weight) r, sum(weight) w
             FROM read_parquet('{W45}') WHERE {TRAIN} GROUP BY 1 ORDER BY 1""")
total_w = sum(r[2] for r in rows)
rows = [r for r in rows if r[2] / total_w >= 0.002]  # hours 0-4 hold <0.2% of weight: noise, not shown
fig, ax = plt.subplots(figsize=(7, 3.6))
ax.bar([r[0] for r in rows], [r[1] * 100 for r in rows], color="#0072B2")
ax.set(xlabel="Outbound scheduled departure hour (hub local; hours 0-6 hold <0.2% of passengers, hidden)",
       ylabel="Missed connections (%)",
       xticks=range(7, 24, 2), title="Early and late departures miss most")
fig.tight_layout()
fig.savefig(FIG / "miss_by_hour.png")
facts["miss_by_hour_pct"] = {int(h): round(r * 100, 2) for h, r, _ in rows}

# %% [markdown]
# ## 3. Seasonality
# Only 18 train months, so each calendar month in H1 appears twice and H2 once. Any month
# feature learns the 2024 pattern for Jul–Dec and is tested on 2025: that is the honest setup.

# %%
rows = q(f"""SELECT year(out_sched_dep) y, month(out_sched_dep) m, sum(weight*missed::INT)/sum(weight) r
             FROM read_parquet('{W45}') WHERE {TRAIN} GROUP BY ALL ORDER BY 1, 2""")
fig, ax = plt.subplots(figsize=(7, 3.6))
for y, c in ((2024, "#0072B2"), (2025, "#D55E00")):
    xs = [m for yy, m, _ in rows if yy == y]
    ys = [r * 100 for yy, _, r in rows if yy == y]
    ax.plot(xs, ys, marker="o", color=c, lw=2)
    ax.annotate(str(y), (xs[-1], ys[-1]), xytext=(5, 0), textcoords="offset points", color=c, va="center")
ax.set(xlabel="Month", ylabel="Missed connections (%)", xticks=range(1, 13),
       title="Miss rate swings between about 5% and 12% by month")
fig.tight_layout()
fig.savefig(FIG / "miss_by_month.png")
facts["miss_by_month_pct"] = {f"{y}-{m:02d}": round(r * 100, 2) for y, m, r in rows}

# %% [markdown]
# ## 4. Carrier

# %%
rows = q(f"""SELECT carrier, sum(weight*missed::INT)/sum(weight) r, sum(weight) w
             FROM read_parquet('{W45}') WHERE {TRAIN} GROUP BY 1 ORDER BY 3 DESC LIMIT 8""")
fig, ax = plt.subplots(figsize=(7, 3.6))
ax.barh([r[0] for r in rows][::-1], [r[1] * 100 for r in rows][::-1], color="#0072B2")
ax.set(xlabel="Missed connections (%)", title="Carriers differ, regionals worst (top 8 by passengers)")
fig.tight_layout()
fig.savefig(FIG / "miss_by_carrier.png")
facts["miss_by_carrier_pct"] = {c: round(r * 100, 2) for c, r, _ in rows}

# %% [markdown]
# ## 5. Does dropping unmatched routes bias the sample?
# 22% of synthetic connections have no DB1B route and carry no weight. If those pairings
# miss at a very different rate, the weighted view is not representative.

# %%
rows = q(f"""
SELECT k.hub, w.passengers IS NOT NULL AS matched, count(*) n, avg(k.missed::INT) r
FROM read_parquet('{(OUT / "mct=45" / "*" / "*.parquet").as_posix()}') k
LEFT JOIN read_parquet('{WEIGHTS.as_posix()}') w
  ON k.carrier = w.carrier AND k.origin = w.origin AND k.hub = w.hub AND k.destination = w.destination
WHERE k.status = 'ok' AND {where("TRAIN", "k.out_sched_dep")}
GROUP BY ALL ORDER BY 1, 2""")
cov = {}
for h in HUBS:
    m = {mt: (n, r) for hh, mt, n, r in rows if hh == h}
    cov[h] = {"matched_share_pct": round(100 * m[True][0] / (m[True][0] + m[False][0]), 1),
              "miss_matched_pct": round(100 * m[True][1], 2), "miss_unmatched_pct": round(100 * m[False][1], 2)}
facts["coverage_by_hub"] = cov
for h, v in cov.items():
    print(h, v)

# %% [markdown]
# ## 6. MCT sensitivity of the label (unweighted, train window)

# %%
sens = {}
for mct in (35, 45, 60):
    glob = (OUT / f"mct={mct}" / "*" / "*.parquet").as_posix()
    n, r = q(f"SELECT count(*), avg(missed::INT) FROM read_parquet('{glob}') WHERE status='ok' AND {TRAIN}")[0]
    sens[mct] = {"connections": int(n), "miss_rate_pct": round(100 * r, 2)}
facts["mct_sensitivity"] = sens
print(sens)

# %% [markdown]
# ## 7. Baseline reliability on the validation window (fit on 2024)
# Points near the diagonal mean the stated probability matches the observed frequency, which is
# what the price (probability × money) needs.

# %%
fit, valid = cells("FIT"), cells("VALID")
by = ("hub", "bucket")
p = predict(fit_rates(fit, by), valid, by)
rel = reliability(valid["W"], valid["Wy"], p)
fig, ax = plt.subplots(figsize=(4.6, 4.6))
top = max(max(r[0], r[1]) for r in rel) * 100 * 1.08
ax.plot([0, top], [0, top], color="#888", ls="--", lw=1)
ax.scatter([r[0] * 100 for r in rel], [r[1] * 100 for r in rel], color="#0072B2", zorder=3)
ax.set(xlabel="Predicted P(miss) (%)", ylabel="Observed miss rate (%)", xlim=(0, top), ylim=(0, top),
       title="Baseline reliability, Jan–Jun 2025", aspect="equal")
fig.tight_layout()
fig.savefig(FIG / "baseline_reliability.png")
facts["baseline_reliability"] = [[round(a * 100, 2), round(b * 100, 2)] for a, b, _ in rel]

# %%
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "eda.json").write_text(json.dumps(facts, indent=2))
print("saved", sorted(p.name for p in FIG.glob("*.png")))
