# Season 2 review and the plan for what follows

Written 14 November 2026 against branch `claude/season2` at commit `8592c5b`. It has two parts. Part A is an independent review of the season 2 pre-registrations and of `VALIDATION.md` Part 7. Part B is a handoff. Each task states the files it touches, what done means, where to stop and report, and whether a pre-registration must be pushed first. An executing model should not need to make a judgment call. Where one is needed, the task says "owner decides" and the work stops there.

Numbers in Part A marked "review run" were computed once by the reviewer from the weekly files on disk and are not yet in a results file. Task T1 turns them into results files with tests. Until then they are not to be quoted anywhere else.

The plan for the other repositories of the portfolio is a separate file, `PORTFOLIO_PLAN.md`, on branch `claude/tender-hypatia-z5ndyk` of `dbechrakis/dbechrakis`.

## Status (14 November 2026)

T1, T2 and T3 are done (`VALIDATION.md` 7J, the scoreboard, the order guard in `mcp.v6`). T4 and T5 are done (7K and 7L). The owner agreed to the forward addendum (O2), which is `PREREGISTRATION_V6_FORWARD_ADDENDUM.md`. T6 stopped at its gate (`VALIDATION.md` 7M: 8 airline-quarters against the 40 needed), as the plan said it should, and was not built. T7 and T8 are open. Each task below keeps its text as written.

## Part A. Review

### A1. What the review confirms

- Every season 2 pre-registration states what was seen, fixes its rule by a formula, and was committed before its data. The addendum to the backcast was written before any outcome and for a reason that can be checked by counting months.
- Failures are reported as failures. B3 to B6, B8, C1 and X1 are in the same commit as their results, and the scoreboard matches the grading code.
- The seasonal pattern of 7G does not depend on the backcast arm. Review run: with the backcast weeks of arm B, C or D in place of arm A, every multiplier stays within 0.05 of the frozen one, and the leave-one-year-out error is 0.123 to 0.134 with the season against 0.205 to 0.213 without. The core of the forward test stands on firm ground.

### A2. Findings that need a correction

**F1. The conclusion of 7C rests on arm A, which 7I showed to be the exception.** 7C says the existing price is about right as sold and that the 1.16 loading is not a requirement. Its weekly record uses the arm A backcast weeks. Review run, technical price as sold at a 35% expense share, as a multiple of the existing price: 1.03 with arm A, 1.13 with arm B, 1.10 with arm C, 1.12 with arm D. The pooled sold loss ratio of the eight-year record is 65.8% with arm A and 70.5% to 72.2% with the others. Weeks above 100% as sold: 51 of 306 with arm A, 69 to 71 with the others. So the statement that the loading is not needed holds only under the one arm that trains on the pandemic months. 7I corrected the README and the memo for the history reading. It did not carry the correction into 7C, the README's reading of the technical price, or the memo.

**F2. Why arm A differs is visible in what it sells.** Review run, share of overnight-risk connections sold within the cap: in 2021 arm A sold 26.3% against 35.5% for arm C, and in 2022 it sold 32.5% against 41.3%. In 2019 and early 2020 the two arms sell the same share. A model that has seen the pandemic months prices higher afterwards, so fewer connections pass the cap and those that pass are safer. Arm A's 60.6% came with about nine points less reach in two of the five years. 7I says the mechanism cannot be told from the record. The reach by arm and year tells most of it.

**F3. The forward test's model is like arms B to D, and it has no loading.** `PREREGISTRATION_V6_FORWARD.md` drops the loading because it missed its line on the backcast. That was measured on arm A. The forward model is fitted on months from January 2024, with no pandemic months, so it resembles the arms that run 68% to 71% as sold. Review run, at the frozen multipliers and without re-applying the cap: the pooled sold loss ratio of the record is 67.3% with arm A and 72.0% to 73.8% with the others, and 3 to 5 of 70 months are above 100%. G3 and H3 (no month above 100% as sold) are therefore at real risk. The pre-registration is not changed. The risk is written down now, before any 2027 month exists, so that a failure of G3 or H3 is read as expected by this review and not as a surprise.

