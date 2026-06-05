# 0003: the CTREND fitted signal (Study 3, PR2)

The reviewed design of the first fitted model in the project: the 28 daily technical
features + the cross-sectional combined elastic-net (CS-C-ENet) aggregation of Fieberg et
al. (JFQA 2025), fit strictly point-in-time on a rolling 52-week window, producing
per-(week, coin) CTREND forecasts + quintile assignments. Written after a design plan and
an independent senior-quant design review; the per-finding resolutions are in CHANGELOG.md.

The kill gate (net-of-cost Deflated Sharpe under event-time-purged CPCV with the
trial-registry multiplicity deflation) is PR3. PR2's real-data proof is the GROSS signal
quality (a positive point-in-time cross-sectional rank IC + a monotonic quintile spread),
the analogue of the VRP Layer-i positive measurement before the Layer-ii gate. A positive
gross IC is necessary, not sufficient: it says nothing about net-of-cost survival.

## Faithfulness caveat (C1, load-bearing): the exact indicator formulas

The paper's 28 indicators are defined precisely only in a Supplementary Material Appendix A
(a separate file); the main text gives a prose characterization plus the non-obvious
parameters. The supplement was not obtainable (SSRN is login-walled, the Cambridge
supplement and the Corvinus mirror were unreachable). So the indicators are implemented
with the paper's STATED parameters where given, and the CANONICAL practitioner defaults
(which the paper invokes by calling these indicators "popular among market practitioners")
where not. The paper STATES: the 7 SMA lengths (3/5/10/20/50/100/200), the 14-day RSI and
stochastics, the 3-day %D, the 12/26-day MACD EMAs + the 9-day signal line, the 20-day /
2-std Bollinger bands, and the StochRSI prose formula. The CANONICAL defaults used for the
unstated parameters (each a documented convention + a PR3 trial-registry robustness knob):
Wilder smoothing for the RSI, a 20-day CCI on the typical price (H+L+C)/3 with the 0.015
constant, a 20-day Chaikin money flow, 12/26/9 EMAs for the volume MACD (PVO), and an
`adjust=False` EMA seeded by the leading SMA. Obtaining Appendix A to tighten these is a
tracked follow-up; the choices are second-order (a common multiplicative or period shift
on one of 28 averaged signals) and are reported as robustness knobs.

## The 28 daily technical signals (computed on the daily panel, sampled weekly)

Momentum oscillators (5): `rsi` (14-day Wilder RSI), `stochK` (14-day %K = (close -
min_14 low) / (max_14 high - min_14 low)), `stochD` (3-day SMA of stochK), `stochRSI`
((rsi - min_14 rsi) / (max_14 rsi - min_14 rsi)), `cci` (20-day, (TP - SMA_20(TP)) / (0.015
* mean_abs_dev_20(TP)), TP = (high+low+close)/3).

Price moving averages (9): `sma_{3,5,10,20,50,100,200}d` = SMA_L(close) / close;
`macd` = (EMA_12(close) - EMA_26(close)) / EMA_12(close); `macd_diff_signal` = macd -
EMA_9(macd).

Volume (10): `volsma_{3,5,10,20,50,100,200}d` = SMA_L(dollar_volume) / dollar_volume;
`volmacd` = (EMA_12(dollar_volume) - EMA_26(dollar_volume)) / EMA_12(dollar_volume);
`volmacd_diff_signal` = volmacd - EMA_9(volmacd); `chaikin` = 20-day Chaikin money flow =
sum_20(mfv) / sum_20(dollar_volume), mfv = ((close-low) - (high-close)) / (high-low) *
dollar_volume (a documented dollar-volume convention; standard Chaikin uses base volume,
a second-order difference since the multiplier is dimensionless).

Volatility (4): `boll_mid` = SMA_20(close) / close; `boll_high` = (SMA_20 + 2*std_20) /
close; `boll_low` = (SMA_20 - 2*std_20) / close; `boll_width` = (boll_high - boll_low) /
boll_mid (= 4*std_20/SMA_20, close-independent). std is the 20-day population std (ddof=0,
the Bollinger standard; a common per-week factor, so rank-innocuous, pinned for fidelity).

Every indicator is strictly backward (rolling/EWM ending at each day; no centering) and is
NULL until its full window is available (a partial-window value is non-comparable; a coin
without the horizon simply has no signal that week). Each is sampled at the weekly
rebalance date = the last daily bar at-or-before each week_end (the PR1 Sunday grid).

## The PR1 panel extension (a prerequisite revealed by the exact feature list)

4 signals (stochK, stochD, cci, chaikin) need daily HIGH + LOW, which PR1's committed panel
lacked (close + dollar volume only). So PR2 extends the daily panel to carry high + low
(`SpotKlineRecord` + `_parse_kline_zip` (now a 5-tuple, cols 2/3/4/7) + `build_daily_panel`
+ the fixtures + the committed `.csv.gz`). The WEEKLY grid + eligibility are UNCHANGED (they
read close + dollar volume), so PR1's eligibility numbers are byte-identical; only the
committed-panel content SHA + the artifact fingerprint + the manifest stamp refresh, and the
PR1 schema tests move from 4 to 6 columns. Guards: high >= close, low <= close, high >= low,
low > 0. No signal needs OPEN, so open is deliberately not stored. The Chaikin
dollar-volume convention (above) avoids needing base volume.

