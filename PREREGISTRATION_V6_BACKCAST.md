# Pre-registration: v6 backcast, the pricing procedures on January 2019 to December 2023

Written **12 November 2026**, before any BTS on-time file for a month earlier than January 2024 has been downloaded, ingested, built or scored by this project. It is a separate document. No earlier pre-registration is edited. The commit that adds it is pushed to GitHub before the first download of any 2018 to 2023 data, and that push bounds when it was fixed. A tag marks the commit (`prereg-v6-backcast`, created by `.github/workflows/preregistration-tags.yml` as for v5). Drafted by Claude for the author, as the decision log records for earlier rounds.

## 1. The question

Every number in this project was produced on 32 months (January 2024 to August 2026). The clean tests cover eight months. Limit 9 of the README says only time closes that. Six earlier years of the same public files exist, and none has been loaded. They cannot show how the pricing procedures would have done in the past as a new test of the future, but they can show whether the procedures, **with every design choice fixed on 2024 to 2026**, hold up on years the choices never saw, and whether the claims level moved in those years the way the project's repairs assume.

Four questions, in order of importance:

1. Does the gap cover's pricing procedure (v3 with no recalibration, refitted at quarterly origins) price within a stated band on 2019 to 2023, outside the pandemic months?
2. Is the month-to-month spread of the realized ratio, and the way the cap selects worse risk, the same in earlier years?
3. Does a model of the claims level that follows the level, with intervals, beat a constant level on months it has not seen? Season 1's central repair (a loading on a moving level) rests on that claim.
4. Does a loading help the self-transfer cover that v5 priced too low?

## 2. What has and has not been seen

- **Seen:** every flight, every outcome and every analysis from January 2024 to August 2026, for the five hubs. All design choices (population, label, features, the 5% cap, the 65% target, the cell table's k, the loading rule, the level candidates) were made on or after looking at those months.
- **Not seen:** no BTS On-Time file before January 2024 has ever been loaded here. No DB1B quarter before 2024 Q1. No GSA rate before fiscal year 2024 is in the cache that `mcp.costs` uses.
- **A weaker protection than "the data does not exist", stated plainly.** The files exist and the author knows the broad history of those years: the 2019 summer, the pandemic collapse of schedules, the airline meltdown and storm of December 2022. What protects the test is that every specification is written down here and pushed before the download, that the files' hashes and ingest dates are recorded in `data/manifest.json`, and that no choice below may change after the read.
- **Done before this document, on months that were already seen.** The 2024 to August 2026 files, DB1B and ASOS were downloaded again to a clean container to rebuild the pipeline and to carry out the sample check of section 7. None of it touches a month before 2024 or after August 2026.

## 3. Population, label and prices (inherited, not chosen here)

- **Gap cover.** Exactly v3: connections within the **marketing** network, minimum connection time 45 minutes, the label `y_gap` (a missed overnight connection, the inbound problem not coded to the airline), the GSA payout for the hub and month, price = P(miss) × payout ÷ 0.65, offered within **5%** of the DB1B route fare. The model is v3's: the v1 feature set, gradient boosting, no recalibration, fitted on a sample of at most 3,000,000 rows as `mcp.v3_rolling` does. Nothing is retuned.
- **Self-transfer cover.** Exactly v5: pairings of two different marketing networks at the five hubs, 90 to 300 minute gaps, minimum self-transfer time 90 minutes, any cause, payout the DB1B nonstop one-way fare plus a GSA night when no later departure exists that day, a cell table (hub × inbound network × 15-minute gap bucket × arrival band) with **k = 1000**, a 5% hash sample of pairings, price = P(miss) × payout ÷ 0.65, offered within 10% of the two-ticket fare.
- **Weights and fares.** DB1B route passengers and fares come from the **previous calendar year's** quarters (for 2019, the 2018 quarters), so no weight or fare depends on a later month. Months of 2018 are used for fitting only.
- **Costs.** GSA per-diem rates for the fiscal year of the month, from the GSA rate pages as `mcp.costs` reads them. If a fiscal year's page cannot be read, the last readable year is used and the month is flagged, not dropped.
- **Sample.** A uniform hash sample of connections. The fraction is fixed by the sample check of section 7 before the download.
- **Known differences from 2024 to 2026.** Airline mergers (for example Virgin America into Alaska in 2018), the 737 MAX grounding in 2019, different hub schedules, and hotel commitments that did not exist as a published dashboard until September 2022. Before then the test is about the risk process, not the product's own history.

## 4. Windows and procedure

| Role | Months |
| --- | --- |
| First fit only | January to December 2018 |
| **Scored** | **January 2019 to December 2023**, read once |
| **Pandemic months** | **March 2020 to June 2021**, declared now |

**Procedure.** As `mcp.v3_rolling`: quarterly blocks. For each block, fit on all months before the block start, then price every month of the block, so each month is priced by a model that has not seen it. Two arms, both declared now:

- **Arm A:** fit on all earlier months from January 2018.
- **Arm B:** fit on the trailing 24 months only.

On top of arm A's out-of-sample prices:

- **The loading** of `mcp.v3_loading`: the fixed-point factor refitted each month on earlier months only, with the one-month booking lag and at least six months of history, evaluated on the same months.
- **The level candidates** of `mcp.level` (`none`, `last12`, `cred`, `local`, `local_season`), at lag 2 months, on the monthly ratio of realized to expected claims of all overnight-risk connections, pooled over hubs and as a five-hub panel.
- **Self-transfers:** v5's table refitted for each month on pairings up to five months earlier, with no level factor (v5.1's chosen rule), and the same table with a loading re-estimated each month from earlier months only (at least three), as v5.2.

