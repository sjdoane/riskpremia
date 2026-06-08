# STATUS

Single source of truth for where Project RiskPremia is and what is deferred.
Read this FIRST on any new session, then the ADRs it points to. Update after
every meaningful work block (rule 2).

Last updated: 2026-06-07 (session 16: Study 8 BUILT and measured = NON-VIABLE, a clean Cederburg replication (the project's 6th honest null). The volatility-managed market gate is implemented (`src/riskpremia/volmanaged/`), run, and shipped with figures on branch `feat/volmanaged-gate`. RESULT (1990-2026, 9032 daily obs): the managed-MINUS-unmanaged difference PSR(0) is 0.457 (bar 0.95); a real gross timing alpha +1.78%/yr at equal vol dies on the 2.0x retail leverage cap (-2.14%/yr, the dominant drag) + costs (-0.53%/yr) -> net -0.88%/yr. Expanding-window real-time c agrees (0.429). Difference near-orthogonal to Study 6 (corr 0.042). Senior-quant design review (2 Critical + 3 High folded into an ADR amendment BEFORE the build: the difference is the kill not the standalone managed PSR; c on the uncapped series + expanding-c; coherent cost; wider deflation) then adversarial post-impl review (SHIP, reproduced to the byte; 1 Medium = surface the gross alpha + name the cap as the dominant killer, resolved). PRIOR session 15: ADR 0010 pre-registration (PR #26 merged); CI-actions Node-24 bump (PR #27 merged).).

**Study 8 (volatility-managed market portfolio, ADR 0010): DONE, NON-VIABLE (a clean Cederburg replication, an honest null).** A deployable swing (the ADR 0008 registered backup), chosen by a four-lens fork + adversarial cross-check over industry/sector momentum, adjudicating the contested volatility-managed claim (Moreira-Muir 2017 vs Cederburg et al. 2020 / Barroso-Detzel 2020 negative-OOS-net-of-cost). **RESULT (1990-02..2026-03, 9032 daily obs, eff T 609): the managed-MINUS-unmanaged difference (the kill, NOT the standalone managed PSR) full-sample conditional PSR(0) = 0.457, far below 0.95; difference annualized Sharpe -0.07. GROSS DECOMPOSITION (the honest attribution): a real gross timing alpha +1.78%/yr at equal vol (Moreira-Muir IS present) dies on the 2.0x retail leverage cap -2.14%/yr (the DOMINANT drag, 80%) + net-of-cost frictions -0.53%/yr (20%) -> net -0.88%/yr. Expanding-window real-time c agrees (0.429). CPCV worst fold 0.127, recency 2008/2022 0.436/0.471, deflated 0.385..0.331 (8..128 trials), cap 1.0/1.5/2.0 -> 0.336/0.413/0.457 (de-risk-only is worst), financing 0.5/1.0/2.0% -> 0.463/0.457/0.444. Context: standalone managed Sharpe 0.553 vs unmanaged 0.484 (the equity premium, not the kill). Redundancy: difference-vs-Study-6 corr 0.042 (near-orthogonal, the objection answered), level corr 0.713, combo Sharpe 0.660 < Study 6 alone 0.692.** Even the market sleeve (Barroso-Detzel's lone survivor) is a null under this conservative cap+cost stack; the cap, not cost, is the dominant killer; the gross alpha is real but not retail-deployable. The committed artifact is `artifacts/volmanaged_gate.json`; it reuses the committed Study 6 panel `tests/data/xtrend_panel.csv` (the primary needs ZERO new data); figures `docs/figures/volmanaged_{wealth,scorecard}.png`. PROCESS (rule 1): a senior-quant design review returned 2 Critical + 3 High + 4 Medium, ALL folded into an ADR 0010 design-review AMENDMENT before any code (C1: the kill is the difference series not the standalone managed PSR, which is equity-premium-dominated; C2: c on the UNCAPPED series + cap as a separate friction + expanding-window c as the OOS check; H4: one coherent cost model; H5: literature-scale deflation; M6: factor secondary is a turnover-only stacked follow-up); then an adversarial post-impl review (SHIP, reproduced to the byte, c-identity to 1e-8; 1 Medium = surface the gross alpha + name the cap as the dominant killer, resolved). Detail in `docs/research/0011-...-design.md` (fork) + `docs/research/0012-...-result.md` (result). **SECONDARY DONE (the factor-asymmetry stacked follow-up): a UNIFORM NULL.** The same scaler applied to the long-short French factors (SMB/HML/RMW/CMA/WML, turnover-only cost, 1990-2026, 9149 obs): the managed market AND all 5 managed factors fail the (undeflated) net-of-cost PSR(0) gate, so the literature's market-survives/factors-die asymmetry does NOT hold here. Momentum (WML) is the apparent standout (gross +11.57%/yr, the Barroso-Santa-Clara managed-momentum effect, full-sample PSR 0.826) BUT this is a LOOK-AHEAD artifact: under the project's pre-registered expanding-window real-time c, WML's OOS PSR collapses to 0.489 and its net alpha to ~0 (a chunk of the apparent edge lives in the 1994-95 expanding burn-in), so the uniform null is robust out-of-sample. The committed factor panel is `tests/data/volmanaged_factor_panel.csv` (Kenneth French 5-factor + momentum daily, SHA-stamped), the artifact `artifacts/volmanaged_factor_asymmetry.json`, the figure `docs/figures/volmanaged_factor_asymmetry.png`. The secondary's adversarial post-impl review caught the missing expanding-c (a CRITICAL: the original WML standout claim was a look-ahead) and it was resolved by adding the expanding-c row for every factor. Registered backup: industry/sector momentum. NEXT: the industry/sector momentum deployable swing (the registered backup).

**Study 7 (crypto funding-dispersion measurement, ADR 0009): DONE, MEASURED (a non-deployable measured object).** A descriptive measurement (like a volatility surface), NOT a deployable verdict and NOT a "positive result" in the make-money sense: it documents that the cross-sectional dispersion of perpetual funding across coins is large but decaying and non-capturable at retail. **Result (1611 daily obs, 2022-01-02..2026-05-31, top-15 PIT liquid universe): equal-weight cross-sectional IQR 0.106 annualized (95% CI [0.092, 0.122], eff T 28); regime pre-ETF 0.123 / post-ETF 0.091, difference -0.032 (CI [-0.058, -0.008]); decay slope -0.013/yr (CI [-0.022, -0.004]); secondary raw std 0.390 / winsorized 0.200; secondary gross high-minus-low sort premium +0.550 annualized (CI [+0.354, +0.783]), non-capturable; coverage mean 13.6/15 funded = 91% (worst 73%).** Method (as built): the point-in-time eligible SPOT universe (CTREND `pit_eligible`, top-15, 2022+) joined to perp funding by USDT-symbol-string identity (the implementation amendment: identity join, no canonical fallback, so prefix-renamed/non-USDT perps fall into the coverage hole by design, a conservative understatement surfaced by the 91% diagnostic), per-event annualization via each event's `funding_interval_hours` (single-sourced to `CRYPTO_ANNUALIZATION_DAYS`, basis 8760), a fixed common daily grid by point-in-time carry-forward (so 4h vs 8h settlements do not manufacture dispersion), an equal-weight cross-sectional IQR headline (robust to small-cap tails) with a stationary-block-bootstrap CI on the FULL series, the pre/post-ETF difference, and a rolling decay slope; the gross quintile sort premium is a secondary banner-attached non-capturable object. Guardrails met: no tradeable-Sharpe headline, an explicit non-deployability banner on the abstract + the artifact caveats + both figures, the decay stated in the headline. The committed artifact is `artifacts/funding_dispersion.json`; the series fixture is `tests/data/funding_dispersion_series.csv` (SHA-stamped); figures are `docs/figures/funding_dispersion_{iqr,sort_premium}.png`. Design + result + reviews in `docs/research/0009-...-design.md` + `docs/research/0010-...-result.md`. Adversarial post-impl review per rule 1: SHIP, no Critical/High; two Medium resolved (the join documented in the ADR footer + research note; the decay knob renamed `decay_plot_window_days` to mark it a plot-only smoother). Next: a fresh fork (Study 8) under the post-CTREND deployable standard + the two ADR-0007 feasibility gates, or the registered volatility-managed deployable swing.

**Study 6 (cross-asset defensive trend, ADR 0008): DONE, QUALIFIED PASS (the first deployable result).** A frozen, no-fit, monthly, long-or-cash trend rule across US equity and long-term US Treasury (with the one-month bill as cash), each sleeve held long only when its total-return index is above its ten-month moving average, else in the bill; fixed one-over-N-of-universe equal weight; realistic fund costs (expense ratio on held notional plus per-side turnover); the net series marked to market daily and scored in excess of the bill. Data is openly-redistributable public-domain research data (Kenneth French daily factors for US equity total return and the one-month bill; the US Treasury par yield curve for the ten-year, the original source of FRED `DGS10`); scraped fund-price endpoints were rejected (browser-User-Agent spoofing + redistribution-restricted, the Study-5 standard). Gold was dropped (no clean public-domain price path; ADR 0008 pre-registered fallback). **Result (1990-2026, 8843 daily obs, 425 months): full-sample conditional PSR(0) 0.9996, monthly non-overlapping 0.9970, Deflated Sharpe 0.999/0.999/0.998 at 8/16/32 trials, max drawdown 11.2%, cost share 2.8%, CAGR 7.1%, net excess gain 360.6%. PASSES the primary gate, but REGIME-DEPENDENT: CPCV worst fold 0.7216, 2022-onward recency 0.4016. Per-sleeve attribution: equity standalone 0.9981 (the workhorse), long-Treasury standalone 0.8456 (fails its own gate, drives the recent-regime weakness).** Honest qualified pass on a classic rule, not a novel edge; the contribution is the reproducible deflated validation on clean data. The committed artifact is `artifacts/xtrend_gate.json`; the design + reviews are in `docs/research/0008-cross-asset-trend-gate-design.md`. Pre-build design review (3 blocking findings) and an adversarial post-implementation review (reproduced to the digit; disproved the false-pass hypothesis; two medium honesty findings resolved by adding the monthly PSR + the per-sleeve attribution to the artifact) per rule 1. Next: optional recruiter-facing figures; otherwise a fresh fork (the registered backup is the crypto funding-dispersion measurement note).

**Study 5 (CME Micro G6 FX carry feasibility, ADR 0007): DONE, NON-VIABLE BEFORE IMPLEMENTATION.** The G10 Micro FX backup from ADR 0006 was tested as a pre-code feasibility gate, not a backtest. The honest tradeable scope is CME Micro G6, not G10: micro contracts cover AUD, CAD, CHF, EUR, GBP, and JPY versus USD, while NZD, NOK, and SEK are missing at micro size. The data lane found free spot FX, policy-rate, VIX, and CFTC positioning paths, but the exact free historical CME settlement path is not robust enough for a long-history, scriptable futures backtest; CME routes historical settlement products through DataMine and local direct TCF CSV fetches returned HTTP 403. The stress lane also failed: one short `MSF` loses about USD 2,438 in the January 2015 CHF shock; two to three short CHF funding legs can plausibly hit 49% to 73% of a USD 10,000 account before slippage or liquidation friction. **Verdict:** kill CME Micro G6 FX carry as a deployable RiskPremia strategy before code. A spot-plus-policy-rate FX carry measurement note remains possible, but it is not a tradeable CME Micro verdict. Next step: fresh strategy fork with data and minimum-size stress gates applied before implementation.

**Study 4 (BTC/ETH slow trend, ADR 0006): DONE, NON-VIABLE.** PR6a `btc_eth_trend_gate` tested the frozen weekly BTC/ETH spot-only trend rule selected after the CTREND null: strict 200-day moving-average signal, Sunday close signal formation, Monday open fill, next Monday open exit, equal-risk active assets, 25% annualized volatility target, 100% notional cap, zero-yield cash, and realistic Kraken spot costs. The 2022+ out-of-sample result is positive but fails the statistical gate: 229 weekly observations, mean net +0.1975%/week, full-window conditional PSR(0) 0.6970, CPCV stress minimum conditional PSR(0) 0.1439, daily max drawdown 26.65%, cost share 11.47%, compounded net gain 43.91%, CAGR 8.64%. **Verdict:** non-viable because CPCV stress PSR 0.144 is below the 0.95 bar. The committed artifact is `artifacts/btc_eth_trend_gate.json`; method note is `docs/research/0005-btc-eth-trend-gate-design.md`. Registered backup: G10 Micro FX carry with a hard risk-off switch, subject first to a free-data and stress-loss gate.

**Study 3 (CTREND, ADR 0005): a faithful replication-and-stress of the one peer-reviewed crypto cost-survival claim (Fieberg et al., JFQA 2025) under the project's REALISTIC retail cost model + a 2022-2026 OOS extension + proper deflation. The FIRST FITTED signal in the project (the CPCV + trial-registry + DSR deflation are load-bearing). PR1 the point-in-time multi-coin universe data layer is DONE, PR2 the trend-feature signal + cross-sectional elastic-net aggregation is DONE, and PR3 the backtest + kill gate + verdict is DONE. Verdict: the retail LONG-ONLY top quintile is NON-VIABLE after costs (mean net -0.906%/week, full OOS DSR 0.0034, CPCV-min DSR 0.0031), and the academic LONG-SHORT comparison also fails the conservative CPCV-min DSR gate (mean net +0.197%/week, full OOS DSR 0.225, CPCV-min DSR 0.0035).**

**CTREND PR3 (the net-of-cost gate, DONE):** `ctrend/gate.py` + `scripts/run_ctrend_gate.py` rebuild the forecasts from the committed daily panel, form equal-weight weekly portfolios, charge spot-leg turnover through the realistic `VenueCostModel`, score 2022+ OOS with event-time-purged CPCV and a frozen trial count of 8, and write `artifacts/ctrend_gate.json`. The gate statistic is the minimum purged CPCV split DSR. Missing selected `forward_return` values are treated as a -100% delisting loss in the headline and counted (8 retail long-only, 16 academic long-short); the favourable drop-and-renormalize sensitivity is recorded but does not drive the verdict. Design review Critical/High issues were resolved before implementation; post-implementation review found one Medium forecast-hash reproducibility issue, fixed by hashing the score-driving gate input instead of raw elastic-net floats. Offline reproduction test rebuilds the gate from `tests/data/ctrend_daily_panel_usdt.csv.gz`.

**CTREND PR2 (the fitted signal, DONE):** the 28 daily technical signals (`ctrend/features.py`) + the cross-sectional combined elastic-net (`ctrend/signal.py`: rank-to-[-0.5,0.5] -> per-signal univariate Fama-MacBeth with 52-week smoothing -> scikit-learn elastic-net SELECTION (eq 10, mix 0.5, in-repo AICc) -> CTREND = equal-weight average of the positive-weight survivors (eq 11) -> quintiles), fit strictly point-in-time (the smoothing window + the elastic-net pool both end at week t-1; no look-ahead, certified by the post-impl review's surgical forward-return-leak test). The committed gross-quality artifact (`artifacts/ctrend_signal.json`) + `scripts/build_ctrend_signal.py` (no network; the forecast series is recomputed, not committed). The data layer was extended with daily high/low (4 signals need them); `scikit-learn==1.5.2` pinned. **The GROSS result: a positive point-in-time rank IC (0.032 full / 0.063 OOS 2022+, t 2.8/4.7), monotonic full-sample quintiles, +1.6%/week gross top-minus-bottom; BUT regime-dependent (significantly negative in 2021) and the retail LONG-ONLY top quintile loses gross in the 2022+ bear market while the long-short is positive (the central PR3 tension). Necessary-not-sufficient; PR3 applies costs + the DSR deflation + CPCV.** Deviations (PR3 trial knobs): equal-weight (no mcap), raw returns, canonical indicator conventions (the paper's Appendix A was unobtainable).

**CTREND PR1 (the universe data layer, DONE):** the paper was verified first (28 DAILY technical signals, e.g. a 14-day RSI + 3-to-200-day SMAs, with a WEEKLY rebalance and a 52-week rolling CS-C-ENet fit), so the layer stores DAILY spot data and derives the weekly grid. `data/sources/binance_vision.py` gained `list_spot_symbols` (delisting-complete S3 enumeration), `fetch_spot_klines` / `available_spot_months` (daily klines, delisting-robust), and a quote-volume parse. `ctrend/universe.py` is the load-bearing PIT spine (the stable/leveraged/non-ASCII exclusion filter, `build_daily_panel`, `build_weekly_panel` with a gap-safe `weekly_return` + an explicit `forward_return`, and `pit_eligible` = top-N by trailing dollar volume, point-in-time). `ctrend/fixtures.py` + `ctrend/artifact.py` + `scripts/build_ctrend_universe.py` produce the committed gzipped daily panel (`tests/data/ctrend_daily_panel_usdt.csv.gz`, 9.6 MB, two-hash reproducibility) + `artifacts/ctrend_universe.json`. The real universe: 664 USDT symbols enumerated, 67 excluded, 597 tradeable, 563 committed (ever in the top-120), 387 weeks (2019-01-06..2026-05-31), the liquid universe ramping 20 -> 100 eligible coins. The paper's market-cap universe + value-weighting are unavailable from Binance, so the dollar-volume top-N screen + (PR3) equal-weighting are documented deviations.

## One-line state

A reproducible, intellectually-honest MEASUREMENT study of crypto risk premia. Study 1
(funding carry, ADR 0003) was killed honestly: net-of-cost Deflated
Sharpe ~0 on every US-tradeable venue and horizon. Study 2 (VRP, ADR 0004) measured a
real positive BTC variance premium, but the cost-gated monthly short-straddle
implementation was non-viable after costs and crash-tail accounting. Study 3 (CTREND,
ADR 0005) found real gross cross-sectional signal quality, but the retail long-only
top quintile was non-viable after costs and the academic long-short comparison also
failed the conservative CPCV-min DSR gate. Study 4 (BTC/ETH slow trend, ADR 0006)
was positive and drawdown-reducing but non-viable because its CPCV stress minimum
conditional PSR(0) was 0.1439, below the 0.95 bar. Study 5 (CME Micro G6 FX carry,
ADR 0007) was killed at feasibility because the exact free futures-settlement data path
and USD 10,000 integer-contract stress gate failed. Study 6 (cross-asset defensive trend,
ADR 0008) is the project's FIRST QUALIFIED PASS: a frozen, no-fit, long-only stock/bond
trend rule into T-bills on clean public-domain data clears the deflated full-sample gate
(conditional PSR(0) 0.9996, monthly 0.9970, Deflated Sharpe 0.998 at 32 trials, 11.2% max
drawdown, 2.8% cost share), but is regime-dependent (CPCV worst fold 0.72, 2022-onward 0.40;
equity-trend-driven, the bond sleeve is the weak part); its figures shipped in session 12.
Study 7 (crypto funding-dispersion measurement, ADR 0009) is DONE and measured: a descriptive,
explicitly non-deployable measurement of the cross-sectional funding-dispersion premium
(distinct from Study 1's level carry) on the clean Binance funding archive. It is large but
decaying (equal-weight cross-sectional IQR 0.106 annualized, post-ETF 0.091 vs pre-ETF 0.123,
slope -0.013/yr) and non-capturable at retail (gross sort premium +0.550 annualized); shipped
with figures. Study 8 (volatility-managed market portfolio, ADR 0010) is DONE and NON-VIABLE: a clean Cederburg
replication (the project's sixth honest null). The managed-minus-unmanaged difference clears
nothing (PSR(0) 0.457); a real +1.78%/yr gross timing alpha at equal vol dies on the 2.0x retail
leverage cap (the dominant drag) and net-of-cost frictions, so volatility timing adds no deployable
value over buy-and-hold. It is near-orthogonal to Study 6 (difference correlation 0.042).
**Next step: the Study 8 factor-asymmetry secondary (stacked follow-up), or the registered
industry/sector momentum backup.**
Repo: https://github.com/sjdoane/riskpremia.

## Dev commands (Windows PowerShell; the venv is run DIRECTLY)

```
$env:PYTHONIOENCODING="utf-8"
$py = "C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe"
& $py -m pytest -q -m "not network" # 278 pass / 18 deselected; never touch the off-limits pit-backtest venvs
& $py -m pytest -q -m network       # 18 pass: Binance Vision + OKX + Deribit DVOL + Tardis + Kenneth French + US Treasury
& $py -m mypy                       # strict, src + scripts (81 source files)
& $py -m ruff check src tests scripts
& $py -m scripts.build_ctrend_universe # one-time: fetch the live USDT universe -> committed CTREND panel + artifact + stamp
& $py -m scripts.build_ctrend_signal   # one-time (no network): committed panel -> committed CTREND signal artifact
& $py -m scripts.run_ctrend_gate     # no-network: committed panel -> committed CTREND net-of-cost gate artifact
& $py -m scripts.build_btc_eth_trend_inputs # one-time: fetch BTC/ETH daily OHLC -> committed fixture + stamp
& $py -m scripts.run_btc_eth_trend_gate # no-network: committed BTC/ETH fixture -> committed Study 4 gate artifact
& $py -m scripts.build_xtrend_inputs # one-time: fetch Kenneth French + US Treasury -> committed Study 6 panel + stamp
& $py -m scripts.run_xtrend_gate     # no-network: committed panel -> committed Study 6 cross-asset trend gate artifact
& $py -m scripts.regenerate_xtrend_figures # render docs/figures/xtrend_*.png from the committed Study 6 artifact
& $py -m scripts.build_dispersion_inputs # one-time: fetch funding across the PIT universe -> committed Study 7 series + stamp
& $py -m scripts.run_dispersion_measurement # no-network: committed series -> committed Study 7 dispersion artifact
& $py -m scripts.regenerate_dispersion_figures # render docs/figures/funding_dispersion_*.png from the committed Study 7 series + artifact
& $py -m scripts.run_volmanaged_gate  # no-network: committed Study 6 panel -> committed Study 8 volatility-managed gate artifact
& $py -m scripts.regenerate_volmanaged_figures # render docs/figures/volmanaged_*.png from the committed panel + Study 8 artifact
& $py -m scripts.build_volmanaged_factor_inputs # one-time: fetch French 5-factor + momentum daily -> committed Study 8 factor panel + stamp
& $py -m scripts.run_volmanaged_factor_asymmetry # no-network: committed factor panel -> committed Study 8 factor-asymmetry artifact
& $py -m scripts.build_vrp_artifact # one-time: fetch live data -> committed VRP artifact + fixtures + manifest stamp
& $py -m scripts.regenerate_figures # render docs/figures/*.png from the committed artifact (no network)
```
Setup if the venv is gone: `uv venv --python 3.12 C:\Users\SamJD\.venvs\riskpremia`
then `uv pip install --python $py -e ".[dev,figures]"` (the `figures` extra adds
matplotlib, render-only; CI installs only `.[dev]` and skips the figure render test).

## What is built (data layer, complete)

`src/riskpremia/`:
- `analytics/` + `validation/`: VENDORED (copied + attributed) from pit-backtest
  `edad904`, stdlib-faithful: `sharpe.py` (PSR/DSR/MinTRL), `bootstrap.py`
  (stationary block bootstrap + Politis-White), `cv.py` (purged CPCV),
  `trial_registry.py` (the DSR trial count). REUSE these verbatim; do not rewrite.
- `data/`: `records.py` (attrs carriers + cross-venue canonicalization),
  `boundary.py` (the ONLY pydantic module, AST-enforced), `clock.py` (the
  funding-event clock: ms->UTC, realized-aware dedup, the backward as-of price
  join, `make_label_horizons`, `marks_frame`/`spot_frame`), `manifest.py` (SHA256
  reproducibility), `errors.py`, `cross_venue.py` (the Binance-vs-OKX funding
  delta), `sources/binance_vision.py` (long-history backbone, checksummed),
  `sources/okx.py` (live kill-gate venue).
- `execution/`: PR4a + PR4b DONE. `errors.py` (loud-failure hierarchy incl.
  `ScoringError`), `cost.py` (the `VenueCostModel` + cited base-tier fee schedules:
  Kraken/Hyperliquid tradeable, Binance/OKX reference; round-trip both legs both
  sides + the 2N financing on the real wall-clock hold; provisional conservative
  spreads), `carry.py` (`funding_window_indices`/`valid_entry_range` = the single
  window source of truth, `simulate_trade`, `simulate_batch`, `per_interval_pnl`
  conservation harness, `price_pnl_contamination`), `scoring.py` (`return_moments`,
  `psr_zero` with block-deflated effective T, `per_interval_series` lumpy/amortised,
  `make_purged_cpcv` embargo>=H), `exhibit.py` (`early_gate`, `headline_score`,
  `funding_sign_regime`, `after_tax_sidebar`, `gate_surface`/`is_killed`).
- `strategy/null.py`: the entry-selection nulls (always-on, non-overlapping, random
  subset). `scripts/run_null_gate.py`: the kill-gate entry point (fetch + surface +
  verdict). `data/sources/binance_vision.py`: + the ms/us kline-timestamp normalizer.
- `trend/` + `scripts/{build_btc_eth_trend_inputs,run_btc_eth_trend_gate}.py` (Study 4,
  PR6a): the BTC/ETH slow trend gate from committed daily OHLC fixtures. It forms the
  signal after Sunday close, fills at Monday open, exits at the next Monday open, charges
  Kraken spot turnover costs before the holding return, scores conditional PSR(0) with a
  CPCV worst-regime stress, and writes `artifacts/btc_eth_trend_gate.json`. Verdict:
  non-viable because CPCV stress PSR 0.144 is below the 0.95 bar.
- `data/sources/tardis_options.py` (PR5c): the Layer-ii Tardis Deribit option-chain
  loader (`OptionQuoteRecord`, `PydanticTardisOptionRow`, `us_to_utc`, the `tardis`
  venue), streaming the free first-of-month ~1.8GB gzip + extracting a backward as-of
  snapshot, never caching the gigabyte.
- `execution/cost.py` `DeribitOptionCostModel` + `execution/options.py` (PR5d): the
  delta-hedged short-option transaction cost model (cited Deribit fees + the option
  bid-ask + the perp delta-hedge leg), fraction-of-underlying-S, `tradeable=False` (US
  retail access via Coinbase FM is institutional-now / retail-coming-soon).
- `execution/options.py` `simulate_option_trade` + `OptionTradePnL` (PR5e): the per-trade
  short-variance P&L in COIN per contract, INVERSE settlement (`intrinsic_usd / S_T`) +
  inverse-perp static hedge (`delta * (1 - S0/S_T)`), the conservation guard + the
  `path_rehedge_unmodeled` marker + `rehedge_cost_sensitivity`.
- `vrp/gate.py` + `scripts/{build_vrp_entries,run_vrp_gate}.py` (PR5f): the Layer-ii
  short-straddle backtest + the regime tail-loss table + the cited peso shock + the
  NON-VIABLE verdict; the committed entries fixture (`tests/data/vrp_straddle_entries.csv`,
  SHA-stamped) + the gate artifact (`artifacts/vrp_short_variance_gate.json`).
- `dispersion/` + `scripts/{build_dispersion_inputs,run_dispersion_measurement,regenerate_dispersion_figures}.py`
  (Study 7): the crypto funding-dispersion MEASUREMENT (a non-deployable measured object).
  `measure.py` (per-event interval annualization single-sourced to `CRYPTO_ANNUALIZATION_DAYS`,
  the point-in-time common-grid carry-forward, the equal-weight cross-sectional IQR + std +
  winsorized std + the gross quintile sort premium), `artifact.py` (the bootstrap-CI artifact:
  IQR level + pre/post-ETF regime split + decay slope + the secondary sort premium + coverage +
  caveats + fingerprint), `fixtures.py` (the committed daily series + provenance), `figures.py`
  (render-only, the `figures` extra). The committed series is `tests/data/funding_dispersion_series.csv`
  (SHA-stamped), the artifact `artifacts/funding_dispersion.json`, the figures
  `docs/figures/funding_dispersion_{iqr,sort_premium}.png`; an offline test reproduces the
  artifact from the fixture. Result: IQR 0.106 annualized, decaying, non-capturable (full numbers
  above + in `docs/research/0010-funding-dispersion-measurement-result.md`).
- `volmanaged/` + `scripts/{run_volmanaged_gate,regenerate_volmanaged_figures}.py` (Study 8): the
  volatility-managed market gate (a non-viable null). `measure.py` (the Moreira-Muir
  inverse-variance signal, the c-normalization on the UNCAPPED series, the daily managed/unmanaged/
  difference series with the coherent expense + financing + turnover costs), `gate.py` (the kill =
  the managed-minus-unmanaged difference PSR(0) + the gross decomposition + CPCV/recency/deflation
  stress + the leverage-cap and financing sensitivities + the expanding-window-c OOS check + the
  redundancy-vs-Study-6 numbers + the artifact), `figures.py` (render-only, the `figures` extra),
  `errors.py`. It REUSES the committed Study 6 panel `tests/data/xtrend_panel.csv` (the primary
  needs no new data) and the vendored PSR/CPCV/bootstrap stack. The committed artifact is
  `artifacts/volmanaged_gate.json`, figures `docs/figures/volmanaged_{wealth,scorecard}.png`; an
  offline test reproduces the artifact from the committed panel to the digit. Verdict: NON-VIABLE
  (a clean Cederburg replication; full numbers above + in `docs/research/0012-...-result.md`).
  `factors.py` + `scripts/{build_volmanaged_factor_inputs,run_volmanaged_factor_asymmetry}.py` are
  the factor-asymmetry SECONDARY: the same scaler on the long-short French factors (turnover-only),
  the committed factor panel `tests/data/volmanaged_factor_panel.csv` (5-factor + momentum daily,
  SHA-stamped) + `artifacts/volmanaged_factor_asymmetry.json` + the figure; a UNIFORM NULL (market
  and all 5 factors fail; the WML standout is a look-ahead that dies under the real-time c). The
  data layer gained `KenFrenchFactorsSource` (5-factor + momentum daily loaders, additive).
- 298 offline pass + 18 live `network` tests (the figure render tests run
  locally, skipif in CI); mypy strict (src + scripts, 91 source files) / ruff /
  em-dash clean; CI green
  (`.github/workflows/ci.yml`, installs `.[dev]`, runs ruff + mypy + `pytest -m "not
  network"`, so CI runs the offline set).

The data layer yields, for a perp, an aligned **funding + perp-mark + spot +
basis** series on the funding-event clock that feeds the vendored
event-time-purged CPCV directly. Every input is checksum-reproducible (Binance
Vision) or live-and-keyless (OKX). The whole layer fetches with the STDLIB ONLY.

## Study 1 (the funding carry, ADR 0003): KILLED on `main`; Study 2 (the VRP, ADR 0004): the active build

The cost model + the random-entry null are built and run (rule 6 honored: no
selection signal exists yet). The full locked methodology, the design-review
findings (C1-C3, H1-H3), and the post-implementation corrections are in ADR 0003
(amendments A1-A3 for PR4a, B1-B7 + the honest-T correction for PR4b).

**The result (regenerate with `& $py scripts/run_null_gate.py`, or `--start/--end`
to vary the window):** on the held-out post-ETF BTCUSDT frame (2024-01-11 to
2026-05-31, 2616 events), net-of-cost Deflated Sharpe (PSR(0), block-deflated T) is
**0.0000 on every US-tradeable venue at every horizon at the conservative 2N
capital charge**, and every tradeable cell still fails the 0.95 bar at the
favourable 1N charge. The round-trip cost (about 69 bps Kraken) dwarfs the median
funding at every horizon, and the 2N financing (about 8%/yr) roughly equals the
funding (about 5.7%/yr). KILL: the naive carry is non-viable, the honest null the
study was always allowed to ship.

**The active study is the VRP (ADR 0004); the carry above is the killed Study 1.**
Layer i (PR5a, branch `feat/vrp-dvol-and-measurement`) is built and the first VRP is
measured + positive (see the one-line state). VRP modules: `data/sources/deribit_dvol.py`,
`vrp/realized.py` (the matched-horizon variance-swap RV), `vrp/measurement.py`
(`build_vrp_frame` + `vrp_headline`, the non-overlapping strided headline). PR5b
(DONE): the committed Layer-i ARTIFACT (`artifacts/vrp_measurement.json`, headline +
regime decomposition + alignment diagnostic + fingerprint + caveats + the daily series)
built by `scripts/build_vrp_artifact.py`, matplotlib figures (`docs/figures/`) rendered
from it by `scripts/regenerate_figures.py` (the `figures` extra, lazy, a skipif render
test), and the M1 gate closed: both daily-close fixtures are committed under
`tests/data/` and SHA256-stamped into `manifest.toml` as `reproducibility_fixture`
entries, with an offline test that the fixtures reproduce the committed headline.
VRP modules: `vrp/fixtures.py`, `vrp/artifact.py`, `vrp/figures.py`. PR5c (DONE): the
Layer-ii Tardis option-chain loader (`data/sources/tardis_options.py`). PR5d (DONE): the
delta-hedged-option cost model (`execution/cost.py` `DeribitOptionCostModel` +
`execution/options.py`), cost-model-first, the first real option cost ~16 bps of the
underlying for a near-ATM call vs ~110 bps premium. PR5e (DONE): the per-trade
short-variance P&L (`simulate_option_trade` + `OptionTradePnL`), in COIN per contract with
the INVERSE coin settlement (`intrinsic_usd / S_T`) + the inverse-perp static hedge
(`delta * (1 - S0/S_T)`); the design review REJECTED the first (linear) design for
understating the put crash tail ~10x, and the inverse fix makes the peso tail honest
(a 90% crash on a short put settles ~9x the notional). PR5f (DONE): the Layer-ii gate +
the VERDICT (`vrp/gate.py` + `scripts/{build_vrp_entries,run_vrp_gate}.py`); 42 monthly
short straddles gathered (0 dropped), the committed entries fixture + the gate artifact.
**VERDICT: NON-VIABLE** (DSR 0.30 below the bar, slightly negative mean, worst in-sample
month 2.7x the margin, cited peso shocks 3.3x/6.1x). Layer ii is complete; both layers
are done. Next steps:
1. PR5g (the recruiter-facing polish, deferred): Layer-ii figures (the monthly short-
   straddle net + the loss-distribution / crash tail) rendered from the committed gate
   artifact (the `figures` extra, lazy, a skipif render test, mirroring the Layer-i
   figures), plus folding BOTH layers into the README front door (a results-at-a-glance
   table: the positive Layer-i measurement + the Layer-ii non-viable null; the README
   banner still says "Layer ii is next" and needs the reframe).
2. The Study-1 (carry) write-up (README results + figures) is the OPTIONAL deferred
   deliverable; the pivot took priority per Sam's directive.

## Pre-registered kill criterion (frozen UPFRONT; ADR 0001)

The study ships regardless (an honest null is an acceptable, intended deliverable);
the gate is about REAL-MONEY deployment.
- Early gate: if median funding collected over the hold does not exceed the
  amortised round-trip cost for a passive always-on carry on the US-tradeable
  venue (held-out post-spot-ETF regime), the naive carry is dead after costs.
- Primary gate: net-of-all-cost Deflated Sharpe < 0.95 out-of-sample, under
  event-time-purged CPCV with embargo, on the frozen trial count, on the held-out
  post-ETF period -> declare non-viable and write the honest null. Do not
  soft-pedal a hit.

## Gotchas / load-bearing facts

- **Windows + polars:** needs the `tzdata` package (pinned `tzdata==2026.2`) to
  resolve "UTC" when materializing tz-aware datetimes, else `to_list()` panics.
- **OKX:** public funding history is RECENT-ONLY (~93 days), so it is the live
  kill-gate venue, NOT a long-history source; the Binance-vs-OKX delta is measured
  on the recent overlap and applied as an adjustment. OKX 403s the default
  `Python-urllib` User-Agent (send a descriptive UA).
- **Cross-venue alignment:** Binance Vision `calc_time` has a few ms of jitter
  around the settlement instant while OKX is clean, so cross-venue joins MUST snap
  `dt` to the funding grid (`dt.dt.round("8h")`); within-venue series keep the raw
  jittered dt (fine for the 8h CPCV clock).
- **ruff auto-strips unused imports:** it silently dropped MarkPriceRecord /
  SpotPriceRecord from clock.py in PR1; re-add when a later change uses them.
- **The data layer fetches with the STDLIB ONLY** (urllib + json + zipfile); httpx
  was removed. Keep it that way (a reproducibility property).

## Hard rules (non-negotiable; full text in README + the session_rules / feedback memories)

1. **Process:** every meaningful component goes Plan -> a senior-quant design
   review -> implement -> a post-implementation review; address Critical + High
   findings before marking done; convene a four-lens review + an adversarial
   cross-check at a genuine fork. Record every finding + its resolution in the
   CHANGELOG.
2. Keep STATUS / CHANGELOG / memory / ADRs current after every block.
3. **No em-dashes** (U+2014) or double-hyphen sequences anywhere; sweep before
   every commit.
4. **Kill-early** on the frozen criterion above; an honest null is a success.
5. **Windows-first** PowerShell, absolute paths, no `&&` chaining, `$null`,
   `$env:VAR`. The clean dedicated venv only; never the off-limits pit-backtest
   venvs.
6. **Verify against REAL data:** fixtures/mocks are necessary but not sufficient;
   the backtest must be net of realistic modeled costs (cost model FIRST, then a
   random-entry null). The live `network` tests are the real-data proof.
7. No secrets in chat (`.env` / env vars; flag any paste as exposed).
8. Determinism + reproducibility: exact-patch pins, seeded `random.Random` only,
   sorted polars, committed regenerable artifacts. Reuse the vendored stack.

## Deferred / open

- Cost-model spread: replace the conservative assumption with the MEASURED median
  from Binance Vision `bookTicker` (free, reproducible) as the follow-up after the
  first gate.
- Capacity curve (the order-book-walk impact + the size where net edge crosses
  zero, the declared honest headline); the carry signal + the risk-OFF regime
  circuit breaker (carry, deferred).
- Data-layer extras (not on the kill-gate path): Hyperliquid source, multi-coin
  universe, `scripts/fetch_funding.py` + the committed derived artifact,
  clamp-incidence diagnostic.
- US-tradeable venue: model a few in the cost model unless Sam names one.

## Reading map

ADR 0001 (lead-track decision + the kill criterion), ADR 0002 (the data layer +
funding clock, incl the PR3 OKX/delta amendment), ADR 0003 (the cost model + null),
ADR 0004 (VRP pivot + completed non-viable tradeable gate), ADR 0005 (CTREND pivot +
completed non-viable gate), ADR 0006 (completed BTC/ETH slow-trend pivot +
non-viable PR6a gate), ADR 0007 (completed CME Micro G6 FX carry feasibility kill), ADR 0008
(cross-asset defensive trend, the qualified pass), ADR 0009 (crypto funding-dispersion
measurement pivot, built and measured; the implementation-amendment footer records the
USDT-identity join + the top-15 universe), ADR 0010 (volatility-managed market-portfolio pivot,
built and measured NON-VIABLE; the design-review amendment makes the managed-minus-unmanaged
difference the kill and moves c to the uncapped series with an expanding-window OOS check).
`docs/research/0001-data-layer-design.md` (the reviewed data-layer design),
`docs/research/0007-cross-asset-trend-feasibility.md` (the Study 6 candidate survey + data probe),
`docs/research/0008-cross-asset-trend-gate-design.md` (the Study 6 gate design, result, and reviews),
`docs/research/0009-funding-dispersion-measurement-design.md` (the Study 7 fork, data probe, method, and review),
`docs/research/0010-funding-dispersion-measurement-result.md` (the Study 7 measured result + post-impl review),
`docs/research/0011-volatility-managed-equity-design.md` (the Study 8 fork, four-lens + adversarial review, literature check, and method),
`docs/research/0012-volatility-managed-equity-result.md` (the Study 8 measured non-viable result + the gross decomposition + post-impl review).
CHANGELOG.md (every review finding + resolution). The `project_riskpremia` memory
note (cross-session summary). README.md (the reviewer-facing front door).
