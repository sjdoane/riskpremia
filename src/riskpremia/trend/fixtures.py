"""Committed BTC/ETH daily OHLC fixtures for Study 4.

The fixture is a small, committed, tamper-evident extract of Binance Vision spot daily
klines. It stores only what the BTC/ETH trend gate consumes: date, symbol, open, close.
The signal is formed after the Sunday close and the trade fills at the next Monday open,
so `open` is load-bearing. The raw monthly zips remain in the gitignored cache and carry
published checksums; `btc_eth_daily_ohlc_sources.json` records the source zip hashes used
to build this fixture.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any

import attrs
import polars as pl

from riskpremia.trend.errors import TrendError

_BAR_HEADER: tuple[str, ...] = ("date", "symbol", "open", "close")
_BAR_SCHEMA = {"date": pl.Date, "symbol": pl.Utf8, "open": pl.Float64, "close": pl.Float64}
_SOURCE_SCHEMA_VERSION = 1


@attrs.frozen(slots=True)
class TrendDailyBar:
    """One daily spot bar in the committed Study 4 fixture."""

    date: date
    symbol: str
    open: Decimal
    close: Decimal


@attrs.frozen(slots=True)
class SourceFile:
    """One Binance Vision monthly zip used to build the fixture."""

    symbol: str
    month: str
    relpath: str
    file_sha256: str
    published_checksum: str


def _scalar_float(value: Any, *, column: str) -> float:
    if value is None:
        raise TrendError(f"{column}: expected a scalar float, got None")
    if not isinstance(value, int | float | Decimal):
        raise TrendError(f"{column}: expected a numeric scalar, got {type(value).__name__}")
    return float(value)


def _fmt_decimal(value: Decimal) -> str:
    return f"{value.normalize():f}"


def bars_csv_text(bars: Sequence[TrendDailyBar]) -> str:
    """Deterministic LF CSV text for the committed BTC/ETH bars."""
    if not bars:
        raise TrendError("bars_csv_text requires at least one bar")
    seen: set[tuple[str, date]] = set()
    for bar in bars:
        if not bar.symbol.strip():
            raise TrendError("TrendDailyBar requires a non-empty symbol")
        if bar.open <= 0 or bar.close <= 0:
            raise TrendError(
                f"{bar.symbol} {bar.date}: open and close must be positive; "
                f"open={bar.open} close={bar.close}"
            )
        key = (bar.symbol, bar.date)
        if key in seen:
            raise TrendError(f"duplicate bar for {bar.symbol} {bar.date}")
        seen.add(key)
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_BAR_HEADER)
    for bar in sorted(bars, key=lambda b: (b.symbol, b.date)):
        writer.writerow(
            [
                bar.date.isoformat(),
                bar.symbol,
                _fmt_decimal(bar.open),
                _fmt_decimal(bar.close),
            ]
        )
    return buf.getvalue()


def write_bars_csv(path: Path, bars: Sequence[TrendDailyBar]) -> None:
    """Write the committed bar fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bars_csv_text(bars), encoding="utf-8", newline="\n")


def read_bars_csv(path: Path) -> list[TrendDailyBar]:
    """Read the committed BTC/ETH bar fixture as Decimal records."""
    rows = list(csv.reader(StringIO(path.read_text(encoding="utf-8"))))
    if not rows or tuple(rows[0]) != _BAR_HEADER:
        raise TrendError(f"{path.name}: header {rows[0] if rows else None} != {list(_BAR_HEADER)}")
    out: list[TrendDailyBar] = []
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != len(_BAR_HEADER):
            raise TrendError(f"{path.name}: expected {len(_BAR_HEADER)} columns, got {row!r}")
        bar = TrendDailyBar(
            date=date.fromisoformat(row[0]),
            symbol=row[1],
            open=Decimal(row[2]),
            close=Decimal(row[3]),
        )
        if not bar.symbol.strip():
            raise TrendError(f"{path.name}: symbol must be non-empty")
        if bar.open <= 0 or bar.close <= 0:
            raise TrendError(
                f"{path.name}: {bar.symbol} {bar.date} open and close must be positive"
            )
        if any(existing.symbol == bar.symbol and existing.date == bar.date for existing in out):
            raise TrendError(f"{path.name}: duplicate bar for {bar.symbol} {bar.date}")
        out.append(bar)
    out.sort(key=lambda b: (b.symbol, b.date))
    return out


def read_bars_frame(path: Path) -> pl.DataFrame:
    """Read the committed fixture into the canonical polars frame."""
    bars = read_bars_csv(path)
    if not bars:
        raise TrendError(f"{path.name}: fixture is empty")
    frame = pl.DataFrame(
        {
            "date": [b.date for b in bars],
            "symbol": [b.symbol for b in bars],
            "open": [float(b.open) for b in bars],
            "close": [float(b.close) for b in bars],
        },
        schema=_BAR_SCHEMA,
    )
    min_open = frame["open"].min()
    min_close = frame["close"].min()
    if min_open is None or min_close is None:
        raise TrendError(f"{path.name}: fixture has no numeric rows")
    if _scalar_float(min_open, column="open") <= 0.0 or (
        _scalar_float(min_close, column="close") <= 0.0
    ):
        raise TrendError(f"{path.name}: open and close must be positive")
    return frame.sort(["symbol", "date"])


def fixture_sha256(path: Path) -> str:
    """SHA256 of the committed fixture bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_source_files_json(path: Path, sources: Sequence[SourceFile]) -> None:
    """Write the source zip provenance used by the fixture builder."""
    payload = {
        "schema_version": _SOURCE_SCHEMA_VERSION,
        "source_files": [attrs.asdict(s) for s in sorted(sources, key=lambda x: x.relpath)],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_source_files_json(path: Path) -> tuple[SourceFile, ...]:
    """Read source zip provenance for the fixture."""
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TrendError(f"{path.name}: source provenance is not a JSON object")
    if int(data.get("schema_version", -1)) != _SOURCE_SCHEMA_VERSION:
        raise TrendError(f"{path.name}: unsupported source provenance schema")
    raw = data.get("source_files")
    if not isinstance(raw, list) or not raw:
        raise TrendError(f"{path.name}: source_files must be a non-empty list")
    out: list[SourceFile] = []
    for item in raw:
        if not isinstance(item, dict):
            raise TrendError(f"{path.name}: source file entry is not an object")
        out.append(
            SourceFile(
                symbol=str(item["symbol"]),
                month=str(item["month"]),
                relpath=str(item["relpath"]),
                file_sha256=str(item["file_sha256"]),
                published_checksum=str(item["published_checksum"]),
            )
        )
    return tuple(sorted(out, key=lambda s: s.relpath))
