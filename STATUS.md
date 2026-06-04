# STATUS

Single source of truth for where Project RiskPremia is and what is deferred.
Read this first on any new session. Update after every meaningful work block
(rule 2).

Last updated: 2026-06-03 (session 2, data-layer PR1).

## One-line state

Lead track LOCKED: **Track B (crypto perpetual-futures funding carry,
delta-neutral), framed as a measurement study.** Repo is on GitHub
(https://github.com/sjdoane/riskpremia, main pushed). Data-layer **PR1 (typed
core) is done**: implemented, green (mypy --strict 15 files, ruff, 36 tests,
em-dash all clean), and post-implementation reviewed (FIX-THEN-SHIP; 1 High + 4 Low all
addressed). On branch `feat/data-layer-pr1-typed-core`, ready to open the PR. No
strategy logic yet (correct: cost model + random-entry null first).

GOTCHA (Windows, load-bearing): polars needs the `tzdata` package to resolve the
"UTC" tz string when materializing tz-aware datetimes (pinned `tzdata==2026.2` in
core deps); without it `to_list()` panics with ZoneInfoNotFoundError.

## Lead-track decision (locked in ADR 0001)

- **Track B is the lead.** Reason: no WRDS/OptionMetrics setup exists on the
  machine and the entitlement is not confirmable without the user's WRDS login; even if entitled,
  OptionMetrics raw data is non-redistributable, which breaks the reproducibility
  brand. Crypto funding data is free and empirically reproducible from a US IP.
- A unanimous four-lens review (realist, quant, builder, growth, all high confidence) and an endorse-with-caveats adversarial cross-check backed Track B. Full record
  in `docs/decisions/0001-lead-track-selection.md`.
- **Career-target fork RESOLVED (2026-06-03):** asked, and the user deferred to
  the project lead's judgment ("make the decision"). Track B is LOCKED. Framing default:
  broad / systematic / reproducibility-first (the Track-B-optimal audience). No
  WRDS/OptionMetrics chase; Track A stays the "also examined" contrast section.

## Spike findings (2026-06-03, US IP)

- WRDS: zero setup (no env vars, no .pgpass, no `wrds` package, no breadcrumbs);
  entitlement unconfirmable without the user's credentials; non-redistributable
  even if entitled.
- Crypto: OKX live funding + candles to 2020-09 (US-reachable, no key);
  Hyperliquid on-chain (US-reachable, ~2023+); Binance Vision S3 dumps from
  2020-01 (checksummed, reproducible, US-reachable). Live Binance/Bybit APIs are
  geo-blocked from the US IP (honest venue-access friction -> risk register).

## Done this session

- Clean dedicated venv at `C:\Users\SamJD\.venvs\riskpremia` (Python 3.12.13;
  NOT the off-limits pit-backtest venvs). Pinned `pyproject.toml`
  (polars 1.41.1 / numpy 1.26.4 / pydantic 2.9.2 / attrs 24.2.0; dataops:
  httpx 0.27.2; dev: pytest/mypy/ruff). Versions verified installed.
- Project structure: `src/riskpremia/{analytics,validation,data,execution,
  strategy}`, `tests/{unit,integration}`, `docs/{decisions,methodology,research}`,
  `scripts`, `artifacts`, `data/snapshots`.
- Vendored (copied + attributed, from pit-backtest `edad904`) the asset-agnostic
  stack: `analytics/sharpe.py` (PSR/DSR/MinTRL), `analytics/bootstrap.py`
  (stationary block bootstrap + Politis-White), `validation/cv.py` (purged
  CPCV), `validation/trial_registry.py` (DSR trial count). Fidelity pinned by
  `tests/unit/test_vendored_stack.py` (8 tests, all green; DSR canonical 0.7657
  matches the 0.766 acceptance pin).
- ADR 0001 (lead-track selection) with the pre-registered kill criterion.
- STATUS / CHANGELOG / memory note.

## Pre-registered kill criterion (frozen UPFRONT, full text in ADR 0001)

The study ships regardless (an honest null is acceptable). The kill gate is about
REAL-MONEY deployment:
- Early economic gate: if median 8h funding collected on the US-tradeable venue
  does not exceed amortised round-trip cost for a passive always-on carry in the
  held-out post-ETF regime, the naive carry is dead after costs.
- Primary kill gate: net-of-all-cost Deflated Sharpe < 0.95 out-of-sample, under
  event-time-purged CPCV with embargo, on the frozen trial count, on the held-out
  post-ETF period -> declare non-viable for deployment and ship the honest null.

## Next (in order)

The data-layer milestone is PLANNED and design-reviewed (design locked in
`docs/research/0001-data-layer-design.md`; the reviewer probed live data and
caught a factual error in the OKX gate, plus 4 more Critical/High findings, all
resolved in that doc). Scope was cut per rule 6 so the cost model is not blocked.

1. ~~Data-layer PR1 (typed core + CPCV contract test).~~ DONE + reviewed; open
   the PR, then continue.
2. **Data-layer PR2:** `binance_vision.py` (BTCUSDT funding + matched MARK + spot)
   + a `network` live checksum-verify test. Ships ADR 0002. Inherits the PR2
   carry-overs from the reviews: pre-committed BTC/ETH survivor universe, the
   matched-mark-vs-spot basis, dedup price frames at the source (post-implementation L4),
   the clamp-incidence diagnostic.
3. **Data-layer PR3:** `okx.py` realized-history single fetch + the Binance-vs-OKX
   funding delta join (for the kill-gate venue).
4. **Cost model (ADR 0003), parameterised to a US-tradeable venue** (taker/maker
   fees + both-leg spread + funding + short-term tax), then run a RANDOM-ENTRY
   NULL through it before any signal. This is also the early economic kill gate.
5. Only then: the carry signal + the risk-OFF regime circuit breaker; event-time
   CPCV glue; capacity curve; break-even-cost exhibit; regime decomposition;
   committed artifact + figures.

Deferred from the data layer (not on the critical path to the first kill-gate
number): Hyperliquid source, OKX retention-probe machinery, multi-coin universe,
full S3 pagination generality.

## Deferred / open

- Career-target fork RESOLVED (user deferred to agent judgment; Track B locked).
- A US-tradeable execution venue must be chosen for the cost model (candidates:
  Kraken, Coinbase, CME micro futures, Hyperliquid). Decide in the cost-model
  ADR with real fee schedules.
- Binance Vision funding-history depth + instrument survivorship to be quantified
  during the data-layer milestone.
- CI (GitHub Actions: mypy --strict src + pytest) deferred until after the first
  real milestone, mirroring pit-backtest.

## Hard rules (full text in README + the portfolio session_rules)

Independent reviews plus a multi-perspective panel on every meaningful chunk/fork; keep STATUS/CHANGELOG/
memory/ADRs current; no em-dashes (sweep before commit); kill-early with the
criterion above; Windows-first PowerShell + absolute paths; clean venv only;
verify against REAL data, cost model first; no secrets in chat; pinned deps +
reproducible artifacts.
