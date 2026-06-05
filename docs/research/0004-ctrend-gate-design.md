# 0004: the CTREND net-of-cost gate (Study 3, PR3)

The design plan for the CTREND backtest, kill gate, and verdict. This PR is the
pre-registered test in ADR 0005: does the CTREND cost-survival claim hold on the liquid,
point-in-time Binance Vision universe after realistic retail costs, a 2022+ OOS extension,
and the trial-registry Deflated Sharpe penalty?

## Kill criterion

The frozen gate is unchanged from ADR 0005:

Net-of-all-cost Deflated Sharpe below 0.95 on the held-out 2022+ window, on the liquid
universe, under event-time-purged CPCV with an embargo at least equal to the one-week
holding horizon, and with the frozen trial count means the published cost-survival claim is
falsified at realistic retail costs. Ship the honest null. A value at or above 0.95 is a
surprising pass and must be attacked for look-ahead, survivorship, cost optimism, and
multiplicity before belief.

The retail headline is the long-only top quintile. The academic top-minus-bottom
long-short is reported as a separate comparison, with the bottom-quintile short leg marked
as hard to trade at retail. A long-only failure is a retail deployability failure. It is not
overclaimed as a direct falsification of the paper's long-short result unless the
long-short result also fails its own net gate.

## Inputs

- Daily panel: `tests/data/ctrend_daily_panel_usdt.csv.gz`, read with
  `ctrend.fixtures.read_daily_panel`.
- Weekly grid: `build_weekly_panel(daily)`.
- Liquid universe: `pit_eligible(weekly, top_n=100, lookback_weeks=4,
  min_history_weeks=8)`.
- Forecasts: recomputed, never committed, with
  `ctrend_forecasts(daily, weekly_eligible, fit_window=52, n_quintiles=5)`.
- Holding return: `forward_return` only. This is the return over `(week_end, next_week_end]`
  and is the only credited return.
- Cost model: the spot leg of `VenueCostModel`, using `leg_cost_fraction(leg="spot",
  taker=...)` from the US-tradeable models in `execution.cost.TRADEABLE_VENUES`. CTREND
  trades spot coins only and does not use the carry model's perp leg. The artifact reports
  every tradeable venue so the assumption is visible.

## Portfolio construction

Each week after burn-in:

1. Sort eligible coins into quintiles with `assign_quintiles`.
2. Long-only portfolio: equal-weight the top quintile.
3. Long-short portfolio: equal-weight long top quintile and equal-weight short bottom
   quintile, with 50 percent gross on each side so the return is `0.5 * top - 0.5 * bottom`.
   This keeps the return base at one unit of capital for the academic comparison.
4. Compute portfolio turnover against the previous week's target weights:
   `sum(abs(w_t - w_{t-1}))`. Missing names have zero target weight.
5. Charge cost on the turned-over spot notional:
   `turnover * (spot fee + spot half spread)`, where the one-side spot cost comes from the
   selected `VenueCostModel` and uses taker execution for the conservative headline.

The first scored week pays entry turnover from cash to the initial target portfolio. The
headline missing-return policy is conservative: if a selected coin has no realized
`forward_return` even though the week is otherwise scorable, it is treated as a delisting
loss of -100 percent and counted in the artifact. Only a week where all selected returns
are unavailable is dropped as not yet realized. A favourable sensitivity that drops missing
constituents and renormalizes the remaining names is recorded in the trial ledger; it does
not drive the verdict.

## Scoring

The OOS scoring window starts at 2022-01-01. For each return series:

1. Build a weekly net return series after costs.
2. Compute realized moments with `execution.scoring.return_moments`.
3. Deflate the sample size with `execution.scoring.effective_sample_size`.
4. Create `make_purged_cpcv(n_obs, horizon_events=1)` and actually score each CPCV split's
   purged test fold. The gate statistic is the minimum split DSR, not merely the full OOS
   weekly-series DSR. This is deliberately conservative and prevents a single favourable
   regime mix from manufacturing a pass.
5. Record the realized trial set through `TrialRegistry`. The frozen naive effective count
   for PR3 is 8: portfolio form (long-only versus long-short), execution style (taker
   versus maker sensitivity), and missing-return treatment (delisting-loss headline versus
   favourable drop-and-renormalize sensitivity). The Sharpe cross-section from those eight
   realized variants supplies `v_sr`; `analytics.sharpe.dsr` supplies each portfolio's
   Deflated Sharpe.

The retail headline verdict reads the long-only top-quintile, taker, delisting-loss CPCV
minimum DSR. The long-short result is not allowed to rescue a failing retail headline.

## Artifact

Commit `artifacts/ctrend_gate.json` as a deterministic JSON artifact:

- schema version, study name, OOS window, viability bar, and verdict
- panel content hash and signal/cost knobs
- venue cost table, including fee, spread, and provisional flag
- long-only and long-short gross and net summaries
- weekly net return series for both portfolios
- CPCV settings, split DSRs, and trial-registry count
- missing-return counts and the sensitivity ledger
- a forecast or weekly-series hash as an audit fingerprint
- caveats carried from ADR 0005

The JSON is regenerated by `scripts/run_ctrend_gate.py`.

## Tests

- Unit tests for turnover and cost booking, including the first-week entry cost.
- Unit tests that the gate verdict is determined by the long-only DSR.
- An offline reproduction test that rebuilds `artifacts/ctrend_gate.json` from the
  committed daily panel and checks the verdict and headline numbers within a documented
  tolerance.

## Expected outcome

PR2 already showed the long-only top quintile loses gross in 2022+ before costs. The
expected PR3 outcome is therefore a retail long-only falsification after costs. That is a
successful deliverable if the artifact and write-up state it plainly. The current spot
spread model is a low-cost favourable assumption for top-100 alt baskets, because the 2 bps
half-spread came from the carry study's liquid BTC-like setting; if the strategy fails even
under that favourable spread, widening to measured alt spreads can only strengthen the
kill. The Binance liquid universe is also not a US-venue listing intersection; a pass would
need a venue-listing rebuild before belief, while a fail remains an honest no-deploy result
for this liquid-universe replication.

## Design review findings and resolutions

The senior-quant design review returned two Critical and four High findings. Resolutions:

- Critical 1, CPCV only wired: fixed in this design by making the CPCV split scores the
  conservative gate statistic. A pass must clear the minimum purged test-fold DSR, not just
  the full OOS DSR.
- Critical 2, trial count under-specified: fixed by freezing `naive_effective_n = 8` and
  recording the realized variant ledger described above.
- High 1, long-only overclaim risk: fixed by splitting the verdict language into retail
  long-only deployability and academic long-short comparison.
- High 2, missing `forward_return`: fixed by the explicit delisting-loss headline policy,
  count disclosure, and favourable drop-and-renormalize sensitivity.
- High 3, US spot listing intersection: accepted as a pass blocker. This PR uses the
  liquid Binance replication universe and labels any pass as non-deployable until a
  US-listed intersection rebuild exists. A fail can ship under this caveat.
- High 4, top-100 alt spread under-modeled: accepted as a pass blocker. The current
  assumed spread is favourable for alts; a fail is robust, while any pass would require a
  measured spread rebuild.
