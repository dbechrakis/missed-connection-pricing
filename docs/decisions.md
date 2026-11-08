# Decision log

One line per decision: what, why, and what it costs. Raw material for `method.md` and interview answers.

## Data (step 1, 3)

| Decision | Why | Cost / caveat |
| --- | --- | --- |
| Keep flights where Origin **or** Dest is a hub | A connection needs the inbound A→H and outbound H→B legs | 5.6M rows, 64 MB Parquet |
| Keep cancelled and diverted flights | They are the label's signal; dropping them hides the worst outcomes | Nulls in time fields, handled explicitly |
| Read CSVs as text, cast explicitly | Type inference can differ month to month | Slightly more code |
| Times stay as raw `hhmm` in ingest | Timestamps need midnight-rollover logic, which belongs in tested `connections.py` | — |
| DB1B weights from the six train quarters only | 2025 Q3/Q4 are unpublished, and weights are a train-only statistic anyway | Weights are fixed through the test window |
| Join DB1B Coupon to Market on `MktID` | Fare then belongs to the exact A→H→B market | Two tables, 1.95 GB of downloads |
| Drop bulk fares and fares outside $20–$5,000 | Placeholder and data-entry values | Thresholds are my judgement |
| `docs/spec.md` is gitignored | It names the employer and contract terms; must not be public | Method is described in `docs/method.md` instead |

## Connections and label (step 2)

| Decision | Why | Cost / caveat |
| --- | --- | --- |
| Timezone shift recovered from scheduled elapsed time | No airport timezone table needed; handles red-eyes and `2400` | Relies on `CRSElapsedTime` being populated |
| Actual time = scheduled + reported delay | Avoids re-deriving date rollover from `hhmm` | — |
| Strict `>` for the MCT boundary | Arriving exactly MCT before departure is a make; a test pins it | — |
| Cancelled outbound is excluded, not "missed" | Spec: not a missed connection; counted via `status` | 2.09M rows (1.5%) |
| A→H→A turnarounds dropped | Not a real itinerary | Added beyond the spec |
| Same **reporting** carrier only | Spec scope | Mainline→regional (AA→Envoy) is not paired: stated limit |
| MCT 45 default, 35/60 sensitivity | Real MCT is not free data | Miss rate moves 7.35% / 7.92% / 8.23% on train |

## Weights (step 3–4)

| Decision | Why | Cost / caveat |
| --- | --- | --- |
| A route's passengers are **split across its pairings** | Giving each pairing the full count counts a busy route once per pairing | — |
| The split is **per month**, not over all months | A train row's weight must not depend on test-month schedules | Caught during step 4; test pins it |
| Unmatched routes (22%) get no weight | No DB1B evidence they exist | Checked: matched vs unmatched miss rates are within ~1 point at every hub |

## Split and baseline (step 4)

| Decision | Why | Cost / caveat |
| --- | --- | --- |
| Chronological windows, in one file (`split.py`) | A random split trains on the future | FIT 2024 / VALID Jan–Jun 2025 / TEST Jul–Dec 2025 |
| EDA and baseline restricted to TRAIN; a test fails if code references TEST | Exploring the test set is leakage | Backtest (step 18) is the one exception |
| Slack buckets of 15 minutes, 12 buckets | Fine enough for the curve, coarse enough for stable cells | Last bucket absorbs slack = 225 |
| Metrics computed on weighted cells | Exact for cell-constant predictions; no row data leaves DuckDB | Not valid once a model varies within a cell (GBM) |
| Equal-weight bins for ECE | Predictions live in 0–30%; equal-width bins would be mostly empty | — |

## Findings so far (train + validation only)

