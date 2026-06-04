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
    ) -> None:
        self._raw_root = raw_root
        self._base_url = base_url.rstrip("/")
        self._s3_list_url = s3_list_url.rstrip("/")
        self._timeout = timeout

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

    def _fetch_to(self, url: str, dest: Path) -> Path:
        """Download `url` to `dest` if absent; return `dest`."""
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                dest.write_bytes(resp.read())
        return dest

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

    def _parse_kline_zip(self, path: Path) -> list[tuple[int, Decimal]]:
        """Return (close_time_ms, close) for each kline row (header tolerated)."""
        out: list[tuple[int, Decimal]] = []
        for r in csv.reader(StringIO(self._read_single_member(path))):
            if not r or not r[0].lstrip("-").isdigit():
                continue  # skip a header row (newer Binance Vision klines carry one)
            close_ms = _kline_close_time_to_ms(int(r[_KLINE_CLOSE_TIME_IDX]))
            out.append((close_ms, Decimal(r[_KLINE_CLOSE_IDX])))
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
            for close_time_ms, close in self._parse_kline_zip(path):
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
            for close_time_ms, close in self._parse_kline_zip(path):
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
