# ADR 0005: pivot to the CTREND crypto cross-sectional trend factor (after the VRP null)

Status: Accepted.
Date: 2026-06-04.
Authors: Sam Doane (strategy-pivot fork made under the project's full-authority scoping
mandate, with three web-grounded research passes, a four-lens review (realist, quant,
builder, growth), and an adversarial cross-check per rule 1; the candidate was selected
from a researched shortlist).

## Context

The VRP short-variance test (ADR 0004 Layer ii) returned NON-VIABLE: the variance premium
is real and positive as a measurement, but the static held-to-expiry short straddle is a
path-blind directional bet that loses before costs and has a catastrophic inverse-
settlement crash tail. That is the third honest NULL in the portfolio, after vanilla
equity momentum (the sibling pit-backtest project) and the crypto funding carry (ADR 0003).

Per the standing rule on a kill (do not stop at the write-up: read the research, learn the
algorithms, survey GitHub, run a four-lens fork, and pivot to a different strategy), and at
the operator's explicit direction to keep pivoting until a strategy survives the gate, the
next candidate was chosen by three independent research passes plus the four-lens and
adversarial cross-check. The decisive lesson the three nulls taught is load-bearing here:
simple, content-farmed premium harvesting dies at retail costs, and any survivor must come
from SELECTION, TIMING, or STRUCTURE, not a passive premium. The binding constraints are
unchanged (free, reproducible, US-reachable data; US-tradeable at retail; additive to the
three nulls; recruiter-impressive through rigor; an honest null is an acceptable, intended
deliverable). The vendored PSR/DSR/CPCV/bootstrap/trial-registry stack and the cost-model-
first / kill-gate discipline are reused.

## The candidate research

Three web-grounded passes (a candidate generator, a GitHub / reproducible-edge survey, and
an adversarial best-shot pass) surveyed the 2022-2026 literature, GitHub, and practitioner
sources, screening ~17 candidate families. The screen confirmed-dead or rejected, with
citations: the crypto factor-zoo (= the momentum null in a crypto wrapper); CME crypto
cash-and-carry (= the carry null, arbed to ~the risk-free rate post-spot-ETF); the Treasury
basis (institutional, 50:1 levered, repo-financed); volatility-managed portfolios (a
documented OOS + cost null); betting-against-beta / low-vol (a microcap / leverage trap);
PEAD (decayed to the illiquid microcap tail, t falls from 2.18 to 1.43 ex-microcaps); crypto
pairs / cointegration (overfit-poisoned, with OOS Sharpe reported ABOVE in-sample, the tell);
liquidation-cascade fade (HFT / latency-bound, a rigorous live write-up made +$0.51 on $200
notional); stablecoin depeg (adverse selection: a free spread is more often a breaking peg
than a gift); and short-vol / skew / VXX term-structure (Volmageddon, the same peso bomb
already killed in ADR 0004, with worse leverage decay).

Three candidates survived the adversarial screen (a real structural reason to persist, free
reproducible US-reachable data, US-retail execution, additivity), and the operator selected
the first:

- **CTREND, the crypto cross-sectional trend factor** [SELECTED]. Fieberg, Liedtke, Poddig,
  Walker and Zaremba, "A Trend Factor for the Cross-Section of Cryptocurrency Returns" (JFQA
  2025). The decisive fact: it is the ONLY surveyed candidate with a peer-reviewed, COST-
  HONEST survival claim. It aggregates a set of trend / technical signals per coin via a
  cross-sectional elastic-net into one forecast, then sorts coins into quintiles, and the
  paper reports explicit transaction-cost tiers (30/40 to 50/60 bps per leg), 68%/week
  turnover, a breakeven cost of ~88 to 141 bps per side (far above realistic retail fees),
  and persistence in the LIQUID top-100 (not a microcap illusion), with a 55,296-
  implementation robustness sweep that pre-pays some of the data-snooping deflation.
- **Selective cross-sectional funding-DISPERSION carry** [staged fallback]. Structurally
  distinct from the killed level carry: cross-coin funding dispersion is ~10x larger,
  extremely persistent (autocorrelation 0.97+), and the long/short legs partly self-finance.
  The honest worry is adverse selection (the fat dispersion lives in illiquid alts; ~40% of
  fat-funding names are positive after costs), so it is most likely a capacity-bounded null.
- **Commodity convenience-yield carry (micro futures)** [staged fallback]. A bona-fide risk
  premium with a clear bearer (the commercial hedger), newly retail-feasible via micro
  futures, free settlement data, low turnover, maximally orthogonal; the most greenfield
  (a new asset class + data layer).

## Why CTREND

