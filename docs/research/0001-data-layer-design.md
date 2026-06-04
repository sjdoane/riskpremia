# Data-layer design (post Plan-review), locked scope for implementation

Status: design locked 2026-06-03 (Plan agent -> senior-quant Plan-reviewer, rule 1).
The ADR (0002) ships with the first implementation PR; this note is the durable
design + the review resolutions so implementation proceeds without re-derivation.

## What the data layer must produce

For a perpetual instrument, an aligned, point-in-time, reproducible series of:
realized funding (on its native funding clock), perp MARK price, and a matched
spot reference (for the delta-neutral leg + the basis). Output: a sorted
`pl.Datetime("us","UTC")` observation frame + a matching-dtype non-null
`label_horizons` series that the vendored event-time-purged CPCV
(`src/riskpremia/validation/cv.py`) consumes, where the event clock is the
FUNDING event, not the calendar.

## Design spine (kept from the plan, verified sound)

- One typed `FundingSource` Protocol; two retention tiers: `BinanceVisionSource`
  (long-history, reproducible backbone, stdlib-only fetch) and a live tier
  (`OKXSource`; Hyperliquid deferred). The premium + post-ETF decay are measured
  on Binance Vision; the kill gate + capacity + paper-trade run on the live tier.
- `funding_interval_hours` is carried as data per row, never hardcoded (Binance
  ships it =8; OKX 8h; Hyperliquid 1h).
- pydantic at the IO boundary (one file), polars + attrs in the hot path.
- Reproducibility = content addressing: raw to `data/raw/` (gitignored),
  checksum-verified vs Binance's published CHECKSUM, SHA256-stamped into
  `data/snapshots/manifest.toml`, one derived aggregate artifact committed.

## Plan-review resolutions (all accepted; load-bearing)

The reviewer probed OKX/Binance live and returned APPROVE-WITH-CHANGES. The five
Critical/High items below are binding on implementation.

1. [Critical] **OKX realized-gate premise was factually wrong.** The
   `/funding-rate-history` head row is ALREADY SETTLED (has `realizedRate`,
   `method == "current_period"`), not a future row; the predicted/future rate
   lives in the SEPARATE `/funding-rate` (current) endpoint. Resolution: gate
   `realized = (realizedRate is not None) and (method == "current_period") and
   (funding_window_end < now)`, strict `<`, NOT a clock `<=`. The observation
   path NEVER reads `/funding-rate`. The predicted `fundingRate` field is
   physically excluded from the `FundingRecord` so a careless edit cannot leak a
   prediction into the label.
2. [Critical] **Binance funding is a CLAMPED interest-rate + premium composite.**
   Reporting `last_funding_rate` as "the premium" is a category error.
   Resolution: `funding_rate` is documented as the realized clamped composite
   CASH FLOW (the carry P&L is correct); keep the `premium` component where the
   venue exposes it (Hyperliquid ships `premium` per row); add a clamp-incidence
   diagnostic (fraction of events at the venue cap) to the derived artifact; the
   ADR states plainly this is the harvestable cash flow, not the pure premium.
3. [Critical] **Basis must be a MATCHED, snapshotted product.** Use the perp MARK
   price (funding settles on mark/index, not trade price) against a same-quote
   spot product, both snapshotted + checksummed. Hyperliquid basis is set to null
   (deferred) because its off-venue spot hedge is not reproducible yet; the kill
   gate is forbidden from reading a basis it cannot regenerate from committed
   inputs.
4. [Critical] **Binance Vision survivorship biases the premium UP** (only
   surviving symbols are dumped; `available_months` cannot detect a symbol that
   never appears). Resolution: the v1 headline universe is a pre-committed
   SURVIVOR set (BTCUSDT first, ETHUSDT next), NOT a multi-coin median (which is
   maximally exposed). ADR 0002 + the methodology doc caveat this at the point
   the premium is computed, mirroring the pit-backtest survivorship lesson.
5. [High] **Quantify the venue-basis confound, do not just caveat it.** Emit a
   Binance-vs-OKX funding DELTA series on the matched `(canonical, dt)` grid so
   the kill gate runs on OKX-realized funding (what a US trader actually
   receives) while the decay headline uses the long Binance history. The
   cross-venue `canonical` id is the join key.

Folded-in determinism/test items (cheap, into PR1/PR2): positive assertion that
`dt` is `pl.Datetime("us","UTC")` TZ-AWARE and `label_horizons` is byte-identical
dtype incl tz (finding 8); a horizon gap-guard (record max wall-clock span of any
H-event horizon; flag outage-straddling labels) + assert `height == horizons.len()`
after the trailing-H drop, at build time (finding 9); a test that the Float64
`basis` matches the Decimal basis to 1e-9 on a real BTC row (finding 10);
`extra="forbid"` ONLY on the immutable Binance CSV, `ignore` on the live OKX/HL
JSON (which carry `formulaType`/`method`/`instType` the plan did not model)
(finding 12); a committed regeneration script + a fixture-scale artifact
byte-equality test, not narration (finding 11); pin the spot-ETF regime boundary
(2024-01-11) as one named constant + test a straddling window without both tiers
raises (finding 15); the modal-gap check is a tolerance-banded WARNING recording
the mismatch fraction, hard-raising only on order-of-magnitude mismatch or a null
interval, because Binance early-2020 funding is ~3/day not a clean 8h grid
(finding 6); dedup key is `(instrument, funding_ts, realized=True)`, prefer the
realized row, raise only when two realized rows at one key differ, deterministic
via a stable `_ingest_idx` (finding 7).

## Locked scope (the reviewer's CUT TO SHIP FASTER, accepted per rule 6)

Rule 6 says the cost model + the random-entry null come NEXT and must not be
blocked. So the data layer ships the minimum that feeds them, then stops:

- **PR1 (the reviewable heart, no network):** `records.py`, `boundary.py`,
  `clock.py`, `manifest.py`, a committed tiny BTCUSDT-2020-01 fixture, the unit
  tests, and the CPCV-consumes-observation-frame CONTRACT test (the single most
  valuable test). Includes findings 8, 9, 10, 12.
- **PR2:** `binance_vision.py` trimmed to BTCUSDT (funding + matched MARK + spot),
  its unit tests + a `network` live test that downloads + checksum-verifies the
  real 2020-01 zip. Includes findings 3, 4, 6. Ships ADR 0002.
- **PR3:** `okx.py` reduced to a single realized-history fetch for the kill-gate
  venue + the Binance-vs-OKX delta join. Includes findings 1, 5.
- **Deferred to later (not on the critical path to the first kill-gate number):**
  Hyperliquid source, the OKX/HL retention-probe machinery, the multi-coin
  universe, full S3 `IsTruncated`+`Marker` pagination generality.

Outcome: a checksummed, reproducible BTCUSDT Binance funding + mark + spot + basis
series, plus an OKX realized series for the kill gate, which is exactly what the
random-entry null and the early economic gate consume. Roughly halves the
pre-cost-model LOC.

## CPCV consumer contract (verified against cv.py, do not drift)

`CPCVSplitter.split(observations, label_horizons)` requires: `observations` is a
`pl.DataFrame` with a `dt` column of dtype `pl.Datetime`, sorted ascending;
`label_horizons` is a `pl.Series` of the SAME dtype, non-null, equal length. The
purge predicate is `dt[j] <= dt[t_end] AND label_horizons[j] >= dt[t_start]`, so
`label_horizons[i]` must be the settlement instant by which event i's labeled
carry is fully realized (`dt.shift(-H)` on the deduped sorted grid).
