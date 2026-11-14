# Pre-registration: v6 forecasts, what a late buyer can know and a sales rule for it

Written **12 November 2026**, before any weather forecast was joined to a connection and before any forecast archive was downloaded. It is a separate document. The commit that adds it is pushed to GitHub before the first such download, and a tag marks it (`prereg-v6-forecast`). Drafted by Claude for the author.

## 1. The question

The project treats the spread of risk that buyers can see and the price cannot (κ) as unmeasurable from public data, and prices a cover that pays when weather or the air traffic system disrupts a connection. A traveller who books three days ahead can read the weather forecast. If the forecast changes the risk of an overnight miss, a buyer who waits is better informed than the price, and the cover is exposed to exactly the selection the memo warns of (`VALIDATION.md` 4C). Travel insurers stop selling once a storm has a name. Two measurements:

1. How much does a forecast **as it was issued** 1, 2, 3, 5 and 7 days ahead improve the prediction of a gap-cover miss over the booking-time price, and what spread of risk does that imply?
2. Would a rule that stops selling on a connection when the forecast says its risk is much higher than priced have lowered the sold loss ratio and the number of bad weeks?

## 2. What has and has not been seen

- **Seen:** every outcome of every connection from January 2024 to August 2026, and every analysis of them, including the weekly loss ratios as sold. The test window below (September 2025 to August 2026) is development data for the gap cover.
- **Not seen:** no forecast has been joined to any connection. No forecast archive has been read by this project. The fit and test windows below are fixed before the join.
- **Not touched:** nothing from September 2026 on.

## 3. Data

- **Forecasts:** the Open-Meteo Previous Runs API (`previous-runs-api.open-meteo.com`), hourly, at the coordinates of each hub airport (ATL 33.6407, −84.4277; ORD 41.9742, −87.9073; DFW 32.8998, −97.0403; DEN 39.8561, −104.6737; CLT 35.2140, −80.9431), default model, variables `precipitation`, `snowfall`, `wind_gusts_10m` and `weather_code`, each at the leads `previous_day1`, `previous_day2`, `previous_day3`, `previous_day5` and `previous_day7`. A value at lead d is what the forecast issued d days earlier said for that hour.
- **Archive start.** Checked on 12 November 2026: day-1 values exist from about 22 January 2024 and day-7 values from about 26 January 2024. The windows start on **1 February 2024**.
- **What is not known:** how the vendor builds the archive (whether earlier runs are archived as issued or reconstructed), which is a limit of the result. The vendor is not a government source.

## 4. Features and models

- **Features at lead d, per connection:** over the hub hours from one hour before to three hours after the inbound flight's scheduled arrival, the maximum forecast precipitation, snowfall and wind gust, an indicator of a thunderstorm code (95, 96, 99) and an indicator of a wintry code (56, 57, 66, 67, 71 to 77, 85, 86). Five numbers. They enter the v3 gradient-boosting model next to the v1 feature set, with the same settings (`LEAVES` 15, the v3 gap label, no calibration).
- **A model per lead.** The booking-time model and the forecast model of each lead are fitted on the same connections, 1 February 2024 to 31 August 2025 (at most 3,000,000 rows), and scored on the same connections, **1 September 2025 to 31 August 2026**, read once, a 10% hash sample of overnight-risk connections.
- **Leakage test, a condition of the code:** replacing the observed weather of the day by anything must not change any feature. The features are built from forecast columns only.
- **Gain.** The pooled weighted log loss of the gap label, `(base − forecast) ÷ base` in percent, per lead, with a 95% interval from a bootstrap over calendar months.
- **κ.** The weighted standard deviation of log(p_forecast ÷ p_booking) over the test connections, per lead, and the exposure exp(θκ²) at θ = 1 that the project's own formula gives.

## 5. The sales rule

Fixed now: **stop selling on a connection when the forecast-informed risk at lead 3 is more than 1.5 times the priced risk** (p_forecast ÷ p_booking > 1.5).

Booking lead is not in public data, so the rule is evaluated over a grid. A share s of buyers book within three days (**10%, 20%, 30%**). The others book earlier and see no forecast, and the rule does not apply to them. Late buyers pick connections in proportion to (p_forecast ÷ p_booking)^θ, with **θ = 0 and θ = 1**. Everything is scored on the test window's actual outcomes at the booking-time price, as sold within the 5% cap. Reported: the sold loss ratio, the number of weeks above a 100% loss ratio, the share of sales lost, with and without the rule.

## 6. Gate

If the gain is **under 1% at every lead**, the result is reported as a null, the question is closed as "forecasts do not arm a late buyer", and the rule is not evaluated.

## 7. Expectations (falsifiable; each is reported, pass or fail)

| # | Expectation | Rule | If it fails |
| --- | --- | --- | --- |
| F1 | **More information closer in.** The gain at lead 1 is larger than the gain at lead 7, and the gain at lead 7 is under 1% | Both | Either the archive is not as issued, or a week-ahead forecast already helps |
| F2 | **The rule helps.** At s = 20% and θ = 1 the number of weeks above a 100% loss ratio as sold is lower with the rule than without | Strictly lower | The stop-selling rule does not address the exposure. F2 is graded only if the gate passes |

The size of the gain, κ at each lead and the grid of the rule are reported without prediction.

## 8. Not allowed after the read

Changing the windows, the leads, the features, the model, the 1.5 threshold, the lead of the rule, the grid, the gate or the metric. A bug may be fixed only with the numbers before and after, in `VALIDATION.md` Part 7.

## 9. What this cannot show

How travellers really choose, how many book late, whether a forecast archive built by a vendor equals what a traveller saw, and anything about demand. The grid is a range and not an estimate.
