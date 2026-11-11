# Pre-registration: v5.2, the self-transfer cover with a price loading, on December 2026 to February 2027

Written **10 November 2026**, when no BTS file after August 2026 had been published. It is a separate document; every earlier pre-registration is unchanged. The commit that adds it is pushed to GitHub before the frozen prices are computed, and those are committed before any of the test window exists. Drafted by Claude for the author.

## 1. Why a loading

v5 priced self-transfers 16% too low on January to August 2026 (`VALIDATION.md` 6B). v5.1 tried to follow the level instead: refit on every published month plus a level correction chosen by rule. On 14 development months no correction helped, because claims data arrive about five months after a sale and the level kept rising (`VALIDATION.md` 6C). The remaining repair is the one v4 used for the gap cover: a fixed loading on the price that carries the expected drift.

## 2. Everything seen before writing this

This is **not blind**. The author has seen every cross-network outcome from January 2024 to August 2026 and computed the following on them before writing:

- On v5.1's walk-forward (July 2025 to August 2026, each month priced by a table fitted on months up to m − 5, no level), claims ran **1.159** times the expected payout, pooled.
- A loading re-estimated each month from earlier walk-forward months only (at least three, up to m − 5) brought February to August 2026 from **1.154 to 1.005**, out of sample.
- Last winter on the same walk-forward: December 2025 1.34, January 2026 1.23, February 2026 0.99 unloaded, so 1.16, 1.07 and 0.85 loaded by 1.16.
- At the loaded price the share of pairings within the 10% cap falls from 80% to 76% (mean of the 14 months).

## 3. The price

- **Table:** v5's cell table (population, 90-minute minimum, label, payout, cells, k = 1000 all unchanged), fitted on **January 2024 to August 2026**, every month published when this is written, and used unchanged for all three months.
- **Loading: λ = 1.16**, the pooled walk-forward ratio of section 2 rounded to two decimals, fixed now. Price = λ × P(miss) × payout ÷ 0.65.
- **Offered** within 10% of the two-ticket fare, at the loaded price.

The frozen table and λ go in `models/v5_2_prices.json`, whose hash is committed before the window exists.

## 4. The test window

**December 2026 to February 2027**, read **once**, when February 2027 is published in both BTS files (probably early May 2027). The pairings are built with counts only (`python -m mcp.v5 build --t 90 --sealed --start 2026-12 --end 2027-02`), then `python -m mcp.v5_2 holdout` reads them. The same table without the loading is scored on the same pairings as the comparison.

**A warning:** this is winter, when storms cancel whole days. Last December ran 1.34 times expected. One bad week can decide a three-month read, and a pass says nothing about summer.

## 5. Expectations (falsifiable; each is reported, pass or fail)

| # | Expectation | Why | If it fails |
| --- | --- | --- | --- |
| W1 | **Calibration.** Loaded realized ÷ target between **0.85 and 1.15** | The out-of-sample loading landed at 1.005 on development months | The loading does not price the cover on average in winter |
| W2 | **The loading helps.** \|loaded − 1\| is smaller than \|unloaded − 1\| on the same pairings | The level has stayed above the table's average since mid 2025 | The level fell back, and the loading over-prices |
| W3 | **Solvency.** No month above **1.54** loaded (a 100% loss ratio) | The worst loaded development winter month was 1.16 | The margin cannot carry a winter month |
| W4 | **Reach.** At the loaded price **65% to 85%** of pairings fit the 10% cap, in every month | 76% on average in development | The fares or the mix moved |
| W5 | **The claim mix.** Cancellations and diversions are **20% to 50%** of misses | 25% in v5's holdout, and winter cancels more | The claim mix moved |

**Not allowed after reading:** changing the table, λ, k, the cap, the target, the population, the label, the payout, the window or the metric. A bug may be fixed only with the numbers before and after, in `VALIDATION.md`.