- It is the single most FALSIFIABLE candidate: a peer-reviewed claim of cost survival to
  test under a realistic retail cost model. The outcome is recruiter-grade EITHER WAY: a
  confirm is a strategy that genuinely clears the gate (the operator's goal); a falsify is
  an honest null that overturns a published JFQA cost-survival claim under realistic retail
  costs, out-of-sample extension, and proper deflation.
- It is cross-sectional SELECTION, the exact thing the carry-kill lesson endorsed, and it is
  additive: it is crypto, cross-sectional, and net-of-cost-POSITIVE where vanilla equity
  momentum was a null (a different RESULT, even though it is trend-family).
- It reuses the apparatus heavily (the Binance Vision loader, the cost model, the vendored
  PSR/DSR/CPCV/bootstrap/trial-registry stack) and the reproducible-free-data brand.
- It is the FIRST FITTED signal in the project. The CPCV + trial-registry + deflation
  machinery, degenerate for the three prior UNCONDITIONAL nulls, becomes genuinely LOAD-
  BEARING here. A fitted-model PASS that survives the multiplicity deflation is a far
  stronger result than any unconditional one.

## The four-lens review

- **Realist (PROCEED):** the replication is doable and bounded; free OHLCV from Binance
  Vision (the existing loader); heavy reuse. Either outcome is a win. Biggest concern: the
  paper's cost assumptions are optimistic and its sample ends May 2022 (pre-ETF), so the
  realistic post-2022 world may have decayed it (McLean-Pontiff: anomalies fall ~26% OOS,
  ~58% post-publication). That decay test IS the experiment.
- **Quant (PROCEED):** cross-sectional selection, additive; the breakeven headroom (~88 to
  141 bps/side vs ~35 to 69 bps realistic retail) is real and large, which is the single
  best survival signal on the shortlist. Biggest concern: it loads on momentum (a CMOM beta
  ~0.79), so it is trend-FAMILY; the defense is that the additivity is the RESULT (cost-
  surviving in crypto), not factor orthogonality. The multi-feature ML aggregation is a
  large trial space that the deflation must genuinely constrain.
- **Builder (PROCEED):** reuses the data loader, the cost model, and the scoring stack. New:
  a multi-coin universe loader (point-in-time, delisting-complete), the trend / technical
  feature set, the cross-sectional elastic-net aggregation, and the cross-sectional
  backtest. The fitted model introduces the first genuine OOS / CPCV requirement (zero new
  analytics LOC; the stack is reused). Biggest concern: the universe + the PIT liquidity
  selection are the schedule risk (survivorship and look-ahead must be handled at the
  source).
- **Growth (PROCEED):** replicating and stress-testing the single peer-reviewed crypto cost-
  survival claim under a realistic retail cost model + an OOS extension + proper deflation
  is a sophisticated, recruiter-grade narrative whichever way it lands. A confirm is a
  deployable edge; a falsify is a publishable correction of the literature. Biggest concern:
  the positioning must lead with the honest deflated number, never the paper's gross.

## The adversarial cross-check: PROCEED, the case is the caveat set

The strongest case against CTREND and its resolution:

1. **The paper's costs are optimistic and the sample is pre-ETF, so the edge may be
   decayed.** REAL and binding. This is precisely the experiment: replicate the published
   signal, apply the project's realistic retail cost model (not the paper's bps), extend
   out-of-sample to 2022-2026, and deflate. If it does not survive, the null falsifies the
   claim, which is an intended, recruiter-grade deliverable.
2. **It is momentum-adjacent (the portfolio already holds a momentum null).** Half-resolved.
   It is a different RESULT (cost-surviving, crypto, cross-sectional, ML-aggregated); the
   additivity argument is the result, not the factor family. The write-up frames it as "the
   one trend signal that does not die where vanilla momentum did, IF it survives my costs."
3. **The cross-sectional ML aggregation overfits (a large trial space).** REAL. The trial
   registry + event-time-purged CPCV + the DSR multiplicity deflation become LOAD-BEARING
   for the first time in the project; every feature-set, universe-size, quintile-width, and
   cost choice counts in the trial penalty, and a fitted PASS must survive it plus an
   adversarial cross-check (rule 1, the go-live fork).
4. **The liquid-universe selection biases the result (survivorship / look-ahead).** REAL.
   The universe is enumerated from the delisting-complete Binance Vision bucket (dead coins
   retained), and the liquidity selection is strictly point-in-time (the universe at time t
   uses only data up to t).

Verdict: the adversarial case is the binding CAVEAT SET, not a stop. The kill gate
adjudicates honestly and either outcome is a win.

## Decision

**Pivot to a faithful replication-and-stress of the CTREND crypto cross-sectional trend
factor.** Replicate the published trend signal (the technical feature set + the cross-
sectional elastic-net aggregation) on the liquid Binance Vision universe, apply the
project's REALISTIC retail cost model rather than the paper's optimistic bps, extend out-
of-sample to 2022-2026, and adjudicate with the net-of-cost Deflated Sharpe under event-
time-purged CPCV with the trial-registry multiplicity deflation. The headline is the honest
verdict: does the published cost-survival claim hold under a realistic retail cost model,
an out-of-sample extension, and proper deflation?

### The v1 specification

