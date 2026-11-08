# Validation

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
