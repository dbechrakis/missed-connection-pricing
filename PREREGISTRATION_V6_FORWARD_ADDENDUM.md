# Addendum 1 to the v6 forward pre-registration: a loaded series reported next to the seasonal price

Written **14 November 2026**, before any BTS month after August 2026 exists in this project and before any month of the 2027 windows has been ingested, built or scored. It amends `PREREGISTRATION_V6_FORWARD.md`, which is not edited. Every expectation, band, window and rule of that document stands. The commit that adds this one is pushed to GitHub before any such month is ingested, and a tag marks it (`prereg-v6-forward-addendum`). Drafted by Claude for the author, on the author's instruction.

## 1. Why

`VALIDATION.md` 7J repeated the technical price and the seasonal price under each of the four backcast arms of 7I. The forward test fits its model on months from January 2024, with no pandemic months, and has no loading. It resembles the arms that ran 68% to 71% as sold, not the pre-registered arm A that ran 60.6%. At its frozen multipliers those arms put 5 months of 70 above a 100% loss ratio as sold. So G3 and H3 (no month above 100% as sold) are at real risk, and the reach band of G4 and H4 (20% to 55%) was set at the price without multipliers. The multiplier of 1.27 in June and July raises every price, so reach may fall below the band for that reason alone. None of this changes a rule. It is written down now so that a failure is read as what the record already suggested.

## 2. What is added

A **second series**, reported next to the pre-registered one in the same result file, **without any expectation**:

- **The loaded price.** The seasonal price of `PREREGISTRATION_V6_FORWARD.md` section 3 multiplied by a fixed loading of **1.10**. 1.10 is the low end of the 1.10 to 1.13 that 7J found as the technical price as sold under the three arms that resemble the forward model. It is fixed here, is not refitted, and is not chosen again after any read.
- **The 5% cap is applied to the loaded price.** Reach and the connections sold therefore differ from the pre-registered series.
- **Reported per month:** the sold loss ratio and the share sold, from `mcp.v6` (`loaded_table`), written under the key `loaded` of `results/v6_forward_<window>.json`.

The pre-registered numbers (`months`, `pooled_adjusted_ratio`, `mae_season`, `mae_none`, `share_sold_range` and the others) are computed by the same code as before, and a test pins them to a hand-built table.

## 3. What is not changed

The multipliers and their hash, the windows, the model, the sample, the cap, the target, the bands G1 to G4, H1 to H4 and Q1, and the rule that a window is read once. G3, H3, G4 and H4 are graded on the series without the loading, as written. The loaded series is **never** used to say that a pre-registered expectation passed or failed.

## 4. Order guard

`mcp.v6` `run` and `read` now refuse to start until the scheduled reads of v3 and v4 (`results/holdout_v3_next.json`, `results/holdout_v4_next.json`) and of v5.2 (`results/v5_2_holdout.json`) have written their results. The forward test refits on every month from January 2024 through the block start, which includes September 2026 to February 2027, the months those reads are scheduled to touch first. The guard changes no computation.

## 5. Not allowed after the read

Changing the loading, the cap rule of the loaded series, the months it is reported for, or reading it as a test. A bug may be fixed only with the numbers before and after, in `VALIDATION.md` Part 7.

## 6. What this cannot show

Whether a loaded price would sell. The share sold at the loaded price says only how many connections stay under the cap, and says nothing about demand. A loading of 1.10 fitted on 2019 to 2026 weeks says nothing about whether the claims of 2027 need that much.
