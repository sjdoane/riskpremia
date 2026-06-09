"""Read and append the month-end level series the live signal and paper engine consume.

The levels file is the operator-maintained record of each traded proxy's month-end total-return
(dividend-adjusted) level: the equity proxy, the long-Treasury proxy, and the cash proxy. The signal
reads the two sleeve columns; the paper engine uses all three as month-end prices. One row per
calendar month, in date order, appended once a month.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from datetime import date
from io import StringIO
from pathlib import Path

import attrs

from riskpremia.live.errors import LiveError
from riskpremia.live.signal import CASH_SYMBOL, SLEEVE_SYMBOLS

# Column order is the date then the proxy symbols (lowercased), the equity sleeve, the bond sleeve,
# then cash. Derived from the signal's symbol map so the file and the rule cannot disagree.
_SYMBOL_COLUMNS: tuple[str, ...] = (
    SLEEVE_SYMBOLS["equity"].lower(),
    SLEEVE_SYMBOLS["bond"].lower(),
    CASH_SYMBOL.lower(),
)
LEVELS_HEADER: tuple[str, ...] = ("date", *_SYMBOL_COLUMNS)


@attrs.frozen(slots=True)
class LevelRow:
    """One month-end observation of the three proxy total-return levels (positive decimals)."""

    date: date
    equity: float
    bond: float
    cash: float

    def price(self, symbol: str) -> float:
        mapping = {
            SLEEVE_SYMBOLS["equity"]: self.equity,
            SLEEVE_SYMBOLS["bond"]: self.bond,
            CASH_SYMBOL: self.cash,
        }
        if symbol not in mapping:
            raise LiveError(f"unknown symbol {symbol!r}")
        return mapping[symbol]


def levels_csv_text(rows: Sequence[LevelRow]) -> str:
    """Deterministic LF CSV text for the committed levels seed."""
    if not rows:
        raise LiveError("levels_csv_text requires at least one row")
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(LEVELS_HEADER)
    for row in sorted(rows, key=lambda r: r.date):
        writer.writerow([row.date.isoformat(), f"{row.equity:.6f}", f"{row.bond:.6f}",
                         f"{row.cash:.6f}"])
    return buf.getvalue()


def write_levels_csv(path: Path, rows: Sequence[LevelRow]) -> None:
    """Write the levels file (used for the committed seed and to initialize the runtime file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(levels_csv_text(rows), encoding="utf-8", newline="\n")


def _next_month(d: date) -> tuple[int, int]:
    return (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)


def read_levels(path: Path) -> list[LevelRow]:
    """Read the month-end levels file, validated, sorted, and checked for month gaps.

    The signal averages the trailing ten rows by position, so a missing month would silently average
    non-consecutive months and make the live signal diverge from the gated rule. The series is
    therefore required to be one consecutive calendar month per row, with no gap.
    """
    rows = list(csv.reader(StringIO(path.read_text(encoding="utf-8"))))
    if not rows or tuple(rows[0]) != LEVELS_HEADER:
        got = rows[0] if rows else None
        raise LiveError(f"{path.name}: header {got} != {list(LEVELS_HEADER)}")
    out: list[LevelRow] = []
    seen: set[date] = set()
    for raw in rows[1:]:
        if not raw:
            continue
        if len(raw) != len(LEVELS_HEADER):
            raise LiveError(f"{path.name}: expected {len(LEVELS_HEADER)} columns, got {raw!r}")
        parsed = LevelRow(date.fromisoformat(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        if parsed.date in seen:
            raise LiveError(f"{path.name}: duplicate level row for {parsed.date}")
        seen.add(parsed.date)
        if min(parsed.equity, parsed.bond, parsed.cash) <= 0.0:
            raise LiveError(f"{path.name}: {parsed.date} levels must be positive")
        out.append(parsed)
    out.sort(key=lambda r: r.date)
    for prev, cur in zip(out, out[1:], strict=False):
        if (cur.date.year, cur.date.month) != _next_month(prev.date):
            raise LiveError(
                f"{path.name}: months must be consecutive, but {prev.date} is followed by "
                f"{cur.date} (a gap). Backfill the missing month(s) before running the signal."
            )
    return out


def append_level(path: Path, row: LevelRow) -> None:
    """Append a single month-end row, refusing an out-of-order, duplicate, or gapped date."""
    existing = read_levels(path) if path.exists() else []
    if existing:
        last = existing[-1].date
        if row.date <= last:
            raise LiveError(f"new level date {row.date} must be after the last {last}")
        if (row.date.year, row.date.month) != _next_month(last):
            raise LiveError(
                f"new level month {row.date} must be the calendar month after {last}; "
                f"backfill the missing month(s) first"
            )
    write_levels_csv(path, [*existing, row])


def sleeve_levels(rows: Sequence[LevelRow]) -> Mapping[str, list[float]]:
    """The per-sleeve month-end level series the signal consumes, keyed by sleeve name."""
    return {"equity": [r.equity for r in rows], "bond": [r.bond for r in rows]}


def prices_at(rows: Sequence[LevelRow], index: int) -> Mapping[str, float]:
    """The three proxy month-end prices at one row, keyed by tradeable symbol."""
    row = rows[index]
    return {
        SLEEVE_SYMBOLS["equity"]: row.equity,
        SLEEVE_SYMBOLS["bond"]: row.bond,
        CASH_SYMBOL: row.cash,
    }