- Miss rate falls from ~22% at 45–59 min slack to ~2.7% at 210+ min. The product exists.
- **Slack carries almost all the signal at this feature level.** Hub × slack beats flat by 4.9% in Brier; hub alone adds 0.1%. More features must earn their place against this.
- **Calibration drifts.** Fit on 2024 (7.60% miss), the baseline under-predicts Jan–Jun 2025 (8.41%) in nearly every bin. Underpricing is the risk, which is what the spec's later-window recalibration is for.
- Early and late departures miss most; July 2024 is the worst month (11.8%).
- Matched vs unmatched routes miss at similar rates, so dropping unmatched routes does not bias the weighted view.

## Features and models (step 5)

| Decision | Why | Cost / caveat |
| --- | --- | --- |
| Booking-time features only; outcome columns are on a forbidden list a test enforces | A price is quoted before the day; actual times, cancellations and that day's weather are day-of information | Low ceiling: little of what makes a connection fail is known at booking |
| Route-history stats are leave-one-month-out for FIT rows, full-FIT for later rows | A row's own outcome must not be inside its own feature, or the model over-trusts it on new data | Slight mismatch between 11-month and 12-month history, checked: feature means match across windows |
| Shrink route stats toward the all-route mean (K=30) | A route with 3 flights should not look perfect or terrible | K is a judgement |
| VALID split into VALID1 (choose the model) and VALID2 (calibrate only) | Choosing and calibrating on the same months makes the calibration score flattering | Calibration judged on the second half of VALID2 |
| Feature set chosen by Brier on VALID1 only | The calibration months must not influence the choice | Differences between candidates are small; treat as a tie among the top ones |
| **Dropped `month` and the weather climatology** | With one fit year, `month` memorises 2024's calendar; climatology (one year of monthly shares) is the same thing in other words. Both made VALID1 worse | The spec's storm/snow climatology did not earn its place. A pre-2024 climatology (small download) could be tested |
| Refit the chosen model on FIT + VALID1, calibrate on VALID2 | More recent data and a second Jan-Mar; the isotonic fit stays out-of-sample | Compared against fit-only on the same eval half: 0.08228 vs 0.08243 raw |
| Isotonic regression for calibration | Non-parametric, monotone, standard; millions of rows so it will not overfit | Cannot extrapolate a level shift (see below) |

### Step 5 results (weighted, validation windows only)

| Window | Baseline | Chosen GBM | Chosen + isotonic |
| --- | --- | --- | --- |
| VALID1 Jan-Mar 2025 (Brier) | 0.06853 | 0.06822 (-0.5%) | n/a |
| VALID2 May 16-Jun 30 (Brier) | 0.08405 | 0.08228 (-2.1%) | 0.08189 (-2.6%) |
| VALID2 May 16-Jun 30 (ECE) | 0.0217 | 0.0213 | 0.0138 |

- **The real limit is level drift, not model class.** Observed miss rate: 7.6% (2024), 7.8% (Jan-Mar 2025), 9.1% (Apr-Jun 2025). After calibration the model still predicts 8.4% against 9.8% observed on May 16-Jun 30. A static price will lag a rising level; the backtest must show this as a sensitivity, not hide it in "model skill".
- Features beyond hub, slack and the schedule add little signal (Brier within 0.0682-0.0685 across candidates). Honest reading: booking-time information is mostly slack.

## Severity and pricing (step 6)

| Decision | Why | Cost / caveat |
| --- | --- | --- |
| Severity from the **schedule**: next distinct departure of the same carrier, same hub to same destination | Known at booking, so it can sit in the price; the spec's method | Cancelled flights stay in the schedule; seat availability unknown, so severity is a **lower bound** |
| Overnight = next departure is on a later date **and** at least 4h later | 23:30 then 00:20 next day is a 50-minute wait, not a hotel night | The 4h guard is mine, a config parameter with a test |
| Flights at the same minute are not each other's fallback | A codeshare twin is not a second chance | — |
| No later flight in the data counts as overnight | Only affects the last days of 2025 | Tiny edge effect |
| Price is **per connection**, then averaged into table cells | Overnight is a schedule property of the connection, so averaging P(overnight) separately would blur it | Cell price is a mean, not a single quote |
| Costs ($75 rebooking, $180 overnight), loss ratio 0.65, WTP cap 10% of fare are **assumptions** | No company data may be used; they are round numbers for a generic OTA | Every one has a sensitivity run; the cap is the one that matters |
| Month in the price table varies only through schedule mix | The model has no `month` feature (step 5) | Say so in the README; do not present a seasonal price the model does not have |

