# Validation

## Map of this file

This file is long because it records everything, including what went wrong. Start with the row that matches your question.

| If you want to know | Go to |
| --- | --- |
| Does the original all-purpose cover (v1, v2) price well on data it never saw? | Part 3C (the January to August 2026 holdout) |
| What did not go as hoped? | Part 3C, "What did not go as hoped", and Part 4 (independent review) |
| Who already pays for a missed connection, and what is left for a new product? | 5A (BTS delay causes), 5H (airline hotel commitments) |
| What does the gap cover earn, and where does it lose money? | 5E, 5G (as sold), **5I (26 backtest months)** |
| How much does the minimum connection time matter? | 5G |
| What does the price loading do, and what is pre-registered about it? | 5L |
| How much do results depend on which connections travellers book? | 5K |
| How real is the data? | 5H (coverage) and 5K (what is observed and what is constructed) |
| What attach rate does the cover need? | 5J |
| What was predicted before the data, and how did it turn out? | Part 3B, `PREREGISTRATION_2026H2*.md`, and the [scoreboard](SCOREBOARD.md) |

The parts were written in order and **earlier parts are not edited after later results**: a correction goes in the later part, marked as one (for example the correction in 5D that 5G makes).

This file is written in two parts. **Part 1 (below) was committed before the test window was read.** Part 2 (results) is appended after the single backtest run. Nothing in Part 1 was changed after seeing results; a git diff shows it.

## Part 1: Backtest protocol (frozen before reading H2 2025)

**Frozen artefacts** (SHA-256, commit `55497c6`)

| File | SHA-256 |
| --- | --- |
| `models/pmiss.joblib` (GBM + isotonic calibrator) | `e5094792b7f758dd2226d67a7afbc77a247807d097ebcdb1a860846f666f5870` |
| `config/pricing.yaml` (costs, loss ratio, WTP cap) | `77f42b8f26d31f058fc2fce77a0cf981bb2dcdf9a7dd3be8e1fcce2549b3e497` |

> *Added later, see Part 4I:* the `config/pricing.yaml` hash above is of the file as it sat on the author's machine, which had mixed line endings. The repository stores the same settings with Unix line endings, whose hash is `75e1db9fda3e188955a0201ea9a29ae317c88deec5619395cfe2bfd89a9e8979`.

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
- **Does not show:** that real passengers would behave like this. Connections are synthetic; the minimum connection time is assumed (miss rates at MCT 35/45/60 on the training window: 7.35% / 7.92% / 8.23%; these rebuild the whole population, since MCT also decides which pairings exist, so they are not a pure label sensitivity); severity is a lower bound; costs, loss ratio and WTP are assumptions; buyer behaviour (θ) is unknown. Dollar assumptions barely move the headline ratio (it is a cost-weighted calibration ratio) but they do set the price levels and the offered set.
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
2. **The `month` feature and a frozen calibrator hurt.** v2 static priced 17% too high, and its month-by-month prediction peaked at 12.0% in July against 9.6% observed. That is consistent with the worry from step 5: with two years of data, a month feature still partly memorises one-off events (July 2024 was 11.8%). v2 rolling (62.3%) beats v2 static (53.7%) with the same model and the same month term, so what separates them is **re-fitting the calibrator monthly**. Whether the month term itself helped or hurt cannot be isolated, because no "v2 without month" variant was pre-registered. (In the 2025 walk-forward the month term helped: pooled log loss 0.25104 with it against 0.25181 without, under isotonic calibration over six months.)
3. **Hub structure persists, and it is the clearest remaining defect.** v2 rolling by hub: ORD **1.156 [1.018, 1.309]** (priced too low, interval excludes 1), ATL 1.031, DEN 0.933, DFW **0.876 [0.774, 0.981]** and CLT **0.880 [0.781, 0.996]** (priced too high). The same ordering appeared in H2 2025 for v1 (ORD 1.040, DFW 0.896, CLT 0.768) and holds for every schedule here. A hub-level correction was a candidate in v2 selection and was not chosen by the pre-declared rule.
4. **The shape across slack differs by model.** v1 over-predicts tight connections (24.1% vs 20.6% observed at 45 to 59 minutes, +17%) and is accurate at long slack. v2 rolling is accurate at tight slack (20.3%) and too high at long slack (4.0% vs 3.3% at 210+ minutes, +21%). Tight connections carry most of the claim cost, so this matters for pricing.
5. **Only 35 weeks and eight months.** The intervals are wide (about ±0.08 around the ratio), and some of the seasonal questions need a full second cycle.

#### What this shows

- **Shows:** on genuinely new data, v1 (frozen before 2026, using no 2026 information) priced 2026 within about 7% of the target loss ratio, and v2 with monthly recalibration within about 4%. The latter uses outcomes up to the end of the previous month, which a real booking lead would not allow (Part 4 tests a lag). Re-fitting the calibrator monthly fixes the biggest weakness of a frozen price (v2 static priced 17% high). Tiering protects the loss ratio against selection on information the price already contains; selection on information it does not contain is simulated in Part 4. The 2024 baseline would have lost 11 points of margin.
- **Does not show:** that the seasonal term, or v2's feature set, is better than v1's; that real buyers behave like any θ; that hub differences are solved; that the result transfers beyond these five hubs and same-carrier connections.

#### Reproducing

```bash
python -m mcp.v2 select && python -m mcp.v2 fit     # v2 selection on 2025 and the final fit (no 2026)
python -m mcp.holdout                                # reads the 2026 months once; results/holdout.json and docs/figures/holdout_*.png
```


---

## Part 4: Independent review, and what changed (post-hoc)

After the 2026 holdout an independent reviewer (a separate model instance, read-only, instructed to be sceptical) audited the whole repository. Each finding was checked against the code and data before anything was changed. **The results and hashes of Parts 1 to 3 are untouched.** Wording that overstated them was corrected in place (the git history shows each change); new analyses are labelled exploratory because both test windows had by then been read.

### 4A. Findings and what was done

| # | Finding | Checked? | Action |
| --- | --- | --- | --- |
| 1 | The adverse-selection test lets buyers select on the model's own probability, so a calibrated model passes almost by construction | Yes (`backtest.py`, `holdout.py`: purchase weight uses the pricing model's P(miss)); the baseline degrades with θ and the calibrated model does not, as predicted | Added selection on hidden information (4C); reworded the README, brief, demo and method |
| 2 | v2 "rolling" calibrates on all of the previous month, but a booking is made weeks before the flight | Yes | Added a lag option and an exploratory run (4B) |
| 3 | Pre-registration cannot be verified from the public record | Yes: protocol commits reached GitHub together with the results; commit times are the author's; an early force-push rewrote history | Reworded; the two model files are now in the repository so the hashes can be checked; the next test's protocol is written before its data exists (`PREREGISTRATION_2026H2.md`) |
| 4 | Demo slider ran past the data and crashed; the thumb started at the wrong position | Yes (slider max 225, buckets end at 210) | Fixed; a Node test drives all 901 control combinations and a second test confirms it catches the old bug |
| 5 | README said Brier skill "about 5%" over the baseline | Yes (5% is the baseline over a flat rate; the model over the baseline is 0.5 to 2.6%) | Corrected to 1 to 2% |
| 6 | "In every version" the hub gaps are 16% and 12% | Yes: ORD is 1.072 for v1, 0.998 for v2 static, 1.156 for v2 rolling | Quoted per model; the demo generates its hub note from the results |
| 7 | Cut-off line: "45 at ATL" means no cut-off; the 50% rule was not stated | Yes: share of connections within the cap at 45 to 59 minutes is ATL 59%, DEN 45%, ORD 37%, DFW 34%, CLT 28% | Reworded; the calculation is unchanged |
| 8 | Seasonality and "no 2026 knowledge" statements contradicted each other | Yes | Corrected in four places |
| 9 | Outbound cancellations excluded from the label, not defined in the product | Yes: 928,102 against 5,261,045 missed in 2024, 17.6% as many | Benefit definition in the brief; sensitivity stated |
| 10 | MCT 35/60 change the population, not just the label | Yes (code) | Reworded; a clean label-only sensitivity is meaningless because the pairings themselves change |
| 11 | "27 weeks at any volume" is wrong; the pause rule ignores volume | Yes (89 weeks at 100 policies a week) | "At least 27 weeks"; volume-aware pause thresholds in `mcp.experiment` and the brief |
| 12 | Intervals probably a little narrow | Yes (4D) | Caveat documented |
| 13 | DB1B weights depend slightly on cancellations | Yes, the effect is at most 0.014 percentage points on a 7 to 10% rate | Documented; frozen weights not changed |
| 14 | Weak tests (an assertion that could not fail; name-based window guards; no ordering, key-matching or negative-timezone tests) | Yes | Fixed or added, apart from the guards: they stay name-based by design, and `v2.py` is allowed to read H2 2025 because that is development data for v2 |
| 15 | Unpinned requirements; EDA step missing from the README; "last 6 months" is 3 to 5 early in 2026 | Yes | `requirements.lock`; README step added; documented below |
| 16 | The loss ratio realizes the miss event only; the demo shows v1's level, which ran 10% high | Yes | Stated in the README; the demo has a level note generated from the results |

Suspicions raised and checked: DB1B has no quarter after 2025 Q2 (still true on 8 November 2026; 2025 Q3, Q4 and 2026 Q1 return not found); regional carriers may be paired across brands (a real limitation, documented); the sales mix is held fixed regardless of price (stated in Part 1); model and calibrator estimation uncertainty is not in the intervals (documented).

### 4B. Does the monthly recalibration depend on seeing the whole previous month? (exploratory, second read of the 2026 months)

v2 rolling prices month *m* with a calibrator fitted on every month up to *m*-1. A real booking is made weeks before the flight, so this re-prices 2026 with the calibrator lagged by one and two further months. The zero-lag row reproduces the pre-registered run exactly (the script aborts otherwise). This is **not validation**: the window had already been read.

| Price | Realized ÷ target [95% interval] | Loss ratio | Brier | Log loss | ECE | Mean predicted (observed 8.14%) |
| --- | --- | --- | --- | --- | --- | --- |
| v1 as shipped (frozen calibrator) | 0.931 [0.853, 1.017] | 60.5% | 0.07125 | 0.26168 | 0.0108 | 8.95% |
| v2 rolling, no lag (pre-registered) | 0.958 [0.875, 1.043] | 62.3% | 0.07079 | 0.26000 | 0.0051 | 8.65% |
| v2 rolling, 1-month lag | 0.934 [0.851, 1.017] | 60.7% | 0.07086 | 0.26042 | 0.0075 | 8.88% |
| v2 rolling, 2-month lag | 0.918 [0.843, 0.995] | 59.7% | 0.07081 | 0.25995 | 0.0088 | 9.02% |

Staleness costs little: the loss ratio moves by about three points and the proper scores barely change (log loss is even marginally lowest at a two-month lag), but calibration error rises (ECE 0.0051 to 0.0088) because the level was **falling** through 2026 and an older calibrator over-prices. In a period of rising level the same lag would under-price, so the sign is specific to this window. The pre-registered headline stands; the fair reading is that the policy is feasible with a booking lead, at a small cost in calibration.

### 4C. Selection on information the price does not have (exploratory, development data)

The θ curve in Parts 2 and 3 lets buyers select on the model's own probability. Here each connection also has a hidden risk factor that buyers see and the price does not (log-spread κ), and buyers favour risky connections with strength θ. Then, whatever the data, per-connection pricing runs at **exp(θκ²) × target**, and a flat price suffers that plus the selection on visible risk. Simulated on the development connections (`mcp.selection`):

| κ | θ | Per connection (simulated) | exp(θκ²) | Flat price (simulated) |
| --- | --- | --- | --- | --- |
| 0.1 | 0.5 | 1.01 | 1.01 | 1.41 |
| 0.1 | 1.0 | 1.01 | 1.01 | 1.87 |
| 0.25 | 0.5 | 1.03 | 1.03 | 1.44 |
| 0.25 | 1.0 | 1.07 | 1.06 | 1.98 |
| 0.5 | 0.5 | 1.13 | 1.13 | 1.58 |
| 0.5 | 1.0 | 1.27 | 1.28 | 2.36 |
| 1.0 | 0.5 | 1.44 | 1.65 | 1.99 |
| 1.0 | 1.0 | 1.96 | 2.72 | 3.53 |

