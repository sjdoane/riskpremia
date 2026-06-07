# ADR 0009: a crypto funding-dispersion measurement study

Status: Accepted. Pre-registration before implementation.
Date: 2026-06-07.
Authors: Sam Doane (strategy fork after the Study 6 qualified pass, with a four-lens decision
review, an adversarial cross-check, a live data probe, and an independent senior-quant design
review of this pre-registration).

## Context

Study 6 (the cross-asset defensive trend) is the project's first result to clear the deflated
full-sample gate, but it is a qualified, regime-dependent pass on a classic rule. The question
for Study 7 is whether to take another deployable swing or to ship a measurement.

A fresh fork weighed both. The four-lens review favoured a measurement; the adversarial
cross-check pushed for a second deployable swing. The decisive facts:

- The clean-data deployable space is thin. The cleanest-data candidate, a volatility-managed
  portfolio, is contested out-of-sample by name (Cederburg, O'Doherty, Wang, and Yan 2020;
  Barroso and Detzel 2020 on costs), so it is a likely null on this project's exact gating
  dimensions. The other candidates rhyme with Study 6 (a cross-asset trend variant) or with the
  failed CTREND (a long-only defensive equity tilt) or need shorting (crypto cash-and-carry).
- Crypto funding-rate dispersion is a real, reproducibly-measurable object the project already
  has the data and machinery for, and it is a distinct premium from the killed Study 1 (which
  measured the funding LEVEL carry; this measures the cross-sectional DISPERSION across coins).

This is a measurement, not a tradeable verdict. It is framed as a descriptive measurement of an
object (like a volatility surface), not as a "positive result" in the make-money sense: the
gross premium behind the dispersion is not capturable at retail and is itself decaying.

## Decision

**Build a crypto funding-rate dispersion measurement study (Study 7), explicitly
non-deployable, mirroring the Study 2 Layer-i variance-premium measurement.** The headline is a
robust cross-sectional dispersion LEVEL with its regime split and decay, never a tradeable
Sharpe or a long-short return.

## The measured object and method (frozen)

### Universe and the spot-to-perp join (the load-bearing seam)

The point-in-time universe spine (CTREND `pit_eligible`) ranks USDT-quoted SPOT symbols by
trailing dollar volume; the funding archive is PERP symbols. These are different symbol sets and
must be joined on the canonical asset key. The frozen steps:

1. Per week, take the point-in-time eligible SPOT set from `pit_eligible` (top-N by trailing
   dollar volume, the delisting-complete enumeration).
2. Map each eligible spot symbol to its canonical asset key.
3. For each canonical, select exactly one perpetual funding series, preferring the USDT-margined
   perp leg, with a written tie-break; drop a canonical that has no perp funding series.
4. Report a per-week coverage diagnostic in the artifact: the eligible-spot count versus the
   matched-perp count, so the spot-to-perp attrition is visible, not silent.

This perp-leg selection is distinct from the spine's stablecoin base-filter and is specified
here because the spine deliberately does not treat the canonical key as a join key.

### Funding normalization (per event)

Funding intervals are heterogeneous and change mid-life (some coins migrate from 8-hour to
4-hour settlement). Each event's raw rate is annualized with THAT event's own
`funding_interval_hours`, never a per-coin aggregate:

```text
annualized_funding = last_funding_rate * (CRYPTO_ANNUALIZATION_DAYS * 24) / funding_interval_hours
```

reading the project's single-sourced `CRYPTO_ANNUALIZATION_DAYS = 365.0` (so the basis is
365 * 24 = 8760, consistent with every other annualization in the repo). A diagnostic counts
coins whose interval changed within the sample.

### The common grid (the second-order units trap)

