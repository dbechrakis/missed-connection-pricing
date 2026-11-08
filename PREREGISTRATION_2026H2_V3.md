# Pre-registration: v3, the overnight gap cover, on September to December 2026

Written **8 November 2026**, when the BTS files for September to December 2026 did not exist yet. A request for the September file (`On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2026_9.zip`) returned HTTP 404 on that day. This is a separate document from `PREREGISTRATION_2026H2.md` and its addendum. Neither of those is edited. It has its own tag, `prereg-2026h2-v3`.

## 1. What is being tested

**The product.** v3 pays the official government hotel-and-meals rate for the hub and month (GSA per diem: lodging plus meals and incidentals). It pays when all of these hold:

- the connection is missed;
- the next flight to the destination is the next day;
- BTS does **not** code the inbound problem to the airline.

Airlines already pay for hotels after overnight disruptions they caused (US DOT Airline Customer Service Dashboard). v3 pays only in the gap they leave, and every condition can be checked from public data.

**The model.** Connections are pairings within one marketing network, meaning how tickets are sold (regional flights count under the brand that sold them). The selection rule fixed for v2 picked the following, unchanged (`results/v3_selection.json`):

- the v1 feature set;
- **no recalibration** (policy `none`);
- a one-month booking lag.

The final model is trained on January 2024 to February 2026.

**Price.** Price = probability × payout ÷ 0.65 (the target loss ratio). The cover is offered only where the price is at most **5% of the average fare**, the declared cap. It is tested at 3% and 7% too.

Why 5%: comprehensive travel insurance costs about 4 to 10% of trip cost (Squaremouth sales, about 6% recently). A single-risk add-on should cost less than that.

| Artefact | SHA-256 |
| --- | --- |
| `models/pmiss_v3.joblib` | `339d3ad170cb2b67bd785533efed934beaf106b75b862844e6313ac4950c9107` |
| `models/v3_state.json` (calibration statistics, March to August 2026, Unix line endings) | `af7d9a10444bb2be5f8136b5d87b49129ccfd9e5a1ef6d3095f6d6887a91fc31` |
| `results/gsa_costs.json` (GSA rates by hub and month, Unix line endings) | `e5b4f02f9c5b6e15d2e5e0abcbb9dca45eab074c340b0a08edb580af2b01c939` |

The code that will run is the tagged `src/mcp/holdout_v3.py`.

## 2. Two arms, both declared now

| Arm | Calibration | Role |
| --- | --- | --- |
| `primary` | none (the rule's pick) | The headline |
| `hub_level` | per-hub level over the last 6 known months | A declared second arm. It was within the rule's own tolerance (log loss +0.0002) and lost only on the tie-break to the simpler policy. On development data it narrowed the spread between hubs (Chicago 1.32 → 1.02), so it is tested, not adopted. |

## 3. Everything that was looked at before writing this

This document is not blind, and here is what the author saw:

1. **The selection** (development, October 2025 to August 2026), run once, chose `none`. Pooled realized/target was 1.03. By hub it ran from 0.89 to 1.32.
2. **A smoke test of the test code on July and August 2026** showed 1.36. Those are spent months.
3. **A robustness check** (`scripts/v3_robustness.py`, `results/v3_robustness.json`, development data only). Neither training on overnight rows, nor a month term, nor any recalibration removed the month-to-month swings:
   - the spread of monthly ratios was 0.17 to 0.25 in every specification;
   - the worst month was 1.31 to 1.46 in every specification.

   Judged by cost-weighted log loss, the chosen model stays at the top. **The model was not changed.**
4. **A development orientation on March to August 2026** (`results/v3_dev.json`). The model is out-of-sample there, since it was trained through February. Results:
   - realized/target **1.12** [1.01, 1.23];
   - by month: 1.03, 0.84, 0.98, 1.20, 1.35, 1.37;
   - **39%** of overnight-risk connections priced within the 5% cap;
   - realized/target on that offered subset **1.22**.

## 4. Expectations (falsifiable; each result is reported, pass or fail)

*n* is the number of months evaluated at the time of the first read. **σ = 0.197** is the sample standard deviation of the 11 monthly ratios in the October 2025 to August 2026 walk-forward of the chosen specification.

| # | Expectation | Why this level | If it fails |
| --- | --- | --- | --- |
| V1 | **Calibration.** Primary pooled realized/target within **1 ± 2σ/√n** (n = 3: 0.77 to 1.23; n = 4: 0.80 to 1.20). | The size of month-to-month noise seen in development. Months are correlated, so the band is if anything too narrow. | The claim that the price is right on average over a season is withdrawn for v3. |
| V2 | **Solvency.** No single month above **1.54** (= 1 ÷ 0.65, a loss ratio of 100%). | The margin is meant to absorb weather months. The worst development month was 1.38. | The 0.65 target is too thin for a correlated weather risk, and the product needs a larger margin or reinsurance. |
| V3 | **Selection inside the cap.** Realized/target on the connections offered within the 5% cap is **higher** than on all overnight-risk connections. | Development showed 1.22 against 1.12. Choosing connections because their predicted risk is low picks up the model's under-predictions (the winner's curse). | The selection effect claimed in VALIDATION.md is withdrawn. |
| V4 | **Hub arm.** `hub_level` has a smaller worst hub deviation, max\|hub ratio − 1\|, than `primary`. | Development: 0.07 against 0.32 (selection window), and 0.21 against 0.31 (March to August). | Per-hub recalibration is dropped for v3. |
| V5 | **The premise.** The share of overnight missed connections that are in the gap (cause not coded to the airline) is between **70% and 90%**. | 80.5% over January 2024 to August 2026 (`results/causes_v3.json`); 81.9% over March to August 2026 (`results/v3_dev.json`). | If below 70%, the airline already covers most of these nights, and the gap cover's value proposition is weaker than stated. |
| V6 | **Reach.** The share of overnight-risk connections priced within the 5% cap is between **25% and 55%**. | 39% in development. | Reported. The price cap or the product scope needs revisiting. |

**Not allowed after reading:** changing the model, the state, the GSA table, the cap, the target loss ratio, σ, the bands above, the arms, or the months included.

## 5. Procedure

Run only after `PREREGISTRATION_2026H2.md` and its addendum have been read and reported:

```bash
cd src
export MCP_VARIANT=v3
python -m mcp.ingest --start 2026-09 --end 2026-12                    # whichever months exist (BTS Marketing Carrier On-Time)
python -m mcp.connections --start 2026-09 --end 2026-12 --quiet --weighted
python -m mcp.pricing --full-severity                                 # severity_full_v3, now including the new flights
python -m mcp.holdout_v3 9 10 11                                      # the months published at the time of the first read
```

The output is `results/holdout_v3_next.json`. Nothing else may score these months before the last command.

## 6. What this does not test

- Demand, and whether passengers would buy at these prices; that needs an experiment.
- Whether BTS cause coding matches what an airline would actually accept or refuse at the desk.
- Connections between different airline networks.
- Any hub beyond the five.
- Tail risk beyond four months: a single bad winter storm week can dominate a season, and four months cannot measure that.
