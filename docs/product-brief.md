# Product brief: Missed-connection protection for a generic online travel agency

Author: Dimitris Bechrakis · November 2026 · Status: proposal, built on public data only

> **What this is.** A brief for an optional add-on sold at checkout: if the traveller misses a connection, the agency pays a defined benefit. It covers who it is for, what to build first, how success is measured, and the experiment that answers what public data cannot.
> **What this is not.** Evidence that travellers want it. The analytics in this repo model *risk* (how often connections are missed and what that costs). Demand, willingness to pay and the legal form are open and are the subject of Section 7.

---

## 1. Summary

| | |
| --- | --- |
| **Problem** | Travellers on itineraries with a connection worry about missing it; an agency that sells those itineraries cannot today price that risk per connection, so it either offers nothing or a flat price. |
| **Proposal** | A protection add-on priced per connection from its measured risk, offered only where the price is acceptable, with a warning or an alternative itinerary where it is not. |
| **Evidence it can be priced** | On Jan to Aug 2026 data that nothing in the project had seen, prices set from information up to 2025 ran a **60.5% to 62.3% loss ratio against a 65% target** (intervals contain the target). A flat price would have been fine only if buyers ignore risk; if they self-select, it ran **1.8x** the target (θ = 1). |
| **What is not known** | How many travellers buy, what they will pay, how strongly the riskiest connections self-select, and whether the benefit must be filed as insurance. |
| **Ask** | Approve a staged launch: ship a monitored MVP at a capped scale, run the pricing experiment in Section 7, and decide on scale-up after the first read. |

---

## 2. Users and problem

**Who.** Travellers booking one itinerary with a connection, on a single carrier, through the agency's checkout. Three segments:

| Segment | What they fear | What they would pay protection to avoid |
| --- | --- | --- |
| Leisure, tight connection | Missing the onward flight and losing a day of a short trip | A stranded night |
| Family or group | Being split or stuck with children overnight | A hotel for several people |
| Business | Missing a meeting the next morning | Lost time |

**How big is the risk?** From the project's own data (24 months of flights, five US hubs, same-carrier connections between 45 and 225 minutes, weighted by real route traffic):

| Scheduled connection time | Share of connections missed |
| --- | --- |
| 45 to 59 minutes | about 21% |
| 90 to 104 minutes | about 7% |
| 210 minutes or more | about 3% |
| All connections (weighted) | about 8% |

If a connection is missed, the next flight of the same airline to the same city leaves the **next day** in roughly 36% of cases (42% of the cases that actually missed), by our estimate. That is where hotels and meals come in.

**The risk this brief must be honest about.** When a connection is missed and it is the airline's doing, airlines usually rebook the traveller on the same ticket at no charge. Obligations vary by airline, ticket type and country, and must be confirmed with the agency's own operations and legal teams. So protection cannot sell "we will rebook you": it has to sell something the airline does not provide, such as hotel, meals and transport beyond the airline's duty, a fixed payout, or cover where the airline gives none (separate tickets, outside this MVP). **The project cannot test this.** If travellers read the add-on as redundant, attach will be low whatever the price. That is hypothesis H4 in Section 7.

---

## 3. Goals, non-goals and success metrics

**Goals (first six months).**
1. Learn the real attach rate, willingness to pay and selection strength, at small scale and bounded loss.
2. Keep the realized loss ratio within the target band without needing to be right about demand.
3. Make a claim feel easy: automatic verification, no paperwork where possible.

**Non-goals.** Maximising attach at any price; selling where the price exceeds what travellers accept; personalising price by traveller attributes.