A 4-hour coin and an 8-hour coin do not emit funding on the same timestamps, so a naive
group-by-timestamp computes a spread over only the coins that happen to settle on that stamp and
manufactures a spurious 4-hourly composition swing. Instead, each coin's annualized funding is
carried forward as a right-continuous step function and sampled onto a FIXED common grid (daily
00:00 UTC, matching the project's daily and weekly cadence) by a backward as-of join. The
carry-forward is point-in-time safe (it uses only the last realized rate) and is rejected across
a multi-day funding gap (mirroring the clock's mark and spot tolerances), so a coin with no live
funding near a grid point is absent there rather than stale.

### The dispersion statistics (the headline) and the decay

- **Headline:** the equal-weight cross-sectional interquartile range (IQR) of annualized funding
  across the eligible universe, as a daily time series. IQR is chosen over the standard deviation
  because the std is dominated by a single extreme small-cap coin entering the liquid set (an
  estimator artifact); the raw std and a winsorized std are reported as secondary diagnostics.
  Equal weight is the headline (each eligible coin one vote); a dollar-weighted spread would
  collapse toward the majors and understate dispersion.
- The headline number is the post-spot-ETF dispersion LEVEL with a confidence interval, plus the
  pre-versus-post-ETF difference and the decay. The spot-ETF boundary is the project's standard
  comparability split, not a claimed cause of an altcoin-funding regime change; the decay curve
  is the primary regime evidence.
- **Decay:** a rolling 90-day median of the daily IQR over time, plus a single summary slope
  (sign and magnitude) with a bootstrap confidence interval.

### The gross sort premium (secondary, measured, non-deployable)

Reported only as a secondary, banner-attached measured object: a quintile cross-sectional
funding sort (top-minus-bottom), equal-weight within bucket, rebalanced on the common grid, with
the return defined as the next-period realized annualized funding of the held coins (sorted at
time t using funding known at t, realized over the following period). It is funding-only and
ignores the perp price PnL, which is exactly why it is non-capturable at retail. No tradeable
Sharpe is quoted for it.

### Significance and reproducibility

- For the dispersion LEVEL, the pre-versus-post difference, and the decay slope: the vendored
  stationary-block bootstrap on the FULL (un-strided) daily dispersion series, with a
  Politis-White block-deflated effective sample size and a percentile confidence interval. The
  dependence here is funding-regime persistence, not window overlap, so there is no VRP-style
  striding; the block length absorbs the persistence. A dispersion level is positive by
  construction, so the reported statement is its LEVEL and its regime DIFFERENCE and decay
  slope (both signed and testable), never a vacuous clears-zero test on the level.
- For the secondary gross sort premium: the block bootstrap on the FORMED top-minus-bottom
  return series (contemporaneous cross-coin correlation is absorbed into the formed return).
- The bootstrap seed and the resample count are pinned in the build for a reproducible artifact.

## Honesty guardrails (pre-registered)

The dispersion looks like free money and must not be oversold:

- No tradeable Sharpe headline and no long-short return as the headline, anywhere.
- An explicit non-deployability banner in the abstract: US retail cannot short a wide
  altcoin-perp cross-section, and the venue with the data (Binance) is not US-tradeable, so the
  gross premium is not capturable at retail (the wall ADR 0006 flagged).
- The decay is stated in the headline, not buried: the related crypto carry literature reports
  the gross level-carry Sharpe collapsing toward zero or negative by 2025, and the dispersion
  decay is the primary regime evidence.
- The deliverable is a descriptive measurement (like a volatility surface), explicitly not a
  "positive result" in the make-money sense.
- The interval-normalization and the equal-weight, IQR-based estimator are shown so no reader
  mistakes a units or estimator artifact for dispersion.

## The two pre-code feasibility gates

- **Data gate: PASS.** The Binance Vision funding archive was probed directly: 816 perpetual
  funding series (733 USDT, 39 USDC, 41 BUSD), BTC history from 2020-01 to 2026-05, published
  per-file SHA256 checksums verifying byte-for-byte, and delisted contracts persisting with a
  frozen end-date (survivorship-complete). The data is free, keyless, reproducible, and already
  has a stdlib loader plus the funding clock and the point-in-time universe spine. The one real
  hole, that not every liquid spot coin has a perp funding series, is handled as the per-week
  coverage diagnostic above, not hidden.
- **Stress gate: not applicable.** A measurement study carries no live position, so there is no
  account-survival stress to fail. The non-deployability is the headline, not a risk to be sized.

## Considered and deferred

- **A volatility-managed (inverse-volatility risk-targeting) stock and bond portfolio** on the
  Study 6 data: a genuine deployable alternative, deferred because it is contested out-of-sample
  by name and is a likely null on this project's deflated gate. It is the registered next
  deployable swing if a measurement is judged insufficient.
- **A cross-asset trend variant** (rhymes with Study 6), a **long-only defensive equity tilt**
  (rhymes with the failed CTREND), and **crypto cash-and-carry** (needs shorting): rejected as
  Study 7.

## First milestone

**The funding-dispersion measurement, built from the committed Binance Vision funding archive.**
A network builder fetches the per-coin funding across the point-in-time universe, performs the
spot-to-perp canonical join and the per-event interval annualization, samples onto the common
daily grid, and writes a committed, SHA256-stamped dispersion series plus the coverage
diagnostic; a no-network builder rebuilds the deterministic artifact (the dispersion time series,
the equal-weight IQR headline with its bootstrap CI, the pre/post-ETF difference, the decay
slope, the secondary banner-attached gross-sort-premium measurement, the coverage and
interval-change diagnostics, and the caveats); an offline reproduction test asserts the committed
fixture reproduces the artifact. The vendored bootstrap and effective-sample stack is reused
unchanged. Recruiter-facing figures follow.

## Status

Accepted. The measured object, the method, the significance design, and the honesty guardrails
above are pre-registered. The candidate survey, the data-path probe, and the design-review
findings are in `docs/research/0009-funding-dispersion-measurement-design.md`. The build and the
measured result follow.

## Implementation amendment (2026-06-07, after the build and post-implementation review)

Two notes record where the build is narrower than the pre-registration above, neither of which
changes the verdict. Both were raised by the post-implementation review as Medium findings.

1. **The spot-to-perp join was resolved by USDT-symbol-string identity, not by a canonical
   asset key.** The eligible set from `pit_eligible` is already USDT-quoted spot symbols (for
   example `BTCUSDT`), and the funding archive is fetched for those exact same symbol strings;
   the Binance USD-margined perpetual for an asset shares that string, so the join is exact
   string identity, with no canonical-key mapping and no USDC/BUSD fallback leg. The
   consequence is a deliberate coverage hole: an asset whose only perp is non-USDT-quoted, or
   whose perp is prefix-renamed (the 1000x meme perps such as `1000SHIBUSDT` or
   `1000000MOGUSDT`, whose spot symbol is unprefixed), is dropped rather than matched. This is a
   conservative understatement of dispersion: it can only narrow the cross-section (drop a coin),
   never widen it or manufacture a spread. The attrition is not silent: the per-day coverage
   diagnostic in the artifact reports a mean of 91% (13.6 of 15 eligible coins funded) with a
   worst day of 73%, so the seam is visible and bounded. A canonical-key join with a quote
   fallback is recorded as a backlog item should this object ever be revisited for deployment;
   for a non-deployable measurement at 91% coverage with a published diagnostic, the identity
   join is acceptable.
2. **The frozen universe is the top-15 most-liquid perpetuals over 2022 onward** (116
   ever-eligible symbols across the window), not an unbounded top-N. The top-50 union was 402
   coins, a heavier fetch dominated by short-lived small caps whose entry and exit add
   estimator noise to the cross-section; the top-15 over the matured-perp-market window is a
   clean, bounded, documented liquid universe, and it is recorded in the provenance and the
   manifest. The decay and the regime split are reported on this fixed universe.