**F4. The reach band of G4 and H4 was set at the existing price.** The band of 20% to 55% comes from the backcast at the price without multipliers. In June and July the multiplier of 1.27 raises every price, so fewer connections pass the cap. The band may fail on its lower side for that reason alone. Nothing is changed. T1 measures the reach at the seasonal price on the record so the expectation can be read with that number next to it.

**F5. The tie band of X1 was below the fit noise.** The rule was a gain of at most 0.0002 in log loss. Two fits of the same information with different seeds differ by 0.000215. With one seed pair, a null result would have failed the rule about half the time. 7H says so in its reading. The verdict stays as written. T4 replicates the comparison over five seeds so the gain is stated with its spread.

**F6. The placebo of the coding audit is weak by design.** Its window is 26 months with three airlines, and the months after the fake break are September to February only, so month-of-year effects estimated on two years cannot separate season from break. The failure of C1 is correctly applied as written. T5 adds an exploratory reference distribution of fake breaks, and T6 proposes a sharper test that needs its own pre-registration.

**F7. Q1 separates little.** Its band of 0.546 to 0.987 overlaps the band of V1 (0.77 to 1.23) between 0.77 and 0.987. Q1 and V1 disagree only below 0.77 or above 0.987. Also the multipliers were fitted on refitted models, and Q1 grades the frozen v3 model, which ran 1.12 on March to August 2026. Nothing is changed. The scoreboard note for Q1 should say this when it is graded.

### A3. Process findings

**P1. The v6 tags do not exist yet.** The remote has tags up to `prereg-v5-2-loading`. The six `prereg-v6-*` rows are in the workflow file on the branch, and the workflow runs only when dispatched. The owner runs it (task O1).

**P2. A squash merge would orphan the pre-registration commits.** `main` has been squash-merged so far. The season 2 pre-registrations are dated by the push time of their own commits on `claude/season2`. If pull request 7 is squashed and the branch deleted before the tags exist, those commits are no longer reachable and the dating evidence is gone. The tags must be created first, and the pull request should be merged with a merge commit (task O1).

**P3. `mcp.v6 run` has no guard on the order of reads.** It refits on every month from January 2024 through the block start, which includes September 2026 to February 2027. Those months belong to the scheduled reads of v3, v4, v5.1 and v5.2. By the calendar the scheduled reads come first. The code does not enforce it (task T3).

**P4. B9 and B10 show as pending on the scoreboard** although 7B reports both. Their document says they are graded by hand (task T2).

**P5. The data for the arms lives only in this container.** `results/backcast_weeks_C.csv` and `_D.csv` were copied from the data directory on 14 November 2026 so that T1 does not need a rebuild. The row files (`rows_A` to `rows_D`) are too large to commit. Tasks that need them say so and say what to do if they are gone.

## Part B. Tasks

General rules for every task. Work on `claude/season2` until pull request 7 is merged, then on a new branch from `main`. Follow `CLAUDE.md`. New text goes in `VALIDATION.md` Part 7 under the letter given. Every number comes from a results file and a test pins it. Run `python -m pytest -q` before every commit. Never touch a month from September 2026 on. Do not merge and do not push to `main`.

Order: T1, T2, T3, then T4 to T7 in any order, then T8. O1 to O3 are the owner's.

### T1. Arm sensitivity of the technical price, the season and the reach (corrects F1 to F4)

- **Pre-registration:** none. Exploratory, on data already read. Label it so.
- **Needs:** `results/backcast_weeks_A.csv` to `_D.csv` and `results/risk_weeks_2019_2026.csv`. All are committed. No raw data.
- **Code:** add `arm_sensitivity()` to `src/mcp/capital.py` and a CLI entry `python -m mcp.capital arms`. For each arm A to D: drop the pandemic months (March 2020 to June 2021) from the arm's weeks, append the development weeks (rows of `risk_weeks_2019_2026.csv` whose `source` is not `backcast_2019_2023`), then compute
  1. pooled loss ratio at the existing price, weeks above 100% and worst week, for all connections and as sold (`weekly_record`),
  2. `solve(...)` at expense 0.35 with no attachment and with attachment 1.0, both views,
  3. `v6.fit_season` multipliers and `v6.leave_one_year_out` at kappa 1 on the monthly log ratio,
  4. the share sold by year (sum of `w` over sold rows divided by the sum over all rows, backcast years only),
  5. as sold at the frozen multipliers of `models/v6_season.json`, premium times the month's multiplier, cap not re-applied: pooled loss ratio and the number of months above 100%, over all months and over June to August.
