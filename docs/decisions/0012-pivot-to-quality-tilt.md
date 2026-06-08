# ADR 0012: a long-only quality (profitability) tilt study

Status: Accepted. Pre-registration before implementation.
Date: 2026-06-07.
Authors: Sam Doane (strategy fork after the Study 9 timing null, with an adversarial cross-check
that redirected the registered low-volatility candidate to a profitability tilt, and a live data
probe of the Kenneth French portfolios).

## Context

The project has seven honest non-make-money results, two measurements, and one qualified deployable
pass (Study 6). Studies 6, 8, and 9 established a thesis: defensive equity timing (volatility-managed
in 8, price-trend in 6 and 9) reduces risk but does not beat buy-and-hold at retail net of cost. The
question for Study 10 is whether any genuinely orthogonal, non-trend, non-timing premium beats the
market at retail.

The registered backup was a long-only low-volatility (low-beta) tilt. An adversarial cross-check
redirected it, on three points: the unlevered retail form of low-volatility is "lower volatility for
lower absolute return", a risk-adjusted result that would be an eighth null re-proving the existing
thesis, not a make-money result; low-volatility is the most crowded and post-publication-decayed
major factor (the documented low-volatility-ETF inflows and the 2016 low-volatility crash); and its
only clean Kenneth French series is monthly, the project's weakest-powered test for its most
contested candidate.

The cross-check's alternative is a long-only **profitability (quality)** tilt, which is stronger on
every dimension: it is the one major factor whose long leg carries a positive **absolute** return
tilt (so a net-of-market pass, a genuine make-money result, is possible rather than a foregone risk-
reduction null); it is the least crowded and most out-of-sample-robust major factor (robust across
23 countries 1987 to 2019); it is **low-turnover** by construction (profitability is persistent), so
the deflated net-of-cost gate that kills crowded high-turnover factors is where quality is strongest;
and the Kenneth French operating-profitability portfolios are available **daily**, keeping the
project's daily-data discipline.

A live data probe confirmed `Portfolios_Formed_on_OP_Daily` is clean (value-weighted daily, 1963-07
to 2026-04, 15813 rows, zero missing markers; the columns include `Hi 30` and `Hi 20`, the high-
profitability tercile and quintile). The monthly market and one-month bill come from the same Kenneth
French factor library already in the loader.

## Decision

**Build a long-only quality (profitability) tilt study (Study 10): hold the high-operating-
profitability value-weighted portfolio, and score it as the difference over buy-and-hold the
value-weight market.** The high-profitability portfolio and the market are both value-weighted, so
the difference is a clean net-of-market comparison with no equal-weight-versus-value-weight confound
(the seam the Study 9 design review caught). The study asks the make-money question directly: does
holding quality beat holding the market, net of cost and deflation?

## The measured object and method (frozen)

### Universe

The Kenneth French `Portfolios_Formed_on_OP_Daily` value-weighted portfolios. The headline is the
**high-profitability tercile `Hi 30`** (a deployable breadth, low turnover, mapping to a quality ETF
such as QUAL); the `Hi 20` quintile and `Hi 10` decile are deflation variants. The benchmark is the
value-weight market total return (`Mkt-RF + RF` from the Kenneth French daily factors) and the
one-month bill. The window is the full daily overlap (1963 onward); the equal-weighted portfolios and
the low-profitability legs are not the headline.

### The rule (no-fit, a static tilt)

Hold the high-profitability value-weighted portfolio continuously; the French portfolio reconstitutes
once a year at the end of June, so there is no timing rule and no fitted parameter. A deployable
implementation is a quality ETF; the cost is the fund expense ratio plus the low annual
reconstitution turnover.

### Costs

A flat 0.15 percent annual expense ratio (the QUAL-style quality-ETF level) accrued daily on held
notional, plus a per-side turnover cost (5 basis points) on the annual reconstitution drift. Quality
is persistent, so the turnover is low; the cost realism is reported, not assumed away, with a
sensitivity at a higher expense and turnover.

### The kill (net-of-market, the make-money test)

