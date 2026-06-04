# CHANGELOG

What shipped, plus every review finding and its resolution (rule 2). Newest
first. This is the audit trail; STATUS.md is the current-state snapshot.

## 2026-06-03, session 2: GitHub + data-layer PR1 + PR2

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

### GitHub presentation (no AI attribution)

- Rewrote history to strip the tooling co-author trailers and force-pushed; the
  contributor graph now shows only the author. Reworded the public docs and
  source docstrings so the review process reads in plain human terms (a design
  plan, an independent senior-quant design review, a post-implementation review,
  and a multi-perspective review with an adversarial cross-check at each fork),
  keeping the substance. Untracked the internal scoping notes (gitignored).

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
  pydantic 2.9.2, attrs 24.2.0; dataops extra httpx 0.27.2; dev pytest 8.3.3 /
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
