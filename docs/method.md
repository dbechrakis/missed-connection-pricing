# Method

How a connection becomes a price, and how we know the price is any good. This page describes *what* is done. Why each choice was made, and what each one costs, is in [`decisions.md`](decisions.md); the evidence is in [`../VALIDATION.md`](../VALIDATION.md).

```
BTS On-Time flights ──► synthetic connections + "missed" label ─┐
BTS DB1B tickets ─────► route weights (real traffic) ───────────┤
                                                                ├─► booking-time features ─► P(miss) ─► calibration
BTS On-Time flights ──► severity (next flight, overnight?) ─────┘                                            │
                                                                                          price = P(miss) × cost ÷ target
                                                                                                             │
                                                                          offer if price ≤ cap × fare, else warn / alternative
```

## 1. Data (all public)

| Source | What it gives | What it cannot give |
| --- | --- | --- |
| BTS Airline On-Time Performance | Every flight of the large US carriers: scheduled and actual times, delay, cancellation, diversion | Passengers, itineraries, prices |
| BTS DB1B (10% ticket sample, quarterly) | Which origin→hub→destination routes passengers really fly, and their fares | Dates, times, flight numbers |
| IEM ASOS hourly weather | Wind, visibility, weather codes per airport | Forecasts as they were at booking time |

Scope: five hubs (ATL, ORD, DFW, DEN, CLT), same-carrier connections only, US domestic. Flights January 2024 to August 2026.

## 2. Connections and the label

No public dataset says which passengers connected, so the connections are **synthetic**: at a hub *H* and for one carrier, every inbound flight *A→H* is paired with every outbound flight *H→B* that

- is the same carrier (reporting carrier) and leaves *H*,
- departs on the same hub-local day as the inbound arrives,
- is scheduled between **MCT** and **MCT + 180 minutes** after the scheduled arrival (the *slack*), with MCT = 45 minutes by default (35 and 60 as sensitivities, which rebuild the set of pairings because MCT also decides which exist),
- does not return to *A*.

Times: the timezone shift between airports is recovered from the data (arrival clock − departure clock − scheduled elapsed time, folded into ±12 h), so no airport timezone table is needed. Actual times are scheduled time plus the reported delay.

**Missed** means the inbound flight was cancelled or diverted, or `actual arrival + MCT > actual outbound departure` (strict inequality: arriving exactly MCT before departure is a make). If the **outbound** flight is cancelled the case is *not* a missed connection: it is excluded and counted separately (1.5% of pairs).

## 3. Weights

A pairing of two flights is not equally likely to exist as a real itinerary. Each connection is weighted by how many DB1B passengers fly its route (*carrier, A, H, B*), pooled over the train quarters only. A route's passengers are split evenly across its scheduled pairings **within each month**, so a busy route is not counted once per pairing and no weight depends on later months. About 77% of synthetic connections lie on a route with weight; the rest are dropped (their miss rates differ by about one point from the rest). Regional airlines fly for several mainline brands and the data kept here does not say which brand sold a ticket, so some regional pairings may mix brands that could not be booked together. The per-pairing weight divides by the number of valid pairings, which depends slightly on cancellations; dividing by all pairings instead changes the weighted miss rate by at most 0.014 percentage points.

## 4. Features: booking time only

A price is quoted weeks before the flight, so only the schedule and *history that existed then* may be used: hub, carrier, slack, outbound hour and weekday, inbound arrival hour, and three route-history statistics of the inbound leg (mean arrival delay, share of flights 15+ minutes late, cancel/divert rate) shrunk toward the all-route average. History is computed on the fit window only; for rows inside that window each route statistic leaves out the row's own calendar month, so a row never sees its own outcome. The day's weather, the inbound flight's actual arrival and anything else that is only known on the day are excluded. That belongs to a separate day-of product. Tests enforce this.

## 5. Model and calibration

