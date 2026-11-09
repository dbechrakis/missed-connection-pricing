# Pre-registration: v4, the loaded gap cover, on September to November 2026

Written **9 November 2026**, when the BTS files for September to December 2026 did not exist yet (a request for the September file returned HTTP 404 on that day, just before this was tagged). This is a separate dated document. `PREREGISTRATION_2026H2.md`, its addendum and `PREREGISTRATION_2026H2_V3.md` are not edited. It has its own tag, `prereg-2026h2-v4`.

## 1. What is being tested

v4 is **not a new model**. It is the frozen v3 gap model (`models/pmiss_v3.joblib`, no recalibration) with one number added to the price: a **loading of 1.16** on the premium.

**Why.** In development the cover as it would be sold, only where its price is within 5% of the fare, ran a 75% loss ratio against a 65% target over 26 months, and lost money in 6 of them. The cap lets through the connections the model rates safest, which are partly the ones it under-rates. A loading raises the price and also changes which connections pass the cap, so it is a fixed point: the smallest factor at which the connections that pass the cap *at that factor* realize the target loss ratio.

**How the number was set.** `mcp.v3_loading`: on a rolling-origin backtest of 26 months (July 2024 to August 2026, each month priced by a model that had not seen it), the smallest loading in 1.00 to 2.00 (steps of 0.01) at which the offered connections realize 65%. It is **1.16**. It is fitted on development months only.

| Artefact | SHA-256 |
| --- | --- |
| `models/pmiss_v3.joblib` (the model; unchanged since the v3 pre-registration) | `339d3ad170cb2b67bd785533efed934beaf106b75b862844e6313ac4950c9107` |
| `models/v4_loading.json` (the loading, its rule and its data; Unix line endings) | `2ea5971c495f8342da082f91001dc826dabe4eb4f5a83066ce0292309e1fbd9a` |
| `results/gsa_costs.json` (hotel and meals rates; unchanged) | `e5b4f02f9c5b6e15d2e5e0abcbb9dca45eab074c340b0a08edb580af2b01c939` |

The code that will run is the tagged `src/mcp/holdout_v4.py`, which prices every connection twice, at the v3 price (loading 1) and at the v4 price (1.16), and judges each on the connections that pass the 5% cap at its own price, over the same months.

## 2. Everything seen before this was written

This document is not blind. Before writing it the author had seen:

1. **The v3 development results** (`VALIDATION.md` 5E to 5J): the frozen model on March to August 2026, a refit bootstrap, and a 26-month rolling-origin backtest.
2. **The loading's out-of-sample behaviour.** Fitted only on months before each test month, with the one-month booking lag the cover would have, it moved the sold loss ratio from **77.8% to 70.4%** over 19 months (February 2025 to August 2026), with months above 100% going from 4 to 3 and the share sold from 40.7% to 36.1%. It did **not** reach 65%.
3. **Windows for fitting.** Fitting on the last 12, 9 or 6 months instead of all history gave 69.6%, 72.2% and 70.2%. The difference is noise, so the simplest rule (all history) was kept; this was a choice among four.
4. **The frozen number itself** (1.16) is fitted on all 26 months, which include the 2026 months already seen. At that value the pooled sold loss ratio on those 26 months is **64.8%, by construction**. That figure is not evidence.
5. **A different value on a different window.** On the frozen v3 model's own months (March to August 2026) the same rule gives 1.21. It is a summer-heavy window.
6. **The seasonal figures this test will be judged against** (section 3), read from the same development months.
7. **A sensitivity to how travellers choose** (`mcp.v3_mix`): across five stylised mixes the sold loss ratio stays between 72.5% and 74.6%, above target in every one; the share sold ranges from 9% to 67%.

## 3. The warning that matters most: this window is the calm season

September to November is the **calmest** part of the year in the development data. Priced at the v3 price the cover ran **38.3%** (2024) and **45.0%** (2025) in those months, against 74.6% across all 26 months. At the v4 price: **34.3%** and **38.1%**. So a result below 65% in this window says almost nothing about summer, when the cover's losses concentrate. **Passing this test does not show the loading fixes the product.** It shows the arithmetic works in a calm season. The summer test is a year away.

The power is also low. Over three months the standard deviation of a monthly loss ratio (0.23) gives a standard error near 0.13, so three months cannot tell 65% from 75%. The bands below are wide on purpose.

## 4. Expectations (falsifiable; each result is reported, pass or fail)

*Months read* are those published at the time of the first read (September to November, `python -m mcp.holdout_v4 9 10 11`).

| # | Expectation | Basis in development | If it fails |
| --- | --- | --- | --- |
| L1 | **Direction.** The v4 pooled sold loss ratio is lower than the v3 one by **at least 3.0 points**, and lower in every month read | Lower in all 24 three-month blocks, by 4.0 points at least and 9.6 on average; in September to November by 4.0 (2024) and 6.9 (2025) | The loading does not do what it was built to do in a calm season; reported, not retuned |
| L2 | **Level.** The v4 pooled sold loss ratio is between **25% and 55%** | 34.3% (2024) and 38.1% (2025) in the same months | Above 55%: the model drifted or the level moved; below 25%: the cover is priced too dear for a calm season |
| L3 | **Reach.** The v4 share sold is between **28% and 42%** in each month read | Monthly 31.7% to 40.6% over 26 months; 36.7% and 34.2% in September to November | The mix or the fares moved; the loading is not the cause |
| L4 | **Weeks.** **At most one week** above a 100% loss ratio under v4 among the weeks read | None of the 27 weeks of September to November 2024 and 2025 was above 100% (worst 86% and 61%) | More than one: calm-season risk is larger than development showed |

L4 is deliberately a calm-season prediction. Over all 26 months the loading leaves 17 of 114 weeks (15%) above 100%, so it does **not** remove bad weeks; they happen in summer. The product's volatility is a matter for an exposure cap or reinsurance, not for the price.

**Not allowed after reading:** changing the model, the loading (1.16), its rule, the cap, the target loss ratio, the bands above, the months, or the sensitivity values. A sensitivity table at loadings 1.00, 1.10, 1.16, 1.21 and 1.30 is reported alongside, for information.

## 5. Procedure

Run only after the v3 test of `PREREGISTRATION_2026H2_V3.md` has been read and reported:

```bash
cd src
export MCP_VARIANT=v3
python -m mcp.ingest --start 2026-09 --end 2026-11                    # whichever months exist (BTS Marketing Carrier On-Time)
python -m mcp.connections --start 2026-09 --end 2026-11 --quiet --weighted
python -m mcp.pricing --full-severity                                 # severity_full_v3, now including the new flights
python -m mcp.holdout_v4 9 10 11
```

Output: `results/holdout_v4_next.json`. The first read is planned for when November 2026 is published (probably early February 2027), decided before any of the data exists (`docs/decisions.md`).

## 6. What this does not test

- Summer, and any season other than autumn.
- Demand, and whether travellers would buy at these prices (`docs/experiment-plan.md`).
- The minimum connection time, the onward-cancellation trigger and the per-airline hotel commitments (`VALIDATION.md` 5G and 5H); the test uses the single rule of v3.
- Whether a different loading rule (by price band, by hub) would do better. Only a single factor was tried.
