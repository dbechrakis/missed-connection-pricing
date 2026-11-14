# Missed-connection pricing, season 2: from the right average to a price for the risk

Plan written 12 November 2026 against `dbechrakis/missed-connection-pricing` at commit `1e56cf7`. It is a handoff: each work package (WP) is sized for one working session of an executing model and states what done means. Nothing in the repository was changed while writing it.

## 0. Status and departures from this plan (updated 12 November 2026)

Written as the work went, so a reader can see where the executed work differs from the plan above. The plan text is otherwise unchanged.

| Package | State | Departures, and why |
| --- | --- | --- |
| WP0 | Done | None |
| WP1 | Done, `VALIDATION.md` 7A | `cred` shrinks toward the all-hub mean instead of a hub's own long-run mean (the latter needs variance components 26 months cannot give). The self-transfer orientation and the sample check were left for the data |
| WP2 | Done. `PREREGISTRATION_V6_BACKCAST.md`, its addendum, `PREREGISTRATION_V6_CODING.md`, `PREREGISTRATION_V6_FORECAST.md` | The addendum replaces `local_season` by `local` in B6 and B7: 44 observed months can never reach the 48 `local_season` needs, so those two could not have been graded. Found before any outcome existed. B10 uses windows 12 months apart because no two valid windows are 24 months apart |
| WP3 | Done | New variant `hist` (all products suffixed `_hist`). GSA rates for fiscal years 2018 to 2023 come from the GSA master files (`mcp.gsa_hist`), because the rate pages and the API carry nothing before fiscal year 2024. DB1B 2017 to 2022 prices the months of the next year. The on-time ingest of 2018 to 2023 (counts only) began before the sample check finished, which section 7 of the backcast pre-registration did not allow. It passed at the first fraction, so nothing depended on it (`results/sample_check.json`) |
| WP4 | Done, `VALIDATION.md` 7B | Read once on 12 November 2026: B1, B2 and B7 passed, B3 to B6 and B8 failed. B10 uses windows 12 months apart |
| WP5 | Done, `VALIDATION.md` 7C | Development evidence on 306 weeks. The annual capital term is small and probably understated |
| WP6 | Done, `VALIDATION.md` 7D and 7E. C1 failed, C2 is not graded | FAA advisories are fetched by four parallel workers at one request a second each, not one worker. The parse gate (100 sampled advisories checked against the pages) passed on the fourth sample, after the first three found an unmapped condition class and flaws in the checker itself |
| WP7 | Done, `VALIDATION.md` 7F. F1 and F2 passed, F2 by one week | Snowfall and weather code at lead 7 exist in the archive only from 12 December 2024, earlier values are missing values. A noise floor for kappa (two fits of the same information) is reported next to it |
| WP8 | Done, `PREREGISTRATION_V6_FORWARD.md` | v6 is the v3 procedure with frozen month multipliers (found after the backcast, `VALIDATION.md` 7G), not a level model and not a loading. The plan's WP8 assumed `local_season` or `none` plus a loading, which the backcast did not support |
| WP9 | Done except the independent review | README round four, the memo's second edition, the decision log, the demo's risk section, the profile. The independent review is done on 14 November 2026 and is in `docs/season3-plan.md` |
| Review | Done, `docs/season3-plan.md` Part A | Seven findings and five process findings. The main one is that 7C rests on arm A, which 7I showed to be the exception |
| T1 to T3 of the review | Done, `VALIDATION.md` 7J | The technical price, the season and the reach under each arm. B9 and B10 are reported on the scoreboard. The forward test waits for the scheduled reads |
| Forward addendum | Done, `PREREGISTRATION_V6_FORWARD_ADDENDUM.md` | A loaded series at a fixed 1.10, reported without an expectation, pushed before any 2027 month existed. The tag row is in the workflow |

## 1. Where the project stands, and what it has not answered

Season 1 answered "is the price right on average?" and reported honestly that the answer is "nearly, and not as sold". Reading every result together, four findings keep recurring and none of them is a modelling problem any more:

