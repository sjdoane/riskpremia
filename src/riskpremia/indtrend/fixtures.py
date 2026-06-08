"""Committed daily panel for the industry-trend study (Study 9, ADR 0011).

Each row is a trading day: the 12 Kenneth French value-weighted industry total returns, the
value-weighted market total return (`Mkt-RF + RF`), and the one-month Treasury bill (all decimals).
The panel is self-contained for offline reproduction; the provenance records the two upstream files
(the 12-industry portfolios and the research factors) and their content hashes.
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

from riskpremia.indtrend.errors import IndTrendError

INDUSTRY_COLS: tuple[str, ...] = (
    "nodur", "durbl", "manuf", "enrgy", "chems", "buseq",
    "telcm", "utils", "shops", "hlth", "money", "other",
)
_PANEL_HEADER: tuple[str, ...] = ("date", *INDUSTRY_COLS, "market_ret", "cash_ret")
_PANEL_SCHEMA = {
    "date": pl.Date,
    **{c: pl.Float64 for c in INDUSTRY_COLS},
    "market_ret": pl.Float64,
    "cash_ret": pl.Float64,
}
_PROVENANCE_SCHEMA_VERSION = 1


@attrs.frozen(slots=True)
class PanelRow:
    """One trading day in the committed industry panel (decimals)."""

    date: date
    industries: tuple[Decimal, ...]
    market_ret: Decimal
    cash_ret: Decimal


@attrs.frozen(slots=True)
class SourceProvenance:
    """The upstream sources used to build the committed panel."""

    industry_url: str
    industry_sha256: str
    factors_url: str
    factors_sha256: str
    fetched_utc: str


def _fmt(value: Decimal) -> str:
    return f"{value.normalize():f}"


def panel_csv_text(rows: Sequence[PanelRow]) -> str:
    """Deterministic LF CSV text for the committed panel."""
    if not rows:
        raise IndTrendError("panel_csv_text requires at least one row")
    seen: set[date] = set()
    for row in rows:
        if len(row.industries) != len(INDUSTRY_COLS):
            raise IndTrendError(f"{row.date}: expected {len(INDUSTRY_COLS)} industries")
        if row.date in seen:
            raise IndTrendError(f"duplicate panel row for {row.date}")
        seen.add(row.date)
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_PANEL_HEADER)
    for row in sorted(rows, key=lambda r: r.date):
        writer.writerow(
            [row.date.isoformat(), *[_fmt(v) for v in row.industries],
             _fmt(row.market_ret), _fmt(row.cash_ret)]
        )
    return buf.getvalue()


def write_panel_csv(path: Path, rows: Sequence[PanelRow]) -> None:
    """Write the committed panel fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(panel_csv_text(rows), encoding="utf-8", newline="\n")


def read_panel_frame(path: Path) -> pl.DataFrame:
    """Read the committed panel into the canonical polars frame, sorted by date."""
    rows = list(csv.reader(StringIO(path.read_text(encoding="utf-8"))))
    if not rows or tuple(rows[0]) != _PANEL_HEADER:
        got = rows[0] if rows else None
        raise IndTrendError(f"{path.name}: header {got} != {list(_PANEL_HEADER)}")
    cols: dict[str, list[float]] = {c: [] for c in (*INDUSTRY_COLS, "market_ret", "cash_ret")}
    dates: list[date] = []
    seen: set[date] = set()
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != len(_PANEL_HEADER):
            raise IndTrendError(f"{path.name}: expected {len(_PANEL_HEADER)} cols, got {row!r}")
        d = date.fromisoformat(row[0])
        if d in seen:
            raise IndTrendError(f"{path.name}: duplicate panel row for {d}")
        seen.add(d)
        dates.append(d)
        for i, c in enumerate(INDUSTRY_COLS, start=1):
            cols[c].append(float(row[i]))
        cols["market_ret"].append(float(row[len(INDUSTRY_COLS) + 1]))
        cols["cash_ret"].append(float(row[len(INDUSTRY_COLS) + 2]))
    return pl.DataFrame({"date": dates, **cols}, schema=_PANEL_SCHEMA).sort("date")


def fixture_sha256(path: Path) -> str:
    """SHA256 of the committed fixture bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_provenance_json(path: Path, provenance: SourceProvenance) -> None:
    """Write the source provenance JSON for the panel."""
    payload = {"schema_version": _PROVENANCE_SCHEMA_VERSION, "provenance": attrs.asdict(provenance)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                    newline="\n")


def read_provenance_json(path: Path) -> dict[str, Any]:
    """Read the source provenance JSON (for inspection)."""
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise IndTrendError(f"{path.name}: provenance is not a JSON object")
    return data