## The CS-C-ENet aggregation (eq 3-11, faithful)

1. Cross-sectionally RANK each signal over the eligible universe each week and map to
   [-0.5, 0.5] via `(rank-1)/(N-1) - 0.5` (Kelly-Pruitt-Su / Gu-Kelly-Xiu, the closed
   interval the paper cites), average-rank ties, computed within each week from that week's
   non-null observations; a week/signal with N<2 non-null observations yields no regression.
2. Per signal j, a cross-sectional UNIVARIATE OLS each week (eq 7): forward_return(W_m) on
   the ranked z_j(W_m), giving (alpha_{j,m}, beta_{j,m}). Smooth over the trailing M=52
   weeks (eq 4-5): the mean of (alpha, beta) over m in {t-52, ..., t-1}. The univariate
   forecast (eq 8): rhat^j_i(W_t) = alphabar_{j,t} + betabar_{j,t} * z_j(W_t)_i.
3. The elastic net (eq 10): a POOLED regression of forward_return(W_m) on the J univariate
   forecasts rhat^j(W_m), over the trailing 52 weeks m in {t-52,...,t-1} (complete-case rows
   only), fit by scikit-learn ElasticNet (l1_ratio=0.5, selection='cyclic' for determinism,
   fit_intercept=True) over an explicit lambda (alpha) path; lambda chosen by corrected AIC
   computed in-repo (k = #nonzero + intercept + sigma^2; #nonzero-as-df is the standard
   elastic-net approximation). Select S_t = {j : theta_j > tol}.
4. CTREND (eq 11): CTREND_i(W_t) = the EQUAL-WEIGHT average of {rhat^j_i(W_t) : j in S_t and
   z_j(W_t)_i is non-null}. The elastic net SELECTS; the surviving forecasts are simple-
   averaged (the theta values are NOT weights). A coin with zero selected non-null signals
   gets NO forecast and is excluded from that week's quintile sort (never assigned 0).
5. Sort coins on CTREND into quintiles (highest = the long top quintile), equal-count bins,
   remainder-front, symbol-ascending tie-break (the PR1 convention); the factor is the
   top-minus-bottom quintile.

### The exact week-index timing (H3, the critical no-look-ahead point)

Each Fama-MacBeth observation is the within-row pair (z_j(W_m), forward_return(W_m)): the
signal observed at the START of a holding week and the return realized OVER that week (the
PR1 `forward_return` column built for exactly this). At the decision week W_t (forecasting
the return over (W_t, W_{t+1}]), the smoothing window and the elastic-net pool both end at
m = t-1 inclusive (the most recent week whose forward return is realized as of W_t).
Including m = t would use forward_return(W_t) (the future being predicted) to fit the
coefficient predicting it: a one-week look-ahead, the single most likely bug, foreclosed and
pinned by a test (appending a later week does not change an earlier forecast). The eq-10
pool's rhat^j(W_m) are the genuine as-of-W_m forecasts (each smoothed over its own m-52..m-1
window), so no future leaks into the pool.

## Deviations from the paper (each documented + a PR3 trial-registry entry)

- EQUAL-WEIGHT OLS, not the paper's value-weighted (by market cap) SSR: Binance has no
  market cap. Defensible on the liquid top-100 (the microcap noise the value-weighting
  suppresses is largely absent) and consistent with PR3's equal-weight portfolio (ADR 0005
  caveat 5). The artifact also reports the dollar-volume-weighted IC as a robustness column
  (dollar volume is the closest mcap analogue), so the result is shown not to hinge on the
  weighting.
- RAW weekly returns, not excess returns (eq 3 uses excess): the cross-sectional intercept
  (alpha_t / xi) absorbs the common weekly risk-free rate, so the slopes and the rank are
  unaffected to first order; the difference is ~5-10 bps/week common to all coins.
- Canonical indicator conventions where Appendix A is unstated (the C1 caveat).
- The PR1 universe (dollar-volume top-N) + Binance-only basis (the PR1 caveats).

## Point-in-time invariants (what the design review attacked, now pinned)

1. Daily indicators are strictly backward; null until the full window is available.
2. The signal at W uses only daily data <= W; it predicts forward_return(W) = the return
   over (W, next]; PR1's `forward_return` was built for this (no same-bar look-ahead).
3. The rolling fit at W_t uses only weeks m <= t-1 (the smoothing window AND the elastic-net
   pool); the forecast is for the period after W_t. No future leak (H3).
4. The cross-sectional rank + the regressions at W use only the eligible universe at W and
   only data observed at-or-before W.
5. Determinism: sorted polars, no RNG in the signal path (ElasticNet selection='cyclic'),
   a theta selection tolerance for cross-platform stability, the seeded-nothing fit.

## Missing-signal handling (H6, specified at every stage)

- A coin with a null z_j(W) (insufficient history for signal j) is excluded from that
  signal's week-W univariate regression; a week/signal with N<2 non-null observations yields
  no (alpha, beta) and contributes nothing to that signal's smoothing.