1. **The level moves and a lagged level trails it.** Chicago ran 0.92, 1.18, 1.23 over 2024 to 2026. v5 failed S1 at 1.16. v5.1 chose "no correction" because no lagged correction helped. The loading of 1.16 is a single number fitted on the same 26 months.
2. **The risk is a correlated weather risk.** Monthly ratios have a standard deviation of 0.24, 6 of 26 months as sold are above 100%, and learning the loss ratio takes about 202 weeks. The memo says "the margin must carry it" but no number says how much margin.
3. **Everything rests on 32 months.** The clean test is 8 months. The tail is 114 weeks. Limit 9 says only time closes this.
4. **Two launch blockers sit outside the 14 limits.** Claims cannot be settled on the night, and airlines write the cause codes the trigger depends on. Also the hidden-information spread κ is declared unmeasurable.

Season 2 takes these four on with data that is public, was verified to exist on 12 November 2026, and has never been loaded by this project.

**The thesis.** Stop asking for a better P(miss). Model the claims level as a random process, test that model on six years the project has never seen, and turn its predictive distribution into a margin, a stop-loss cost and a sales rule. Then replace the airline-written trigger with one that an independent public source can settle the same night.

## 2. New data, all checked on 12 November 2026

| Source | What it adds | Check made |
| --- | --- | --- |
| BTS Marketing Carrier On-Time, **January 2018 to December 2023** | 72 unseen months of the same flights file v3 to v5 use. About 33 MB a month | `..._Beginning_January_2018_2018_1.zip` returned HTTP 200, 33.6 MB |
| BTS Reporting Carrier, 1987 on | Optional, only if a v1 arm is wanted | 2019_7 returned 200 |
| FAA ATCSCC Advisories Database | Every ground stop and ground delay program by airport, with issue time and stated cause, written by the FAA and not the airline, published in real time | `https://www.fly.faa.gov/adv/adv_list?whichAdvisories=ATCSCC&advisoryCategory=All&date=2019-07-18&airflow=true&ctop=true&gStop=true&gDelay=true&route=true&other=true` returned the 18 July 2019 list including `ORD/ZAU CDM GROUND STOP` and `ORD/ZAU CDM GROUND DELAY PROGRAM`. Detail pages are `/adv/adv_otherdis?adv_date=MMDDYYYY&advn=N`. The date field accepts 1980 onward |
| Open-Meteo Previous Runs API | Forecasts **as issued** 1 to 7 days ahead (`<var>_previous_day1` … `_previous_day7`): precipitation, snowfall, wind gusts, weather code | Non-null on 2024-04-15, 2024-08-15, 2025-07-15, 2026-07-15. Null on 2024-01-12, so the archive starts between January and April 2024. Find the first non-null date before using it |
| IEM MOS archive (`/api/1/mos.json`) | US government forecast guidance as issued. GFS MOS to 72 hours. MEX to 8 days | GFS returned rows for 2018-07-01. MEX returned rows for 2021, 2022, 2023, 2024 and none for 2019-07-01 |
| IEM TAF archive | Airport terminal forecasts as issued, about 24 to 30 hours ahead | Rows from 2020 on, none in 2018 |
| IEM ASOS, GSA per diem, DB1B | Already in the pipeline. Need earlier years | `mcp.costs` already takes a fiscal year. DB1B has every quarter before 2025 Q2 |

Not verified, from memory only: the DOT Airline Customer Service Dashboard went live about 1 September 2022, with most hotel commitments made in the weeks before. WP6 must confirm the date at the source before using it.

## 3. Standing rules for whoever executes this

These come from the repository's own practice. Breaking any of them destroys the thing that makes the project credible.

