# Cross-Asset Defensive Trend: Candidate Survey and Data-Path Feasibility

Date: 2026-06-06.
Related decision: [ADR 0008](../decisions/0008-pivot-to-cross-asset-defensive-trend.md).

## Two gates up front

Every candidate had to clear two pre-code feasibility gates before any backtest code:

- **Data gate:** a free, keyless, reproducible, source-approved data path for the exact
  traded or measured object. Probe the endpoints, do not assume.
- **Stress gate:** a minimum-size deployment that cannot plausibly destroy a USD 10,000
  account before the model has a chance to be right.

The survey selected a cross-asset defensive trend rule and a public-domain data path. The
detail below is the audit trail.

## Lane 1: candidate survey

Four verticals were reviewed against recent research and practitioner sources, then run
through a four-lens decision review (realist, quant, builder, growth) and an adversarial
cross-check.

| Candidate | Verdict | Binding reason |
| --- | --- | --- |
| Crypto funding dispersion | Measurement-only | Deployable capture needs shorting a wide altcoin-perp cross-section US retail cannot trade, at a turnover whose costs exceed the spread |
| Short-horizon reversal / liquidation fade | Kill | Liquid majors show momentum not reversal; the clean liquidation feed is discontinued or paid; the surviving edge needs sub-five-minute holds |
| Commodity convenience-yield carry | Kill direct, measurement-only via ETF | No free keyless reproducible futures-curve-shape data; integer micro-contract sizing breaks a small account |
| Cross-asset defensive trend | Selected | Long-only, low-turnover, retail-executable; genuinely low-correlated sleeves repair Study 4's worst-fold weakness; the only open question was data |

The cross-asset trend was selected because it is the one candidate that directly fixes the
specific reason Study 4 failed. Study 4's worst CPCV fold collapsed because two crypto
majors are highly correlated, so the blended series had little real diversification.
Equities, long-term Treasuries, and gold are structurally far less correlated, so a blended
long-or-cash trend book can carry a higher and steadier quality into the worst fold while
staying long-only, unlevered, and cheap to run.

## Lane 2: data-path probe (the load-bearing deliverable)

The deployable rule trades exchange-traded funds, so the question was whether a free,
keyless, source-approved, long-history total-return series exists per asset class. Endpoints
were probed live on 2026-06-06.

| Source | Probe result | Verdict |
| --- | --- | --- |
| Popular undocumented fund-price chart API | HTTP 200 only with a spoofed browser User-Agent; the standard-library client gets HTTP 429 on first contact; terms restrict automated access and redistribution | Rejected |
| A similar exchange historical endpoint | HTTP 200 only with a browser User-Agent; same restriction class | Rejected |
| A widely-used free EOD price API | Keyed (HTTP 403 without a key) | Rejected on the keyless bar |
| A second free price API | Requires an API key | Rejected on the keyless bar |
| A formerly-scriptable free CSV mirror | Now serves a JavaScript proof-of-work wall instead of CSV | Rejected, no longer scriptable |
| Federal Reserve economic data (FRED) | Keyless CSV, public domain, but the licensed equity index series is short and price-only | Accepted for rates and gold, not for the equity total return |
| Kenneth French Data Library | HTTP 200, openly redistributable research factors, daily US market total return and the one-month Treasury bill rate since 1926 | Accepted as the equity and cash keystone |

The decisive finding mirrors Study 5. The only paths to scraped fund prices require shipping
code that spoofs a browser User-Agent to defeat an anti-bot block and then redistributing
terms-restricted data from a public repository whose entire credibility rests on
reproducibility. By the identical standard that killed the CME settlement path in Study 5,
those sources are rejected.

The accepted path uses openly-redistributable, public-domain research data for the
asset-class returns, and implements the position through the matching funds with a modeled
fund-versus-index basis:

- US equity total return and the one-month Treasury bill rate from the Kenneth French daily
  research factors.
- Long-term US Treasury total return reconstructed from the FRED constant-maturity yield
  using a standard point-in-time constant-maturity formula.
- Gold from a public-domain daily price series, included in the headline only if its
  redistribution terms and history are confirmed clean, otherwise reported as a sensitivity.

Because these series are published once and are not retroactively restated, they also avoid
the back-adjusted-price look-ahead hazard that a scraped adjusted-close series carries: a
moving-average signal computed on a retroactively restated price embeds future distributions
into past levels, and the public-domain return series do not have that defect.

## Lane 3: methodology and the frozen rule

The economics of cross-asset time-series trend are well established in the public literature
(asset-class trend with a moving-average filter, and time-series momentum across many
markets), with the honest caveat that the recent multi-year window has been one of the worst
trend-following environments on record. That recency risk is a real reason the deflated gate
could land below the bar, and it is the reason the headline is scored on the full history
with the recent slice reported only as a stress diagnostic.

The frozen, no-fit rule and the pre-registered kill criterion are stated in full in ADR 0008.
The load-bearing freezes, each chosen to remove a researcher degree of freedom before any
data is touched:

- The universe is defined by clean-data availability and anchored to Faber's 2007 asset
  classes (US equity, long-term US Treasury, gold), not chosen in hindsight; real estate and
  broad commodities are excluded for a documented lack of free public-domain total-return data,
  and foreign developed-market equity is a reported sensitivity.
- The signal is a ten-month simple moving average, monthly, computed by position on the
  total-return index, with the position effective the following month and filled at its first
  trading bar.
- Weighting is a fixed one-over-N-of-the-universe per active sleeve with inactive capital in
  bills, removing both the volatility-target and the concentration degrees of freedom.
- The long-term Treasury sleeve is reconstructed from the FRED ten-year constant-maturity yield
  with a frozen start-of-period-yield total-return formula, so the hardest computation is
  pinned point-in-time before code.
- Cash earns the realistic one-month Treasury bill rate, with a zero-yield sensitivity so the
  bill carry cannot hide as fake edge. The gate is scored on returns in excess of the bill, the
  honest measure of trend skill.
- Costs are realistic retail fund costs rounded up: an annual expense ratio charged on held
  notional (not turnover), plus a per-side turnover cost on rebalances.
- The scored series is marked to market daily (turnover stays monthly), so the statistic has
  daily-resolution observations.
- The primary gate is the full-sample net-of-cost conditional PSR(0) on the daily
  excess-of-bills series, at least 0.95, with the purged-CPCV stress distribution, the recency
  slices, and a deflated-Sharpe ladder at eight, sixteen, and thirty-two trials all reported
  alongside and never soft-pedaled.

## Final review

The conclusion of the fork is build-with-guardrails:

- Build the cross-asset defensive trend, because it is the only surveyed candidate that is
  both deployable at retail scale and a direct repair of Study 4's failure.
- Do not source fund prices from scraped or terms-restricted endpoints. Use public-domain
  research data and model the fund-versus-index basis honestly.
- Pre-register the universe, the rule, the cash treatment, the out-of-sample window, and the
  trial budget before fetching data, so the no-fit claim is real and the deflation is honest.
- Hold the same deflated, net-of-cost bar as Studies 3 through 5. A documented near-miss with
  a clear regime explanation is an acceptable honest null; a gate tuned to pass is not.
