# CHANGELOG

What shipped, plus every review finding and its resolution (rule 2). Newest
first. This is the audit trail; STATUS.md is the current-state snapshot.

## 2026-06-03, session 3: the kill gate, PR4a (the per-trade P&L math)

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