### Step 6 results (training-era connections, weighted; assumptions as above)

| Slack (min) | P(miss) | Price | Fare | Offered |
| --- | --- | --- | --- | --- |
| 45-59 | 24.6% | $54.6 | $326 | 46% |
| 60-74 | 15.4% | $36.0 | $330 | 64% |
| 90-104 | 8.3% | $19.0 | $335 | 81% |
| 150-164 | 4.4% | $9.7 | $330 | 97% |
| 210+ | 3.2% | $6.7 | $328 | 99% |

- Price falls about 8x from the tightest to the loosest slack: a flat price cannot be right at both ends (to be shown in the backtest).
- 36% of connections would be overnight if missed, 42% among those that actually missed (tight connections skew to thin routes). Median wait if missed: 265 min.
- **The "do not sell below N minutes" cut-off is driven by the WTP cap, not the model.** With the cap at 10% the cut-off is 45-60 minutes; at 5% it is 60-105; at 15% there is none. The result line in the README must say "under these assumptions".
- The calibrator carries the Apr-Jun 2025 level (9.1%), so mean predicted P(miss) on 2024 rows (9.1%) sits above what 2024 saw (7.9%). That is intended for pricing H2 2025, and is exactly what the backtest tests.

## Backtest (step 7)

| Decision | Why | Cost / caveat |
| --- | --- | --- |
| Protocol and frozen hashes committed **before** the test window was read | So nothing can be tuned on it; a git diff proves it | The window is now spent: later improvements cannot be validated on it |
| Headline = realized ÷ target = cost-weighted calibration ratio | Depends on P(miss), only weakly on assumed dollar costs | Dollar assumptions still set price levels and the offered set |
| Purchase weight ∝ P(miss)^θ, shown as a curve over θ | Who buys cannot be known from public data; no single θ is defensible | The adverse-selection claim is "tiering protects at any θ > 0", not a number |
| Flat price compared in two forms, incl. a hindsight oracle | The oracle is the strongest possible flat price, so its loss is adverse selection alone | Oracle is unattainable in practice |
| Weekly block bootstrap for intervals | Days within a week are correlated | 27 weeks only |
| Whole test window scored, no sampling | Exact numbers, no sampling error | 3 minutes of compute |
| A pipeline smoke test on Apr-Jun 2025 before the real run | To find bugs without touching the test window | Those months are in-sample for the calibrator, so only code paths were checked |

### Result and what it means (details in VALIDATION.md)

- Realized ÷ target = **0.909 [0.822, 1.004]**: a 59% loss ratio against a 65% target. Priced slightly high.
- The uncalibrated model is better calibrated on H2 than the calibrated product: the isotonic fit carried Apr-Jun's 9.1% level into a half-year that ran at 7.9%.
- Month-by-month the observed rate swung 5.8%-10.4% while the model predicted a flat 9%: no seasonality.
- Flat pricing is fine if buyers ignore risk and ruinous if they do not (1.4x target at theta 0.5, 1.9x at 1). Tiered stays near 0.9 throughout.
- **Open question for improvement, not for this window:** a calibration window of a full year, or a seasonal term when more years exist.

## v2 and the 2026 holdout (step 8)

