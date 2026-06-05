# STATUS

Single source of truth for where Project RiskPremia is and what is deferred.
Read this FIRST on any new session, then the ADRs it points to. Update after
every meaningful work block (rule 2).

Last updated: 2026-06-05 (session 7: CTREND PR3 DONE, the net-of-cost backtest + kill gate + verdict, on `feat/ctrend-gate`; design plan + senior-quant design review + post-implementation review per rule 1; retail long-only is a decisive honest null, and the academic long-short comparison also fails the conservative CPCV-min DSR gate).

**Study 3 (CTREND, ADR 0005): a faithful replication-and-stress of the one peer-reviewed crypto cost-survival claim (Fieberg et al., JFQA 2025) under the project's REALISTIC retail cost model + a 2022-2026 OOS extension + proper deflation. The FIRST FITTED signal in the project (the CPCV + trial-registry + DSR deflation are load-bearing). PR1 the point-in-time multi-coin universe data layer is DONE, PR2 the trend-feature signal + cross-sectional elastic-net aggregation is DONE, and PR3 the backtest + kill gate + verdict is DONE. Verdict: the retail LONG-ONLY top quintile is NON-VIABLE after costs (mean net -0.906%/week, full OOS DSR 0.0034, CPCV-min DSR 0.0031), and the academic LONG-SHORT comparison also fails the conservative CPCV-min DSR gate (mean net +0.197%/week, full OOS DSR 0.225, CPCV-min DSR 0.0035).**

**CTREND PR3 (the net-of-cost gate, DONE):** `ctrend/gate.py` + `scripts/run_ctrend_gate.py` rebuild the forecasts from the committed daily panel, form equal-weight weekly portfolios, charge spot-leg turnover through the realistic `VenueCostModel`, score 2022+ OOS with event-time-purged CPCV and a frozen trial count of 8, and write `artifacts/ctrend_gate.json`. The gate statistic is the minimum purged CPCV split DSR. Missing selected `forward_return` values are treated as a -100% delisting loss in the headline and counted (8 retail long-only, 16 academic long-short); the favourable drop-and-renormalize sensitivity is recorded but does not drive the verdict. Design review Critical/High issues were resolved before implementation; post-implementation review found one Medium forecast-hash reproducibility issue, fixed by hashing the score-driving gate input instead of raw elastic-net floats. Offline reproduction test rebuilds the gate from `tests/data/ctrend_daily_panel_usdt.csv.gz`.

**CTREND PR2 (the fitted signal, DONE):** the 28 daily technical signals (`ctrend/features.py`) + the cross-sectional combined elastic-net (`ctrend/signal.py`: rank-to-[-0.5,0.5] -> per-signal univariate Fama-MacBeth with 52-week smoothing -> scikit-learn elastic-net SELECTION (eq 10, mix 0.5, in-repo AICc) -> CTREND = equal-weight average of the positive-weight survivors (eq 11) -> quintiles), fit strictly point-in-time (the smoothing window + the elastic-net pool both end at week t-1; no look-ahead, certified by the post-impl review's surgical forward-return-leak test). The committed gross-quality artifact (`artifacts/ctrend_signal.json`) + `scripts/build_ctrend_signal.py` (no network; the forecast series is recomputed, not committed). The data layer was extended with daily high/low (4 signals need them); `scikit-learn==1.5.2` pinned. **The GROSS result: a positive point-in-time rank IC (0.032 full / 0.063 OOS 2022+, t 2.8/4.7), monotonic full-sample quintiles, +1.6%/week gross top-minus-bottom; BUT regime-dependent (significantly negative in 2021) and the retail LONG-ONLY top quintile loses gross in the 2022+ bear market while the long-short is positive (the central PR3 tension). Necessary-not-sufficient; PR3 applies costs + the DSR deflation + CPCV.** Deviations (PR3 trial knobs): equal-weight (no mcap), raw returns, canonical indicator conventions (the paper's Appendix A was unobtainable).

