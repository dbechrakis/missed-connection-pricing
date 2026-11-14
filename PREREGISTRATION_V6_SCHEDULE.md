# Pre-registration: v6 schedule structure, do three features of the timetable earn a place in the booking-time model?

Written **13 November 2026**, before any of the three features below was built or joined to a connection. It is a separate document. The commit that adds it is pushed to GitHub before the features are built, and a tag marks it (`prereg-v6-schedule`). Drafted by Claude for the author. It is the optional item 2 of `docs/season2-plan.md`, time-boxed to one session.

## 1. The question

The project's oldest finding is that booking-time information is mostly the connection time: a gradient-boosting model beats a hub × connection-time table by 1% to 2% in Brier score (`VALIDATION.md` Part 2). Three things about the timetable are known at booking and have never been tried: how crowded the hub is when the inbound flight is due, how crowded it is when the onward flight leaves, and how much slack the airline has padded into the inbound flight's scheduled time. If any of them carries risk the model lacks, the price is leaving it out. The project's own finding predicts that they add nothing that matters.

## 2. What has and has not been seen

- **Seen:** every outcome from January 2018 to August 2026, in the backcast (`VALIDATION.md` 7B) and before. The test year below, 2023, is not unseen: its monthly ratios were read on 12 November 2026.
- **Not seen:** none of the three features has been computed for any flight, and no model has been fitted with them. As with the forecast test (`PREREGISTRATION_V6_FORECAST.md`), what is new is the join.

## 3. The features (all from scheduled fields)

At a hub H, with the 2018 to 2023 Marketing Carrier flights of the `hist` variant:

- **`hub_arr_15`**: the number of flights of any marketing network scheduled to arrive at H in the same quarter-hour of the hub-local clock as the inbound flight's scheduled arrival.
- **`hub_dep_15`**: the number scheduled to depart H in the same quarter-hour as the onward flight's scheduled departure.
- **`in_block_pad`**: the inbound flight's scheduled elapsed minutes, minus the median **actual** elapsed minutes of flights of the same marketing network on the same origin to H leg **in the fit window**. Missing when that leg has fewer than 20 completed flights in the fit window.

Cancelled flights stay in the counts, because they were scheduled when the ticket was sold. Nothing about the day of travel enters: no actual time, no delay, no cancellation of the flights in question. `in_block_pad` uses actual times of earlier flights only, from the fit window.

## 4. Design

- **Label, population, model:** the gap label on the v3 population of the backcast, the v1 feature set, gradient boosting with the settings of `mcp.backcast` (`LEAVES` 15, at most 3,000,000 fit rows), no calibration.
- **Fit window:** January 2018 to December 2022, **without the pandemic months** (March 2020 to June 2021). **Test window:** January to December 2023, a 20% hash sample, overnight-risk connections, read once.
- **Two models on the same rows:** the v1 feature set, and the v1 feature set plus the three features. A third fit, the v1 feature set with another random seed, gives the difference that two fits of the same information show.
- **Metric:** the pooled weighted log loss of the gap label over the test connections. Gain = base − with features.

## 5. Expectation (falsifiable; reported, pass or fail)

| # | Expectation | Rule | If it fails |
| --- | --- | --- | --- |
| X1 | **The timetable features do not earn a place.** The gain in log loss is at most the project's tie band | Gain ≤ 0.0002 | They add information the model lacks. They would then enter a later model version under its own pre-registration. Nothing already frozen changes |

Reported without prediction: the gain as a percentage of the base log loss, the seed difference, the gain of each feature added alone, and the pooled realized over expected ratio of both models.

## 6. Not allowed after the read

Changing the features, the windows, the model, the sample, the rule or the metric. A bug may be fixed only with the numbers before and after, in `VALIDATION.md` Part 7.

## 7. What this cannot show

That no feature of the timetable matters (three were tried). Anything about a year other than 2023. Whether a gain in log loss would be worth a more complex price.
