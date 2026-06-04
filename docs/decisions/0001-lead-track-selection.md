# ADR 0001: lead-track selection (the week-1 data-access spike)

Status: Accepted.
Date: 2026-06-03.
Authors: Sam Doane (lead-track decision made under the project's full-authority scoping mandate, with a four-lens review and an adversarial cross-check per project rule 1).

## Context

Project RiskPremia must choose between two pre-scoped tracks (full detail in
`docs/STRATEGY-BRIEF.md`). The choice is a genuine fork, so it runs the rule-1
process: a four-lens review (realist, quant, builder, growth) plus an
adversarial cross-check, fed the same evidence dossier. The project scope fixes
the decision rule:

- **Track A** (single-name earnings Variance Risk Premium measurement study)
  requires BOTH (i) confirmed USC WRDS / OptionMetrics IvyDB access AND (ii) a
  career target that is a pure options/vol desk (Jane Street, SIG, Optiver,
  Citadel Securities).
- **Track B** (crypto perpetual-futures funding carry, delta-neutral) is the
  lead otherwise: if WRDS is unavailable, OR reproducibility + real money at
  small size + a faster first result is the priority, OR the target is
  systematic / relative-value / crypto / multi-strat.

## The spike findings (run 2026-06-03 from this machine, a US IP)

### Track A, WRDS / OptionMetrics

- **Zero existing WRDS setup on the machine.** No `WRDS_*` env vars, no
  `~/.pgpass` or `.wrds` config, the `wrds` Python package is not installed, and
  there are no WRDS / OptionMetrics / IvyDB breadcrumbs anywhere under
  `OneDrive\Desktop\AI Projects`.
- **The entitlement is not confirmable without the user's WRDS login.** Confirming an
  OptionMetrics IvyDB entitlement requires logging into WRDS with the user's
  personal credentials (which the author does not hold and which must not be requested as a
  secret per rule 7) and checking the subscription. OptionMetrics is a separate,
  expensive WRDS entitlement that many university base subscriptions exclude;
  student summer-access and entitlement scope are both uncertain.
- **Even if entitled, the data is non-redistributable.** OptionMetrics raw data
  cannot be reshipped to a public repo, so only derived / aggregated artifacts
  could be committed. An external reviewer therefore could not regenerate the
  headline vol-surface numbers from the repo. This structurally breaks the
  reproducibility guarantee that is the project's brand (the sibling pit-backtest
  headline is a clone-and-regenerate honest momentum null).

### Track B, crypto funding data

Empirically probed end-to-end; the funding clock and realized series are real:

- **OKX** (`/api/v5/public/funding-rate-history`, `/market/history-candles`):
  WORKS from the US IP, no key. Returns the realized funding series with
  `realizedRate`; BTC-USDT-SWAP candles go back to at least 2020-09-12. Good for
  a live forward paper-trade.
- **Hyperliquid** (`/info` `metaAndAssetCtxs`): WORKS, on-chain perp DEX, no
  geo-block, 100% reproducible by anyone; but only ~2023+ history (no pre-ETF
  baseline).
- **Binance Vision S3 dumps**
  (`s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=...`): WORKS from
  the US IP and lists checksummed monthly funding zips from 2020-01
  (`BTCUSDT-fundingRate-2020-01.zip` + `.CHECKSUM`). This is the long-history,
  content-addressable, fully reproducible source.