Three things to read from it. Per-connection pricing is never worse than a flat price. It is not immune: at κ = 0.5 and θ = 1 it runs 27% over target. And κ cannot be measured from public data. The model's own errors by month and by hub are a floor (their log-spread is 0.14 and 0.12, about 2% exposure at θ = 1), and how much more buyers know is exactly what the brief's H2(b) measures, without paying a claim. As a check on the simulation, a flat price with κ near zero simulates to 1.87 at θ = 1; the real 2026 holdout measured 1.80. For κ ≥ 1 the closed form overstates exposure (probabilities cannot exceed 1), and the θ = 2 rows with κ ≥ 0.5 depend on a handful of extreme draws (`tests/test_selection.py`).

### 4D. Intervals

The bootstrap treats weeks as independent. The level also moves by month, so a t-interval over the eight monthly observed ÷ predicted ratios is wider:

| Price | Monthly ratios, mean ± t-interval | Bootstrap half-width |
| --- | --- | --- |
| v1 as shipped | 0.911 ± 0.107 | 0.082 |
| v2 rolling | 0.956 ± 0.125 | 0.084 |

Neither changes whether the interval contains the target (v1's monthly interval is 0.80 to 1.02; v2 rolling's 0.83 to 1.08), but the stated intervals are best read as lower bounds on the uncertainty. They also exclude uncertainty in the fitted model and calibrator.

### 4E. Small facts recorded

- **Weight dependence on cancellations:** weighting each pairing by route passengers ÷ the number of pairings with a valid status, rather than ÷ all pairings, changes the weighted miss rate by 0.008, 0.012 and 0.014 percentage points (March 2024, March 2025, July 2025). Not changed, so the frozen results stay reproducible.
- **"Last six known months"** is fewer in early 2026: the calibrator sees 3, 4 and 5 months in January, February and March, and January's rolling prediction equals the static one.
- **Outbound cancellations** are 17.6% as many events as missed connections; a quarter also had a disrupted arriving flight.

### 4F. Not done in this round

Seat availability, live severity, cross-carrier connections and a seasonal term that helps remain open; they are in the brief's roadmap.


### 4G. A dry run of the monthly job, and what it says about its own thresholds

`python -m mcp.monitor --replay 2026-01 2026-08` runs the monthly policy over the 2026 months, one at a time, each priced only from earlier months (no lag). It is an operational rehearsal on months already spent as a test, not a validation. It also builds `models/v2_state.json`, the state the next pre-registered test starts from.

| | Result |
| --- | --- |
| Months the job would have said "recalibrate" (overall realized ÷ expected outside 1 ± 10%) | 5 of 8 (2026-01, 2026-03, 2026-04, 2026-05, 2026-08) |
| Hub-months flagged "review" (outside 1 ± 20%) | 15 of 40 |
| Weeks above the pause threshold (1.53× expected) | 1 of 42; months with two in a row: none |
| Monthly realized ÷ expected, range and spread | 0.81 to 1.20, standard deviation 0.15 |
| Weekly realized ÷ expected, spread | standard deviation 0.29 |

**The finding is about the thresholds, not the model.** A month's realized level moves with a standard deviation of about 0.15 around what was expected, so a ±10% band is inside ordinary month-to-month noise and would fire most months; the hub band of ±20% fires on about 38% of hub-months. The bands in the brief (±10% overall, ±20% per hub) are assumptions I chose before this run and **have not been retuned to make it look calmer**. Used as written, the job would be too jumpy to act on monthly. A sensible next version triggers on a rolling window of several months, or on a band sized from the measured spread, and that is done in 4J and in `PREREGISTRATION_2026H2_ADDENDUM.md`.


### 4H. What the day itself would add: value of information (development data)

The spec asks how much a day-of product could improve on a booking-time price. `mcp.voi` answers it. The **alert time is one hour before the inbound flight's scheduled arrival**; then known are how late the inbound flight left (if it had left) and the hub's weather in the previous hour. Fitted on 2024, evaluated on January to June 2025, with the same gradient-boosting model and route history as v1; **cancelled inbound flights are excluded** because an alert for them is trivial.

| Information at the alert time | Brier | Brier vs booking only | AUC | Misses caught in the riskiest 5% | Precision | Caught in the riskiest 10% | Precision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| booking time only | 0.06251 | 0.0% | 0.757 | 19% | 28% | 32% | 24% |
| + inbound departure delay | 0.03524 | 43.6% | 0.953 | 52% | 75% | 76% | 55% |
| + hub weather | 0.06201 | 0.8% | 0.768 | 20% | 29% | 34% | 25% |
| + both | 0.03503 | 44.0% | 0.956 | 52% | 75% | 77% | 55% |

- **Departure delay is worth a lot.** An alert on the riskiest 5% of connections catches about half of all misses at about three in four precision, against 19% at 28% from booking-time information. **Hub weather adds almost nothing** (under 1%), most likely because a delayed inbound flight already carries the weather's effect.
- **A miss is mostly a late arrival, not a cancellation:** 82% of missed connections follow a late arrival, 15% an inbound cancellation and 3% a diversion. The cancelled ones (excluded above) are knowable even earlier, so the figures here understate what a real alert could catch.
- **This is the project's main finding seen from the other side.** The booking-time model's ceiling is low (1 to 2% over a connection-time baseline) because what separates a missed connection from a made one is mostly not known when the price is quoted. A day-of product is a different product: alerts and rebooking help, not a price.
- **What it does not show:** that an alert would help anyone. That depends on whether the traveller can act an hour before landing (rebook, tell the airline, find the next gate), on a real-time data feed with its own cost and delays, and on the alert's false-alarm cost (one in four alerts is a false alarm even at the top 5%).

**A correction recorded in the open.** The first version of this analysis told the model each inbound flight's **final** departure delay. For a flight that left after the alert time, that delay was not knowable then. The corrected version gives the model only what is observable at the alert time (the real delay if the flight had left, otherwise that it had not and how long it had been waiting). The first version overstated the value: departure delay alone gave a 52.1% Brier improvement, AUC 0.961 and 57% of misses caught in the top 5%; corrected, 43.6%, 0.953 and 52%. Tests (`tests/test_voi.py`) pin the corrected timing, including that two flights that had not left yet look identical whatever their final delay turned out to be.


### 4I. A hash that nobody else could reproduce, found and corrected

While preparing the pre-registration for the next window, the hash of `config/pricing.yaml` as committed was compared with the hash frozen in Part 1 and **did not match**. The cause is line endings, not content: the file on the author's machine had mixed endings (five Windows-style lines from when it was first written, sixteen Unix-style lines appended later), and git stores text with Unix endings. So the hash in Part 1 (`77f42b8f26d31f05…`) is a hash of bytes that exist only on that machine, and anyone cloning would have got a file hashing to `75e1db9fda3e1889…`.

- **The settings did not change.** Parsed, the two files are identical, and their bytes are equal once Windows endings are converted to Unix endings (checked).
- **Fix:** the file is now stored and checked out with Unix endings on every system (`.gitattributes` pins the hashed text files), its true hash is `75e1db9fda3e188955a0201ea9a29ae317c88deec5619395cfe2bfd89a9e8979`, the pre-registration uses that hash, and a test fails if it drifts. Part 1 keeps its original text with a footnote.
- **Anyone can reproduce it on any system:** `python -c "import hashlib;print(hashlib.sha256(open('config/pricing.yaml','rb').read().replace(b'\r\n',b'\n')).hexdigest())"` prints `75e1db9fda3e188955a0201ea9a29ae317c88deec5619395cfe2bfd89a9e8979`.
- The other frozen files were checked the same way and match their committed versions byte for byte: the two model files, `config/guards.yaml` and `models/v2_state.json`.


### 4J. A principled alert rule, and what it cannot see

The 4G finding led to a replacement rule: alert on the claim-weighted realized ÷ expected over the last 3 months, outside 1 ± 2σ/√3, with σ measured on the **2025** walk-forward only (0.119 overall from 6 months, 0.267 per hub from 30 hub-months, giving bands of ±0.137 and ±0.308). The rule, its parameters and the expectations for the next window are frozen in `PREREGISTRATION_2026H2_ADDENDUM.md` (config hash `bcf4e04866706278…`). The author had seen the 2026 spread before writing it, so the derivation is from 2025 data but not blind.

| 2026 replay (spent data, a consistency check) | Old single-month bands | Rolling rule |
| --- | --- | --- |
| Overall "recalibrate" alerts | 5 of 8 months | 0 of 6 checked months |
| Hub alerts | 15 of 40 hub-months | 1 of 30 hub checks (Chicago, April: rolling ratio 1.36) |

**What the quiet costs.** The rule is slow and its hub band is wide, so it cannot see steady small gaps. Chicago ran about 16% under-priced and Charlotte and Dallas about 12% over-priced across the 2026 test, and none of that alerts: it sits inside ±0.31. Alerting less is only a gain if the alerts that remain are the ones that matter; here a persistent hub error is exactly what goes unflagged. Detecting it needs a cumulative rule or a hub-level calibration, which this project has not built.


## Part 5: v3, the overnight gap cover (senior audit, round 1)

An audit of the project's own assumptions, done after Part 4. Each item says what was assumed, what the data says, and what changed. v1 and v2, and their pre-registered test, are untouched: v3 has its own files (`MCP_VARIANT=v3`), its own model and its own pre-registration, `PREREGISTRATION_2026H2_V3.md`.

### 5A. Who pays for a missed connection already (BTS delay causes)

BTS codes every delay of 15 minutes or more to a cause. The new `mcp.causes` gives each missed connection the cause of its inbound flight's problem: the dominant cause by minutes, or the cancellation code. On v3 connections, January 2024 to August 2026 (27.0 million weighted misses):

| Cause of the inbound problem | All misses | Overnight misses |
| --- | --- | --- |
| Airline (carrier) | 27.5% | 19.5% |
| Late-arriving aircraft | 31.9% | 41.8% |
| Weather | 14.6% | 12.5% |
| Air traffic control and airport (NAS) | 13.8% | 15.7% |
| Security, diverted, not coded | 12.3% | 10.6% |

US airlines commit to a hotel for overnight disruptions **they control** (DOT Airline Customer Service Dashboard). The rest is a gap the passenger pays for. That gap is **72.5%** of all misses if only "carrier" counts as controllable, and **40.6%** if late-arriving aircraft count too. For overnight misses it is 80.5% and 38.8%. BTS does not say why the aircraft was late, so the truth lies between the two.

Chicago and Denver lose about 20% of misses to air traffic control. Dallas loses 21% to weather.

**What changed.** The product question became sharper. A cover that pays for every missed connection mostly duplicates what the airline already owes. A cover that pays only in the gap does not. That is v3.

### 5B. Costs from an official source, not assumed

The $180 overnight assumption was replaced by the GSA per-diem rate for the hub's ZIP code and month: lodging plus meals and incidentals (`mcp.costs`, cached pages under `data/external/gsa/`). A night costs $198 to $295 on annual average, by hub and fiscal year. The $180 was 9 to 39% too low, with seasonal swings on top (Chicago lodging runs from $142 to $234 a month in FY2026).

### 5C. How tickets are sold, not who flies the plane

v1 paired flights by the airline that **operated** them. A passenger booked on American through Charlotte may fly a PSA or Piedmont regional flight, which v1 treated as a different airline, so that connection was missing. v3 uses BTS's marketing-carrier file and pairs flights within the **marketing** network, with DB1B route weights by ticketing carrier.

In 2025 that gives **115.8 million** connections against 55.5 million in v1, and American's weighted passengers rise from 19.1 to 35.7 million. The weighted miss rate is 8.7% against 8.2%.

### 5D. The v3 model, its selection, and a mistake in what the selection measured

The v2 rule (pooled log loss, ties to the simpler policy) chose **no recalibration** on the October 2025 to August 2026 walk-forward with a one-month booking lag. Pooled realized/target was 1.03, with hubs ranging from 0.89 to 1.32 (`results/v3_selection.json`).

