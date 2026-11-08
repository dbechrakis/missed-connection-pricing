# Validation

This file is written in two parts. **Part 1 (below) was committed before the test window was read.** Part 2 (results) is appended after the single backtest run. Nothing in Part 1 was changed after seeing results; a git diff shows it.

## Part 1: Backtest protocol (frozen before reading H2 2025)

**Frozen artefacts** (SHA-256, commit `55497c6`)

| File | SHA-256 |
| --- | --- |
| `models/pmiss.joblib` (GBM + isotonic calibrator) | `e5094792b7f758dd2226d67a7afbc77a247807d097ebcdb1a860846f666f5870` |
| `config/pricing.yaml` (costs, loss ratio, WTP cap) | `77f42b8f26d31f058fc2fce77a0cf981bb2dcdf9a7dd3be8e1fcce2549b3e497` |

**Data.** Test = connections whose outbound is scheduled Jul 1 – Dec 31 2025 (`split.WINDOWS["TEST"]`), every row, no sampling. Nothing in training, selection or calibration used these months, including DB1B weights (train quarters only) and route statistics (2024 only).

**Question.** Prices set from information up to June 2025: how close does the realized loss ratio come to the target in H2 2025?

**Headline metric.** Realized loss ratio ÷ target loss ratio, tiered pricing, all connections, with a 95% interval from a weekly block bootstrap (weeks are resampled, because days within a week are not independent).

> realized LR = Σ claims ÷ Σ premiums. With premium = P(miss) × cost ÷ target LR, **realized ÷ target = Σ w·miss·cost ÷ Σ w·P(miss)·cost**: a cost-weighted calibration ratio. It depends on how good P(miss) is, and only weakly on the dollar cost assumptions, which change the weights between connections but not the probabilities. This is why the headline can be stated without trusting the cost numbers.

**What cannot be known from public data, and how it is handled (no assumption is hidden in a point estimate):**

| Unknown | Treatment |
| --- | --- |
| Who buys protection (adverse selection) | Purchase weight ∝ P(miss)^θ. θ = 0 means everyone equally likely to buy (no selection); larger θ means riskier connections buy more. Results are reported as a **curve over θ ∈ {0, 0.5, 1, 2}**, never at one chosen θ. Sales mix is held equal across pricing schedules, so the comparison isolates pricing accuracy |
| Dollar costs, loss ratio, WTP cap | Config assumptions. Costs: headline ratio is nearly invariant (above). The WTP cap only decides *which* connections are offered, so results are shown for all connections and for the offered subset |
| Seat availability on the next flight | Not observable; severity is a lower bound |
| Real minimum connection time | Label built with MCT 45; the 35 / 60 sensitivity is shown on the label rate, not re-priced |

**Comparators.**
1. Baseline: hub × slack-bucket rate fit on 2024 (step 4).
2. GBM raw (no calibration).
3. GBM + isotonic (the product).
4. Flat price, set from the average observed claim cost in the training window ÷ target LR.
5. Flat price, **hindsight oracle**: set so the realized LR equals target at θ = 0 on the test window. It cannot be achieved in practice. It is the strongest possible flat competitor, so any loss it shows at θ > 0 is the cost of adverse selection alone.

**Reported, in this order.** Overall and per-hub realized ÷ target (tiered, θ = 0, with intervals); loss ratio versus θ for tiered, flat and oracle-flat; Brier, log loss, ECE for baseline, raw and calibrated; reliability by predicted probability and by slack bucket; month-by-month level (Jul–Dec) against what the model predicted; the offered subset.

**Not allowed after seeing the result:** changing the model, features, calibration window, cost parameters, WTP cap, θ grid, or the metric. A bug found afterwards may be fixed only if the fix and its reason are written in Part 2, together with the number before and after.

