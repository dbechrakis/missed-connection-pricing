# Pre-registration: v5.1, the self-transfer cover with a level that follows recent months, on September to November 2026

Written **10 November 2026**. At 15:55 UTC that day the BTS download addresses for September, October and November 2026 (both the Reporting Carrier and the Marketing Carrier files) all returned "not found". It is a separate document; `PREREGISTRATION_V5_SELF_TRANSFER.md` and every earlier pre-registration are unchanged. The commit that adds it is pushed to GitHub before the selection below is run, and the frozen prices are committed before any of the test window exists. Drafted by Claude for the author.

## 1. What failed, and what this tests

v5 priced self-transfer connections from a table fitted on January 2024 to December 2025. On January to August 2026 it paid out **1.159** times its expected cost [1.05, 1.28], outside its band (`VALIDATION.md` 6B). Two things went wrong. The level rose: the table averaged a lower 2024 into a higher 2026. And the error grew with the gap: 1.07 at 90 to 104 minutes, about 1.30 beyond four hours.

v5.1 keeps everything v5 fixed (population, 90-minute minimum, label, payout, cells, k = 1000, 65% target, 10% cap) and adds two things a real operator would do:

- **Refit the table on every month that would have been published** when the cover is sold.
- **Multiply it by a level factor learned from recent months.** One of five candidates, chosen by a rule fixed here.

## 2. Everything seen before writing this

This is **not blind**. The author has seen every cross-network outcome from January 2024 to August 2026: v5's development months, and v5's holdout, which is now spent and becomes development data here. The candidate set below was written **after** seeing that v5's level rose and that its error grew with the gap. The September to November 2026 window has never existed.

## 3. What is known when a price is set

BTS publishes a month about two months after it ends (November 2026 is expected in early February 2027). A self-transfer is booked up to about a month before travel. So the newest month known when pricing travel month m is **m − 5**. For September 2026 that is April 2026.

## 4. The table

For travel month m: the v5 cell table (hub × inbound network × gap bucket × inbound arrival band, shrunk toward hub × gap bucket with k = 1000), fitted on **January 2024 to m − 5**.

## 5. The level: five candidates, declared now

For travel month m, L(m) multiplies the table's probability (capped below 1). "Ratio over months W" means realized misses ÷ the table's expected misses over the pairings of months W, with the table of section 4. Inside the fit range this is in sample. That is the point: it measures how recent months differ from the average the table learned.

| Candidate | L(m) |
| --- | --- |
| `none` | 1 |
| `last12` | ratio over the 12 months m − 16 to m − 5 |
| `last6` | ratio over the 6 months m − 10 to m − 5 |
| `season` | ratio over the same three calendar months a year earlier, m − 13 to m − 11 |
| `last12_by_gap` | `last12`, computed separately for gaps of 90 to 149 minutes and of 150 to 300 minutes |

## 6. The selection (run after this document is pushed)

Walk forward over the **14 development months July 2025 to August 2026**. Each month is priced by its own section-4 table and each candidate's level, using only months up to m − 5. The rule picks the candidate with the **lowest pooled log loss**. Candidates within 0.0002 of the best are tied, and ties go to the simpler one, in the order of the table above. Realized ÷ target is reported for every candidate, not used.

The chosen candidate's prices for **September, October and November 2026** depend only on months up to June 2026. They are computed, hashed and committed before the window exists, as `models/v5_1_prices.json`.

## 7. The test window

**September to November 2026**, read **once**, when November is published, by `python -m mcp.v5_1 holdout`. The pairings are built with counts only (`python -m mcp.v5 build --t 90 --sealed --start 2026-09 --end 2026-11`). The frozen v5 table is scored on the same pairings as the comparison. December is not part of this test.

**A warning:** September to November is the calmest season in the development data. Cross-network miss rates there were 4.7% to 5.4% in 2024 and 5.5% to 8.6% in 2025, against about 8% to 10% from June to August. A level learned partly from spring and summer months may over-price a calm autumn, and a pass in autumn says little about summer.

## 8. Expectations (falsifiable; each is reported, pass or fail)

| # | Expectation | Why | If it fails |
| --- | --- | --- | --- |
| R1 | **Calibration.** v5.1 pooled realized ÷ target between **0.85 and 1.15** | The band v5 failed | The fix does not price the cover right on average |
| R2 | **Better than v5.** \|v5.1 − 1\| is smaller than \|v5 − 1\| on the same pairings | v5's table is a year staler, and its level is older | Refitting and the level do not help |
| R3 | **Solvency.** No month above **1.54** (a 100% loss ratio) | The margin must absorb a calm month at least | The 65% target is too thin even in autumn |
| R4 | **The claim mix holds.** Cancellations and diversions are **20% to 50%** of misses | 25% in v5's holdout | The product's claim mix moved |
| R5 | **The gap pattern is gone.** Realized ÷ target for gaps of 150 to 300 minutes is within **0.15** of that for 90 to 149 minutes | In v5's holdout the long gaps ran about 0.1 to 0.2 worse | The table's shape, not only its level, needs fixing |

**Not allowed after reading:** changing the table, k, the candidates, the rule, the chosen level, the lag, the population, the label, the payout, the cap, the target, the window, or the metric. A bug may be fixed only with the numbers before and after, in `VALIDATION.md`.
