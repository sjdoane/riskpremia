"""Tardis Deribit option-chain snapshot source (ADR 0004 Layer ii, the data layer).

Tardis publishes the FIRST DAY of each month of Deribit `options_chain` data for free
and keyless (verified US-reachable), as a single ~1.8 GB gzipped CSV per day that
interleaves every BTC and ETH option's tick-level quote updates. The file is ordered by
`local_timestamp` (the capture clock); the exchange `timestamp` is NON-monotonic by up
to about 1 second (verified on the real file: about 27% of rows step backward in
exchange time, max step ~1.0 s), which the snapshot logic below is built to tolerate.
The monthly cadence constrains Layer ii to a low-frequency (monthly-snapshot) design, a
reproducibility feature.

We never cache the gigabyte: the loader STREAMS the gzip and extracts a point-in-time
chain snapshot, stopping as soon as it has read past the snapshot instant. The snapshot
is a BACKWARD as-of (design review C1, the same point-in-time discipline as the
funding-clock backward join): pick an explicit `as_of` entry instant (the day's midnight
plus `as_of_offset_minutes`) and keep, per instrument, its FRESHEST quote (the maximum
exchange `timestamp`) with `timestamp <= as_of`. Keeping the max-timestamp quote (NOT
the file-last one) makes the pick row-order-independent despite the ~1 s exchange-clock
disorder. That is point-in-time honest (a position stamped at `as_of` is priced only on
data at or before `as_of`); the freshest-in-a-forward-window rule would leak future
information into the entry and is deliberately NOT used. Contracts that already expired
by `as_of` are dropped (a settled instrument can still carry a stale quote).

The early stop tolerates the exchange-clock disorder (design review C2): we read until
the exchange `timestamp` exceeds `as_of + grace`, where the 30 s default grace dwarfs
the ~1 s disorder, so no `timestamp <= as_of` quote is skipped before the stop fires.
Before returning, a loud completeness check asserts the file actually covered `as_of`,
the snapshot has enough instruments, and the strikes bracket the underlying, so a
truncated or thin chain fails loudly rather than silently biasing the downstream
selection. (Reproducibility: the committed offline monthly snapshot is deferred to the
consuming cost-model PR, once the needed months/expiries are fixed; this loader's live
network test is the real-data proof, and an immutable Tardis daily object will then be
stamped as the snapshot's provenance.)

Stdlib-only (urllib + gzip + csv), an injectable stream opener for deterministic
offline tests, the same zero-third-party-fetch property as the other sources.
"""

from __future__ import annotations

import csv
import gzip
import io
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import IO

import attrs

from riskpremia.data.boundary import TARDIS_OPTIONS_HEADER, PydanticTardisOptionRow
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.records import DvolCurrency, OptionQuoteRecord

_USER_AGENT = "riskpremia variance-risk-premium research (https://github.com/sjdoane/riskpremia)"
_COL = {name: i for i, name in enumerate(TARDIS_OPTIONS_HEADER)}
_TS_IDX = _COL["timestamp"]
_SYM_IDX = _COL["symbol"]
_TYPE_IDX = _COL["type"]
_US_PER_SECOND = 1_000_000
# Backstop against a runaway read if the early-stop ever fails to trigger (e.g. a
# non-increasing timestamp stream): a full day is roughly 12M rows, so this caps the
# scan to a fraction of that and raises rather than pulling the whole gigabyte.
_MAX_ROWS_SCANNED = 8_000_000


@attrs.frozen(slots=True)
class OptionChainSnapshot:
    """A point-in-time option-chain snapshot for one currency at one `as_of` instant.

    `quotes` is sorted by `(expiry, strike, option_type)` (deterministic, vendor-row-
    order-independent). Each quote's `quote_ts` is its real last-<=`as_of` observation,
    so per-instrument staleness is `as_of - quote_ts`.
    """

    currency: DvolCurrency
    snapshot_date: date
    as_of: datetime
    quotes: tuple[OptionQuoteRecord, ...]


