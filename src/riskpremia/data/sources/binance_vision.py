"""Binance Vision source: the long-history reproducible backbone (ADR 0002).

Stdlib-only (urllib + zipfile + hashlib + xml.etree + csv), so the reproducible
path has zero third-party surface. Fetches the public, immutable monthly dumps
that Binance publishes to S3 with a sibling `.CHECKSUM`, verifies every download
against the published SHA256, and caches by content (an idempotent re-fetch
re-verifies rather than re-downloading). The live Binance REST API is geo-blocked
from US IPs, but these S3 dumps are not (the week-1 spike confirmed this), so this
is the source a US-based reviewer regenerates the headline from.

Three datasets, all monthly zips:
  - funding:     data/futures/um/monthly/fundingRate/<SYM>/<SYM>-fundingRate-YYYY-MM.zip
  - perp MARK:   data/futures/um/monthly/markPriceKlines/<SYM>/<INT>/<SYM>-<INT>-YYYY-MM.zip
  - spot ref:    data/spot/monthly/klines/<SYM>/<INT>/<SYM>-<INT>-YYYY-MM.zip
The MARK dataset (not the trade-price klines) is used for the perp leg because
funding settles on the mark/index, not the last trade (design review finding C3).

Survivorship caveat (finding C4): the S3 listing only contains symbols that still
exist, so a cross-sectional median over "all coins" would be survivorship-inflated.
The v1 headline universe is therefore the pre-committed survivor set
`SURVIVOR_UNIVERSE`, and `available_months` cannot detect a symbol that never
appears. ADR 0002 and the methodology doc carry this caveat at the point the
premium is computed.
"""

from __future__ import annotations

import csv
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path

from riskpremia.data.boundary import BINANCE_FUNDING_HEADER, BinanceFundingRow
from riskpremia.data.clock import ms_to_utc
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.manifest import parse_checksum_line, verify_sha256
from riskpremia.data.records import (
    FundingRecord,
    InstrumentId,
    MarkPriceRecord,
    SpotKlineRecord,
    SpotPriceRecord,
    Venue,
)

SURVIVOR_UNIVERSE: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
"""The pre-committed v1 headline universe (finding C4). Restricted to liquid
survivors where survivorship bias on the funding premium is economically
negligible; a multi-coin median is deliberately NOT computed."""

_BASE_URL = "https://data.binance.vision"
_S3_LIST_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
_S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
_KLINE_CLOSE_IDX = 4
_KLINE_CLOSE_TIME_IDX = 6
_KLINE_QUOTE_VOLUME_IDX = 7  # "quote asset volume" = the USD(T) dollar volume directly

# Binance Vision kline dumps switched their open_time / close_time from epoch
# MILLISECONDS (13-digit) to epoch MICROSECONDS (16-digit) in the late-2024 monthly
# files, while the fundingRate dumps stayed in milliseconds. The kline parser
# normalizes to ms so the millisecond-strict `ms_to_utc` chokepoint is unchanged.
_KLINE_MS_LOW = 1_000_000_000_000  # 1e12: 13-digit epoch ms (about 2001-09 onward)
_KLINE_MS_HIGH = 10_000_000_000_000  # 1e13: upper bound of 13-digit ms (about 2286)
_KLINE_US_LOW = 1_000_000_000_000_000  # 1e15: 16-digit epoch us
_KLINE_US_HIGH = 10_000_000_000_000_000  # 1e16: upper bound of 16-digit us


def _kline_close_time_to_ms(raw: int) -> int:
    """Normalize a Binance Vision kline close_time to epoch milliseconds.

    Accepts the 13-digit millisecond stamp (older dumps) and the 16-digit
    microsecond stamp (late-2024 onward), converting microseconds by integer
    division. Anything else (a seconds stamp or a malformed value) raises rather
    than silently mis-scaling the price-leg timestamp.

    Raises:
      VenueFetchError: when `raw` is neither a 13-digit ms nor a 16-digit us epoch.
    """
    if _KLINE_MS_LOW <= raw < _KLINE_MS_HIGH:
        return raw
    if _KLINE_US_LOW <= raw < _KLINE_US_HIGH:
        return raw // 1000
    raise VenueFetchError(
        f"kline close_time {raw} is neither a 13-digit epoch-ms nor a 16-digit epoch-us "
        f"value; Binance Vision klines are ms before about 2024-12 and us after"
    )


