"""What attach rate the gap cover needs: the arithmetic that turns "demand is untested" into a number to beat.

Public data cannot say how many travellers would buy. It can say what each policy earns, which fixes what demand has to be
for the cover to matter. Everything here is multiplication of measured quantities (the average price of the cover as it
would be sold, its realized loss ratio) by inputs that belong to the agency (expense ratio, fixed costs, attach rate),
which are parameters of a grid, not claims.

    cd src && MCP_VARIANT=v3 python -m mcp.economics        # needs results/v3_rolling.json; writes results/economics_v3.json
"""
from __future__ import annotations

import json

from mcp.connections import ROOT

RESULTS = ROOT / "results" / "economics_v3.json"
ATTACH = (0.01, 0.02, 0.05, 0.10)
EXPENSE = (0.0, 0.10, 0.20, 0.30)


def margin_per_policy(price: float, loss_ratio: float, expense: float) -> float:
    """Premium left after claims and the agency's own costs, per policy sold. Negative when the cover loses money."""
    return price * (1.0 - loss_ratio - expense)


def profit(offers: float, attach: float, price: float, loss_ratio: float, expense: float) -> float:
    return offers * attach * margin_per_policy(price, loss_ratio, expense)


def break_even_attach(offers: float, fixed_cost: float, price: float, loss_ratio: float, expense: float) -> float:
    """Attach rate at which `offers` shown cover `fixed_cost`; infinite when each policy loses money."""
    m = margin_per_policy(price, loss_ratio, expense)
    return fixed_cost / (offers * m) if m > 0 else float("inf")


def main() -> None:
    r = json.loads((ROOT / "results" / "v3_rolling.json").read_text())["sold_within_cap"]
    price, lr = r["mean_price_sold"], r["pooled_loss_ratio"]
    out = {"price_per_policy": price, "realized_loss_ratio_sold": lr, "target_loss_ratio": 0.65, "offers": 100_000,
           "profit_per_100k_offers": {f"attach_{a:.0%}": {f"expense_{e:.0%}": profit(100_000, a, price, lr, e) for e in EXPENSE} for a in ATTACH},
           "margin_per_policy": {f"expense_{e:.0%}": margin_per_policy(price, lr, e) for e in EXPENSE},
           "attach_to_cover_fixed_cost_per_100k_offers": {f"fixed_{f}": {f"expense_{e:.0%}": break_even_attach(100_000, f, price, lr, e) for e in EXPENSE}
                                                         for f in (1_000, 5_000, 20_000)}}
    RESULTS.write_text(json.dumps(out, indent=1))
    print(f"price per policy ${price:.2f}, realized loss ratio as sold {lr:.0%}")
    print({k: f"${v:.2f}" for k, v in out["margin_per_policy"].items()})


if __name__ == "__main__":
    main()
