# The demand experiment: a plan fixed before it runs

Demand for the gap cover is the one question public data cannot answer: nobody has bought it. This page fixes **how it will be measured and what each result will mean before a single traveller is shown an offer**, so the result cannot be bent afterwards. The design and sample sizes are in the [product brief](product-brief.md#7-the-experiment); this adds the analysis, the decision rule and the evidence that the analysis works.

## Design in one paragraph

Travellers booking an itinerary with a connection where a miss means a night away are assigned by a stable hash of the session to one of: a **no-offer control** (about 10%), or an offer at **0.8×, 1.0× or 1.25× the model price** (never above the 5% cap), with the **benefit-led** or **outcome-led** wording at random. Claims close later; whether a missed connection happened is known for everyone from public flight data, buyer or not.

## What is recorded

One row per traveller (`mcp.demand.analyse`): `shown`, `arm_price` (the multiplier), `message`, `purchased`, `booked` (did the itinerary booking itself complete), `p` (the model's probability), `claim_cost`, `y_gap` (the realized outcome), `weight`, `week`, `price`.

## What is estimated, and the decision it feeds

| Quantity | How | Used for |
| --- | --- | --- |
| Attach rate by price arm, with Wilson intervals | share of those shown who buy | Is demand at the model price above what the economics need? |
| Price response | logit coefficient on log price (about the elasticity of the attach rate when attach is small) | Where the price can move |
| Self-selection on visible risk (θ) | logit coefficient on log model risk | Whether the riskiest connections buy more, beyond price |
| **Adverse selection on hidden risk** | realized ÷ expected claims among buyers over the same among everyone shown, weekly block bootstrap | Whether buyers know more than the model; this is what a loading cannot see |
| Message effect | odds ratio of outcome-led against benefit-led wording, price fixed | Which wording to use |
| **Guardrail** | booking conversion of those shown an offer against the control | The cover must not cost bookings |
| Margin per offer | attach × (price − payout), per arm | The comparison between arms |

## The decision rule (`mcp.demand.decide`)

Go only if **all four** hold, each judged at the end of its interval that is worse for the cover:

1. the lower end of the attach rate at the model price is at least `min_attach`;
2. the upper end of θ is at most `max_theta`;
3. the upper end of adverse selection is at most `max_adverse`;
4. the lower end of the booking-conversion difference is at least `min_conversion_diff`.

The four thresholds are **arguments, not numbers this project chooses**: they come from the agency's own costs. `mcp.economics` turns them into arithmetic: at an average price of about $10 and a 75% loss ratio as sold, each policy leaves about $2.50 before expenses and nothing once expenses pass 25% of premium (`VALIDATION.md` 5J). `min_attach` is the attach rate at which the margin pays the agency's fixed cost, `max_adverse` is how much extra loss the margin can absorb.

## Why the analysis can be trusted before it has seen a customer

`mcp.demand.simulate` generates travellers with **planted** answers (a price elasticity, a θ, a hidden-risk spread, a message effect). Tests (`tests/test_demand.py`) check that across ten independent simulated experiments each 95% interval contains the planted answer in at least eight, which is the number an honest interval would give about 99% of the time; that adverse selection is found where it is planted and absent where it is not; that the guardrail catches an offer that costs bookings and stays quiet otherwise; and that the decision rule uses the unfavourable end of each interval. Two mistakes of mine were caught this way while writing it: a closed-form value for the planted adverse selection that ignored saturation of the purchase probability, and a test that had picked a lucky random seed. The analysis does not say what real travellers do; it says it would find it if they did.

## Stop rules

- **Harm:** stop an arm if the booking-conversion difference has an upper bound below −0.01 after at least 20,000 travellers.
- **No peeking at a winner:** the attach and margin comparisons are read once, at the sample size fixed in the brief for the baseline attach rate seen in the first week.
- **Claims:** the loss ratio cannot be learned from claims in any useful time, because weather moves whole weeks together: about 200 weeks to ±10% as sold (`VALIDATION.md` 5I). So the loss side is read from the model and the public outcomes of the connections offered, as above, not from claims.

## What each outcome means

- **All four hold:** run the cover at the winning price arm at a capped volume, with an exposure limit per hub-week (`docs/agency-inputs.md`, row 7).
- **Attach too low:** the cover is not worth running at the model price. Test the 0.8× arm only if its attach rate clears the bar with a margin that is still positive.
- **Adverse selection too high:** the price must carry a loading for it, or the cover is not offered; this is the risk the project cannot see from public data.
- **Guardrail fails:** the offer costs more in lost bookings than it earns. Stop.

## Running it

```python
from mcp.demand import analyse, decide
result = analyse(df)          # df: one row per traveller, the columns above
decide(result, min_attach=..., max_theta=..., max_adverse=..., min_conversion_diff=...)
```
