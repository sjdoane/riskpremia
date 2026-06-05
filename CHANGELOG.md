# CHANGELOG

What shipped, plus every review finding and its resolution (rule 2). Newest
first. This is the audit trail; STATUS.md is the current-state snapshot.

## 2026-06-05, session 7 (CTREND PR3): the net-of-cost gate + verdict

The CTREND study's kill gate is built and the verdict is an honest null. Shipped on
`feat/ctrend-gate`:

- `ctrend/gate.py`: weekly equal-weight CTREND portfolio construction, spot-only turnover
  cost from `VenueCostModel.leg_cost_fraction(leg="spot", taker=...)`, the conservative
  missing-return policy, the frozen trial ledger, DSR scoring, CPCV split scoring, typed
  gate artifact serialization, and artifact loading.
- `scripts/run_ctrend_gate.py`: offline regeneration entry point. It reads the committed
  daily panel, rebuilds the weekly PIT universe and CTREND forecasts, writes
  `artifacts/ctrend_gate.json`, and prints the retail and academic verdicts.
- `tests/unit/test_ctrend_gate.py` and `tests/unit/test_ctrend_gate_reproduces.py`: focused
  turnover and missing-return tests, plus the offline reproduction gate that rebuilds the
  committed verdict from `tests/data/ctrend_daily_panel_usdt.csv.gz`.
- `docs/research/0004-ctrend-gate-design.md`: the reviewed PR3 design plan and review
  resolutions.

**VERDICT: NON-VIABLE retail long-only honest null.** On the held-out 2022+ window, the
retail long-only top quintile has mean net return **-0.906%/week**, turnover **1.16/week**,
full-window DSR **0.0034**, and conservative CPCV-min DSR **0.0031**, far below the
0.95 bar. Missing selected returns are charged as -100% delisting losses in the headline
(8 selected retail names), and the favourable drop-and-renormalize sensitivity is recorded
but does not drive the verdict. The academic long-short comparison has positive mean net
return (**+0.197%/week**) but still fails the conservative CPCV-min DSR gate (**0.0035**;
full-window DSR **0.2252**), so it does not rescue either the retail headline or the
paper-comparison stress. Trial family: 8 realized variants (portfolio form x execution
style x missing-return treatment), `v_sr=0.007287`, `n_effective=8`.

#### Design review (APPROVE-WITH-CHANGES, 2 Critical + 4 High + 2 Medium/Low, all resolved or accepted)

- **C1 [fixed]:** CPCV was only wired in the first design, not used as the validation
  estimator. Resolved by making the minimum purged CPCV test-fold DSR the gate statistic.
- **C2 [fixed]:** the initial trial count of 2 undercounted the documented design family.
  Resolved by freezing `naive_effective_n=8` and recording portfolio form, execution style,
  and missing-return treatment variants.
- **H1 [fixed]:** a long-only failure must not be overclaimed as a direct falsification of
  the paper's long-short result. Resolved by splitting the verdict into retail long-only
  deployability and academic long-short comparison. Here both fail the conservative
  CPCV-min gate.
- **H2 [fixed]:** missing selected `forward_return` values could create a false pass if
  dropped silently. Resolved by charging selected missing returns as -100% delisting losses
  in the headline, counting them, and recording a favourable sensitivity separately.
- **H3 [accepted, pass blocker]:** the Binance liquid universe is not a US spot listing
  intersection. A pass would require a US-listed-universe rebuild before belief; the fail can
  ship under this caveat.
- **H4 [accepted, pass blocker]:** the carry study's 2 bps spot half-spread is favourable
  for a top-100 alt basket. A pass would require measured alt spreads; a fail under the
  favourable spread is robust to wider measured spreads.

#### Post-implementation review (SHIP after one Medium fix, 0 Critical/High)

The reviewer rebuilt the gate from the committed panel and reproduced the scored numbers.
No Critical or High findings. Resolved:

- **Medium-1 [fixed]:** the artifact's forecast audit hash used raw elastic-net forecast
  floats, which can drift at the last bit across numeric paths even when all scored results
  match. Resolved by hashing the score-driving gate input (`week_end`, `symbol`, `quintile`,
  `forward_return`) instead, and adding an exact reproduction-test assertion for the hash.
- **Low [accepted]:** the PR3 trial penalty is narrower than ADR 0005's broad wording, but
  the strategy fails with CPCV-min DSR near zero, so this cannot create a false pass here.

Verification: `pytest -q -m "not network"` 218 pass / 16 deselected; `pytest -q -m network`
16 pass / 218 deselected; `mypy` clean (55 source files); `ruff check src tests scripts`
clean.

## 2026-06-05, session 6 (CTREND PR2): the fitted signal (the 28 features + the CS-C-ENet)

The first FITTED model in the project: a faithful replication of the CTREND cross-sectional
combined elastic-net (Fieberg et al., JFQA 2025), fit strictly point-in-time, producing
per-(week, coin) forecasts + quintiles. The paper's exact method was verified first (the 28
daily signals in Section III.B, the eq 3-11 CS-C-ENet protocol in Section III.C). Shipped on
`feat/ctrend-signal`:

- `ctrend/features.py`: the 28 DAILY technical signals (5 momentum: rsi/stochK/stochD/
  stochRSI/cci; 9 price MA: 7 SMAs + macd + macd_diff_signal; 10 volume: 7 volume-SMAs +
  volmacd + volmacd_diff_signal + chaikin; 4 Bollinger), computed on the daily panel per coin
  (polars rolling/EWM, strictly backward) and sampled at each weekly rebalance date.
- `ctrend/signal.py`: the CS-C-ENet. The cross-sectional rank-to-[-0.5,0.5] transform; the
  per-signal univariate Fama-MacBeth with 52-week coefficient smoothing (eq 7-8); the
  elastic-net SELECTION (eq 10, scikit-learn, mix 0.5, in-repo AICc lambda); the CTREND
  forecast = the equal-weight average of the positive-weight survivors (eq 11); the rolling
  PIT driver, the quintile sort, and the gross rank-IC + quintile-spread exhibits.
- `ctrend/signal_artifact.py` + `scripts/build_ctrend_signal.py`: the committed gross-quality
  artifact (`artifacts/ctrend_signal.json`: the full + OOS rank IC, the quintile spread, the
  per-year IC regime diagnostic, the fingerprint, the caveats) + its offline reproduction
  test, built from the committed panel (no network; the forecast series is recomputed, not
  committed, the VRP/PR1 discipline).
- Data-layer extension (prerequisite, revealed by the exact feature list): 4 signals (stochK,
  stochD, cci, chaikin) need daily HIGH/LOW, so `SpotKlineRecord` + `_parse_kline_zip` (now a
  5-tuple) + `build_daily_panel` (+ OHLC guards) + the fixtures gained high/low and the
  committed panel was rebuilt (the PR1 eligibility is byte-identical; only the panel SHA +
  artifact + manifest refreshed). `scikit-learn==1.5.2` (+ scipy/joblib/threadpoolctl) pinned.

**The gross result (real data, 563 coins, 238 scored weeks 2020-08..2026-05): the signal
predicts the cross-section at the GROSS level.** Point-in-time cross-sectional rank IC 0.032
(t 2.77) full-sample, 0.063 (t 4.73) on the held-out 2022+ window; monotonic full-sample
quintiles; +1.6%/week gross top-minus-bottom. Two honest caveats the post-implementation
review surfaced and the artifact carries: (1) the IC is REGIME-DEPENDENT, not a stable edge,
significantly NEGATIVE in 2021 (-0.07, t -3.3, the trend factor inverted) and strongly
positive only in 2025-2026 (+0.14/+0.15, t ~5.8), so the OOS headline aggregates a favorable
recent regime mix; (2) the 2022+ quintile means are all NEGATIVE (bear market) but positively
sloped, so the long-short spread is positive (+1.0%/week gross) while the retail-realistic
LONG-ONLY top quintile loses gross (-0.4%/week) before costs (the central PR3 tension, ADR
0005 caveat 5). This is GROSS, necessary-not-sufficient; the net-of-cost kill gate is PR3.

Deviations (documented, each a PR3 trial-registry knob): equal-weight OLS (no market cap on
Binance, so no value-weighted SSR); raw weekly returns (the cross-sectional intercept absorbs
the common risk-free rate); the canonical indicator conventions where the paper's
Supplementary Material Appendix A was unobtainable (the design review's C1). Full design in
docs/research/0003-ctrend-signal-design.md. 213 offline + 16 network tests; mypy --strict (53
files); ruff; em-dash clean.

#### Design review (APPROVE-WITH-CHANGES, 1 Critical + 6 High + 6 Medium + 4 Low, all resolved)

The independent senior-quant design review grounded itself in the paper PDF + the code.

- **C1 [resolved-with-caveat]:** the 28 formulas were textbook reconstructions, not verified
  against the paper's Supplementary Material Appendix A (a separate, unobtainable file: SSRN
  login-walled, the Cambridge supplement + the Corvinus mirror unreachable). Resolved per the
  reviewer's sanctioned fallback: the paper STATES the load-bearing parameters (the SMA set,
  14-day RSI/stochastics, 12/26/9 MACD, 20-day/2-std Bollinger, the StochRSI prose), and the
  canonical practitioner defaults (Wilder RSI, 20-day CCI on the typical price + 0.015, 20-day
  Chaikin, EMA adjust=False) are used + documented for the unstated few, each a PR3 robustness
  knob; obtaining Appendix A is a tracked follow-up.