- **Result file:** `results/arm_sensitivity.json`.
- **Check against the review run.** As sold, technical multiple at expense 0.35 and no attachment: A 1.032, B 1.130, C 1.103, D 1.118. Pooled sold loss ratio: A 0.658, B 0.722, C 0.705, D 0.715. Weeks above 100% as sold: 51, 71, 70, 69. Share sold in 2021 and 2022: A 0.263 and 0.325, C 0.355 and 0.413. Leave-one-year-out error with the season: 0.125, 0.134, 0.123, 0.125. Months above 100% at the frozen multipliers: A 3 of 70, B 5, C 5, D 5.
- **Gate:** if any of these differs from the review run by more than 0.005 (or by more than one week or month for counts), stop and report both numbers. Do not write the section.
- **Document:** `VALIDATION.md` section 7J, "The technical price, the season and the reach under each arm (exploratory)". It must contain: one table of the numbers above, a paragraph marked **Correction** saying that the reading of 7C ("the existing price is about right, and the 1.16 loading is not a requirement") holds under arm A only and that under the other arms the price needed as sold is 1.10 to 1.13 times the existing one, a paragraph on reach (F2), a paragraph on the forward test (F3 and F4) that states plainly that this is written before any 2027 month exists and that G3, H3 and the lower side of G4 and H4 are at risk, and a line that the seasonal multipliers do not depend on the arm.
- **Other files:** in `README.md` and `docs/decision-memo.md`, find every sentence that says the existing price is about right or that the loading is not required, and qualify it with the arm range and a pointer to 7J. Search for "about right", "not a requirement", "1.16". In `VALIDATION.md` 7B, add one bracketed line directly under the exploratory paragraph: "[Corrected in 7I.]". In 7C add one bracketed line under "What it says": "[Qualified in 7J.]". Change nothing else in 7B or 7C.
- **Tests:** in `tests/test_capital.py`, a hand-built test of `arm_sensitivity` on a small table with known answers, and a test that every number in the 7J table equals `results/arm_sensitivity.json` (pattern: the 7I test in `tests/test_backcast.py`).
- **Done when:** the suite is green, 7J exists, the two documents are qualified, commit and push.

### T2. Scoreboard rows for B9 and B10 (P4)

- **Files:** `results/prereg_status.json`, `SCOREBOARD.md`, and whatever writes them (`src/mcp/grade.py` or its scoreboard writer. Read how E6 or another hand-graded row was set and follow it).
- **Change:** status "reported" with a one-line result. B9: "arm A 0.932 as sold, arm B 1.088 (see 7B and 7I)". B10: "largest change +0.121 between windows 12 months apart (see 7B)". The numbers must be read from `results/backcast.json`.
- **Gate:** if the status vocabulary has no "reported" value and adding one breaks a test whose intent is to restrict statuses, stop and report.
- **Done when:** the scoreboard shows both rows as reported and the suite is green.

### T3. Order guard for the forward test (P3)

- **Files:** `src/mcp/v6.py`, `tests/test_v6.py`, `CLAUDE.md` (one sentence in rule 1).
- **Change:** `run(window)` and `read(window)` raise `SystemExit` with a clear message unless `results/holdout_v3_next.json` exists and the result file of v5.2 exists. Find the v5.2 result file name in `src/mcp/v5_2.py`. The guard is a function `scheduled_reads_done(root) -> bool` so it can be tested with a temporary directory.
- **Not allowed:** any change to `analyse`, `monthly_table`, the constants, or the windows. The computation of the forward test must stay byte for byte the same. Add a test that `analyse` on a fixed small table returns the same numbers as before the change (compute them before editing and paste them into the test).
- **Document:** one line in 7J under "Process": the guard was added on the date of the commit, before any 2027 month existed, and changes no computation.
- **Done when:** tests cover both the refusal and the pass, the suite is green.

