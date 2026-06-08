# ADR 0011: an industry-trend net-of-market study

Status: Accepted. Pre-registration before implementation.
Date: 2026-06-07.
Authors: Sam Doane (strategy fork after the Study 8 volatility-managed null, with a focused panel
review, a literature check, and live data probes of the Kenneth French industry and beta-sorted
portfolios).

## Context

Study 8 (the volatility-managed market) is the project's sixth honest null: a real gross
volatility-timing alpha that did not survive the retail leverage cap and net-of-cost frictions,
scored honestly as the managed-minus-unmanaged difference over buy-and-hold. The project has one
qualified, regime-dependent deployable pass (Study 6, a cross-asset defensive trend that beat the
one-month bill) and needs a second clean deployable result.

The registered backup was cross-sectional industry/sector momentum. A focused fork (an adversarial
direction review, a deployability realist, and a senior-quant design review, each web-searching the
literature) reached two strong conclusions that redirect the study:

- **Cross-sectional industry momentum is the dominated, likely-null candidate.** Its cumulative
  cross-sectional premium is roughly flat from 2000 onward (exactly the regime the deflated gate
  stresses), it is documented as largely subsumed by the broad momentum factor, and the long-only
  retail version forfeits about half the academic long-short alpha while carrying full market beta.
  The impressive long-history industry result in the recent literature (Zarattini and Antonacci) is
  a time-series (absolute) trend, not the cross-section.
- **The kill must be net-of-market, not net-of-bills.** This is the load-bearing lesson carried
  from Study 8: a long-only equity book that beats the one-month bill is mostly harvesting the
  equity premium, not skill. The honest deployable bar is beating buy-and-hold the market, net of
  cost.

A live data probe confirmed the Kenneth French 12-industry daily value-weighted portfolios are
clean and complete (the 49-industry set carries early missing markers; the beta-sorted portfolios
are monthly only). The strongest deployable trend effect with clean daily data, the lowest
researcher degrees-of-freedom, and a clean kill statistic is therefore absolute (time-series)
industry trend, scored net-of-market.

## Decision

**Build an industry-trend net-of-market study (Study 9): hold each of the 12 Kenneth French
industries long when its own trend is up and in Treasury bills otherwise, and score the strategy as
the difference over buy-and-hold the market.** The frozen trend rule is reused verbatim from Study 6
(a no-fit ten-month moving average), so the only new elements are the 12-industry universe and the
net-of-market kill. The study answers a question the trend literature usually skips and that Study 6
did not: does price-trend timing beat buy-and-hold the market, net of cost and deflation, or only
beat cash?

## The measured object and method (frozen)

### Universe

The Kenneth French **12-industry daily value-weighted** portfolios (NoDur, Durbl, Manuf, Enrgy,
Chems, BusEq, Telcm, Utils, Shops, Hlth, Money, Other), and the daily market total return and
one-month bill from the Kenneth French factors. Value-weighted matches the investable
capitalization-weighted SPDR sector funds; the 12-industry set is complete (no missing markers) and
maps closely to the deployable sector-ETF set. The 49-industry and equal-weighted sets are deflation
variants only, never the headline. The window is the full overlap of the industry and factor daily
files; recency slices (2008 onward, 2022 onward) are reported as stress.

### The frozen rule (no-fit, reused from Study 6)

Each industry is held long when its total-return index is strictly above its ten-month moving
average at the prior month-end, otherwise that sleeve's capital earns the one-month bill. Fixed
one-twelfth-of-the-universe weight per sleeve, monthly rebalance, the net series marked to market
daily. The ten-month window and the long-or-cash structure are frozen verbatim from Study 6 (ADR
0008); no length is re-optimized for this universe, which is the single most important safeguard
against a forking-path pass.

### Costs

The Study 6 cost model verbatim: a per-side turnover cost of 5 basis points on each rebalance trade
plus a 0.10 percent annual SPDR-style expense ratio accrued daily on held notional. Twelve sleeves
churn more than two, so turnover is a real, pre-registered, untuned drag.

### The kill (net-of-market, the Study 8 lesson)