- **Data:** Binance Vision spot klines (free, reproducible, US-reachable, and delisting-
  complete for survivorship, so the universe can include dead coins). A liquid universe
  (top-N by trailing USD dollar-volume), selected strictly point-in-time. Weekly resampling.
  Caveat: a small CoinMarketCap (the paper's source) vs Binance-only basis.
- **Signal:** the CTREND technical / trend feature set aggregated cross-sectionally via an
  elastic-net, fit on past data only (a rolling / expanding window), predicting next-period
  returns, then sorted into quintiles. The exact feature list and the elastic-net protocol
  are PR2's design plan (faithful to the paper, verified against its methodology).
- **Cost + structure:** the project's `VenueCostModel` (a US-tradeable venue's taker fee +
  the measured spread), never the paper's optimistic bps. The retail-realistic headline is
  LONG-ONLY the top quintile (shorting the bottom-quintile alts is hard at retail; the paper
  shows the long leg carries much of the alpha); the academic long-short is the comparison.
- **Pre-registered kill criterion (frozen upfront):** net-of-all-cost Deflated Sharpe below
  0.95 out-of-sample, under event-time-purged CPCV with embargo, on the frozen trial count
  (every feature-set / universe-size / quintile-width / cost choice counts), on the held-out
  OOS window (2022 onward), on the LIQUID universe, means the published cost-survival claim
  does NOT hold at realistic retail costs: declare it a falsification and ship the honest
  null. A Deflated Sharpe at or above 0.95 means a strategy that genuinely clears the gate;
  it then requires an adversarial cross-check before belief (rule 1, the go-live fork:
  verify it is not a look-ahead / survivorship / cost-optimism artifact).

### Binding caveats

1. Reproduce and report the LIQUID-universe net number, not the headline thousands-of-coins
   gross; the survivable claim is liquid-only.
2. Use the project's realistic cost model, not the paper's optimistic bps; the kill reads the
   realistic cost.
3. The trial registry + CPCV + the DSR deflation are LOAD-BEARING (the first fitted signal);
   count every design choice, and a fitted PASS must survive the multiplicity deflation plus
   the adversarial cross-check.
4. The universe is point-in-time + delisting-complete (Binance Vision), with no survivorship
   or look-ahead; the liquidity selection at time t uses only data up to t.
5. Long-only-top-quintile is the retail-realistic headline; the long-short is the academic
   comparison.
6. Post-2022 decay (McLean-Pontiff) is the central risk; the OOS 2022-2026 extension is where
   the published claim is genuinely tested.

## Status

Accepted. This is Study 3 in the repo (joining the killed funding carry and the VRP null),
reusing the apparatus and the reproducible-free-data brand; the README will frame the repo
as a portfolio of kill-gate-tested crypto systematic strategies. The build proceeds, each
piece via the rule-1 process: PR1 the point-in-time multi-coin universe data layer, PR2 the
trend-feature signal + the cross-sectional aggregation (the first fitted model), PR3 the
backtest + the kill gate + the verdict. A Deflated-Sharpe PASS is a strategy that clears the
gate (cross-checked before belief); a FAIL is an honest falsification of the published cost-
survival claim. The next flip condition to watch is the OOS 2022-2026 window decaying the
edge below the bar, in which case the falsification is the headline.

## Amendment (2026-06-04, PR1 design verification)

The PR1 design review insisted the panel's data granularity be settled before any panel is
committed (it is expensive to redo), so the paper's exact construction was verified against
the published text (Fieberg et al., JFQA 2025). Findings that refine the v1 spec above:

- The 28 technical signals are computed on DAILY bars (a 14-day RSI, 3- to 200-day SMAs,
  daily volume and volatility indicators) even though the rebalance is WEEKLY (a fixed
  rolling 52-week fit predicting the next week, value-weighted quintiles). So the v1
  "weekly resampling" line is refined: the universe data layer stores DAILY price + volume
  and derives the weekly rebalance grid (returns + the PIT eligibility) from it. The
  committed reproducibility anchor is the daily panel; the weekly grid is a pure function
  of it.
- The aggregation is the cross-sectional combined elastic net (CS-C-ENet of Han, He,
  Rapach, Zhou 2024): per-signal cross-sectional univariate forecasts, then a pooled
  elastic net (L1/L2 mix 0.5, lambda by corrected AIC) selecting and averaging the
  positive-weight forecasts. This is PR2's spec.
- The paper's universe is a MARKET-CAP floor (>= USD 1M) with VALUE-WEIGHTED portfolios;
  the cost-survival claim PR3 tests is its Table 8 "top-100 most liquid" subset (Amihud).
  Binance Vision has no market cap, so PR1 screens by trailing USD DOLLAR VOLUME (top-N)
  and PR3 will equal-weight; these are the data-forced deviations already named in the v1
  spec and caveat 1, now explicit and carried as artifact caveats. Stablecoin/fiat pairs
  and leveraged tokens are excluded (a dollar-volume-ranked universe would otherwise be
  dominated by pegs; the paper's "coins" are not pegs or decaying derivatives).

The design + the per-finding resolutions are in docs/research/0002-ctrend-universe-design.md
and CHANGELOG.md.
