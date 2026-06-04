# ADR 0003: the cost model, the per-trade P&L, and the random-entry null

Status: Accepted (the design; ships with PR4a + PR4b).
Date: 2026-06-03.
Authors: Sam Doane (design plan + an independent senior-quant design review per
rule 1; the review grounded itself in the actual code and caught three
kill-gate-flipping issues, all resolved below).

## Context

This milestone is the kill gate. Rule 6: build the cost model FIRST and run a
random-entry NULL through it before any selection signal; if the carry is not
clearly better than the null after costs, there is no edge. The stress-test
verdict is binding: "the single most likely loss is the SPREAD, not the tail."
The cost must be parameterised to a genuinely US-tradeable venue (Kraken Futures,
Hyperliquid), not the Binance data venue. The pre-registered kill criterion is in
ADR 0001.

The trade: delta-neutral funding carry, long spot notional N, short the perp
notional N, hold H funding intervals, collect the funding the short receives,
close both legs. There is no spot/perp cross-margin (you fund both legs, the BIS
WP 1087 friction).

## The locked per-trade P&L (entry at funding event i, exit at i+H, per unit notional)

The design review verified the off-by-one against the real code:
`make_label_horizons` sets event i's horizon to `dt[i+H]`, so the CPCV-labeled
trade for entry i owns exactly the H settlements at indices `i+1 .. i+H`. The
simulator's funding window MUST be that same index set, so the null's return
series and the CPCV label are the same economic object.

- **Entry/exit timing convention (frozen):** entry is immediately AFTER the
  settlement at `dt[i]` (so `funding_rate[i]` is NOT collected); the first
  collected funding is `funding_rate[i+1]`; the trade closes at the settlement
  `dt[i+H]`. Pinned by an index-identity test (see Tests), not a comment.

- **Funding sign (frozen, finding 1, was the highest risk):** `funding_rate` is
  the standard perp funding rate where a POSITIVE rate means longs pay shorts. The
  delta-neutral book is SHORT the perp, so it COLLECTS positive funding:
  `funding_collected = + sum(funding_rate[i+1 .. i+H])`. This is pinned by an
  economic-direction fixture (a known-positive-funding case must yield a positive
  `funding_collected`), because `records.py` wording and the negative-default test
  fixtures make the sign a trap. The convention is asserted, never assumed.

- **Delta-neutral price P&L (static-notional, finding 4):**
  `spot_leg_pnl = (spot_close[x]-spot_close[e]) / spot_close[e]` (long spot),
  `perp_leg_pnl = -(perp_close[x]-perp_close[e]) / perp_close[e]` (short perp),
  `price_pnl = spot_leg_pnl + perp_leg_pnl`. This is the exact equal-NOTIONAL
  return-space basis-convergence term. v1 is buy-and-hold both legs with NO
  intra-hold rebalance, so the book is not delta-neutral through the hold and
  `price_pnl` is a static-notional APPROXIMATION whose bias is signed (short gamma
  on the basis). Binding: PR4a bounds `|price_pnl|` on the real BTCUSDT frame and
  reports its median/tails relative to median funding; if comparable, the proxy is
  not good enough and the kill number is flagged contaminated.

- **Costs (both legs, both sides):** per leg per side,
  `taker_or_maker_bps/10_000 + half_spread_bps/10_000`. Default execution is
  TAKER both legs both sides (conservative). A round trip pays the half-spread on
  entry AND exit on BOTH legs (= two full spreads), which is the "spread is the
  likely loss" made visible. `round_trip_cost = entry_cost + exit_cost`, always a
  positive outflow.

- **Financing / capital cost (finding 6, frozen):** because there is no
  cross-margin, the book ties up 2N of capital with an opportunity cost over the
  hold: `financing_cost = funding_capital_rate * (H * interval_hours / 8760)`,
  configurable (default a money-market rate). It is subtracted from net; at a
  multi-interval hold it can be the difference between a thin positive carry and
  zero. v1 sets a non-zero default and reports the result with it; setting it to
  zero requires stating the bias.

- **Net and tax:** `gross = funding_collected + price_pnl`;
  `net_pretax = gross - round_trip_cost - financing_cost`. **The DSR kill-gate
  headline reads the PRE-tax net-of-cost series** (finding 8): tax is a personal
  rate level-shift, not a property of the edge. After-tax is a deployment sidebar
  computed at the ANNUAL aggregate with within-year loss offset (short-term
  ordinary income, configurable rate), NOT per-trade gains-only (which would
  overstate the drag). Both are reported.

## The null and the scoring (PR4b)

- **Headline null = the always-on passive carry** (every eligible event is an
  entry), the object the early gate is literally about. A random-subset null
  (seeded `random.Random`, matched trade count to a future signal) is a secondary
  comparator.

- **Cost is booked where incurred, NOT amortised (finding 2, Critical).**
  Amortising the round-trip cost evenly across the H intervals smears the
  entry/exit cost lumps, which shrinks the realized skew/kurtosis the Deflated
  Sharpe penalises (`sigma_sq = 1 - gamma_3*SR + (gamma_4-1)/4*SR^2`) and
  mechanically INFLATES the DSR; it is also economically wrong (you pay cost per
  turnover, not per interval). The headline per-period series books the full
  round-trip cost on the interval it is incurred. A diagnostic reports the
  amortised-vs-lumpy moments so the inflation is visible, and the kill decision
  reads the LESS favourable.