### T4. Five-seed replication of the schedule test (F5)

- **Pre-registration:** none. It is a replication of a test already read, exploratory, and cannot change the verdict of X1.
- **Needs:** the `hist` variant data on disk. Check that `data/parquet/` holds the `hist` weighted connections and flights (the paths `mcp.schedule_features` reads). If they are missing, stop and report. Do not rebuild without the owner's word, because the rebuild takes hours and downloads 2018 to 2023 again.
- **Code:** add `seeds(n=5)` to `src/mcp/schedule_features.py`: fit the base model and the model with the three features with seeds 0 to 4 on the same rows as the pre-registered run, score each on the same 2023 sample.
- **Result file:** `results/schedule_features_seeds.json` with the ten log losses, the mean and standard deviation of each model, the mean gain, and the standard deviation of the five paired gains.
- **Document:** section 7K. One table. State the mean gain and its spread, and whether the mean gain exceeds twice the spread of the base model across seeds. State that X1 failed as written and that this section does not regrade it.
- **Gate:** none on the outcome. Report whatever it shows.
- **Tests:** a number-pinning test for 7K, and a test on a tiny table that `seeds` returns `n` results per model and that the seed changes the fit.

### T5. A reference distribution for the coding audit's placebo (F6)

- **Pre-registration:** none. Exploratory. C1 and C2 keep their status.
- **Needs:** the airline-month panel that `mcp.coding_audit` builds. If the panel is cached in the data directory, use it. If it must be rebuilt from flights and they are missing, stop and report.
- **Code:** add `placebo_distribution()` to `src/mcp/coding_audit.py`. On the pre-break period January 2018 to August 2022 without the pandemic months, run the primary model for every fake break month that leaves at least 8 observed months on each side. Record each estimate for Y1 and Y2.
- **Result file:** `results/coding_placebo_distribution.json` with the list of fake breaks and estimates, their 2.5th and 97.5th percentiles, and where the real estimates of 1 September 2022 (−7.9 and −2.6) fall in that distribution.
- **Document:** section 7L, short. Say whether the real estimates lie outside the central 95% of fake-break estimates for each outcome. Say that fake breaks next to each other share data, so this is a reference and not a test.
- **Tests:** a hand-built panel with a known step at a known month. The function must return a larger estimate at that month than at the others. A number-pinning test for 7L.

### T6. A sharper coding test on clear days (new, sealed)

