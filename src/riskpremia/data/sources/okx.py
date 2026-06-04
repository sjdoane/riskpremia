"""OKX live funding source: the US-reachable kill-gate venue (ADR 0002).

OKX's public `funding-rate-history` is reachable from a US IP without a key (the
live Binance/Bybit REST APIs are geo-blocked; OKX is not). It is the venue a US
retail trader can actually fund against, so the kill gate and a forward
paper-trade run on OKX-realized funding, while the long-history premium and decay
are measured on the immutable Binance Vision backbone. The Binance-vs-OKX funding
delta (see `data.cross_venue`) measures the venue basis on the overlap so the
Binance-based estimate can be adjusted to what is actually receivable.

Two empirical facts the source is built to (verified live 2026-06-03):
  - retention is RECENT-ONLY: the public history pages back about 93 days (3
    months), then exhausts. OKX is a live/recent source, NOT a long-history one;
    `fetch_funding` returns whatever is available and does not error past the
    floor. This is why the delta is measured on the recent overlap and applied as
    an adjustment, not computed across 2024-2026.
  - the endpoint 403s the default `Python-urllib` User-Agent, so a descriptive
    User-Agent is sent.

Stdlib-only fetch (urllib + json), same zero-third-party-surface property as the
Binance Vision source; an injectable `http_get` and `now_fn` keep it testable and
deterministic.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from riskpremia.data.boundary import PydanticOKXFundingRow
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.records import FundingRecord, InstrumentId, Venue

_USER_AGENT = "riskpremia funding-carry research (https://github.com/sjdoane/riskpremia)"
_OKX_INTERVAL_HOURS = 8
_MAX_PAGES = 60  # safety cap; OKX's ~3-month retention is about 3 pages of 100


class OKXSource:
    """Realized funding from OKX `funding-rate-history` (recent-only)."""

    venue: Venue = "okx"

    def __init__(
        self,
        *,
        base_url: str = "https://www.okx.com",
        now_fn: Callable[[], datetime] | None = None,
        http_get: Callable[[str], dict[str, Any]] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._now = now_fn if now_fn is not None else (lambda: datetime.now(UTC))
        self._http_get = http_get
        self._timeout = timeout

    def _get(self, path: str) -> dict[str, Any]:
        if self._http_get is not None:
            return self._http_get(path)
        req = urllib.request.Request(self._base + path, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.load(resp)
        if not isinstance(data, dict):
            raise VenueFetchError(f"OKX response was not a JSON object: {type(data).__name__}")
        return data

    @staticmethod
    def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data", [])
        if not isinstance(data, list):
            raise VenueFetchError(f"OKX 'data' was not a list: {type(data).__name__}")
        return data

    def fetch_funding(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[FundingRecord]:
        """Realized funding records in `[start, end)` (UTC), recent-only.

        Pages backward via `after=<oldest fundingTime>` until a page predates
        `start` or the history exhausts. Each row passes the boundary realized
        gate (use `realizedRate`, require a settled period strictly before now);
        unsettled rows are dropped, never errored.
        """
        if end <= start:
            raise VenueFetchError(f"fetch_funding requires start < end; got {start}, {end}")
        now_ms = int(self._now().timestamp() * 1000)
        start_ms = int(start.timestamp() * 1000)
        instrument = InstrumentId.of(self.venue, symbol)
        after = int(end.timestamp() * 1000)
        out: list[FundingRecord] = []
        for _ in range(_MAX_PAGES):
            path = (
                f"/api/v5/public/funding-rate-history?instId={symbol}"
                f"&limit=100&after={after}"
            )
            rows = self._rows(self._get(path))
            if not rows:
                break
            funding_times: list[int] = []
            for row in rows:
                parsed = PydanticOKXFundingRow(**row)
                funding_times.append(parsed.fundingTime)
                rec = parsed.to_record(instrument, now_ms, _OKX_INTERVAL_HOURS)
                if rec is not None:
                    out.append(rec)
            oldest = min(funding_times)
            if oldest < start_ms:
                break
            if oldest >= after:  # non-progress guard: avoid a re-fetch loop if the
                break            # endpoint ever returns a boundary-inclusive page
            after = oldest
        return [r for r in out if start <= r.funding_ts < end]

    def available_months(self, symbol: str) -> tuple[str, ...]:
        """The YYYY-MM periods OKX can serve, derived from the recent retention
        window (OKX is cursor-paginated recent-only and has no month-listing API,
        so this spans retention_floor..now, NOT a vendor listing)."""
        floor = self.retention_floor(symbol)
        if floor is None:
            return ()
        now = self._now()
        months: list[str] = []
        y, m = floor.year, floor.month
        while (y, m) <= (now.year, now.month):
            months.append(f"{y:04d}-{m:02d}")
            m += 1
            if m == 13:
                y, m = y + 1, 1
        return tuple(months)

    def retention_floor(self, symbol: str) -> datetime | None:
        """The earliest funding timestamp OKX serves for `symbol`, or None.

        Pages backward to exhaustion (bounded by `_MAX_PAGES`) and returns the
        oldest settled funding instant. On OKX this lands about 3 months back, the
        documented recent-only retention.
        """
        now_ms = int(self._now().timestamp() * 1000)
        after = now_ms
        oldest_seen: int | None = None
        for _ in range(_MAX_PAGES):
            path = (
                f"/api/v5/public/funding-rate-history?instId={symbol}"
                f"&limit=100&after={after}"
            )
            rows = self._rows(self._get(path))
            if not rows:
                break
            funding_times = [PydanticOKXFundingRow(**r).fundingTime for r in rows]
            page_oldest = min(funding_times)
            oldest_seen = page_oldest if oldest_seen is None else min(oldest_seen, page_oldest)
            if page_oldest >= after:  # non-progress guard
                break
            after = page_oldest
        if oldest_seen is None:
            return None
        return datetime.fromtimestamp(oldest_seen / 1000.0, tz=UTC)