| Metric | Definition | Target | Notes |
| --- | --- | --- | --- |
| **Margin per offer shown** (north star) | attach rate × (premium − expected claim cost) per traveller shown an offer | positive and rising | Combines demand and risk in one number |
| Attach rate | travellers who buy ÷ travellers shown an offer | **set after the first read** | Unknown today; do not guess a target |
| Realized loss ratio | claims paid ÷ premium, rolling | 65% ± 10% (assumption) | Needs about 27 weeks to know to ±10% at scale (Section 7.4) |
| Time to payout | claim event to money in hand | to be set with operations | Automatic verification is the lever |
| **NPS after a claim** | NPS asked of claimants only | to be set after the first claims | The product's real test of trust |
| Complaint rate, refund rate | per 1,000 policies | guardrail: no increase vs checkout baseline | Stop signal |
| Share of offers shown at the price cap | offers within 10% of the cap | watch | A sign the cap is binding |

The 65% loss ratio, the ±10% band and the 10% price cap are **assumptions** of this brief (see the register in Section 9).

---

## 4. What we would build

**The offer.** At checkout, for an itinerary with an eligible connection (same carrier; the five hubs in scope), show the price and the covered benefit. If the price is above the cap for that fare, do not offer protection; show a plain warning about the tight connection and, where one exists, an alternative itinerary with more time.

**MVP (in scope).**
- Per-connection price from a precomputed table: hub, carrier, connection time, with a floor so a model's zero never becomes a $0 price.
- A monthly recalibration job: re-fit the level of the price table on the last six months of outcomes.
- Automatic claim verification from public flight status data; a defined, capped benefit (the amount is a product decision; the validation uses assumed costs of $75 for rebooking and $180 more when the next flight is the next day).
- A pause rule (Section 7.5) and a weekly dashboard of attach, claims and loss ratio by hub.

**Out of scope for the MVP.**
- Connections between different airlines or self-transfers; airports beyond the five hubs; international itineraries.
- Day-of re-pricing or alerts (a possible second product; the value of day-of information has not been measured).
- Seat availability on the next flight (so the benefit estimate is a lower bound).
- Personalised prices.
- Anything involving the agency's own customer data. The validation uses public data only.

---

## 5. How the price is set (one paragraph and one table)

P(miss) is estimated from the schedule and the carrier's history at booking time only, and calibrated against recent outcomes. The expected claim is P(miss) × (rebooking cost + overnight cost if the next flight is the next day). The price is that divided by the target loss ratio. Protection is offered while the price is at most a fixed share of the fare. All dollar inputs are assumptions with a sensitivity run. Method and every decision are in `docs/decisions.md` and `VALIDATION.md`.

Illustrative prices on development data (mean fare about $330; assumptions as above):

| Connection time | P(miss) | Illustrative price | Share of connections offered at a 10% cap |
| --- | --- | --- | --- |
| 45 to 59 min | 24.6% | $54.6 | 46% |
| 75 to 89 min | 10.8% | $25.7 | 71% |
| 120 to 134 min | 5.5% | $11.6 | 93% |
| 210+ min | 3.2% | $6.7 | 99% |

The spread is about 8x. A single price near the $21 average would be too cheap for the tight connections and too dear for the loose ones.

---

## 6. Evidence from validation (summarised; full account in `VALIDATION.md`)

| Test | Loss ratio vs 65% target | Notes |
| --- | --- | --- |
| 2024 hub × slack baseline, Jan to Aug 2026 | 76.3% | Under-prices by about 17% |
| **v1, frozen before 2026, Jan to Aug 2026** | **60.5%** [55.4, 66.1] | Clean test: nothing tuned on it |
| **v2 with monthly recalibration, Jan to Aug 2026** | **62.3%** [56.9, 67.8] | Pre-registered product |
| v2 with a frozen calibrator | 53.7% | Priced 17% too high |
| v1, H2 2025 (a test that was then spent) | 59.1% [53.4, 65.3] | Reported as produced |
| Flat price, any θ ≥ 0.5 | 1.4x to 2.7x target | Degrades as buyers self-select |

What this does not establish: that real travellers behave like any assumed buyer model; that hub-level pricing is right (**ORD runs about 16% under-priced and CLT and DFW about 12% over-priced** in every schedule); that seasonality is captured (the best-calibrated version re-learns the level monthly instead); that results hold beyond five hubs and same-carrier connections.

---

## 7. The experiment

