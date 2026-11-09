# Scoreboard: every pre-registered prediction and how it turned out

Each prediction was written, hashed and tagged **before** its data existed, so each is judged by the rule it was written with. Nothing here is edited by hand once a result is in: `python -m mcp.grade` grades from the result files with thresholds copied from the documents (`src/mcp/grade.py`), except E1 to E6 and A1 to A3, which their documents say are graded by hand.

**0 of 19 graded.** The first read is planned for when November 2026 is published (probably early February 2027), decided before any of the data exists. Until then every row is pending.

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

**How the read happens.** A weekly scheduled job on the author's machine checks that BTS has published September, October and November 2026, and only then runs the four tests once, in the pre-registered order, grades them with the rules above and commits the results to a local branch. It never pushes, never changes a model or a threshold, and never runs twice. The author reviews and publishes. v3 and v4 are judged on these three months only. For E1 to E6 and A1 to A3, `PREREGISTRATION_2026H2.md` allows one final read with December once it is published. It was decided before any of the data existed that this read will be run, once, and reported next to the first (`VALIDATION.md` 5M).

A failed prediction is reported as prominently as a passed one, in the same commit as the result. The calm-season warning in `PREREGISTRATION_2026H2_V4.md` applies: September to November is the easiest part of the year for this cover, so passing says little about summer.
