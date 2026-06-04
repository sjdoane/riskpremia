# STATUS

Single source of truth for where Project RiskPremia is and what is deferred.
Read this FIRST on any new session, then the ADRs it points to. Update after
every meaningful work block (rule 2).

Last updated: 2026-06-03 (session 2: data layer complete, kill-gate design locked).

## One-line state

A reproducible, intellectually-honest MEASUREMENT study of the crypto
perpetual-futures funding-carry risk premium. Lead track LOCKED: **Track B**
(crypto funding carry, delta-neutral), ADR 0001. Repo:
https://github.com/sjdoane/riskpremia. **The reproducible multi-venue data layer is COMPLETE** (PR1+PR2+PR3
merged). **The cost model + random-entry null (the kill gate) is DESIGNED and
deeply reviewed: ADR 0003.** NEXT: implement PR4a (the per-trade P&L math) then
PR4b (the null + the first net-of-cost kill number). No strategy logic yet (by
design: the cost model + null come before any signal, rule 6).

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
- `execution/` + `strategy/`: only docstrings so far (the kill gate goes here).
- 62 tests (57 offline + 5 live `network`); mypy --strict / ruff / em-dash clean;
  CI green (`.github/workflows/ci.yml`, installs `.[dev]`, runs ruff + mypy +
  pytest, network tests skipped).

The data layer yields, for a perp, an aligned **funding + perp-mark + spot +
basis** series on the funding-event clock that feeds the vendored
event-time-purged CPCV directly. Every input is checksum-reproducible (Binance
Vision) or live-and-keyless (OKX). The whole layer fetches with the STDLIB ONLY.

## Current task: the kill gate (ADR 0003)

The trade: delta-neutral funding carry (long spot N, short perp N, hold H funding
intervals, collect funding, close). Build the cost model FIRST, run a
random-entry NULL through it, produce the first net-of-cost number (rule 6). ADR
0003 has the full locked design; the load-bearing decisions a reviewer caught
(all resolved) and that the implementation MUST honor:

- **Funding sign (was a trap):** `funding_rate` positive = longs pay shorts; the
  short book collects `+sum(funding_rate[i+1..i+H])`. Pin with an
  economic-direction FIXTURE, never a comment.
- **Cost is LUMPY, not amortised:** booking the round-trip cost per interval
  shrinks the skew/kurtosis the DSR penalises and INFLATES it. Book it on the
  interval incurred; report amortised-vs-lumpy; the **kill reads the LESS
  favourable**.
- **CPCV embargo >= H:** the overlapping holds leak unless the embargo covers the
  H-event window. Force `embargo_count >= H`, assert before splitting.
- **Financing/capital cost:** no cross-margin means 2N capital is tied up; charge
  its opportunity cost over the hold.
- **DSR headline is PRE-tax** (tax is a personal level-shift); after-tax is an
  annual-aggregate sidebar with within-year loss offset.
- **Non-overlapping return series** for the DSR `T` (overlapping holds
  autocorrelate; raw `T` overstates significance).
- The null is a separate **control** trial-family, so at this pre-signal
  milestone the kill number is honestly `PSR(0)` at `n_effective=1`.
- **Spread is conservative-or-MEASURED** (the stress-test's most-likely loss):
  use a deliberately high half-spread + label provisional, OR measure the median
  from the free Binance Vision `bookTicker` dataset. The kill reads the less
  favourable so a soft spread cannot fake a pass.
- **The kill_gate-marked invariant:** the funding window for entry `i` is exactly
  `range(i+1, i+H+1)` AND identical to the `make_label_horizons` `dt.shift(-H)`
  label (verified correct in review), with a P&L-conservation cross-check.

PR4a = `execution/{errors,cost,carry}.py` + the per-trade math tests (the sign
fixture, the index-identity kill_gate test, the financing term). PR4b =
`strategy/null.py` + `execution/{scoring,exhibit}.py` + `scripts/run_null_gate.py`
+ the embargo>=H glue + the first kill number across venues. Model a few
US-tradeable venues (Kraken Futures, Hyperliquid; Binance/OKX as non-tradeable
reference) so the gate is a cost-sensitivity surface.

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
