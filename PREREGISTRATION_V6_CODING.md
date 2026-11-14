# Pre-registration: v6 coding audit, did airlines change how they code delays once a code decided who pays for the hotel?

Written **12 November 2026**, before any BTS on-time file for a month earlier than January 2024 has been downloaded, and before any FAA advisory has been read. It is a separate document. The commit that adds it is pushed to GitHub before the first such download, and a tag marks it (`prereg-v6-coding`). Drafted by Claude for the author.

## 1. The question

The gap cover pays exactly when the BTS cause code of the inbound delay is **not** the airline's. US airlines commit to a free hotel only for overnight disruptions they control (DOT Airline Customer Service Dashboard). So from the day those commitments existed, an airline had a money reason to code a delay as weather or air traffic rather than its own. The README lists this as a risk outside the 14 limits and offers expectation V5 of the v3 pre-registration as an early warning. This document tests it directly, on years before and after the commitments.

## 2. When the commitments began, and what is not known

The dashboard was announced by the US Department of Transportation just before Labor Day 2022. A trade article is dated 2 September 2022 (AirlineGeeks, found by web search on 12 November 2026). The DOT's own page returned an access error from this environment, so the date was **not read at its source**. The airlines' commitments were made in the weeks before the announcement, so the first sign of a change could precede it.

- **Break date (primary): 1 September 2022.**
- **Sensitivity breaks:** 1 June 2022 and 1 January 2023. Reported, never used to choose.
- **Airlines.** The commitments listed in `data/external/dot/hotel_commitments.json` (read on 9 November 2026) are for Alaska, Allegiant, American, Delta, Hawaiian, JetBlue, Southwest and United. **Frontier** does not commit to a hotel. The **committing group** is every airline in that list with at least 1,000 cancelled or three-hour-late flights at the five hubs in each of the two periods. The **comparison** is Frontier. One comparison airline is thin, so the within-airline reading below is primary.

## 3. What has and has not been seen

- **Seen:** the cause shares for 2024 to August 2026 (`VALIDATION.md` 5A: 27.5% of missed connections coded to the airline, 31.9% to late-arriving aircraft), all after the break.
- **Not seen:** every month before 2024. That is every pre-break month and the sixteen post-break months from September 2022 to December 2023. No cause-code series from before 2024 has been loaded by this project.
- Unlike the backcast, the weather covariates come from sources the project has partly used (ASOS) and partly never read (FAA advisories). The advisory data is fetched after this document is pushed.

## 4. Data and outcome

- **Flights:** the BTS Marketing Carrier on-time files for the five hubs, **January 2018 to December 2023**, plus 2024 to August 2026 as already ingested. Flights with an origin or destination at ATL, CLT, DEN, DFW or ORD. The airline is the **marketing carrier**.
- **Pandemic months** March 2020 to June 2021 are excluded, as in `PREREGISTRATION_V6_BACKCAST.md`.
- **Y1, cancellations.** Among cancelled flights with a BTS cancellation code of carrier, weather or national air system (A, B, C), the share coded **carrier (A)**, by airline and month.
- **Y2, long delays.** Among flights that arrived 180 minutes or more late, the share of the delay minutes that BTS attributes to **carrier delay**, out of carrier, weather, national air system, security and late-arriving aircraft minutes, by airline and month.
- **Units.** An airline-month is used only if it has at least 200 flights in the denominator of that outcome.

## 5. Adjusting for what objectively happened

A fall in the carrier-coded share could be a better-run airline or a stormier month. Conditions the airline does not write:

- **Weather at the hub** from ASOS: the share of the month's flight-hours with thunder, snow, freezing weather, visibility under one mile, or wind of 25 knots or gust of 35 knots (the flags of `mcp.ingest`).
- **FAA traffic-management programs:** the share of flight-hours at the hub under an FAA ground stop or ground delay program with a non-airline cause, from the FAA ATCSCC advisories database. If the advisories cannot be parsed to the standard of the gate in the plan (90 of 100 hand-checked programs), this covariate is dropped and the analysis uses weather only. That fallback is fixed now.

## 6. Model

For each outcome, a weighted least squares regression on the airline-month panel (weights are the denominators), outcome as the share:

`share = airline effect + month-of-year effects + b1·weather + b2·FAA programs + c·post`

where `post` is 1 from the break month on. The coefficient of interest is `c`, in percentage points. Intervals come from a bootstrap over calendar quarters (resampling quarters of all airlines together), 2,000 draws, seed 0.

- **Primary reading:** `c` for the committing group pooled, within airline (airline effects), Y1 and Y2 reported separately.
- **Secondary reading:** a difference-in-differences with the committing group against Frontier, `c·post·committing`, reported with the warning that it rests on one comparison airline.
- **Placebo, fixed now:** the same primary model on January 2018 to February 2020 with a fake break on **1 September 2019**.

## 7. Expectations (falsifiable; each is reported, pass or fail)

| # | Expectation | Rule | If it fails |
| --- | --- | --- | --- |
| C1 | **The test has no trend of its own.** The placebo estimate of `c` for Y1 and for Y2 is within ± 3 percentage points | Both estimates inside ± 3 points | The design finds breaks that are not there, and no result below is read as an effect |
| C2 | **No material fall in the carrier-coded share after the break.** The primary estimate of `c`, pooled over committing airlines, is above −3 percentage points for Y1 and for Y2 | Both estimates greater than −3.0 points | Airlines moved their coding, and the gap cover's claims are under-estimated by the amount below |

**Materiality, fixed now.** The cover pays on the share not coded to the airline. A fall of `d` points in the carrier-coded share raises the paid share from `s` to `s + d`. At the strict reading of 5A, where about 72.5% of misses are in the gap, a fall of 3 points raises claims by 3 ÷ 72.5, which is **4.1%**, before any change in what the airline codes as late aircraft. The write-up reports the estimated fall and this conversion, whichever the sign.

If C1 fails, C2 is reported as not gradable and left pending. The sensitivity breaks, the difference-in-differences and each airline's own estimate are reported without expectation.

## 8. Not allowed after the read

Changing the break date, the airline groups, the outcomes, the thresholds, the covariates, the model, the pandemic months, the bootstrap or the materiality rule. A bug may be fixed only with the numbers before and after, in `VALIDATION.md` Part 7.

## 9. What this cannot show

Why a code changed, only that the share did, conditional on the weather and FAA programs recorded. Whether the carrier-coded share of one kind of flight stands for another. Coding by late-arriving aircraft, which BTS does not explain. Whether a launched cover would need a second source for cause (it would, if C2 fails).
