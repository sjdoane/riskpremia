"""Deribit DVOL implied-volatility index source (ADR 0004, the VRP study).

The DVOL index is the model-free, 30-day, 365-annualized implied volatility Deribit
publishes from its BTC/ETH option strip (the variance-swap methodology, VIX-style).
`public/get_volatility_index_data` is reachable from a US IP without a key (verified
2026-06-04), so it is the reproducible implied-variance input; the realized leg comes
from the immutable Binance Vision klines.

Reproducibility note (load-bearing): unlike the Binance Vision dumps (immutable,
checksummed S3 objects), DVOL is a LIVE, as-of, potentially-revisable series with no
published `.CHECKSUM`. Reproducibility therefore rests on SHA256-stamping a fetched
snapshot into the manifest (the `manifest.py` machinery), NOT on the API being
stable; the headline pins to that snapshot. A small committed CSV mirror is the
offline CI fixture.

Stdlib-only fetch (urllib + json), the same zero-third-party-surface property as the
OKX and Binance Vision sources; an injectable `http_get` and `now_fn` keep it
testable and deterministic. The response pages via a `continuation` token, handled
with the same bounded + non-progress-guarded loop as `okx.py`.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from riskpremia.data.boundary import PydanticDeribitDvolRow
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.records import DvolCurrency, DvolRecord, Venue

_USER_AGENT = "riskpremia variance-risk-premium research (https://github.com/sjdoane/riskpremia)"
# The endpoint caps a response at about 1000 points (and returns the MOST RECENT
# points within the requested range, silently dropping the earlier tail), so the
# range is fetched in deterministic sub-windows kept under the cap, rather than
# relying on the `continuation` cursor semantics. Resolution values are seconds
# (1, 60, 3600, 43200) or the literal "1D"; the per-point span sizes the window.
_VALID_RESOLUTIONS = ("1", "60", "3600", "43200", "1D")
_MS_PER_POINT = {
    "1": 1_000,
    "60": 60_000,
    "3600": 3_600_000,
    "43200": 43_200_000,
    "1D": 86_400_000,
}
_MAX_POINTS_PER_REQUEST = 900  # under the ~1000 cap with headroom
_MAX_REQUESTS = 2_000  # safety bound on the chunk loop


class DeribitDVOLSource:
    """Daily DVOL implied-vol index history from Deribit (live / as-of)."""

    venue: Venue = "deribit"

    def __init__(
        self,
        *,
        base_url: str = "https://www.deribit.com",
        now_fn: Callable[[], datetime] | None = None,
        http_get: Callable[[str], dict[str, Any]] | None = None,
        timeout: float = 30.0,
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
            raise VenueFetchError(f"Deribit response was not a JSON object: {type(data).__name__}")
        return data

    def fetch_dvol(
        self,
        currency: DvolCurrency,
        start: datetime,
        end: datetime,
        *,
        resolution: str = "1D",
    ) -> list[DvolRecord]:
        """DVOL records in `[start, end)` (UTC), sorted ascending and deduped on `ts`.

        Fetches the range in deterministic sub-windows kept under the endpoint's
        ~1000-point cap (the cap silently drops the earlier tail of a too-wide
        request), deduping the boundary-shared points. Each row passes the boundary
        model (`PydanticDeribitDvolRow`); the resolution defaults to daily.

        Raises:
          VenueFetchError: on `end <= start`, an unknown resolution, a malformed
            response, or a row that fails the boundary shape/positivity checks.
        """
        if end <= start:
            raise VenueFetchError(f"fetch_dvol requires start < end; got {start}, {end}")
        if resolution not in _VALID_RESOLUTIONS:
            raise VenueFetchError(
                f"fetch_dvol resolution must be one of {_VALID_RESOLUTIONS}; got {resolution!r}"
            )
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        span = _MAX_POINTS_PER_REQUEST * _MS_PER_POINT[resolution]

        by_ts: dict[int, DvolRecord] = {}
        cursor = start_ms
        for _ in range(_MAX_REQUESTS):
            if cursor >= end_ms:
                break
            chunk_end = min(cursor + span, end_ms)
            path = (
                f"/api/v2/public/get_volatility_index_data?currency={currency}"
                f"&start_timestamp={cursor}&end_timestamp={chunk_end}&resolution={resolution}"
            )
            result = self._get(path).get("result")
            if not isinstance(result, dict):
                raise VenueFetchError("Deribit DVOL response missing a 'result' object")
            rows = result.get("data", [])
            if not isinstance(rows, list):
                raise VenueFetchError(f"Deribit DVOL 'data' was not a list: {type(rows).__name__}")
            for row in rows:
                rec = PydanticDeribitDvolRow.from_array(row).to_record(currency)
                by_ts[int(rec.ts.timestamp() * 1000)] = rec  # dedup the shared boundary point
            cursor = chunk_end

        records = sorted(by_ts.values(), key=lambda r: r.ts)
        return [r for r in records if start <= r.ts < end]