**CTREND PR1 (the universe data layer, DONE):** the paper was verified first (28 DAILY technical signals, e.g. a 14-day RSI + 3-to-200-day SMAs, with a WEEKLY rebalance and a 52-week rolling CS-C-ENet fit), so the layer stores DAILY spot data and derives the weekly grid. `data/sources/binance_vision.py` gained `list_spot_symbols` (delisting-complete S3 enumeration), `fetch_spot_klines` / `available_spot_months` (daily klines, delisting-robust), and a quote-volume parse. `ctrend/universe.py` is the load-bearing PIT spine (the stable/leveraged/non-ASCII exclusion filter, `build_daily_panel`, `build_weekly_panel` with a gap-safe `weekly_return` + an explicit `forward_return`, and `pit_eligible` = top-N by trailing dollar volume, point-in-time). `ctrend/fixtures.py` + `ctrend/artifact.py` + `scripts/build_ctrend_universe.py` produce the committed gzipped daily panel (`tests/data/ctrend_daily_panel_usdt.csv.gz`, 9.6 MB, two-hash reproducibility) + `artifacts/ctrend_universe.json`. The real universe: 664 USDT symbols enumerated, 67 excluded, 597 tradeable, 563 committed (ever in the top-120), 387 weeks (2019-01-06..2026-05-31), the liquid universe ramping 20 -> 100 eligible coins. The paper's market-cap universe + value-weighting are unavailable from Binance, so the dollar-volume top-N screen + (PR3) equal-weighting are documented deviations.

## One-line state

A reproducible, intellectually-honest MEASUREMENT study of crypto risk premia. Study
1 (the funding carry) was KILLED honestly (the kill gate, on `main`: net-of-cost
Deflated Sharpe ~0 on every US-tradeable venue/horizon, an honest null). Per the
pivot-on-failure rule, **the active study is now the crypto VARIANCE RISK PREMIUM
(VRP), ADR 0004**, in two layers: (i) a reproducible index-level MEASUREMENT (Deribit
DVOL implied variance minus realized variance from the Binance Vision klines), and
(ii) a cost-gated short-variance tradeable test, pre-registered as a likely
cost/peso-bounded null. **BOTH LAYERS ARE NOW BUILT.** Layer i (the MEASUREMENT,
PR5a-PR5b): the first measured VRP (BTC, 2022-01..2025-06, 30-day) is mean variance
premium 0.087, 95% bootstrap CI [0.033, 0.119] CLEARING zero (overlap-honest), 70% of
days positive, pre-ETF 0.101 -> post-ETF 0.059 (a real, positive, significant premium;
committed regenerable artifact + figures). **Layer ii (the tradeable test, PR5c-PR5f):
VERDICT NON-VIABLE, the pre-registered cost/peso-bounded honest null.** A systematic
monthly short straddle (delta-hedged, held to expiry) over 2022-2025 nets a Deflated
Sharpe of 0.30 (below the 0.95 bar) with a slightly NEGATIVE mean, and a catastrophic
inverse-settlement crash tail (the worst in-sample month loses 2.7x the posted margin; a
cited -50% one-day crash loses 6.1x). The honest conclusion: the VRP is real and
positive (Layer i), but the static held-to-expiry straddle is a path-blind directional
bet that does NOT harvest it after costs, and the un-modeled path rehedge + the peso tail
make it non-viable for retail. The measurement floor is the study's positive headline.
Repo: https://github.com/sjdoane/riskpremia. PR5f on `feat/vrp-short-variance-gate`.

## Dev commands (Windows PowerShell; the venv is run DIRECTLY)

```
$env:PYTHONIOENCODING="utf-8"
$py = "C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe"
& $py -m pytest -q -m "not network" # 218 pass (offline); never touch the off-limits pit-backtest venvs
& $py -m pytest -q -m network       # 16 live: Binance Vision + OKX + Deribit DVOL + Tardis (the real-data proof)
& $py -m mypy                       # strict, src + scripts (55 source files)
& $py -m ruff check src tests scripts
& $py -m scripts.build_ctrend_universe # one-time: fetch the live USDT universe -> committed CTREND panel + artifact + stamp
& $py -m scripts.build_ctrend_signal   # one-time (no network): committed panel -> committed CTREND signal artifact
& $py -m scripts.run_ctrend_gate     # no-network: committed panel -> committed CTREND net-of-cost gate artifact
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
- 174 offline + 12 live `network` tests (the figure render test runs locally, skipif
  in CI); mypy --strict (src + scripts) / ruff / em-dash clean; CI green
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
funding clock, incl the PR3 OKX/delta amendment), ADR 0003 (the cost model + null,
the locked methodology). `docs/research/0001-data-layer-design.md` (the reviewed
data-layer design). CHANGELOG.md (every review finding + resolution). The
`project_riskpremia` memory note (cross-session summary). README.md (the
reviewer-facing front door).