A smoke test of the test code on July and August 2026 then showed **1.36**. The cause was two flaws in how v3 was selected:

- it ranked candidates by error over all connections, although the cover pays only on overnight ones;
- it weighted by passengers, although the cover's result is in dollars.

The robustness check (`scripts/v3_robustness.py`, development data only) asked whether anything fixes it:

| Specification | Spread of monthly ratios | Worst month |
| --- | --- | --- |
| Chosen (all connections, no month term, no recalibration) | 0.188 | 1.38 |
| Trained on overnight connections only | 0.187 | 1.38 |
| With a month term | 0.168 to 0.190 | 1.33 to 1.41 |
| Any recalibration (global or per hub, 1 to 6 months) | 0.18 to 0.25 | 1.31 to 1.46 |

**Nothing does.** The month term only moves which months are wrong: it under-prices fall 2025 instead of summer 2026, because fall 2024 was calmer. Judged by the correct cost-weighted log loss, the chosen model still ranks first (0.26303, a statistical tie with its overnight-trained twin at 0.26266). **So the model was not changed. The conclusion changed.**

The gap cover insures a **correlated weather and air-traffic risk**: whole months come in 20 to 40% above or below the price, and no information available at booking predicts which. That risk is carried by the margin, not by the model. At a 0.65 target loss ratio, break-even is a realized/target of 1.54. The worst development month (1.38) is a loss ratio of 90%. **Correction: that sentence was about all overnight-risk connections. The cover as it would be sold is worse; see 5G.**

### 5E. Development orientation, March to August 2026 (not validation)

The final model, trained through February 2026, is out of sample here (`results/v3_dev.json`).

| | Primary (no recalibration) |
| --- | --- |
| Realized/target, pooled | **1.12** [1.01, 1.23] |
| By month, March to August | 1.03, 0.84, 0.98, 1.20, 1.35, 1.37 |
| By hub | Atlanta 1.14, Charlotte 0.98, Denver 1.14, Dallas 1.02, Chicago 1.31 |
| Mean price per overnight-risk connection | $34.65 |
| Share offered within a 3% / 5% / 7% fare cap | 20% / 39% / 51% |
| Realized/target on the offered subset at 5% | **1.22** |

**The winner's curse, measured.** Offering cover only where the price is low selects connections whose risk the model under-estimates, so the offered subset runs about 9% worse than all connections. A price loading on offered cover would correct it. It is not added here, because fitting it on these months would make the pre-registered test grade its own homework. It is the first change for a v4.

**The price cap is now sourced.** Comprehensive travel insurance costs about 4 to 10% of trip cost; Squaremouth's recent sales average about 6%. Policies cap missed-connection benefits at about $500 to $2,500. A single-risk add-on should cost less than full insurance, so the cap is 5% of fare, with 3% and 7% reported.

### 5F. What is frozen for September to December 2026

The pre-registration `PREREGISTRATION_2026H2_V3.md` (tag `prereg-2026h2-v3`) fixes the model, state and GSA table hashes, two arms (primary, and per-hub level as a declared second arm), and six falsifiable expectations:

- calibration within 1 ± 2σ/√n;
- no month above break-even;
- the winner's curse inside the cap;
- the per-hub arm narrows the hub spread;
- the gap is 70 to 90% of overnight misses;
- 25 to 55% of overnight-risk connections priced within the cap.

It also lists everything the author saw before writing it. A weekly workflow (`.github/workflows/watch-bts.yml`) opens an issue as each month is published, so the test cannot be quietly skipped.


### 5G. Audit, round 2: what the first round left open (development data, March to August 2026; the pre-registered window is untouched)

Written on 8 November 2026, before the September to December data exists. Code: `src/mcp/v3_audit.py`, results: `results/v3_audit.json`, tests: `tests/test_v3_audit.py`. None of it changes the frozen v3 model or its pre-registration.

**A correction in the open.** In 5D, the memo, the brief and the README I wrote that the worst development month "still leaves a thin margin" (an 89% loss ratio). That was true for **all** overnight-risk connections. It is not how the cover would be sold. Sold only where the price is within the 5% cap, the same months look like this:

| | All overnight-risk connections | Sold within the 5% cap |
| --- | --- | --- |
| Average weekly loss ratio (target 65%) | 73% | **78%** |
| Worst week | 114% | 128% |
| Weeks above 100% | 1 of 28 | **8 of 28** |
| Worst month | 89% | **111%** (July) |
| Cost of a weekly stop-loss at 100% / 90% attachment, per unit of premium (no loading) | 0.5% / 1.5% | 3.9% / 7.8% |

Monthly loss ratio as sold: 03: 82% | 04: 45% | 05: 59% | 06: 78% | 07: 111% | 08: 94%. All before commission, payment fees and handling. The worst hub-week as sold was Chicago, at 932% of that week's premium. With 28 weeks the numbers are indicative, not an estimate of a tail.

