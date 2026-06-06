# ADR 0006: pivot to BTC/ETH slow trend with cash and a volatility cap

Status: Accepted. PR6a completed with a non-viable verdict.
Date: 2026-06-06.
Authors: Sam Doane (strategy-pivot fork after the CTREND null, with five
web-grounded vertical reviews and an adversarial senior-quant decision review).

## Context

Study 3, the CTREND crypto cross-sectional trend factor, returned a decisive honest
null under the project's realistic retail cost gate. The retail long-only top quintile
lost after costs on the held-out 2022-plus window, and the academic long-short
comparison also failed the conservative CPCV-min DSR gate. That result changes the
search problem.

The prior failures are not identical, but they rhyme:

- The vanilla funding carry failed because passive premium collection could not beat
  realistic costs, capital drag, and post-ETF compression.
- The VRP study measured a real implied-minus-realized variance premium, but the
  static monthly short-straddle implementation failed because tradeability was path
  blind and tail exposed.
- CTREND had real gross cross-sectional signal quality, but the retail deployable
  long-only version lost after turnover and costs.

The new decision standard is therefore stricter than "find a large academic premium."
The next primary strategy must be retail executable, low turnover, free-data
reproducible, no unbounded short convexity, no seconds-level latency edge, and no
inaccessible financing. A boring pass is worth more than a clever null with an obvious
execution hole.

## Research fork

Five vertical reviews were run over recent published research and practitioner data
sources:

- **Crypto funding dispersion and basis:** cross-venue perp-perp and same-venue
  funding dispersion are structurally more promising than the killed level carry, but
  the best edge lives in venue fragmentation, collateral movement, short-perp access,
  and capacity. Decision-critical sources: [BIS Crypto Carry](https://www.bis.org/publ/work1087.pdf)
  and [The Two-Tiered Structure of Cryptocurrency Funding Rate Markets](https://www.mdpi.com/2227-7390/14/2/346).
- **Short-horizon reversal, liquidations, and microstructure:** the literature supports
  liquidity-provision premia, reversal, and order-flow prediction, but the likely edge
  lives in illiquid names, paid order-book data, or horizons too fast for retail.
- **Slow crypto trend and allocation overlays:** BTC/ETH time-series trend with cash
  and volatility targeting has the cleanest data path and cost profile. It is not
  exciting, but it is the only primary candidate whose failure would be a clean
  statistical result rather than an execution footnote.
- **Crypto options and VIX-style volatility trades:** state-dependent VRP and skew are
  real research topics, but daily option-surface history, dynamic hedge cost, and short
  convexity remain blockers. The prior VRP result already showed that a premium can be
  real while the retail trade is non-viable.
- **Non-crypto diversifiers:** G10 Micro FX carry is the best backup because it is
  macro-legible, small-account tradeable, and structurally different. VIX roll has
  better public data but unacceptable retail short-vol tail risk. Commodity carry is
  intellectually strong but blocked by a free, point-in-time futures-curve data path.

## Decision

**Move forward with BTC/ETH slow trend with cash and a volatility cap.**

This is Study 4. The object is a no-fit, preregistered allocation rule:

- **Universe:** BTC and ETH spot only.
- **Clock:** weekly rebalance, using prior closes only.
- **Signal:** hold an asset only when its prior close is above its 200-day simple
  moving average. Otherwise hold cash.
- **Sizing:** equal-risk active assets, 25 percent annualized volatility target, 100
  percent notional cap. No leverage is needed for a pass.
- **Cash:** use a transparent cash or T-bill proxy for inactive capital.
- **Costs:** spot-only realistic retail costs through the existing cost model. No
  shorting, no perps, no option legs, no financing assumption needed for the headline.
- **No parameter search:** the 200-day moving average and 25 percent volatility target
  are frozen. Breadth gates, macro gates, 150-day variants, and alt baskets are not part
  of the first gate.

The economic thesis is simple: crypto beta has large persistent trends and clustered
crashes; standing aside in cash during downtrends may be a deployable drawdown-control
premium even if it is not a pure alpha. The point of the gate is to determine whether
that defensive timing survives the project's deflated, net-of-cost standard.

Decision-critical support:

- [Monash, "Trend-following Strategies for Crypto Investors"](https://www.monash.edu/__data/assets/pdf_file/0011/3744821/Trend-following-Strategies-for-Crypto-Investors.pdf)
  tests crypto trend rules with cash and volatility overlays across BTC, ETH, and a
  large-cap crypto index.
- [Quantpedia, "Revisiting Trend-following and Mean-reversion Strategies in Bitcoin"](https://quantpedia.com/revisiting-trend-following-and-mean-reversion-strategies-in-bitcoin/)
  revisits Bitcoin trend and reversal out of sample through August 2024.
- [Fidelity Digital Assets Q3 2025 Signals Report](https://www.fidelitydigitalassets.com/sites/g/files/djuvja3256/files/acquiadam/FDA_Q3_2025_SignalsReport_1228043.2.0_V2.pdf)
  treats Bitcoin moving-average regimes as live institutional monitoring signals.

## Backup

If Study 4 dies quickly, the backup is **G10 Micro FX carry with a hard risk-off kill
switch**, traded only through CME Micro FX.

Why it is the backup, not the primary:

- It is the best non-crypto diversifier and has recruiter value as a macro risk-premia
  study.
- CME states Micro G5 FX contracts are one-tenth the size of the standard contracts and
  have average initial margin around USD 180, so the small-account execution path is
  plausible: [CME Micro FX](https://www.cmegroup.com/markets/microsuite/fx.html).
- The forward-premium anomaly remains a valid research target, but the August 2024 yen
  carry unwind is the failure mode. BIS estimated a rough JPY 40 trillion, about USD
  250 billion, carry footprint going into that event:
  [BIS Bulletin 90](https://www.bis.org/publ/bisbull90.htm). See also the 2024
  re-examination of the forward-premium anomaly:
  [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S1062976924000528).

Backup kill criterion: do not proceed unless the data path is free and reproducible from
public spot FX, rate, futures settlement, and CFTC positioning sources. Kill deployment if
net-of-cost out-of-sample DSR under purged CPCV is below 0.95, or if historical stress
loss at the minimum practical contract size can plausibly exceed 50 percent of a USD
10,000 account.

## Why the tempting paths wait

- **Funding dispersion:** keep as a measurement project. It may be real, but the
  deployable edge is entangled with fragmented collateral, venue access, short-perp
  execution, and capacity. It is not the next core strategy.
- **Short-horizon reversal and liquidation fades:** do not lead with these unless the
  retail-speed, liquid-asset version survives first. Paid microstructure data and ugly
  fills are too likely to be the hidden edge.
- **Crypto options and VIX roll:** do not lead with another short-vol family now. The
  data and convexity blockers are exactly what the VRP gate just exposed.
- **Breadth-gated alt allocation and macro gates:** defer as robustness overlays. After
  CTREND, anything that adds top-20 breadth, macro thresholds, or post-ETF regime logic
  is too easy to overfit unless the plain BTC/ETH gate clears first.
- **Commodity carry and Treasury basis:** commodity carry is blocked by point-in-time
  futures-curve data; Treasury basis is institutional financing, repo, margin, and
  leverage. Both can be written about, not led as retail strategy builds.

## First milestone

**PR6a: `btc_eth_trend_gate`.**

Scope:

- Build a no-network gate from committed BTC/ETH daily OHLC fixtures, with a network
  builder that can refresh the fixtures from free public sources.
- Implement the frozen 200-day moving-average signal, weekly rebalance, cash proxy,
  equal-risk active-asset sizing, 25 percent volatility target, 100 percent notional cap,
  and spot-cost model.
- Score the series through 2026-05-31 with the existing PSR, CPCV, and effective-sample
  stack. Because the rule is frozen and no-fit, the statistic is conditional PSR(0), not
  Deflated Sharpe.
- Write a regenerable artifact with the headline, stress checks, turnover-cost share,
  drawdown versus buy-and-hold, and caveats.

Pre-registered kill criterion:

- Kill if net-of-cost 2022-plus out-of-sample CPCV stress minimum conditional PSR(0) is
  below 0.95.
- Kill if max drawdown exceeds 35 percent.
- Kill if turnover costs consume more than 25 percent of gross edge.
- Kill if the result only passes by relaxing the 100 percent notional cap.

Secondary diagnostics, not pass conditions: post-ETF 2024-plus performance, max-drawdown
reduction versus buy-and-hold BTC/ETH, CAGR give-up versus buy-and-hold, and sensitivity
to the cash proxy.

## Status

Accepted. PR6a was built from committed BTC/ETH daily OHLC fixtures and returned a
non-viable verdict: 229 weekly observations, mean net +0.1975 percent per week,
full-window conditional PSR(0) 0.6970, CPCV stress minimum conditional PSR(0) 0.1439,
daily max drawdown 26.65 percent, cost share 11.47 percent, and compounded net gain
43.91 percent. The result is positive and drawdown-reducing, but it fails the statistical
kill gate. The G10 Micro FX backup named here was later tested and killed at feasibility
in [ADR 0007](0007-kill-cme-micro-g6-fx-carry.md).