**Pre-registered expectation.** Miss rates rose through 2025 (7.6% in 2024, 9.1% in Apr–Jun). If that level held, the calibrated model should run near target. If H2 2025 moved again, the realized ÷ target ratio will move with it, and that will be reported as a level risk, not as model error.

---

## Part 2: Results (one run, 28,848,642 test connections, Jul–Dec 2025, 27 weeks)

Run once with the frozen model and config of Part 1. No parameter, feature, window or metric was changed after seeing the numbers. The only edits after the run were presentation (a figure legend, a deprecated pandas call); the result file `results/backtest.json` is as produced. Target loss ratio is 65%, so *realized ÷ target* of 0.909 means a realized loss ratio of 59.1%.

### Headline

> Prices set on data through June 2025 ran a **59% loss ratio** on H2 2025 against a **65% target** (95% interval 53%–65%, weekly block bootstrap): realized ÷ target = **0.909** [0.822, 1.004]. The product priced slightly **too high**, not too low: it would have lost margin competitiveness, not money.

### Pricing schedules at θ = 0 (buyers ignore risk), realized ÷ target [95% interval]

| Schedule | Realized ÷ target | Realized loss ratio |
| --- | --- | --- |
| Baseline (hub × slack, fit 2024) | 1.142 [1.033, 1.262] | 74.2% |
| GBM, uncalibrated | 1.078 [0.975, 1.190] | 70.1% |
| **GBM + isotonic (the product)** | **0.909 [0.822, 1.004]** | **59.1%** |
| Flat price from training average | 1.037 [0.939, 1.141] | 67.4% |
| Flat price, hindsight oracle | 1.000 by construction | 65.0% |

### Adverse selection: realized ÷ target as buyers self-select by risk (θ)

| θ | Tiered (product) | Flat (training avg) | Flat (hindsight oracle) |
| --- | --- | --- | --- |
| 0 | 0.909 [0.822, 1.004] | 1.037 [0.939, 1.141] | 1.000 |
| 0.5 | 0.905 [0.829, 0.987] | 1.440 [1.320, 1.567] | 1.389 [1.274, 1.512] |
| 1 | 0.902 [0.833, 0.976] | 1.906 [1.761, 2.058] | 1.839 [1.698, 1.985] |
| 2 | 0.900 [0.838, 0.964] | 2.795 [2.612, 2.985] | 2.696 [2.519, 2.879] |

- **Tiered pricing does not move with θ; flat pricing does.** Even the impossible flat price that is perfectly levelled in hindsight drifts to 1.84× the target at θ = 1: that gap is adverse selection alone.
- **θ is not known.** It cannot be estimated from public data. The result is therefore a *curve*, and the claim that holds at every θ > 0 is that tiering protects the loss ratio; how much it protects depends on how strongly real buyers self-select, which only an experiment can show (`docs/product-brief.md`).
- **At θ = 0 tiering buys nothing on loss ratio**: a flat price is as good (1.037 vs 0.909, intervals overlap). The case for tiering is robustness to who buys, not a better average.

### Calibration on the test window (weighted)

| Model | Brier | Log loss | ECE | Mean predicted | Observed |
| --- | --- | --- | --- | --- | --- |
| Baseline | 0.06964 | 0.25638 | 0.0033 | 7.60% | 7.93% |
| GBM uncalibrated | **0.06856** | **0.25141** | 0.0039 | 7.57% | 7.93% |
| GBM + isotonic | 0.06875 | 0.25208 | 0.0107 | 9.00% | 7.93% |

### What did not go as hoped

