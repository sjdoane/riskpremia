"""Committed daily panel for the cross-asset trend gate (Study 6, ADR 0008).

The panel is a small, committed, tamper-evident daily series aligned to the intersection of
the Kenneth French trading days and the US Treasury par-yield days. Each row stores what the
gate consumes: the US equity total-return for the day, the one-month Treasury bill return for
the day (both decimals), and the ten-year par yield (a decimal), from which the gate
reconstructs the long-Treasury total return. The provenance JSON records the upstream sources
used to build the panel (the Kenneth French zip URL and hash, the Treasury year range, and the
fetch date), so the as-of snapshot is auditable.
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

from riskpremia.xtrend.errors import XTrendError

_PANEL_HEADER: tuple[str, ...] = ("date", "equity_ret", "cash_ret", "bond_yield")
_PANEL_SCHEMA = {
    "date": pl.Date,
    "equity_ret": pl.Float64,
    "cash_ret": pl.Float64,
    "bond_yield": pl.Float64,
}
_PROVENANCE_SCHEMA_VERSION = 1


@attrs.frozen(slots=True)
class PanelRow:
    """One trading day in the committed cross-asset panel (decimals)."""

    date: date
    equity_ret: Decimal
    cash_ret: Decimal
    bond_yield: Decimal


@attrs.frozen(slots=True)
class SourceProvenance:
    """The upstream sources used to build the committed panel."""

    ken_french_url: str
    ken_french_sha256: str
    treasury_start_year: int
    treasury_end_year: int
    fetched_utc: str


def _fmt_decimal(value: Decimal) -> str:
    return f"{value.normalize():f}"


def panel_csv_text(rows: Sequence[PanelRow]) -> str:
    """Deterministic LF CSV text for the committed panel."""
    if not rows:
        raise XTrendError("panel_csv_text requires at least one row")
    seen: set[date] = set()
    for row in rows:
        if row.date in seen:
            raise XTrendError(f"duplicate panel row for {row.date}")
        seen.add(row.date)
        if row.bond_yield <= 0:
            raise XTrendError(f"{row.date}: bond_yield must be positive")
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_PANEL_HEADER)
    for row in sorted(rows, key=lambda r: r.date):
        writer.writerow(
            [
                row.date.isoformat(),
                _fmt_decimal(row.equity_ret),
                _fmt_decimal(row.cash_ret),
                _fmt_decimal(row.bond_yield),
            ]
        )
    return buf.getvalue()


def write_panel_csv(path: Path, rows: Sequence[PanelRow]) -> None:
    """Write the committed panel fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(panel_csv_text(rows), encoding="utf-8", newline="\n")


def read_panel_csv(path: Path) -> list[PanelRow]:
    """Read the committed panel fixture as Decimal records."""
    rows = list(csv.reader(StringIO(path.read_text(encoding="utf-8"))))
    if not rows or tuple(rows[0]) != _PANEL_HEADER:
        got = rows[0] if rows else None
        raise XTrendError(f"{path.name}: header {got} != {list(_PANEL_HEADER)}")
    out: list[PanelRow] = []
    seen: set[date] = set()
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != len(_PANEL_HEADER):
            raise XTrendError(f"{path.name}: expected {len(_PANEL_HEADER)} columns, got {row!r}")
        parsed = PanelRow(
            date=date.fromisoformat(row[0]),
            equity_ret=Decimal(row[1]),
            cash_ret=Decimal(row[2]),
            bond_yield=Decimal(row[3]),
        )
        if parsed.date in seen:
            raise XTrendError(f"{path.name}: duplicate panel row for {parsed.date}")
        seen.add(parsed.date)
        if parsed.bond_yield <= 0:
            raise XTrendError(f"{path.name}: {parsed.date} bond_yield must be positive")
        out.append(parsed)
    out.sort(key=lambda r: r.date)
    return out


def read_panel_frame(path: Path) -> pl.DataFrame:
    """Read the committed panel into the canonical polars frame, sorted by date."""
    rows = read_panel_csv(path)
    if not rows:
        raise XTrendError(f"{path.name}: panel is empty")
    return pl.DataFrame(
        {
            "date": [r.date for r in rows],
            "equity_ret": [float(r.equity_ret) for r in rows],
            "cash_ret": [float(r.cash_ret) for r in rows],
            "bond_yield": [float(r.bond_yield) for r in rows],
        },
        schema=_PANEL_SCHEMA,
    ).sort("date")


def fixture_sha256(path: Path) -> str:
    """SHA256 of the committed fixture bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_provenance_json(path: Path, provenance: SourceProvenance) -> None:
    """Write the source provenance JSON for the panel."""
    payload = {
        "schema_version": _PROVENANCE_SCHEMA_VERSION,
        "provenance": attrs.asdict(provenance),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_provenance_json(path: Path) -> SourceProvenance:
    """Read the source provenance JSON for the panel."""
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise XTrendError(f"{path.name}: provenance is not a JSON object")
    if int(data.get("schema_version", -1)) != _PROVENANCE_SCHEMA_VERSION:
        raise XTrendError(f"{path.name}: unsupported provenance schema")
    raw = data.get("provenance")
    if not isinstance(raw, dict):
        raise XTrendError(f"{path.name}: provenance payload missing")
    return SourceProvenance(
        ken_french_url=str(raw["ken_french_url"]),
        ken_french_sha256=str(raw["ken_french_sha256"]),
        treasury_start_year=int(raw["treasury_start_year"]),
        treasury_end_year=int(raw["treasury_end_year"]),
        fetched_utc=str(raw["fetched_utc"]),
    )
