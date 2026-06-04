# STATUS

Single source of truth for where Project RiskPremia is and what is deferred.
Read this FIRST on any new session, then the ADRs it points to. Update after
every meaningful work block (rule 2).

Last updated: 2026-06-04 (session 4: PIVOTED to the crypto VRP study (ADR 0004); the measurement floor (PR5a) is built and the first VRP is measured + positive; PR5b shipped the committed measurement artifact + figures + the DVOL/spot reproducibility-fixture manifest stamp; PR5c shipped the Tardis Deribit option-chain loader; PR5d shipped the delta-hedged-option cost model; PR5e shipped the per-trade short-variance option P&L with the inverse coin settlement that makes the crash tail honest).

## One-line state

A reproducible, intellectually-honest MEASUREMENT study of crypto risk premia. Study
1 (the funding carry) was KILLED honestly (the kill gate, on `main`: net-of-cost
Deflated Sharpe ~0 on every US-tradeable venue/horizon, an honest null). Per the
pivot-on-failure rule, **the active study is now the crypto VARIANCE RISK PREMIUM
(VRP), ADR 0004**, in two layers: (i) a reproducible index-level MEASUREMENT (Deribit
DVOL implied variance minus realized variance from the Binance Vision klines), and
(ii) a cost-gated short-variance tradeable test, pre-registered as a likely
cost/peso-bounded null. **Layer i (PR5a) is BUILT** (the DVOL source, the
realized-variance estimator, the non-overlapping headline). **First measured VRP**
(BTC, 2022-01..2025-06, 30-day, real data): mean variance premium 0.087, 95%
bootstrap CI [0.033, 0.119] CLEARING zero (overlap-honest), 70% of days positive,
pre-ETF 0.101 -> post-ETF 0.059 (a decay paralleling the carry). The VRP is a real,
positive premium; the open question is whether it survives option-selling costs +
the peso tail (Layer ii). Repo: https://github.com/sjdoane/riskpremia. PR5a on
`feat/vrp-dvol-and-measurement`.

## Dev commands (Windows PowerShell; the venv is run DIRECTLY)

```
$env:PYTHONIOENCODING="utf-8"
$py = "C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe"
& $py -m pytest -q -m "not network" # 163 pass (offline); never touch the off-limits pit-backtest venvs
& $py -m pytest -q -m network       # live: Binance Vision + OKX + Deribit DVOL + Tardis (the real-data proof)
& $py -m mypy                       # strict, src + scripts
& $py -m ruff check src tests scripts
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
- 163 offline + 12 live `network` tests (the figure render test runs locally, skipif
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
(a 90% crash on a short put settles ~9x the notional). Next steps:
1. Layer ii FINALE (PR5f): the short-variance random-entry null + the cost/peso-bounded
   gate + the regime-conditional tail-loss table + the verdict (reuse `strategy/null.py`
   + `execution/scoring.py` + the kill-gate discipline; a `scripts/run_vrp_gate.py`). It
   gathers the first-of-month entry snapshots across the VRP window (select a near-ATM
   option per month via the Tardis loader; the realized expiry underlying from Binance
   Vision), runs `simulate_option_trade` per entry, and COMMITS the monthly snapshot
   fixtures (the deferred reproducibility artifact, SHA256-stamped) now that the
   months/expiries are fixed. Headline = the measurement + the regime tail-loss table,
   NEVER a short-vol Sharpe; the un-measurable path-rehedge slippage is the dominant
   un-modeled cost (named on `OptionTradePnL` via `path_rehedge_unmodeled`; ADR 0004).
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
