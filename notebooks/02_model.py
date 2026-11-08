# %% [markdown]
# # 02 — The model: what was tried, what won, how good it really is
#
# Plain `.py` with `# %%` cells (runs as a script or opens as a notebook). It reads only the published
# `results/*.json`, so it is fast and cannot disagree with the validation. Figures go to `docs/figures/`
# (override with the `MCP_FIG_DIR` environment variable).
#
# The question: how much does booking-time information improve on a plain hub × connection-time rate, and does
# the improvement survive data the model never saw?

# %%
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIG = Path(os.environ.get("MCP_FIG_DIR", ROOT / "docs" / "figures"))
FIG.mkdir(parents=True, exist_ok=True)
R = lambda name: json.loads((ROOT / "results" / name).read_text())
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
                     "figure.dpi": 130, "font.size": 10})
COL = {"baseline": "#888888", "v1_raw": "#E69F00", "v1_iso": "#D55E00", "v2_static": "#56B4E9", "v2_rolling": "#0072B2"}
LAB = {"baseline": "baseline 2024", "v1_raw": "v1 raw", "v1_iso": "v1 as shipped", "v2_static": "v2 static", "v2_rolling": "v2 rolling"}

# %% [markdown]
# ## 1. The ceiling is low, and that is the finding
# A baseline that only knows hub and connection time already beats a flat rate by about 5% on Brier score.
# Everything else a booking-time model can use adds only 1 to 2% on top. Most of what makes a connection fail
# (weather, a late aircraft, a closed runway) is not known when someone books.

# %%
base = R("baseline.json")["models"]
print("Brier score on Jan-Jun 2025 (fit on 2024), lower is better")
for name, m in base.items():
    print(f"  {name:28s} {m['brier']:.5f}   skill vs flat {m['brier_skill_vs_flat']:.1%}")
h = R("holdout.json")["scores"]
print("\nBrier score on the clean Jan-Aug 2026 holdout")
for m in LAB:
    print(f"  {LAB[m]:18s} {h[m]['brier']:.5f}   improvement over baseline {1 - h[m]['brier'] / h['baseline']['brier']:+.1%}")

# %% [markdown]
# ## 2. Which features earned their place (validation Jan–Mar 2025 only)
# Candidate feature sets were compared on one window and chosen there, never on the window used to calibrate.
# Dropping `month` and the weather climatology helped: one fit year cannot separate seasons from one-off events.

# %%
cand = R("final_model.json")
c = cand["valid1_candidates"]
ref = cand["valid1_reference_baseline"]["brier"]
names = list(c)
fig, ax = plt.subplots(figsize=(8.6, 3.8))
vals = [c[n]["brier"] for n in names]
# dots, not bars: the values sit far from zero and differ in the fourth decimal, so a truncated bar would exaggerate them
ax.hlines(range(len(names)), min(vals + [ref]) - 0.0002, vals, color="#cdd5dc", lw=1)
ax.scatter(vals, range(len(names)), s=70, color=["#0072B2" if n == cand["chosen"] else "#6b7b8a" for n in names], zorder=3)
ax.axvline(ref, color="#888", ls="--", lw=1.2, label="hub × connection-time baseline")
ax.legend(frameon=False, fontsize=8, loc="upper right")
spread = max(vals + [ref]) - min(vals)
ax.set(yticks=range(len(names)), yticklabels=names,
       xlabel="Brier score, Jan-Mar 2025 (lower is better)\nthe whole axis spans only %.4f" % spread,
       title="Feature sets compared on the selection window", xlim=(min(vals + [ref]) - 0.0002, max(vals + [ref]) + 0.0003))
ax.invert_yaxis()
fig.tight_layout()
fig.savefig(FIG / "model_feature_sets.png")
plt.close(fig)
print("chosen:", cand["chosen"])

# %% [markdown]
# ## 3. Calibration: the probability has to be right, not just well ranked
# A price multiplies a probability by money, so a model that ranks connections well but states 9% when 8% happened
# misprices every policy. On the 2026 holdout, by connection time:

# %%
by = R("holdout.json")["by_slack_bucket"]
xs = sorted(int(k) for k in by)
fig, ax = plt.subplots(figsize=(7.4, 4))
ax.plot(xs, [by[str(x)]["observed"] * 100 for x in xs], color="k", lw=2.5, marker="o", label="observed")
for m in ("baseline", "v1_iso", "v2_rolling"):
    ax.plot(xs, [by[str(x)][f"pred_{m}"] * 100 for x in xs], color=COL[m], lw=1.8, marker="o", ms=3.5, label=LAB[m])
ax.set(xlabel="Scheduled time between flights (minutes, start of 15-minute step)", ylabel="Missed connections (%)",
       title="2026 holdout: predicted against observed, by connection time")
ax.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(FIG / "holdout_by_slack.png")
plt.close(fig)
gap = {m: np.mean([abs(by[str(x)][f"pred_{m}"] / by[str(x)]["observed"] - 1) for x in xs]) for m in ("baseline", "v1_iso", "v2_rolling")}
print("mean absolute relative gap across connection times:", {LAB[k]: f"{v:.1%}" for k, v in gap.items()})

# %% [markdown]
# ## 4. All five prices on the three scores, 2026 holdout
# `ECE` (expected calibration error) is the average distance between the stated probability and what happened,
# in equal-weight bins. v2 with monthly recalibration is best on all three; v2 with a frozen calibrator has the
# right shape but the wrong level.

# %%
fig, axes = plt.subplots(1, 3, figsize=(10, 3.4))
for ax, key, title in zip(axes, ("brier", "log_loss", "ece"), ("Brier score", "Log loss", "Calibration error (ECE)")):
    v = [h[m][key] for m in LAB]
    ax.bar(range(len(v)), v, color=[COL[m] for m in LAB])
    ax.set(xticks=range(len(v)), xticklabels=[LAB[m].replace(" ", "\n", 1) for m in LAB], title=title)
    ax.tick_params(axis="x", labelsize=7)
    lo = min(v) * (0.97 if key != "ece" else 0.0)
    ax.set_ylim(lo, max(v) * 1.02)
fig.tight_layout()
fig.savefig(FIG / "holdout_scores.png")
plt.close(fig)
print({LAB[m]: {k: round(h[m][k], 5) for k in ("brier", "log_loss", "ece")} for m in LAB})

# %% [markdown]
# ## 5. What the model cannot do
# - It has no seasonal term that helps: v2's month term and a frozen calibrator priced 2026 17% too high.
# - It treats hubs unequally well (Chicago too cheap, Charlotte and Dallas too dear).
# - Its level is only as current as its last calibration, which is why the operating policy re-fits it monthly.
# `docs/decisions.md` and `VALIDATION.md` carry the full account.