- **H1 [fixed]:** the rank transform is `(rank-1)/(N-1)-0.5` (the closed-interval KPS/GKX), with
  average-rank ties + an N<2 no-regression rule. **H2 [fixed]:** the AICc df is
  `nnz + intercept + sigma^2` (the reviewer's correction), with #nonzero-as-elastic-net-df
  documented as the standard approximation. **H3 [fixed]:** the FM smoothing window AND the
  elastic-net pool both end at week t-1 (never t, whose forward return is the target); the
  exact week-index pairing (z(W_m), forward_return(W_m)) is documented + pinned by a
  no-look-ahead test. **H4 [adopted]:** the gate-critical elastic-net uses scikit-learn
  (pinned, `selection='cyclic'`, post-fit theta>0), not bespoke numerics, with the AICc in-repo.
  **H5 [fixed]:** the raw-return-vs-excess-return deviation is documented (rank-innocuous via
  the cross-sectional intercept). **H6 [fixed]:** missing-signal handling specified at all three
  stages (univariate exclusion + N<2 floor; the eq-11 average over only the coin's non-null
  selected forecasts, a coin with none dropped not zeroed; the eq-10 complete-case pool).
- **M1 [fixed]:** Wilder RSI (alpha 1/period) + EMA adjust=False + min_samples=span +
  ignore_nulls, validated against an independent computation; the first (null) delta is kept
  null so the EWM seeds at the first real move (the cleaner seeding, caught by the feature
  test). **M2 [fixed]:** equal-weight applied consistently to eq-7 + eq-10, the deviation
  documented; the dollar-volume-weighted variant is a deferred PR3 knob (the liquid universe
  mitigates the concern). **M3 [fixed]:** the deliverable is the summary + fingerprint (the
  forecast series recomputed by PR3); the IC is the PIT cross-sectional rank IC on post-burn-in
  weeks; the gross-necessary-not-sufficient caveat is carried. **M4 [fixed]:** the panel-extension
  blast radius (the schema constant, the reader offsets, the 4-to-6-column tests, the rebuilt
  artifact/manifest) all updated. **M5 [done]:** confirmed only high/low needed (no OPEN); Chaikin
  uses the dollar-volume convention (documented). **M6 [fixed]:** Bollinger std ddof=0.
- **L1-L4 [fixed]:** quintile remainder-front + symbol tie-break; `naive_effective_n` semantics
  pinned (PR2 documents the trial family, PR3 records); `min_samples` (not the deprecated
  `min_periods`); the `Any`-narrowing + the sklearn/scipy mypy override + a ConvergenceWarning
  guard under filterwarnings=error.

#### Post-implementation review (SHIP, 0 Critical/High, 2 Medium, 2 Low; reproduced from first principles)

The reviewer reproduced every committed number bit-for-bit (full IC 0.032191049215932487
exact, OOS 0.06266829845084093 exact, 238 weeks) and CERTIFIED no look-ahead by three
independent adversarial tests, including a surgical test perturbing ONLY `forward_return(W*)`
by +100 and confirming the week-W* forecast changes by exactly 0.0 (ruling out the m=t
off-by-one). It re-derived all 28 indicators against a third independent implementation (0
mismatches on synthetic + ~16k real BTC values), confirmed the eq-11 equal-weight-of-selected
faithfulness, and confirmed the elastic-net abstention does NOT bias the IC (a neutral
counterfactual on the 67 no-select weeks gives ~the same IC). Resolved:

- **Medium-1 [fixed]:** the OOS IC is not temporally stable (significantly negative in 2021),
  which was not disclosed. Resolved by adding the per-year `ic_by_year` block to the artifact +
  a regime-instability caveat + a reproduction-test assertion that the IC is not uniformly
  positive; the regime non-stationarity is now an explicit input to the PR3 gate.
- **Medium-2 [accepted]:** the reproduction IC tolerance (5e-3) is loose vs the ~1e-15 same-
  platform variation; kept for cross-platform (Linux CI) elastic-net-selection robustness, with
  the exact `n_weeks` match as the structural-regression guard.
- **Low-1/Low-2 [accepted]:** the quintile remainder is bottom-loaded (documented, immaterial
  at N~100); the smoothing re-indexing is the correct PIT translation of the paper (confirmed
  faithful, the doc already explains it).

## 2026-06-04, session 5 (CTREND PR1): the point-in-time, delisting-complete universe data layer

The data foundation for Study 3 (the CTREND crypto cross-sectional trend factor, ADR 0005).
It turns the delisting-complete Binance Vision DAILY spot klines into (i) a daily panel
(close + USD dollar volume per coin) the signal (PR2) computes the 28 daily technical
signals on, and (ii) a weekly rebalance grid (returns + a point-in-time liquid-universe
eligibility flag) the backtest (PR3) consumes. Shipped on `feat/ctrend-universe-data-layer`:

- `data/records.py` `SpotKlineRecord` (close + quote/dollar volume); `data/sources/
  binance_vision.py` extended: `list_spot_symbols` (delisting-complete S3 enumeration via
  CommonPrefixes), `fetch_spot_klines` + `available_spot_months` (daily klines, delisting-
  robust month intersection), `_parse_kline_zip` refactored to also return the quote-asset
  volume (column 7 = USD dollar volume), and an optional retry/backoff for the multi-symbol
  build (off by default, so the single-symbol funding/mark/spot paths and tests are
  unchanged).
- `ctrend/universe.py`: the exclusion filter (non-standard/non-ASCII tickers, stablecoins/fiat,
  and leveraged tokens, with the UP/DOWN listed-base disambiguation), `build_daily_panel`, `build_weekly_panel` (daily ->
  weekly resample, gap-safe `weekly_return`, explicit `forward_return`), and `pit_eligible`
  (the point-in-time top-N-by-trailing-dollar-volume liquidity selection). `ctrend/
  fixtures.py` (the committed daily-panel CSV) + `ctrend/artifact.py` (the universe summary
  JSON) + `ctrend/errors.py`.
- `scripts/build_ctrend_universe.py`: the one-time real-data build (enumerate -> concurrent
  fetch -> daily/weekly panel -> ever-top-N_MAX trim -> losslessness + fidelity asserts ->
  committed gzipped CSV fixture + artifact + manifest stamp). The committed daily panel
  (`tests/data/ctrend_daily_panel_usdt.csv.gz`) is the reproducibility anchor; the weekly
  grid + eligibility are pure functions of it.

**The universe (live Binance Vision, 2026-06): 664 USDT-quoted spot symbols enumerated
(delisting-complete), 67 excluded (48 leveraged tokens + 18 stablecoins/fiat + 1 non-standard
non-ASCII ticker), 597 tradeable; the committed daily panel is trimmed to the 563 coins ever
in the top-120 liquid set over 2019-01-06..2026-05-31 (387 weeks, 721,954 daily rows, 9.6 MB
gzipped). The PIT liquid universe ramps from 20 eligible coins in early 2019 to the full 100
from 2021 on.** Survivorship is demonstrated on the real data: SRMUSDT is retained and stops
trading 2022-12-04 (a genuine post-FTX delisting), while LUNAUSDT and FTTUSDT trade through
the present (Binance ticker reuse / relisting, exactly the case the H4 caveat flags). The
full build surfaced one real-data edge case (a non-ASCII CJK novelty symbol that cannot be
ASCII-encoded into an S3 URL), handled by the non-standard-ticker exclusion.

The paper's exact method was verified first (the design review insisted the data granularity
be settled before committing a panel): the 28 technical signals are computed on DAILY bars
(14-day RSI, 3- to 200-day SMAs) with a WEEKLY rebalance, so the layer stores daily data and
derives the weekly grid. The aggregation is the CS-C-ENet (PR2). The paper's market-cap
universe + value-weighting are unavailable from Binance, so the dollar-volume top-N screen +
(PR3) equal-weighting are documented deviations (ADR 0005 amendment + artifact caveats). Full
design in docs/research/0002-ctrend-universe-design.md.

#### Design review (APPROVE-WITH-CHANGES, 2 Critical + 4 High + 5 Medium + 6 Low, all resolved)

The independent senior-quant design review grounded itself in the real code + polars 1.41.1.

- **C1 [fixed]:** the `_parse_kline_zip` refactor to a 3-tuple breaks its pinned unit test;
  resolved by updating the test (and asserting the new quote-volume field is parsed from
  column 7), and resolving the open question in favour of refactor-in-place.
- **C2 [fixed]:** the obvious `struct(...).rank(descending=True)` tie-break inverts the
  symbol order (selecting the lexicographically-LAST coin on a volume tie, a silent
  selection bug). Resolved with an explicit `sort(descending=[False, True, False])` +
  `cum_sum` rank, pinned by an all-tied-volume test asserting the ASCENDING symbol wins.
- **H1 [fixed]:** native weekly bars would foreclose the paper's daily-MA features. Resolved
  by verifying the paper (daily features, weekly rebalance) and storing the DAILY panel
  (the weekly grid derived from it); recorded as an ADR 0005 amendment.
- **H2 [fixed]:** the liquidity-ranking basis (dollar volume vs the paper's market cap) is a
  data-forced deviation; surfaced as an explicit artifact caveat distinct from the price
  basis (mean-vs-median trailing volume is a tracked PR2/PR3 knob).
- **H3 [fixed]:** the same-bar look-ahead trap (decide and realize on the same close).
  Resolved by documenting `weekly_return` as contemporaneous AND exposing an explicit
  `forward_return` (the holding return over (t, t+1]) so PR3 cannot use the same-bar return.
- **H4 [fixed]:** the canonical-collision / ticker-reuse survivorship subtlety (1000SHIB vs
  SHIB, LUNA -> LUNC). Resolved by keying the panel on `symbol` (canonical informational
  only, never a dedup key) and documenting that a rename appears as a delisting + a fresh
  listing (the dead leg retained), with the decision in the design doc + artifact caveats.
- **M1 [fixed]:** the rolling/history windows count weekly BARS, not calendar weeks;
  documented precisely (== calendar weeks absent a halt) and pinned by a gappy-panel test.
  **M2 [fixed]:** checksum-before-parse kept for the ~30k-file build, with a per-request
  retry/backoff (build-only) and file-granular resumability via the content cache.
  **M3 [fixed]:** a per-symbol fetch failure is FATAL in the build (a silent drop would
  reintroduce survivorship through the harness). **M4 [fixed]:** the exclusion sets are
  committed constants and the full excluded list is emitted into the artifact so a missed
  stablecoin is visible; the UP/DOWN rule uses the post-strip listed-base set, pinned by
  tests (JUP kept, BTCUP excluded). **M5 [fixed]:** `week_end` is normalized to the Sunday
  calendar Date in `build_weekly_panel` itself, so the live build and the committed-fixture
  reproduction compare like-for-like (byte-stable).
- **L1 [fixed]:** `min_samples` (not the deprecated `min_periods`). **L2 [fixed]:**
  `CtrendError(ValueError)` mirroring `VrpError`. **L3 [fixed]:** `pit_eligible` /
  `build_weekly_panel` sort defensively before the windowed ops (the `make_label_horizons`
  precedent). **L4 [fixed]:** `SpotKlineRecord` imported only at its use site so ruff does
  not strip it. **L5 [resolved by build, decision evolved]:** the plain daily panel is ~35 MB
  (too heavy for a fixture), so the committed panel is GZIPPED (~9.6 MB) with a two-hash model
  that stays cross-platform stable: the universe artifact pins the decompressed-CONTENT SHA
  (platform-independent), and the snapshot manifest stamps the committed `.gz` blob's FILE SHA
  (git preserves the blob, `.gitattributes` marks `*.gz binary`); the CSV values are written as
  exact Decimals with trailing zeros stripped (lossless). **L6 [fixed]:** the delisting proof
  is asserted (a named dead coin present with a last week before the window end) in the
  reproduction test (SRMUSDT satisfies it).

#### Post-implementation review (SHIP, 0 Critical/High/Medium, 3 Low; reproduced from first principles)

The independent senior-quant post-implementation review re-derived every load-bearing number
from the committed `.gz` panel and the live bucket (not from comments) and could not break the
PIT property. Confirmed by running code: the decompressed-content SHA + the `.gz` file SHA +
`verify_snapshot` all match; the gzip is byte-reproducible (mtime=0); 721,954 rows / 563
symbols / 0 duplicate (date,symbol) / sorted; the eligible-by-week breadth, the ever-eligible
count, the trim set (ever-top-120 == the 563 committed), and the delisting proof all
reproduce; a late-week volume perturbation changes NO earlier week's eligibility (no
look-ahead); `trailing_dollar_volume` is a backward mean ending at t (0 mismatches vs a
hand-rolled mean); `forward_return(t) == weekly_return(t+1)` with 0 violations and null across
all 4 real calendar-week gaps; non-rankable new-coin spikes never consume a top-N slot (max
eligible is exactly 100); the trim is lossless at top_n in {1,20,100,120}; the exclusion filter
has no false positives (JUP/SUPER/AUDIO/PEOPLE/WBTC kept) or false negatives; the artifact JSON
is 0 non-ASCII bytes (the CJK symbol escaped); `pytest -m "not network"` 195 pass, `-m network`
4 pass, mypy + ruff clean. Resolved:

