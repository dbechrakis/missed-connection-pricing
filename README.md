# Missed-connection protection pricing

**The decision, in three lines** ([one-page memo](docs/decision-memo.md)):

1. **Price per connection, never one flat price.** Prices fixed before the test ran a **60.5%** loss ratio on 37.1 million unseen connections from January to August 2026 (95% interval 55.4% to 66.1%), against a 65% target. A flat price would have run 117% if buyers favour risky connections.
2. **Refuse to sell where the price is too large a share of the fare.** Under an assumed 10% price cap, fewer than half of the connections under about 60 minutes can be priced within the cap at DEN, CLT, DFW and ORD (Atlanta has no such limit). At a 5% cap that line moves to 75 to 105 minutes. It comes from the assumed cap and costs, not from the data.
3. **Airlines already pay for much of this, so the product worth building covers the gap they leave.** That is the hotel night after a weather or air-traffic disruption. It carries a correlated weather risk the margin must absorb, and is [pre-registered](PREREGISTRATION_2026H2_V3.md) on September to December 2026.

**[Try the live demo](https://dbechrakis.github.io/missed-connection-pricing/)** · [Decision memo](docs/decision-memo.md) · [Product brief](docs/product-brief.md) · [Method](docs/method.md) · [Validation](VALIDATION.md) · [Decision log](docs/decisions.md)

How much should an online travel agency charge to protect a connection, and on which connections should it not offer protection at all? This repository answers with a price table by hub, airline and connection time, and an offer rule, built only from public data, with a validation designed so the answer cannot be flattered.

## The result in three pictures

**1. The risk is real and steep.** About 21% of 45 to 59 minute connections are missed, against about 3% at 210 minutes or more. Price follows risk: about eight times as much for the tightest connections.

![Miss rate falls steeply with connection time](docs/figures/miss_by_slack.png)

**2. Pricing per connection holds up on data it never saw.** Realized ÷ target loss ratio by hub on January to August 2026 (1.0 is on target). The 2024 baseline under-prices; the two final versions land within about 7% of target overall.

![2026 holdout by hub](docs/figures/holdout_by_hub.png)

By connection time, v1 as shipped follows what happened most closely (its predictions are on average 6% from the observed rate), while v2 with monthly recalibration gets the overall level right but is about 12% off by connection time, too high for long connections ([`notebooks/02_model.py`](notebooks/02_model.py)):

![2026 holdout, predicted against observed by connection time](docs/figures/holdout_by_slack.png)

**3. Why not one price?** If buyers lean toward the connections the model already rates as risky (θ rises), a flat price drifts to 2.7× the target while the per-connection price barely moves. At θ = 0 (buyers ignore risk) a flat price is about as good. This test is deliberately generous to tiering: a calibrated model cannot lose to selection on its own probability. The harder case, buyers who know something the model does not, is simulated in the fourth picture.

![Loss ratio against buyer self-selection](docs/figures/holdout_vs_selection.png)

**4. What if buyers know more than the model?** Give every connection a hidden risk factor that buyers can see and the price cannot (spread κ, on a log scale), and let buyers favour risky connections with strength θ. Pricing per connection then runs at **exp(θκ²) × target** whatever the data (simulated on our real risk distribution to confirm), while a flat price suffers that *and* the selection on visible risk. At θ = 1: κ = 0.25 gives 1.06 (per connection) against 1.98 (flat); κ = 0.5 gives 1.27 against 2.36. κ cannot be measured from public data; the model's own errors by month and by hub put a floor of about 0.12 to 0.14 on it (about 2% exposure at θ = 1). So per-connection pricing is never worse than a flat price, but it is not immune; how exposed it is depends on something only an experiment can measure ([`mcp.selection`](src/mcp/selection.py), exploratory).

![Selection on information the price does not have](docs/figures/selection_private_info.png)

| Jan to Aug 2026, θ = 0 | Loss ratio (target 65%) | 95% interval |
| --- | --- | --- |
| 2024 baseline (hub × connection time) | 76.3% | 69.8 to 83.3 |
| **v1, frozen before 2026** | **60.5%** | 55.4 to 66.1 |
| **v2, recalibrated monthly** | **62.3%** | 56.9 to 67.8 |
| v2, calibrator frozen at December 2025 | 53.7% | 49.4 to 58.3 |
| One flat price | 68.2% | 62.6 to 74.3 |

## Round two: who already pays, and a cover for the gap (v3)

An audit of the assumptions above changed the product question ([`VALIDATION.md`](VALIDATION.md) Part 5).

- **Airlines already pay for most of what v1 insures.** US airlines commit to a hotel when an overnight disruption is their fault. BTS delay causes say the airline caused 27.5% of missed connections, and late-arriving aircraft caused another 31.9%. So **40.6% to 72.5%** of misses fall in a gap nobody covers, depending on whether late aircraft count as the airline's fault.
- **v3 pays only in that gap:** the official GSA hotel-and-meals rate for the hub and month, when the connection is missed, the next flight is the next day, and BTS does not code the inbound problem to the airline. Every condition can be checked from public data. [Try it in the demo](https://dbechrakis.github.io/missed-connection-pricing/#gap-cover).
- **Costs and the cap are now sourced.** A night costs $198 to $295 by hub and year (GSA), so the $180 assumption was 9 to 39% too low. The cap is 5% of fare, below what comprehensive travel insurance costs (about 4 to 10% of trip cost).
- **Connections follow how tickets are sold.** A Charlotte passenger on American often flies a PSA or Piedmont regional flight. Pairing by marketing airline doubles the population to 115.8 million connections in 2025.
- **What the data says about the gap cover:** whole months come in 20 to 40% above or below the price, and no model choice removes it: no month term, no recalibration, no training on overnight connections only. This is a correlated weather and air-traffic risk, carried by the margin and not by the model. On March to August 2026, outside its training data, v3 ran at **1.12** × target. Offering it only where the price is under 5% of fare reaches 39% of overnight-risk connections, which run 9% worse (the winner's curse of selecting on a low estimate).
- **Pre-registered** for September to December 2026, with six falsifiable expectations and everything seen beforehand disclosed: [`PREREGISTRATION_2026H2_V3.md`](PREREGISTRATION_2026H2_V3.md). A weekly workflow opens an issue as each month is published.

## What this does **not** show

These are limits, not footnotes.

- **The connections are synthetic.** They are every same-airline pairing of an arriving and a departing flight at five US hubs, weighted by real route traffic. The data does not say which passengers actually connected, so risk is modelled, not observed in travellers.
- **The minimum connection time is an assumption** (45 minutes; 35 and 60 were tested by rebuilding the whole population, since MCT also decides which pairings exist, so those rates are not a pure label sensitivity). Same airline only, US domestic only.
- **Costs, the 65% target and the 10% price cap are assumptions** ($75 to rebook, $180 more if the next flight is the next day). The headline ratio hardly depends on the dollar amounts; the prices and the offer cut-off do. (v3 replaces them with GSA rates and a sourced cap.)
- **Demand is untested.** On one ticket an airline usually rebooks a missed connection for free, so protection must cover something extra. How many people would buy, at what price, and how strongly the riskiest connections self-select (θ) need an experiment ([designed in the brief](docs/product-brief.md#7-the-experiment)).
- **Severity is a lower bound.** Seat availability on the next flight is not observable.
- **No seasonal price in the demo.** v1 has no month term. v2 has one, and with a frozen calibrator it priced 2026 17% too high; because v2's good result also re-fits its calibrator every month, the 2026 test cannot say how much the month term itself helped.
- **Hubs are not equally well priced.** The ordering persists in every version but one: Chicago (ORD) too cheap, Charlotte (CLT) and Dallas (DFW) too dear. On the 2026 test v1 (the demo's model) priced ORD about 7% too cheap and CLT and DFW about 18% and 16% too dear; v2 rolling about 16% too cheap and 12% and 12% too dear.
- **Monthly recalibration assumes the whole previous month is known**, but a booking is made weeks before the flight. Re-pricing 2026 with the calibrator one month staler gives a 60.7% loss ratio (two months: 59.7%) against 62.3% with none; calibration error rises, and in a period when the level rises a stale calibrator would under-price instead. Exploratory ([`VALIDATION.md`](VALIDATION.md) Part 4), since 2026 had already been read.
- **Eight months, 35 weeks of clean test data.** The intervals are wide (about ±0.08 around the ratio).
- **Learning the loss ratio takes at least 27 weeks to ±10%**, however many policies are sold, because weather and operations hit all travellers in a week at once (89 weeks at 100 policies a week, 34 at 1,000).
- **The intervals are probably a little narrow.** They treat weeks as independent, but the level moves by month. A t-interval over the eight monthly ratios is about ±0.11 for v1 and ±0.12 for v2 rolling, against about ±0.08 from the bootstrap; neither changes whether the interval contains the target.
- **Not every synthetic connection is a real itinerary.** 23% have no DB1B route (their miss rates differ by about one point from the rest). Regional airlines fly for several mainline brands and the data used here does not say which brand sold a ticket, so some regional pairings may combine brands that could not be booked together. (v3 fixes this by pairing within the marketing network.)
- **An onward flight cancelled by the airline is not covered.** Those pairs are excluded from the label; they are about 18% as many events as missed connections, so a product that paid for them would see that many more claims before any difference in cost.
- **The loss ratio realizes the miss event, not what a miss cost.** Claim amounts are a schedule-based assumption; nothing here observes the actual cost of a missed connection.

## How it was validated

Prices are set from information up to the booking, then scored on months the model has never seen. Every test was **pre-registered**: the protocol, the frozen model hashes and the list of what may not change afterwards were committed *locally* before the window was read. They reached GitHub together with the results, so the commit times are the author's own and cannot be independently checked; the two model files are in the repository so the frozen hashes can be verified. The next test (BTS data for September to December 2026, not yet published) has its protocol, frozen hashes and falsifiable expectations in [`PREREGISTRATION_2026H2.md`](PREREGISTRATION_2026H2.md), written and tagged before the data exists.

| Window | Role | Result |
| --- | --- | --- |
| 2024 to mid-2025 | Fit and select v1 | Brier about 1 to 2% better than a hub × connection-time baseline (itself about 5% better than a flat rate): booking-time information is mostly connection time |
| July to December 2025 | v1 backtest, read once | 59.1% loss ratio vs 65% (spent; v1 over-priced because its calibrator carried a high level) |
| through December 2025 | v2 development (walk-forward) | Not quoted as validation |
| **January to August 2026** | **Clean holdout of v1 and v2, read once** | **60.5% and 62.3%**, both intervals contain 65% |

What did not go as hoped is written up in [`VALIDATION.md`](VALIDATION.md): v2 did not clearly beat v1 on the headline, a frozen calibrator on a month term priced 17% too high, and one of the four pre-registered expectations was not supported.

## Reproduce

Python 3.12. About 3 GB of downloads and 6 GB of Parquet on disk. On a laptop the compute (DuckDB, scikit-learn) is roughly two hours in total; download time depends on how BTS throttles you. Raw data is not in the repository.

```bash
pip install -r requirements.lock                    # the exact versions the frozen models were built with (requirements.txt gives looser ranges)
bash scripts/download_data.sh                       # DB1B and weather (BTS On-Time is fetched by ingest)
cd src
python -m mcp.ingest --start 2024-01 --end 2025-12  # BTS On-Time to Parquet
python -m mcp.ingest --source asos
python -m mcp.ingest --source db1b                  # route weights from the train quarters
python -m mcp.connections --mct 45 35 60            # synthetic connections and the label (MCT 45, with 35 and 60 as sensitivity)
python -m mcp.connections --mct 45 --no-build --weighted   # attach the DB1B route weights
python -m mcp.model                                 # baseline and metrics
python -m mcp.features                              # booking-time feature samples
python ../notebooks/01_eda.py                       # exploratory figures (docs/figures) and results/eda.json; train and validation months only
python -m mcp.model models && python -m mcp.model final   # v1: logistic, boosting, calibration
python -m mcp.pricing                               # severity, price table, sensitivity
python -m mcp.selection                             # exploratory: adverse selection on information the price lacks
python -m mcp.voi                                   # exploratory: what day-of information would add (development data)
python -m mcp.backtest                              # the July to December 2025 backtest (reads the test window once)
python -m mcp.v2 select && python -m mcp.v2 fit     # v2: walk-forward selection on 2025 and the final fit
cd .. && python -m pytest                           # the test suite (no data needed)
```

The 2026 holdout is sealed behind its own steps; read [`VALIDATION.md`](VALIDATION.md) Part 3 before running them:

```bash
cd src
python -m mcp.ingest --start 2026-01 --end 2026-08
python -m mcp.connections --start 2026-01 --end 2026-08 --quiet --weighted   # counts only, never outcome rates
python -m mcp.pricing --full-severity
python -m mcp.holdout                               # reads the 2026 months once
python -m mcp.experiment                            # experiment sizes for the product brief (uses the holdout's weekly variability)
python -m mcp.demo                                  # rebuilds site/prices.js for the demo
```

v3 has its own files, switched by one environment variable (v1 and v2 files are never touched):

```bash
cd src
export MCP_VARIANT=v3
python -m mcp.ingest --start 2024-01 --end 2026-08 && python -m mcp.ingest --source db1b   # BTS Marketing Carrier file; DB1B by ticketing carrier
python -m mcp.connections --mct 45 35 60 && python -m mcp.connections --mct 45 --no-build --weighted
python -m mcp.pricing --full-severity
python -m mcp.causes                                # who caused each missed connection (BTS delay causes)
python -m mcp.costs                                 # GSA hotel + meals by hub and month (cached pages in data/external/gsa)
python -m mcp.v3 select && python -m mcp.v3 fit     # walk-forward selection with a booking lag, final fit
python -m mcp.holdout_v3 9 10 11                    # ONLY under PREREGISTRATION_2026H2_V3.md, after the data is published
```

## What the day itself would add

The price is quoted at booking, so it can only use what is known then. The spec's open question: how much would day-of information improve things, and does it justify a second product, an alert to the traveller? With the alert placed one hour before the inbound flight's scheduled arrival, knowing how late that flight left cuts the booking-time model's Brier error by **44%** and lets an alert on the riskiest 5% of connections catch **52%** of misses at **75%** precision (booking-time information: 19% at 28%). Hub weather adds under 1%, most likely because a delayed flight already carries it. A first version of this analysis leaked each flight's final delay and overstated the value (52% instead of 44%); it is corrected and both are reported in [`VALIDATION.md`](VALIDATION.md) 4H. It does **not** show that an alert would help anyone: that depends on whether a traveller can act in that hour and on what a real-time feed costs.

![What day-of information adds](docs/figures/voi.png)

## Use it

The same price table serves the demo page, a command-line tool and a small API, so they cannot disagree.

```bash
cd src
python -m mcp.score --hub ORD --airline UA --minutes 60 --next-flight next      # one quote, printed
uvicorn mcp.api:app                                                              # API; interactive docs at http://127.0.0.1:8000/docs
python -m mcp.monitor --month 2026-08                                            # monthly recalibration and drift report
```

`/quote` returns the chance of a miss, expected claim cost, price, the share of such connections that fit the price cap, a three-state decision (offer, offer selectively, do not offer), the model's validated loss ratio, the assumptions and the caveats. `/model` reports the SHA-256 of the frozen model files, which match the hashes in [`VALIDATION.md`](VALIDATION.md). The monthly job prices the month with a calibrator built only from earlier months, reports drift by hub and week, alerts when the claim-weighted ratio over the last three months leaves a band sized from the 2025 spread (a rule that replaced hand-picked single-month bands that fired in 5 of 8 months; it is slow on purpose and cannot see steady hub gaps of 12 to 16%, see [`VALIDATION.md`](VALIDATION.md) 4J), and only then adds the month to its state.

## Repository

```
src/mcp/        ingest, connections, split, features, model, calibration, v2, pricing, experiment, backtest, holdout, selection, voi,
                monitor, service, score, api, demo; v3: variant, causes, costs, v3, holdout_v3
config/         pricing.yaml (assumptions, frozen), guards.yaml (price floor), connections settings
site/           the static demo (index.html + prices.js), published to GitHub Pages
tests/          label logic, leakage, pricing maths, validation accounting, guards on the test windows
notebooks/      01_eda.py, 02_model.py, 03_pricing.py (cells run as scripts or as notebooks; 02 and 03 read only the published results)
docs/           method.md, product-brief.md, decisions.md, figures/
results/        every number quoted above, as JSON/CSV produced by the code
VALIDATION.md   the pre-registered protocols and results, including what went wrong
```

## Data sources

[BTS Airline On-Time Performance](https://transtats.bts.gov/DatabaseInfo.asp?QO_VQ=EFD) · [BTS DB1B Origin and Destination Survey](https://transtats.bts.gov/DatabaseInfo.asp?QO_VQ=EFI) · [Iowa Environmental Mesonet ASOS](https://mesonet.agron.iastate.edu/request/download.phtml). All public. No company data is used anywhere in this project.

Author: [Dimitris Bechrakis](https://github.com/dbechrakis) · [MIT License](LICENSE)
