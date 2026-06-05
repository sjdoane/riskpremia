"""The committed daily-panel CSV fixture for the CTREND universe (ADR 0005 PR1).

The reproducibility anchor for Study 3. The raw Binance Vision daily-kline zips are
immutable + checksummed (re-fetchable), but the derived multi-coin daily panel is what
PR2 (features) and PR3 (the gate) consume offline, so the panel TRIMMED to the
ever-top-N_MAX coins is committed and SHA256-stamped. The weekly grid + the eligibility
are pure functions of this committed panel (computed in `universe.py`, never separately
committed, so they cannot drift), and an offline test rebuilds the universe artifact from
it. The build re-fetches the checksummed raw and proves it reproduces the committed panel.

Storage: a daily panel of ~560 liquid coins over seven years is large (~35 MB plain), so
the committed panel is GZIPPED (`*.csv.gz`). Two integrity hashes are kept, both
cross-platform stable: the artifact fingerprint pins the SHA256 of the DECOMPRESSED CSV
CONTENT (the meaningful, platform-independent integrity check, since a re-gzip on a
different zlib build yields different container bytes for identical content), and the
snapshot manifest stamps the committed `.gz` blob's file SHA256 (git preserves the blob
byte-for-byte, `.gitattributes` marks `*.gz binary`, so CI reads the identical bytes a
build wrote). The underlying CSV is deterministic: sorted by `(symbol, date)`, LF
newlines, and each value formatted as its EXACT `Decimal` with trailing zeros stripped (a
lossless normalization, so `Decimal("4.83900000")` is written `4.839` and reads back to
the identical float). The reader routes through `build_daily_panel` so the positivity
guards fire on the reproduction path. Stdlib only (csv, gzip, hashlib).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path

import polars as pl

from riskpremia.ctrend.errors import CtrendError
from riskpremia.ctrend.universe import build_daily_panel
from riskpremia.data.records import InstrumentId, SpotKlineRecord

_DAILY_HEADER: tuple[str, ...] = ("date", "symbol", "close", "high", "low", "dollar_volume")


def _fmt_decimal(value: Decimal) -> str:
    """The exact Decimal in fixed-point notation with trailing zeros stripped (lossless).

    `4.83900000` -> `4.839`, `100` -> `100`, `0.00122300` -> `0.001223`. `normalize()`
    removes trailing zeros (and may move to an exponent form, which `:f` forces back to
    fixed-point), so the written value parses back to the identical Decimal and float.
    """
    return f"{value.normalize():f}"


def _daily_panel_csv_text(records: Sequence[SpotKlineRecord]) -> str:
    """The deterministic daily-panel CSV text: sorted, deduped, LF, normalized Decimals.

    Raises:
      CtrendError: on an empty input or a non-positive close / negative dollar volume.
    """
    if len(records) == 0:
        raise CtrendError("the daily panel requires at least one record")
    deduped: dict[tuple[str, date], SpotKlineRecord] = {}
    for rec in records:
        if rec.low <= 0:
            raise CtrendError(f"low must be positive; got {rec.low} for {rec.instrument.symbol}")
        if rec.close <= 0:
            raise CtrendError(
                f"close must be positive; got {rec.close} for {rec.instrument.symbol}"
            )
        if rec.high < rec.low or rec.close > rec.high or rec.close < rec.low:
            raise CtrendError(
                f"inconsistent OHLC for {rec.instrument.symbol}: close={rec.close} "
                f"high={rec.high} low={rec.low}"
            )
        if rec.quote_volume < 0:
            raise CtrendError(
                f"dollar_volume must be >= 0; got {rec.quote_volume} for {rec.instrument.symbol}"
            )
        deduped[(rec.instrument.symbol, rec.period_end_ts.date())] = rec
    rows = sorted(deduped.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_DAILY_HEADER)
    for (symbol, d), rec in rows:
        writer.writerow(
            [
                d.isoformat(),
                symbol,
                _fmt_decimal(rec.close),
                _fmt_decimal(rec.high),
                _fmt_decimal(rec.low),
                _fmt_decimal(rec.quote_volume),
            ]
        )
    return buf.getvalue()


def write_daily_panel_csv(path: Path, records: Sequence[SpotKlineRecord]) -> None:
    """Write the committed daily panel as a plain LF CSV (used by the unit fixtures)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_daily_panel_csv_text(records), encoding="utf-8", newline="\n")


def write_daily_panel_gz(path: Path, records: Sequence[SpotKlineRecord]) -> None:
    """Write the committed daily panel as a deterministic gzip (`mtime=0`) of the LF CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _daily_panel_csv_text(records).encode("utf-8")
    path.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))


def _read_panel_text(path: Path) -> str:
    """The CSV text, decompressing transparently when `path` is a `.gz`."""
    if path.suffix == ".gz":
        return gzip.decompress(path.read_bytes()).decode("utf-8")
    return path.read_text(encoding="utf-8")


def daily_panel_content_sha256(path: Path) -> str:
    """SHA256 of the DECOMPRESSED CSV content (the cross-platform integrity pin)."""
    return hashlib.sha256(_read_panel_text(path).encode("utf-8")).hexdigest()


def read_daily_panel_records(path: Path) -> list[SpotKlineRecord]:
    """Read the committed daily panel (plain or `.gz`) back into `SpotKlineRecord`s.

    The `period_end_ts` is the midnight-UTC instant of the date (the only granularity the
    panel consumes is the calendar date); the close + dollar volume are exact `Decimal`s.

    Raises:
      CtrendError: on a bad header or a malformed row.
    """
    rows = list(csv.reader(StringIO(_read_panel_text(path))))
    if not rows or tuple(rows[0]) != _DAILY_HEADER:
        raise CtrendError(
            f"{path.name}: header {rows[0] if rows else None} != {list(_DAILY_HEADER)}"
        )
    out: list[SpotKlineRecord] = []
    for r in rows[1:]:
        if not r:
            continue  # tolerate a trailing blank line
        if len(r) != len(_DAILY_HEADER):
            raise CtrendError(f"{path.name}: expected {len(_DAILY_HEADER)} columns, got {r!r}")
        d = date.fromisoformat(r[0])
        out.append(
            SpotKlineRecord(
                instrument=InstrumentId.of("binance_vision", r[1]),
                period_end_ts=datetime(d.year, d.month, d.day, tzinfo=UTC),
                close=Decimal(r[2]),
                high=Decimal(r[3]),
                low=Decimal(r[4]),
                quote_volume=Decimal(r[5]),
            )
        )
    return out


def read_daily_panel(path: Path) -> pl.DataFrame:
    """Read the committed daily panel (plain or `.gz`) into the canonical daily frame.

    Routes through `build_daily_panel`, so the positivity guards fire on the reproduction
    path and the frame is identical (schema, dedup, sort) to a freshly-built panel.
    """
    return build_daily_panel(read_daily_panel_records(path))
