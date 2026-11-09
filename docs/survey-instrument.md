# A stated-demand survey for the gap cover

The [pricing experiment](experiment-plan.md) needs a live product. This survey needs only respondents, so it gives a first, cheap read of demand in weeks. It is written, with its analysis, before anyone answers (`mcp.survey`, checked on simulated respondents with planted answers).

**What it can do: kill the idea cheaply. What it cannot do: prove it.** Stated intent overstates what people actually buy. So the stated share is treated as an **upper bound** on the real attach rate. If even that upper bound is below the attach rate the economics need (`VALIDATION.md` 5J), the cover is not worth the experiment. If it is above, the survey has shown nothing more than that the experiment is not ruled out.

## Respondents

US adults who have taken a domestic flight with a connection in the last 12 months. Screen out anyone who works in travel, insurance or market research. Sample size for a share to within ±5 points is **385** at the worst case (`sample_size_share`), ±3 points is **1,068**. Plan for at least 400 who pass the checks below. No personal data is collected beyond the answers, and nothing here comes from any employer or company.

## What each respondent sees

One of six connections, assigned at random, with prices set from the model for January 2027 (the model price is chance of a gap night × the government hotel-and-meals rate ÷ 0.65):

| Connection | Scheduled gap | Fare | Payout if it happens | Model price |
| --- | --- | --- | --- | --- |
| Atlanta | 105 min | $363 | $293 | $19.61 |
| Chicago O'Hare | 120 min | $355 | $240 | $22.62 |
| Dallas–Fort Worth | 135 min | $351 | $264 | $22.39 |
| Denver | 105 min | $332 | $262 | $17.60 |
| Charlotte | 150 min | $298 | $223 | $13.93 |
| Atlanta | 150 min | $352 | $293 | $10.13 |

The cover is described in one of two wordings, assigned at random (the same two the experiment tests):

- **Benefit-led:** "Imagine you could add protection to this trip. If you miss your connection and the delay is not the airline's responsibility, you get $[payout] toward a hotel and meals."
- **Outcome-led:** "Imagine you could add protection to this trip. If a delay leaves you stuck overnight at [airport] and the airline will not pay for your hotel, you are covered for $[payout]."

## The question, six times

For each price in a **random order** of the multiples **0.5×, 0.8×, 1.0×, 1.25×, 1.5×, 2×** the model price (shown rounded to the nearest dollar):

> "Would you buy this protection for this trip at $[price]?"
> **Definitely would · Probably would · Probably would not · Definitely would not**

"Definitely would" and "probably would" are recorded as `definitely` and `probably`; the other two as `no`. A random order avoids anchoring on the first price.

## Checks fixed before fielding

- **Attention check:** one item that asks for a specific answer. Fail it and the respondent is dropped.
- **Speeders:** dropped if they finish in less than a third of the median time.
- **Inconsistent answers** (saying yes at a higher price and no at a lower one) are **kept** and counted; the demand curve is made non-increasing by pooling adjacent violators, and the share of inconsistent respondents is reported.
- No other respondent is dropped after seeing the results.

## Analysis (`mcp.survey`)

- **Primary outcome:** the share who would *definitely* buy at 1.0× the model price, with a 95% interval from resampling respondents.
- **Also reported:** the share who would definitely or probably buy (the upper bound), the demand curve at all six prices, the elasticity of stated demand (the slope of log share on log price) and the revenue index (price × share).
- **Decision rule, fixed now:** let *A* be the attach rate the agency needs (`mcp.economics`, from its own fixed cost and expense ratio). If the upper end of the interval for the "definitely or probably" share at 1.0× is below *A*, stop: real purchases are almost always fewer than stated ones. Otherwise run the experiment, which measures the actual attach rate and how it relates to the stated one.

## Why the analysis can be trusted before the data exists

`simulate_survey` generates respondents with planted willingness to pay, some inattentive. The tests check that the 95% intervals contain the planted share at each price at the rate they claim (measured 96% for the loose curve and 93% for the strict one over 60 simulated surveys), that the curve is non-increasing, that the strict level sits below the loose one, and that inattentive answers show up as a flatter curve.

## What it does not tell us

- **Revealed behaviour.** The experiment does.
- **Representativeness.** An online panel is not travellers at the moment of booking.
- **The wording of a real offer.** Only the two tested.
- **Anything about claims or adverse selection.** Buyers' hidden risk needs real buyers.