1. **Isotonic calibration made the level worse, not better.** The calibrator was fit on Apr–Jun 2025, when 9.1% of connections were missed. H2 2025 ran at 7.9%. The uncalibrated GBM has the best Brier and log loss on the test window, and an ECE (0.0039) close to the baseline's (0.0033). It also under-prices (1.078); the calibrated product over-prices (0.909). In the protocol's terms: this is the level risk anticipated in Part 1, not a leak or a bug.
2. **The model has no seasonality, so it cannot follow the swings.** Observed miss rate by month: Jul 10.4%, Aug 9.0%, Sep 5.8%, Oct 5.9%, Nov 7.6%, Dec 9.0%. The calibrated model predicts 8.9%–9.1% in every month. One fit year cannot separate seasonality from 2024's events (step 5), so `month` was dropped. A static price will therefore be too high in September–October and too low in July; this shows in `docs/figures/backtest_level.png`.
3. **Hubs differ.** Calibrated realized ÷ target by hub: CLT 0.768 [0.677, 0.866] (priced too high, interval excludes 1), ATL 0.881, DFW 0.896, DEN 0.990, ORD 1.040 [0.920, 1.169]. The uncalibrated model under-prices DEN (1.18) and ORD (1.24). Hub-level calibration is not solved.
4. **Calibrated predictions run 8–17% above observed in every one of the 12 slack buckets** (e.g. 24.2% vs 21.4% at 45–59 minutes). The shape is right; the level is carried from Apr–Jun.
5. **The interval for the headline just reaches 1.0** (upper bound 1.004). Honest reading: consistent with on-target at the top of the range, and probably a little high.

### Offered subset

With the 10% willingness-to-pay cap (an assumption) the product would offer protection on 80.8% of connection weight. Realized ÷ target on the offered subset is 0.890 [0.779, 1.011]; on the not-offered subset 0.922 [0.851, 1.000]. The cap changes who is sold, not whether the prices track risk.

### What this does and does not show

- **Shows:** a model of booking-time information, fit on 2024 and the first half of 2025, prices H2 2025 within about ±10% of the target loss ratio on average, beats the 2024 baseline, and, unlike flat pricing, is insensitive to who buys.
- **Does not show:** that real passengers would behave like this. Connections are synthetic; the minimum connection time is assumed (label rates at MCT 35/45/60: 7.35% / 7.92% / 8.23% on the training window); severity is a lower bound; costs, loss ratio and WTP are assumptions; buyer behaviour (θ) is unknown. Dollar assumptions barely move the headline ratio (it is a cost-weighted calibration ratio) but they do set the price levels and the offered set.
- **The test window is now spent.** Any change motivated by these results (for example a calibration window that spans a full year, or a seasonal term once more history exists) would be a post-hoc improvement and cannot be validated on H2 2025 again. It would need new data, or an honest label as exploratory.

### Reproducing

```bash
python -m mcp.backtest        # from src/; reads the test window once, writes results/backtest.json and docs/figures/backtest_*.png
```

---

## Part 3: The 2026 holdout and v2

**Why.** H2 2025 was spent in Part 2. The product (v1) showed two weaknesses: a single short calibration window carried a transient level into the next half-year, and the model had no seasonality. Fixes tried on H2 2025 would prove nothing, so the clean test is new data: BTS On-Time for **Jan to Aug 2026**, published after v1 was frozen.

### 3A. v2 development design (committed before the selection experiment was run)

**What v2 may use.** Everything through December 2025, including H2 2025, which is now ordinary development data. It follows that **H2 2025 is not a clean test of v2**, and v2's H2 2025 numbers must never be quoted as validation. The 2026 months are sealed: no 2026 outcome is read until the run in 3B.

**Selection experiment (uses 2025 only).** Fit the GBM on `S_FIT` (Jan 2024 to Mar 2025). Score Apr to Dec 2025. Then, month by month from July to December 2025 ("walk-forward"), price month *m* with a calibrator built **only from months before *m*** (from April on, so the GBM has not seen them). This mirrors how a real team would recalibrate, and no policy sees its own evaluation month.

**Candidates** (decided now, not after looking):

| Choice | Options |
| --- | --- |
| Feature set | v1 set (no month, no weather); v1 set plus `month` (two years of data now exist) |
| Calibration policy | none; level shift, global, last k ∈ {1, 2, 3, 6} months; level shift per hub, k ∈ {1, 3, 6}; isotonic, k ∈ {3, 6} |

