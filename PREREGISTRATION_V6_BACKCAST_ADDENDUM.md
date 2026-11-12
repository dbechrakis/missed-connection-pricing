# Addendum 1 to the v6 backcast pre-registration: two expectations that could not be graded, and the self-transfer rules

Written **12 November 2026**, before any BTS on-time file for a month earlier than January 2024 has been downloaded, and so before any outcome of the backcast exists. It amends `PREREGISTRATION_V6_BACKCAST.md`, which is not edited. Where the two differ, this document governs. The commit that adds it is pushed to GitHub before the first on-time download, and a tag marks it (`prereg-v6-backcast-addendum`). Drafted by Claude for the author.

## 1. What was wrong

The backcast pre-registration (section 9) tests `local_season` in B6 and B7 "over the months where it is active, at least 48 known months". Counting before any data was loaded, that cannot happen. The monthly ratio series starts in January 2019, because 2018 is used only to fit the first model and has no priced outcomes. After the pandemic months are removed (16 of 60) it has **44** observed months, so `local_season` never has 48. B6 and B7 would have been ungradable, and a test that cannot be graded would have been quietly dropped.

Found by the author on 12 November 2026 while writing `mcp.backcast`, before any 2018 to 2023 on-time file was downloaded. The DB1B and ASOS files for those years had been downloaded (they carry no outcome of a connection).

## 2. The change

- **The level model under test in B6 and B7 is `local`**, the local-level model of `mcp.level` without a seasonal term, on the pooled monthly series. `local_season` is still computed and reported, with the months in which it was active (none are expected), and is not graded.
- **B6.** Over the months that have a forecast from all three candidates, the CRPS of `local` is below that of `none` and below that of `last12`. Both comparisons.
- **B7.** The 90% predictive intervals of `local`, over the same months: the number of months inside the interval lies in the central 95% exact binomial range for `n` months at p = 0.90.
| # | Expectation | Rule | If it fails |
| --- | --- | --- | --- |
| B6 | **Following the level pays.** The CRPS of `local` on the pooled monthly series is below that of `none` and of `last12`, over the months with a forecast | Both comparisons | A moving level cannot be told from noise at this length, and v6 keeps `none` plus a loading |
| B7 | **Intervals.** The 90% predictive intervals of `local` over the same months | The number of months inside lies in the central 95% exact binomial range for `n` months at p = 0.90 | The intervals are miscalibrated |

- **The months.** A month has a forecast when at least six non-pandemic months are known at lag 2 (months up to two earlier, pandemic months skipped). About 37 of the 44 months qualify.
- **Pandemic months in the level model.** They are missing observations. The model sees the non-pandemic months in order, as a series without the gap, and the lag is counted in calendar months.
- **What follows.** If B6 passes, v6 uses the `local` level. If it fails, v6 uses no level model and keeps a loading refitted on earlier months. Season effects wait for more years.

Development evidence is unchanged and unfavourable to this test: on 19 forecast months `local` did not beat `none` (`VALIDATION.md` 7A). A pass would be informative.

## 3. The rules that section 4 of the pre-registration left open for B5 and B8

- **B5 (the loading).** The fixed-point loading of `mcp.v3_loading` refitted each month from earlier non-pandemic months only, with the one-month booking lag and at least six months of history. It is scored on the months that have it, and the unloaded sold loss ratio is pooled over the **same** months.
- **B8 (self-transfers).** Pairings and prices as v5. For a month m the table is fitted on non-pandemic months up to m − 5, and a month is scored when at least six such months exist. The loaded price is the same table times a loading re-estimated for each month from the earlier scored months only (at least three months, the pooled realized ÷ expected of those months), so the first three scored months have no loading and are left out of the comparison on both sides. B8 compares the pooled ratio over the months that have both.
- **Weights for self-transfers** are none (every pairing counts once, as v5). **Fares** are the DB1B nonstop one-way fares of the previous calendar year, passenger-weighted, as the gap cover's weights.

## 4. Not allowed after the read

As in section 8 of the pre-registration. In particular the choice of `local` here cannot be replaced by `local_season` or any other candidate after seeing results.
