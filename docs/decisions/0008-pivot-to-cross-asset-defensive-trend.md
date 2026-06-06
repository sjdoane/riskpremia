# ADR 0008: pivot to a cross-asset defensive trend on public-domain data

Status: Accepted. Pre-registration before implementation.
Date: 2026-06-06.
Authors: Sam Doane (strategy-pivot fork after the CME Micro FX feasibility kill, with a
four-lens decision review, an adversarial cross-check, live data-path probes, and an
independent senior-quant design review of this pre-registration).

## Context

Five studies are honest nulls. Funding carry, the VRP short-straddle, the CTREND
cross-sectional factor, and the BTC/ETH slow trend all failed the net-of-cost deflated
gate; CME Micro G6 FX carry was killed at feasibility before code. The standing goal is
unchanged: keep forking until a retail-deployable rule survives the same gate, or document
why each candidate does not.

Study 4 is the most informative prior result. The BTC/ETH slow-trend rule was positive and
drawdown-reducing but failed on statistical strength: its worst-regime CPCV minimum
conditional PSR(0) was 0.1439 on 229 weekly observations of two highly-correlated assets.
The lesson is twofold. First, two highly-correlated assets give the blended return series
too little real diversification. Second, a worst-fold-of-six gate on a low-frequency series
is a very high bar, because the worst fold has both the fewest observations and the worst
regime. Study 6 addresses both: genuinely low-correlated sleeves, and a daily-resolution
scoring series with a principled primary statistic for a no-fit rule.

## Research fork

A fresh candidate survey ran four vertical reviews over recent research and practitioner
sources, plus a four-lens decision review (realist, quant, builder, growth) and an
adversarial cross-check. Every data claim was probed live.

- **Crypto funding dispersion:** real and currently alive, data already loaded, but the
  deployable long-short needs shorting a wide altcoin-perp cross-section US retail cannot
  access on venues a US account cannot trade. A measurement subject, not a deployable rule.
- **Short-horizon reversal and liquidation fades:** in liquid majors the documented effect
  is momentum, not reversal; the clean liquidation feed is discontinued or paid; the
  surviving edge needs sub-five-minute holds. Fails retail-speed, free-data, and no-latency.
- **Commodity convenience-yield carry:** no free, keyless, reproducible futures-curve-shape
  source exists, and integer micro-contract sizing breaks a small account, the Study 5 wall.
- **Cross-asset slow trend (a Faber-style defensive allocation):** long-only, low-turnover,
  retail-executable, and the only candidate that directly repairs Study 4's weakness, because
  equities, long-term Treasuries, and gold are far less correlated than two crypto majors. Its
  one open question was the data path.

## The data path decision

The deployable rule trades exchange-traded funds, but the reproducibility question is whether
a free, keyless, source-approved, long-history total-return series exists per asset class.
The probes were decisive:

- Scraped fund-price endpoints (a popular undocumented chart API and a similar exchange
  endpoint) return data only when the client spoofs a browser User-Agent; the honest
  standard-library client receives HTTP 429 on first contact, and their terms restrict
  automated access and redistribution. Committing a fixture from such a source redistributes
  restricted data and contradicts the exact standard that killed Study 5. Rejected.
- One free-but-keyed source and one proof-of-work-walled source were rejected on the keyless
  and reproducibility bars.

The accepted path uses public-domain and openly-redistributable research data for the
asset-class returns, and implements the position through funds with a modeled fund-versus-index
basis:

- **US equity total return and the one-month Treasury bill rate:** the Kenneth French Data
  Library daily research factors, openly redistributed, daily since 1926. US equity total
  return is the market factor plus the bill rate; cash earns the bill rate directly.
- **Long-term US Treasury total return:** reconstructed from the Federal Reserve ten-year
  constant-maturity yield, series `DGS10` (FRED, public domain, daily since 1962), using the
  point-in-time constant-maturity formula stated below.
- **Gold:** a public-domain daily London gold price series (FRED). FRED redistributes it
  freely; if a strict reading of the underlying benchmark terms later disallows it, gold drops
  to a sensitivity and the headline is equity plus long Treasury.

These series are published as realized returns or as-observed yields and are not retroactively
restated like a scraped adjusted-close, which removes the back-adjusted-price look-ahead hazard.

**Reproducibility model.** Kenneth French re-releases its zip monthly and silently restates the
most recent months as source data finalizes; FRED revises recent observations. So these are
as-of reproducibility fixtures, not immutable vendor dumps. The build commits the derived input
series (the daily equity total return, the daily bill rate, the daily ten-year yield, and the
gold price) as SHA256-stamped fixtures of kind `reproducibility_fixture`, records the fetch date
as load-bearing provenance, and the offline gate rebuilds from those committed bytes. The
checksum attests tamper-evidence of the committed snapshot, not vendor byte-fidelity. A hard
data end-date is frozen at **2026-03-31**, and the network fetch is dated **2026-06-06**, so the
headline window ends at least two months before the as-of to avoid scoring on the
most-likely-to-be-restated points.

