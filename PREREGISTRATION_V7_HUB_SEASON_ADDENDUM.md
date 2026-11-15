# Addendum 1 to the hub-level forward pre-registration: how the expectations are graded

Written **15 November 2026**, before any BTS month after August 2026 exists in this project and before any month of the 2027 windows has been ingested, built or scored. It amends `PREREGISTRATION_V7_HUB_SEASON.md`, which is not edited. Every expectation, band, window and rule of that document stands. The commit that adds this one is pushed to GitHub before any such month is ingested, and a tag marks it (`prereg-v7-hub-season-addendum`). It follows an independent review of the first document by a second model, which found that the grading rule left six points open. Drafted by Claude for the author, on the author's instruction.

## 1. What is made exact

- **Where the rule of K1 comes from.** K1 says what it says because `VALIDATION.md` 7O, section "The fixed rule", was written before any fit: `hier` earns its place over `pooled` if its ranked probability score is lower in at least all folds but one and the mean gain is above 0.005. 7O found that it did not, and the document follows from that.
- **Covered.** A hub-month is covered when the realized z is within 1.6449 predictive standard deviations of the predictive mean of `hier`, both taken from `models/v7_hub_season.json`, with the edge counted as covered.
- **The spread of `pooled`.** It is the root mean square residual of the pooled rule on all 350 hub-months of `results/risk_weeks_2019_2026.csv`, and its mean is the log of the multiplier of `models/v6_season.json`. No expectation uses it. It is reported only.
- **A hub-month that cannot be scored.** A hub-month with no claims or no expected claims has no finite z. It is left out of K1 and K2 and listed in the result file. K1 is the difference of the mean absolute errors over the hub-months that remain. K2 is passed when the share covered is between 21 over 30 and 1. If fewer than 24 of the 30 hub-months can be scored, K1 and K2 are not graded and the result file says why.
- **One read per window.** Each window is read once, as for `PREREGISTRATION_V6_FORWARD.md`. `mcp.hub_season read` refuses a second run for a window.
- **Order guard.** The read refuses to run until `mcp.v6 read` has written its result for the same window, and until the scheduled reads of v3, v4 and v5.2 have written theirs, as `mcp.v6` does.

## 2. What is not changed

The predictors, their hashes, the months, the hubs, the bands K1 and K2, and the two expectations without a prediction, K3 and K4.

## 3. Not allowed after the read

Changing any rule above, the windows, or the way a hub-month is scored. A bug may be fixed only with the numbers before and after, in `VALIDATION.md` Part 7.