The analytics fix the *cost* side. The experiment measures the *demand* side and the one unknown that decides whether tiering is worth it (θ).

### 7.1 Hypotheses

| # | Hypothesis | How it is measured |
| --- | --- | --- |
| H1 | Attach rate falls as price rises, and by how much (price elasticity) | Attach rate by price arm |
| H2 | Riskier connections are bought more often, beyond what price explains (selection strength θ) | Slope of purchase on risk, controlling for price |
| H3 | The willingness-to-pay cap sits near the assumed 10% of fare | Attach and margin by price-to-fare ratio |
| H4 | The message matters: "covers hotel and meals" sells better than "covers a missed connection" | Attach by message arm, price held fixed |

### 7.2 Design

- **Unit and randomisation.** The traveller session, assigned by a stable hash, so a traveller sees the same arm on every visit. Only itineraries with an eligible connection enter.
- **Price arms** (applied to the model price, never above the cap): 0.8x, 1.0x, 1.25x. **Message arms** (price at 1.0x): benefit-led vs outcome-led. Hold-out: a control that sees no offer, to measure any effect on conversion of the booking itself.
- **Primary metric:** margin per offer shown, with attach rate as the fast read. Claims arrive with delay, so margin is projected from expected cost at first and corrected as claims close.
- **Guardrails:** booking conversion, complaint rate and refund rate must not worsen against the control; prices above the cap are never shown.
- **Analysis plan:** fixed before launch; two-sided tests at 5%; one primary comparison per hypothesis; secondary cuts (hub, carrier, connection time) labelled exploratory; no stopping early on a good-looking interim read.

### 7.3 How many travellers

All figures are computed in `src/mcp/experiment.py` and tested against textbook values (`results/experiment_design.json`). "Travellers" means travellers *shown an offer*.

**H1, H3, H4: travellers per arm to detect a change in attach rate** (80% power, 5% two-sided). The baseline attach rate is **unknown**, so the table is a grid; replace the row with the observed rate after the first week.

| Baseline attach rate | Detect +10% relative | Detect +20% relative | Detect +30% relative |
| --- | --- | --- | --- |
| 1% | 163,095 | 42,693 | 19,827 |
| 2% | 80,682 | 21,109 | 9,798 |
| 5% | 31,234 | 8,158 | 3,780 |
| 10% | 14,751 | 3,841 | 1,774 |

**H2: travellers to tell apart a selection strength θ that differs by the amount shown.** Risk varies a lot across connections (the standard deviation of log P(miss) is 0.80 in our data), which helps.

| Baseline attach rate | θ differs by 1.0 | by 0.5 | by 0.25 |
| --- | --- | --- | --- |
| 1% | 1,229 | 4,916 | 19,661 |
| 2% | 621 | 2,483 | 9,931 |
| 5% | 257 | 1,025 | 4,098 |
| 10% | 136 | 541 | 2,163 |

H2 is much cheaper than H1: it uses variation in risk that already exists in the offered connections, not a price change.

### 7.4 How long until the loss ratio is known

This is the finding that shapes the whole launch. **Volume does not shorten it much**, because weather and operational events hit every traveller in a week at once. From the holdout, the realized/target ratio has a weekly coefficient of variation of about 0.26. A single policy's claim cost is very skewed (coefficient of variation about 4.0), which adds noise for a small book.

| Policies sold per week | Weeks to know the loss ratio to ±20% | Weeks to ±10% |
| --- | --- | --- |
| 100 | 23 | 89 |
| 1,000 | 9 | 34 |
| 10,000 | 7 | 28 |
| 100,000 | 7 | 27 |

At any volume, **about 27 weeks (six months)** are needed for ±10%, and **108 weeks** for ±5%. Attach rate can be read in weeks; the loss ratio cannot. The launch must therefore bound the risk before it can measure it.

### 7.5 Bounding the risk in the meantime

