# Scoreboard: every pre-registered prediction and how it turned out

Each prediction was written, hashed and tagged **before** its data existed, so each is judged by the rule it was written with. Nothing here is edited by hand once a result is in: `python -m mcp.grade` grades from the result files with thresholds copied from the documents (`src/mcp/grade.py`), except E1 to E6, A1 to A3, B9, B10 and the sizes of F3, which their documents say are graded by hand.

**17 of 58 graded.** v5 (S1 to S5) was read on 9 November 2026. The rows read when November 2026 is published (probably early February 2027) include v5.1 (R1 to R5). v5.2 (W1 to W5) is read when February 2027 is published (probably early May 2027). Every date was decided before the data exists. The backcast (B1 to B10) and the coding audit (C1, C2) are read once, after the 2018 to 2023 months are ingested, and are pending until then. The seasonal price (G1 to G4, H1 to H4) is read when May 2027 and August 2027 are published (probably August and November 2027). Q1 is graded from the same file as V1 to V6.

| # | Prediction | Document (tag) | Status | Result |
| --- | --- | --- | --- | --- |
| E1 | Both v1 as shipped and v2 rolling land within 15% of target (0.85 to 1.15) | [prereg-2026h2](PREREGISTRATION_2026H2.md) | pending |  |
| E2 | v2 rolling has lower calibration error than v1, and a Brier score no worse | [prereg-2026h2](PREREGISTRATION_2026H2.md) | pending |  |
| E3 | Hub ordering persists: Chicago above 1, Charlotte and Dallas below 1 | [prereg-2026h2](PREREGISTRATION_2026H2.md) | pending |  |
| E4 | A flat price at θ = 1 runs at least 1.5× target; per-connection pricing stays within 0.10 of its θ = 0 value | [prereg-2026h2](PREREGISTRATION_2026H2.md) | pending |  |
| E5 | v2 static is further from 1 than v2 rolling | [prereg-2026h2](PREREGISTRATION_2026H2.md) | pending |  |
| E6 | No prediction which of v1 and v2 has the better headline (reported either way) | [prereg-2026h2](PREREGISTRATION_2026H2.md) | pending |  |
| A1 | The monthly job's overall rule says "recalibrate" in at most 1 evaluated month | [prereg-2026h2-addendum](PREREGISTRATION_2026H2_ADDENDUM.md) | pending |  |
| A2 | The hub rule alerts in at most 2 hub checks | [prereg-2026h2-addendum](PREREGISTRATION_2026H2_ADDENDUM.md) | pending |  |
| A3 | The old single-month rule says "recalibrate" in at least half of the months | [prereg-2026h2-addendum](PREREGISTRATION_2026H2_ADDENDUM.md) | pending |  |
| V1 | v3 gap cover priced within 1 ± 2σ/√n of expected claims (σ = 0.197) | [prereg-2026h2-v3](PREREGISTRATION_2026H2_V3.md) | pending |  |
| V2 | No single month above 1.54 times expected claims (a loss ratio of 100%) | [prereg-2026h2-v3](PREREGISTRATION_2026H2_V3.md) | pending |  |
| V3 | Connections offered within the 5% cap run worse than all overnight-risk connections | [prereg-2026h2-v3](PREREGISTRATION_2026H2_V3.md) | pending |  |
| V4 | Per-hub calibration narrows the worst hub deviation | [prereg-2026h2-v3](PREREGISTRATION_2026H2_V3.md) | pending |  |
| V5 | 70% to 90% of overnight misses are in the gap (not coded to the airline) | [prereg-2026h2-v3](PREREGISTRATION_2026H2_V3.md) | pending |  |
| V6 | 25% to 55% of overnight-risk connections priced within the cap | [prereg-2026h2-v3](PREREGISTRATION_2026H2_V3.md) | pending |  |
| L1 | The 1.16 loading lowers the sold loss ratio by at least 3.0 points, in every month | [prereg-2026h2-v4](PREREGISTRATION_2026H2_V4.md) | pending |  |
| L2 | The loaded sold loss ratio is between 25% and 55% (a calm season) | [prereg-2026h2-v4](PREREGISTRATION_2026H2_V4.md) | pending |  |
| L3 | The loaded share sold is between 28% and 42% in each month | [prereg-2026h2-v4](PREREGISTRATION_2026H2_V4.md) | pending |  |
| L4 | At most one week above a 100% loss ratio under the loading | [prereg-2026h2-v4](PREREGISTRATION_2026H2_V4.md) | pending |  |
| S1 | v5 self-transfer cover priced within 0.85 to 1.15 of its payout on January to August 2026 | [prereg-v5-self-transfer](PREREGISTRATION_V5_SELF_TRANSFER.md) | **failed** | realized/target 1.159 [1.05, 1.28] against 0.85 to 1.15 |
| S2 | Inbound cancellations and diversions are 20% to 50% of misses | [prereg-v5-self-transfer](PREREGISTRATION_V5_SELF_TRANSFER.md) | **passed** | 25.0% of misses after a cancellation or diversion |
| S3 | At every hub the 90 to 104 minute miss rate is above the 165 to 179 minute rate | [prereg-v5-self-transfer](PREREGISTRATION_V5_SELF_TRANSFER.md) | **passed** | miss rate 90 to 104 min against 165 to 179 min: ATL 26.2%/6.4%, ORD 27.2%/8.1%, DFW 25.3%/6.6%, DEN 24.8%/5.0%, CLT 23.6%/5.6% |
| S4 | The standard deviation of the eight monthly ratios is 0.08 to 0.35 | [prereg-v5-self-transfer](PREREGISTRATION_V5_SELF_TRANSFER.md) | **passed** | monthly sd 0.17 |
| S5 | Pairings offered within the 10% cap run worse than all pairings | [prereg-v5-self-transfer](PREREGISTRATION_V5_SELF_TRANSFER.md) | **passed** | within the 10% cap 1.175, all 1.159 |
| R1 | v5.1 self-transfer cover priced within 0.85 to 1.15 of its payout on September to November 2026 | [prereg-v5-1-level](PREREGISTRATION_V5_1_LEVEL.md) | pending |  |
| R2 | v5.1 is closer to 1 than the frozen v5 table on the same pairings | [prereg-v5-1-level](PREREGISTRATION_V5_1_LEVEL.md) | pending |  |
| R3 | No month above 1.54 (a 100% loss ratio) | [prereg-v5-1-level](PREREGISTRATION_V5_1_LEVEL.md) | pending |  |
| R4 | Inbound cancellations and diversions are 20% to 50% of misses | [prereg-v5-1-level](PREREGISTRATION_V5_1_LEVEL.md) | pending |  |
| R5 | Long gaps (150 to 300 minutes) within 0.15 of short gaps (90 to 149) | [prereg-v5-1-level](PREREGISTRATION_V5_1_LEVEL.md) | pending |  |
| W1 | v5.2 loaded self-transfer cover within 0.85 to 1.15 of its payout on December 2026 to February 2027 | [prereg-v5-2-loading](PREREGISTRATION_V5_2_LOADING.md) | pending |  |
| W2 | The loading is closer to 1 than the same table unloaded | [prereg-v5-2-loading](PREREGISTRATION_V5_2_LOADING.md) | pending |  |
| W3 | No month above 1.54 loaded (a 100% loss ratio) | [prereg-v5-2-loading](PREREGISTRATION_V5_2_LOADING.md) | pending |  |
| W4 | 65% to 85% of pairings fit the 10% cap at the loaded price, every month | [prereg-v5-2-loading](PREREGISTRATION_V5_2_LOADING.md) | pending |  |
| W5 | Inbound cancellations and diversions are 20% to 50% of misses | [prereg-v5-2-loading](PREREGISTRATION_V5_2_LOADING.md) | pending |  |
| B1 | Gap cover priced within 1 ± 2σ/√n_eff of expected claims on 2019 to 2023, outside the pandemic (σ = 0.241, ρ = 0.70) | [prereg-v6-backcast](PREREGISTRATION_V6_BACKCAST.md) | **passed** | 0.964 against 1 ± 0.173 (n = 44) |
| B2 | Monthly spread of the realized ratio between 0.19 and 0.33 | [prereg-v6-backcast](PREREGISTRATION_V6_BACKCAST.md) | **passed** | monthly sd 0.245 against 0.19 to 0.33 |
| B3 | Connections within the 5% cap run worse than all overnight-risk connections | [prereg-v6-backcast](PREREGISTRATION_V6_BACKCAST.md) | **failed** | within the cap 0.932, all 0.964 |
| B4 | 9% to 44% of months have a sold loss ratio above 100% | [prereg-v6-backcast](PREREGISTRATION_V6_BACKCAST.md) | **failed** | 2.3% of months above a 100% loss ratio as sold, against 9% to 44% |
| B5 | The refitted loading lowers the pooled sold loss ratio by at least 3.0 points | [prereg-v6-backcast](PREREGISTRATION_V6_BACKCAST.md) | **failed** | loading lowers the sold loss ratio by 2.9 points (55.7% to 52.9%) |
| B6 | local has lower CRPS than none and than last12 over the months with a forecast (replaces local_season, see the addendum) | [prereg-v6-backcast-addendum](PREREGISTRATION_V6_BACKCAST_ADDENDUM.md) | **failed** | CRPS local 0.199, none 0.156, last12 0.170 over 37 months |
| B7 | The 90% intervals of local cover within the central 95% binomial range (replaces local_season, see the addendum) | [prereg-v6-backcast-addendum](PREREGISTRATION_V6_BACKCAST_ADDENDUM.md) | **passed** | 30 of 37 months inside the 90% interval, range 29 to 36 |
| B8 | The refitted loading brings the self-transfer ratio closer to 1 | [prereg-v6-backcast](PREREGISTRATION_V6_BACKCAST.md) | **failed** | loaded 0.912, unloaded 0.981 |
| B9 | Arm A (all earlier months) against arm B (trailing 24): reported either way, no prediction | [prereg-v6-backcast](PREREGISTRATION_V6_BACKCAST.md) | pending |  |
| B10 | Largest earlier 24-month change in the 12-month level, reported next to 2024 to 2026, no prediction | [prereg-v6-backcast](PREREGISTRATION_V6_BACKCAST.md) | pending |  |
| C1 | The placebo break (September 2019) shows a change within ± 3 points for both outcomes | [prereg-v6-coding](PREREGISTRATION_V6_CODING.md) | **failed** | placebo effects Y1 +3.4, Y2 +2.7 points against ± 3 |
| C2 | No fall of 3 points or more in the carrier-coded share after the break | [prereg-v6-coding](PREREGISTRATION_V6_CODING.md) | pending |  |
| F1 | The forecast gain is larger at lead 1 than at lead 7, and under 1% at lead 7 | [prereg-v6-forecast](PREREGISTRATION_V6_FORECAST.md) | **passed** | gain at lead 1 1.05%, at lead 7 0.06% |
| F2 | The sales rule lowers the weeks above a 100% loss ratio as sold (graded only if the gate passes) | [prereg-v6-forecast](PREREGISTRATION_V6_FORECAST.md) | **passed** | weeks above 100% as sold: 14 with the rule, 15 without |
| G1 | Spring 2027: the seasonal price calibrates, within 1 ± 0.287 | [prereg-v6-forward](PREREGISTRATION_V6_FORWARD.md) | pending |  |
| G2 | Spring 2027: the season beats a constant level on absolute log error | [prereg-v6-forward](PREREGISTRATION_V6_FORWARD.md) | pending |  |
| G3 | Spring 2027: no month above a 100% loss ratio as sold at the seasonal price | [prereg-v6-forward](PREREGISTRATION_V6_FORWARD.md) | pending |  |
| G4 | Spring 2027: 20% to 55% of connections priced within the cap in every month | [prereg-v6-forward](PREREGISTRATION_V6_FORWARD.md) | pending |  |
| H1 | Summer 2027: the seasonal price calibrates, within 1 ± 0.287 | [prereg-v6-forward](PREREGISTRATION_V6_FORWARD.md) | pending |  |
| H2 | Summer 2027: the season beats a constant level on absolute log error | [prereg-v6-forward](PREREGISTRATION_V6_FORWARD.md) | pending |  |
| H3 | Summer 2027: no month above a 100% loss ratio as sold at the seasonal price | [prereg-v6-forward](PREREGISTRATION_V6_FORWARD.md) | pending |  |
| H4 | Summer 2027: 20% to 55% of connections priced within the cap in every month | [prereg-v6-forward](PREREGISTRATION_V6_FORWARD.md) | pending |  |
| Q1 | The v3 model runs 0.546 to 0.987 on September to November 2026 (the seasonal prediction) | [prereg-v6-forward](PREREGISTRATION_V6_FORWARD.md) | pending |  |
| X1 | Three timetable features add at most 0.0002 to the log loss (they do not earn a place) | [prereg-v6-schedule](PREREGISTRATION_V6_SCHEDULE.md) | **failed** | gain in log loss +0.00073 (+0.32%) against a tie band of 0.0002; two seeds differ by 0.00022 |

**How the read happens.** A weekly scheduled job on the author's machine checks that BTS has published September, October and November 2026, and only then runs the four tests once, in the pre-registered order, grades them with the rules above and commits the results to a local branch. It never pushes, never changes a model or a threshold, and never runs twice. The author reviews and publishes. v3 and v4 are judged on these three months only. For E1 to E6 and A1 to A3, `PREREGISTRATION_2026H2.md` allows one final read with December once it is published. It was decided before any of the data existed that this read will be run, once, and reported next to the first (`VALIDATION.md` 5M).

A failed prediction is reported as prominently as a passed one, in the same commit as the result. The calm-season warning in `PREREGISTRATION_2026H2_V4.md` applies: September to November is the easiest part of the year for this cover, so passing says little about summer.
