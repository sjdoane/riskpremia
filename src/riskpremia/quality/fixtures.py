"""Committed daily panel for the quality-tilt study (Study 10, ADR 0012).

Each row is a trading day: the high-operating-profitability value-weighted tercile, quintile, and
decile returns and the equal-weighted high tercile (the headline plus the deflation family), and the
five Fama-French daily factors plus the one-month bill (for the net-of-market difference and the
factor attribution). The value-weight market total return is `mkt_rf + rf`. The panel is
self-contained for offline reproduction; the provenance records the two upstream files and their
content hashes.
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

from riskpremia.quality.errors import QualityError

PORTFOLIO_COLS: tuple[str, ...] = ("hi30_vw", "hi20_vw", "hi10_vw", "hi30_ew")
FACTOR_COLS: tuple[str, ...] = ("mkt_rf", "smb", "hml", "rmw", "cma", "rf")
_PANEL_HEADER: tuple[str, ...] = ("date", *PORTFOLIO_COLS, *FACTOR_COLS)
_PANEL_SCHEMA = {"date": pl.Date, **{c: pl.Float64 for c in (*PORTFOLIO_COLS, *FACTOR_COLS)}}
_PROVENANCE_SCHEMA_VERSION = 1


@attrs.frozen(slots=True)
class PanelRow:
    """One trading day in the committed quality panel (decimals)."""

    date: date
    portfolios: tuple[Decimal, ...]  # hi30_vw, hi20_vw, hi10_vw, hi30_ew
    factors: tuple[Decimal, ...]  # mkt_rf, smb, hml, rmw, cma, rf


@attrs.frozen(slots=True)
class SourceProvenance:
    """The upstream sources used to build the committed panel."""

    op_url: str
    op_sha256: str
    five_factor_url: str
    five_factor_sha256: str
    fetched_utc: str


def _fmt(value: Decimal) -> str:
    return f"{value.normalize():f}"


def panel_csv_text(rows: Sequence[PanelRow]) -> str:
    """Deterministic LF CSV text for the committed panel."""
    if not rows:
        raise QualityError("panel_csv_text requires at least one row")
    seen: set[date] = set()
    for row in rows:
        if len(row.portfolios) != len(PORTFOLIO_COLS) or len(row.factors) != len(FACTOR_COLS):
            raise QualityError(f"{row.date}: wrong number of portfolios/factors")
        if row.date in seen:
            raise QualityError(f"duplicate panel row for {row.date}")
        seen.add(row.date)
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_PANEL_HEADER)
    for row in sorted(rows, key=lambda r: r.date):
        cells = [_fmt(v) for v in row.portfolios] + [_fmt(v) for v in row.factors]
        writer.writerow([row.date.isoformat(), *cells])
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
        raise QualityError(f"{path.name}: header {got} != {list(_PANEL_HEADER)}")
    cols: dict[str, list[float]] = {c: [] for c in (*PORTFOLIO_COLS, *FACTOR_COLS)}
    dates: list[date] = []
    seen: set[date] = set()
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != len(_PANEL_HEADER):
            raise QualityError(f"{path.name}: expected {len(_PANEL_HEADER)} cols, got {row!r}")
        d = date.fromisoformat(row[0])
        if d in seen:
            raise QualityError(f"{path.name}: duplicate panel row for {d}")
        seen.add(d)
        dates.append(d)
        for i, c in enumerate((*PORTFOLIO_COLS, *FACTOR_COLS), start=1):
            cols[c].append(float(row[i]))
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
        raise QualityError(f"{path.name}: provenance is not a JSON object")
    return data
