# CME Micro G6 FX Carry Feasibility Note

Date: 2026-06-06.
Related decision: [ADR 0007](../decisions/0007-kill-cme-micro-g6-fx-carry.md).

## Kill Criterion Up Front

This feasibility pass was allowed to proceed only if both gates cleared:

- **Data gate:** free, keyless, reproducible public sources must cover spot FX, rates,
  futures settlements or exact traded-contract proxies, VIX or risk-off data, and CFTC
  positioning.
- **Deployment gate:** the minimum practical CME Micro FX implementation must not have a
  plausible historical stress loss above 50 percent of a USD 10,000 account.

The result is a kill at feasibility. The data path is good enough for measurement, but not
for a deployable exchange-traded futures verdict. The deployment gate also fails because
integer micro contracts are too coarse for a small diversified carry basket.

## Lane 1: Free Data Path

The source stack that works for a measurement study:

| Need | Source | Feasibility |
| --- | --- | --- |
| Spot FX | BIS bilateral exchange rates, Federal Reserve H.10, FRED graph exports | Plausible free source path |
| Policy-rate carry signal | BIS central bank policy rates | Plausible free source path |
| Risk-off switch | Cboe VIX CSV or FRED VIXCLS | Plausible free source path |
| Positioning | CFTC COT historical compressed files | Confirmed useful auxiliary path |
| CME Micro FX settlements | CME delayed settlement pages or TCF files | Not robust enough for long-history scripted backtest |

CFTC official historical ZIP files for 2025 and 2026 returned HTTP 200 in the local probe.
That validates the COT auxiliary path. The CME settlement path did not validate: direct local
fetches of current TCF CSV settlement files returned HTTP 403, and the browser-visible public
directory does not provide a durable 2010-plus history. CME also points historical settlement
products toward DataMine.

Decision from this lane: **kill the exact free CME settlement-history path as a primary
dependency.** A spot-plus-policy-rate measurement note could proceed later, but it would not
answer the deployable CME Micro FX question.

Key sources:

- [BIS bilateral exchange rates](https://data.bis.org/topics/XRU)
- [BIS central bank policy rates](https://data.bis.org/topics/CBPOL)
- [Federal Reserve H.10](https://www.federalreserve.gov/Releases/H10/default.htm)
- [FRED DEXUSEU](https://fred.stlouisfed.org/series/DEXUSEU)
- [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS)
- [Cboe VIX historical data](https://www.cboe.com/tradable_products/vix/vix_historical_data)
- [CFTC historical compressed COT](https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm)
- [CME settlement data FAQ](https://www.cmegroup.com/articles/faqs/access-to-cme-group-settlement-data-faq.html)

## Lane 2: Methodology And Literature

The economics are real enough to study, but not clean enough to waive the gates.

Classic currency-carry research links carry returns to crash risk, global FX volatility,
and crowded positioning. Recent work is more cautious: out-of-sample carry performance is
unstable, G10 premia appear compressed, and regime dependence is a central risk.

The no-fit rule that would have been defensible:

- Universe: CME Micro AUD, CAD, CHF, EUR, GBP, and JPY versus USD.
- Carry signal: futures-implied carry if settlements are available, otherwise a frozen
  policy-rate differential only for measurement.
- Portfolio: monthly long the two highest carry currencies and short the two lowest.
- Circuit breaker: fully flat when a predeclared VIX risk-off condition is active.
- Diagnostics: CFTC positioning as crowding context, not an optimized filter.

That rule is not implemented because the feasibility gates fail first.

Key sources:

- [Brunnermeier, Nagel, and Pedersen, currency crashes](https://www.princeton.edu/~markus/research/papers/carry_trades_currency_crashes.pdf)
- [Menkhoff, Sarno, Schmeling, and Schrimpf, global FX volatility](https://openaccess.city.ac.uk/id/eprint/3391/)
- [Lustig, Roussanov, and Verdelhan, common risk factor](https://econpapers.repec.org/paper/nbrnberwo/14082.htm)
- [Hsu, Taylor, Wang, and Li, out-of-sample carry trades](https://profiles.wustl.edu/en/publications/the-out-of-sample-performance-of-carry-trades/)
- [BIS Bulletin 90 on the 2024 yen carry unwind](https://www.bis.org/publ/bisbull90.htm)

## Lane 3: Execution And Stress

CME Micro FX is not a full G10 implementation. The supported micro set is AUD, CAD, CHF,
EUR, GBP, and JPY versus USD. NZD, NOK, and SEK are not in the current micro set.

The minimum-size stress math is enough to fail the deployment gate:

| Stress | Minimum leg | Approximate loss | USD 10,000 account impact |
| --- | --- | ---: | ---: |
| August 2024 yen unwind | Short one `MJY` | USD 955 | 9.6 percent |
| AUD/JPY-style two-leg cross in the same window | Long `M6A`, short `MJY` | USD 1,214 | 12.1 percent |
| 2015 CHF shock | Short one `MSF` | USD 2,438 | 24.4 percent |
| 2015 CHF shock, two short CHF funding legs | Two `MSF` equivalents | USD 4,876 | 48.8 percent |
| 2015 CHF shock, three short CHF funding legs | Three `MSF` equivalents | USD 7,314 | 73.1 percent |

That is before slippage, widened spreads, extra margin calls, broker liquidation policy, and
roll friction. A diversified carry basket can reach the two-leg or three-leg state naturally.
The strategy therefore fails the kill criterion for a USD 10,000 account.

Key sources:

- [CME FX Product Guide](https://www.cmegroup.com/markets/fx/fx-product-guide.html)
- [CME Micro FX](https://www.cmegroup.com/markets/microsuite/fx.html)
- [CME FX futures margins context](https://www.cmegroup.com/markets/fx/fx-futures.html)
- [CME historical margins](https://www.cmegroup.com/solutions/risk-management/margin-services/historical-margins.html)
- [SNB 2015 announcement context](https://www.snb.ch/en/publications/communication/speeches/2015/ref_20150424_tjn)
- [Fed H.10 January 20, 2015](https://www.federalreserve.gov/releases/h10/20150120/)

## Final Review

The review conclusion is kill-before-code:

- Do not call the strategy G10. The exchange-traded micro universe is G6.
- Do not build a futures backtest without source-approved historical settlements.
- Do not use policy-rate spot carry as a proxy for a deployable futures strategy.
- Do not trade a diversified micro carry basket in a USD 10,000 account when CHF-style
  integer sizing can plausibly erase more than half the account.
- Do not add COT, volatility scaling, or custom VIX thresholds after failure unless they
  are recorded as new trials.

The clean next action is a fresh strategy fork with the feasibility gates applied before
implementation.
