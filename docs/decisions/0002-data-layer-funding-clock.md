# ADR 0002: the data layer and the funding-event clock

Status: Accepted (ships with PR1 + PR2).
Date: 2026-06-03.
Authors: Sam Doane (design locked via a design plan + an independent senior-quant
design review per rule 1; full record in `docs/research/0001-data-layer-design.md`).

## Context

The funding-carry study needs a point-in-time, reproducible, multi-venue data
layer that yields, per perpetual instrument, an aligned series of realized
funding, perp mark price, and a matched spot reference, shaped so the vendored
event-time-purged CPCV (`validation/cv.py`) consumes it directly. The week-1
spike (ADR 0001) established the venue facts: the live Binance/Bybit REST APIs are
geo-blocked from US IPs, but the Binance Vision S3 dumps and OKX are reachable, so
the long-history reproducible backbone is Binance Vision and the live US-reachable
tier (for the kill gate and a forward paper-trade) is OKX.

## Decisions

1. **The event clock is the funding settlement, not the calendar.** The
   observation frame carries one row per realized funding event, `dt` = the
   settlement instant as `pl.Datetime("us", "UTC")` (tz-aware), 24/7. This dtype
   is pinned so the `dt` column and the `label_horizons` series share an
   identical dtype, which the CPCV parity gate requires.

2. **`funding_interval_hours` is carried as data, never hardcoded.** Binance
   ships it per row (=8 for BTCUSDT); OKX is 8h, Hyperliquid 1h. The cost
   model amortizes round-trip cost over the holding period in interval units, so
   a wrong interval would silently mis-scale net carry.

3. **pydantic at the IO boundary, polars + attrs in the hot path.** Raw rows
   validate once through frozen pydantic models in `data/boundary.py` (the only
   module importing pydantic, AST-enforced by a lint) and convert to attrs
   records; all alignment is polars. The single Decimal-to-Float64 cast is the
   one documented precision commitment.

4. **Realized-aware, order-deterministic normalization.** `normalize_funding_frame`
   rejects a multi-instrument mix, raises on a null interval, detects settled-row
   conflicts (two `realized` rows at one stamp with differing rates), dedups
   preferring the settled row then the earliest ingest (a stable `_ingest_idx`,
   not fetch order), and hard-raises on an interval mislabel only when the median
   gap is an order of magnitude off the stamped interval. A smaller mismatch is a
   recorded diagnostic, because Binance early history is genuinely about 3 per day,
   not a clean 8h grid (design review finding 6).

5. **The perp leg is the MARK price; the basis is a matched product** (design
   review finding C3). Funding settles on the mark/index, not the last trade, so
   the perp leg uses the Binance Vision `markPriceKlines` dataset, and the spot
   leg uses the spot-market klines with an explicit matched quote (`USDT`), so the
   basis is never a cross-quote artifact. Prices join onto each funding event with
   a backward `join_asof` (structurally PIT-safe); the realistic study pattern
   warms up the price legs before the funding window so the first event has a
   prior price rather than a null.

6. **Funding is the clamped composite cash flow, not the pure premium** (finding
   C2). `funding_rate` is documented as the realized clamped interest + premium
   composite that is actually paid or received (the carry P&L is correct);
   `premium` is carried where a venue exposes it (Hyperliquid does, Binance does
   not); a clamp-incidence diagnostic is planned for the derived artifact.

7. **Pre-committed survivor universe** (finding C4). Binance Vision only dumps
   surviving symbols, so a cross-sectional median over all coins would be
   survivorship-inflated and `available_months` cannot detect a symbol that never
   appears. The v1 headline universe is the fixed survivor set
   `SURVIVOR_UNIVERSE = (BTCUSDT, ETHUSDT)`; no multi-coin median is computed.