class TardisOptionChainSource:
    """First-of-month Deribit option-chain snapshots from the free Tardis datasets."""

    venue = "tardis"

    def __init__(
        self,
        *,
        base_url: str = "https://datasets.tardis.dev",
        open_stream: Callable[[str], IO[bytes]] | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._open = open_stream
        self._timeout = timeout

    def _default_open(self, url: str) -> IO[bytes]:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        resp: IO[bytes] = urllib.request.urlopen(req, timeout=self._timeout)
        return resp

    def _url(self, snapshot_date: date) -> str:
        # The free tier is the first day of each month; day is guarded to 1 by the caller.
        return (
            f"{self._base}/v1/deribit/options_chain/"
            f"{snapshot_date.year:04d}/{snapshot_date.month:02d}/01/OPTIONS.csv.gz"
        )

    def fetch_snapshot(
        self,
        currency: DvolCurrency,
        snapshot_date: date,
        *,
        as_of_offset_minutes: int = 60,
        grace_seconds: int = 30,
        min_instruments: int = 20,
    ) -> OptionChainSnapshot:
        """Stream the first-of-month chain and extract the backward as-of snapshot.

        `as_of = midnight(snapshot_date) + as_of_offset_minutes` is the explicit entry
        instant; each instrument's quote is its last with `timestamp <= as_of`. Reading
        stops once `timestamp > as_of + grace_seconds`.

        Raises:
          VenueFetchError: when `snapshot_date` is not the first of a month (the free-
            tier constraint), the header drifts, the file did not cover `as_of`
            (truncated), the snapshot is too thin, or its strikes do not bracket the
            underlying (a silent-truncation guard).
        """
        if snapshot_date.day != 1:
            raise VenueFetchError(
                f"Tardis free option chains are first-of-month only; got {snapshot_date}"
            )
        midnight = datetime(snapshot_date.year, snapshot_date.month, 1, tzinfo=UTC)
        as_of = midnight + timedelta(minutes=as_of_offset_minutes)
        as_of_us = int(as_of.timestamp()) * _US_PER_SECOND
        stop_us = as_of_us + grace_seconds * _US_PER_SECOND
        prefix = f"{currency}-"

        opener = self._open if self._open is not None else self._default_open
        stream = opener(self._url(snapshot_date))
        snapshot: dict[str, OptionQuoteRecord] = {}
        reached_as_of = False
        try:
            text = io.TextIOWrapper(gzip.GzipFile(fileobj=stream), encoding="utf-8")
            reader = csv.reader(text)
            header = next(reader, None)
            if header is None or tuple(header) != TARDIS_OPTIONS_HEADER:
                raise VenueFetchError(f"Tardis options header mismatch: {header}")
            try:
                for scanned, values in enumerate(reader):
                    if scanned > _MAX_ROWS_SCANNED:
                        raise VenueFetchError(
                            f"Tardis scan exceeded {_MAX_ROWS_SCANNED} rows without reaching the "
                            f"cutoff; the early-stop did not trigger (non-increasing timestamps?)"
                        )
                    if len(values) <= _TS_IDX:
                        continue
                    try:
                        ts_us = int(values[_TS_IDX])
                    except ValueError:
                        continue  # a stray/blank row; the boundary would reject it anyway
                    if ts_us >= as_of_us:
                        reached_as_of = True
                    if ts_us > stop_us:
                        # The file is ordered by local_timestamp and the exchange timestamp is
                        # non-monotonic by ~1s; the 30s grace guarantees every <= as_of quote
                        # was already seen before this fires, so it is safe to stop.
                        break
                    if ts_us > as_of_us:
                        continue  # in the grace zone (after as_of); keep reading, do not include
                    if values[_TYPE_IDX] not in ("put", "call") or not values[
                        _SYM_IDX
                    ].startswith(prefix):
                        continue  # not a matching-currency option (skip futures/perps/other coin)
                    rec = PydanticTardisOptionRow.from_row(values).to_record(currency)
                    if rec.expiry <= as_of:
                        continue  # an already-expired contract still carrying a stale quote
                    prev = snapshot.get(rec.instrument)
                    if prev is None or rec.quote_ts >= prev.quote_ts:
                        # Keep the FRESHEST quote at-or-before as_of (max exchange timestamp),
                        # NOT the file-last, so the pick is independent of the ~1s row disorder.
                        snapshot[rec.instrument] = rec
            except (EOFError, gzip.BadGzipFile) as exc:
                raise VenueFetchError(
                    f"Tardis stream for {snapshot_date} is corrupt or truncated before as_of: "
                    f"{exc}"
                ) from exc
        finally:
            stream.close()

        return self._finalize(
            currency, snapshot_date, as_of, reached_as_of, snapshot, min_instruments
        )

    @staticmethod
    def _finalize(
        currency: DvolCurrency,
        snapshot_date: date,
        as_of: datetime,
        reached_as_of: bool,
        snapshot: dict[str, OptionQuoteRecord],
        min_instruments: int,
    ) -> OptionChainSnapshot:
        """Run the loud completeness checks and return the sorted snapshot."""
        if not reached_as_of:
            raise VenueFetchError(
                f"Tardis file for {snapshot_date} did not cover as_of {as_of} (truncated?)"
            )
        if len(snapshot) < min_instruments:
            raise VenueFetchError(
                f"thin {currency} snapshot at {as_of}: {len(snapshot)} instruments "
                f"(< {min_instruments}); the chain looks truncated"
            )
        quotes = sorted(snapshot.values(), key=lambda r: (r.expiry, r.strike, r.option_type))
        strikes = [float(r.strike) for r in quotes]
        underlyings = sorted(float(r.underlying_price) for r in quotes)
        mid_underlying = underlyings[len(underlyings) // 2]
        if not (min(strikes) < mid_underlying < max(strikes)):
            raise VenueFetchError(
                f"{currency} snapshot strikes [{min(strikes)}, {max(strikes)}] do not bracket "
                f"the underlying {mid_underlying}; the ATM region looks missing"
            )
        return OptionChainSnapshot(
            currency=currency, snapshot_date=snapshot_date, as_of=as_of, quotes=tuple(quotes)
        )
