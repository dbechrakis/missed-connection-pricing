# Pre-registration: the next test window (September to December 2026)

Written **8 November 2026**. This file is committed and given the tag `prereg-2026h2` **before the data it tests exists**, so the tag's date on GitHub is evidence independent of the author's own commit times (an earlier review pointed out that the previous protocols reached GitHub together with their results).

**The data does not exist yet.** At 12:56 UTC on 8 November 2026 the BTS download addresses for the On-Time files of September, October, November and December 2026 all returned "not found" (the latest published month is August 2026). Nothing from the window has been read, scored or looked at.

## 1. What is frozen

| Artefact | SHA-256 |
| --- | --- |
| `models/pmiss.joblib` (v1: GBM + isotonic calibrator, unchanged since the first protocol) | `e5094792b7f758dd2226d67a7afbc77a247807d097ebcdb1a860846f666f5870` |
| `models/pmiss_v2.joblib` (v2 GBM fitted on Jan 2024 to Sep 2025, calibration statistics Oct to Dec 2025) | `ecee867eb5dfc930c7571722d1797fd0ba47ed7555cfb4d01d3e0a45e74b90a8` |
| `models/v2_state.json` (monthly calibration statistics for Oct 2025 to Aug 2026, built by `python -m mcp.monitor --replay 2026-01 2026-08`) | `429b61b13c995cbb2da295d7b4ca5c26cf16033768cccd83de3d2c94b75568a4` |
| `config/pricing.yaml` (costs, loss ratio, price cap; Unix line endings, see `VALIDATION.md` 4I) | `75e1db9fda3e188955a0201ea9a29ae317c88deec5619395cfe2bfd89a9e8979` |
| `config/guards.yaml` (price floor) | `73290140ff591db67a0c9fac013f49122737d6d72e076fb9aae0b05a474383df` |
| Code | the commit the tag `prereg-2026h2` points to |

DB1B route weights stay the six train quarters (no later quarter is published). Route statistics for v1 stay those of 2024, for v2 those of Jan 2024 to Sep 2025. Nothing is refitted.

## 2. What is tested and how it is read

**Window.** Connections whose outbound flight is scheduled from 1 September to 31 December 2026 (`split.WINDOWS["NEXT"]`).

**One read, no optional stopping.** The first evaluation is run once, when at least September to November have been published, on every month published at that moment. If December is not yet published, one further and final evaluation of the full window may be run once it is, and both are reported. No other re-read is allowed, except to fix a bug, which must be written up with the numbers before and after.

**Prices compared on every connection** (`python -m mcp.holdout --next`):

1. the 2024 baseline (hub × connection time);
2. v1 uncalibrated; 3. **v1 as shipped**;
4. v2 static (calibrator from Oct to Dec 2025 only, nothing later);
5. v2 rolling with no lag;
6. **v2 rolling with a one-month lag** (calibrator from months up to two months before; the version a booking lead allows). This is the product for the offered subset and the purchase weights.

**Headline metric.** Realized ÷ target loss ratio (target 65%) at θ = 0 for price 6, with the weekly block-bootstrap interval. Reported alongside it: the same for price 3, and a monthly t-interval for both (the review showed the bootstrap alone is a little narrow).

**Also reported, as before:** the θ curve against flat prices; by hub; Brier, log loss and ECE; predicted against observed by connection time and by month; the offered subset; coverage of connections by DB1B weights. The adverse-selection simulation (hidden risk) cannot be tested on this data and is not.

## 3. Expectations, written before the data exists

Each is falsifiable. Where one fails, the matching claim in the README is withdrawn or qualified, in the same commit that reports the result.

| # | Expectation | If it fails |
| --- | --- | --- |
| E1 | Both **v1 as shipped** and **v2 rolling, one-month lag** land within 15% of the target: realized ÷ target between 0.85 and 1.15 | The README's "within about 7% of target" is withdrawn and the headline is restated at the new value |
| E2 | v2 rolling (one-month lag) has lower ECE than v1 as shipped, and a Brier score no worse | The claim that monthly recalibration improves calibration is dropped |
| E3 | The hub ordering persists for both prices: Chicago (ORD) above 1, Charlotte (CLT) and Dallas (DFW) below 1 | The "hub ordering persists" statement is withdrawn; hub-level pricing is reported as unstable |
| E4 | A flat training-average price at θ = 1 runs at least 1.5× the target, while per-connection pricing at θ = 1 stays within 0.10 of its own θ = 0 value | The "tiering is robust to selection on visible risk" statement is withdrawn |
| E5 | v2 static is further from 1 than v2 rolling (one-month lag) | The claim that re-fitting monthly is what rescues v2 is dropped |
| E6 | **No prediction** which of v1 and v2 has the better headline ratio. Both are consistent with the earlier results | Nothing to withdraw; reported either way |

**Not allowed after reading:** changing the models, the state, the configs, the window, the metric, the tolerances above, or the θ grid.

## 4. Procedure

```bash
cd src
python -m mcp.ingest --start 2026-09 --end 2026-12                    # whichever months exist (BTS On-Time)
python -m mcp.connections --start 2026-09 --end 2026-12 --quiet --weighted   # counts only, never outcome rates
python -m mcp.pricing --full-severity                                 # severity table that includes the new flights
python -m mcp.holdout --next 9 10 11                                  # the months published at the time of the first read
```

Until that last command, nothing may score or summarise these months, including the monthly job (`mcp.monitor` refuses September 2026 onward without an explicit flag).

## 5. What this does not test

Demand, willingness to pay, and buyers' private information (they need an experiment); seat availability; connections between airlines; airports beyond the five hubs. The frozen models carry the limits stated in the README.