8. **Reproducibility = content addressing.** Raw zips/JSON are fetched to
   `data/raw/` (gitignored), every Binance download is verified against the
   published `.CHECKSUM` SHA256, and snapshots are SHA256-stamped into
   `data/snapshots/manifest.toml` (committed). A reviewer re-fetches and verifies
   byte-identity before regenerating. The Binance Vision dumps are immutable, so
   the long-history headline reproduces exactly; the OKX/Hyperliquid live tier is
   as-of-stamped (an honest split documented here).

## What ships in PR2

`data/sources/base.py` (the `FundingSource` / `MarkSource` / `SpotSource`
Protocols) and `data/sources/binance_vision.py` (stdlib-only: S3 listing with
marker pagination, checksummed download with an idempotent content cache, and
funding / mark-price / spot parsing), plus `clock.marks_frame` / `spot_frame`.
A tiny real BTCUSDT-2020-01 funding zip and a full S3-listing XML are committed
as offline fixtures; the live end-to-end pull is a `network`-marked integration
test (the reproducibility proof on real data: it lists S3, downloads and
checksum-verifies the immutable funding zip, and builds the funding + mark + spot
+ basis frame).

## Deferred (per the cut-to-ship scope, rule 6)

The OKX live source + the Binance-vs-OKX funding delta (PR3, findings 1 and 5);
Hyperliquid; the OKX retention-probe machinery; the multi-coin universe; the
`scripts/fetch_funding.py` manifest-stamping entry point and the committed derived
artifact (a later PR). None block the cost model + the random-entry null, which
are next.


## PR3 amendment: the OKX live tier + the venue delta

PR3 adds the US-reachable kill-gate venue and the venue-basis measurement.

9. **OKX realized gate (design review finding 1).** `data/sources/okx.py` reads
   only the SETTLED `funding-rate-history` endpoint (never the predicted
   `/funding-rate`), and `boundary.PydanticOKXFundingRow.to_record` accepts a row
   only when `realizedRate` is present, `method == "current_period"`, and the
   settlement instant is strictly before now; it uses `realizedRate` (the paid
   rate), never the predicted `fundingRate`. `extra="ignore"` on the live JSON so
   OKX adding a field does not crash the tier.

10. **OKX is recent-only (verified live).** The public funding history pages back
    about 93 days (3 months), then exhausts; `fetch_funding` returns what is
    available and does not error past the floor. OKX is therefore the live/recent
    source for the kill gate and a forward paper-trade, NOT a long-history source.

11. **Binance-vs-OKX funding delta (finding 5).** `data/cross_venue.py` measures
    the venue basis directly on the overlap: `funding_rate_binance -
    funding_rate_okx` on the matched settlement grid. Because OKX is recent-only,
    the delta is measured on the recent overlap and applied as an adjustment to
    the longer Binance-based estimate, so the kill gate reflects what a US trader
    actually receives. Live, the basis is small (median under 0.1% per 8h).

12. **GRID-SNAP gotcha (verified live).** Binance Vision `calc_time` carries a few
    milliseconds of jitter around the settlement instant (e.g. 00:00:00.003),
    while OKX `fundingTime` is the clean boundary. A naive timestamp join loses
    about half the events; the delta rounds each `dt` to the funding-interval grid
    before joining. Within-venue series keep the raw jittered `dt` (harmless for
    the 8h-spaced CPCV clock); only the CROSS-venue join snaps.

13. **Stdlib-only fetch.** OKX (and a future Hyperliquid) fetch with the stdlib
    (`urllib` + `json`), like the Binance Vision source, so the whole data layer
    has zero third-party fetch surface; the unused `httpx` dependency and the
    `dataops` extra are removed. The OKX endpoint 403s the default
    `Python-urllib` User-Agent, so a descriptive User-Agent is sent.


## Status

Accepted. PR2 implements decisions 5, 7, 8 (and the PR1-shipped 1 to 4, 6
apparatus). PR3 adds the live tier; the cost model (ADR 0003) follows.
