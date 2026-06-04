# STATUS

Single source of truth for where Project RiskPremia is and what is deferred.
Read this FIRST on any new session, then the ADRs it points to. Update after
every meaningful work block (rule 2).

Last updated: 2026-06-03 (session 3: the kill gate is COMPLETE; PR4a + PR4b shipped, first kill number is an honest NULL).

## One-line state

A reproducible, intellectually-honest MEASUREMENT study of the crypto
perpetual-futures funding-carry risk premium. Lead track LOCKED: **Track B**
(crypto funding carry, delta-neutral), ADR 0001. Repo:
https://github.com/sjdoane/riskpremia. **The data layer (PR1+PR2+PR3) and the
KILL GATE (PR4a per-trade math + PR4b the null + the first kill number) are DONE.**
**The first net-of-cost number is a decisive, honest NULL: net-of-cost Deflated
Sharpe (PSR(0)) = 0.0000 on every US-tradeable venue (Kraken, Hyperliquid) at every
horizon at the conservative 2N capital charge**, and every tradeable cell still
fails the 0.95 bar even at the favourable 1N charge. The naive always-on /
random-entry carry is non-viable after costs; any edge must come from selection
(which raises the bar). PR4a on `feat/cost-model-pr4a-per-trade-pnl`
(github.com/sjdoane/riskpremia/pull/4), PR4b on `feat/cost-model-pr4b-null-gate`
(stacked).

## Dev commands (Windows PowerShell; the venv is run DIRECTLY)

```
$env:PYTHONIOENCODING="utf-8"
$py = "C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe"
& $py -m pytest -q                 # 62 pass (offline); never touch the off-limits pit-backtest venvs
& $py -m pytest -q -m network      # live-exchange tests (OKX + Binance Vision), skipped in CI
& $py -m mypy                       # strict, 20 src files
& $py -m ruff check src tests
```
Setup if the venv is gone: `uv venv --python 3.12 C:\Users\SamJD\.venvs\riskpremia`
then `uv pip install --python $py -e ".[dev]"`.

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
- 104 tests (96 offline + 8 live `network`); mypy --strict 26 files (+ the script) /
  ruff / em-dash clean; CI green (`.github/workflows/ci.yml`, installs `.[dev]`, runs
  ruff + mypy + `pytest -m "not network"`, so CI runs the 96 offline).

The data layer yields, for a perp, an aligned **funding + perp-mark + spot +
basis** series on the funding-event clock that feeds the vendored
event-time-purged CPCV directly. Every input is checksum-reproducible (Binance
Vision) or live-and-keyless (OKX). The whole layer fetches with the STDLIB ONLY.

## The kill gate (ADR 0003): DONE; the result; what is next

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

**Next session (the gate is done; this is no longer cost-model work):**
1. Write up the null as the recruiter-facing deliverable: the README results
   table + the decay/financing-dominance story + the venue cost-sensitivity
   surface + the figures (matplotlib `figures` extra; commit a regenerable JSON
   artifact like the sibling project, NOT a parquet/db).
2. The deferred follow-ups (ADR 0003): replace the conservative assumed spread with
   the MEASURED median from the free Binance Vision `bookTicker` dataset; the
   capacity curve (order-book-walk impact, the size where net edge crosses zero).
3. ONLY IF pursuing deployment: a selection / regime-OFF signal, which now must
   clear a RAISED bar (it has to beat this null after costs AND survive the
   multiple-testing deflation the trial registry is already accumulating). A
   genuine fork -> a four-lens review + an adversarial cross-check before building.

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
  circuit breaker; the committed artifact + figures (matplotlib `figures` extra).
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