- **Primary:** the full-sample conditional PSR(0) of the **high-profitability-minus-market**
  difference series (the high-profitability portfolio's net total return minus the market's net total
  return), against the 0.95 bar, block-deflated effective T. Both legs are value-weighted and carry
  the same expense, so the difference isolates the quality tilt's value-add over the market. This is
  the Study 8 and Study 9 difference-kill machinery; a positive, significant, deflated difference is a
  make-money pass (quality beats the market), and a null is an honest result.
- **Attribution (context, not the kill):** a Fama-French regression of the high-profitability excess
  return on the market (and the size and value factors) to show how much of the net-of-market
  difference is pure profitability alpha versus a bundled size, value, or market-beta tilt; the RMW
  (robust-minus-weak) spread is reported as the long-short factor context. The net-of-bill PSR (the
  equity premium) and the standalone Sharpes are reported as context, explicitly labeled.
- **Stress:** the purged-CPCV worst fold and the 2000-, 2008-, and 2022-onward recency slices on the
  difference series; the monthly non-overlapping difference PSR(0) as the honest independent-unit
  cross-check; a Deflated-Sharpe trial ladder over the breadth family (`Hi 30`, `Hi 20`, `Hi 10`).
- **Redundancy:** the correlation of the difference series with the qualified-pass Study 6 strategy,
  reported for distinctness (quality is a fundamental cross-sectional tilt, orthogonal to trend).

### Significance and reproducibility

The vendored deflated-Sharpe, purged-CPCV, and Politis-White block stack and the committed-fixture
plus offline-reproduction pattern are reused unchanged. A network builder commits the daily panel
(the high-profitability portfolios, the market, and the bill); a no-network builder rebuilds the
deterministic gate artifact; an offline test reproduces it. The trial count and the v_sr family are
frozen in this ADR and the gate constants.

## Honesty guardrails (pre-registered)

- The kill is net-of-market (does quality beat the market), never net-of-bill (the equity premium);
  the net-of-bill number is reported only as context.
- The Fama-French attribution is reported so a net-of-market pass is not mis-attributed entirely to
  quality when part is a size, value, or beta tilt; the deployable claim honestly includes the
  bundled tilts a quality ETF carries, while the attribution shows the composition.
- Crowding and post-publication decay are acknowledged: the recency slices (2000-, 2008-, 2022-
  onward) are the regime stress, and a meaningful decay in the recent slices is reported as such.
- The rule is a static tilt with no fitted parameter; the breadth variants are a deflation family.

## The two pre-code feasibility gates

- **Data gate: PASS.** `Portfolios_Formed_on_OP_Daily` and the daily factors are free, keyless,
  reproducible, redistribution-permitted, daily, clean (zero missing markers, 1963 to 2026), and
  already have a loader family (extended for Studies 8 and 9).
- **Stress gate: PASS.** The strategy is long-only with no shorting and no leverage, so a minimum
  practical position cannot destroy a small account; the deployable implementation is a quality ETF.

## Considered and deferred

- **A long-only low-volatility / low-beta tilt:** the registered backup, redirected because its
  unlevered retail form is a likely risk-reduction null, it is the most crowded and decayed major
  factor, and its clean Kenneth French series is monthly only. Recorded as a deferred candidate; the
  betting-against-beta long-short is a possible labeled context comparator if quality is built.
- **A value (HML) tilt:** a candidate, deferred because value's long leg is more cyclical and its
  post-2008 decade is weak; profitability is the more out-of-sample-robust, lower-turnover, positive-
  absolute-tilt choice for a make-money shot.

## First milestone

**The quality-tilt net-of-market gate, built from a committed Kenneth French high-profitability daily
panel.** A network builder fetches the operating-profitability portfolios and the factors and commits
the panel; a no-network builder holds the high-profitability portfolio, charges the costs, marks the
series daily, and writes the gate artifact (the net-of-market difference PSR, the Fama-French
attribution, the net-of-bill context, the CPCV and recency stress, the deflation ladder, and the
Study-6 correlation); an offline test reproduces it. A senior-quant design review precedes the freeze
of any new code, then a post-implementation review. Figures follow.

## Status

Accepted. The measured object, the frozen method, the gate design, and the honesty guardrails above
are pre-registered. The fork, the adversarial findings, the literature check, and the data probes are
in `docs/research/0015-quality-tilt-design.md`. The build and the measured result follow.