- **Honest venue-access finding:** the LIVE Binance (`fapi.binance.com`) and
  Bybit REST APIs are GEO-BLOCKED from the US IP ("Service unavailable from a
  restricted location"; CloudFront country block). The data dumps and OKX /
  Hyperliquid are not. A US-based retail trader cannot use Binance/Bybit perps
  live, which is real venue-access friction that feeds the risk register.

## The four-lens review (unanimous)

All four members chose **Track B at HIGH confidence**, and all four independently
returned the SAME flip condition: the candidate confirms BOTH an active
WRDS/OptionMetrics entitlement AND a pure options/vol-desk career target.

- **Realist:** Track B is the only one a retail person can actually run with real
  money; the data is reachable and reproducible from a US IP; Track A fails on
  two independent grounds (the options spread eats essentially the whole premium,
  and the GPP demand rationale is wrong-signed for single names). Biggest risk:
  post-ETF decay + fees + the funding-sign-flip tail may compress net carry to
  near zero (a friction-and-decay null).
- **Quant:** Track A fails the entry gate before any statistics run, because
  non-redistributable data makes a reproducible null impossible, and a
  non-reproducible null is just an assertion; Track A's premium is also
  structurally confounded by borrow/recall fees. Track B is a genuinely
  economically-motivated premium (BIS WP 1087) with a clean separable cost model
  and a crisp capacity boundary, and its decay is itself the honest headline.
- **Builder:** Track A breaks the brand at the data layer (a reviewer
  structurally cannot regenerate the headline) and is gated on an unconfirmed
  entitlement; Track B's checksummed dumps are byte-for-byte reproducible, and
  600 to 1,000 LOC over 2 to 3 weeks beats 2,000 to 3,000 over 6 to 8. Biggest
  risk: the US geo-block needs a multi-venue data layer from day one.
- **Growth:** Track B preserves the differentiating brand (clone-and-regenerate
  reproducibility) and demonstrates broader, rarer solo skills (risk
  engineering, regime gating, counterparty/liquidation tail, honest decay
  quantification). Biggest risk: "vanilla carry" reads as hype, so the README
  headline must be the decay null + reproducibility, never carry returns.

## The adversarial cross-check (adversarial audit): ENDORSE-WITH-CAVEATS

The adversarial cross-check confirmed the verdict but flagged that the 4-0 unanimity is
partly over-determined (every lens keys off the same dominant fact, the
non-redistributable data), and surfaced caveats that are now binding on the
build:

1. **(Most important) Cost-model against a US-TRADEABLE venue, not the
   Binance-data venue.** The premium's existence and decay are measured on the
   long Binance Vision history, but the cost model, the capacity curve, and the
   kill gate must be parameterised to a venue a US retail trader can actually use
   (the adversarial cross-check named Kraken / CME / Hyperliquid / Coinbase). Otherwise the kill
   gate runs against costs that cannot be incurred. Make "does net two-leg carry
   survive the post-ETF basis at retail fees on that venue" the explicit early
   kill check.
2. **Restructure the user escalation:** career target is the PRIMARY, always-
   asked question (it reframes Track B even if A stays dead, and picks which
   "also examined" section gets written); WRDS is a conditional follow-up only if
   the answer is a pure vol desk.
3. **Portfolio-additivity:** a second reproducible honest-leaning study must show
   RANGE, not repeat the momentum null. RiskPremia is additive because it is a
   different market (crypto), a different premium (carry, not a maximally-
   arbitraged equity factor), genuinely retail-tradeable, and the contribution is
   the risk engineering + decay quantification, not a backtest number.
4. **Crypto landmines for the risk register** (none raised by the four-lens review): US
   venue access / backtest-venue mismatch; net carry after BOTH legs' financing +
   capital tie-up; exchange-solvency fat tail (FTX-class); coin/venue
   survivorship in the Binance Vision instrument set (only survivors are dumped).

The steelman the adversarial cross-check preserved for Track A: a non-reproducible honest null
is still impressive to a vol desk that HAS OptionMetrics and can re-run it
internally. That is exactly why career target is the right gate, and why Track A
is demoted, not deleted.

## Decision

**Track B (crypto perpetual-futures funding carry, delta-neutral) is the LEAD
track**, on the decision rule's "no confirmed WRDS, reproducibility + real-money
+ speed priority" branch, validated by a unanimous four-lens review and an
endorse-with-caveats adversarial cross-check. Track A is demoted to a one-section "I also
examined this; here is the friction-adjusted result and why I deprioritized it,"
which itself demonstrates kill-early judgment.

One question is escalated to the user (non-blocking; the build proceeds): the
career target. If and only if the user confirms a pure options/vol-desk target
AND a verified live OptionMetrics entitlement, the decision rule promotes Track A
and Track B becomes the "also examined" section. Absent that dual confirmation,
the reproducibility break alone is disqualifying for Track A as the lead.

### Locked decisions (binding on the build)

1. **Lead track: B.** Track A is the friction-adjusted contrast section.
2. **Cost model FIRST, then a random-entry NULL, then any signal** (rule 6,
   inverted build order). The cost model charges both legs: exchange taker/maker
   fees, the half-to-full bid-ask spread on entry AND exit, and the funding paid
   or received on the 8h clock, net of short-term-ordinary-income tax.
3. **Cost model + capacity + kill gate are parameterised to a genuinely
   US-tradeable venue.** The Binance Vision long history measures the premium and
   its decay; the tradeable-venue parameters gate deployment. Both are reported.
4. **Multi-venue data layer from day one:** Binance Vision S3 (long history,
   reproducible) + OKX (live, US-reachable) + Hyperliquid (on-chain). Raw
   snapshots SHA256-stamped in `data/snapshots/manifest.toml`.
5. **Regime gate is a risk-OFF circuit breaker only** (stand aside when funding
   is thin or tail risk is elevated), never a lean-in signal, mirroring the
   Track-A discipline on the Bollerslev-Tauchen-Zhou gate.
6. **Risk register** carries, at minimum: US venue access / backtest-venue
   mismatch, both-legs financing + capital tie-up, exchange-solvency fat tail,
   coin/venue survivorship, funding-sign-flip, depeg, withdrawal halts.
7. **Multiple testing:** freeze the knob list, log every configuration to the
   vendored trial registry, deflate with DSR + Harvey-Liu BHY FDR. If DSR clears,
   suspect an undercounted trial ledger before believing the edge.
8. **Positioning:** title it a measurement study; lead the README with the decay
   quantification + the reproducibility claim + the kill criterion, never carry
   returns; chain explicitly to the sibling momentum null.

## Pre-registered kill criterion (rule 4, declared UPFRONT)

The study SHIPS regardless of outcome (an honest null is an acceptable, intended
deliverable). The kill criterion gates REAL-MONEY DEPLOYMENT, not whether the
write-up is worth doing. Two gates, frozen now, before any signal exists:

- **Early economic gate (first build days, cost-model + random-entry null).** If,
  on the held-out post-spot-ETF regime (2024-2026), the median 8h funding
  collected on the US-tradeable venue does not exceed the modeled round-trip cost
  amortised over the holding period for a passive always-on carry, the naive
  carry is dead after costs. Any surviving edge must then come entirely from
  selection / regime-timing, which RAISES the bar; this is documented, and the
  break-even-cost exhibit makes it visible.
- **Primary kill gate (deflated, out-of-sample).** Declare the strategy
  NON-VIABLE for real-money deployment, and write it up as an honest null, if the
  net-of-all-modeled-cost (US-tradeable-venue fees + both-leg spread + funding +
  short-term tax) **Deflated Sharpe is below 0.95 out-of-sample**, under
  event-time-purged CPCV with embargo, on the FROZEN trial count, on the held-out
  post-ETF period. (0.95 is the same viability bar the sibling project used; it
  is a deploy/no-deploy line, not a study-worth-shipping line.)

If a gate is hit, recommend killing plainly and ship the honest null; do not
soft-pedal.

## Status

Accepted. The build begins under this ADR: the data layer + the cost model are
the first milestones (each via Plan -> design reviewer -> implement -> post-implementation
reviewer, per rule 1). The career-target question is escalated to the user in
parallel and does not block the scaffold or the cost-model-first work.