- **Pre-registration: required, before the outcome is built.** Write `PREREGISTRATION_V7_CLEAR_DAY.md`, commit and push it, and add its row to `.github/workflows/preregistration-tags.yml` in a second commit, before any share below is computed.
- **Idea.** On flights between two of the five hubs, both ends have ASOS weather and FAA programs on disk. Take cancelled flights whose scheduled departure hour and scheduled arrival hour, each with three hours either side, had no adverse ASOS flag and no FAA program at either hub. On such flights a weather or air-system code cannot be explained by conditions at either airport. The outcome Y3 is the share of these cancellations coded weather or national air system (B or C), by committing airline and calendar quarter.
- **Step 1, counts only, before the pre-registration is finalised.** Count the denominator (cancelled hub-to-hub flights on clear windows) by airline and quarter, with no cause code read. **Gate:** if fewer than 40 airline-quarters have at least 100 such cancellations outside the pandemic, stop and report the counts. Do not lower the threshold.
- **The pre-registration must fix:** the definition above, the break of 1 September 2022, the same airlines as `PREREGISTRATION_V6_CODING.md`, the model (airline effects, quarter-of-year effects, one covariate: the share of the airline's flights at the five hubs that day under adverse weather or a program, averaged over the quarter, and a post indicator), the bootstrap over quarters with 2,000 draws and seed 0, a placebo break at 1 September 2019 on January 2018 to February 2020, and two expectations. K1: the placebo estimate is within ±3 points. K2: the post estimate is below +3 points. If K1 fails, K2 is not graded. It must state what was seen (the cause shares of 7E, all aggregate) and that what is new is the restriction to clear windows.
- **Code:** `src/mcp/clear_day.py`, tests in `tests/test_clear_day.py` including a leakage test (changing any cause code cannot change which flights are in the denominator), grading in `src/mcp/grade.py` as `grade_clear_day`, scoreboard rows K1 and K2.
- **Result file:** `results/clear_day.json`. Read once. The module refuses a second run.
- **Document:** section 7M, pass or fail in the same commit as the result.
- **Gate:** if the data for hub-to-hub flights or the FAA program table is missing from disk, stop and report.

### T7. A parametric hedge built on the same-night trigger (new, development evidence)

- **Pre-registration:** none. Both periods have been read. Label as development evidence.
- **Idea.** 7D shows the T2 trigger's monthly payouts move with the gap cover's (correlation 0.88 to 0.95). A reinsurance that pays on the trigger would settle on public data the airline does not write. Measure how much of the sold book's weekly risk it removes.
- **Needs:** the per-connection trigger flags that `mcp.trigger.evaluate` computes, by week. If the weighted connections of `v3` or `hist` are missing, stop and report.
- **Code:** add `weekly()` to `src/mcp/trigger.py` returning, per week, the T2 payouts on connections sold within the cap and the sold gap claims and premium. Add `hedge()` to `src/mcp/capital.py`: fit one hedge ratio h on 2019 to 2023 (least squares of weekly sold claims minus expected on weekly T2 payouts minus their mean), apply it unchanged to 2024 to August 2026.
- **Result file:** `results/trigger_hedge.json` with h, and for the later period: the standard deviation of the weekly sold loss ratio with and without the hedge, the weeks above 100% with and without, and the hedge's average cost as a share of premium (its expected payout).
- **Document:** section 7N. State that the hedge ratio is fitted on one period and applied to another, that both were already seen, and what share of the weekly spread remains.
- **Tests:** leakage test (changing weeks after 2023 cannot change h), a hand-built example with a known h, number pinning.

### T8. Housekeeping after T1 to T7

- **Files:** `docs/season2-plan.md` section 0 (add rows for the review and for each task done), `README.md` test count if it quotes one, `CLAUDE.md` map (add `schedule_features`, `clear_day` if created, and this file), the description of pull request 7.
- **Profile:** in `dbechrakis/dbechrakis` on branch `claude/tender-hypatia-z5ndyk`, the flagship bullet about the backcast says the cover as sold did not lose money (60.6%). Replace that clause with the 7I and 7J reading: the pre-registered arm ran 60.6%, three other ways of fitting the model ran 68% to 71%, and the price needed as sold is up to 1.13 times the existing one. Every number from `results/backcast_arms.json` and `results/arm_sensitivity.json`. Also set the test count in the table "How each project is served and checked" to the count the suite prints.
- **Done when:** the suite is green and both branches are pushed.

### Owner actions

- **O1. Tags and merge, in this order.** In GitHub, Actions, "preregistration tags" workflow, run it on branch `claude/season2`. Check that six `prereg-v6-*` tags exist. Only then merge pull request 7, with "Create a merge commit" and not "Squash and merge". Do not delete the branch before the tags exist.
- **O2. Decide on the forward test (F3).** Recommended: leave `PREREGISTRATION_V6_FORWARD.md` as it is and let 7J carry the warning. The alternative is an addendum before any 2027 month exists that adds a loaded price as a second series reported without expectation. An executing model must not write that addendum without the owner's word.
- **O3. Field the survey** (`docs/survey-fielding.md`), and run the scheduled reads and the `mcp.v6` commands on the author's machine when the months are published.

### Ideas recorded and not scheduled

- **A season by hub.** Denver and Chicago have winter weather and Atlanta and Dallas have summer storms, so a single calendar pattern may hide hub patterns. With 5 to 7 observations per month and hub it needs strong shrinkage. It can only be explored on the record and tested on 2028, because the 2027 multipliers are frozen.
- **A price that knows it is selected.** The cap sells the connections with the lowest prices, which are partly the ones the model under-rates. A loading that rises as the price falls toward the cheapest decile would address the selection where it happens. It needs a pre-registration and a forward window of its own.
- **Europe.** EU261 changes who pays and Eurocontrol publishes delay causes. It is a new project, not a work package of this one.
