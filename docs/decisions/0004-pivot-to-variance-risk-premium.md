# ADR 0004: pivot to the crypto variance risk premium (after the carry kill)

Status: Accepted.
Date: 2026-06-04.
Authors: Sam Doane (strategy-pivot fork made under the project's full-authority
scoping mandate, with a four-lens review (realist, quant, builder, growth) plus an
adversarial cross-check per rule 1, and a verified week-1 data-access spike).

## Context

The first strategy, the naive delta-neutral crypto funding carry, was KILLED
honestly (ADR 0003 + the kill-gate run): net-of-cost Deflated Sharpe ~0 on every
US-tradeable venue and horizon at the conservative 2N capital charge. That is the
intended, acceptable null. The standing rule on a kill is NOT to stop and polish the
null write-up but to read the research, learn the algorithms, survey GitHub, and
PIVOT to a different strategy (the kill itself is a clue, not a dead end). The carry
kill pointed two ways: "any edge must come from selection," and (from the BIS Crypto
Carry evidence) the spot-ETF arbitrage capital has compressed the basis premium the
carry harvested (a DiD of ~36% on exchanges, ~97% on CME; carry negative in 2025).

The binding constraints are unchanged from ADR 0001 and are what disqualified the
prior alternative track: the data must be FREE, reproducible, and US-reachable (the
reproduce-from-a-clone brand); the strategy must plausibly survive retail costs OR
yield a rigorously-bounded honest null; it must be ADDITIVE to a portfolio that
already holds an equity-momentum null (the sibling project) and this crypto
funding-carry null; and it must be recruiter-impressive through rigor, never a hyped
backtest. The vendored PSR/DSR/CPCV/bootstrap/trial-registry stack and the
cost-model-first / random-entry-null / kill-gate discipline are reused.

## The candidate research

Three independent research passes (a candidate generator, a deep-dive on the
selective-carry next step, and an adversarial breadth check) surveyed the 2023-2026
literature, GitHub, and practitioner sources. The shortlist and verdicts:

- **Crypto variance risk premium (VRP)** [SELECTED]. Implied variance persistently
  exceeds subsequent realized variance in BTC/ETH; the gap compensates option
  sellers for bearing variance/jump risk. The premium is structurally LARGE (BTC VRP
  ~14% annualized vs ~2% for equities), which is the decisive fact: it is roughly
  the one crypto premium big enough to make the kill gate a genuine both-ways test
  rather than a foregone cost-driven null. It is maximally ADDITIVE (a
  volatility-insurance premium, orthogonal to both the momentum and the carry
  nulls), and it recovers the intellectual content of the equity-VRP / vol-desk
  route (Track A) that ADR 0001 deprioritized purely for data reasons, now on data
  that IS reproducible.
- **Selective / cross-sectional funding carry** [rejected]. Harvests cross-coin
  funding dispersion (an order of magnitude larger than the BTC level) and the legs
  partly self-finance, so it is structurally distinct from the killed level-carry.
  But it is low-conviction ("more carry" the day after carry was killed), the honest
  net edge ceiling is modest, the alt legs carry a worse liquidation/depeg tail, and
  the alt-leg round-trip cost is a multiple of the BTC cost that already killed the
  trade. (Useful finding: the survivorship trap is BOUNDABLE because Binance Vision
  is delisting-complete for Binance perps, with dead symbols like LUNA/FTT retained,
  enumerable from the bucket itself rather than the live API.)
- **Short-term reversal as a cost-threshold measurement** [fallback]. Cheapest to
  build, reuses the existing klines + cost harness; the honest deliverable is the
  break-even cost at which 1-day reversal flips sign. Lower additivity. Retained as
  the FALLBACK if the VRP data spike had failed.
- **Perp factor-zoo net-of-cost replication** [rejected]. Best data fit but overlaps
  the momentum null on the factor axis; low marginal range.
- **AVOID**: cross-sectional momentum (it is the equity-momentum null this portfolio
  already holds, and its only crypto-specific alpha lives in an untradeable
  altcoin-short leg); on-chain/DEX signals (fail out-of-sample, not in the data
  layer); intraday/day-of-week seasonality (a documented false-discovery null);
  cross-venue lead-lag (HFT-competed, and the geo-block makes a US retail trader the
  follower who cannot touch the leading venues).

## The week-1 data-access spike (verified 2026-06-04 from this machine, a US IP, stdlib only)

The pivot's load-bearing data claims were verified before committing, mirroring the
ADR 0001 track-selection spike:

- **Deribit DVOL implied-vol index: FREE, keyless, US-reachable.**
  `public/get_volatility_index_data` returns daily OHLC for BTC and ETH; history
  confirmed back to 2021-04-01 (the documented inception). This is the
  fully-reproducible measurement input; realized variance comes from the existing
  Binance Vision klines. A static CSV mirror exists as a CI fixture / fallback.