**The pandemic.** The pandemic months are scored and reported separately and are in **no** headline. They are removed from every series the level model sees, as missing months, and from every pooled ratio, spread and share below. A calendar quarter or year with any pandemic month is reported only in a separate table.

**Not read.** No month from September 2026 on, and no 2024 to 2026 month in a role it did not have before, is scored here.

## 5. What is reported

For the gap cover and for self-transfers, outside the pandemic months: realized ÷ target pooled, by month, by hub and by year, for all overnight-risk connections and as sold within the cap, with month-block bootstrap intervals; the monthly spread; months and weeks above a 100% loss ratio; the loaded and unloaded sold loss ratios; arm A against arm B; every level candidate's CRPS, interval coverage and repriced ratio; the largest change in the 12-month level over any earlier 24 months (section 9, B10). Separately: the pandemic months.

## 6. Why these bands

The expectation bands come from development results by a formula written next to each, so nobody has to decide after the read what counted. The formulas use the 26 development months of `results/v3_rolling.json` (spread of the monthly ratio 0.241, lag-1 autocorrelation of the monthly ratios 0.70, pooled ratio 1.04 and as sold 1.15, 6 of 26 months above a 100% loss ratio as sold).

## 7. Order of work, fixed now

1. **Sample check, on 2024 to August 2026 only.** A new hash sample of the gap cover's connections at 20% must reproduce the published pooled ratios of `results/v3_rolling.json` (1.04 all overnight-risk, 1.15 as sold) within 0.02. If it does not, the fraction is raised to 50%, and then to 100% if needed. The fraction and both ratios go in `results/sample_check.json`, committed before the first 2018 to 2023 download. Self-transfers keep the 5% sample v5 pre-registered.
2. **Download and ingest 2018 to 2023**, counts only (outcome rates suppressed), as `mcp.v5 build --sealed` does for a sealed window.
3. **Run the backcast once**, `python -m mcp.backcast`, which refuses a second run.
4. **Grade** B1 to B10 with `python -m mcp.grade`, and report every one, pass or fail, in the same commit as the result.

## 8. Not allowed after the read

Changing the population, the label, the features, the model, the cap, the target, the cost source, the sample, the quarterly origins, the two arms, the pandemic months, the loading rule, the candidates of `mcp.level`, the lag, the bands below, or the metric. A bug may be fixed only with the numbers before and after, in `VALIDATION.md` Part 7. If B1 fails, the pricing procedure is not right outside the years it was designed on, and that is the headline. Nothing is refitted.

## 9. Expectations (falsifiable; each is reported, pass or fail)

Months are scored months outside the pandemic. `n` is their number (about 44 of 60).

| # | Expectation | Band and the formula that gives it | If it fails |
| --- | --- | --- | --- |
| B1 | **Calibration.** Gap cover, all overnight-risk connections, arm A, pooled realized ÷ target | 1 ± 2σ ÷ √n_eff, with σ = 0.241, n_eff = n (1 − ρ) ÷ (1 + ρ) and ρ = 0.70 (0.173 at n = 44) | The procedure is not right outside 2024 to 2026 |
| B2 | **Spread.** Standard deviation of the monthly realized ÷ expected ratios | 0.19 to 0.33: the 95% chi-square interval for an sd of 0.241 from 26 months (25 degrees of freedom) | The weather risk was calmer or wilder before 2024 |
| B3 | **The winner's curse.** Realized ÷ target within the 5% cap is higher than on all connections | Directional. Development: 1.15 against 1.04 | Selecting on a low price did not select under-estimated risk in earlier years |
| B4 | **Bad months as sold.** Share of months with a sold loss ratio above 100% (unloaded) | 9% to 44%: the exact 95% interval for 6 of 26 | The cover as sold was safer or more dangerous than 2024 to 2026 |
| B5 | **The loading helps.** The refitted loading lowers the pooled sold loss ratio | By at least 3.0 points, as v4's L1 | The loading does not travel to earlier years |
| B6 | **Following the level pays.** Over the months where `local_season` is active (at least 48 known months), its CRPS on the pooled monthly series is below that of `none` and of `last12` | Both comparisons. Development, where it could not run, preferred `none` (`VALIDATION.md` 7A), so this is a real test | A moving level cannot be told from noise at this length, and v6 keeps `none` plus a loading |
| B7 | **Intervals.** The 90% predictive intervals of `local_season`, over the same months | The number of months inside the interval lies in the central 95% exact binomial range for `n_active` months at p = 0.90 | The intervals are miscalibrated |
| B8 | **A loading helps self-transfers.** v5's table with the refitted loading is closer to 1 than the same table without it, pooled over the scored months | \|loaded − 1\| < \|unloaded − 1\|. Development: 1.154 to 1.005 (`PREREGISTRATION_V5_2_LOADING.md`) | The repair v5.2 tests in winter does not generalise |
| B9 | **Arm A against arm B.** Reported either way, no prediction | None | |
| B10 | **Was 2024 to 2026 unusual?** The largest change in the log 12-month level over any earlier 24 months, reported next to the 2024 to 2026 value. No prediction | None | |

B9 and B10 are graded by hand and stay pending on the scoreboard until written up.

**What follows from the result.** If B6 passes, v6 (WP8 of the plan) uses the `local_season` level. If it fails, v6 uses no level model and keeps a loading refitted on earlier months. This rule is fixed now.

## 10. What this cannot show

That real passengers behave like the synthetic connections. That 2019 to 2023 predicts 2027. Anything about the hotel commitments' effect on coding (that is `PREREGISTRATION_V6_CODING.md`). Anything about demand. With 44 months and a month-to-month autocorrelation near 0.7, the bands above are wide on purpose: a pass says the procedure is not contradicted, not that it is right.