| Decision | Why | Cost / caveat |
| --- | --- | --- |
| Treat H2 2025 as spent for v1 and as development data for v2, with a new walk-forward scheme | Fixes tried on the spent window would prove nothing; the clean test is new data | H2 2025 numbers for v2 must never be quoted as validation |
| Download Jan-Aug 2026 and keep it sealed (quiet connection builds, counts only) | A genuine out-of-time test of v1 and v2 | Eight months, 35 weeks: wide intervals |
| Selection rule declared before the run: pooled log loss, ties to the simpler policy | A rule fixed in advance cannot be bent toward a favourite | It picked a near-tie and the most complex policy |
| Two v2 pricing policies, static and rolling, both reported | The better one is not chosen after the fact | Static was the worst of the five |
| Rows matched by key, not order, between v1 and v2 feature frames | Row order from separate queries is not guaranteed | A one-to-one check aborts on duplicates |
| Refactored the backtest accounting; reproduced earlier numbers exactly on Apr-Jun 2025 | Refactors must not change results | Checked, not assumed |

**Result:** frozen v1 ran 60.5% and v2 rolling 62.3% against a 65% target; both intervals contain the target. v2 is a little better calibrated; the gain came from re-fitting the level monthly, not from the seasonal term. ORD is under-priced and CLT/DFW over-priced in every schedule: hub-level calibration is the open defect.

## Product brief, experiment design and a price floor (step 9)

| Decision | Why | Cost / caveat |
| --- | --- | --- |
| The brief says up front that demand is untested and that airlines usually rebook for free on a single ticket | Analytics model risk, not demand; a flagship should not imply otherwise | The proposition may be weaker than the numbers suggest |
| Sample sizes computed in tested code from measured inputs (weekly variability of the ratio, claim-cost skew, spread of log risk) | No size is stated from memory; each checks against a textbook value | Baseline attach rate stays a grid because it is unknown |
| Weeks to learn the loss ratio do not shrink with volume (about 27 weeks for +-10%) | Weather and operations hit all travellers in a week at once | The launch must bound loss before it can measure it |
| Pause rule derived from the measured weekly variability (1 + 2 x 0.26 = 1.5x expected, two weeks running) | A threshold taken from data, not guessed | Needs live monitoring |
| H2 (selection strength) is sized separately and is cheap | It uses risk variation that already exists in offered connections | Needs enough range of risk across offers |
| Price floor of 0.9% P(miss) in `config/guards.yaml`, not in `pricing.yaml` | The calibrator gave exactly 0 for 0.0075% of weight; a $0 price is never acceptable | Applies to the product from now on, not to the frozen validation numbers; the frozen config hash stays true |
| Brief written as a generic agency, no internal facts | The repo is public; the author works in the same industry | Real costs and rules must replace the assumptions |

## The demo (step 10)

| Decision | Why | Cost / caveat |
| --- | --- | --- |
| No month input | The model has no seasonal term, so the control would change nothing; a flagship should not show a control that does nothing | The spec's four inputs became three, plus the next-flight option |
| The demo is the frozen v1 model | Month-free by construction and validated on the clean 2026 holdout (60.5% loss ratio) | Its calibration level is stale; v2 with monthly recalibration is the operating policy described in the brief |
| Every number on the page comes from `site/prices.js`, built from the results files | Nothing is typed by hand, so the page cannot drift from the validation | Rebuild with `python -m mcp.demo` after any new results |
| Three decision states: offer (at least 90% of such connections within the cap), mixed, do not offer (at most 10%) | Testing showed one averaged price can contradict the cap when same-day and next-day cases are mixed | The 90/10 thresholds are mine; they only set wording |
| "If missed, the next flight leaves..." selector | The price depends on it (hotel or not), and it is the traveller-relevant unknown | Typical case uses the observed mix |
| Static page, no libraries, data in a script file | Opens instantly, works offline, no cold start; zero spend | Chart is hand-drawn SVG |
| Deploy by GitHub Actions from `site/` | The spec wants a `site/` folder; Actions allows that without moving it | Pages on a private repository needs a paid plan; the repo becomes public at launch |
