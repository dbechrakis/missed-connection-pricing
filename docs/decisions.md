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
