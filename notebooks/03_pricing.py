# %% [markdown]
# # 03 — From probability to price, and when not to offer one
#
# Plain `.py` with `# %%` cells. Reads the published results and the demo's price table, so every number matches
# the validation. Figures go to `docs/figures/` (override with `MCP_FIG_DIR`).
#
#     price = P(miss) × (rebooking cost + overnight cost × overnight) ÷ target loss ratio
#     offer = price ≤ cap × fare
#
# The costs ($75, $180), the 65% target and the 10% cap are **assumptions**; this notebook shows how much the
# decision depends on them.

# %%
import json
import os
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIG = Path(os.environ.get("MCP_FIG_DIR", ROOT / "docs" / "figures"))
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
                     "figure.dpi": 130, "font.size": 10})
P = json.loads(re.sub(r"^window\.PRICES = |;\s*$", "", (ROOT / "site" / "prices.js").read_text(encoding="utf-8")))
A = P["assumptions"]
pricing = json.loads((ROOT / "results" / "pricing.json").read_text())
HUB = {"ATL": "#0072B2", "CLT": "#D55E00", "DEN": "#009E73", "DFW": "#CC79A7", "ORD": "#E69F00"}
cell = lambda hub, s: next(c for c in P["cells"] if c["hub"] == hub and c["carrier"] == "ALL" and c["slack"] == s)

# %% [markdown]
# ## 1. Price falls about eight-fold with connection time
# The tightest connections are missed one time in four or five; the loosest, about one in thirty. Price follows,
# and so does the share of connections that fit under the willingness-to-pay cap.

# %%
fig, ax = plt.subplots(figsize=(7.4, 4))
for hub in P["hubs"]:
    xs = P["buckets"]
    ax.plot(xs, [cell(hub, s)["price_typical"] for s in xs], color=HUB[hub], lw=2, label=hub)
cap = np.mean([A["wtp_cap_pct"] * cell(h, s)["fare"] for h in P["hubs"] for s in P["buckets"]])
ax.axhline(cap, color="#a4380f", ls="--", lw=1.4)
ax.text(P["buckets"][-1], cap, f" cap ≈ ${cap:.0f}\n ({A['wtp_cap_pct']:.0%} of fare)", va="center", fontsize=8, color="#a4380f")
ax.set(xlabel="Scheduled time between flights (minutes, start of 15-minute step)", ylabel="Price of protection ($)",
       title="Price by connection time, by hub (typical next-flight case)", xlim=(45, 245))
ax.legend(frameon=False, ncol=5, fontsize=8)
fig.tight_layout()
fig.savefig(FIG / "price_curve.png")
plt.close(fig)
tight, loose = np.mean([cell(h, 45)["price_typical"] for h in P["hubs"]]), np.mean([cell(h, 210)["price_typical"] for h in P["hubs"]])
print(f"mean price: ${tight:.2f} at 45-59 min, ${loose:.2f} at 210+ min -> {tight / loose:.1f}x")

# %% [markdown]
# ## 2. The overnight matters more than the hub
# Whether the next flight to the destination is the next day roughly triples the claim, so the same connection can
# be sellable or not depending on the onward schedule. This is why the demo asks.

# %%
print("45-59 minute connection, price and share of connections within the cap")
print(f"{'hub':5s} {'same day':>18s} {'typical':>18s} {'next day':>18s}")
for hub in P["hubs"]:
    c = cell(hub, 45)
    print(f"{hub:5s} " + " ".join(f"${c['price_' + k]:>6.2f} ({c['offer_' + k]:>4.0%})  " for k in ("same", "typical", "next")))

# %% [markdown]
# ## 3. The cut-off is a statement about the assumptions
# At each hub, the shortest connection time from which at least half of connections fit the cap and stay that way.
# The line moves a lot with the cap and a little with the costs. It is a question for the experiment, not the data.

# %%
sens = pricing["sensitivity"]
caps = {0.05: "wtp_cap_pct=0.05", 0.10: "wtp_cap_pct=0.1", 0.15: "wtp_cap_pct=0.15"}
fig, ax = plt.subplots(figsize=(7, 3.8))
x = np.arange(len(P["hubs"]))
for i, (cp, key) in enumerate(caps.items()):
    cut = [sens[key]["cutoff_min_slack_by_hub"][h] for h in P["hubs"]]
    ax.bar(x + (i - 1) * 0.27, cut, 0.27, label=f"cap {cp:.0%} of fare", color=["#9ab", "#0072B2", "#bcd"][i])
ax.set(xticks=x, xticklabels=P["hubs"], ylabel="Shortest connection time with offers (min)", ylim=(40, 112),
       title="Where protection stops being sellable, by price cap")
ax.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(FIG / "cutoff_sensitivity.png")
plt.close(fig)
for cp, key in caps.items():
    print(f"cap {cp:.0%}: cut-offs {sens[key]['cutoff_min_slack_by_hub']}, offered on {sens[key]['offer_rate']:.0%} of connections")

# %% [markdown]
# ## 4. One-at-a-time sensitivity of the offer rate

# %%
base_rate = pricing["summary"]["offer_rate"]
print(f"default offer rate {base_rate:.1%}")
for key, v in sens.items():
    name, val = key.split("=")
    if name != "wtp_cap_pct":
        print(f"  {name:20s} {val:>5s}   offer rate {v['offer_rate']:.1%}   ({v['offer_rate'] - base_rate:+.1%})")

# %% [markdown]
# ## 5. What these prices are and are not
# They are the frozen v1 table, weighted by real route traffic, with assumed costs. They have been validated on how well
# P(miss) predicts (loss ratio 60.5% against a 65% target on 2026 data), not on whether anyone would pay them.