- **Overlap-corrected significance (finding 9, Critical-adjacent).** An always-on
  carry with H>1 has overlapping holds, so consecutive per-interval returns
  autocorrelate and a naive `T` overstates significance in
  `dsr(z = (sr_hat-sr_0)*sqrt(T-1)/...)`. The headline DSR is computed on a
  NON-OVERLAPPING return series (one observation per H intervals, genuinely
  independent trades); the overlapping always-on series is reported separately.
  The vendored `politis_white_block_length` justifies the effective sample.

- **Event-time-purged CPCV embargo >= H (finding 3, Critical).** The vendored
  `cv.py` embargo is `floor(n_obs * embargo_pct)`, blind to H. With H-event
  forward overlap, obs within H of the test block leak unless the embargo covers
  them. The CPCV glue forces `embargo_pct >= H / n_obs` and asserts
  `_embargo_count(n_obs, embargo_pct) >= horizon_events` before splitting.

- **Honest deflation (finding 10).** The random-entry null is a CONTROL, recorded
  under a separate `strategy_family` so its seed variance does not pollute the
  real-strategy `v_sr`. At this pre-signal milestone `naive_effective_n = 1`, so
  the DSR degenerates to `PSR(sr_star=0)` per the vendored code; the kill-gate
  number at the cost-model milestone IS PSR(0). Multiple-testing deflation
  activates only when the signal knob list is frozen (a later ADR).

- **Funding-sign-regime bucket (finding 11).** The per-period series is reported
  decomposed by funding sign (positive-funding vs negative-funding intervals),
  with the drawdown conditional on the negative-funding regime, so a paying regime
  is not averaged into a collecting regime as a misleadingly positive mean.

## The early economic gate (kill criterion part 1) + the spread

- Per (venue, H): does the median funding collected over the hold exceed the
  amortised round-trip cost for the passive always-on carry? `break_even_cost =
  median(gross_per_trade)` is the round-trip cost at which net carry crosses zero;
  the exhibit reports `median_funding`, the round-trip cost, `break_even_cost`,
  `realized_cost`, and `headroom`, per venue. Reported across Kraken Futures,
  Hyperliquid, and the non-tradeable Binance/OKX reference, so the gate is a
  venue-cost-sensitivity surface.

- **The spread (finding 7, binding).** The stress-test names the spread the most
  likely loss, so the kill gate must not rest on a soft assumption. v1 uses a
  deliberately CONSERVATIVE (high) half-spread per venue, the gate result is
  labelled provisional-pending-measured-spread, and the kill decision reads the
  conservative number so a soft input cannot manufacture a false pass. Measuring
  the median half-spread from the free, reproducible Binance Vision `bookTicker`
  dataset (with a documented venue adjustment) is the immediate follow-up that
  replaces the conservative assumption.

## Deferred (stated, per finding 12): slippage / partial-fill beyond top-of-book,
and the order-book-walk impact, which belong to the capacity-curve milestone (the
size at which the spread/impact eats the carry is the project's declared honest
headline). v1 assumes full fill at top-of-book plus the half-spread.

## The kill-decision discipline (frozen)

The kill decision reads the LESS favourable of (amortised vs lumpy cost) and
(assumed vs measured spread). No smoothing or soft input may manufacture a pass.

## PR split + the central invariant

- **PR4a (per-trade math foundation, no RNG/IO):** `execution/errors.py`,
  `execution/cost.py` (the per-venue `VenueCostModel` with cited fee schedules),
  `execution/carry.py` (the single-trade simulator + the vectorised batch),
  `execution/scoring.py` (the reuse adapter to `analytics/sharpe.py`), and the
  math tests. Ships the ADR math + venue + convention sections.
- **PR4b (the null + the exhibit + the gate):** `strategy/null.py`,
  `execution/exhibit.py`, `scripts/run_null_gate.py`, the CPCV embargo>=H glue,
  the trial-registry plumbing, the funding-sign decomposition, and the first
  net-of-cost number.
- **The kill_gate-marked central invariant:** the funding-window-alignment test
  asserts (a) the funding index set equals `range(i+1, i+H+1)`, (b) it is
  identical to the indices implied by the CPCV label `dt.shift(-H)`, and (c) the
  per-trade `net_pretax` recomputed from the frame equals the per-period series
  summed over the trade's intervals (a P&L-conservation cross-check). Its failure
  means the net number and the deflated-Sharpe validation describe different
  trades, voiding the kill gate.

## Status

Accepted. PR4a implements the per-trade math with findings 1, 4, 5, 6 (the sign
fixture, the static-notional bound, the index-identity invariant, the financing
term). PR4b implements findings 2, 3, 7, 8, 9, 10, 11 (lumpy cost, embargo>=H,
conservative/measured spread, pre-tax PSR(0) headline, non-overlapping T, the
control trial family, the sign-regime bucket) and produces the first kill number.
