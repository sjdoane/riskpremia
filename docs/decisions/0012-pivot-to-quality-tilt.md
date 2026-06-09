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

## Design-review amendment (2026-06-07, before implementation)

A senior-quant design review of the build plan, which measured the result directly on the live data
through the project's own scoring stack, returned three Critical, three High, and several Medium
findings, all folded in here before any code. The review found the headline difference PSR(0) sits at
0.9505 only at trial-count-one-and-gross, and every honest tightening (the differential cost, the
deflation, every recency slice) pushes it below the 0.95 bar. The elevated stakes (a possible live
deployment) make false-pass avoidance paramount; the revisions below make the gate honest. The
original text is superseded where it conflicts.

1. **Critical: the cost is the deployable DIFFERENTIAL expense, not the high-leg expense alone.** A
   quality ETF and a market ETF are both deployed, so the honest drag is the quality-ETF expense
   ratio minus the market-ETF expense ratio. The frozen primary is 0.15 percent on the
   high-profitability leg and 0.04 percent on the market leg (a net differential near 0.11 percent),
   with a pre-registered sensitivity bracket of 0.05, 0.10, and 0.20 percent differential. The gross
   (zero-cost) PSR is reported only as context, labeled "before the deployable expense differential",
   never the headline. On the live data the differential cost alone takes the headline below the bar.
2. **Critical: no separate reconstitution turnover (no double-count).** The held portfolio is a
   static single portfolio that the build never rebalances, and the French daily series already
   embeds the annual end-June reconstitution, so there is no build-side weight change to charge. The
   pre-registration's separate per-side reconstitution turnover line is dropped; the differential
   expense (which embeds an index fund's reconstitution drag) is the only cost. The cost-model basis
   string records this.
3. **Critical: the deflation ladder is a HARD gate condition, not a stress footnote.** A
   trial-count-one PSR is not a pass for a factor as mined as quality. A clean make-money pass
   requires the Deflated Sharpe to clear 0.95 at a named minimum trial count of 16 (literature-scale
   for the quality factor). The trial ladder runs to 128, and the v_sr family is widened beyond the
   breadth cut (the tercile, quintile, and decile are near-collinear) to span the weighting axis
   (value and equal weighted) at minimum; the definitional axis (gross profitability, investment, the
   quality composite) is acknowledged as a search the v_sr understates, so the reported deflation is a
   lower bound on the true penalty. On the live data the headline fails deflation at every trial count
   at or above three, and the widest cut (the tercile) is the strongest member, the signature of a
   broad large-cap-quality beta rather than a monotone profitability premium.
4. **High: the Fama-French alpha is a gate guardrail, not context.** The headline kill stays the raw
   net-of-market difference (the deployable bundle a quality ETF gives you, which cannot strip its own
   factor exposures), but a clean make-money pass additionally requires a positive Fama-French
   five-factor alpha with the robust-minus-weak loading the dominant positive exposure, so a beta,
   size, or value tilt cannot be deployed mislabeled as profitability alpha. The attribution reports
   the five-factor alpha with a Newey-West (heteroskedasticity-and-autocorrelation-consistent)
   standard error and t-statistic. No beta-scaling is applied: the measured high-profitability beta is
   0.98, so the difference is not a disguised low-beta bet and adding a fitted scalar is unwarranted.
5. **High: a 2010-onward recency slice is pre-registered.** The quality-ETF era (QUAL launched 2013)
   is the decisive crowding and post-publication-decay stress for a candidate whose selling point is
   low crowding. The recency slices are 2000, 2008, 2010, and 2022 onward; the verdict string names
   the binding constraint (the deflation and the differential cost), as Study 8's named the leverage
   cap.
6. **High: the deployable-versus-proxy gap is stated up front.** The Kenneth French academic
   operating-profitability value-weighted tercile is not the deployable MSCI-quality ETFs (QUAL and
   peers use a sector-neutral composite of return-on-equity, leverage, and earnings stability over
   roughly 125 large caps, with their own turnover and tracking error). A tercile pass demonstrates
   the academic operating-profitability premium net of an assumed differential expense, not a QUAL
   guarantee. This goes in the caveats and the verdict reason.
7. **Medium: reuse the scoring scaffold, not the Study 9 timing simulator.** The strategy is a static
   hold: the high-profitability net daily return is the portfolio return minus its expense, the market
   net is the market return minus its expense, and the difference is scored. There is no monthly
   rebalance, no signal, no weight vector, so the Study 9 simulator is not reused (copying it would
   resurrect the reconstitution double-count). The redundancy reports only the difference-versus-
   Study-6 correlation (there is no active bet for a static hold). The decomposition is
   quality-specific (the raw difference, the five-factor alpha, and the robust-minus-weak-attributed
   component), not the Study 9 timing-tilt-deploy split.
8. **Medium: the make-money verdict semantics.** A make-money pass requires the headline difference
   PSR to clear the bar AND the deflation to clear at trials 16 or more AND the five-factor alpha to
   be positive AND the result not to be regime-dependent; anything less is reported as "the
   operating-profitability premium is real but does not survive the deflated net-of-differential-cost
   gate; survives only undeflated", an honest marginal-to-null result, not a deployable pass.
