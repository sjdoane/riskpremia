"""Kenneth French Data Library daily factors source (Study 6, ADR 0008).

The daily research factors give the US equity market total return and the one-month
Treasury bill rate as openly-redistributed, public-domain research data back to 1926.
The market total return is `Mkt-RF + RF`; the cash leg earns `RF`; and the equity sleeve's
excess-over-bills return is exactly `Mkt-RF`. The file is a small zipped CSV; the fetch is
stdlib-only (urllib + zipfile + csv), matching the zero-third-party-surface property of the
other sources, with an injectable `open_zip` for deterministic offline testing.

Reproducibility note (load-bearing): the library re-releases the zip monthly and silently
restates the most recent months as the underlying CRSP data finalizes, so this is an as-of
source, not an immutable checksummed dump. Reproducibility rests on SHA256-stamping the
committed derived series into the manifest, not on the upstream zip being stable. Values are
in PERCENT in the file and are converted to decimals here. A missing-data marker
(values at or below -99) is treated as a loud error because the daily factors are complete
across the study window.
"""

from __future__ import annotations

import io
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import attrs

from riskpremia.data.errors import VenueFetchError

_USER_AGENT = "riskpremia cross-asset-trend research (https://github.com/sjdoane/riskpremia)"
_FACTORS_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_daily_CSV.zip"
)
_HEADER_TOKEN = "Mkt-RF"
_MISSING_FLOOR = Decimal("-99")
_PERCENT = Decimal("100")


@attrs.frozen(slots=True)
class KenFrenchDailyFactor:
    """One trading day of the daily research factors, as decimals (not percent)."""

    date: date
    mkt_rf: Decimal
    rf: Decimal

    @property
    def market_total_return(self) -> Decimal:
        """The US equity market total return for the day (`Mkt-RF + RF`)."""
        return self.mkt_rf + self.rf


def _parse_day(token: str) -> date | None:
    if len(token) != 8 or not token.isdigit():
        return None
    return date(int(token[:4]), int(token[4:6]), int(token[6:8]))


def _decimal(text: str, *, field: str, day: str) -> Decimal:
    try:
        value = Decimal(text.strip())
    except (ArithmeticError, ValueError) as exc:
        raise VenueFetchError(f"Ken French {day}: cannot parse {field} {text!r}") from exc
    if value <= _MISSING_FLOOR:
        raise VenueFetchError(f"Ken French {day}: {field} is a missing-data marker {text!r}")
    return value / _PERCENT


def parse_daily_factors(text: str) -> list[KenFrenchDailyFactor]:
    """Parse the daily factor CSV text into decimal factor records.

    The file has a free-text preamble, then a header row containing `Mkt-RF`, then
    rows of `YYYYMMDD, Mkt-RF, SMB, HML, RF` (percent, whitespace-padded), then a
    trailing copyright line. Only the eight-digit-dated rows are kept.
    """
    lines = text.splitlines()
    header_index = next(
        (i for i, line in enumerate(lines) if _HEADER_TOKEN in line and "RF" in line), None
    )
    if header_index is None:
        raise VenueFetchError("Ken French daily factors: header row not found")
    out: list[KenFrenchDailyFactor] = []
    seen: set[date] = set()
    for line in lines[header_index + 1 :]:
        fields = [f.strip() for f in line.split(",")]
        if len(fields) < 5:
            continue
        day = _parse_day(fields[0])
        if day is None:
            continue
        if day in seen:
            raise VenueFetchError(f"Ken French daily factors: duplicate date {day}")
        seen.add(day)
        out.append(
            KenFrenchDailyFactor(
                date=day,
                mkt_rf=_decimal(fields[1], field="Mkt-RF", day=fields[0]),
                rf=_decimal(fields[4], field="RF", day=fields[0]),
            )
        )
    if not out:
        raise VenueFetchError("Ken French daily factors: no dated rows parsed")
    out.sort(key=lambda r: r.date)
    return out


class KenFrenchSource:
    """Daily US equity market total return and the one-month bill rate (as-of)."""

    def __init__(
        self,
        *,
        url: str = _FACTORS_URL,
        open_zip: Callable[[str], bytes] | None = None,
        timeout: float = 60.0,
        max_attempts: int = 4,
        retry_backoff_s: float = 2.0,
    ) -> None:
        self._url = url
        self._open_zip = open_zip
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._retry_backoff_s = retry_backoff_s

    def _fetch_zip_bytes(self) -> bytes:
        if self._open_zip is not None:
            return self._open_zip(self._url)
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                req = urllib.request.Request(self._url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    return bytes(resp.read())
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
                if attempt + 1 < self._max_attempts:
                    time.sleep(self._retry_backoff_s * (attempt + 1))
        raise VenueFetchError(
            f"Ken French fetch failed after {self._max_attempts} attempts"
        ) from last_error

    def fetch_daily_factors(self) -> list[KenFrenchDailyFactor]:
        """Fetch and parse the daily research factors, sorted ascending by date.

        Raises:
          VenueFetchError: on an unreadable zip, a missing CSV member, or a file that
            parses to zero dated rows or carries a missing-data marker.
        """
        raw = self._fetch_zip_bytes()
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise VenueFetchError("Ken French response was not a valid zip") from exc
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise VenueFetchError("Ken French zip has no CSV member")
        text = archive.read(sorted(names)[0]).decode("utf-8", errors="strict")
        return parse_daily_factors(text)