1. **Sealed months.** No code other than the existing scheduled job may ingest, build or score BTS months from September 2026 on. The reads in February 2027 (v1 to v4, v5.1) and May 2027 (v5.2) are not part of this plan and must not be touched, moved or anticipated.
2. **Pre-register before the data is on disk.** For every WP marked "sealed", the pre-registration is committed and pushed before the first download of the data it concerns. Tags are added by extending `.github/workflows/preregistration-tags.yml`, as for v5.
3. **Frozen files stay frozen.** Never edit, reformat or re-save `models/*`, `config/pricing.yaml`, `config/guards.yaml`, any `PREREGISTRATION_*.md`, or Parts 1 to 6 of `VALIDATION.md`. New results go in a new **Part 7**. A correction goes in the later part, marked as one.
4. **New history lives in new directories.** Put 2018 to 2023 under `data/parquet/ontime_hist/` and `data/parquet/hist_*`. Several existing modules scan a whole directory. If old months land in `ontime_v3/` the published numbers stop reproducing.
5. **Do not change `requirements.lock` versions.** `tests/test_frozen_models.py` fails under another scikit-learn. Prefer numpy implementations over new dependencies. If one is unavoidable, add it pinned and confirm the frozen-model test still passes.
6. **Every number in a document comes from a results file, and a test checks it.** Follow `tests/test_docs.py`. The suite must stay green and needs no data.
7. **Leakage tests come with the feature.** Any forecast, advisory or history feature needs a test showing that changing later information cannot change it. The project already made this mistake once (`VALIDATION.md` 4H) and recorded it.
8. **Report failures as prominently as passes**, in the same commit as the result. Never retune after a read.
9. **House style in documents:** plain sentences, full stops in place of dashes and semicolons, no number typed by hand, limits stated as what was found and what closes the rest.
10. Work on a branch and open a pull request only when the owner asks. Never push to `main` directly.

WP0 writes these ten rules into a `CLAUDE.md` at the repository root so every later session starts with them.

## 4. The work packages

Order matters because of the sealing. WP1 and WP2 use only data already seen. WP3 onward touches unseen data.

### WP0. Orientation and `CLAUDE.md` (small)

Read `README.md`, `SCOREBOARD.md`, `docs/method.md`, `VALIDATION.md` Parts 5 and 6, `src/mcp/v3_rolling.py`, `v3_loading.py`, `v5.py`, `v5_1.py`, `grade.py`. Run the test suite. Add `CLAUDE.md` with section 3 above plus the repository map.

Done means: suite green, `CLAUDE.md` committed, nothing else changed.

### WP1. A model of the level, and the risk arithmetic, on development data only (medium)

**Why.** Every repair so far treats the level as a constant to be estimated late. Treat it as a process and forecast it, with an honest variance.

**Build `src/mcp/level.py`** in numpy, no new dependency:

- Input: a monthly series per hub of `log(claims ÷ expected claims)` with its exposure, and a publication lag L in months (2 for the gap cover, 5 for self-transfers as v5.1 used).
- Candidates, all fixed now so that none is chosen after a look:
  - `none`: level 1. What v3 and v5.1 use.
  - `last12`: the pooled ratio of the last 12 known months.
  - `cred`: Bühlmann-Straub credibility. Level = Z × recent 12 months + (1 − Z) × long-run mean, per hub, with Z from the estimated between-period and within-period variances.
  - `local`: a local-level state-space model (random walk plus noise) by Kalman filter, forecast L months ahead. Variances by maximum likelihood on earlier months only.
  - `local_season`: `local` plus a month-of-year effect, shrunk toward zero, used only when at least four earlier years exist. **This one is the primary candidate.**
- Output for each month: a point level and a **predictive distribution** of that month's realized ÷ expected ratio (lognormal, variance = state variance at lag L + month noise).
- Comparator for the intervals: adaptive conformal intervals on the same one-step errors.

**Build `src/mcp/risk.py`:** functions for the stop-loss burning cost at an attachment point per week, month and year, a season-stratified block bootstrap of weeks into simulated years, value at risk and tail value at risk of the annual loss ratio, a cost-of-capital margin, and the continuous ranked probability score and interval coverage of a set of predictive distributions.

