"""Committed CSV fixtures for the VRP measurement (ADR 0004 PR5b).

The reproducibility anchor for Layer i. DVOL is a LIVE / as-of / revisable series
with no published checksum (unlike the immutable, checksummed Binance Vision dumps),
so a re-fetch is NOT guaranteed byte-identical and reproducibility cannot rest on
"re-fetch and verify". Instead the exact daily closes used for the committed headline
are written to small CSV fixtures that ARE committed, and their SHA256 is stamped into
`data/snapshots/manifest.toml` so the fixture is tamper-evident from a clone. The
committed JSON artifact is then a pure function of these two fixtures, and an offline
test rebuilds the headline from them (see `tests/unit`).

Two fixtures, both `date,<close>` daily series sorted ascending:
  - the DVOL implied-vol index close (the implied leg);
  - the Binance Vision spot close (the realized leg), a derived daily-close extract
    of the public spot klines (symbol/interval/range recorded in the manifest entry).

Determinism: written with explicit LF newlines (`.gitattributes` pins `*.csv eol=lf`)
and the exact `Decimal` string of each close, so `read -> build -> headline` reproduces
the committed numbers bit-for-bit across a Windows build and a Linux CI checkout. The
DVOL reader rebuilds each `DvolRecord` THROUGH the `PydanticDeribitDvolRow` boundary
model so the positivity / consistency guards still fire on the reproduction path (a
corrupted fixture raises rather than silently producing a wrong implied variance).
Stdlib only (csv).
"""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path

from riskpremia.data.boundary import PydanticDeribitDvolRow
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.records import DvolCurrency, DvolRecord, SpotPriceRecord

_DVOL_HEADER = ("date", "dvol_close")
_SPOT_HEADER = ("date", "close")


def _date_to_ms(d: date) -> int:
    """Midnight-UTC epoch milliseconds for a calendar date (the daily anchor).

    Only the date is consumed downstream (`build_vrp_frame` reads `ts.date()`), so a
    midnight-UTC instant is a faithful, stable reconstruction of the daily stamp.
    """
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000)


def _write_csv(path: Path, header: tuple[str, str], rows: list[tuple[str, str]]) -> None:
    """Write `header` + `rows` as a deterministic LF CSV (no trailing CR)."""
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue(), encoding="utf-8", newline="\n")


def _read_csv(path: Path, header: tuple[str, str]) -> list[tuple[str, str]]:
    """Read a `date,<value>` CSV, asserting the header and a 2-column shape."""
    rows = list(csv.reader(StringIO(path.read_text(encoding="utf-8"))))
    if not rows or tuple(rows[0]) != header:
        raise VenueFetchError(
            f"{path.name}: header {rows[0] if rows else None} != {list(header)}"
        )
    out: list[tuple[str, str]] = []
    for r in rows[1:]:
        if not r:
            continue  # tolerate a trailing blank line
        if len(r) != 2:
            raise VenueFetchError(f"{path.name}: expected 2 columns, got {r!r}")
        out.append((r[0], r[1]))
    return out


def write_dvol_csv(path: Path, dvol: list[DvolRecord]) -> None:
    """Write the DVOL close fixture (`date,dvol_close`), sorted, one row per date.

    Raises:
      VenueFetchError: on an empty input or a duplicate calendar date (the fixture is
        a daily measurement anchor; a duplicate date would mean a non-daily series).
    """
    if not dvol:
        raise VenueFetchError("write_dvol_csv requires at least one DVOL record")
    by_date = sorted(dvol, key=lambda r: r.ts)
    seen: set[date] = set()
    rows: list[tuple[str, str]] = []
    for rec in by_date:
        d = rec.ts.date()
        if d in seen:
            raise VenueFetchError(f"write_dvol_csv got a duplicate date {d.isoformat()}")
        seen.add(d)
        rows.append((d.isoformat(), str(rec.close)))
    _write_csv(path, _DVOL_HEADER, rows)


def read_dvol_csv(path: Path, *, currency: DvolCurrency = "BTC") -> list[DvolRecord]:
    """Read the DVOL fixture back into `DvolRecord`s, sorted ascending by date.

    Each row is rebuilt THROUGH the `PydanticDeribitDvolRow` boundary (with `o=h=l=c`,
    the only field the measurement consumes), so the positivity / consistency guards
    still fire; a corrupted fixture (a non-positive close) raises `VenueFetchError`
    rather than flowing a wrong implied variance into the headline.
    """
    records: list[DvolRecord] = []
    for date_str, close_str in _read_csv(path, _DVOL_HEADER):
        d = date.fromisoformat(date_str)
        ts_ms = _date_to_ms(d)
        records.append(
            PydanticDeribitDvolRow.from_array(
                [ts_ms, close_str, close_str, close_str, close_str]
            ).to_record(currency)
        )
    records.sort(key=lambda r: r.ts)
    return records


def write_spot_csv(path: Path, spot: list[SpotPriceRecord]) -> None:
    """Write the spot close fixture (`date,close`), sorted, one row per date.

    Raises:
      VenueFetchError: on an empty input or a duplicate calendar date.
    """
    if not spot:
        raise VenueFetchError("write_spot_csv requires at least one spot record")
    by_date = sorted(spot, key=lambda r: r.period_end_ts)
    seen: set[date] = set()
    rows: list[tuple[str, str]] = []
    for rec in by_date:
        d = rec.period_end_ts.date()
        if d in seen:
            raise VenueFetchError(f"write_spot_csv got a duplicate date {d.isoformat()}")
        seen.add(d)
        rows.append((d.isoformat(), str(rec.close)))
    _write_csv(path, _SPOT_HEADER, rows)


def read_spot_csv(
    path: Path, *, symbol: str = "BTCUSDT", quote: str = "USDT"
) -> list[SpotPriceRecord]:
    """Read the spot fixture back into `SpotPriceRecord`s, sorted ascending by date.

    Mirrors how `binance_vision.fetch_spot` constructs the record (spot_venue
    `binance_spot`, the matched `quote`); the period-end is the midnight-UTC anchor of
    the date, the only granularity the measurement consumes.

    Raises:
      VenueFetchError: on a non-positive close (a corrupted fixture).
    """
    records: list[SpotPriceRecord] = []
    for date_str, close_str in _read_csv(path, _SPOT_HEADER):
        close = Decimal(close_str)
        if close <= 0:
            raise VenueFetchError(f"spot close must be positive; got {close} in {path.name}")
        d = date.fromisoformat(date_str)
        records.append(
            SpotPriceRecord(
                spot_venue="binance_spot",
                spot_symbol=symbol,
                quote=quote,
                period_end_ts=datetime(d.year, d.month, d.day, tzinfo=UTC),
                close=close,
            )
        )
    records.sort(key=lambda r: r.period_end_ts)
    return records
