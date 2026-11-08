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
