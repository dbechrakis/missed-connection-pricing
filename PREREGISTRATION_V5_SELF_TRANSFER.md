# Pre-registration: v5, protection for self-transfer connections

Written **9 November 2026**, before any cross-airline pairing has been built, labelled or scored. It is a separate document; no earlier pre-registration is edited. The commit that added it (`48b2dd20fd93`) was pushed to GitHub, on branch `claude/serene-hypatia-pk5fvr`, before the first cross-airline pairing was built, and GitHub's record of that push bounds when this was fixed. The tag `prereg-v5-self-transfer` marks that commit. The session that wrote this could push branches but not tags, so the author adds the tag. It was drafted by Claude for the author, as the decision log records for earlier rounds.

## 1. The question

An online travel agency can sell an itinerary on **two separate tickets** with different airlines (a self-transfer). No airline owes anything if the first flight is late. The traveller loses the onward ticket and pays for a new one, and a hotel if the next flight is tomorrow. The project's own brief and decision memo name this as the case where protection is most worth selling (`docs/product-brief.md`, roadmap; `docs/decision-memo.md`, recommendation 1), and the market evidence shows a product of this kind priced at about 25% of the ticket (`docs/market-evidence.md`).

What should such a cover cost, per connection, and where should it not be offered?

## 2. What has and has not been seen

- **Seen:** every analysis in this repository so far used **same-network** pairings (same reporting airline for v1 and v2, same marketing network for v3 and v4), from January 2024 to August 2026, including their outcome rates by hub, month and connection time. The underlying flights are the same BTS flights, so how late inbound flights run at these hubs is known in broad terms.
- **Not seen:** no pairing of an inbound flight with an outbound flight of a **different** marketing network has been built, labelled or scored, for any month. The connection-time windows used here (90 to 300 minutes) and the self-transfer label have never been computed.

## 3. Population

- Inbound A → H on marketing network X, outbound H → B on marketing network Y, with **X ≠ Y**, at the five hubs (ATL, CLT, DEN, DFW, ORD), from the BTS Marketing Carrier file.
- Scheduled gap from **90 to 300 minutes**, both flights on the same hub-local day, A ≠ B.
- Every such pairing counts once (**unweighted**). Who actually books self-transfers is not observable in public data (a self-transfer is two separate tickets, so DB1B does not record it as one journey). A second, stylised mix that favours short gaps (weight e^(−buffer/60), as in `VALIDATION.md` 5K) is reported as sensitivity only.
- Interline and codeshare agreements between some networks are not modelled. On such pairs a real traveller might be protected. This makes the population an upper bound on unprotected connections.

## 4. The label (what a claim is)

- **Minimum self-transfer time T = 90 minutes**: time to leave one airline's area, change terminal if needed, re-check a bag and clear security. A connection is **missed** when the inbound flight is cancelled or diverted, or its actual arrival plus T is later than the outbound flight's actual departure.
- **Any cause counts.** There is no airline-fault exclusion, because no airline owes the traveller anything across two tickets.
- Pairs whose **outbound** flight is cancelled are excluded: that airline refunds its own ticket, which is a different product. Pairs with missing times are excluded and counted.
- T = 60 and T = 120 are rebuilt and reported as sensitivity, never used to choose anything.

## 5. The payout

- **Replacement ticket:** the passenger-weighted mean one-way market fare for **nonstop H → B** in DB1B, all carriers, over the training quarters 2024 Q1 to 2025 Q2. A fare bought on the day is usually dearer than this mean, so the payout is a **lower bound** on what a stranded traveller pays. Multipliers of 1.5 and 2.0 are reported as sensitivity.
- **Hotel:** plus the GSA lodging and meals rate for the hub and month (as v3, `results/gsa_costs.json`) when **no other departure H → B, on any network, is scheduled later the same hub-local day** than the missed outbound flight.
- Pairs whose H → B market has no DB1B nonstop fare are dropped and counted.

