# Addendum to the pre-registration: the monthly job's alert rule

Written **8 November 2026**, after the tagged `PREREGISTRATION_2026H2.md` and, like it, **before any data from the window exists** (the BTS files for September to December 2026 were still unpublished). The original is not edited; this is a separate dated file with its own tag, `prereg-2026h2-addendum`.

## Why

The monthly job's first alert bands (overall ±10%, per hub ±20%, judged on one month) were chosen by hand. A dry run over 2026 showed they fire most months: **5 of 8** months said "recalibrate" and **15 of 40** hub-months were flagged (`VALIDATION.md` 4G). The bands were not retuned to look calmer; they were replaced by a rule derived from data that predates 2026.

## The rule (frozen)

Alert when the realized ÷ expected claims over the **last 3 months** (summed claims over summed expected claims, not an average of ratios) is outside **1 ± z × σ / √3**, with z = 2:

| Level | σ (from 2025) | Band |
| --- | --- | --- |
| Overall | 0.119 (6 monthly ratios) | 1 ± 0.137 |
| One hub | 0.267 (30 hub-months) | 1 ± 0.308 |

σ is measured on the 2025 walk-forward only: the GBM fitted through March 2025, each month July to December priced from earlier months, using the policy v2 chose. **Nothing from 2026 entered the derivation** (`python -m mcp.bands`). The weekly pause rule is unchanged.

| Artefact | SHA-256 |
| --- | --- |
| `config/monitoring.yaml` (Unix line endings) | `bcf4e048667062782b8acfbd13c862e87fc8cf1d342d9b053fcee8426f2a70c7` |

The first check in September uses the saved reports for June to August 2026 in `results/monitor/`.

## Limits stated up front

- **Not blind.** The author had already seen the 2026 monthly spread (about 0.15) before writing this rule. The numbers come from 2025 only, but the design decision was not made in ignorance.
- **Six months and thirty hub-months** is a small sample for a standard deviation.
- **The √3 scaling assumes independent months.** They are not quite, so the true false-alarm rate is higher than the nominal 4.6% per check.
- **It is slow on purpose, and that costs sensitivity.** The hub band is wide: the persistent hub gaps of 12 to 16% found in the validation sit inside it and would not alert. The rule catches large shifts, not steady small ones. A cumulative rule or a hub-level recalibration would be needed for those.

## Orientation: how it behaves on 2026 (a consistency check on spent data, not a validation)

On the dry replay of January to August 2026, the first two months have no three-month history. Of the 6 months checked, the overall rule alerted **0** times, and the hub rule alerted **1** time in 30 hub checks (Chicago, April). The old single-month bands, on the same data, alerted in 5 of 8 months and 15 of 40 hub-months.

## Expectations for September to December 2026

Each is falsifiable; a failure is reported in the same commit as the result.

| # | Expectation | If it fails |
| --- | --- | --- |
| A1 | The overall rule says "recalibrate" in **at most 1** of the evaluated months (nominal false alarms would be about 0.2 in four) | The band is too tight, or the level is moving more than 2025 suggested; both are reported, and the rule is not retuned on the same data |
| A2 | The hub rule alerts in **at most 2** of the hub checks (5 hubs × the months evaluated; nominal about 0.9 in 20) | Same |
| A3 | The **old** single-month rule (±10% overall) says "recalibrate" in **at least half** of the evaluated months | The claim that the old bands were too jumpy is withdrawn |

**Not allowed after reading:** changing the rule, σ, z, the window, the tolerances above, or the history it starts from.

## Procedure

Run only after the pre-registered evaluation of the original document has been read:

```bash
cd src
python -m mcp.monitor --replay 2026-09 2026-12 --accept-preregistration --dry     # --dry: the frozen state is not overwritten
python -m mcp.monitor --replay 2026-09 2026-12 --accept-preregistration --dry --legacy-bands   # for A3
```

(Months not yet published are simply left out; the evaluation covers the months that exist at the time of the first read.)
