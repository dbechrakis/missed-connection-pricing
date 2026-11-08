# Decision memo: missed-connection protection

**To:** Head of ancillaries, generic online travel agency · **From:** Dimitris Bechrakis · **Date:** 8 November 2026
**Evidence:** public US data only (BTS, DB1B, GSA). Full method and validation: [`VALIDATION.md`](../VALIDATION.md).

## The decision

Should we sell protection against missed connections, at what price, and where should we refuse to sell it?

## Recommendation

1. **Do not sell blanket protection on single-airline tickets.** On one ticket the airline already rebooks a missed connection for free. For overnight disruptions it causes itself, it also pays the hotel; this is a commitment on the US DOT dashboard. BTS delay causes put **27.5%** of missed connections on the airline directly, and **31.9%** more on late-arriving aircraft. A cover that pays regardless sells passengers something they partly already have.
2. **If we sell, price per connection, never one flat price.** Prices fixed before the test ran a **60.5%** loss ratio against a 65% target, on 37.1 million connections the model had never seen (January to August 2026). One flat price was fine only if buyers ignore risk (68.2%). If the riskiest connections buy more, it runs **117%**: we would pay out more than we collect.
3. **Refuse where the price would be too large a share of the fare.** Tight connections cost about eight times as much to protect. At a 5% price cap, Denver, Charlotte, Dallas and Chicago cannot price most connections under 75 to 105 minutes. There we should warn the traveller or show a longer connection instead of selling.
4. **The product worth building is the gap cover.** It pays the official hotel-and-meals rate for the hub and month, only when the night is not the airline's fault (weather, air traffic control). That gap is **40.6% to 72.5%** of missed connections, and 80.5% of the overnight ones under the strict reading. The average price is about **$35** per connection at overnight risk. **39%** of those connections can be priced within 5% of the fare.

## What it costs us if we are wrong

- **Weather risk is correlated and the model cannot see it coming.** Whole months came in from **0.84 to 1.37 times** the expected claims on data the model had not seen. No model choice removed this, and refitting the model eight times on resampled training data moved the pooled result by only about 0.01 (the weather, not the model, is the uncertainty).
  - **As it would actually be sold, the cover loses money in bad months.** Selling only where the price fits the 5% cap, the same six months ran a **78%** average loss ratio against the 65% target: **111% in July**, 94% in August, and **8 of 28 weeks above 100%**. That is before commission, payment fees and handling.
  - The all-connections view looks gentler (worst month 89%). The sold view is the one that counts, and it is worse because the cap selects connections the model under-prices.
  - One Chicago week paid out about nine times its premium, so exposure needs a cap per hub-week or reinsurance. A stop-loss on the weekly loss ratio would have cost at least **3.9%** of premium at a 100% attachment and **7.8%** at 90% on these weeks, before any loading.
- **Selling only where it is cheap selects our own mistakes.** The connections the price cap lets through ran **9% worse** than average, because a low price partly reflects under-estimated risk. Loading the price by about a fifth on offered cover would be needed just to reach the target on these months, at the cost of fewer connections qualifying.
- **We will not know the loss ratio quickly.** Weather and operations hit everyone in a week at once. Measuring the loss ratio to ±10% takes at least 27 weeks, however many policies we sell.

## What we do not know, and how to find out

- **The minimum connection time.** The model assumes 45 minutes at every airport. If the real minimum were 60, the prices would have paid out **1.57 times** what they assumed; at 35, 0.90 times. This matters more than anything else tested. A real product must price on each airline's own minimum for each connection, which an agency has and public data does not.
- **Demand.** How many travellers buy, at what price, and whether the riskiest connections buy more. Public data cannot answer this.
- **The test:** randomised price arms (0.8×, 1.0×, 1.25× the model price), a message test ("covers your hotel" against "covers a missed connection"), and a no-offer control as a guardrail on booking conversion.
- **Sample size:** at a 2% attach rate, telling apart how strongly risky connections self-select (θ differing by 0.5) needs about 2,500 travellers shown the offer. Sizes for every assumption are in the [product brief](product-brief.md#7-the-experiment).
- **Whether the gap cover's pricing holds.** This is already being tested: it is [pre-registered](../PREREGISTRATION_2026H2_V3.md) on September to December 2026, before that data existed. Results are due when BTS publishes those months (September had not appeared on 8 November).

## Next step

Approve a four-week pricing experiment on the gap cover at one hub where the gap is largest (Dallas, 21% of misses from weather, or Chicago, 20% from air traffic control). Price it on each airline's own minimum connection time, load the price for the selection effect, set a claims exposure cap per hub-week and pre-agree the stop rule. Do not launch the blanket cover.
