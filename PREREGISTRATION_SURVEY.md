# Pre-registration: the stated-demand survey for the gap cover

Written **9 November 2026**, before any respondent has seen a question. It has its own tag, `prereg-survey`. It fixes the instrument, the exclusions, the analysis and the decision rule, so none of them can be chosen after the answers are in.

## 1. What is being measured

Whether travellers say they would buy the gap cover (it pays a hotel-and-meals amount when a missed connection leaves them stuck overnight and the airline will not pay for it), at prices set as multiples of the model price. It is a **stated** demand: a survey cannot show what people buy. Stated intent overstates purchase, so the result is read as an **upper bound** on attach. It can rule the cover out at a given need; it cannot prove demand.

| Artefact | SHA-256 |
| --- | --- |
| `docs/survey-instrument.md` (the questions, the checks and the decision rule; Unix line endings) | `7f48c90714a2b8d9d304d1fb989a6413dbf2ef0950ea991f1ddf04a8e5b26c9d` |
| `docs/survey-question-bank.csv` (all 72 questions with their dollar prices; Unix line endings) | `62c8f59be2fa971d0aa4cf6cb208e0847d99ba72379910afa79cb83b758bea60` |

The analysis code is the tagged `src/mcp/survey.py` (`analyse_responses`), checked on simulated respondents with planted answers (`tests/test_survey.py`).

## 2. The design, fixed

- **Respondents:** US adults who have taken a domestic flight with a connection in the last 12 months; no one who works in travel, insurance or market research.
- **Each respondent sees** one of six connections and one of two wordings, both assigned at random, then the cover at the six multiples (0.5×, 0.8×, 1.0×, 1.25×, 1.5×, 2×) of the model price, in a random order, with a four-point answer scale ("Definitely would" to "Definitely would not").
- **Sample:** field until **400 respondents have passed the checks**, which gives about ±5 points on a share at the worst case. At most 800 are collected in total. There is no interim analysis: nobody looks at answers before the 400 clean respondents exist.
- **Pilot:** up to 20 respondents may be used to check wording and timing. Their answers are **excluded** from the analysis. If the instrument changes after the pilot, the changed files get a new hash and a new tag before the main fielding.

## 3. Exclusions (the only ones)

1. Fail the attention check.
2. Finish in less than a third of the median completion time.

Nobody else is dropped. Respondents whose answers are inconsistent (yes at a higher price, no at a lower one) are **kept** and their share is reported.

## 4. The analysis, fixed

- **Primary outcome:** the share who would *definitely* buy at 1.0× the model price, with a 95% interval from resampling respondents.
- **Also reported:** the share who would definitely *or probably* buy (the upper bound), both demand curves at all six prices made non-increasing, the elasticity of stated demand, the revenue index, and the share at 1.0× by wording.
- **Decision scenarios:** for each need in **1%, 3% and 10%**, the cover is **ruled out** at that need if the upper end of the 95% interval for the "definitely or probably" share at 1.0× is below it. All three are reported, whatever the result; none is chosen afterwards.

**No prediction of the share is made.** Public data gives no basis for one, and a number written to be hit would only look like rigour. What is fixed is what each result will mean.

## 5. What will be published

`results/survey_results.json`, a new Part in `VALIDATION.md` with the numbers as they are, and an update to the README's limits table, in one commit, **whether the cover is ruled out or not**. A result that rules the cover out at 3% or 10% is reported as prominently as one that does not.

## 6. Not allowed after the first answer arrives

Changing the prices or multiples, the six connections, either wording, the exclusions, the definition of the two levels, the decision scenarios, the sample target, or the analysis code.

## 7. People and data

No identifier is collected: the panel supplies an anonymous respondent code and handles payment. Respondents see a short consent text before the first question and may stop at any time. No employer's data, names or figures are used anywhere in the instrument or the analysis.

## 8. What this does not show

- What people buy: the experiment measures that (`docs/experiment-plan.md`).
- Representativeness: an online panel is not travellers at the moment of booking.
- Anything about claims or hidden risk among buyers.
- Wordings other than the two tested.