- **Tardis first-of-month free Deribit datasets: reachable, keyless.** The Deribit
  `options_chain` and `derivative_ticker` CSVs download from a US IP (HTTP 200). The
  full options-chain day is large (~1 GB), so the loader will STREAM and extract the
  near-the-money snapshot it needs rather than cache the raw gigabyte; the chains are
  free only for the FIRST day of each month, which constrains the tradeable backtest
  to a low-frequency (monthly-snapshot, hold-to-expiry or weekly-rehedge) design.

Both flip conditions about data reachability are therefore cleared.

## The four-lens review

- **Realist (PROCEED, medium-high):** the index-level measurement is unambiguously
  doable and cannot be an artifact (a published index minus a checksummed realized
  series). The tradeable layer is doable at monthly cadence precisely because it
  cannot pretend to be more. Biggest concern: the peso/sample-path problem (a
  2021-2026 window may under-sample the catastrophic tail), so the headline must be
  the premium plus the realized tail losses in the crashes that ARE in-sample, never
  a short-vol Sharpe.
- **Quant (PROCEED, high):** the VRP is a genuinely different premium (the price of
  insurance against realized-variance spikes; gamma/jump risk, not financing/
  liquidation risk) and is near-uncorrelated with both existing nulls. The
  measurement layer is not too thin if done rigorously (matched-horizon RV, the
  forward-vs-trailing look-ahead distinction, regime decomposition, overlapping-
  horizon standard errors reusing the ADR 0003 finding-9 machinery). Biggest concern:
  the measurement-vs-tradeable seam must be kept explicit (Layer i measures the
  premium daily; Layer ii tests a specific low-frequency proxy of harvesting it).
- **Builder (PROCEED, high):** the effort is proportionate and reuses heavily, ~900
  to 1,300 new LOC over ~2.5 to 3.5 weeks. New: a stdlib Deribit DVOL source (mirrors
  `okx.py`), a realized-variance estimator on existing klines, a Tardis monthly-chain
  loader (the only true greenfield surface), and a delta-hedged-option cost model
  extending the existing `VenueCostModel`. Zero new analytics LOC (the stack is
  reused verbatim). Biggest concern: the option-chain loader is the schedule risk
  (more schema + failure modes than funding rows); it needs an option-leg
  P&L-conservation invariant analogous to the carry index-identity test.
- **Growth (PROCEED, high):** a third orthogonal premium-type plus a new options/vol
  competency converts the portfolio narrative from "ran the same null" to
  "systematically mapped three orthogonal premia across two asset classes with one
  reproducible apparatus." The Track-A-closure story (the reproducibility constraint
  drove the research design rather than chasing prestige data) is sophisticated.
  Biggest concern: short vol is the most content-farmed retail strategy, so the
  positioning discipline must be stricter than for carry: lead with the measurement
  and the kill, never let "premium" appear without "and here is the insurance you
  sold."

## The adversarial cross-check: PROCEED, the case reshapes the deliverable

The strongest case against VRP, and its resolution:

1. **The peso problem makes a short-vol Sharpe meaningless and the kill gate cannot
   see it** (the DSR penalises only the skew/kurtosis IN the sample, not the missing
   left-tail mass). REAL, and binding: the headline is therefore NOT a short-vol
   Sharpe; the DSR is reported necessary-not-sufficient, and the deploy verdict rests
   on the in-sample crash losses plus a stated peso-adjustment. This converts the
   weakness into the study's thesis (the same move as the ADR 0003 funding-sign
   regime conditioning).
2. **The free data supports a measurement, not a tradeable result** (continuous
   chains are not free; monthly snapshots give few post-ETF observations, too few for
   a credible CPCV). REAL: the tradeable layer is therefore scoped as a measurement-
   grade, cost/peso-bounded test that is EXPECTED to be an honest null, which the
   charter explicitly accepts. Pre-register that as the expected outcome so a null is
   logged as hitting the thesis, not as a disappointment.
3. **DVOL is BTC/ETH-only, so the cross-sectional breadth the apparatus is built for
   is gone.** Half-wrong: the term-structure (multiple expiries) and the regime axis
   supply real econometric breadth without a name cross-section, and the trial
   registry's honest output on a small hypothesis set is calibrated humility, not
   over-engineering.
4. **Option-selling cost modeling from monthly snapshots is too lossy** (the
   path-dependent rehedge slippage that dominates short-vol cost is unobservable in
   first-of-month chains). REAL and binding: the un-measurable rehedge cost is named
   as the dominant un-modeled term (the explicit analogue of the carry static-
   notional `price_pnl` contamination guard); a gate that rests on a soft rehedge
   assumption is disqualified.