**Why the sold view is worse.** The cap lets through connections whose predicted risk is low, and those are partly the ones the model under-estimates (the winner's curse). Realized/target on the connections within the cap is **1.20**, against 1.12 for all of them, and it hardly moves with the cap or the target loss ratio:

| Share of overnight-risk connections offered | cap 3% | cap 5% | cap 7% | cap 10% |
| --- | --- | --- | --- | --- |
| target loss ratio 55% | 15% | 32% | 45% | 57% |
| target loss ratio 65% | 20% | 39% | 51% | 63% |
| target loss ratio 75% | 25% | 44% | 56% | 67% |

Realized/target on what is offered is 1.17 to 1.23 in every cell. At the 65% target and the 5% cap the realized loss ratio is 78%; at a 75% target it is 91%. The 65% target is itself an assumption: no US regulator publishes a travel-insurance loss ratio (`docs/market-evidence.md`).

**Is it the model, or the weather? (refit bootstrap).** The gap model was refitted 8 times on resamples of 2,500,000 rows of its training sample (4,999,330 rows), and the same March to August connections were scored each time. Pooled realized/target: mean 1.123, standard deviation 0.0075, range 1.115 to 1.136, against 1.117 for the frozen model. Share offered within the cap: 38.7% to 40.0%. For comparison, resampling whole weeks gives an interval of 1.02 to 1.23. **Refitting moves the result by roughly a tenth of what the weather does.** The frozen model is not an unlucky draw; the uncertainty is in the risk, not the model. (The resamples come from the model's own 5-million-row training sample, so this understates variation from the choice of that sample.)

**The minimum connection time.** The model assumes 45 minutes at every airport; real minimums differ by airport, airline and terminal (`docs/market-evidence.md`). Hubs are independent, so one table covers every combination. It scores the frozen model's prices on connections built and labelled with a different minimum, first as they are, then with the gap re-expressed above the true minimum:

| True minimum | 35 min | 45 min (assumed) | 60 min |
| --- | --- | --- | --- |
| Realized/target, model told the scheduled gap | 0.90 | 1.12 | **1.57** |
| Realized/target, model told the buffer above the minimum | **1.11** | 1.12 | **1.13** |
| Share offered within the 5% cap, told the buffer | 40% | 39% | 39% |

By hub (35 min: as is / buffer; 60 min: as is / buffer):

| Hub | 35 min | 45 min | 60 min |
| --- | --- | --- | --- |
| ATL | 0.89 / 1.12 | 1.13 | 1.64 / 1.14 |
| CLT | 0.81 / 0.98 | 0.98 | 1.34 / 0.99 |
| DEN | 0.88 / 1.13 | 1.14 | 1.68 / 1.13 |
| DFW | 0.86 / 1.03 | 1.03 | 1.34 / 1.03 |
| ORD | 1.06 / 1.31 | 1.31 | 1.86 / 1.34 |

**It was an input-definition error, and it is fixed without retraining.** A connection is missed when the passenger has less than the minimum between the real arrival and the real departure, so the risk depends on the buffer above the minimum, not on the scheduled gap alone. The model was built with 45 minutes. For an airline whose minimum is m it is told the scheduled gap minus (m − 45): `mcp.v3.model_slack`. A 70-minute gap at a 60-minute airport is a 10-minute buffer, which the model knows as a 55-minute gap. The same frozen model then prices connections at 35 and at 60 minutes, two minimums it never saw, as well as it prices 45 (1.11, 1.12, 1.13), and the hub pattern is unchanged (Chicago stays the worst). The demo has the selector.

Three things this does **not** show. (1) The label uses the same rule, arrival plus the minimum later than departure, so part of this is by construction: it removes a modelling error, not the question of whether an airline's minimum is the right definition of a missed passenger. That needs real itineraries (`docs/agency-inputs.md`, rows 1 and 2). (2) It was checked from 35 to 60 minutes only. (3) After the re-expression no connection is scored outside the range the model was trained on, which the as-is scoring was not (4.1% of the 35-minute connections had under 45 minutes scheduled).

**A prediction written before the data exists (not part of the frozen set).** Expectation V2 in `PREREGISTRATION_2026H2_V3.md` ("no month above 1.54") is judged on all overnight-risk connections, as the test code computes it, and development passed it. On the sold view development did not (July, 111%). If September to December behave like this, V2 will pass as written and the sold loss ratio will still exceed 100% in at least one month. The test code is frozen by tag, so the sold view will be computed afterwards with `mcp.v3_audit` and reported as exploratory.

**When the test is read.** Decided on 8 November 2026, before any of the data exists: the first read is when November 2026 is published (probably early February 2027), covering September to November, with `python -m mcp.holdout_v3 9 10 11`. It is not run earlier on fewer months, whatever the first months look like.

**Not done.** A price loading for the selection effect (it would be fitted on these months and then graded on them); a model that takes the minimum connection time as an input; a real reinsurance quote.

### 5H. Who already pays, what the cover leaves out, and how much real traffic it represents (development data, January 2024 to August 2026)

Written on 9 November 2026, before the September to December data exists. Code: `src/mcp/commitments.py`, `outbound.py`, `coverage.py`; results: `results/commitments_v3.json`, `outbound_v3.json`, `coverage_v3.json`. None of it changes the frozen v3 model or its pre-registered test, which apply one rule to every airline.

**Not every airline pays for the hotel.** The US DOT's dashboard lists whether each airline commits to a free hotel after an overnight delay it controls. As read on 9 November 2026 (`data/external/dot/hotel_commitments.json`), every named airline does except **Frontier**; one row carries no carrier name and is not guessed. For an airline that does not commit, a missed connection that ends in a night away is a gap whatever its cause, so the right trigger is "any miss". Overnight misses by airline:

| Airline | Share of overnight misses | Commits to a hotel | Caused by the airline | Share the cover pays, under its own commitment |
| --- | --- | --- | --- | --- |
| AA | 47.7% | yes | 15.3% | 84.7% |
| DL | 13.5% | yes | 28.9% | 71.1% |
| F9 | 6.0% | **no** | 24.3% | 100.0% |
| NK | 0.4% | yes (not named on the page) | 20.0% | 80.0% |
| UA | 24.1% | yes | 22.5% | 77.5% |
| WN | 8.3% | yes | 15.8% | 84.2% |

Overall the share of overnight misses the cover pays for moves from 80.5% (one rule for all) to **82.0%** under each airline's own commitment; the one airline the page does not name (Spirit is not confirmed) is 0.4% of the total, so counting it either way gives 82.0%. By hub: ATL 72.4% → 74.0% | ORD 80.6% → 80.6% | DFW 83.6% → 84.2% | DEN 78.7% → 82.9% | CLT 86.4% → 86.5%. It matters most at Denver, where Frontier flies. The dashboard changes and the saved copy is dated; a launch would refresh it.

**Onward flights cancelled for reasons that are not the airline's.** The v3 label excludes pairs whose onward flight was cancelled, so a storm that cancels the flight a traveller was about to board pays nothing. Over the same connections and weights, overnight onward cancellations coded to weather, air traffic or security came to 1,063,120 weighted events against 5,129,458 missed-connection gaps the cover does pay for (weather 980,735, air traffic 81,952, security 433): **20.7% more events**. Those coded to the airline (240,606, 4.7%) are ones the airline owes a hotel for, so they stay out. By hub: DFW 32%, CLT 25%, ORD 21%, ATL 16%, DEN 9%. By month the addition ranges from 5% to 74% of the gap events, so it is a storm risk too. Whether to sell it is a product decision (`docs/agency-inputs.md`, row 6); it is not in the pre-registered test.

**How much real traffic the connections represent.** The DB1B ticket sample says how many passengers really flew each route through the five hubs on one ticket: **97.7%** of them are on a route with at least one pairing in our connections. Of the pairings we build, 78.7% sit on a ticket-sample route and get a weight; the others are dropped. They could bias the headline if they missed at a different rate, and they do not: 9.15% against 9.23% (-0.08 points, March to August 2026). The regional-brand mismatch of v1 is gone because v3 pairs within the marketing network. What remains is which passengers actually connected, which public data does not say.


### 5I. A rolling-origin backtest: 26 out-of-sample months instead of six (development data, 2024-07 to 2026-08)

Code: `src/mcp/v3_rolling.py`; results: `results/v3_rolling.json` and the weekly series `results/v3_rolling_weeks.csv`. The same specification (v1 features, the gap label, no recalibration) was refitted at nine origins, each trained only on data before the block it then scored, so every one of the months was priced by a model that had not seen it. It is **not a clean test**: the specification was chosen on October 2025 to August 2026, a choice among 20 candidates. The pre-registered window is never read.

| | All overnight-risk connections | Sold within the 5% cap |
| --- | --- | --- |
| Pooled realized/target | 1.04 | 1.15 |
| Monthly realized/target: mean, sd | 1.05, 0.24 | 1.16, 0.40 |
| Monthly realized/target: range | 0.65 to 1.54 | 0.51 to 1.85 |
| Mean of the monthly ratios, 95% interval (3-month block bootstrap) | 0.91 to 1.17 | 0.94 to 1.31 |
| Same, t-interval over the months | 0.95 to 1.15 | 0.99 to 1.32 |
| Months with a loss ratio above 100% | 1 of 26 | **6 of 26** |
| Weeks with a loss ratio above 100% | 10 of 114 | **28 of 114** |
| Worst week | 127% | 248% |
| Realized loss ratio, pooled (target 65%) | 68% | **75%** |

**What it settles.** The six-month result (1.12, with single months from 0.84 to 1.37) was not a freak: over 26 months the monthly ratio has a standard deviation of 0.24, against the 0.197 used in the pre-registration, which came from 11 months. The cover as it would be sold lost money in 6 of 26 months, so the six-month finding in 5G was a real feature of the product, not a quirk of summer 2026. The month-block intervals are the proper ones: they treat neighbouring months as related, which the weekly bootstrap used earlier did not.

**How long it takes to learn the loss ratio.** From the weekly series, allowing for neighbouring weeks being related (first-order autocorrelation 0.23 as sold): to know the average weekly loss ratio to within ±10% of itself takes about **202 weeks** for the cover as sold (94 for all overnight-risk connections), however many policies are sold, because weather hits everyone in a week at once. That replaces the 27 weeks quoted for v1.

**By hub, over all 26 months.** Realized/target by hub and year:

| Hub | 2024 (from July) | 2025 | 2026 (to August) | All | Months above 1 |
| --- | --- | --- | --- | --- | --- |
| ATL | 1.06 | 1.12 | 1.09 | 1.10 | 16 of 26 |
| CLT | 0.98 | 0.94 | 0.97 | 0.96 | 8 of 26 |
| DEN | 0.83 | 1.23 | 1.08 | 1.10 | 14 of 26 |
| DFW | 0.79 | 1.03 | 0.94 | 0.95 | 11 of 26 |
| ORD | 0.92 | 1.18 | 1.23 | 1.13 | 17 of 26 |

Chicago ran 0.92 in 2024, 1.18 in 2025 and 1.23 in 2026: priced about right at first and under-priced since. That is a drift, not a standing pattern, so the older README line that Chicago is always too cheap was only half right. Denver (0.83, 1.23, 1.08) and Dallas (0.79, 1.03, 0.94) show the same upward movement; Charlotte barely moves (0.98, 0.94, 0.97). The 2024 numbers come from models trained on only six to twelve months, so part of that year's low level is a thin training set; it is not evidence that 2024 was calmer. In March to August 2026 Chicago's error was concentrated in connections of two hours or more (ratio 1.58 to 1.63 beyond three hours against 1.15 under one) and in five weeks that carried 29% of its claims; without them its ratio was 1.14. Its long-connection misses were 50% weather and air-traffic coded (33% and 17%) against 27% at the other hubs, so they are event days, storms and ground stops, that route history cannot see. A per-hub level correction is pre-registered as the second arm of the v3 test.

**The pre-registered band is narrower than 26 months suggest.** `PREREGISTRATION_2026H2_V3.md` expectation V1 uses σ = 0.197 from the 11 months then available. Over 26 months the standard deviation is 0.24, which makes the band for three months 1 ± 0.28 instead of 1 ± 0.23. The tagged test will be judged with 0.197, as written. If it fails V1 only by falling between the two bands, this section is where to look first; both readings will be reported.

**The level drifts.** Priced from earlier months with no recalibration, the model ran below target in 2024 for most hubs and above it since. A model that learns a trend or a rolling level could correct that, and the selection experiment found no recalibration policy that improved the log loss on October 2025 to August 2026. With three years visible, that is worth re-testing in a later version, on windows the first selection did not use.


### 5J. What attach rate the cover needs (arithmetic on measured numbers; demand itself is untested)

Public data cannot say how many travellers would buy. It can say what each policy earns, which fixes what demand has to be (`src/mcp/economics.py`, `results/economics_v3.json`). The cover as it would be sold averaged **$10.01** a policy over the backtest at a **75%** realized loss ratio. The expense ratio and the attach rate are inputs of a grid, not claims.

| Margin per policy sold | expense 0% | expense 10% | expense 20% | expense 30% |
| --- | --- | --- | --- | --- |
| after claims and expenses | $2.52 | $1.52 | $0.52 | −$0.48 |

Profit per 100,000 offers shown:

| | expense 0% | expense 10% | expense 20% | expense 30% |
| --- | --- | --- | --- | --- |
| attach rate 1% | $2,519 | $1,519 | $518 | −$483 |
| attach rate 2% | $5,039 | $3,037 | $1,035 | −$966 |
| attach rate 5% | $12,596 | $7,593 | $2,589 | −$2,415 |
| attach rate 10% | $25,193 | $15,185 | $5,177 | −$4,831 |

Attach rate needed to cover a fixed cost per 100,000 offers shown:

| Fixed cost | expense 0% | expense 10% | expense 20% | expense 30% |
| --- | --- | --- | --- | --- |
| $1,000 | 0.4% | 0.7% | 1.9% | never |
| $5,000 | 2.0% | 3.3% | 9.7% | never |
| $20,000 | 7.9% | 13.2% | 38.6% | never |

**What this says.** A cover that averages $10 a policy and runs at a 75% loss ratio leaves little per policy once the agency's own costs are taken out, and nothing at all once they pass 25% of premium. It is a small-ticket ancillary: viable at very low marginal cost and a loss-ratio target that is actually reached, not as a stand-alone business. The experiment in the product brief is what measures the attach rate; this table says what to beat.

### 5K. What is real and what is modelled, and how much the pairing mix matters (development data, 2024-07 to 2026-08)

Code: `src/mcp/v3_mix.py`, results: `results/v3_mix.json`. Written on 9 November 2026, before the September to December data exists.

**What is observed and what is constructed.**

| Observed (real data) | Constructed or assumed |
| --- | --- |
| Every flight's scheduled and actual times, cancellations, diversions and delay-cause codes: 8.1 million flights, January 2024 to August 2026 (BTS) | Which passengers connected: every same-airline pairing of an arriving and a departing flight, weighted by the route's real traffic |
| Passengers and fares by route and airline (DB1B ticket sample) | The minimum connection time rule (a model input now, `VALIDATION.md` 5G) |
| Hotel and meals rates by hub and month (GSA) | How travellers choose among a route's pairings |
| Which airlines commit to a hotel (DOT dashboard, read 9 November 2026) | The trigger and the target loss ratio |
| Weather at the hubs (ASOS) | Demand |

The one construction that touches every result is the **mix**: public data does not say which of a route's pairings travellers book. Published work on airline booking data finds that some choose a longer connection voluntarily and value connections close to the minimum less (Theis, MIT thesis, 2011), and booking systems show short connections first. The same connections were re-weighted under five stylised mixes:

| Mix | All overnight-risk connections, loss ratio | **Sold within the cap, loss ratio** | Share sold | Months above 100% (sold) | Average scheduled gap |
| --- | --- | --- | --- | --- | --- |
| Equal (as modelled) | 67.9% | **74.6%** | 41.4% | 6 of 26 | 124 min |
| Prefer short connections, gentle (weight e^(−buffer/60)) | 67.3% | **74.1%** | 18.5% | 6 of 26 | 86 min |
| Prefer short connections, steep (e^(−buffer/30)) | 67.2% | **72.5%** | 8.6% | 2 of 26 | 69 min |
| Avoid connections within 15 minutes of the minimum (half as often) | 68.0% | **74.6%** | 44.0% | 6 of 26 | 129 min |
| Prefer long connections (e^(+buffer/60)), the opposite stress | 69.1% | **74.0%** | 67.2% | 5 of 26 | 169 min |

**What survives and what does not.** The cover as sold stays above its 65% target in every mix, between **72.5% and 74.6%**; the all-connections figure stays between 67.2% and 69.1%. So the finding that the sold cover loses to its target does not depend on the one thing public data cannot tell us. **Reach does**: the share of connections that fit the cap runs from 9% to 67%, because short connections are priced out of the cap. Any statement about how many travellers could be offered the cover, including expectation V6 of `PREREGISTRATION_2026H2_V3.md` (25% to 55% priced within the cap), holds for the equal mix only. The months above 100% fall to 2 of 26 in the steepest short-connection mix only because almost nothing is sold there (9%).

The mixes are stylised. They give a range, not an estimate of how travellers choose.


### 5L. The price loading (development data; pre-registered as v4)

Code: `src/mcp/v3_loading.py`, results: `results/v3_loading.json`, frozen artefact `models/v4_loading.json`, pre-registration `PREREGISTRATION_2026H2_V4.md` (tag `prereg-2026h2-v4`).

**The problem.** Sold only where the price is within 5% of the fare, the cover ran a 75% loss ratio against a 65% target over 26 backtest months. The cap lets through the connections the model rates safest, which are partly the ones it under-rates.

**The loading.** A factor on the premium. It raises the price and also changes which connections pass the cap, so the right factor is a fixed point: the smallest one at which the connections that pass the cap *at that factor* realize the target loss ratio.

**Out of sample.** Fitted only on months before each test month, with the one-month booking lag the cover would have, over the 19 months from 2025-02 to 2026-08:

| | Unloaded | Loaded |
| --- | --- | --- |
| Sold loss ratio, pooled (target 65%) | 77.8% | **70.4%** |
| Months above 100% | 4 | 3 |
| Share sold | 40.7% | 36.1% |

It helps and it is **not enough**: it does not reach 65%, because the level rose across the period, so a loading fitted on earlier months was always a little behind. Fitting on the last 12, 9 or 6 months instead gave 69.6%, 72.2% and 70.2%: no better in a way that could be told from noise, so the simplest rule, all history, was kept rather than tuned on the same months.

> *Corrected in 5M:* in the next paragraph, "the loaded price is below the unloaded one" means the loaded **loss ratio**; and the out-of-sample result above belongs to a loading refitted each month (1.00 to 1.23), not to the frozen 1.16.

**Frozen at 1.16**, fitted on all 26 months. On those months the pooled sold loss ratio is 64.8% (from 74.6%) **by construction**, so that figure is not evidence. What is informative: the loaded price is below the unloaded one in 24 of 24 three-month blocks (by 4.0 points at least, 9.6 on average); months above 100% fall from 6 to 1; weeks above 100% from 28 to 17 of 114; the worst week from 252% to 224%.

**What a loading cannot do.** It sets the average. Weather moves a whole month at once, so 17 of 114 weeks still exceed a 100% loss ratio. That is a matter for an exposure cap or reinsurance (`docs/agency-inputs.md`, row 7), not for the price.

**The test and its warning.** `PREREGISTRATION_2026H2_V4.md` fixes four expectations for September to November 2026. That window is the calmest of the year in the data: 38.3% and 45.0% unloaded, 34.3% and 38.1% loaded, with no week above 100% in either year. A good result there does not show the product is fixed; summer is the real test and is a year away.


### 5M. Corrections from an external review (9 November 2026; no result of Parts 1 to 5L changes)

**The demand analysis confused θ with the price response.** `mcp.demand` estimated θ, the selection on risk "beyond price", from a logit on the log price **arm** and log risk. The price shown is risk × payout × arm, so a traveller who reacts to price also reacts to risk, and that coefficient is θ plus the price elasticity: with an elasticity of −1.5 a true θ of +0.5 reads as −1.0, and the go/no-go rule's "θ low enough" check would pass for the wrong reason. The simulator hid this because its travellers reacted to the arm but not to the price they saw. Fixed: travellers in `simulate` react to the price shown; `analyse` estimates θ with log price shown in the model and reports the net tilt (θ plus the price response) as `log_risk_net`; a test plants exactly this case. Sample sizes change: with the price held fixed only the 0.8×, 1.0× and 1.25× arms move price independently of risk (about 5% of the variance of log risk), so telling apart θ that differs by 0.5 at a 2% attach rate needs **50,737** travellers shown, not 2,483 (`mcp.experiment.n_theta_beyond_price`, `results/experiment_design.json`). The 2,483 figure measures the net tilt. Within one hub the spread of log risk across priced cells is 0.67 to 0.82, close to the 0.80 used, so the single-hub experiment the memo proposes is sized about right by these tables.

**The loading's out-of-sample result belongs to a refitted loading, not to 1.16.** In 5L, "the loaded price is below the unloaded one in 24 of 24 three-month blocks" means the loaded **loss ratio**. The 77.8% to 70.4% result comes from a loading refitted each month on earlier months only (1.00 to 1.23, 1.13 on average); the README, the memo, the brief and the demo had attributed it to the frozen 1.16, which is fitted on all 26 months and is first judged on September to November 2026, as `PREREGISTRATION_2026H2_V4.md` already says correctly. Wording corrected in those places.

**Read windows, settled before any data exists.** The documents disagreed on December. `PREREGISTRATION_2026H2.md` (v1 and v2) runs the first read once September to November are published, and allows "one further and final evaluation of the full window" once December is. The scoreboard said the read "never runs twice", and the v3 and v4 documents fix their months at the first read. Decided on 9 November 2026, before any of September to December exists: v3 and v4 are judged on September to November only. For v1 and v2 the December read **will** be run, once, and reported next to the first, so that whether to run it cannot depend on how the first read came out. The BTS watcher now opens an issue only when both files the tests need are published, the Reporting Carrier file (v1, v2) and the Marketing Carrier file (v3, v4). Before, it watched only the first.

**Two runs of the same 26-month backtest disagree slightly.** `v3_rolling` (weekly results, `results/v3_rolling.json`) and `v3_loading` (unloaded figures, from the saved connection rows) report the cover as sold at a 74.8% and a 74.6% loss ratio, with worst weeks of 248% and 252%. Single months differ by up to about two points (February 2025: 73.0% and 75.2%). The code path, the hash-based row sampling and the model seeds are the same in both, so the likeliest cause is that the connection files were rebuilt between the two runs. The committed files cannot confirm it. Read both as one estimate with that much noise, about 75% and about 250%. The README and memo quote the first.

****The gap cover is served.** `/gap-quote` and `python -m mcp.score --gap` price the gap cover from `site/prices_v3.js`, the same table as the demo, with the airline's minimum connection time as an input and the frozen loading. A test drives the demo page's own script through every control combination (over 10,000) and compares it with the API. The container check now compares 750 quotes, 300 of them for the gap cover. The share within the cap is reported at the unloaded price, because that is what the table holds.

The frozen models are now checked by behaviour, not only by hash.** A pickled scikit-learn model can load under another library version with only a warning and then predict differently. `tests/test_frozen_models.py` scores every frozen model on 300 fixed rows and compares the result with golden predictions written under `requirements.lock`, to 1e-10. CI now installs `requirements.lock`, not the looser `requirements.txt`. Under scikit-learn 1.8.0 the test fails, as it should.

**The December read, confirmed.** On 9 November 2026, still before any of September to December exists, the author confirmed the decision above: v1 and v2 get their December read, once, and v3 and v4 do not.


## Part 6: v5, protection for self-transfer connections

Pre-registered in `PREREGISTRATION_V5_SELF_TRANSFER.md` (commit `48b2dd2`, pushed before any cross-airline pairing existed). Code: `src/mcp/v5.py`, tests: `tests/test_v5.py`.

### 6A. Built and frozen before the holdout is read (9 November 2026)

- **Pairings.** A 5% uniform hash sample of every cross-network pairing at the five hubs with a 90 to 300 minute gap. The full population is about 1.5 million pairings a week, too many to hold, and a uniform sample of an unweighted population estimates the same quantities. Development months, January 2024 to December 2025: 9,265,229 sampled, 9,121,925 usable after excluding cancelled outbound flights, missing times and markets with no DB1B fare (1,785). Monthly miss rates at T = 90 ran from 4.7% (October 2024) to 10.8% (January 2024). The January to August 2026 holdout was built with counts only: 3,242,771 usable pairings in eight months before markets without a fare are dropped, and no outcome printed.
- **Source files.** The 32 Marketing Carrier zips, downloaded again from BTS for this part, hash identically to the ones recorded in `data/manifest.json` for v3, so v5 and v3 read the same flights.
- **Fares.** 10,799 nonstop markets from DB1B 2024 Q1 to 2025 Q2, passenger-weighted, with the same placeholder rule as `mcp.ingest` (no bulk fares, $20 to $5,000). Median market fare $227.
- **Selection of k** (July to December 2025, table fitted on January 2024 to June 2025): log loss 0.25014 (k = 0), 0.24985 (50), 0.24983 (200), 0.24999 (1000). k = 1000 is within the 0.0002 tie band of the best and ties go to the larger k, so **k = 1000**. On the selection months the table fitted on earlier months ran at 1.14 times its expected payout: the level moved up in the second half of 2025, as it did for v3.
- **Frozen table** (`models/v5_table.json`, January 2024 to December 2025, 2,005 cells): SHA-256 `154b580d86094700a8307520334f0d948bf3c4e84c940b31d4787380bf7519d1`.

### 6B. The holdout, read once (9 November 2026, January to August 2026, 3,228,037 pairings)

Run once with the frozen table (hash above), `results/v5_holdout.json`. Nothing was changed after the read.

| # | Expectation | Result | Verdict |
| --- | --- | --- | --- |
| S1 | Realized ÷ target 0.85 to 1.15 | **1.159** [1.05, 1.28] | **Failed** |
| S2 | Cancellations and diversions 20% to 50% of misses | 25.0% | Passed |
| S3 | 90 to 104 minute miss rate above 165 to 179 at every hub | 23.6% to 27.2% against 5.0% to 8.1% | Passed |
| S4 | Monthly standard deviation 0.08 to 0.35 | 0.17 (0.94 to 1.36 by month) | Passed |
| S5 | Offered within the 10% cap runs worse than all | 1.175 against 1.159 | Passed |

**The headline failed.** Priced from 2024 and 2025, the cover would have paid out 16% more than expected in 2026: a 75% loss ratio against the 65% target. By the pre-registration's own rule the price is not right on average, and the cover is not priced as it stands. The failure was foreseeable in kind. On the development selection window a table fitted on earlier months already ran at 1.14, so the level was rising, and a table frozen on 2024 to 2025 carried an average of a lower level into 2026. That is the same drift v3 showed (5I).

**Where it is wrong.** By hub: ATL 1.20, ORD 1.24, CLT 1.11, DEN 1.08, DFW 0.95. By month: 1.23, 0.97, 1.36, 1.00, 0.94, 1.15, 1.30, 1.33. By gap the error grows with time: 1.07 at 90 to 104 minutes, 1.21 at 135 to 149, about 1.30 beyond four hours. Long gaps are missed mostly through cancellations, so the cancellation level is what moved most.

**Sensitivities (pre-registered, not used to choose).** A 60-minute self-transfer minimum: 1.23 (miss rate 5.7%). A 120-minute one: 1.05 (17%). The definition of a miss matters as much as the model. A payout of 1.5 or 2 times the mean fare: 1.15 and 1.15, because the ratio is a calibration ratio. A mix that favours short gaps: 1.12. Offered within a 5%, 10% or 15% cap: 56%, 79% and 88% of pairings, at 1.19, 1.18 and 1.16.

**What the cover would cost** (development months, July to December 2025, so the holdout is read once): median price $85 at 90 to 104 minutes (19% of the two-ticket fare), $34 at 120 to 134, $19 over all gaps, against a median payout of $226. The 10% cap cuts off the shortest self-transfers, from 76% (ORD) to 83% (CLT) of pairings offered.

**What would fix S1, and why it is not done here.** A recalibrated level (a rolling level shift, as v2 used) is the obvious repair, but choosing it on these months would grade its own homework. It needs a new pre-registration and data after August 2026.

### 6C. v5.1: refitted on published months, with a level rule chosen in advance (10 November 2026, before September to November exists)

Pre-registered in `PREREGISTRATION_V5_1_LEVEL.md` (commit `46055a6`, pushed before the selection ran, while every BTS file for September to November 2026 returned not found). Code: `src/mcp/v5_1.py`, tests: `tests/test_v5_1.py`.

**Selection** (walk-forward over July 2025 to August 2026, each month priced by a table fitted on months up to m − 5 and each candidate's level, `results/v5_1_selection.json`):

| Candidate | Pooled log loss | Realized ÷ target (reported, not used) |
| --- | --- | --- |
| `none` | 0.25804 | 1.159 |
| `last12` | 0.25800 | 1.137 |
| `last6` | 0.25815 | 1.122 |
| `season` | 0.25800 | 1.155 |
| `last12_by_gap` | 0.25807 | 1.137 |

`season` has the lowest log loss, but `none` is within the 0.0002 tie band (0.00004 behind) and ties go to the simpler candidate, so the rule chose **`none`**: refit on every published month, no level factor.

**What the selection already says, before the test.** No candidate fixes the under-pricing on the development months: all of them pay out 1.12 to 1.16 times what they charge. With a five-month publication lag a level learned from the past is always behind a level that keeps rising, and refitting on more recent months closes little of the gap. Expectation R1 is therefore likely to fail. It stays as written. If it fails, the next repair is a loading on the price, as v4 did for the gap cover, which this document does not test.

**Frozen prices** (`models/v5_1_prices.json`, three monthly tables fitted through April, May and June 2026, level 1): SHA-256 `ac3b9e0ca54454821e972233fe1d8f511160c5a90c82b08fff69dde6201dac19`.

### 6D. v5.2: a fixed loading of 1.16, frozen for December 2026 to February 2027 (10 November 2026)

Pre-registered in `PREREGISTRATION_V5_2_LOADING.md` (commit `6444e22`, pushed while no BTS month after August 2026 existed). Code: `src/mcp/v5_2.py`, tests: `tests/test_v5_2.py`.

- **Why a loading.** On v5.1's walk-forward (July 2025 to August 2026) claims ran 1.159 times the expected payout, and no level correction removed it (6C). A loading re-estimated each month from earlier walk-forward months only brought February to August 2026 from 1.154 to 1.005, out of sample. That is development evidence, not a test.
- **Frozen:** v5's cell table refitted on January 2024 to August 2026 (k = 1000) and λ = 1.16, in `models/v5_2_prices.json`, SHA-256 `56180af9135ae112c9ab97a7d78bf8e6d0c63ea59f0dbeb4943321895ace697b`.
- **The read:** December 2026 to February 2027, once, when February 2027 is published in both BTS files (probably early May 2027). Expectations W1 to W5 are on the scoreboard. Winter is the hard season: last December ran 1.34 unloaded on the same walk-forward.

**Tags for v5 to v5.2.** The session that wrote these pre-registrations could push branches but not tags. `.github/workflows/preregistration-tags.yml` creates `prereg-v5-self-transfer`, `prereg-v5-1-level` and `prereg-v5-2-loading` with the repository's token, each at the commit that added its document (`48b2dd2`, `46055a6`, `6444e22`), and only after checking that the commit adds that file. The tags are created after the fact. What dates each document is the push of its commit to GitHub, before the data existed, which the branch's push history records.


## Part 7: Season 2

Written from 12 November 2026. The plan is `docs/season2-plan.md`. Earlier parts are not edited. Nothing in this part reads, builds or scores any BTS month from September 2026 on, and nothing here changes a frozen file or a pre-registered test.

### 7A. A model of the claims level, and what 26 months can say about it (development data, July 2024 to August 2026)

Code: `src/mcp/level.py` and `src/mcp/risk.py`. Tests: `tests/test_level.py` and `tests/test_risk.py`. Results: `results/level_dev.json`.

**The idea.** Every repair so far (a recalibration, a level shift, the loading of 1.16) treated the ratio of realized to expected claims as a constant to be estimated late. Here the monthly log ratio is a series with a level that may move, and each candidate forecasts a month from the months that would be known when it is priced, which is every month up to two months earlier for the gap cover (`lag` 2) and five for self-transfers (`lag` 5, as v5.1). Each forecast is a normal distribution for the log ratio, so it can be scored as a distribution and its intervals can be checked. The candidates were fixed before the run and none was added or dropped after it:

| Candidate | What it does |
| --- | --- |
| `none` | Level 1. What v3 and v5.1 use. Its spread is the mean squared log ratio of the known months |
| `last12` | The mean of the last 12 known months |
| `cred` | Buhlmann-Straub credibility across the five hubs: each hub's recent mean shrunk toward the all-hub recent mean |
| `local` | A local-level state-space model (random walk plus noise), Kalman filter, forecast `lag` months ahead, one variance ratio chosen by maximum likelihood on known months only |
| `local_season` | `local` plus a month-of-year effect shrunk toward zero, used only once 48 months are known and otherwise equal to `local` |

**One departure from the plan, recorded here.** The plan describes `cred` as a shrinkage of the recent mean toward a hub's own long-run mean. With 26 months that needs variance components that cannot be estimated, so `cred` shrinks toward the all-hub mean instead, which is the classical Buhlmann-Straub form and needs only the five hubs. The time-series version of the idea is the `local` model.

**The run.** The 26 out-of-sample months of the gap cover from `results/v3_rolling_weeks.csv`, at the weekly file's own monthly sums, as all overnight-risk connections and as sold within the 5% cap. A forecast needs six known months, so 19 months are forecast (February 2025 to August 2026), 95 hub-months in the panel. CRPS is in log-ratio units, lower is better. Coverage is the share of months inside the 90% interval. "Repriced" is the pooled realized/expected ratio had the expected claims been multiplied by the forecast level, over the same months, where 1 is on target.

| View and series | Candidate | CRPS | Coverage | Unadjusted | Repriced |
| --- | --- | --- | --- | --- | --- |
| All, pooled | `none` | 0.125 | 0.89 | 1.089 | 1.058 |
| All, pooled | `last12` | 0.145 | 0.89 | 1.089 | 1.047 |
| All, pooled | `local` | 0.143 | 0.89 | 1.089 | 0.999 |
| All, hub panel | `none` | 0.160 | 0.91 | 1.089 | 1.041 |
| All, hub panel | `last12` | 0.174 | 0.87 | 1.089 | 1.040 |
| All, hub panel | `cred` | 0.172 | 0.88 | 1.089 | 1.045 |
| All, hub panel | `local` | 0.193 | 0.92 | 1.089 | 0.976 |
| Sold, pooled | `none` | 0.212 | 1.00 | 1.200 | 1.107 |
| Sold, pooled | `last12` | 0.223 | 1.00 | 1.200 | 1.035 |
| Sold, pooled | `local` | 0.277 | 0.89 | 1.200 | 0.909 |
| Sold, hub panel | `none` | 0.273 | 0.92 | 1.200 | 1.039 |
| Sold, hub panel | `last12` | 0.299 | 0.86 | 1.200 | 1.019 |
| Sold, hub panel | `cred` | 0.284 | 0.92 | 1.200 | 1.050 |
| Sold, hub panel | `local` | 0.367 | 0.89 | 1.200 | 0.825 |

`local_season` equals `local` in every month and is not listed again, because no month has 48 known months.

**What it says.**

- **No candidate beats `none` on CRPS, in any of the four views.** The monthly ratio has a standard deviation of 0.24 around its level, which is larger than the movement of the level that a model could learn from 19 forecast months. A model that follows the level also follows the noise, and pays for it: `local` is closest to 1 on the repriced ratio (0.999 pooled, all connections) and still scores worse than `none` on CRPS (0.143 against 0.125). Being closer to 1 on one pooled number is not evidence of a better forecast.
- **The hubs are not distinguishable from one another beyond noise.** The credibility factor averaged 0.21 for all connections and 0.02 as sold. At 0.02 each hub is pooled almost entirely with the other four, so `cred` becomes the all-hub mean, which is why it sits next to `last12`.
- **The intervals are about right.** Coverage runs from 0.86 to 1.00 against a nominal 0.90 over 19 or 95 forecasts, which is inside what that many forecasts allow. A pooled interval that never misses (1.00 as sold for `none` and `last12`) is a sign the intervals are wide, not that they are good.
- **The repriced ratio for `none` is not 1.0 because the forecast carries its variance.** The forecast level is the mean of a lognormal, so a noisy series loads the price by about half its variance even when the log level is 0.

**What this does not show.** Nineteen forecast months cannot separate a moving level from noise, and cannot run the seasonal candidate at all. That is the reason for WP3, which adds six years the project has never loaded. The result here is a baseline to beat and not a verdict on any candidate. It also says what the backcast must show to justify season 2's central claim: that following the level beats not following it, on months this analysis has not seen.

**Not done in this section, and why.**

- *The self-transfer series.* The committed results hold the pooled walk-forward ratio for v5.1 (1.159) and the eight spent months of v5's holdout, but no monthly series for the fourteen development months. It needs the pairings and is graded as expectation B8 of the backcast. The code already takes `lag` 5.
- *The sample check.* The plan asks that a 20% uniform hash sample of pairings reproduce the published pooled ratios (1.04 all, 1.15 as sold) within 0.02. The stored rows are a 10% sample, so the check needs a new build from the BTS files and belongs at the start of WP3, before any 2018 to 2023 month is read.

**Reproducing.**

```bash
cd src && python -m mcp.level dev     # about a second, reads results/v3_rolling_weeks.csv, writes results/level_dev.json
```


### 7F. What a late buyer can know: forecasts as issued and a stop-selling rule (read once, 12 November 2026)

Pre-registered in `PREREGISTRATION_V6_FORECAST.md` (tag `prereg-v6-forecast`) before any forecast was joined to a connection. Code: `src/mcp/forecast.py`, tests: `tests/test_forecast.py`, result: `results/forecast.json`. The booking-time model and a forecast model for each lead were fitted on February 2024 to August 2025 and scored once on September 2025 to August 2026 (12 months, a 10% hash sample of overnight-risk connections, the gap label). The forecasts are the Open-Meteo Previous Runs values, hourly at each hub, as the forecast issued 1, 2, 3, 5 and 7 days earlier said them. A dry run on months of the fit window (not the test window) found one thing before the read: snowfall and weather code at lead 7 exist in the archive only from 12 December 2024, so earlier values are missing values, which the gradient-boosting model reads as such.

| Lead (days) | Gain in log loss over the booking-time price | 95% interval (months resampled) | Spread of log(p forecast ÷ p booking) | Net of the noise floor | Exposure at θ = 1 |
| --- | --- | --- | --- | --- | --- |
| 1 | 1.05% | 0.62% to 1.57% | 0.302 | 0.259 | 1.10 |
| 2 | 1.59% | 1.25% to 1.91% | 0.357 | 0.321 | 1.14 |
| 3 | 1.13% | 0.71% to 1.55% | 0.373 | 0.338 | 1.15 |
| 5 | 0.56% | 0.20% to 0.93% | 0.310 | 0.267 | 1.10 |
| 7 | 0.06% | −0.39% to 0.54% | 0.279 | 0.231 | 1.08 |

The noise floor is the spread between two fits of the same booking-time information with different seeds, 0.156 (reported next to the pre-registered measure, which does not remove it). The exposure column is exp(θκ²) with the spread as measured, not net.

**Gate and expectations.** The gain is at least 1% at leads 1, 2 and 3, so the gate passes and the rule was evaluated. **F1 passed**: the gain at lead 1 (1.05%) is larger than at lead 7 (0.06%), and the gain at lead 7 is under 1%. It is not monotone: lead 2 is better than lead 1. **F2 passed, by one week**: at s = 20% and θ = 1 the number of weeks above a 100% loss ratio as sold is 14 with the rule and 15 without, out of 53.

**The sales rule (stop selling where the forecast-informed risk at lead 3 is more than 1.5 times the priced risk).** Sold loss ratio, with and without the rule, by the share s of buyers who book within three days and the strength θ with which they pick connections by the forecast. The target is 65%.

| s, θ | Without the rule | With the rule | Share of sales lost | Weeks above 100% (of 53), without and with |
| --- | --- | --- | --- | --- |
| 10%, 0 | 72.7% | 71.7% | 1.2% | 13 and 13 |
| 10%, 1 | 76.4% | 72.2% | 2.8% | 14 and 14 |
| 20%, 0 | 72.7% | 70.8% | 2.4% | 13 and 13 |
| 20%, 1 | 80.1% | 71.7% | 5.6% | 15 and 14 |
| 30%, 0 | 72.7% | 69.9% | 3.7% | 13 and 12 |
| 30%, 1 | 83.8% | 71.2% | 8.5% | 16 and 14 |

**What it says.**

- **A forecast helps a little, and mostly one to three days out.** The gain is about one percent of the log loss, which is the same order as everything else this project could add at booking time (`VALIDATION.md` Part 4). It fades to nothing at a week. An archive built by a vendor is not proof that a traveller saw the same numbers, and this one is the vendor's, not a government source.
- **The exposure it opens is real and modest.** A buyer who picks by the forecast with θ = 1 and books late raises the sold loss ratio from 72.7% to 76% to 84%, depending on how many buy late. Those are the figures the hidden-information simulation of 4C only gave as a formula. They rest on an assumed share of late buyers, which public data cannot give.
- **The rule recovers the average and does very little for the bad weeks.** It brings the loss ratio back to about 71% to 72% where late buyers select. The count of weeks above 100% moves by zero to two weeks. Weather moves whole weeks and the rule removes only the connections whose forecast was clearly worse than the price. F2 was passed by a single week and should not be read as more than that.
- **The rule costs sales.** Between 1% and 9% of sold weight, rising with the late share and the selection.

**What this does not show.** How travellers really choose, how many book late, whether a rule like this is practical to run (it needs a forecast feed and a decision per connection), and anything about demand. The grid is a range, not an estimate.


### 7E. Did airlines change how they code delays? The coding audit (read once, 12 November 2026)

Pre-registered in `PREREGISTRATION_V6_CODING.md` (tag `prereg-v6-coding`) before any cause code from before 2024 was loaded. Code: `src/mcp/coding_audit.py`, tests: `tests/test_coding_audit.py`, result: `results/coding_audit.json`. Outcomes are shares of carrier-coded events by airline and month at the five hubs, January 2018 to August 2026, outside the pandemic months. Y1 is the share of cancellations coded to the carrier among those coded carrier, weather or national air system. Y2 is the share of the delay minutes of flights that arrived three hours or more late that BTS codes to carrier delay. The model is a weighted regression on airline effects, month-of-year effects, the share of the airline's flights in the denominator that were at the hub under adverse weather (ASOS), the share under an FAA ground stop or ground delay program (`mcp.faa`, which passed its parse gate), and a post-break indicator for 1 September 2022. Intervals resample calendar quarters (2,000 draws).

The committing airlines with enough volume at these hubs are American, Delta, United and Southwest (Alaska, JetBlue, Allegiant and Hawaiian fly too few cancelled or late flights there). The comparison, Frontier, is one airline. The placebo has three (American, Delta, United), because Southwest has too little volume in 2018 to 2019. Effects are in percentage points of the carrier-coded share. A negative effect is a fall.

| Estimate | Outcome | Effect | 95% interval | Airline-months |
| --- | --- | --- | --- | --- |
| Placebo, break 1 September 2019 | Y1 | +3.4 | −4.8 to +10.5 | 62 |
| Placebo, break 1 September 2019 | Y2 | +2.7 | +0.7 to +4.7 | 78 |
| Break 1 September 2022 | Y1 | −7.9 | −13.5 to −3.0 | 261 |
| Break 1 September 2022 | Y2 | −2.6 | −4.4 to −0.8 | 285 |
| Break 1 June 2022 | Y1 | −7.3 | −13.1 to −2.4 | 261 |
| Break 1 June 2022 | Y2 | −1.8 | −3.6 to +0.2 | 285 |
| Break 1 January 2023 | Y1 | −7.9 | −13.1 to −2.7 | 261 |
| Break 1 January 2023 | Y2 | −3.1 | −4.8 to −1.2 | 285 |
| Committing airlines against Frontier | Y1 | −23.1 | −28.6 to −17.6 | 281 |
| Committing airlines against Frontier | Y2 | −14.2 | −16.2 to −12.2 | 304 |

By airline, break 1 September 2022, Y1 and Y2: American −14.9 and −5.0, Delta +4.5 and +5.9, United +0.4 and −3.8, Southwest −11.4 and −4.8.

**C1 failed, so C2 is not graded.** The pre-registered placebo rule is that a break on 1 September 2019, three years before the dashboard, must show a change within ±3 points for both outcomes. It showed +3.4 for Y1 and +2.7 for Y2. Y1 is outside the band, and the rule says the design then finds changes that are not there, and that nothing below is read as an effect. C2 (no fall of 3 points or more) stays pending on the scoreboard. A strict reading of the placebo interval says otherwise for Y1 (−4.8 to +10.5 includes zero), but the rule was written on the point estimate and is applied as written.

**What can and cannot be said.**

- **The data do not show that airlines moved their coding, and they do not show that they did not.** The post-break estimates are negative, and their intervals exclude zero in five of the six rows for the three break dates. The Y1 estimates (7 to 8 points) are well above the 3-point materiality threshold, and the Y2 estimates (2 to 3 points) sit around it. But the same design returns a placebo of the same sign and of comparable size, Y2's placebo interval excludes zero, and the three airlines' own estimates disagree (American and Southwest fall, Delta rises, United is flat on Y1).
- **The comparison with Frontier is not usable.** Frontier's carrier-coded share moved the other way by a large amount, so the difference is −23 and −14 points. With one comparison airline, and one that is not like the others in network, this says more about Frontier than about the committing airlines.
- **The conversion the pre-registration fixed**, for reference and not as a finding: a fall of 3 points in the carrier-coded share raises gap-cover claims by 4.1%. The point estimates of the primary break would correspond to 11.0% (Y1) and 3.6% (Y2), under the strict reading of who is in the gap.
- **What it means for the cover.** The risk the README names, that airlines code toward weather once a carrier code costs them a hotel, is neither confirmed nor ruled out. A launched cover would still need its own check of the coding against a second source, which the trigger of 7D is a first step toward.

**Limits.** Four airlines at five hubs, 261 to 304 airline-months. The weather covariate is each flight's own hub hour, not the pre-registered "flight-hours" taken literally. Whether a given hub hour was stormy is a coarse stand-in for what the airline faced. The FAA programs are the ones the FAA's database lists, and revised programs keep their first end time. BTS coding of late-arriving aircraft, which does not say why an aircraft was late, is outside Y2's carrier share and is not examined.


### 7B. The backcast: the pricing procedures on January 2019 to December 2023 (read once, 12 November 2026)

Pre-registered in `PREREGISTRATION_V6_BACKCAST.md` and its addendum (tags `prereg-v6-backcast`, `prereg-v6-backcast-addendum`) before any 2018 to 2023 outcome existed. Code: `src/mcp/backcast.py` and `src/mcp/backcast_st.py`, tests: `tests/test_backcast.py`, results: `results/backcast.json`, `results/backcast_weeks_A.csv` and `results/backcast_weeks_B.csv`. Nothing was changed after the read. Sixty months were scored, 16 pandemic months (March 2020 to June 2021) are reported separately, so every figure below is over **44 months**. The gap cover is v3's procedure refitted at 20 quarterly origins, each month priced by a model that had not seen it. Arm A fits on everything from January 2018, arm B on the trailing 24 months. The sample is 20%, fixed by the sample check (`results/sample_check.json`: 1.047 against 1.045 published, and 1.138 against 1.151 as sold, both within 0.02).

**Two departures from the pre-registered order, recorded here.** The 2018 to 2023 on-time ingest (counts only) had begun before the sample check finished, which section 7 of the pre-registration did not allow. The check passed at the first fraction, so nothing depended on it. And B6 and B7 were amended before any outcome existed by the addendum, because the 44 observed months can never reach the 48 that `local_season` needed.

| # | Expectation | Result | Verdict |
| --- | --- | --- | --- |
| B1 | Gap cover within 1 ± 0.173 of expected claims | **0.964** | Passed |
| B2 | Monthly spread of the ratio 0.19 to 0.33 | **0.245** | Passed |
| B3 | As sold within the cap runs worse than all connections | 0.932 as sold, 0.964 all | **Failed** |
| B4 | 9% to 44% of months above a 100% loss ratio as sold | 2.3% (1 of 44 months) | **Failed** |
| B5 | The refitted loading lowers the sold loss ratio by at least 3.0 points | 2.9 points (55.7% to 52.9%) | **Failed** |
| B6 | `local` has lower CRPS than `none` and `last12` | 0.199, against 0.156 and 0.170 | **Failed** |
| B7 | The 90% intervals of `local` cover within the binomial range | 30 of 37 months, range 29 to 36 | Passed |
| B8 | The loading brings the self-transfer ratio closer to 1 | loaded 0.912, unloaded 0.981 | **Failed** |
| B9 | Arm A against arm B, no prediction | see below | Reported |
| B10 | Largest earlier change in the 12-month level, no prediction | see below | Reported |

**What held.** The pricing procedure priced the earlier years on target: **0.964** against a band of 0.83 to 1.17 (a realized loss ratio of 62.7% against 65%), and the month-to-month spread, 0.245, is what 26 months had said, 0.241. The procedure was designed on 2024 to 2026 and is not contradicted by 2019 to 2023.

**What did not, and what it changes.**

- **The sold cover was not worse than the average cover.** Within the 5% cap the ratio was 0.932, below the 0.964 of all connections, and the sold loss ratio over the 37 months that have a loading was 55.7%. Only **1 of 44 months** ran above a 100% loss ratio as sold, against 6 of 26 in 2024 to 2026. The finding of the audit, that the cover as sold lost money in bad months and the cap selected connections the model under-prices, **did not appear in these five years**. 23 of 192 weeks were above 100% as sold, worst week 197%.
- **The loading was not needed, and it did little.** The refitted loading (mean 1.08, from 1.00 to 1.42) lowered the sold loss ratio by 2.9 points, 0.1 short of the line, in years when the sold cover already ran under target.
- **Following the level did not pay.** `local` scored worse than a constant level (CRPS 0.199 against 0.156) and worse than the last 12 months (0.170). This is the same answer as the 26 development months (7A), now on 37 months it had not seen. By the rule fixed in the pre-registration, **v6 uses no level model**. `local_season` was never active, as the addendum said it would not be. The intervals of `local` do cover (30 of 37 months).
- **The loading hurt the self-transfer cover.** The table priced 2019 to 2023 within 2% on average (0.981 over the 37 months compared, 1.024 over all 44), and adding a loading re-estimated from earlier months moved it to 0.912. The mechanism of the 2026 failure of v5 (a level that kept rising) was not present in these years.

**B9, arm A against arm B (no prediction).** Arm B, which sees only the last 24 months, ran 1.012 on all connections and **1.088 as sold**, a sold loss ratio of 67.6% (58.9% loaded), and 43 of 192 weeks above 100%. Arm A ran 0.964, 0.932, 55.7% and 23 of 192. The longer the model's history, the better the cover did as sold.

**B10, was 2024 to 2026 unusual (no prediction).** The log of the 12-month level (claims over expected, all overnight-risk connections) ranged from −0.099 to +0.036 across the 22 windows in which all 12 months were observed, and the largest change between two windows 12 months apart was +0.121 (window ending October 2023 against October 2022). The development years offer only three comparable windows and a change of −0.061. The pre-registration asked for windows 24 months apart, and no two valid windows are that far apart once the pandemic is removed.

**By hub and year (arm A), realized over expected.**

| Hub | 2019 | 2020 (Jan, Feb) | 2021 (Jul to Dec) | 2022 | 2023 |
| --- | --- | --- | --- | --- | --- |
| ATL | 0.91 | 0.82 | 0.77 | 0.95 | 1.00 |
| CLT | 1.03 | 1.00 | 0.76 | 1.08 | 1.09 |
| DEN | 1.08 | 0.71 | 0.92 | 0.92 | 1.04 |
| DFW | 1.05 | 0.86 | 0.84 | 0.97 | 0.94 |
| ORD | 1.05 | 0.71 | 0.84 | 0.88 | 0.85 |

**The pandemic months, separately.** Over the 16 months the pooled ratio was 1.043, and single months ran from 0.37 to 5.14 (April 2020, when a handful of connections carried the claims). They are in no headline.

**Exploratory, after the read, and not pre-registered: the winner's curse and the length of history.** Arm A's ratio as sold, divided by its ratio on all connections, by year: 1.09 (2019, the first model had 12 to 24 months), 1.03, 0.84, 0.98, 0.87 (2023, five years of history). Arm B, with 24 months throughout: 1.10, 1.05, 0.98, 1.18, 0.98. The cap selected connections the model under-rated when the model had little history, and stopped doing so as the history grew. That fits how 2024 to 2026 looked (a model with 6 to 30 months of history) and would make the 75% loss ratio as sold a property of a young model, and not of the cover. Five years do not prove it, and it is one reading among others.

**What this does and does not show.** It shows that the pricing procedure travels to earlier years on average and in its monthly spread, that the loading and the level models should not be built on the strength of 2024 to 2026 alone, and that the "sold loses money" finding was period or model-age specific. It does not show that 2024 to 2026 is the unusual period. The pandemic years, a different airline mix (Virgin America had just merged into Alaska) and no published hotel commitments before September 2022 all limit what 2019 to 2023 says about the cover as it would be sold today.


### 7C. What the margin has to carry: the technical price on eight years of weeks (development evidence)

Code: `src/mcp/capital.py` and `src/mcp/risk.py`, tests: `tests/test_capital.py` and `tests/test_risk.py`, results: `results/risk_v6.json` and the weekly record `results/risk_weeks_2019_2026.csv`. The record joins the 192 weeks of the backcast (2019 to 2023, outside the pandemic, 7B) to the 114 development weeks (July 2024 to August 2026), **306 weeks**, from two different fit windows. January to June 2024 and the pandemic months are missing. It is development evidence, and eight years cannot give a 1-in-100 year. The annual figures come from a season block bootstrap of the weeks (runs of four neighbouring weeks drawn quarter by quarter), which keeps the week-to-week weather but **cannot** carry a level that persists from one year to the next, so the annual tail is probably understated.

**The record at the existing price** (expected claims over the 65% target).

| | All overnight-risk connections | Sold within the 5% cap |
| --- | --- | --- |
| Pooled loss ratio | 64.7% | 65.8% |
| Weeks above a 100% loss ratio | 16 of 306 | 51 of 306 |
| Worst week | 127% | 248% |
| Annual loss ratio, mean, 90th and 95th percentile | 65.0%, 69.0%, 70.2% | 66.0%, 73.8%, 76.1% |
| Cost of a weekly stop-loss per unit of premium at 90%, 100%, 120% attachment | 1.5%, 0.6%, 0.0% | 7.3%, 5.1%, 2.8% |
| Standard deviation of the five-hub weekly ratio against the average single hub | 0.73 | 0.67 |

**The technical price.** Premium that equals expected claims realized on this record, plus the cost of a weekly stop-loss at the attachment, plus a cost of capital (10%) on the tail value at risk of the annual loss ratio beyond its mean, divided by one minus an expense ratio. It is stated as a multiple of the existing price (expected claims over 65%). The existing price pays a 35% share that must cover expenses, commissions and any margin, so 35% is the expense ratio at which a multiple of 1 is expected.

| Expense ratio | All connections | Sold within the cap | Sold, weekly stop-loss at 100% |
| --- | --- | --- | --- |
| 10% | 0.73 | 0.75 | 0.74 |
| 25% | 0.87 | 0.89 | 0.89 |
| 35% | 1.00 | 1.03 | 1.03 |

**What it says.**

- **On this record the existing price is about right, and the 1.16 loading is not a requirement.** At a 35% expense share the price needed is 1.00 to 1.03 times the existing one, and below that at lower expense shares. The 1.16 loading answers 2024 to 2026 alone (a sold ratio of 1.15), and the earlier years ran under target (0.93). Over all eight years the record averages out to about on target.
- **The margin for the weather is small in the annual sense, and the weeks are not.** The capital term is 0.3% to 2.5% of premium across costs of capital of 6% to 15%, because the bootstrap's annual loss ratio stays within 66% to 76% in 19 of 20 years. The weeks are another matter: 51 of 306 weeks as sold (17%) ran above a 100% loss ratio, the worst at 248%. A cover that cannot absorb a bad week needs a weekly stop-loss, which costs 5.1% of premium at a 100% attachment as sold, or reserves that do. The capital term does not price that.
- **More hubs would buy some safety.** The five-hub weekly ratio varies 0.67 to 0.73 as much as the average single hub (mean correlation between hubs 0.32 as sold, 0.42 for all connections), so volume at one hub is riskier per dollar than the same volume spread over five. The roadmap's "more hubs" is worth something, not much: hubs share a good part of their weather.
- **The annual tail is probably understated.** The bootstrap treats years as independent draws of quarters. The level persisted across years in 2024 to 2026 (the monthly ratios have a lag-1 correlation of 0.70), and a persistent level is exactly what an annual capital figure should carry.

**Margin per policy.** At the sold book's realized loss ratio of 65.8% and the average premium of $10.01 a policy (`VALIDATION.md` 5J), a 1.00 loading leaves $0.92 a policy after claims at a 25% expense share and **−$0.08** at 35%. A 1.16 loading leaves $2.12 at 25% and $0.96 at 35%. This holds the claims fixed when the price rises, which flatters it (fewer connections would pass the cap).

**What this does not do.** It does not say what the cover costs to run, what a reinsurer would quote, or what a traveller would pay.


### 7D. A trigger that can settle the same night, and how far it sits from the one the cover was priced on (development data and the backcast years)

Code: `src/mcp/trigger.py`, tests: `tests/test_trigger.py`, results: `results/trigger.json`. The two triggers were fixed in the module's docstring before either was scored. **T1** pays when the connection is missed overnight and an FAA ground stop or ground delay program (not a proposal, not one airline's own stop, `mcp.faa`) was in effect at the hub at some moment between three hours before the inbound flight's scheduled arrival and its actual arrival (three hours after the schedule for a cancelled or diverted inbound flight). **T2** is T1 or adverse hub weather in the same window (ASOS thunder, snow, freezing weather, visibility under one mile, wind of 25 knots or a gust of 35). Both pay the hub's GSA night, weighted by the route weight. They are compared with what the cover was priced on: the BTS-coded gap payout, where the inbound delay is not coded to the airline.

| Period | Trigger | Share of the BTS-coded gap payouts it also pays | Share of its payouts that BTS codes to the airline | Its payouts over the gap payouts | Correlation of monthly payouts with the gap's |
| --- | --- | --- | --- | --- | --- |
| 2024 to August 2026 (32 months) | T1 | 29.2% | 11.4% | 0.33 | 0.89 |
| 2024 to August 2026 (32 months) | T2 | 36.5% | 13.6% | 0.42 | 0.95 |
| 2019 to 2023, outside the pandemic (44 months) | T1 | 25.6% | 11.2% | 0.29 | 0.78 |
| 2019 to 2023, outside the pandemic (44 months) | T2 | 34.4% | 14.2% | 0.40 | 0.88 |

The BTS-coded gap is 80.3% of the payouts on missed overnight connections in 2024 to 2026 and 78.3% in 2019 to 2023. The share of all missed-overnight payouts that T1 pays is 26.4% and 22.6%, and T2's is 33.9% and 31.3%.

**What it says.**

- **A trigger of this kind is a narrower cover, not the same one paid earlier.** It pays a quarter to a third of the payouts the BTS-coded cover pays (0.29 to 0.42 of the dollars). Most of the gap, misses after late-arriving aircraft, air-traffic delay with no ground stop and delays at hubs with no flagged weather, would pay nothing. A traveller whose connection was missed for those reasons receives nothing at all, which is the basis risk.
- **It is closely tied to the same months.** Monthly payouts of the trigger and of the BTS-coded cover move together (0.78 to 0.95), so a trigger priced on the model, with a margin that carries the same weather, would carry about the same monthly shape.
- **It pays the airline's own delays much less than the BTS code would.** Only 11% to 14% of what the triggers pay is coded to the airline, against 20% to 22% of missed-overnight payouts overall. An FAA program is an independent record of a system-wide problem, which is exactly what an airline cannot write. That is the useful property for the coding risk of 7E: a same-night trigger cannot be moved by coding.
- **The two periods agree.** The coverage and leakage figures are within a few points between 2019 to 2023 and 2024 to 2026, so the relation did not change with the airlines' commitments in September 2022.

**What stays outside.** A same-night settlement needs the inbound flight's actual arrival that night, which a flight-status feed has and BTS, published two months late, does not. The FAA database keeps a program's first end time when it was revised, so intervals can be too long, and a weather flag at the airport is a coarse stand-in for what stopped a flight. A trigger that pays less is also a different product to price and to sell, and its price and its demand are untested.


### 7G. A calendar pattern in the claims level (exploratory, on the 70 months already seen)

Written after the backcast was read, so **none of this is a test**. Code: `src/mcp/v6.py` (`season_report`), tests: `tests/test_v6.py`, results: `results/v6_season_dev.json`. The monthly ratio of realized to expected claims (all overnight-risk connections) for the 70 observed months of 2019 to 2023 (outside the pandemic) and July 2024 to August 2026, from `results/risk_weeks_2019_2026.csv`, averaged by calendar month. The log ratio is the quantity the level models of 7A and 7B tried to follow over time. By calendar month it is far steadier than over time.

| Month | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Mean log ratio | −0.03 | −0.05 | −0.07 | +0.02 | +0.05 | +0.30 | +0.28 | +0.19 | −0.22 | −0.33 | −0.37 | −0.19 |
| Observed months | 6 | 6 | 5 | 5 | 5 | 5 | 7 | 7 | 6 | 6 | 6 | 6 |

Predicting each year's months from a season fitted on the other six or seven years (leave one year out) gives a mean absolute error of the monthly log ratio of **0.125** with the season (deviations shrunk by n ÷ (n + 1)), against **0.206** with no adjustment (level 1) and 0.210 with a constant level fitted on the other years. The error falls by about 40%, and shrinking harder only makes it worse (0.129 at κ = 2, 0.140 at κ = 4). The residual spread is 0.1585 and its lag-1 autocorrelation 0.423.

**Summer, by year.** Realized over expected on all connections for June to August, and the sold loss ratio at the existing price: 2019 1.36 and 105%, 2022 1.19 and 72%, 2023 1.32 and 85%, 2025 1.42 and 106%, 2026 1.30 and 95%. In every one of the five summers the cover ran above its expected claims by 19% to 42%, and in two of them above a 100% loss ratio as sold.

**What it suggests.**

- **The model's missing month feature costs a third of the claims in summer and gives a third back in autumn.** The cover is under-priced in June to August and over-priced in September to December, and the average over the year hides both. The project had dropped a month term in 2025 because one year of data memorised that year's events (decision log, step 5). With seven years of each month the pattern is no longer one year's events.
- **It explains what the level models could not.** A level that moves over time cannot beat a constant level, but a level that depends on the calendar does. The seasonal candidate of 7A could not run on 26 months and the backcast could not test it on 44, which is why this had to be found on the whole record.
- **It re-reads two earlier findings.** The "calm season" warning of `PREREGISTRATION_2026H2_V4.md` (September to November are the easiest months) is this pattern, and the 2024 to 2026 sold results, which were worst in July and August, were summers.
- **It is a prediction, and the project's way of testing a prediction is the one it already has.** The multipliers are frozen in `models/v6_season.json` and tested forward in `PREREGISTRATION_V6_FORWARD.md` on March to August 2027, with one prediction about the sealed autumn of 2026.

**Limits.** Seven years of a pattern in months that are also the weather of those years. The multipliers are in-sample for the record they were fitted on. A seasonal price raises summer prices by up to 27% and lowers autumn prices, which changes what can be offered within the cap and has no demand evidence behind it. The record joins two different fit windows.


### 7H. Do three features of the timetable earn a place? The schedule-structure test (read once, 13 November 2026)

Pre-registered in `PREREGISTRATION_V6_SCHEDULE.md` (tag `prereg-v6-schedule`) before any of the features was built. Code: `src/mcp/schedule_features.py`, tests: `tests/test_schedule_features.py`, result: `results/schedule_features.json`. The three features are the number of flights scheduled into the inbound flight's quarter-hour at the hub (`hub_arr_15`), the number scheduled out in the onward flight's quarter-hour (`hub_dep_15`), and the inbound flight's scheduled time minus the median time flown by the same network on the same leg in the fit window (`in_block_pad`). Fit on January 2018 to December 2022 without the pandemic months (3,000,654 rows), scored once on 2023 (5,497,858 overnight-risk connections, a 20% sample, the gap label, the v1 feature set plus the three).

| Model | Weighted log loss | Difference from the base |
| --- | --- | --- |
| Base (v1 feature set) | 0.230573 | |
| Base, another random seed | 0.230358 | 0.000215 |
| Base plus `hub_arr_15` alone | 0.230255 | 0.000318 |
| Base plus `hub_dep_15` alone | 0.230521 | 0.000052 |
| Base plus `in_block_pad` alone | 0.230358 | 0.000215 |
| **Base plus all three** | **0.229839** | **0.000734** |

**X1 failed.** The expectation was that the three features add at most 0.0002 to the log loss, the project's tie band. They added **0.00073**, which is 0.32% of the base log loss. By the rule written before the read, the features carry information the model lacks.

**How to read a failure of this size.**

- **It is small.** A third of one percent of the log loss, against 1% to 2% for everything the model already uses over a connection-time table (Part 2). The pooled realized over expected ratio moves from 1.006 to 1.002.
- **It is only about three times the noise between two fits.** Refitting the base model with another seed moves the log loss by 0.000215, which is as much as `in_block_pad` adds alone. So `hub_dep_15` and `in_block_pad` are indistinguishable from fit noise here, and `hub_arr_15` (0.000318) is not far above it.
- **Most of the gain is `hub_arr_15`.** How crowded the hub is when the inbound flight lands carries some risk that connection time and the route's history do not. That is a scheduled field known at booking.
- **The project's prior was a null, and the rule says the null did not hold.** The pre-registration says such a failure sends the features to a later model version under its own pre-registration, and changes nothing already frozen. Nothing frozen changes. The three-month forward test of the seasonal price (`PREREGISTRATION_V6_FORWARD.md`) does not use them.

**Limits.** One year (2023), whose monthly ratios were already seen. Three features out of many possible timetable features. A gain in log loss is not a gain in margin, and the price cap would change which connections are sold. The comparison uses two fits with different features, and the seed difference shows a fit alone moves the score by a fifth of the gain.