- **Capped exposure:** a ceiling on weekly policies sold and on the benefit per policy.
- **Pause rule:** if weekly claims exceed the expected figure by more than two weekly standard deviations (about 1.5x expected) for two weeks in a row, pause sales in that hub and review. The threshold comes from the measured weekly variability, not from a guess.
- **Recalibration:** monthly. A frozen price went 17% wrong in the test; re-learning the level fixed most of it.
- **Event handling:** a manual switch to stop selling at an airport during a declared outage or severe weather, since the model cannot see the day.

---

## 8. Roadmap and prioritisation

Impact and confidence are judgement calls, stated with their reasons; effort is a rough size. Nothing is scored with invented numbers.

| Order | Item | Why now / next | Evidence in this repo | Effort |
| --- | --- | --- | --- | --- |
| Now | Pricing experiment (Section 7) | It is the only way to learn demand, willingness to pay and θ; everything after depends on it | θ is not identifiable from public data | M |
| Now | Monthly recalibration job | A frozen price was 17% wrong; the rolling one was best calibrated | 2026 holdout | S |
| Now | Claim auto-verification and payout rules | Trust, and cost per claim | Not tested by this repo | M |
| Now | Pause rule and weekly dashboard | The loss ratio cannot be measured fast (Section 7.4) | Weekly variability ≈ 0.26 | S |
| Next | Hub-level calibration | ORD is under-priced about 16% and CLT, DFW over-priced about 12% in every schedule | 2025 and 2026 backtests | S to M |
| Next | Cross-carrier and self-transfer connections | Where the airline gives no protection, the proposition is strongest (Section 2) | Out of scope of the data here | L |
| Next | Day-of alerts | The model's ceiling is low because most of the risk is day-of; the value of knowing is unmeasured | Brier skill from booking-time features about 5% | M |
| Later | Seat availability, live severity | Makes the benefit estimate exact | Severity is a lower bound today | L |
| Later | More hubs | Wider coverage | Same method, new data | M |

---

## 9. Risks, open questions and the assumptions register

**Open questions that could stop the project.**
1. **Is the proposition redundant** next to the airline's own duty to rebook? (H4; ask operations and legal first.)
2. **Is it insurance** in the markets where it would be sold, and who may underwrite it? A legal question this brief does not answer.
3. **Claim definition.** A "missed connection" trigger, the benefit amount and what is excluded (for example, a traveller late to the gate through their own fault) must be fixed before launch.
4. **Real costs.** The benefit and handling costs here are assumptions; the real ones change the price.

**Known weaknesses of the evidence.** Hub-level miscalibration (above). No seasonal term that clearly helps. Only eight months of clean test data. Connections are synthetic: the data show flights, not which passengers actually connected. The minimum connection time is assumed (45 minutes, with 35 and 60 tested on the label only).

**Assumptions register.**

| Quantity | Value used | Source | Status |
| --- | --- | --- | --- |
| Miss rate by connection time | table in Section 2 | Public flight data, same-carrier synthetic connections | Measured, with the caveats above |
| Weights by route | by passengers | Public 10% ticket sample, train period only | Measured |
| Minimum connection time | 45 min | Assumption | Sensitivity run |
| Rebooking cost / overnight cost | $75 / $180 | Assumption | Sensitivity run; to replace with real costs |
| Target loss ratio | 65% | Assumption | A business decision |
| Willingness-to-pay cap | 10% of fare | Assumption | **To be learned (H3)** |
| Attach rate | not set | Unknown | **To be learned (H1)** |
| Selection strength θ | not set | Unknown | **To be learned (H2)** |
| Message effect | not set | Unknown | **To be learned (H4)** |
| Price floor | 0.9% P(miss) | Lowest 2% of predictions on development data | Guard in `config/guards.yaml` |

---

## 10. Decision requested and next steps

1. **Go / no-go on a capped MVP** and on the experiment in Section 7.
2. **Before that:** operations and legal answer questions 1 to 3 in Section 9. Those answers can end the project, so they come first.
3. If go: build the monthly recalibration, claim verification and pause rule; launch at capped volume in one or two hubs; read attach and θ at four to six weeks; read the loss ratio only once the book is large enough (Section 7.4).