Verdict: the adversarial case is fatal to "VRP as a short-vol strategy backtest" and
decisive that the tradeable layer is likely a cost/peso-bounded honest null. It is
NOT fatal to "VRP as a reproducible measurement plus an honestly-bounded tradeability
verdict," which is the deliverable the charter wants. The strikes are the binding
caveats, not a stop.

## Decision

**Pivot to a reproducible crypto variance risk premium study, in two explicitly
separated layers:**

- **Layer i (the reproducible measurement floor):** the BTC/ETH VRP at daily
  resolution = a matched-horizon implied variance (Deribit DVOL, 30-day) minus
  realized variance (from the existing Binance Vision klines), with its term
  structure, regime decomposition, and overlapping-horizon standard errors. Fully
  reproducible from free data; ships regardless of the tradeable verdict.
- **Layer ii (the cost-gated tradeable test):** whether a delta-hedged short-variance
  / option-selling proxy survives realistic retail costs (Deribit option fees +
  bid-ask + the perp delta-hedge leg), at the monthly-snapshot cadence the free Tardis
  chains allow, under regime conditioning and explicit tail accounting, scored with
  the kill-gate discipline. **Pre-registered expected outcome: a cost/peso-bounded
  honest null** (an accepted, intended deliverable per ADR 0001).

The fallback (if the build stalls on the option-chain loader) is the short-term
reversal cost-threshold measurement.

### Binding caveats (these keep the study honest)

1. **The headline is the VRP measurement plus the regime-conditional tail-loss table,
   NEVER a short-vol Sharpe.** The DSR is necessary-not-sufficient, reported with the
   explicit caveat that it cannot price the out-of-sample crash; the deploy verdict
   rests on the in-sample crash losses plus a stated peso-adjustment.
2. **Layer i and Layer ii are explicitly separated objects** (the analogue of the
   ADR 0003 `funding_collected`-vs-`gross` split); the write-up states that the daily
   measurement does not validate the low-frequency tradeable claim.
3. **Cost-first discipline carries over verbatim, and the un-measurable path-rehedge
   cost is named as the dominant un-modeled term** (the analogue of the carry static-
   notional contamination guard); the option spread uses the conservative-or-measured
   rule, cost is booked lumpy where incurred, and the kill reads the less favourable.
4. **Reproducibility plumbing is identical to the existing layer**: DVOL + the Tardis
   monthly snapshots SHA256-stamped into the manifest, the DVOL CSV mirror committed
   as an offline CI fixture, stdlib-only loaders, and an option-leg P&L-conservation
   invariant asserted so the option P&L cannot silently lie.
5. **A cost-model-first, signal-last build order** (rule 6), reusing the vendored
   analytics/validation stack and the kill-gate machinery verbatim.

### Pre-registered kill criterion (frozen upfront; this study)

The study ships regardless of outcome. For REAL-MONEY deployment of a short-variance
implementation: net-of-all-modeled-cost Deflated Sharpe below 0.95 out-of-sample,
under event-time-purged CPCV with embargo on the frozen trial count, on the held-out
post-ETF period, OR an in-sample crash loss plus peso-adjustment that a retail
account could not survive, means declare non-viable and ship the honest null. The
measurement floor (Layer i) is reported either way as the primary deliverable.

## Status

Accepted. The build begins under this ADR with the data layer (a Deribit DVOL source
+ the realized-variance estimator + the Tardis monthly-chain loader), then the cost
model, then the random-entry null, then the measurement and the gated tradeable test,
each via the rule-1 process. The week-1 data spike is done and passed; the next flip
condition to watch is the post-ETF tradeable sample being too small to deflate, in
which case Layer ii is reported descriptively and the measurement is the headline.

Build progress: Layer i (PR5a) is built and the first BTC VRP measured and positive
(mean 0.087, phase-0 95% CI [0.033, 0.119] clearing zero, 70% of days positive, a
pre-ETF 0.101 to post-ETF 0.059 decay). PR5b ships the committed Layer-i deliverable
(`artifacts/vrp_measurement.json` + the `docs/figures/` figures rendered from it) and
closes caveat 4's reproducibility plumbing for the live DVOL series: because DVOL is
live/as-of with no published checksum, a re-fetch is not guaranteed byte-identical, so
the exact daily closes used are committed as small CSV fixtures (`tests/data/`,
`kind = "reproducibility_fixture"`) whose SHA256 is stamped into the manifest, and an
offline test rebuilds the committed headline from them. This is the deliberate
counterpart to the immutable-dump model (gitignore the bytes, re-fetch, verify): for a
mutable source the bytes are committed and the stamp makes them tamper-evident. Layer
ii (the cost-gated tradeable test) is next, cost-model-first.