- **Baseline:** the weighted miss rate per hub × 15-minute slack bucket.
- **Logistic regression** and **histogram gradient boosting** on the features above. Boosting is used.
- **Calibration:** a price multiplies a probability by money, so ranking is not enough. The probability is recalibrated with isotonic regression. **v1** fits it once on April to June 2025. **v2** re-fits it each month on the last six months of outcomes that were already known (walk-forward), and adds a `month` term that two years of data allow. The monthly re-fit uses every outcome up to the end of the previous month; a real booking is made weeks before the flight, so `VALIDATION.md` Part 4 tests the same policy with a lag.

## 6. Severity, price and decision

If a connection is missed, the traveller takes the next *scheduled* flight of the same carrier from the hub to the same destination. If that flight leaves on a later date and at least four hours later, the case is an **overnight**. This comes from the schedule, so it is known at booking; it ignores seat availability, so it is a lower bound.

```
expected cost = P(miss) × (rebooking cost + overnight cost × overnight)
price         = expected cost ÷ target loss ratio
offer         = price ≤ cap × fare            (fare: DB1B mean for that route)
```

Rebooking cost ($75), overnight cost ($180), the target loss ratio (65%) and the cap (10% of fare) are **assumptions** ([`../config/pricing.yaml`](../config/pricing.yaml)), each with a sensitivity run. A floor of 0.9% on P(miss) ([`../config/guards.yaml`](../config/guards.yaml)) stops a calibrator's zero from becoming a $0 price. Where the price exceeds the cap the right answer is not a dearer price but a warning or a longer alternative itinerary.

## 7. Validation design

Windows are chronological and defined in one file ([`../src/mcp/split.py`](../src/mcp/split.py)).

| Window | Dates | Use |
| --- | --- | --- |
| FIT | Jan to Dec 2024 | Fit v1 and the baseline |
| VALID1 / VALID2 | Jan to Mar / Apr to Jun 2025 | v1 model selection / v1 calibration |
| TEST | Jul to Dec 2025 | v1 backtest, read once, now spent |
| V2 development | through Dec 2025 | v2 selection (walk-forward) and fit |
| HOLDOUT | Jan to Aug 2026 | Clean test of v1 and v2, read once |

Each test was **pre-registered**: the protocol, frozen model hashes and a list of what may not change afterwards were committed before the window was read. Guard tests fail if any module other than the backtest or holdout reads the test windows.

## 8. Metrics

- **Brier score, log loss:** how good the probabilities are; lower is better. **ECE** (expected calibration error): how far predicted probabilities sit from observed rates, in equal-weight bins.
- **Realized ÷ target loss ratio** (headline): total claims ÷ total premium ÷ the target. With premium = P(miss) × cost ÷ target it equals `Σ w·miss·cost ÷ Σ w·P(miss)·cost`, a cost-weighted calibration ratio, so it depends mainly on how good P(miss) is and only weakly on the dollar assumptions. 1.0 is on target.
- **Buyer selection θ:** nobody knows who buys protection. Purchase weight ∝ P(miss)^θ; θ = 0 means buyers ignore risk. Results are a curve over θ, never one chosen value. Pricing is compared with a flat price (average training claim, and an impossible hindsight-oracle flat price). This tests selection on risk the price already captures, which a calibrated model passes almost by construction. Selection on information the price lacks is simulated separately ([`selection.py`](../src/mcp/selection.py)): with a hidden risk spread κ, per-connection pricing runs at exp(θκ²) × target and a flat price worse.
- **Intervals:** weekly block bootstrap (days within a week are correlated); weeks, not policies, are the unit of uncertainty. The level also moves by month, so a monthly t-interval is wider (about ±0.11 for v1 against ±0.08), which does not change any conclusion about the target. Uncertainty in the fitted model and calibrator is not included.

## 9. What the method cannot do

Connections are synthetic; MCT is assumed; costs, loss ratio and cap are assumptions; severity ignores seat availability; demand and θ are unmeasured; there is no seasonal term that clearly helps; hubs are not equally well calibrated. The README and `VALIDATION.md` state these in full.