**Selection rule (declared in advance).** Lowest pooled walk-forward **log loss** over Jul to Dec 2025, because a price multiplies a probability by money and log loss punishes confident wrong probabilities most. Candidates within 0.0002 of the best are treated as tied; ties go to the simpler policy (none, then global level, then per-hub level, then isotonic) and then the longer window. Brier, ECE and realized ÷ target are reported but **not** used to choose.

**What is then frozen for the 2026 run.**
- v1 as it stands (`models/pmiss.joblib`, hashes in Part 1), uncalibrated and calibrated.
- The 2024 baseline (hub × slack).
- **v2 static:** GBM fit on `V2_FIT` (Jan 2024 to Sep 2025) with the chosen feature set, calibrator from `V2_CAL` (Oct to Dec 2025, out-of-sample for the GBM), no 2026 information at all. It measures how fast a fixed price goes stale.
- **v2 rolling:** the same GBM; the calibrator is re-fitted each month on the chosen window of months already known, which in 2026 includes earlier 2026 months. This is legitimate walk-forward, since those outcomes would be known when pricing the next month, and it is the realistic operating policy.

**The 2026 run reports** (same as Part 2, plus the v2 rows): realized ÷ target with weekly block-bootstrap intervals, over a θ curve, by hub, by month, calibration (Brier, log loss, ECE, reliability), the offered subset, and the share of 2026 connections on routes with no DB1B weight (DB1B has no quarter after 2025 Q2, so route weights stay train-only).

**Not allowed after the 2026 run:** changing v1, v2, either calibrator policy, the metric, or the θ grid. Only bug fixes, written up with before and after numbers.

**Known limits of this design, stated up front.** 2026 is eight months, so seasonality is judged on one repeat of Jan to Aug only; the real minimum connection time, seat availability and buyer behaviour (θ) remain unobserved; the two held-out pricing policies (static and rolling) are both candidates of mine, and I report both rather than the better one.

### 3B. Selection outcome and frozen artefacts (committed before 2026 was scored)

**What the pre-declared rule chose** (`results/v2_selection.json`, walk-forward Jul to Dec 2025, pooled log loss): feature set **v1 + month**, calibration **isotonic over the last 6 months** (log loss 0.25104). The runner-up (isotonic over 3 months, same features) was 0.25125, just outside the 0.0002 tie band, so the rule picked the winner outright. The ten best candidates lie within about 0.0007 log loss of each other, so this choice is close to a tie in log loss. Realized ÷ target over the same months ranged from 0.91 to 1.12 across candidates (the chosen one: 1.067). The rule was not changed after seeing this.

**Frozen artefacts (SHA-256)**

| File | SHA-256 |
| --- | --- |
| `models/pmiss.joblib` (v1, unchanged since Part 1) | `e5094792b7f758dd2226d67a7afbc77a247807d097ebcdb1a860846f666f5870` |
| `models/pmiss_v2.joblib` (v2 GBM on Jan 2024 to Sep 2025, plus Oct to Dec 2025 calibration statistics) | `ecee867eb5dfc930c7571722d1797fd0ba47ed7555cfb4d01d3e0a45e74b90a8` |
| `config/pricing.yaml` (unchanged) | `77f42b8f26d31f058fc2fce77a0cf981bb2dcdf9a7dd3be8e1fcce2549b3e497` |
| `results/v2_selection.json` | `e4b5e097578f02a7b06e24939cb5688642e81cbee91cbd402a1a681c341b8617` |

**What is read.** `mcp.holdout` reads the 2026 months once (guard-tested). Window: outbound scheduled Jan 1 to Aug 29 2026. The last two days of data are dropped because a flight whose next departure falls after August 31 would be mis-read as an overnight.