- **Primary:** the full-sample conditional PSR(0) of the **strategy-minus-market difference**
  series (the daily net strategy return minus the daily market total return) against the 0.95 bar,
  block-deflated effective T. This isolates the trend-timing value over buy-and-hold; a long-only
  equity strategy that clears a net-of-bill bar on the equity premium does not clear this.
- **Context (not the kill):** the standalone strategy's net-of-bill conditional PSR(0) (the Study 6
  metric) and the standalone strategy and market annualized Sharpes, reported to show how much of
  the result is the equity premium rather than timing skill.
- **Stress:** purged-CPCV worst fold and the 2008-onward and 2022-onward recency slices on the
  difference series; the monthly non-overlapping difference PSR(0) as the honest independent-unit
  cross-check; a Deflated-Sharpe trial ladder (8, 16, 32) with a v_sr proxy from the moving-average
  length family (6, 8, 10, 12 months) on the difference series.
- **Redundancy:** the correlation of the difference series with the Study 6 strategy is reported, so
  the distinctness from Study 6 (a different universe and a harder, net-of-market benchmark) is
  shown rather than assumed.

### Significance and reproducibility

The vendored deflated-Sharpe, purged-CPCV, and Politis-White block stack and the committed-fixture
plus offline-reproduction pattern are reused unchanged. The trial count is frozen in the registry.
A network builder fetches the 12-industry daily file and the factors, writes a committed
SHA256-stamped panel; a no-network builder rebuilds the deterministic gate artifact; an offline test
reproduces it.

## Honesty guardrails (pre-registered)

- The kill is net-of-market, never net-of-bill; the net-of-bill number is reported only as context,
  explicitly labeled as equity-premium-dominated.
- The trend rule is frozen from Study 6 with no re-optimization for this universe; the
  moving-average length variants are a deflation family, not a search for a winner.
- The fork expects a likely null (a long-or-cash trend strategy is crash insurance, so the
  difference over buy-and-hold is near zero or negative net of cost); an honest null is the intended
  deliverable and would, with Study 8, establish that defensive equity timing does not beat
  buy-and-hold at retail. A pass would be a genuinely strong deployable result that beats the market,
  not just cash.
- The redundancy with Study 6 is addressed head-on (the net-of-market benchmark and the 12-industry
  universe make it a distinct, harder test; the correlation is reported).

## The two pre-code feasibility gates

- **Data gate: PASS.** The Kenneth French 12-industry daily value-weighted portfolios and the daily
  factors are free, keyless, reproducible, redistribution-permitted, and already have a loader
  family (the source extended for Study 8); the 12-industry set is complete with no missing markers.
- **Stress gate: PASS.** The strategy is long-or-cash with no shorting and no leverage, so a minimum
  practical position cannot destroy a small account; the deployable implementation is the SPDR
  sector funds and the bill.

## Considered and deferred

- **Cross-sectional industry/sector momentum:** the registered backup, redirected because the fork
  found it the dominated, post-2000-flat, likely-null candidate that forfeits half its alpha
  long-only. Recorded as a deferred variant.
- **A long-only low-volatility / defensive (low-beta) tilt:** the genuinely orthogonal,
  non-trend alternative and the panel's runner-up for portfolio diversity. Deferred because the
  Kenneth French beta-sorted portfolios are monthly only (a data and apparatus divergence from the
  daily pattern) and the right kill statistic for an unlevered defensive tilt (a Sharpe or
  information-ratio comparison, not a mean difference) needs its own design pass. It is the
  registered next candidate if the project wants a non-trend premium.

## First milestone

**The industry-trend net-of-market gate, built from a committed Kenneth French 12-industry daily
panel.** A network builder fetches the industry portfolios and the factors and writes the committed
panel; a no-network builder runs the frozen rule, charges the costs, marks the series daily, and
writes the gate artifact (the difference PSR, the net-of-bill context, the CPCV and recency stress,
the deflation ladder, and the Study-6 correlation); an offline test reproduces it. A senior-quant
design review precedes the freeze of any new code, then a post-implementation review. Figures
follow.

## Status

Accepted. The measured object, the frozen method, the gate design, and the honesty guardrails above
are pre-registered. The fork, the panel findings, the literature check, and the data probes are in
`docs/research/0013-industry-trend-net-of-market-design.md`. The build and the measured result
follow.
