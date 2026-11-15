# Pre-registration of the hub-level forward test of the season

Written **15 November 2026**, before any BTS month after August 2026 exists in this project and before any month of the 2027 windows has been ingested, built or scored. It adds a second prediction for the same months as `PREREGISTRATION_V6_FORWARD.md`, at hub level, and changes nothing in that document, in `PREREGISTRATION_V6_FORWARD_ADDENDUM.md`, in `models/v6_season.json` or in any price. The commit that adds this document is pushed to GitHub before any such month is ingested, and a tag marks it (`prereg-v7-hub-season`).

## 1. What was seen

Every month to August 2026, and the result of `VALIDATION.md` 7O: a hierarchical model of the season by hub did **not** earn its place over one calendar for all hubs (lower ranked probability score in 2 of 4 folds, mean gain -0.0001). No month from September 2026 on has been seen.

## 2. What is predicted

For the 30 hub-months of March to August 2027 (five hubs, six months), the log ratio z of realized to expected claims at hub level, under two frozen predictors.

- `pooled`: the multipliers of `models/v6_season.json` (SHA-256 `885c18ba1e071a357c2ea41489970925acec4e0cee59dc3e0696fa701a377b71`), the same for every hub. The predictive standard deviation is the root mean square residual of the hub panel in 7O.
- `hier`: `models/v7_hub_season.json` (SHA-256 `c5bcc13461979c6a8eab499679ad7e23ae60bd2f40fd099d4e85b24ae09e3aa6`), the predictive mean and standard deviation of z for each hub and month.

## 3. The data

The same rows, sample, model and cap as the two v6 windows. Nothing new is ingested. The ratio is computed per hub and month from the rows that the v6 read has already built, for the windows `spring2027` and `summer2027`.

## 4. Expectations

Their direction follows from 7O by a rule fixed before it was run, which is why K1 reads as it does.

- **K1.** The mean absolute errors of `hier` and `pooled` over the 30 hub-months differ by less than 0.02.
- **K2.** The 90% predictive intervals of `hier` cover between 21 and 30 of the 30 hub-months.
- **K3.** No prediction. 7O lists 0 hub-months whose multiplier differs from the shared calendar with posterior probability above 0.9, so there is nothing to predict.
- **K4.** No prediction on whether any hub-level pattern would have changed a price. Reported.

## 5. Order guard

The read of this test runs only after `mcp.v6 read` has written its result for the same window. It never reads a window before v6 has.

## 6. Not allowed after the read

Refitting, changing the predictors, the months, the hubs or the bands. A bug may be fixed only with the numbers before and after, in `VALIDATION.md` Part 7.

## 7. What this cannot show

Thirty hub-months in one spring and summer can contradict the model. They cannot confirm it. Hubs share the same months, so the effective number of independent observations is nearer six. A hub-level price has no demand evidence behind it and is not proposed.