Both pre-code feasibility gates pass: the data gate (free, keyless, redistributable, long
history, standard-library fetch) and the stress gate (long-or-cash funds, no shorting, leverage,
or convexity, so no minimum-size position can plausibly destroy a USD 10,000 account).

## Decision

**Build a cross-asset defensive trend rule, scored on public-domain asset-class data.**

This is Study 6. The object is a frozen, no-fit, pre-registered allocation rule.

- **Universe (defined by clean-data availability, anchored to Faber 2007, not by hindsight):**
  US equity, long-term US Treasury, and gold; cash is the one-month Treasury bill. The
  common daily history runs from the latest sleeve inception (gold, about 1968) through the
  frozen end-date. Real estate and broad commodities are excluded for a documented reason: no
  free, keyless, public-domain long-history total-return series exists for them (the commodity
  exclusion is the same data wall found in the commodity-carry feasibility review). Foreign
  developed-market equity (Kenneth French, daily since 1990) is available and is reported as a
  pre-registered robustness sensitivity, not in the longest-common-history headline.
- **Clock:** monthly rebalance using prior month-end closes only. Month-end is the last
  trading day on or before the calendar month-end.
- **Signal:** hold a sleeve long only when its total-return index is strictly above its
  ten-month simple moving average, computed by position as the mean of the last ten monthly
  closes, at the prior month-end. Otherwise that sleeve's capital earns the one-month bill.
- **Weighting:** fixed one-over-N-of-the-universe per active sleeve, with inactive sleeves'
  capital in bills. With three sleeves, a single active sleeve is one third invested and two
  thirds in bills. This caps single-sleeve exposure, is genuinely defensive, and respects the
  100 percent notional cap. Equal weight is frozen to remove the volatility-target degree of
  freedom; one-over-N-of-the-universe (not one-over-N-active) is frozen to remove the
  concentration degree of freedom.
- **Execution and scoring frequency:** the position is formed from month-end signals and is
  effective for the following month, filled at the next month's first trading bar (no same-bar
  leak). The net return series is marked to market **daily** for scoring, so the statistic has
  daily-resolution observations while turnover stays monthly. This is the direct fix for the
  power problem that a monthly-resolution worst-fold gate would otherwise impose.
- **Cash:** the realistic one-month Treasury bill rate (the daily bill return from the Kenneth
  French risk-free series, which is the realized return on a bill held that day, known at the
  start of the period). The risk-free rate is an observable, not a tunable parameter. A
  zero-yield-cash version is reported as a sensitivity.
- **Costs:** a realistic retail fund-implementation cost, rounded conservatively up:
  - an annual expense ratio charged on the **held notional**, accrued daily (not on turnover),
    at 0.10 percent for equity, 0.15 percent for long Treasury, and 0.40 percent for gold,
    anchored to liquid 2026 funds;
  - a per-side turnover cost of 5 basis points (spread plus commission) on each rebalance trade;
  - the fund-versus-index basis is otherwise carried by the expense-ratio drag.
  Charging the expense ratio on held notional is essential: a low-turnover rule would otherwise
  escape its real holding drag and the result would be flattered.
- **No parameter search:** the ten-month moving average, monthly rebalance, one-over-N-of-universe
  equal weight, and the data-defined universe are frozen. Twelve-month variants,
  inverse-volatility weighting, the foreign-equity sleeve, and a crypto sleeve are explicitly
  deferred as separate trials.

### Bond total-return reconstruction (frozen formula)

For the ten-year constant-maturity Treasury, the daily total return from the prior close to the
current close, using only point-in-time data, is:

```text
TR_t = y_{t-1} * dt  -  D(y_{t-1}, M) * (y_t - y_{t-1})  +  0.5 * C(y_{t-1}, M) * (y_t - y_{t-1})^2
```

where `dt = 1/252` (daily accrual), `M = 10` years, `y` is the DGS10 yield in decimal, and
`D` and `C` are the modified duration and convexity of a par bond priced at the start-of-period
yield `y_{t-1}` with maturity `M` and semiannual coupon equal to `y_{t-1}`. The load-bearing
point: the carry term and the duration and convexity use the start-of-period yield `y_{t-1}`,
which is known when the position is formed; only the yield change uses `y_t`. The par-coupon
convention, the inclusion of convexity, and the start-of-period duration are all frozen.

## Pre-registered kill criterion (frozen here, before any backtest code)

The study ships regardless of outcome; an honest null is an intended, acceptable deliverable.
The gate is about real-money deployability.

The scored series is the **daily, net-of-cost, in-excess-of-the-one-month-bill** return of the
strategy. Scoring in excess of bills is the honest measure of trend skill, so a result that
passes only on bill carry is an honest null, not a strategy.