**Prices compared on every 2026 connection:** baseline (2024); v1 uncalibrated; v1 as shipped; v2 static (calibrator from Oct to Dec 2025, no 2026 information); v2 rolling (calibrator re-fitted monthly on the last 6 known months, which from February includes earlier 2026 months, walk-forward). The purchase weight and the offered subset both use v2 rolling's probability, for every schedule alike.

**Pre-registered expectations (no directional claim is made about which schedule wins).**
1. If the 2026 level differs from Apr to Jun 2025 (9.1%) and H2 2025 (7.9%), v1 as shipped will be off by about that ratio, since its calibrator is frozen.
2. v2 rolling should have the smallest level error, because it re-learns the level each month; v2 static is the open question.
3. Tiered pricing should again be insensitive to θ and flat pricing should degrade with θ. This is mostly arithmetic given calibrated probabilities, so it is a check of the machinery, not a finding.
4. Month-by-month, v2 should follow the seasonal shape better than v1 (v2 has a `month` feature, v1 does not).

### 3C. Results: the 2026 holdout (one run, 37,079,333 connections, Jan 1 to Aug 29 2026, 35 weeks)

Run once with the frozen artefacts of 3B. Nothing was changed after seeing the numbers. Observed miss rate over the window: **8.14%**. Target loss ratio 65%.

#### Headline: realized ÷ target at θ = 0 (95% interval from a weekly block bootstrap)

| Schedule | Realized ÷ target | Realized loss ratio |
| --- | --- | --- |
| Baseline (2024 hub × slack) | 1.173 [1.075, 1.282] | 76.3% |
| v1 uncalibrated | 1.104 [1.011, 1.206] | 71.7% |
| **v1 as shipped** (frozen since Part 1) | **0.931 [0.853, 1.017]** | **60.5%** [55.4, 66.1] |
| v2 static (nothing from 2026) | 0.826 [0.759, 0.896] | 53.7% [49.4, 58.3] |
| **v2 rolling** (pre-registered product) | **0.958 [0.875, 1.043]** | **62.3%** [56.9, 67.8] |
| Flat price, training average | 1.050 [0.963, 1.143] | 68.2% |
| Flat price, hindsight oracle | 1.000 by construction | 65.0% |

> On data never seen during development, the frozen v1 ran a **60.5% loss ratio** and v2 with monthly recalibration a **62.3%**, against a **65% target**. Both intervals contain 65%. The 2024 baseline ran 76%.

#### Adverse selection (realized ÷ target as buyers self-select by risk, θ)

| θ | v1 as shipped | v2 rolling | Flat (training avg) | Flat (hindsight oracle) |
| --- | --- | --- | --- | --- |
| 0 | 0.931 | 0.958 | 1.050 | 1.000 |
| 0.5 | 0.929 | 0.967 | 1.390 | 1.324 |
| 1 | 0.928 | 0.974 | 1.799 | 1.714 |
| 2 | 0.929 | 0.978 | 2.658 | 2.532 |

The same pattern as H2 2025: tiered pricing barely moves with θ; flat pricing degrades steeply. At θ = 0 flat is not worse than tiered on average (1.050 vs 0.958, intervals overlap), so the argument for tiering is robustness to who buys, as in Part 2.

#### Calibration on the holdout (weighted)

| Schedule | Brier | Log loss | ECE | Mean predicted | Observed |
| --- | --- | --- | --- | --- | --- |
| Baseline | 0.07199 | 0.26582 | 0.0073 | 7.56% | 8.14% |
| v1 uncalibrated | 0.07106 | 0.26148 | 0.0082 | 7.52% | 8.14% |
| v1 as shipped | 0.07125 | 0.26168 | 0.0108 | 8.95% | 8.14% |
| v2 static | 0.07118 | 0.26214 | 0.0192 | 10.06% | 8.14% |
| **v2 rolling** | **0.07079** | **0.26000** | **0.0051** | 8.65% | 8.14% |

v2 rolling is best on all three scores, by modest margins (Brier 0.6% lower than v1 as shipped).

