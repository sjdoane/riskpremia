# CHANGELOG

What shipped, plus every review finding and its resolution (rule 2). Newest
first. This is the audit trail; STATUS.md is the current-state snapshot.

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