## 6. The model and the price

- **A cell model, not a gradient-boosted model.** P(miss) by hub × inbound network × gap bucket (15 minutes: 90 to 104, …, 285 to 300) × inbound scheduled arrival band (05:00 to 10:59, 11:00 to 15:59, 16:00 to 20:59, 21:00 to 04:59). Each cell is shrunk toward its hub × gap-bucket rate with a prior of k pseudo-connections. v1 found booking-time models only 1% to 2% better than a hub × connection-time baseline, so a transparent table is the right first model.
- **k** is the only choice made on data: the value in {0, 50, 200, 1000} with the lowest pooled log loss on the selection window. Ties within 0.0002 go to the larger k.
- **Price** = P(miss) × payout ÷ 0.65, the same target loss ratio as every earlier version.
- **Offered** only where the price is at most **10% of the two-ticket fare** (DB1B nonstop mean fare A → H plus H → B), below the roughly 25% of the ticket charged for a full rebooking guarantee, because this cover pays for the onward leg only. 5% and 15% are reported.

## 7. Windows

| Window | Months | Use |
| --- | --- | --- |
| Fit | January 2024 to June 2025 | cell rates |
| Selection | July to December 2025 | choose k only |
| Final fit | January 2024 to December 2025 | the frozen table |
| **Holdout** | **January to August 2026** | read **once**, by `python -m mcp.v5 holdout`, after the frozen table's hash is committed |

The holdout pairings are built with outcome rates suppressed (counts only), as for the 2026 holdout of v1 and v2. Nothing else may score them first.

## 8. What is reported

Realized ÷ target loss ratio (claims ÷ premium ÷ 0.65) on the holdout: overall, by hub, by month, by gap bucket, and on the subset offered within the 10% cap. Intervals from a weekly block bootstrap. The share of misses caused by inbound cancellation or diversion. The share of pairings offered. The T, payout and mix sensitivities.

## 9. Expectations (falsifiable; each is reported, pass or fail)

| # | Expectation | Why this level | If it fails |
| --- | --- | --- | --- |
| S1 | **Calibration.** Holdout realized ÷ target between **0.85 and 1.15** | The v1 holdout landed within 7% with a richer model; a cell table on a new population should land within 15% unless the level moves | The price is not right on average, and the cover is not priced |
| S2 | **Cancellations matter more than for a same-airline connection.** Inbound cancellations and diversions are **20% to 50%** of holdout misses | For same-airline connections at a 45-minute minimum, 18% of misses follow a cancellation or diversion (`VALIDATION.md` 4H). A 90-minute minimum removes many late-arrival misses but none caused by cancellation | The claim mix is not what the product assumes |
| S3 | **Risk falls with the gap.** At every hub, the holdout miss rate in the 90 to 104 minute bucket is above the rate in the 165 to 179 minute bucket | The mechanism of every earlier version | The table's shape is wrong |
| S4 | **Weather moves whole months.** The standard deviation of the eight monthly realized ÷ target ratios is between **0.08 and 0.35** | v3's gap cover showed 0.24 over 26 months, and an any-cause cover dilutes weather with airline causes | Either the risk is calmer than the gap cover's or wilder |
| S5 | **The winner's curse inside the cap.** Realized ÷ target on the pairings offered within the 10% cap is **higher** than on all pairings | Found in v3 (`VALIDATION.md` 5E, 5G) | Selecting on a low price does not select under-estimated risk here |

**Not allowed after reading the holdout:** changing the population, T, the label, the payout rule, the fares, the cell definition, k, the cap, the target loss ratio, the windows, or the metric. A bug may be fixed only with the numbers before and after, in `VALIDATION.md`.

## 10. What this cannot show

Who books self-transfers, and therefore the real mix and weights. Whether a 90-minute minimum is what travellers need. What a same-day fare really costs. Interline protection on some pairs. Demand. Whether an agency may legally sell this as a benefit rather than insurance.