- **Primary gate:** the full-sample conditional PSR(0) on the daily excess-of-bills net return
  series must be at least 0.95. Because the rule is frozen and no-fit, the statistic is
  conditional PSR(0), not Deflated Sharpe, and the full sample is the legitimate out-of-sample
  window (there is no fitting period to hold out from). The effective sample size uses the
  project block-length deflation, which correctly discounts the daily autocorrelation induced
  by monthly holding.
- **Reported robustness (prominent in the verdict, never soft-pedaled):** the purged CPCV
  path-stitched conditional PSR(0) distribution (median and worst path); the worst single
  purged-CPCV fold conditional PSR(0) (the harshest reading, the one Study 4 used); and the
  2008-onward and 2022-onward recency-slice conditional PSR(0). A full-sample pass with a weak
  CPCV-stress or recency number is reported as deployable-but-regime-dependent, a qualified
  result, not a clean pass.
- **Deflation sensitivity:** the Deflated Sharpe on a trial-budget ladder of 8, 16, and 32,
  reported alongside the headline so the reader sees how fast the deflated number decays against
  the inherited search behind a ten-month moving-average trend rule.
- **Secondary checks (consistent with Study 4):** maximum drawdown no more than 35 percent;
  total costs no more than 25 percent of compounded gross gain; the long-or-cash book respects
  the 100 percent notional cap.

Kill and declare an honest null if the primary gate is below 0.95. Do not soft-pedal a hit.

## Backup

If Study 6 is an honest null, the registered backup is the crypto funding-dispersion measurement
note: clean data already loaded, pre-approved on the ADR 0006 deferred menu, and a measurement
note's deliverable is the measured object, so it is not a tradeable-verdict null. A fresh
strategy fork follows under the same decision standard and the same two pre-code feasibility
gates.

## First milestone

**The cross-asset trend gate, built from committed public-domain fixtures.** A network builder
fetches the Kenneth French factors and the FRED series and writes SHA256-stamped committed
fixtures of the derived input series; a no-network gate rebuilds a deterministic artifact with
the headline, the CPCV stress distribution, the recency slices, the cost share, the drawdown
versus buy-and-hold, the deflation ladder, and the caveats; an offline reproduction test asserts
the committed fixtures reproduce the artifact. The reused PSR, CPCV, and effective-sample stack
is unchanged. The windowing and annualization layer is written fresh for monthly TradFi data
(position-based ten-month moving average, daily marks, 252-day annualization for diagnostics);
the crypto-continuous calendar-walking window helper and 365-day constant from the Study 4 gate
are not reused. Surgical tests cover the month-end resample, the signal-to-fill timing, the bond
reconstruction point-in-time property, and the expense-ratio-on-held-notional charge.

## Status

Accepted. The frozen rule and the kill criterion above are pre-registered. The supporting
candidate survey and data-path feasibility detail are in
`docs/research/0007-cross-asset-trend-feasibility.md`. Implementation and the verdict follow in
the gate build.

## Amendment (implementation, 2026-06-06)

Four points are recorded from the build, none of which change the frozen rule or the kill
criterion:

- **Gold dropped.** The FRED London gold series returned HTTP 404 (the licensed series is no
  longer served) and no other free, keyless, public-domain daily gold path was found, so the
  headline universe is the pre-registered fallback: US equity plus long Treasury.
- **Treasury source.** The ten-year yield is the US Treasury daily par yield curve
  (home.treasury.gov), fetched per year, rather than FRED `DGS10`, because the FRED bulk
  series fetch was unreliable from the build machine. It is the original source of the same
  ten-year par yield; the par-yield history begins in 1990, which sets the common window.
- **CPCV path-stitching is degenerate for a no-fit rule** and is not reported: the returns do
  not depend on a training set, so every stitched path equals the full sample. The worst
  held-out fold is the meaningful CPCV stress.
- **The honest independent unit is the month.** The daily marks within a held month share one
  position, so the non-overlapping monthly conditional PSR(0) is reported alongside the daily
  one as the conservative cross-check (it gives the same verdict); the daily series is used for
  resolution, not to inflate the effective sample. The post-implementation review confirmed the
  daily excess series has negative net autocorrelation, so the deflation is conservative.

**Verdict: a qualified pass.** Full-sample conditional PSR(0) 0.9996 and monthly 0.9970 both
clear 0.95 and survive deflation (Deflated Sharpe 0.998 at 32 trials), with an 11.2 percent
maximum drawdown and a 2.8 percent cost share; but the result is regime-dependent (CPCV worst
fold 0.72, 2022-onward recency 0.40), and per-sleeve attribution shows the equity trend sleeve
carries it (standalone PSR 0.998) while the long-Treasury sleeve is weaker (0.846) and drives
the recent-regime weakness. The first result to clear the deflated full-sample gate; an honest
qualified pass on a classic rule, not a novel edge. Detail in
`docs/research/0008-cross-asset-trend-gate-design.md`.