- The eq-10 pool uses COMPLETE-CASE rows (a (coin, week) row enters only if all J univariate
  forecasts are non-null), documented; the selection is thus driven by coins with full
  signal availability over the window (a mild, named bias).
- The eq-11 average for coin i runs over {j in S_t : rhat^j_i(W_t) non-null}; a coin with
  zero such signals gets no CTREND and is dropped from the sort that week (not assigned 0).

## Modules + reproducibility

- `ctrend/features.py`: the 28 daily indicators (polars rolling/ewm, strictly backward) +
  the weekly sampling -> a `(week_end, symbol, <28>)` frame.
- `ctrend/signal.py`: `rank_to_unit_interval`, `univariate_fm_forecasts` (eq 7-8),
  `combined_elastic_net` (eq 10 selection + eq 11 average, the sklearn solve + the in-repo
  AICc), `ctrend_forecasts` (the PIT rolling driver), `assign_quintiles`, `signal_ic`.
- `ctrend/signal_artifact.py`: the committed GROSS-quality summary (the PIT cross-sectional
  rank IC of CTREND vs forward_return, averaged over post-burn-in weeks; the per-quintile
  mean forward return; the per-year IC regime-stability diagnostic; the n scored weeks;
  a fingerprint = the panel content SHA + the signal knobs; the caveats) + a JSON artifact.
  (The dollar-volume-weighted-regression variant is a deferred PR3 trial-registry knob, not a
  PR2 column; the liquid top-100 universe mitigates the equal-weight-vs-value-weight concern.)
- `scripts/build_ctrend_signal.py`: builds the artifact from the committed panel (no
  network). The full per-(week,coin) forecast series is NOT committed (it is a pure function
  of the committed panel + the pinned code, the VRP/PR1 discipline); PR3 recomputes it
  deterministically from the panel. An offline reproduction test rebuilds the summary (IC +
  quintile spread within a documented tolerance, the libm/BLAS precedent; the sign +
  monotonicity asserted robustly).

## The trial registry (set up here; recorded + deflated in PR3)

PR2 enumerates and documents the v1 design family + the named robustness variants (the
feature set, the universe size, the quintile width = 5, the fit window = 52 weeks rolling,
the elastic-net mix = 0.5 + AICc, the rank transform, the equal-weight vs dollar-volume-
weight choice, the canonical-convention knobs). It does NOT call `TrialRegistry.record()`
(there are no realized net-of-cost return moments until PR3); the honest multiplicity count
(naive_effective_n = the number of independent families actually tried, a small integer) and
the DSR deflation are PR3, which records each variant's realized Sharpe so the cross-
sectional v_sr is well-defined.

## The elastic-net solver (H4): scikit-learn at runtime

The gate-critical eq-10 selection uses scikit-learn's ElasticNet (pinned 1.5.2), a battle-
tested deterministic coordinate-descent solver, rather than bespoke numerics: a buggy
selection would bias the PR3 gate, and the correctness of the selection outweighs
dependency minimalism. Determinism: `selection='cyclic'` (never 'random'), fixed tol +
max_iter (high enough to converge, so no ConvergenceWarning under filterwarnings=error), the
features standardized for the solve, theta>0 applied post-fit (eq 11), a selection tolerance
so a borderline coefficient does not flip the averaged set across platforms. The AICc lambda
selection is computed in-repo (auditable), not delegated. This is the fitted-signal layer's
dependency; the data layer + the vendored analytics remain stdlib-only / numpy-only.

## The gross result + the honest regime-stability disclosure

On the real committed panel (563 coins, 238 scored weeks 2020-08..2026-05): the gross
point-in-time cross-sectional rank IC is 0.032 (t 2.77) full-sample and 0.063 (t 4.73) on
the held-out 2022+ window, with monotonic full-sample quintiles and a +1.6%/week gross
top-minus-bottom spread. The signal predicts the cross-section at the gross level, a faithful
CTREND replication. Two honest caveats the post-implementation review surfaced, carried in the
artifact:

- The IC is REGIME-DEPENDENT, not a stable edge (the `ic_by_year` block): it was
  significantly NEGATIVE in 2021 (IC -0.07, t -3.3, the trend factor inverted), roughly flat
  in 2022 and 2024, and strongly positive only in 2025-2026 (IC +0.14/+0.15, t ~5.8). The
  positive OOS headline aggregates a favorable recent regime mix; the PR3 DSR deflation under
  CPCV must price this non-stationarity.
- The 2022+ quintile means are all NEGATIVE (the bear market) but positively sloped: the
  long-short top-minus-bottom is positive (+1.0%/week gross) while the retail-realistic
  LONG-ONLY top quintile LOSES money gross (-0.4%/week) before any costs. This is the central
  PR3 tension (ADR 0005 caveat 5): the academic long-short can look alive where the deployable
  long-only does not, and the kill gate reads the net-of-cost long-only as the retail headline.

These are GROSS, necessary-not-sufficient findings; whether anything survives realistic retail
costs + the multiplicity deflation is PR3.