**Tests** (`tests/test_level.py`, `tests/test_risk.py`): each candidate recovers a planted level, a planted trend and a planted seasonal pattern within stated tolerance. No candidate reads a month later than m − L, shown by changing later months and checking nothing moves. Interval coverage is right on simulated series, judged over many simulated series and not one seed, as `decisions.md` round 4 learned. Stop-loss and tail functions match closed forms on a known distribution.

**Orientation run** on the existing 26 out-of-sample months (`results/v3_rolling.json`, `results/v3_rolling_weeks.csv`, and v5.1's walk-forward). Write `results/level_dev.json`. This is development evidence and is labelled so. With 26 months the seasonal candidate cannot run. That is expected and is the reason for WP3.

**Sample check.** WP3 will use a 20% uniform hash sample of pairings. Show on 2024 to 2026 that the sample reproduces the published pooled ratios of `v3_rolling` (1.04 all, 1.15 as sold) within 0.02. If it does not, raise the fraction until it does and record the fraction.

Done means: both modules, tests green, `results/level_dev.json`, a short `VALIDATION.md` 7A describing the candidates and what the 26 months say. No candidate may be dropped or added after this point.

### WP2. Two pre-registrations, pushed before any 2018 to 2023 byte is downloaded (small, and the most judgment-heavy step)

Write, commit, push, then stop. The owner should have these two documents reviewed by the strongest model available before the push. They are short and every later result is judged by them.

**`PREREGISTRATION_V6_BACKCAST.md`.** A backward holdout.

- What has been seen: everything from January 2024 to August 2026. What has not: no flight before January 2024 has ever been loaded by this project. Say plainly that this is weaker than "the data does not exist". The data exists and the author knows the broad history (the summer of 2022, the December 2022 storm and airline meltdown, the pandemic). What protects the test is that every specification was chosen on 2024 to 2026 and the push precedes the download, which the manifest's file hashes and ingest dates record.
- Population, label, features, cap, target: exactly v3 for the gap cover and exactly v5 for self-transfers. A 20% hash sample (or the fraction WP1 fixed).
- Procedure: rolling origin, as `v3_rolling`. Fit on 2018 only, then score from **January 2019 to December 2023**, in three-month blocks, each block priced by a model fitted only on earlier months, with v3's one-month booking lag. Arm A uses all earlier months. Arm B uses the trailing 24 months. For self-transfers, v5's cell table with k = 1000 fitted on months up to m − 5.
- On top of those out-of-sample prices: the v4 fixed-point loading refitted each month on earlier months, and all five level candidates of WP1.
- Weights and fares: DB1B of the **previous** calendar year (at least the second and third quarters), so no weight depends on a later month. GSA per diem by fiscal year.
- **Pandemic months, declared now: March 2020 to June 2021.** Reported separately and excluded from every headline.
- A caveat to state: the DOT hotel commitments did not exist as a dashboard before 2022, so before then this tests the risk process and not the product's history.
- Expectations. Proposed values below. Final bands must be written with the formula that produced them from development results:

| # | Expectation | Proposed band | From |
| --- | --- | --- | --- |
| B1 | Gap cover, all overnight-risk connections, pooled realized ÷ target | 0.90 to 1.20 | 1.04 on 26 months |
| B2 | Standard deviation of the monthly ratios | 0.17 to 0.33 | 0.24 on 26 months |
| B3 | As sold within the 5% cap runs worse than all connections | directional | 1.15 against 1.04 |
| B4 | Share of months above a 100% loss ratio as sold | 8% to 40% | 6 of 26 |
| B5 | The monthly refitted loading lowers the pooled sold loss ratio by at least 3 points | at least 3.0 | 77.8% to 70.4% |
| B6 | `local_season` is closer to 1 than `none` and than `last12`, pooled | directional | the thesis of season 2 |
| B7 | The 90% predictive intervals of `local_season` cover 80% to 97% of months | 80% to 97% | binomial range at about 48 months |
| B8 | Self-transfers: years in which the 12-month level rose are under-priced and years in which it fell are over-priced (the annual ratio and the annual change in level have the same sign in at least 4 of 5 years) | 4 of 5 | the mechanism behind S1's failure |
| B9 | Arm A against arm B: no prediction, reported either way | none | open question |
| B10 | Was the 2024 to 2026 rise unusual? The largest earlier 24-month change in the 12-month level is reported. No prediction | none | open question |

- If B1 fails, the pricing procedure is not right outside the years it was designed on, and that becomes the headline. Nothing is refitted.

**`PREREGISTRATION_V6_CODING.md`.** Did airlines change how they code delays once the code decided who pays for the hotel?

- Question: after the DOT dashboard, an overnight disruption coded to the airline costs it a hotel. The gap cover pays exactly when the code is **not** the airline's. The README names this as an unpriced risk.
- Outcome: by airline and month, among flights touching the five hubs, the share coded to the carrier of (a) cancellations and (b) arrival-delay minutes on delays of 180 minutes or more.
- Adjustment for what objectively happened, from sources the airline does not write: an FAA ground stop or ground delay program at the hub during the flight's scheduled window, and hub weather from ASOS (thunderstorm, freezing or frozen precipitation, visibility under 1 mile, gusts over 35 knots).
- Design: an interrupted time series per committing airline around the dashboard date, pandemic months excluded, with Frontier (no hotel commitment) as the comparison series. One comparison airline is thin, so the document says so and makes the within-airline break, conditional on objective conditions, the primary reading.
- Expectation C1: no directional prediction on the sign. C2: whatever the estimate, the document fixes in advance the size that would matter for the price (a fall of 3 points or more in the carrier-coded share, conditional on conditions) and how much that would raise gap-cover claims.
- The same months are also used by the backcast for outcomes. This document must be pushed before the download so the coding series is specified blind.

Done means: both documents on GitHub, tag rows added to the tagging workflow, scoreboard rows added as pending with rules written in `mcp.grade`.

### WP3. Ingest 2018 to 2023, sealed (medium)

- Extend `mcp.ingest` with a `--hist` switch writing to `data/parquet/ontime_hist/`. Record every zip's SHA-256 and ingest date in `data/manifest.json`.
- ASOS for the five hubs for the same years. GSA for fiscal years 2018 to 2024 through `mcp.costs`. DB1B for 2018 to 2022 (previous-year rule).
- Build gap-cover connections and self-transfer pairings with the existing SQL, sampled, with outcome rates suppressed (counts only), as `--sealed` does in `mcp.v5`.
- Add the new directories to the guard tests so only `mcp.backcast` may read them.
- Known traps: Virgin America disappears into Alaska in 2018. Schedules collapse in spring 2020. Some 2018 months have different column casing, so read as text and cast explicitly as the decision log already requires.

Done means: row counts by month and hub in `results/hist_counts.json`, no outcome rate printed or stored, suite green.

### WP4. The backcast, read once (medium)

- `src/mcp/backcast.py`: runs the procedure of WP2 exactly, refuses a second run as `mcp.v5 holdout` does, writes `results/backcast.json` and a weekly series `results/backcast_weeks.csv`.
- `mcp.grade` grades B1 to B10. Update `SCOREBOARD.md`.
- Write `VALIDATION.md` 7B: every pre-registered number, pass or fail, then pandemic months separately, then by hub and year.
- Then, and only then, join the two periods into one series from 2019 to August 2026 and save it as `results/level_series.json`. This is the input to WP5 and WP8.

Done means: results committed in the same commit as the write-up. If the headline failed, the README says so in its first screen.

### WP5. Pricing the risk (medium)

Uses the 2019 to 2026 weekly series, about 400 weeks against the 114 the project had. Development evidence, labelled so. Eight years cannot give a 1-in-100 year and the write-up must say that and report 1-in-10 and 1-in-20 with intervals.

- **Stop-loss cost**: burning cost per unit of premium at weekly, monthly and annual attachments of 90%, 100% and 120%, with block-bootstrap intervals. This replaces "at least 8.6% of premium" from 114 weeks and answers row 7 of `docs/agency-inputs.md` as far as public data can.
- **Margin from capital**: annual loss-ratio distribution by season-stratified block bootstrap, value at risk and tail value at risk at 90% and 95%, and a cost-of-capital margin on a grid of 6%, 10% and 15%.
- **The technical price**: expected claims × forecast level + stop-loss cost + capital margin, divided by one minus an expense ratio. Show it next to the ad hoc loading of 1.16. Say which is larger and why.
- **Diversification**: the correlation matrix of weekly hub ratios, and the standard deviation of the five-hub book against the average single hub. Says whether "more hubs" on the roadmap buys safety or only volume.
- **Economics, second edition**: redo the `VALIDATION.md` 5J tables (margin per policy, attach rate needed) at the technical price.

Done means: `src/mcp/capital.py`, `results/risk_v6.json`, tests on closed forms, `VALIDATION.md` 7C, and one sentence for the memo: what the cover must cost for the margin to carry the weather, and what share of connections still fit the cap at that price.

### WP6. A trigger that settles the same night, and the coding audit (large, split into two sessions)

**Session 1: FAA advisories.** `src/mcp/faa.py` fetches one list page per day from 2018 to August 2026, then the detail page of each ground stop and ground delay program at ATL, CLT, DEN, DFW and ORD. At most one request a second. Cache the parsed result per day under `data/external/faa/` with the reading date, as the GSA pages are cached. Parse airport, program type, start, end or cancellation, and the stated impacting condition, then map it to weather, volume, runway or equipment, staffing, airline, other. Times are UTC. BTS times are local, so convert with `zoneinfo` and three zones (New York, Chicago, Denver). Test daylight-saving days explicitly.

Gate: hand-check 100 random programs. If fewer than 90 are parsed and classified correctly, stop and fall back to the weather-only trigger.

**Session 2: the trigger and the audit.**

- `src/mcp/trigger.py`. Two parametric triggers fixed before scoring: (T1) the connection is missed overnight and an FAA program with a non-airline cause was active at the hub between three hours before the inbound's scheduled arrival and its actual arrival. (T2) T1 or severe hub weather by the ASOS rule of WP2. Report, on development months 2024 to August 2026 and separately on the backcast years: the share of BTS-coded gap claims each trigger pays, the share of its payouts that BTS codes to the airline, both claim-weighted, the price of each cover with the existing machinery, and its monthly spread. That is the **basis risk** between a cover that can be settled tonight and the one season 1 priced.
- `src/mcp/coding_audit.py` runs `PREREGISTRATION_V6_CODING.md` once and grades it.
- What stays open and must be written down: a same-night settlement also needs actual arrival times that night, which a flight-status feed has and BTS does not. That is one more agency input.

Done means: `VALIDATION.md` 7D and 7E, the "claims cannot be paid on the night" and "airlines code their own delay causes" paragraphs of the README each updated with what was found and what remains.

### WP7. What a late buyer can know: forecasts and the sales window (medium, sealed by a new join)

**Why.** κ, the spread of risk that buyers see and the price does not, is declared unmeasurable. Part of it is measurable: a traveller booking five days out can read the forecast. Travel insurers stop selling once a storm is named. This measures whether this cover needs the same rule.

- Pre-register first (`PREREGISTRATION_V6_FORECAST.md`): fit window from the first non-null Open-Meteo date to August 2025, test window September 2025 to August 2026, read once. The outcomes of those months are known to the project. The join with forecasts has never been made. Say so.
- Features at lead d = 1, 2, 3, 5, 7 days, **as issued**: Open-Meteo previous-run precipitation, snowfall, gusts and weather code for the hub over the connection's afternoon and evening, and IEM MEX thunderstorm and snow guidance. The leakage test: replacing the observed weather of the day must not change any feature.
- Report by lead: the gain in log loss over the booking-time price for the gap cover, the implied spread of log(forecast-informed risk ÷ priced risk), which is a measured floor on κ at that lead, and the exposure exp(θκ²) the project's own formula gives.
- A sales rule, fixed in the pre-registration: stop selling a hub-day when the forecast-informed risk is above 1.5 times the priced risk at lead 3 or less. Report the sold loss ratio, weeks above 100% and the share of sales lost, over a grid of assumed shares of bookings made within 7 days (10%, 20%, 30%), since booking lead is not in public data.
- Expectations: F1, forecasts add under 1% at 7 days and more at 1 day (monotone in lead). F2, the rule lowers weeks above 100% as sold. F3, no prediction on the size.

Gate: if the gain is under 1% at every lead, report the null, close the question as "forecasts do not arm a late buyer", and skip the rule.

### WP8. Freeze v6 for spring and summer 2027 (small, must be pushed before March 2027 data exists)

The README says summer is the real test and is a year away. Register it now.

- v6 is a **procedure**, not a table: v3's model and v5's table, the level by the candidate that the backcast supports under a rule written in WP2 (the primary one unless B6 failed, in which case `none` plus the loading), the technical price of WP5, and the sales rule of WP7 if it survived its gate. It updates itself each month from published months only, with the publication lag.
- Windows: March to May 2027, read when May is published. June to August 2027, read when August is published. Its first run happens after the February 2027 read has been made and published by the existing job, so it cannot touch September to November 2026 before they are graded.
- Expectations in the form the scoreboard already uses, including one on interval coverage and one on the worst month. Extend `watch-bts.yml` to the new months.

### WP9. Tell it (medium)

- `docs/decision-memo.md`, second edition: one page. What the cover must cost once the margin carries the weather, whether it still fits the cap, whether a same-night trigger is close enough to the coded one, and the sales rule. Recommend or withdraw.
- README: move the four-line decision to the season 2 findings, keep season 1 below. Update the limits table. Limit 9 changes from "Open, needs time" to what the backcast showed. Update the tests that pin the limit counts.
- Demo: a third view, "the risk", built from a generated `site/risk.js`: a fan chart of the monthly loss ratio with the predictive intervals against what happened, and the price ladder from expected claims to technical price. Drive it with a Node harness test as the two existing views are.
- An independent sceptical review of the whole of Part 7 by a fresh read-only session, as Part 4 did, with every finding checked before anything changes.
- Profile README (`dbechrakis/dbechrakis`): replace the flagship bullets with the season 2 results once they exist.

## 5. Optional, in order of value

1. **Field the stated-demand survey** that is already written and pre-registered. This is the owner's action and costs money. It is the only way limit 4 moves at all.
2. **Schedule-structure features**, as one pre-registered arm and time-boxed to one session: scheduled arrivals at the hub in the inbound's 15-minute window, and scheduled block time against the route's median actual block time. Keep only if log loss improves by more than the tie band of 0.0002 on the backcast years. The project's own finding predicts a null.
3. **More hubs** with the cell-table approach, only if WP5 shows that diversification across hubs is material.
4. **Europe**, where self-transfer protection is the live product. EUROCONTROL's research archive has flight-level actual times for sample months. Access needs registration and was not verified here. EU261 changes who already pays, so this is a new project and not an extension.

## 6. Calendar and gates

| When | What |
| --- | --- |
| November to December 2026 | WP0, WP1, WP2 (review, then push), WP3 |
| January 2027 | WP4, WP5 |
| Early February 2027 | The existing job reads September to November 2026. Not part of this plan |
| February to March 2027 | WP6, WP7, then WP8 pushed |
| April 2027 | WP9 |
| May 2027 | The existing v5.2 read |
| About August and November 2027 | The two v6 reads |

Stop and report to the owner, without trying alternatives, if: the sample check of WP1 fails at every fraction up to 50%. B1 fails. The FAA parse fails its gate. Any step would require reading a sealed month.

## 7. If only one thing gets done

WP1 to WP4. Six unseen years, a level model judged on them, and intervals whose coverage was predicted in advance. It turns "eight months of clean test data, closed by time" into about 48 clean months, and it tells the project whether its central repair (a loading on a moving level) was right or lucky.
