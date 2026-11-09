# What the market says about price, demand and margin

Public data cannot test demand for this product: nobody has bought it from us. What it can do is tell us whether the two assumed numbers (the price cap and the 65% target loss ratio) sit inside the range real products live in. This note records what was found, what could be verified, and what could not. Looked up on 8 November 2026.

## Price: what comparable cover costs

| Product | Price | Source and caveat |
| --- | --- | --- |
| Comprehensive travel insurance | **4% to 10% of trip cost** | Squaremouth, as cited by [Experian](https://www.experian.com/blogs/ask-experian/average-cost-of-travel-insurance/) (2 July 2026). Verified at the page. Covers much more than a missed connection. |
| Kiwi.com Guarantee (self-transfer trips: connection protection across separate tickets) | **about 25% of the ticket** ($48.74 on a $200 fare, $159 on a $638 fare) | [The Points Guy](https://thepointsguy.com/guide/use-kiwi-book-multi-ticket-travel) (20 December 2021). Verified at the page. A different product: it rebooks or refunds the trip across separate tickets, so it covers the whole fare, not a hotel night. Four years old. |
| Policy benefits for missed connections | Capped at about $500 to $2,500 per trip | Insurer schedules of benefits, as returned by search; varies by plan. Not verified one by one. |

**What this means for the cap.** The assumed 5% sits at the low end of what travellers are offered for broader protection. That is where a single-risk add-on that pays one hotel night should be, so it is a reasonable starting point and probably conservative. It is **not** evidence that anyone would pay it: a price list shows what sellers ask, not what buyers accept. The pre-registered cap stays at 5% (sensitivities 3%, 7%); the audit adds 10%.

## Demand: what is known

- **No audited attach rate for flight disruption cover was found.** The figures that circulate are vendor claims (for example, 5% to 15% of bookings for travel insurance at checkout, from an affiliate-network blog). They are marketing, not measurement, and they are for insurance, not this product.
- The experiment in [the product brief](product-brief.md#7-the-experiment) is how attach rate, price response and self-selection get measured. Nothing here replaces it.

## Margin: what the 65% target loss ratio rests on

- **Not found.** US regulators do not publish a travel-insurance loss ratio. Travel is reported inside inland marine, and the industry association has argued against publishing one. A European regulator's thematic review compares travel claims ratios and commissions with non-life insurance overall, and finds that high commissions go with low claims ratios. Its figures sit in a chart that could not be read here, so no number is quoted.
- So 65% remains an assumption. The audit tests 55%, 65% and 75%.
- A loss ratio is not the whole margin. The 35% left over pays commission, payment fees, handling, and profit. None of those has a sourced value here.

## Cost of the payout

- The payout is the US government's per-diem for lodging plus meals and incidentals, by hub and month ([GSA](https://www.gsa.gov/travel/plan-book/per-diem-rates)). It is a public, dated figure, and it is what the government reimburses its own staff.
- It may be **below** what a stranded traveller pays near an airport on a disrupted night, when hotels fill and prices rise. That is a plausible direction, not a measurement: no source for disruption-night hotel prices was found, so neither the direction nor the size is established.

## Minimum connection time: what is public

- Minimums are set by airport, airline, connection type and sometimes terminal. [One Mile at a Time](https://onemileatatime.com/guides/airport-minimum-connection-times/) (4 January 2026) says so, and gives no US domestic hub figures.
- The one US domestic number that could be verified is American's **25 minutes** at Austin and Phoenix ([One Mile at a Time](https://onemileatatime.com/insights/american-airlines-minimum-connection-time/), 9 November 2022, updated 4 September 2024), which the author calls aggressive.
- A travel-tools blog lists per-hub figures for individual airlines (35 to 40 minutes at the hubs used here) and says they match the airline industry's own table. Its method is not stated and its figures could not be checked against any primary source, so **none of it is used**.
- Consequence: the 45 minutes assumed throughout may be longer than some real minimums, which would make the price too high, the safe direction. The real values are in an agency's booking system (`docs/agency-inputs.md`, row 1).

## Who already pays for the hotel

- The US DOT's Airline Customer Service Dashboard lists whether each airline commits to a free hotel after an overnight delay it controls. Read on 9 November 2026 ([page](https://www.transportation.gov/airconsumer/airline-customer-service-dashboard/complimentary-hotel-accommodations-any-passenger-0), saved with its reading date in `data/external/dot/hotel_commitments.json`): Alaska, Allegiant, American, Delta, Hawaiian, JetBlue, Southwest and United commit; **Frontier does not**. One of the ten rows has no carrier name in the page text and is recorded as unattributed, not guessed.
- The page's own text carries no revision date, and search results from 2022 describe a different set (for example, Allegiant as the only airline with no commitments). The dashboard changes; the saved copy is what this project used.
- What it changes in the cover: `mcp.commitments`, `VALIDATION.md` 5H.

## What the literature says about demand

No peer-reviewed study of take-up or willingness to pay for a missed-connection cover was found. Related, verified at the source:

- [Koster, Verhoef and Kroes (2011)](https://tinbergen.nl/publication/160520/travel-time-variability-and-airport-accessibility), *Transportation Research Part B* 45(10): a stated-choice experiment estimating what air travellers would pay to reduce the chance of missing a flight; the abstract calls the values "relatively high" and gives no figures.
- [Theis (2011)](https://dspace.mit.edu/handle/1721.1/66854), MIT thesis: misconnection risk as one of three things travellers weigh about a connection; in one airline's booking data up to 25% of passengers in a sample market chose a longer connection voluntarily, and connections close to the minimum are valued less.
- No open dataset of observed missed connections exists. The closest public item is an estimated 2007 itinerary dataset from the Barnhart group at Dartmouth (built from public flows and a small booking sample; later years listed as "coming soon"); commercial booking data is sold by OAG. A web search on 9 November 2026 found nothing else.

What this supports: that travellers do value protection against missing a connection, in stated choices. What it does not: any attach rate or price for this cover. The survey (`docs/survey-instrument.md`) and the experiment (`docs/experiment-plan.md`) are how that gets measured.
