"""Venue source Protocols (ADR 0002).

The typed surface every venue source implements. Sources return TYPED RECORDS
(not frames); `clock.normalize_funding_frame` / `marks_frame` / `spot_frame` turn
records into the CPCV-ready frames, so normalization lives in exactly one place
and a multi-venue concatenation (the PR3 Binance-vs-OKX delta) composes cleanly.

`fetch_funding` windows are half-open `[start, end)` in UTC. `retention_floor` is
the earliest timestamp the source can actually serve, so the alignment layer can
refuse to silently produce a one-sided short series (the kill-gate retention
invariant).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from riskpremia.data.records import FundingRecord, MarkPriceRecord, SpotPriceRecord, Venue


class FundingSource(Protocol):
    """A source of realized funding for a perpetual instrument."""

    venue: Venue

    def available_months(self, symbol: str) -> tuple[str, ...]:
        """The retrievable `YYYY-MM` periods for `symbol`, sorted ascending."""
        ...

    def fetch_funding(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[FundingRecord]:
        """Realized funding records in `[start, end)` (UTC), unsorted is fine."""
        ...

    def retention_floor(self, symbol: str) -> datetime | None:
        """Earliest funding timestamp the source can serve, or None if unknown."""
        ...


class MarkSource(Protocol):
    """A source of perp MARK prices (funding settles on mark, not trade price)."""

    def fetch_marks(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> list[MarkPriceRecord]:
        """Perp mark-price records at `interval` close in `[start, end)` (UTC)."""
        ...


class SpotSource(Protocol):
    """A source of spot reference closes for the delta-neutral leg and the basis."""

    def fetch_spot(
        self, symbol: str, quote: str, interval: str, start: datetime, end: datetime
    ) -> list[SpotPriceRecord]:
        """Spot close records for a matched-quote product in `[start, end)` (UTC)."""
        ...
