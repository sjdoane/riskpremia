"""US Treasury daily par yield curve source (Study 6, ADR 0008).

The US Treasury publishes the daily par yield curve rates as free, keyless, public-domain
per-year CSV files. The ten-year column is the constant-maturity par yield that FRED also
redistributes as `DGS10`; this is the original source of record, and it is fetched per year
so each response stays small and robust on a throttled connection. The fetch is stdlib-only
(urllib + csv), with an injectable `http_get_text` for deterministic offline testing.

Values are in PERCENT in the file and are converted to decimals here. The available maturity
columns vary by year (early years omit some tenors), so the ten-year column is located by its
header name, never by position. Dates are `M/D/YYYY`.

Reproducibility note: the par yield curve dataset begins in 1990. Like the Kenneth French
factors it is an as-of public source; reproducibility rests on SHA256-stamping the committed
derived series, not on the upstream files being immutable.
"""

from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import attrs

from riskpremia.data.errors import VenueFetchError

_USER_AGENT = "riskpremia cross-asset-trend research (https://github.com/sjdoane/riskpremia)"
_BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv"
_TEN_YEAR_HEADER = "10 Yr"
_DATE_HEADER = "Date"
_PERCENT = Decimal("100")
FIRST_YEAR = 1990


def _year_url(year: int) -> str:
    return (
        f"{_BASE}/{year}/all?type=daily_treasury_yield_curve"
        f"&field_tdr_date_value={year}&page&_format=csv"
    )


@attrs.frozen(slots=True)
class TreasuryParYield:
    """One trading day's ten-year par yield, as a decimal (not percent)."""

    date: date
    ten_year: Decimal


def _parse_date(token: str) -> date:
    month, day, year = (int(part) for part in token.strip().split("/"))
    return date(year, month, day)


def parse_year_csv(text: str, *, year: int) -> list[TreasuryParYield]:
    """Parse one year's par-yield CSV, keeping only the date and the ten-year column."""
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise VenueFetchError(f"Treasury {year}: empty CSV")
    header = [h.strip() for h in rows[0]]
    if _DATE_HEADER not in header or _TEN_YEAR_HEADER not in header:
        raise VenueFetchError(f"Treasury {year}: header missing Date or 10 Yr column: {header}")
    date_index = header.index(_DATE_HEADER)
    ten_index = header.index(_TEN_YEAR_HEADER)
    out: list[TreasuryParYield] = []
    for row in rows[1:]:
        if len(row) <= max(date_index, ten_index):
            continue
        raw_date = row[date_index].strip()
        raw_ten = row[ten_index].strip()
        if not raw_date or not raw_ten:
            continue
        day = _parse_date(raw_date)
        if day.year != year:
            raise VenueFetchError(f"Treasury {year}: row date {day} is outside the requested year")
        try:
            value = Decimal(raw_ten)
        except (ArithmeticError, ValueError) as exc:
            raise VenueFetchError(f"Treasury {day}: cannot parse 10 Yr {raw_ten!r}") from exc
        if value <= 0:
            raise VenueFetchError(f"Treasury {day}: 10 Yr yield must be positive; got {raw_ten!r}")
        out.append(TreasuryParYield(date=day, ten_year=value / _PERCENT))
    if not out:
        raise VenueFetchError(f"Treasury {year}: no ten-year rows parsed")
    out.sort(key=lambda r: r.date)
    return out


class TreasuryParYieldSource:
    """Daily ten-year Treasury par yield history, fetched per year (as-of)."""

    def __init__(
        self,
        *,
        http_get_text: Callable[[str], str] | None = None,
        timeout: float = 60.0,
        max_attempts: int = 4,
        retry_backoff_s: float = 2.0,
    ) -> None:
        self._http_get_text = http_get_text
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._retry_backoff_s = retry_backoff_s

    def _get_text(self, url: str) -> str:
        if self._http_get_text is not None:
            return self._http_get_text(url)
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    return bytes(resp.read()).decode("utf-8", errors="strict")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
                if attempt + 1 < self._max_attempts:
                    time.sleep(self._retry_backoff_s * (attempt + 1))
        raise VenueFetchError(
            f"Treasury fetch failed after {self._max_attempts} attempts: {url}"
        ) from last_error

    def fetch_ten_year(self, start_year: int, end_year: int) -> list[TreasuryParYield]:
        """Ten-year par yields for `[start_year, end_year]`, sorted ascending by date.

        Raises:
          VenueFetchError: on a year before 1990, an unparseable file, a missing ten-year
            column, or a non-positive yield.
        """
        if start_year < FIRST_YEAR:
            raise VenueFetchError(f"Treasury par yields begin in {FIRST_YEAR}; got {start_year}")
        if end_year < start_year:
            raise VenueFetchError(f"end_year {end_year} is before start_year {start_year}")
        out: list[TreasuryParYield] = []
        seen: set[date] = set()
        for year in range(start_year, end_year + 1):
            for record in parse_year_csv(self._get_text(_year_url(year)), year=year):
                if record.date in seen:
                    raise VenueFetchError(f"Treasury: duplicate date {record.date}")
                seen.add(record.date)
                out.append(record)
        out.sort(key=lambda r: r.date)
        return out
