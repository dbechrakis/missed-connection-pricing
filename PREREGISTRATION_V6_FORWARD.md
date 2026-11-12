# Pre-registration: v6, the gap cover with a seasonal price, on March to August 2027

Written **12 November 2026**, before any BTS month after August 2026 exists in this project. It is a separate document. No earlier pre-registration is edited. The commit that adds it is pushed to GitHub before any such month is ingested, and a tag marks it (`prereg-v6-forward`). Drafted by Claude for the author.

## 1. Why a seasonal price

The 70 months of claims over expected claims that the project now holds (the 2019 to 2023 backcast outside the pandemic, `VALIDATION.md` 7B, joined to July 2024 to August 2026) carry a calendar pattern the model has never had. The model has no month feature, because one year of data cannot separate a season from one year's events. The mean log ratio by calendar month (5 to 7 observations each) runs from +0.30 in June and +0.28 in July to −0.37 in November. Predicting each year from the other years' month means cuts the mean absolute error of the monthly log ratio from 0.206 to 0.125. That was found **after** the data were seen (`VALIDATION.md` 7G, exploratory), so it is not evidence. This document turns it into a prediction about months that do not exist yet.

## 2. What has and has not been seen

- **Seen:** every month through August 2026 and the pattern above. The multipliers are fitted on all 70 months, so they are in-sample for them.
- **Not seen:** every month from September 2026 on. September to November 2026 are the window of the pre-registered v3 and v4 tests (`PREREGISTRATION_2026H2_V3.md`, `_V4.md`), read by the scheduled job in early 2027 and **not touched here**. This document makes one prediction about them (Q1) and does not read them.

## 3. The price

- **Frozen multipliers:** `models/v6_season.json`, SHA-256 `885c18ba1e071a357c2ea41489970925acec4e0cee59dc3e0696fa701a377b71`. For calendar month m the multiplier is exp(grand mean + n/(n + 1) times the month's mean deviation of the log ratio), fitted on all 70 months. They run from 0.72 in November to 1.27 in June and July.
- **The model and the sample:** exactly arm A of the backcast (`PREREGISTRATION_V6_BACKCAST.md`, `mcp.backcast`): the v3 procedure refitted at quarterly origins on all months from January 2024 through the block start, v1 feature set, no recalibration, a 20% hash sample, the gap label, the GSA payout.
- **The seasonal price:** price = P(miss) × payout ÷ 0.65 × the month's multiplier. The 5% cap is applied to this price. There is **no loading**: the refitted loading did not reach its 3-point line on the backcast (`VALIDATION.md` 7B).
- **What is compared.** The ratio of realized to expected claims is taken against the model's expected claims **without** the multiplier, so the multiplier is a prediction of that ratio.

## 4. Windows

| Window | Months | Read when |
| --- | --- | --- |
| Spring 2027 | March, April, May 2027 | May 2027 is published in the Marketing Carrier file (probably August 2027) |
| **Summer 2027** | **June, July, August 2027** | August 2027 is published (probably November 2027) |

Each is read once, by `python -m mcp.v6 read <window>`, which refuses a second run. Summer is the real test: the multipliers move the price by 18% to 27% there, and spring's multipliers are within 7% of 1. Every pairing of the model's fit and the block follows the backcast: fitted through the block start, which a real booking could not (two months of data lag), a limit stated here.

## 5. Expectations (falsifiable; each is reported, pass or fail)

Per window. `z` is the log of the month's realized over expected claims (all overnight-risk connections).

| # | Expectation | Rule |
| --- | --- | --- |
| G1 | **The seasonal price calibrates.** Pooled realized ÷ (expected × multiplier) over the window | Within 1 ± 0.287 (2σ ÷ √n_eff with σ = 0.1585, the leave-one-year-out residual spread, and n_eff = 3 (1 − ρ) ÷ (1 + ρ) with ρ = 0.423 its lag-1 autocorrelation) |
| G2 | **The season beats a constant level.** The mean absolute error of z against log(multiplier) is below its error against 0 | Strictly below |
| G3 | **No month above a 100% loss ratio as sold.** At the seasonal price | Every month at or below 100% |
| G4 | **Reach.** The share of overnight-risk connections priced within the cap | 20% to 55% in every month (the backcast ran 24.5% to 50.6%) |
| H1 | **The seasonal price calibrates.** Pooled realized ÷ (expected × multiplier) over the window | Within 1 ± 0.287 (2σ ÷ √n_eff with σ = 0.1585, the leave-one-year-out residual spread, and n_eff = 3 (1 − ρ) ÷ (1 + ρ) with ρ = 0.423 its lag-1 autocorrelation) |
| H2 | **The season beats a constant level.** The mean absolute error of z against log(multiplier) is below its error against 0 | Strictly below |
| H3 | **No month above a 100% loss ratio as sold.** At the seasonal price | Every month at or below 100% |
| H4 | **Reach.** The share of overnight-risk connections priced within the cap | 20% to 55% in every month (the backcast ran 24.5% to 50.6%) |

G is the spring window and H the summer window. G2 is nearly uninformative in spring, because its multipliers are close to 1, and is graded as written.

| # | Expectation | Rule |
| --- | --- | --- |
| Q1 | **A prediction about the sealed autumn.** The v3 model's ratio on September to November 2026 | 0.546 to 0.987, graded from `results/holdout_v3_next.json` |

**Q1 in words.** The multipliers for September, October and November average 0.767. The v3 model, unchanged, should therefore run **0.546 to 0.987** (0.767 × (1 ± 0.287)) on September to November 2026, where its pre-registered V1 expects 1 ± 0.23. It is graded from `results/holdout_v3_next.json` when the scheduled job has written it, by `mcp.grade`. It does not change any v3 or v4 expectation.

## 6. Not allowed after reading

Changing the multipliers, the windows, the model, the sample, the cap, the target, the rule of the seasonal price, the bands, or the metric. A bug may be fixed only with the numbers before and after, in `VALIDATION.md` Part 7.

## 7. What this cannot show

That the pattern is a property of the weather and not of eight years. That it survives a change in how connections are booked. Anything about demand. If summer 2027 is unlike the five summers in the record, G1 and H3 will say so.