#### Pre-registered expectations, checked

| # | Expectation (Part 3B) | Verdict |
| --- | --- | --- |
| 1 | v1 as shipped is off by about the level difference, since its calibrator is frozen | **Held.** It predicted 8.95% against 8.14% observed and priced about 7% high (0.931) |
| 2 | v2 rolling has the smallest level error; v2 static is open | **Held for rolling** (ECE 0.0051, 8.65% vs 8.14%). **v2 static was the worst on level** (10.06% predicted, priced 17% high): a frozen calibrator on top of a `month` feature overshot |
| 3 | Tiered insensitive to θ, flat degrades | **Held** (this is mostly arithmetic given calibrated probabilities; a check of the machinery) |
| 4 | v2 follows the seasonal shape better than v1 | **Not clearly supported.** Over eight months, v2 rolling and static correlate positively with the observed monthly pattern (+0.46, +0.59) and v1 does not (−0.42), but mean absolute monthly error is no better (v2 rolling 1.04 pp, v1 1.01 pp), and v2 missed January badly (11.2% predicted vs 9.0%) and April to May (8.3% and 9.2% vs 6.6% and 7.3%). Eight points cannot settle it |

#### What did not go as hoped

1. **v2 did not clearly beat v1 on the headline.** v1 as shipped (60.5%) and v2 rolling (62.3%) are statistically indistinguishable, and both sit a little under the target (priced a little high). v2 is better calibrated on Brier, log loss and ECE, but by small margins.
2. **The `month` feature and a frozen calibrator hurt.** v2 static priced 17% too high, and its month-by-month prediction peaked at 12.0% in July against 9.6% observed. That is consistent with the worry from step 5: with two years of data, a month feature still partly memorises one-off events (July 2024 was 11.8%). What helped v2 was **re-fitting the level monthly**, not the seasonal term. This run cannot separate the two, because no "v2 rolling without month" variant was pre-registered.
3. **Hub structure persists, and it is the clearest remaining defect.** v2 rolling by hub: ORD **1.156 [1.018, 1.309]** (priced too low, interval excludes 1), ATL 1.031, DEN 0.933, DFW **0.876 [0.774, 0.981]** and CLT **0.880 [0.781, 0.996]** (priced too high). The same ordering appeared in H2 2025 for v1 (ORD 1.040, DFW 0.896, CLT 0.768) and holds for every schedule here. A hub-level correction was a candidate in v2 selection and was not chosen by the pre-declared rule.
4. **The shape across slack differs by model.** v1 over-predicts tight connections (24.1% vs 20.6% observed at 45 to 59 minutes, +17%) and is accurate at long slack. v2 rolling is accurate at tight slack (20.3%) and too high at long slack (4.0% vs 3.3% at 210+ minutes, +21%). Tight connections carry most of the claim cost, so this matters for pricing.
5. **Only 35 weeks and eight months.** The intervals are wide (about ±0.08 around the ratio), and some of the seasonal questions need a full second cycle.

#### What this shows

- **Shows:** on genuinely new data, a model fit on information up to September 2025 and priced without any 2026 knowledge priced 2026 within about ±7% of the target loss ratio, under two different design choices (frozen v1 and monthly-recalibrated v2). Recalibrating the level monthly fixes the biggest weakness of a frozen price. Tiering protects the loss ratio at every buyer-selection strength. The 2024 baseline would have lost 11 points of margin.
- **Does not show:** that the seasonal term, or v2's feature set, is better than v1's; that real buyers behave like any θ; that hub differences are solved; that the result transfers beyond these five hubs and same-carrier connections.

#### Reproducing

```bash
python -m mcp.v2 select && python -m mcp.v2 fit     # v2 selection on 2025 and the final fit (no 2026)
python -m mcp.holdout                                # reads the 2026 months once; results/holdout.json and docs/figures/holdout_*.png
```