- **L1 [fixed]:** this CHANGELOG entry's shipped-summary numbers were pre-build placeholders
  (66 excluded / 598 tradeable / a non-`.gz` path) and the L5 line described the superseded
  plain-CSV decision; corrected to the shipped 67 / 597 / gzip-with-two-hash reality.
- **L2 [accepted, documented]:** the offline reproduction test pins the panel-derived fields
  but not `n_symbols_enumerated` / the `excluded` list (build-time provenance, the VRP
  precedent); the `test_enumeration_is_delisting_complete` network test guards enumeration.
- **L3 [accepted, documented]:** `n_weeks=387` (the full grid) vs the 380-entry
  `eligible_by_week` series differ because the first 7 weeks (early 2019) have 0 eligible coins
  (no coin has the 8-bar history yet) and 0-eligible weeks are omitted from the series; both are
  internally consistent and honest.

## 2026-06-04, session 4 (PR5f): the Layer-ii short-variance gate + the verdict (an honest null)

The finale of the VRP study's tradeable layer. A systematic monthly SHORT STRADDLE (a
near-ATM call + put, each delta-hedged, held to expiry) across the VRP window, scored on
the frozen ADR 0004 criterion. Shipped on `feat/vrp-short-variance-gate`:

- `vrp/gate.py`: `build_straddle_trade` (the sum of two delta-hedged `simulate_option_trade`
  legs, with a conservation post-init + a combined-ATM-delta check), the regime-conditional
  `RegimeTail`, the cited `PesoShock`, the `GateVerdict`, and `build_gate_artifact` +
  `GateArtifact` JSON serialization. The DSR series divides each month's net by `2 *
  initial_margin_fraction` (a conservative-high base, understates the Sharpe); the tail loss
  is reported as a multiple of the SINGLE-leg margin (so a single-leg crash is not halved).
- `vrp/fixtures.py`: the committed monthly straddle-entries read/write + the spot-by-date
  expiry lookup. `scripts/build_vrp_entries.py` (network, one-time) gathered 42 of 42
  first-of-months (0 dropped) into `tests/data/vrp_straddle_entries.csv` (SHA256-stamped).
  `scripts/run_vrp_gate.py` (offline) builds + commits `artifacts/vrp_short_variance_gate.json`.

**THE VERDICT (real data, 42 BTC short straddles, 2022-01..2025-06): NON-VIABLE, the
pre-registered cost/peso-bounded honest null.** Net-of-cost Deflated Sharpe 0.30 (below the
0.95 bar; effective T 33, not underpowered); mean net slightly NEGATIVE (-0.009 coin/month;
pre-ETF -0.017, post-ETF +0.002); 48% of months losing; the worst in-sample month loses
2.7x the posted single-leg margin (account-ending in-sample, before any shock); the cited
peso shocks (a -37% 'Black Thursday' and a -50% May-2021 one-day crash on a representative
straddle) lose 3.3x and 6.1x the margin. **Both gates fail.** The honest finding: the
positive Layer-i VRP measurement does NOT translate into a profitable tradeable straddle,
because the static held-to-expiry straddle is a path-BLIND directional bet (realized 30-day
endpoint moves averaged 11.9% vs 11.4% of premium collected, so it loses before costs), and
the un-modeled path rehedge (the dominant cost) is what would convert it to a variance
harvest. The measurement floor (Layer i) remains the study's positive headline; the
tradeable harvest is cost/peso-bounded. 174 offline + 12 network tests; mypy --strict (43
files), ruff, em-dash clean.

#### Design review (APPROVE-WITH-CHANGES, 2 Critical + 6 High, all resolved; an adversarial fork review)

- **C1 [fixed]:** separate the DSR return base (2x IM) from the tail base (the SINGLE-leg
  IM), so dividing the single-leg crash by a doubled base cannot halve the apparent
  catastrophe. **C2 [fixed]:** the peso-adjustment is a deterministic, CITED structural
  shock (the -37%/-50% one-day precedents) on a representative straddle, not a free number
  on the cherry-picked worst month.
- **H1 [fixed]:** the both-legs-tradeable selection funnel is surfaced (n_dropped) and drops
  a month loudly rather than silently sliding to a far strike. **H2 [fixed]:** the
  daily-close-vs-08:00-Deribit-settlement terminal basis is flagged
  (`terminal_basis_unmodeled`) + caveated (convexity makes it understate large-move losses).
  **H3 [fixed]:** the underpowered DSR is subordinated, the verdict is `(dsr < 0.95) OR
  (tail fails)` so a high DSR can never rescue a failing tail (pinned by a passing-DSR +
  failing-tail test). **H4 [fixed]:** the straddle-sum + the combined-ATM-delta-near-zero
  invariant. **H5 [fixed]:** the entries fixture SHA256-stamped, the spot coverage of every
  expiry asserted loud, the artifact carries the two fixtures' SHAs. **H6 [fixed]:** the
  committed JSON gate artifact is a required deliverable.
- Mediums/Lows folded in: per-regime n reported (the post-ETF cell is ~17 obs, a tail lower
  bound); CPCV correctly omitted + stated (~17 post-ETF obs cannot support it); the pass-
  branch cross-check text; the path-rehedge + terminal-basis caveats carried in the artifact.

#### Post-implementation review (SHIP, 0 Critical/High/Medium, 3 Low)

The reviewer reproduced the artifact byte-identical, hand-recomputed the worst month (the
2022-06 LUNA-crash straddle, a deep-ITM put) to 16 figures confirming the inverse
`intrinsic_usd / S_T` settlement (a linear `/S0` would understate it 33%), independently
recomputed the DSR (the block deflation RAISES it 0.273 -> 0.297, so the kill is not
manufactured), confirmed the H3 subordination by a constructed DSR=1.0 + failing-tail input,
and ran the false-null/false-pass attack: the negative mean is bug-free (the path-blind
static straddle loses before costs; the kill rests on the inverse crash tail via the
OR-verdict, robust to the cost knobs). Resolved the 3 Low (doc currency): the H3 test now
asserts a passing DSR is still killed; STATUS/CHANGELOG brought current; the PR5g deferral
(figures + the README results section) recorded.

## 2026-06-04, session 4 (PR5e): the per-trade short-variance option P&L (Layer ii)

The per-trade math the null and gate (PR5f) will run, pure (no IO, no RNG), the analogue
of the carry's PR4a `simulate_trade`. Shipped on `feat/vrp-option-trade-pnl`:

- `execution/options.py` `simulate_option_trade` + `OptionTradePnL`: the realized P&L of
  selling one option, statically delta-hedging on the perp, and holding to expiry,
  accounted in COIN per contract (the inverse settlement currency). The short receives
  the bid premium, pays `terminal_payoff = intrinsic_usd / S_T` (the INVERSE cash
  settlement), and runs a static inverse-perp delta hedge `delta * (1 - S0/S_T)`. A
  `__attrs_post_init__` conservation guard and a `path_rehedge_unmodeled=True` marker so a
  downstream Sharpe must acknowledge the static-endpoint proxy. `rehedge_cost_sensitivity`
  bounds the un-modeled rehedge transaction cost (not the path-P&L gap).
- `execution/cost.py` `DeribitOptionCostModel` gained `funding_capital_rate`, the
  ITM-conditional `option_delivery_fee_on_intrinsic` (refining the PR5d ceiling), and
  `margin_financing_fraction` (financing on the option margin, a FLOOR); `OptionPnLError`.

154 -> 163 offline + 12 network tests; mypy --strict (src + scripts, 40 files), ruff,
em-dash clean.

#### Design review (REJECT, 2 Critical, both resolved before re-implementing)

The review caught a load-bearing INVERSE-CONTRACT error in the first design and rejected
it outright (the rule-1 process working as intended; an honest record):

- **C1 [fixed]:** Deribit BTC/ETH options are inverse (coin-settled at the expiry price
  S_T), so the short's payoff is `intrinsic_usd / S_T`, NOT the linear `intrinsic / S0`
  the first design used. The linear form UNDER-STATED the put crash tail by ~10x (a 90%
  crash settles ~9x the notional, not ~0.9x), the exact false-PASS direction the study
  guards against. Re-implemented in coin per contract with the inverse settlement.
- **C2 [fixed]:** the delta hedge is the Deribit INVERSE perp, P&L `delta * (1 - S0/S_T)`
  (= `delta*S0*(1/S0 - 1/S_T)`), not the linear `delta*(S_T - S0)/S0` (which under-stated
  the hedge loss on a down-move by ~2x, compounding C1).
- Highs/Mediums folded into the re-implementation: the conservation invariant exact by a
  fixed left-to-right association in the post-init (H1); the round-trip uses the
  ITM-conditional delivery, with the swap from the ceiling pinned (H2, M1); the
  static-endpoint status carried ON the object via `path_rehedge_unmodeled` so PR5f cannot
  read it as a faithful variance return (H3); financing labeled a FLOOR, not conservative
  (H4); guards on S_T<=0 / S0<=0 / hold<0 (M4); a dedicated `OptionPnLError` (L2); a
  real-fixture crash-tail pin (L4); the single-delta-hedged-option proxy scoped (M2).

#### Post-implementation review (SHIP, 0 Critical/High/Medium/Low)

The reviewer re-derived the inverse settlement by hand and confirmed the fix: the 90%
crash put pays exactly 9.0 coin (net -4.46), the linear form's 10.00x understatement is
gone; the hedge signs are correct for the short call (long perp) and short put (short
perp); the option+hedge residual is O(dS^2) and only ever more-negative into a crash (so
the deferred inverse-greek subtlety cannot hide tail loss); the conservation guard had 0
false raises over 22 awkward-value trades; the ITM-conditional delivery uses the coin
intrinsic; every guard, the financing floor, and the rehedge caveat are in place. No
findings.

## 2026-06-04, session 4 (PR5d): the delta-hedged-option cost model (Layer ii, cost-model-first)

The cost side of the short-variance test, built BEFORE the P&L/null (rule 6). Shipped on
`feat/vrp-option-cost-model`:

- `execution/cost.py` `DeribitOptionCostModel` (frozen) + the cited `DERIBIT_OPTION`: the
  transaction cost of a delta-hedged SHORT option, every term a positive fraction of the
  underlying notional S (the inverse-contract convention; S is the COST base, NOT the
  return base). Deribit fees (web-verified + cited June 2026): trade fee min(0.03% of
  underlying, 12.5% of premium), maker == taker; delivery fee 0.015% of underlying capped
  at 12.5% of value, daily options exempt; the perp delta-hedge leg on the Deribit perp
  (taker 0.05%, maker rebate dropped to 0).
- `execution/options.py` `delta_hedged_option_cost` + `OptionCostBreakdown`: the
  quote-driven cost decomposition (option fee on the executed bid + the measured entry
  spread + the conservative delivery ceiling + the perp hedge floor), with loud guards
  (untradeable quote, |delta| > 1) and a self-consistency post-init.
- A deterministic offline real-data pin on the committed Tardis sample fixture (the ATM
  0.03%-fee leg and a deep-OTM 12.5%-cap leg both exercised) + a live network cost test.

**The first real option cost** (live, a near-ATM BTC call): round-trip 16.1 bps of the
underlying (option fee 3.0 + floored spread 5.0 + hedge 6.6 + delivery 1.5) against ~110
bps of premium received, i.e. about 15% of the premium consumed by entry/exit costs
before the dominant un-modeled path-rehedge term. 154 offline + 12 network tests; mypy
--strict (src + scripts, 40 files), ruff, em-dash clean.

**Binding deploy caveat (the ADR 0001 C1 analogue):** `tradeable=False`. US retail
cannot directly trade Deribit; the regulated path (Coinbase Financial Markets, CFTC-
cleared May 2026) is institutional-live / retail-coming-soon. The kill gate reads the
flag, and the eventual deploy verdict notes the access path is improving but not yet open
to US retail.

#### Design review (APPROVE-WITH-CHANGES, 2 Critical + 4 High, all resolved before/while implementing)

- **C1 [fixed]:** pin the capital base now. A short option is margined (~15% of S), not
  fully funded, so the eventual Sharpe must divide net P&L by the margin, not S. Added a
  cited `initial_margin_fraction` field and documented "S = cost base, NOT return base" so
  the units cannot drift in PR5e.
- **C2 [fixed]:** charge the option trade fee on the EXECUTED bid (the premium actually
  received), not the mark, so the fee matches the cash inflow; pinned by a cap-binding test.
- **H1 [fixed]:** the static entry+exit hedge is labeled a cost FLOOR; the path rehedge is
  the dominant un-modeled term (ADR 0004 caveat 3). **H2 [fixed]:** the hedge is modeled
  same-venue on the Deribit perp and hedge financing is named as deferred (not silently
  dropped). **H3 [fixed]:** a crossed/thin quote (mark <= bid) is floored, never a
  zero/negative spread, with a `spread_is_floored` flag. **H4 [fixed]:** the flat delivery
  fee is labeled a CEILING (the OTM majority expire worthless and pay ~0; PR5e charges it
  ITM-conditional on the actual intrinsic).
- Mediums folded in: a `routing_fee` field at 0 for the Coinbase layer (M1); the cost
  invariants + exact-equality where construction allows (M2); full value-domain validation
  (cap in [0,1], margin in (0,1], |delta| <= 1) (M3); a deterministic offline cost test on
  the committed fixture, not only a live test (M4). Lows: the inverse-contract + short-side
  + full-spread-vs-half-spread conventions documented.

#### Post-implementation review (SHIP, 0 Critical/High/Medium, 2 Low fixed)

The reviewer reproduced the real-fixture cost decomposition by hand (matching to 1e-18),
confirmed every term is genuinely a fraction of S with no coin/fraction mixing, found no
under-charging beyond the named deferrals, and confirmed the Deribit fee rules + the loud
guards. Resolved:

- **L1 [fixed]:** named the single-contract / touch-bid fill assumption (the spread is the
  touch-level `mark - bid`, not a depth-aware walk of `bid_amount`) alongside the other
  deferrals, so PR5e inherits it as a known bound.
- **L2 [fixed]:** added a `__attrs_post_init__` self-consistency guard to
  `OptionCostBreakdown` (matching the repo's other frozen carriers), so a hand-constructed
  instance cannot carry inconsistent entry/exit/round-trip fields.

## 2026-06-04, session 4 (PR5c): the Tardis Deribit option-chain loader (Layer ii data layer)

The first piece of Layer ii (the cost-gated short-variance test), built cost-model-
FIRST: the data loader the cost model and the null will consume. Shipped on
`feat/vrp-tardis-option-chain`:

- `data/sources/tardis_options.py`: `TardisOptionChainSource.fetch_snapshot` streams the
  free first-of-month Deribit `options_chain` gzip (~1.8 GB) WITHOUT caching it, and
  extracts a point-in-time chain snapshot. The snapshot is a BACKWARD as-of: an explicit
  `as_of` entry instant (midnight + offset), keeping per instrument its freshest quote
  with `timestamp <= as_of`. It stops once the exchange timestamp passes `as_of + grace`,
  and a loud completeness check (reached as_of, enough instruments, strikes bracket the
  underlying) fails a truncated/thin chain rather than silently biasing selection.
- `data/boundary.py` `PydanticTardisOptionRow` (the 24-column header, empty quote/greek
  cells to None, a put/call enum, positivity + strike-vs-underlying sanity, the `SYN.*`
  synthetic-underlying flag); `data/records.py` `OptionQuoteRecord` + `OptionType` + the
  `tardis` venue; `data/clock.py` `us_to_utc` (the range-guarded microsecond clock).
- A 20-row VERBATIM real-slice fixture (`tests/data/tardis_deribit_options_sample.csv`)
  for the offline parse tests; the as-of / stop / completeness logic is tested on
  synthetic gzipped data; one live network test fetches a real BTC snapshot.

**Verified on real data:** a live BTC first-of-month fetch returns 1048 instruments at a
20-minute as-of, underlying ~43269, strikes 10000..180000 bracketing it, every quote
point-in-time honest (`quote_ts <= as_of`), bounded (~14 s, never the full gigabyte).
144 offline + 11 network tests; mypy --strict (src + scripts, 39 files), ruff, em-dash
clean. Reproducibility note: the committed offline monthly snapshot is deferred to the
consuming cost-model PR (once the needed months/expiries are fixed); this loader's live
network test is the real-data proof, and the immutable Tardis daily object will then be
stamped as the snapshot's provenance.

#### Design review (APPROVE-WITH-CHANGES, 2 Critical + 5 High, all resolved before/while implementing)

The review grounded itself in the real schema (probed live before designing):

- **C1 [fixed]:** the snapshot is a BACKWARD as-of (the freshest quote at-or-before an
  explicit `as_of`), NOT the last quote in a forward window (which would let different
  instruments resolve to different later times and leak future data into an entry stamped
  at the window start).
- **C2 [fixed]:** the early stop tolerates the exchange-clock disorder via a grace margin
  (not break-on-first-over-cutoff), plus a loud completeness assertion (reached as_of,
  `min_instruments`, strikes bracket the underlying) so a truncated chain fails loudly.
- **H1 [fixed]:** carry `underlying_index` + a `synthetic_underlying` flag for the `SYN.*`
  forward, and positivity-guard `underlying_price`; **H2 [fixed]:** only identity + as-of
  + underlying are required, every quote/greek observation is nullable (empty to None);
  **H3 [fixed]:** a validated `us_to_utc` that RAISES on a ms/seconds value;
  **H4 [accepted]:** PR5c is live-test-only with a verbatim parse fixture, the committed
  monthly snapshot documented as deferred to the consuming PR; **H5 [fixed]:** capture
  `bid_amount`/`ask_amount` + `vega`/`gamma` so a capacity / short-variance cost model
  needs no gigabyte re-fetch.
- Mediums folded in: parse `option_type` from the authoritative column, loud on non
  put/call, futures/perps skipped not raised (M2); the strike-vs-underlying ratio sanity
  check (M3); the deterministic `(expiry, strike, option_type)` sort (M5); Decimal straight
  from the CSV string, never via float (M6); the `tardis` venue as a distinct
  reproducibility model from the live `deribit` DVOL API (M1).

#### Post-implementation review (FIX-THEN-SHIP, 1 High + 1 Medium + 2 Low; the High found by streaming the real file)

The reviewer streamed the real production file and measured the ordering, catching a
load-bearing error:

- **H1 [fixed]:** the file is ordered by `local_timestamp` (the capture clock), NOT the
  exchange `timestamp` (about 27% of rows step backward in exchange time, up to ~1 s), so
  the original file-last-wins selection could keep a STALER quote. Resolution: keep the
  max-exchange-timestamp quote at-or-before `as_of` (row-order-independent), and the
  docstrings/comments corrected (the 30 s grace dwarfs the ~1 s disorder, so the early
  stop is still safe). Not a look-ahead leak (PIT held); the fix removes a sub-second,
  order-dependent staleness. Pinned by an out-of-order regression test.
- **M [fixed]:** the loader did not drop an already-expired contract still carrying a
  stale quote. Resolution: drop `expiry <= as_of`; pinned by a test.
- **L [fixed]:** a gzip truncated before `as_of` raised a bare `EOFError`; now re-raised
  as `VenueFetchError` for a consistent loud-failure contract. **L [done]:** the committed-
  snapshot deferral (H4) is documented in the source docstring + this entry.
- The reviewer independently CONFIRMED the point-in-time guarantee holds (a quote strictly
  after `as_of`, even inside the grace window, can never enter the snapshot), the boundary
  empty-to-None + Decimal-not-float paths, the `us_to_utc` guard, the strike-ratio bounds
  (no false rejects of legitimate deep-OTM), and the deterministic sort.

## 2026-06-04, session 4 (PR5b): the committed VRP artifact + figures + the DVOL reproducibility stamp

Layer i's recruiter-facing, regenerable deliverable, and the M1 reproducibility gate
from the PR5a review. Shipped on `feat/vrp-artifact-and-figures`:

- `vrp/fixtures.py`: stdlib CSV read/write of the two committed daily-close fixtures.
  `read_dvol_csv` rebuilds each `DvolRecord` THROUGH the `PydanticDeribitDvolRow`
  boundary (`o=h=l=c`, the only field the measurement consumes) so the positivity /
  consistency guards still fire on the reproduction path; `read_spot_csv` carries a
  positivity check. Written LF with the exact `Decimal` string of each close.
- `vrp/artifact.py`: the `VrpArtifact` (headline + regime decomposition + an
  alignment-count diagnostic + the dataset fingerprint + the pinned inference knobs +
  the binding caveats + the daily series), `build_artifact`, deterministic
  `artifact_to_json` (`attrs.asdict` + `json.dumps(sort_keys, indent, allow_nan=False)`)
  and an explicit loud-failure `artifact_from_dict`/`load_artifact`. matplotlib-free.
- `vrp/figures.py`: lazy-matplotlib (Agg, pinned PNG metadata) render of the
  DVOL-vs-realized-vol series and the forward-VRP decay, PURELY from the artifact (no
  bootstrap recompute), with the honesty caveats as figure footnotes.
- `scripts/build_vrp_artifact.py` (network, one-time): fetches the live DVOL + spot,
  writes the fixtures, PROVES they reproduce the live headline exactly (the fidelity
  check), builds `artifacts/vrp_measurement.json`, and SHA256-stamps both fixtures into
  the manifest. `scripts/regenerate_figures.py` (no network) renders `docs/figures/`.
- The M1 gate closed: because DVOL is live/as-of with no published checksum, a re-fetch
  is not byte-guaranteed, so the exact daily closes are COMMITTED (`tests/data/*.csv`,
  `kind = "reproducibility_fixture"`, `published_checksum=None`) and SHA256-stamped, and
  an OFFLINE test rebuilds the committed headline from them. This is the documented
  counterpart to the immutable-dump model (gitignore + re-fetch + verify).
- `.gitattributes`: `*.csv text eol=lf` (cross-platform SHA stability) + `*.png binary`.

**The committed measurement (reproduced bit-exactly from the fixtures): BTC VRP,
2022-01..2025-05, 30-day, median-phase mean 0.0873, phase-0 95% block-bootstrap CI
[0.0331, 0.1194] clearing zero, 70% of days positive, pre-ETF 0.1006 to post-ETF
0.0593.** 128 offline + 10 network tests; mypy --strict (src + scripts, 38 files), ruff
(src + tests + scripts), em-dash clean.

#### Design review (APPROVE-WITH-CHANGES, 2 Critical + 4 High, all resolved before/while implementing)

- **C1 [fixed]:** the DVOL fixture reader must route through the pydantic boundary
  (`o=h=l=c`) + `ms_to_utc`, so a tampered/non-positive close raises rather than flowing
  a wrong implied variance into the headline (pinned by a test).
- **C2 [fixed]:** the artifact pins `seed`, `n_boot`, and the resolved bootstrap block
  length in an `inference` block, and the reproduction test passes them explicitly into
  `vrp_headline` (never the function defaults), so the committed CI stays regenerable if
  a default later changes.
- **H1 [fixed]:** the spot fixture is committed (the offline CI test needs it), with the
  derivation recorded in the manifest entry + ADR, and the build script asserts the
  committed fixtures reproduce the live headline exactly before writing.
- **H2 [fixed]:** committed fixtures use a distinct `kind = "reproducibility_fixture"`
  with a provenance `note` field (new on `SnapshotEntry`), and `verify_snapshot`'s
  missing-file message no longer assumes a re-fetchable vendor dump; the deliberate
  departure (committed in-repo anchor for a live source) is documented in ADR 0004.
- **H3 [fixed]:** the decay figure renders the phase BAND as the point estimate's
  dispersion and LABELS the bootstrap interval as the phase-0 strided CI, never an error
  bar on the median; pre/post regime means are plain descriptive segments.
- **H4 [fixed]:** the cross-underlying basis (Deribit index vs Binance spot) and the
  vol-vs-variance caveats are carried as artifact `caveats` data AND as figure
  footnotes, so an exhibit that travels without the README still carries them.
- Mediums/Lows folded in: tiered cross-platform tolerance in the reproduction test
  (exact point estimates; 1e-6 relative on the bootstrap CI / Politis-White block length,
  citing the in-repo `sharpe.py` `_phi` libm precedent, **M1**); pinned PNG metadata for
  byte-stable re-renders (**M2**); exact headline floats (**M3**); `json.dumps` over a
  hand-rolled emitter + a round-trip test (**M4**); a coherent two-study README reframe
  rather than a bolt-on section (**M5**); a stronger committed-manifest test asserting the
  fixture SHAs (**L1**); the vol-vs-variance figure label (**L2**); figures never recompute
  the bootstrap (**L3**).
- **upsert bug found + fixed while stamping:** `upsert_entries` located the preamble with
  `str.find("[[snapshot]]")`, which matched the COMMENTED `# [[snapshot]]` schema example
  and truncated the documentation. Fixed to find the marker only at a real line start;
  pinned by a regression test.

#### Post-implementation review (SHIP, 0 Critical/High/Medium, 4 Low)

The reviewer reproduced the committed headline bit-exactly by independent reconstruction,
confirmed the SHA stamps + `verify_snapshot` + the byte-identical JSON round-trip, the
series-vs-frame consistency, the alignment diagnostic surfacing a real join shortfall,
the figure honesty, the null-tail render path, and the boundary guard, and confirmed the
em-dash sweep. Resolved:

- **L1 [fixed]:** `build_vrp_artifact.py` carried a ruff E501 + a mypy `object`-typed
  return that the src-only gate did not catch. Fixed (typed `_headline` as
  `tuple[VrpHeadline, pl.DataFrame]`, wrapped the long line) AND extended the gate to
  `scripts/` (ruff + mypy) so script debt cannot recur; `run_null_gate.py` was already
  clean under the extended gate.
- **L2 [fixed]:** an empty regime would make `json.dumps` emit a bare `NaN` (invalid
  JSON). `artifact_to_json` now passes `allow_nan=False`, so a future empty-regime build
  fails loudly at write time (the shipped full-range artifact has no empty regime).
- **L4 [fixed]:** STATUS.md carried stale test/file counts; reconciled to the current
  128 offline + 10 network, mypy src + scripts.
- **L3 [accepted as-is]:** a tampered DVOL close reports "open must be positive" (the
  boundary checks the equal `o=h=l=c` in field order); functionally correct (it raises),
  cosmetically imperfect, left as-is.

#### Verification (against real data, not just fixtures)

The build script ran end-to-end on the live Deribit DVOL (1247 daily points) + Binance
Vision spot (1333 daily closes); the committed-fixture fidelity check passed (the
committed bytes reproduce the live headline exactly), and a re-run produced byte-
identical fixtures + artifact (only `fetched_utc` changes), confirming the live DVOL is
stable for the historical window. All 10 live `network` tests pass; the figures re-render
byte-stably from the committed artifact.

## 2026-06-04, session 4: the VRP pivot (ADR 0004) + the measurement floor (PR5a)

### The pivot: crypto variance risk premium (ADR 0004, merged)

The naive funding carry came back a clean net-of-cost null, so per the
pivot-on-failure rule the next strategy was chosen by reading the research,
surveying GitHub, and running a four-lens review (realist / quant / builder /
growth) plus an adversarial cross-check over a researched shortlist, gated by a
verified data-access spike. Decision (ADR 0004): pivot to a reproducible crypto VRP
study in two explicitly separated layers, a fully-reproducible index-level
measurement (Deribit DVOL minus realized variance) and a cost-gated short-variance
tradeable test (pre-registered as a likely cost/peso-bounded null). VRP won on
additivity (a third orthogonal premium-type), magnitude (the one crypto premium
large enough to make the kill gate a genuine both-ways test), and reproducibility
(it recovers the equity-VRP / vol-desk route deprioritized in ADR 0001, on free
data). The spike confirmed Deribit DVOL (free, keyless, US-reachable, daily from
2021-04) and the Tardis first-of-month free chains. Git note: a stacked-PR base did
not auto-retarget when its base merged, so PR4b first landed on the PR4a branch and
was re-landed on `main` via a corrective PR; future PRs base on `main`.

### VRP measurement floor (PR5a) on `feat/vrp-dvol-and-measurement`

Layer i, the reproducible measurement. Shipped:
- `data/sources/deribit_dvol.py`: a stdlib DVOL source (mirrors `okx.py`, injectable
  `http_get`); the range is fetched in deterministic sub-windows under the API's
  ~1000-point cap (a too-wide request silently drops the early tail).
- `data/boundary.py` `PydanticDeribitDvolRow` (validates the `[ts,o,h,l,c]` array),
  `data/records.py` `DvolRecord` + the `deribit` `Venue`, `data/clock.py`
  `CRYPTO_ANNUALIZATION_DAYS = 365`.
- `vrp/realized.py`: the matched-horizon realized variance `(365/W) * sum(log-return^2)`
  over a COMPLETE calendar window (the variance-swap convention matching DVOL;
  incomplete windows null; a calendar gap raises, never interpolates).
- `vrp/measurement.py`: `build_vrp_frame` (implied `(DVOL/100)^2` minus realized;
  forward = the ex-post measurement, trailing = the tradeable proxy; the spot-ETF
  regime split) and `vrp_headline` (the NON-OVERLAPPING strided forward series across
  all phases, with a block-bootstrap CI + the Politis-White block-deflated effective
  T, reusing the vendored stack).

**The first measured VRP** (live Deribit DVOL + Binance Vision spot, BTC,
2022-01..2025-06, 30-day): mean variance premium **0.0873** (phase band
[0.055, 0.109]), **95% bootstrap CI [0.033, 0.119] clearing zero** (overlap-honest,
effective T 13 from 42 strided), 70% of days positive, and a pre-ETF 0.101 ->
post-ETF 0.059 compression paralleling the funding-carry decay. The VRP is a real,
positive, statistically-significant premium; whether it survives option-selling
costs + the peso tail is Layer ii. 108 offline + 3 new network tests; mypy --strict
31 files, ruff, em-dash clean.

#### Design review (APPROVE-WITH-CHANGES, 3 Critical + 5 High, all resolved before implementing)

- **C1:** realized variance is the matched-horizon `(365/W)*sum(r^2)` on COMPLETE
  windows, not `mean(r^2)*365` (which drifts with the observation count on a gappy
  window).
- **C2:** the realized leg is the zero-mean sum of squared LOG returns (the
  variance-swap convention matching DVOL), verified against Deribit's published
  365-annualized model-free methodology.
- **C3:** the headline is the NON-OVERLAPPING strided forward-VRP series with a phase
  band + a block-deflated effective T (mirroring the carry `scoring.py`), not a
  dishonest t-stat on the 29/30-overlapping daily series.
- **H4** (forward t+1..t+W / trailing t-W+1..t no-look-ahead, the re-anchor identity),
  **H6** (one 365 constant on both legs; verified DVOL is 365-annualized), **H7**
  (gap-free calendar, raise not interpolate), **H8** (DVOL documented as
  live/as-of/mutable; the `deribit` Venue literal). **H5** (the Deribit-index vs
  Binance-spot basis) is caveated at the point of computation.

#### Post-implementation review (SHIP, 0 Critical/High)

The reviewer traced the estimator, the non-overlapping headline, the chunking fetch,
and the look-ahead identity in running code and confirmed every convention correct.
Five Medium/Low: **[M1, tracked]** the DVOL SHA256 manifest stamp + a committed CSV
fixture are DEFERRED to the committed-artifact PR (acceptable for PR5a because the
network test re-fetches and the as-of nature is documented, but it GATES the artifact
PR before the number is quoted as a reproducible headline); **[fixed]** the
`vol_spread` same-row filter + the `pw` display precision; **[noted]** the
phase-0-CI-vs-median-phase-mean seam is disclosed in the docstring, and a build-frame
alignment diagnostic is a tracked nit.

## 2026-06-03, session 3: the kill gate (PR4a per-trade math + PR4b the first kill number)

### The null + the first net-of-cost kill number (PR4b) on `feat/cost-model-pr4b-null-gate`

The second half of the kill gate: the random-entry null, the deflated-Sharpe
scoring, the reported exhibits, and the first net-of-cost number. Shipped:

- `strategy/null.py`: the entry-selection nulls (always-on, non-overlapping strided
  by H, seeded random subset), all drawn from `valid_entry_range`.
- `execution/scoring.py`: `return_moments`, `psr_zero` (the kill number = PSR(0) at
  the pre-signal `n_effective=1`), the lumpy/amortised `per_interval_series`,
  `effective_sample_size` (the block-deflated honest T), and `make_purged_cpcv` (the
  embargo>=H glue derived from the integer horizon).
- `execution/exhibit.py`: `early_gate`, `headline_score` (per-trade non-overlapping
  PSR(0) across all H phases + the lumpy/amortised diagnostic + the PW iid check),
  `funding_sign_regime`, `after_tax_sidebar`, and `gate_surface` / `is_killed`.
- `scripts/run_null_gate.py`: fetches the held-out post-ETF BTCUSDT frame and prints
  the venue x H x capital-multiple surface + the verdict.
- Data-layer fix (found by running the gate on the full window): Binance Vision
  switched its KLINE timestamps from milliseconds to MICROSECONDS in the late-2024
  dumps (the funding dumps stayed ms); `_kline_close_time_to_ms` normalizes both and
  rejects anything else. Plus a `py.typed` marker so the package types resolve for
  the script.

**The first net-of-cost kill number (live Binance Vision, BTCUSDT 2024-01-11 to
2026-05-31, 2616 funding events): KILL.** Net-of-cost Deflated Sharpe (PSR(0)) =
0.0000 on every tradeable venue (Kraken, Hyperliquid) at every horizon (H in
1..189) at the conservative 2N capital charge; the round-trip cost (about 69 bps
Kraken) dwarfs the median funding (0.6 bps at H=1 to 89 bps at H=189) at every
horizon, and the 2N financing opportunity cost (about 8%/yr) roughly equals the
funding (about 5.7%/yr) so the carry barely breaks even even before trading costs.
The bracket holds: at the favourable 1N capital charge every tradeable cell still
fails the 0.95 bar (the closest is the non-tradeable reference venue at a 63-day
hold, DSR 0.60). The naive always-on / random-entry carry is non-viable for
real-money deployment; any edge must come from selection, which raises the bar.
This is the honest pre-registered null. 96 offline + 8 network tests; mypy --strict
26 files + the script; ruff + em-dash clean.

#### Design review findings and resolutions (senior-quant design review: APPROVE-WITH-CHANGES, 3 Critical + 3 High)

The review ran experiments against the actual vendored `sharpe.py` / `bootstrap.py`.
All resolved before implementing (ADR 0003 amendments B1 to B7):

- **C1 [fixed, B1]:** the claim that lumpy cost lowers the DSR via the skew/kurtosis
  penalty is backwards (for a negative-mean series the tail term can RAISE it); the
  real mechanism is per-interval variance inflation. Resolution: the kill reads the
  empirical `min(lumpy, amortised)`, not an assumption, pinned by a test.
- **C2 [fixed, B2]:** findings 2 and 9 named different series (per-interval lumpy vs
  per-trade non-overlapping) whose DSR differs by more than the threshold.
  Resolution: declare the per-trade non-overlapping net series THE headline
  (cost-placement-invariant); the per-interval pair is a diagnostic; kill reads the
  min.
- **C3 [fixed, B3]:** the lumpy/amortised distinction is vacuous on the always-on
  book (uniform cost in steady state). Resolution: each exhibit scoped to its null
  (early gate / sign regime / contamination on always-on; headline DSR + lumpy on
  non-overlapping).
- **H1 [fixed, B4]:** the embargo derived from a float `H/n` can floor to `H-1` and
  spuriously abort. Resolution: `embargo_pct = max(0.05, (H+0.5)/n)`, then assert
  `_embargo_count >= H`, with a test over the float-edge cases (79,21) and (55,7).
- **H2 [fixed, B4]:** dressing the pre-signal number as "OOS under CPCV" is
  dishonest (no fitting -> CPCV is degenerate). Resolution: framed as the
  full-sample PSR(0) on the held-out post-ETF REGIME; the CPCV is wired +
  embargo-asserted but explicitly degenerate until a signal exists.
- **H3 [fixed, B5]:** the venue x H grid is an un-deflated CONTROL set. Resolution:
  recorded under one control family at `naive_effective_n=1` -> PSR(0); the kill
  reads tradeable cells; the trigger that ends the PSR(0) regime is documented.
- Resolved highs/mediums: financing reported at BOTH `capital_multiple` 2.0 and 1.0
  with the verdict bracketed (B6, distinguishing the owned-spot OPPORTUNITY cost
  from a borrow cost); the non-overlapping DSR across all H phases with the PW iid
  check (M3); `scoring.py` is a PR4b module (B7).

#### Post-implementation review findings and resolutions (senior-quant post-impl review: FIX-THEN-SHIP, 2 High)

The review reproduced the kill numbers from first principles and confirmed the KILL
is SOUND (not a false kill; the cm=1 floor is round-trip-cost-dominated). Resolved:

- **H1 [fixed]:** the headline computed the Politis-White block length (9.68,
  iid_ok=False on real data: funding-regime persistence makes even strided trades
  serially dependent) but ignored it, taking T at face value (a false-pass landmine
  for the signal milestone). Resolution: `psr_zero` deflates T to the block effective
  sample size `floor(T/block)`; `effective_t` + the block length are reported; pinned
  by a test.
- **H2 [fixed]:** ADR B2 wrongly claimed the strided series is near-iid (PW<=1).
  Resolution: corrected the B2 text to acknowledge PW~9.7 on the real data and that
  the T-deflation is what restores honesty.
- **M3 [fixed]:** `gate_surface` admitted a short frame that `headline_score` then
  rejected (a crash). Resolution: skip a cell unless `height > 2H`.
- **M4 [fixed]:** the trial-registry rows recorded normal moments, so they could not
  reproduce the per-trade DSR. Resolution: record the realized phase-0 per-trade
  moments + the block-deflated effective T; the authoritative dsr_kill rides in the
  metadata.
- Presentation [fixed]: the after-tax sidebar summed the overlapping always-on batch
  (a meaningless aggregate); it now uses the non-overlapping (deployable) series.

#### Verification (against real data, not just fixtures)

The kill gate runs end-to-end on the live Binance Vision post-ETF window (the
microsecond-kline fix was discovered and fixed precisely because the full window
exercised the late-2024 us-stamped dumps). The funding-sign regime is 84% positive
(the short collects) / 16% negative; price_pnl contamination ratio is 0.001 (the
static-notional proxy is not padding the carry); batch-vs-scalar parity holds on the
real frame. The verdict reproduces deterministically.

### Cost model + per-trade carry P&L (PR4a) shipped on `feat/cost-model-pr4a-per-trade-pnl`

The first half of the kill gate: the per-trade math everything downstream is built
on, no RNG and no IO. Three new modules under `src/riskpremia/execution/`:

- `errors.py`: the loud-failure hierarchy (`ExecutionError` / `CostModelError` /
  `CarryComputationError`), mirroring `data/errors.py`.
- `cost.py`: a frozen `VenueCostModel` charging both legs both sides (taker/maker
  fee + bid-ask half-spread per leg, the no-cross-margin 2N financing cost), with
  REAL cited base-tier fee schedules verified June 2026: Kraken Pro spot 26/16 bps
  + Kraken Futures perp 5/2 (tradeable), Hyperliquid perp 4.5/1.5 (tradeable), and
  Binance/OKX as non-tradeable reference points. Spreads are provisional
  conservative assumptions (`spread_basis="assumed"` -> `provisional=True`); the
  measured-spread follow-up replaces them. Kraken round-trip = 69.0 bps exactly.
- `carry.py`: `funding_window_indices` / `valid_entry_range` (the single source of
  truth for the window and the entry bound), the `TradePnL` record, `simulate_trade`
  (scalar), `per_interval_pnl` (the conservation harness), `simulate_batch` (the
  polars-vectorised batch), and `price_pnl_contamination` (the ADR A3 guard).

26 new offline tests + 3 live `network` tests. The three `kill_gate`-marked tests
pin the invariants whose failure would void the gate: the funding-sign economic
fixture (through the real Decimal boundary), the funding-window index identity vs
`make_label_horizons`' `dt.shift(-H)`, and the per-trade P&L conservation. Toolchain
green: 83 offline + 8 network pass, mypy --strict 23 files, ruff clean, em-dash clean.

ADR 0003 amended (A1 to A3) and the per-trade math (findings 1, 4, 5, 6) implemented.

#### Design review findings and resolutions (senior-quant design review: APPROVE-WITH-CHANGES, 2 Critical + 4 High)

The review grounded itself in the actual `clock.py` / `records.py` / `sharpe.py`
code and CONFIRMED the load-bearing math (the funding sign, the `range(i+1, i+H+1)`
window, its identity with `dt.shift(-H)`, the round-trip "two full spreads"
algebra, the batch `c[i+H]-c[i]` formula). Resolved before implementing:

- **C1 [fixed]:** the `entry+H < height` boundary was stated two ways (scalar guard
  vs batch slice), so a future off-by-one could let one path book a truncated-window
  trade the other rejects. Resolution: one definition (`funding_window_indices` /
  `valid_entry_range`); the scalar guard asserts `window.stop <= height` and the
  batch slices `range(0, height-H)` from it; a `kill_gate` test pins the row count
  and the `entry=height-H` raise.
- **C2 [fixed, ADR A1]:** the ADR financing FORMULA omitted the factor of 2 the
  prose ("2N capital tied up") requires. Resolution: keep `capital_multiple=2.0`
  (the conservative, economically correct no-cross-margin charge; the additive drag
  genuinely lowers the DSR, it is not Sharpe-neutral), amend ADR line 65, pin the 2x
  with a test.
- **H3 [fixed, ADR A2]:** financing used the nominal `H*interval`, which understates
  the drag on the irregular early history the baseline leans on. Resolution: use the
  real wall-clock hold `dt[i+H]-dt[i]` (both paths; pinned by a 16h-gap test).
- **H4 [fixed]:** the batch-vs-scalar funding parity must be `abs(...) < 1e-12`, not
  `==`, because the rolling-sum vs left-to-right sum cancel differently on a long
  mostly-positive funding series. Resolution: `BATCH_SCALAR_ATOL = 1e-12`, documented;
  the batch funding uses `rolling_sum(H).shift(-H)` (sums exactly H terms, minimal
  cancellation).
- **H5 [fixed, ADR A3]:** `funding_collected` is a separate field; the early-gate
  break-even reads `median(funding_collected)`, NOT `median(gross)` (so the signed
  basis-convergence proxy cannot pad the cost hurdle); the contamination guard
  reports the SIGNED `mean(price_pnl)` (the bias is one-sided short gamma), not only
  `median|price_pnl|`.
- **H6 [fixed]:** `entry_taker`/`exit_taker` split + per-leg (spot/perp) half-spreads
  so the cost surface can model the realistic maker-in / taker-out without forcing a
  single style.
- Mediums/Lows folded in: the `provisional` flag + required `source` citation; the
  `per_interval_pnl` scoped as a conservation harness (not the PR4b per-period
  series); explicit float narrowing for mypy --strict; the exact-add field algebra
  invariants; the sign test consuming the real boundary path.

#### Post-implementation review findings and resolutions (senior-quant post-impl review: FIX-THEN-SHIP, 1 High)

The reviewer traced the index math and conservation on a running interpreter and
verified the math is correct by execution (not by reading comments). Resolved:

- **H1 [fixed]:** `simulate_batch` dropped a trade on an interior null FUNDING rate
  (it only checked null prices) while the scalar path raised, breaking the C1
  same-input/same-result guarantee (a funding gap would silently shrink the trade
  count when PR4b takes `median`/`mean`, which skip nulls). Resolution: the batch
  null guard now also rejects a null `funding_collected` within the valid range,
  with a regression test.
- **Determinism defect found while fixing H1 [fixed]:** the batch `hold_hours` used
  polars `.dt.total_seconds()` (integer-second truncation) while the scalar used
  Python `.total_seconds()` (microseconds), so on the real frame's sub-second
  settlement jitter the two financing terms disagreed by ~2.5e-9 (a real batch/scalar
  divergence, caught by the new real-data parity spot-check). Resolution: both paths
  now compute the hold from integer microseconds, numerically identical.
- **M2 [fixed]:** the contamination threshold was `< 1.0` (would wave through a proxy
  half the size of the funding). Resolution: `PRICE_PNL_CONTAMINATION_LIMIT = 0.25`,
  tied to ADR A3's "non-trivial fraction" (the realized post-ETF ratio is 5 to 7%).
- **L3 [fixed]:** the A3 signed-mean guard lived only in a network-gated test.
  Resolution: extracted `price_pnl_contamination` and added an offline unit test of
  the guard logic (clean / contaminated / degenerate frames).
- **L4 [fixed]:** the `BATCH_SCALAR_ATOL` justification was narrated, not pinned on
  the real frame. Resolution: the network test now spot-checks batch-vs-scalar parity
  on the live BTCUSDT frame at the tolerance.

#### Verification (against real data, not just fixtures)

The live Binance Vision pull builds the held-out post-ETF BTCUSDT frame
(2024-06..09) and runs the vectorised batch under the Kraken cost model. GROSS
median funding rises with the hold (0.75 bps at H=1, to 15.3 bps at H=21) while the
round-trip cost is a fixed ~69 bps, so the naive always-on taker carry does not
clear the cost at any tested horizon (the early-gate kill previews cleanly; PR4b
produces the deflated number). The signed `mean(price_pnl)` is 5 to 7% of mean
funding (the static-notional proxy is not contaminating the carry mean), though at
H=1 the per-trade `median|price_pnl|` (9.5 bps) is comparable to the funding itself
(an honest per-trade-variance caveat at short holds). Batch-vs-scalar parity holds
on the real frame at 1e-12.

## 2026-06-03, session 2: GitHub + data layer (PR1+PR2+PR3) + cost-model design

### Cost model + random-entry null: design locked (ADR 0003)

The kill-gate milestone was designed (a file-by-file plan) and put through an
independent senior-quant design review that grounded itself in the actual code.
The review verified the per-trade off-by-one against `make_label_horizons`
(entry i owns settlements i+1..i+H, the same trade the CPCV label scores) and
returned APPROVE-WITH-CHANGES with three merge-blocking findings, all resolved in
ADR 0003:

- **C1 (funding sign):** the repo's `funding_rate` wording and the negative
  default test fixtures made the short-collects-funding sign a trap. Resolution:
  freeze the convention (`funding_rate` positive = longs pay shorts; the short
  book collects `+sum(funding_rate)`) and pin it with an economic-direction
  fixture, never a comment.
- **C2 (cost amortisation inflates the Deflated Sharpe):** smearing the
  once-per-trade round-trip cost across H intervals shrinks the realized
  skew/kurtosis the DSR penalises and inflates it. Resolution: book the cost on
  the interval it is incurred (lumpy), report amortised-vs-lumpy as a diagnostic,
  and the kill decision reads the less favourable.
- **C3 (CPCV embargo blind to the hold overlap):** an always-on carry with H>1
  has overlapping holds; the fraction-of-T embargo can be smaller than H, leaking
  across the train/test boundary. Resolution: force `embargo_count >= H`.

Plus the resolved highs: a financing/capital cost for the no-cross-margin 2N
capital base; the DSR headline read PRE-tax (tax is a personal level-shift, not a
property of the edge) with after-tax as an annual sidebar; a non-overlapping
return series so the DSR `T` is honest; the random-entry null recorded as a
separate control family (so at this pre-signal milestone the kill number is
PSR(0) at n_effective=1); a measured-or-conservative spread so the most-likely
loss cannot be soft-assumed into a false pass; and a funding-sign-regime
decomposition. ADR 0003 carries the full locked design; PR4a/PR4b implement it.

## 2026-06-03, session 2: GitHub + data layer (PR1+PR2+PR3)

### Data-layer PR3 (OKX live source + Binance-vs-OKX funding delta) + ADR 0002 amendment

Completes the cut-to-ship data layer. Shipped on `feat/data-layer-pr3-okx`:

- `data/sources/okx.py`: a stdlib OKX source (paginates `funding-rate-history`
  backward via `after=`), the US-reachable kill-gate venue. PIT realized gate
  (`PydanticOKXFundingRow.to_record`): accept a row only when `realizedRate` is
  present, `method == "current_period"`, and the settlement instant is strictly
  before now; use `realizedRate` (the paid rate), never the predicted
  `fundingRate`, and never read the predicted `/funding-rate` endpoint.
- `data/cross_venue.py`: the Binance-vs-OKX funding delta on the matched
  settlement grid (the venue-basis measurement, design finding 5).
- **Two empirical findings** (verified live): OKX public funding history is
  RECENT-ONLY (~93 days), so it is the live/recent kill-gate venue and the delta
  is measured on the recent overlap as an adjustment, not over 2024-2026; and
  Binance Vision `calc_time` carries a few MS of jitter around the settlement
  instant while OKX is clean, so the delta snaps both `dt` to the funding grid
  (`dt.dt.round`) before joining (a naive timestamp join lost ~half the events).
- **httpx removed**: with OKX on the stdlib too, the whole data layer fetches with
  `urllib` + `json` (zero third-party fetch surface); the `dataops` extra is gone
  and CI installs `.[dev]`. OKX 403s the default `Python-urllib` User-Agent, so a
  descriptive UA is sent.
- ADR 0002 amended (decisions 9 to 13). 9 OKX/delta offline tests + 3 live
  `network` tests; live-verified (OKX recent funding + the small venue basis).

#### Review findings and resolutions (post-implementation review: FIX-THEN-SHIP)

The review confirmed the PIT gate (realized-only, paid `realizedRate`, predicted
endpoint never touched) and the grid-snap are correct, with determinism intact.
No Critical. Resolved:

- **H1 [fixed]:** removing the `dataops` extra left the README Setup command
  installing `.[dev,dataops]`, which now errors. Fixed the README to `.[dev]` and
  reconciled the stale CHANGELOG reference.
- **M2 [fixed]:** `OKXSource` did not implement the `FundingSource` Protocol's
  `available_months`. Added it, deriving the months from the recent retention
  window (OKX has no listing API), with a test.
- **M3 [fixed]:** added a non-progress guard to the backward-pagination loops
  (`if oldest >= after: break`) so a hypothetical boundary-inclusive page cannot
  cause a re-fetch loop or duplicates.
- **M4 [fixed]:** the grid-snap now fails loudly (`VenueFetchError`) if snapping
  collapses two real events to one point (an irregular sub-grid series the overlap
  measurement is not valid on), with a test; the 8h/8h case is provably
  collision-free.
- **L5 [fixed]:** `retention_floor` now parses through the pydantic boundary
  rather than reading the raw JSON key, honoring the loud-failure contract.
- **L6 [noted]:** `_MAX_PAGES` is a backstop that cannot bind today (~5.5 years vs
  OKX's ~93-day retention); a signal-on-exhaustion is a later refinement.

Toolchain: ruff clean, mypy --strict clean (20 files), 57 offline + 5 network
tests pass, em-dash clean.

### Data-layer PR2 (Binance Vision source) + ADR 0002

Shipped on `feat/data-layer-pr2-binance-vision`:

- `data/sources/base.py` (the `FundingSource` / `MarkSource` / `SpotSource`
  Protocols; sources return typed records, `clock` normalizes them) and
  `data/sources/binance_vision.py`: stdlib-only S3 listing with marker
  pagination, checksummed download with an idempotent content cache (verify the
  published SHA256 before parsing any bytes), and funding / mark-price / spot
  parsing. `clock.marks_frame` / `spot_frame` build the as-of-join price frames
  (deduped on `period_end_ts` at the source).
- Locked-fix fidelity: the perp leg reads `markPriceKlines` (the MARK price, since
  funding settles on mark not trade price) and the spot leg carries an explicit
  matched `quote="USDT"`, so the basis is a matched-product computation (finding
  C3); a pre-committed `SURVIVOR_UNIVERSE = (BTCUSDT, ETHUSDT)` with no multi-coin
  median, caveated in the module + ADR 0002 (finding C4).
- Committed a real BTCUSDT-2020-01 funding zip + its CHECKSUM and a full
  S3-listing XML as offline fixtures (gitignore zip-exception added). 9 offline
  tests (`urlopen` monkeypatched) + 2 live `network` integration tests.
- **Real-data verification:** the live S3 end-to-end pull works (93 funding
  records for 2020-01 matching the committed fixture; mark + spot + a
  single-digit-percent basis built into the CPCV-ready frame). It also surfaced a
  genuine PIT detail: the first event of an isolated window has no prior mark, so
  the backward as-of join returns null rather than leaking a future price; the
  realistic study pattern (a price warm-up before the funding window) is used.
- ADR 0002 (the data layer + the funding-event clock) written, ships with PR2.

#### Review findings and resolutions (post-implementation review: SHIP)

The review verified PIT-safety, reproducibility (checksum-before-parse, corrupt
cache detected + re-fetched + re-verified, cache-hit fully offline), determinism,
and the C3/C4/finding-6 fidelity are all correct. No Critical/High. Folded in:

- **L1 [fixed]:** dropped a dead `and not name.endswith(".CHECKSUM")` clause in
  `available_months` (a `.zip.CHECKSUM` name already fails the `.zip` check).
- **L2 [fixed]:** `_download_and_verify` now asserts the parsed CHECKSUM filename
  matches the target file, not just that some bytes hash matches.
- **L5 [fixed]:** added a multi-month fetch test and a corrupt-cache RECOVERY test
  (the unlink + re-fetch + re-verify branch and the per-month loop are now locked
  by committed tests, not just verified manually).
- **L3, L4 [deferred, reviewer-agreed]:** unconditionally refreshing the cached
  `.CHECKSUM` would break the offline cache-hit property (the reviewer judged the
  current trade better); URL-encoding the S3 `marker` rides with the deferred full
  pagination generality (latent: BTCUSDT funding is a single non-truncated page).

Toolchain: ruff clean, mypy --strict clean (18 files), 45 offline + 2 network
tests pass, em-dash clean.

### Shipped

- **Repo on GitHub** (https://github.com/sjdoane/riskpremia). README
  restructured as a reviewer front door (honest WIP status, the question, the
  pre-registered kill criterion, a methodology table, the reproducibility story,
  a reading map). `main` pushed (scaffold + plan + README commits).
- **Data-layer PR1 (typed core)** on branch `feat/data-layer-pr1-typed-core`:
  `data/errors.py` (loud-failure hierarchy), `records.py` (attrs carriers +
  cross-venue canonicalization; `premium` carried, perp MARK price, explicit spot
  `quote`), `boundary.py` (the pydantic IO boundary, `extra="forbid"` on the
  immutable Binance CSV), `clock.py` (ms-to-UTC chokepoint, realized-aware
  deterministic dedup, median-robust interval guard, backward as-of join,
  per-event label horizons), `manifest.py` (SHA256 + CHECKSUM parsing + TOML
  read/write/verify). Committed the verified BTCUSDT-2020-01 fixture.
- **28 new tests (36 total).** The centerpiece CPCV contract test feeds the
  observation frame + label horizons into the REAL vendored `CPCVSplitter` /
  `PurgedKFoldSplitter` (not a mock) and asserts the splits + gates. Plus the PIT
  backward-join test, the Float64-vs-Decimal basis check, and the conflict /
  gross-interval / multi-instrument / seconds-vs-ms / extra-column failure modes.
- Found + pinned the Windows `tzdata==2026.2` requirement (polars needs it to
  resolve the "UTC" tz string when materializing tz-aware datetimes).

### Review findings and resolutions

Data-layer milestone ran the rule-1 gate (recorded in session-1 entry): design plan
-> design reviewer (APPROVE-WITH-CHANGES, 5 Critical/High resolutions). PR1 then ran
a senior-quant **post-implementation review (FIX-THEN-SHIP)**:

- **C1 [High, fixed]:** `derive_canonical` stripped `USD` before `BUSD`, so
  `BTCBUSD` wrongly yielded `BTCB` (a silently-wrong cross-venue join key).
  Resolution: order suffixes longest-first (`USDT, USDC, BUSD, USD`) + a
  `BTCBUSD -> BTC` test.
- **L2 [Low, fixed]:** `parse_checksum_line` left the GNU binary-mode `*` marker
  in the filename. Resolution: strip a single leading `*`.
- **L3 [Low, fixed]:** `make_label_horizons` did not assert its input was sorted
  (a partial-lookahead foot-gun on a public function). Resolution: raise on an
  unsorted `dt`.
- **L4 [Low, deferred to PR2 with a documented precondition]:** the as-of join
  ties on input order under duplicate price stamps. Resolution: docstring
  precondition (price sources dedup at source; kline/spot closes are unique).
- **L5 [Low, fixed]:** the manifest writer emitted leading blank lines on an
  empty preamble. Resolution: special-cased empty preamble.
- The reviewer independently VERIFIED (not findings): the backward as-of join
  cannot pull a future price; `make_label_horizons` has no partial-label
  lookahead and satisfies cv.py's `_require_label_horizons` + purge predicate; the
  dedup is order-deterministic via the stable `_ingest_idx`; every Critical/High
  design review resolution is present in code, not narrated.

### Verification (against real data, not just mocks)

- The committed real fixture flows through boundary -> records -> normalize ->
  observation end to end (`dt` is `Datetime(us, UTC)`, canonical `BTC`, exact
  rate preserved, the deliberate ~30-day gap surfaces as a 0.33 diagnostic, not a
  false failure). mypy --strict 15 files clean, ruff clean, pytest 36/36, em-dash
  clean in the riskpremia venv.

## 2026-06-03, session 1: scaffold + week-1 data-access spike

### Shipped

- **Project scaffold.** Clean dedicated venv `C:\Users\SamJD\.venvs\riskpremia`
  (Python 3.12.13). Pinned `pyproject.toml` (polars 1.41.1, numpy 1.26.4,
  pydantic 2.9.2, attrs 24.2.0; dataops extra httpx 0.27.2 (REMOVED in PR3); dev pytest 8.3.3 /
  mypy 1.13.0 / ruff 0.7.4 / pytest-cov 5.0.0 / pytest-env 1.1.5), mypy --strict
  config, ruff config, pytest config (PYTHONHASHSEED=0, warnings-as-errors).
  `.gitignore`, MIT `LICENSE`, `data/snapshots/manifest.toml` stub. Installed
  versions verified to match the pins exactly.
- **Vendored analytics/validation stack** from pit-backtest (commit `edad904`),
  each file carrying a provenance header: `analytics/sharpe.py`,
  `analytics/bootstrap.py`, `validation/cv.py`, `validation/trial_registry.py`.
  Vendored (not a path dependency) so a reviewer regenerates every number from
  THIS repo alone. `tests/unit/test_vendored_stack.py` pins the canonical
  numerical results (8 tests, all green; Bailey-LdP 2014 DSR = 0.7657 vs the
  0.766 pin; CPCV(6,2) = 5 paths; bootstrap seed-determinism).
- **Week-1 data-access spike** run end-to-end. WRDS: zero setup on the machine,
  entitlement not confirmable without the user's WRDS login, non-redistributable even if entitled.
  Crypto: OKX + Hyperliquid live and US-reachable; Binance Vision S3 dumps
  (checksummed, from 2020-01) reproducible and US-reachable; live Binance/Bybit
  APIs geo-blocked from the US IP.
- **ADR 0001 (lead-track selection):** Track B (crypto funding carry) chosen as
  lead, with the pre-registered kill criterion declared upfront.

### Review findings and resolutions

The lead-track fork ran the rule-1 process: a four-lens review + adversarial
adversarial cross-check.

- **Four-lens review (realist, quant, builder, growth): unanimous Track B, HIGH
  confidence, identical flip condition** (confirm BOTH WRDS entitlement AND a
  pure vol-desk target). Recorded in ADR 0001. No dissent to resolve.
- **Cross-check C1 [Critical, accepted]:** the cost model, capacity curve, and kill
  gate must be parameterised to a genuinely US-TRADEABLE venue, not the Binance
  data venue, or the kill gate runs against costs that cannot be incurred.
  Resolution: locked decision 3 in ADR 0001; the cost-model milestone picks a
  US-tradeable venue with a real fee schedule.
- **Cross-check H1 [High, accepted]:** restructure the user escalation so career
  target is the PRIMARY question, WRDS conditional. Resolution: the user-facing
  question leads with career target; WRDS is the conditional follow-up.
- **Cross-check H2 [High, accepted]:** portfolio-redundancy risk (a second
  reproducible null must show range, not repeat the momentum null). Resolution:
  positioning in ADR 0001 decision 8 + the additivity argument (different market,
  different premium, retail-tradeable, risk-engineering contribution).
- **Cross-check M1 [Medium, accepted]:** add crypto landmines to the risk register
  (US venue access, both-legs financing + capital tie-up, exchange-solvency fat
  tail, coin/venue survivorship). Resolution: ADR 0001 locked decision 6.
- **Cross-check note [accepted]:** the 4-0 unanimity is partly over-determined (all
  lenses key off the non-redistributable-data fact), so confidence is discounted
  from "4-0" to "strong but single-fact-dominated." The career-target escalation
  is the honest hedge.

### Career-target fork resolved

- Asked the user (career target is the only input that could promote Track A).
  The user deferred the call ("make the decision"). Track B is
  LOCKED; framing default is broad / systematic / reproducibility-first; no
  WRDS/OptionMetrics chase. STATUS + memory updated.

### Data-layer milestone: planned + design-reviewed (rule 1)

- **design plan (senior quant-infra architect)** produced a file-by-file data-layer
  plan grounded in the live-verified vendor facts. Empirical groundwork confirmed:
  Binance Vision funding zips download + checksum-verify (schema
  `[calc_time, funding_interval_hours, last_funding_rate]`, 94 rows for 2020-01);
  OKX funding history does NOT page back past ~2021 (so it is live/recent only,
  not the long-history backbone); Hyperliquid funds HOURLY (not 8h) with a thin
  spot leg. Design captured in `docs/research/0001-data-layer-design.md`.
- **design reviewer (senior quant/data-infra)** returned APPROVE-WITH-CHANGES after
  probing the live endpoints itself. Findings and resolutions (all accepted):
  - **C1 [Critical]:** the plan's OKX realized-gate premise was FACTUALLY WRONG
    (the `/funding-rate-history` head row is already settled, not future; the
    predicted rate is in the separate `/funding-rate` endpoint). Resolution: gate
    on `realizedRate is not None AND method == "current_period" AND window_end <
    now` (strict `<`); never read `/funding-rate`; exclude the predicted field
    from the record path.
  - **C2 [Critical]:** Binance funding is a clamped interest + premium composite;
    reporting it as "the premium" is a category error. Resolution: document it as
    the realized clamped cash flow, keep the `premium` component, add a
    clamp-incidence diagnostic.
  - **C3 [Critical]:** the basis must use the perp MARK price vs a matched,
    snapshotted, same-quote spot product; Hyperliquid basis set null (off-venue
    spot not yet reproducible).
  - **C4 [Critical]:** Binance Vision survivorship biases the premium up; v1
    headline universe is a pre-committed survivor set (BTCUSDT then ETHUSDT), NOT
    a multi-coin median; caveated in ADR 0002 + methodology.
  - **H5 [High]:** quantify the venue-basis confound (emit a Binance-vs-OKX
    funding delta on the matched grid; kill gate on OKX-realized, decay headline
    on Binance), plus determinism/test items (tz-aware dtype parity assertion,
    horizon gap-guard + length-parity assert, Decimal-vs-Float64 basis test,
    `extra="forbid"` only on the immutable CSV, committed regeneration script +
    byte-equality test, pinned spot-ETF regime constant, tolerance-banded
    modal-gap warning, realized-aware dedup).
  - **Scope [accepted]:** the reviewer's CUT TO SHIP FASTER (BTCUSDT Binance
    backbone + OKX-realized delta; defer Hyperliquid, retention probes,
    multi-coin, full pagination) roughly halves pre-cost-model LOC, honoring
    rule 6. PR split locked in the design doc (PR1 heart, PR2 Binance, PR3 OKX).

### Verification (against real behaviour, not just mocks)

- Crypto endpoints hit live from the machine (real OKX JSON + real geo-block
  responses confirm the network path and the findings). The design reviewer
  independently re-probed OKX/Binance live and corrected the OKX gate premise.
- Vendored stack imported and executed in the venv: DSR canonical pin reproduced
  to 1e-3; CPCV path count + bootstrap determinism confirmed.
- Em-dash sweep clean on all new files (verified before commit).

### Deferred

- Career-target confirmation (user); US-tradeable venue choice (cost-model ADR);
  Binance Vision history depth + instrument survivorship (data-layer milestone);
  CI workflow (after the first real milestone).