def _month_strings(start: datetime, end: datetime) -> list[str]:
    """The `YYYY-MM` periods overlapping the half-open window `[start, end)`."""
    if end <= start:
        raise VenueFetchError(f"_month_strings requires start < end; got {start}, {end}")
    months: list[str] = []
    y, m = start.year, start.month
    # iterate inclusive of the month containing the last instant before `end`
    last = end - timedelta(microseconds=1)
    while (y, m) <= (last.year, last.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return months


class BinanceVisionSource:
    """Funding + mark + spot from the Binance Vision S3 dumps."""

    venue: Venue = "binance_vision"

    def __init__(
        self,
        raw_root: Path,
        *,
        base_url: str = _BASE_URL,
        s3_list_url: str = _S3_LIST_URL,
        timeout: float = 30.0,
        max_fetch_attempts: int = 1,
        retry_backoff_s: float = 0.0,
    ) -> None:
        self._raw_root = raw_root
        self._base_url = base_url.rstrip("/")
        self._s3_list_url = s3_list_url.rstrip("/")
        self._timeout = timeout
        # Retry is OFF by default (max_fetch_attempts=1) so the single-symbol funding/mark/
        # spot paths and their unit tests are byte-for-byte unchanged. The multi-symbol
        # universe build (scripts/build_ctrend_universe.py) opts into a few attempts with a
        # linear backoff so a transient S3 reset over ~30k requests does not abort the run
        # (design review M2). Retry covers only network errors, never a checksum mismatch.
        if max_fetch_attempts < 1:
            raise VenueFetchError(f"max_fetch_attempts must be >= 1; got {max_fetch_attempts}")
        self._max_fetch_attempts = max_fetch_attempts
        self._retry_backoff_s = retry_backoff_s

    # ----- S3 listing -------------------------------------------------------

    def _list_keys(self, prefix: str) -> list[str]:
        """All object keys under `prefix`, following S3 marker pagination, sorted."""
        keys: list[str] = []
        marker = ""
        while True:
            url = f"{self._s3_list_url}?prefix={prefix}&max-keys=1000"
            if marker:
                url += f"&marker={marker}"
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                root = ET.fromstring(resp.read())
            page = [
                key.text
                for c in root.findall(f"{_S3_NS}Contents")
                if (key := c.find(f"{_S3_NS}Key")) is not None and key.text is not None
            ]
            keys.extend(page)
            truncated = root.find(f"{_S3_NS}IsTruncated")
            if truncated is None or truncated.text != "true" or not page:
                break
            marker = page[-1]
        return sorted(keys)

    def available_months(self, symbol: str) -> tuple[str, ...]:
        """The `YYYY-MM` periods with a published funding dump for `symbol`."""
        prefix = f"data/futures/um/monthly/fundingRate/{symbol}/"
        suffix = ".zip"
        months: list[str] = []
        for key in self._list_keys(prefix):
            name = key.rsplit("/", 1)[-1]
            if name.endswith(suffix):  # ".zip" only; a ".zip.CHECKSUM" name does not end in ".zip"
                # <SYM>-fundingRate-YYYY-MM.zip
                stem = name[: -len(suffix)]
                months.append(stem.rsplit("-", 2)[-2] + "-" + stem.rsplit("-", 2)[-1])
        return tuple(sorted(set(months)))

    def retention_floor(self, symbol: str) -> datetime | None:
        """The start of the earliest available funding month, or None if absent."""
        months = self.available_months(symbol)
        if not months:
            return None
        y, m = (int(p) for p in months[0].split("-"))
        return datetime(y, m, 1, tzinfo=UTC)

    # ----- download + verify ------------------------------------------------

    def _urlopen_retry(self, url: str) -> bytes:
        """GET `url`, retrying only on transient network errors (design review M2).

        With the default `max_fetch_attempts=1` this is a single `urlopen` (the prior
        behaviour). The universe build raises it to a few attempts with a linear backoff
        so one transient reset over ~30k requests does not abort the run. A non-network
        failure (e.g. a malformed XML downstream) is not caught here; a checksum mismatch
        is handled by the caller (delete + re-fetch), not by this retry.
        """
        last: Exception | None = None
        for attempt in range(self._max_fetch_attempts):
            try:
                with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                    data: bytes = resp.read()
                    return data
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                if attempt + 1 < self._max_fetch_attempts and self._retry_backoff_s > 0:
                    time.sleep(self._retry_backoff_s * (attempt + 1))
        assert last is not None  # the loop runs >= 1 time, so a failure set `last`
        raise last

    def _fetch_to(self, url: str, dest: Path) -> Path:
        """Download `url` to `dest` if absent; return `dest`."""
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self._urlopen_retry(url))
        return dest

    def _list_common_prefixes(self, prefix: str) -> list[str]:
        """The immediate sub-prefixes under `prefix` (S3 delimiter listing), sorted.

        Used to enumerate symbol directories without listing every object. Follows the
        same marker pagination as `_list_keys` but reads `CommonPrefixes` (one per
        sub-directory) under `delimiter=/`.
        """
        out: list[str] = []
        marker = ""
        while True:
            url = f"{self._s3_list_url}?prefix={prefix}&delimiter=/&max-keys=1000"
            if marker:
                url += f"&marker={marker}"
            root = ET.fromstring(self._urlopen_retry(url))
            page = [
                cp.text
                for c in root.findall(f"{_S3_NS}CommonPrefixes")
                if (cp := c.find(f"{_S3_NS}Prefix")) is not None and cp.text is not None
            ]
            out.extend(page)
            truncated = root.find(f"{_S3_NS}IsTruncated")
            if truncated is None or truncated.text != "true" or not page:
                break
            nextmarker = root.find(f"{_S3_NS}NextMarker")
            marker = nextmarker.text if nextmarker is not None and nextmarker.text else page[-1]
            if not marker:
                break
        return sorted(out)

    def _download_and_verify(self, key: str, relpath: str) -> Path:
        """Download `<key>` and its `.CHECKSUM`, verify SHA256, content-cache.

        Idempotent: a cached zip whose hash still matches the published checksum
        is reused; a drifted cache is re-downloaded.
        """
        dest = self._raw_root / relpath
        checksum_dest = dest.with_name(dest.name + ".CHECKSUM")
        self._fetch_to(f"{self._base_url}/{key}.CHECKSUM", checksum_dest)
        expected_sha, checksum_name = parse_checksum_line(checksum_dest.read_text(encoding="utf-8"))
        if checksum_name != dest.name:
            raise VenueFetchError(
                f"{checksum_dest.name} refers to {checksum_name!r}, not {dest.name!r}"
            )
        if dest.exists():
            try:
                verify_sha256(dest, expected_sha)
                return dest
            except Exception:
                dest.unlink()
        self._fetch_to(f"{self._base_url}/{key}", dest)
        verify_sha256(dest, expected_sha)
        return dest

    # ----- parsing ----------------------------------------------------------

    @staticmethod
    def _read_single_member(path: Path) -> str:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if len(names) != 1:
                raise VenueFetchError(f"{path.name}: expected one CSV member, got {names}")
            return zf.read(names[0]).decode("utf-8")

    def _parse_funding_zip(self, path: Path, instrument: InstrumentId) -> list[FundingRecord]:
        rows = list(csv.reader(StringIO(self._read_single_member(path))))
        if not rows or tuple(rows[0]) != BINANCE_FUNDING_HEADER:
            raise VenueFetchError(
                f"{path.name}: header {rows[0] if rows else None} != {BINANCE_FUNDING_HEADER}"
            )
        out: list[FundingRecord] = []
        for r in rows[1:]:
            row = BinanceFundingRow(
                calc_time=int(r[0]),
                funding_interval_hours=int(r[1]),
                last_funding_rate=Decimal(r[2]),
            )
            out.append(row.to_record(instrument))
        return out

    def _parse_kline_zip(self, path: Path) -> list[tuple[int, Decimal, Decimal]]:
        """Return (close_time_ms, close, quote_volume) for each kline row (header tolerated).

        `quote_volume` is the kline "quote asset volume" (column 7), the USD(T)-denominated
        dollar volume the CTREND universe ranks on. The price-only callers (`fetch_marks`,
        `fetch_spot`) discard it by unpacking `(_ms, close, _qv)`; only `fetch_spot_klines`
        keeps it.
        """
        out: list[tuple[int, Decimal, Decimal]] = []
        for r in csv.reader(StringIO(self._read_single_member(path))):
            if not r or not r[0].lstrip("-").isdigit():
                continue  # skip a header row (newer Binance Vision klines carry one)
            close_ms = _kline_close_time_to_ms(int(r[_KLINE_CLOSE_TIME_IDX]))
            out.append(
                (close_ms, Decimal(r[_KLINE_CLOSE_IDX]), Decimal(r[_KLINE_QUOTE_VOLUME_IDX]))
            )
        return out

    # ----- public fetch -----------------------------------------------------

    def fetch_funding(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[FundingRecord]:
        instrument = InstrumentId.of(self.venue, symbol)
        out: list[FundingRecord] = []
        for month in _month_strings(start, end):
            key = f"data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
            relpath = f"binance_vision/{symbol}/{symbol}-fundingRate-{month}.zip"
            path = self._download_and_verify(key, relpath)
            out.extend(self._parse_funding_zip(path, instrument))
        return [r for r in out if start <= r.funding_ts < end]

    def fetch_marks(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> list[MarkPriceRecord]:
        instrument = InstrumentId.of(self.venue, symbol)
        out: list[MarkPriceRecord] = []
        for month in _month_strings(start, end):
            key = (
                f"data/futures/um/monthly/markPriceKlines/{symbol}/{interval}/"
                f"{symbol}-{interval}-{month}.zip"
            )
            relpath = f"binance_vision/{symbol}/marks/{symbol}-{interval}-{month}.zip"
            path = self._download_and_verify(key, relpath)
            for close_time_ms, close, _qv in self._parse_kline_zip(path):
                out.append(
                    MarkPriceRecord(
                        instrument=instrument,
                        period_end_ts=ms_to_utc(close_time_ms),
                        mark_close=close,
                    )
                )
        return [r for r in out if start <= r.period_end_ts < end]

    def fetch_spot(
        self, symbol: str, quote: str, interval: str, start: datetime, end: datetime
    ) -> list[SpotPriceRecord]:
        out: list[SpotPriceRecord] = []
        for month in _month_strings(start, end):
            key = f"data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
            relpath = f"binance_vision/{symbol}/spot/{symbol}-{interval}-{month}.zip"
            path = self._download_and_verify(key, relpath)
            for close_time_ms, close, _qv in self._parse_kline_zip(path):
                out.append(
                    SpotPriceRecord(
                        spot_venue="binance_spot",
                        spot_symbol=symbol,
                        quote=quote,
                        period_end_ts=ms_to_utc(close_time_ms),
                        close=close,
                    )
                )
        return [r for r in out if start <= r.period_end_ts < end]

    # ----- multi-coin universe (CTREND Study 3, PR1) ------------------------

    def list_spot_symbols(self, quote: str = "USDT") -> tuple[str, ...]:
        """Every spot symbol ending in `quote`, enumerated from the S3 bucket, sorted.

        Delisting-complete: the bucket retains the directories of symbols that have since
        been delisted (the listing is of stored objects, not the live API), so the
        returned set includes dead coins (the survivorship-safe universe source for ADR
        0005). A `quote` suffix match keeps only the matched-quote pairs (the dominant
        liquid quote is USDT); a name equal to the quote (a malformed prefix) is excluded.
        """
        prefixes = self._list_common_prefixes("data/spot/monthly/klines/")
        symbols = {
            name
            for p in prefixes
            if (name := p.rstrip("/").rsplit("/", 1)[-1]).endswith(quote) and len(name) > len(quote)
        }
        return tuple(sorted(symbols))

    def fetch_spot_klines(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> list[SpotKlineRecord]:
        """Spot klines (close + quote/dollar volume) for `symbol` at `interval` in [start, end).

        The CTREND universe source method (ADR 0005): reads the close (column 4) and the
        quote-asset volume (column 7, the USD(T) dollar volume) from each month's
        checksum-verified spot-kline zip, stamped on the close time. `interval` is
        typically "1d" (the daily bars the 28 technical signals are computed on).

        Only months with a published dump are fetched (the window is intersected with
        `available_spot_months`), so a delisted symbol whose life ends inside the window
        does not 404 on the post-delisting months (delisting-robust, ADR 0005 caveat 4).
        """
        instrument = InstrumentId.of(self.venue, symbol)
        wanted = set(_month_strings(start, end))
        available = set(self.available_spot_months(symbol, interval))
        out: list[SpotKlineRecord] = []
        for month in sorted(wanted & available):
            key = f"data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
            relpath = f"binance_vision/{symbol}/spot/{symbol}-{interval}-{month}.zip"
            path = self._download_and_verify(key, relpath)
            for close_time_ms, close, quote_volume in self._parse_kline_zip(path):
                out.append(
                    SpotKlineRecord(
                        instrument=instrument,
                        period_end_ts=ms_to_utc(close_time_ms),
                        close=close,
                        quote_volume=quote_volume,
                    )
                )
        return [r for r in out if start <= r.period_end_ts < end]

    def available_spot_months(self, symbol: str, interval: str) -> tuple[str, ...]:
        """The `YYYY-MM` periods with a published spot-kline zip for `(symbol, interval)`.

        Lets the universe build skip a month with no dump rather than 404 on it (a
        just-listed or already-delisted symbol has a bounded month range).
        """
        prefix = f"data/spot/monthly/klines/{symbol}/{interval}/"
        suffix = ".zip"
        months: list[str] = []
        for key in self._list_keys(prefix):
            name = key.rsplit("/", 1)[-1]
            if name.endswith(suffix):
                stem = name[: -len(suffix)]
                months.append(stem.rsplit("-", 2)[-2] + "-" + stem.rsplit("-", 2)[-1])
        return tuple(sorted(set(months)))
