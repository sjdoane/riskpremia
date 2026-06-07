"""Committed daily funding-dispersion series for Study 7 (ADR 0009).

The committed fixture is the small daily dispersion series (one row per grid day): the
point-in-time eligible and funded coin counts, the equal-weight cross-sectional dispersion
statistics (interquartile range, standard deviation, winsorized standard deviation) of
annualized funding, and the secondary gross high-minus-low sort premium. The raw per-coin
funding (hundreds of checksummed Binance Vision zips) is not committed; the daily series is the
reproducible input from which the bootstrap, the regime split, and the decay are rebuilt
offline, and the raw-funding-to-series aggregation is exercised by unit tests on synthetic
funding. The provenance JSON records the upstream sources and the build parameters.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Sequence
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any

import attrs
import polars as pl

from riskpremia.dispersion.errors import DispersionError

_SERIES_HEADER: tuple[str, ...] = (
    "date", "n_eligible", "n_funded", "iqr", "std", "winsor_std", "sort_premium"
)
_SERIES_SCHEMA = {
    "date": pl.Date,
    "n_eligible": pl.Int64,
    "n_funded": pl.Int64,
    "iqr": pl.Float64,
    "std": pl.Float64,
    "winsor_std": pl.Float64,
    "sort_premium": pl.Float64,
}
_PROVENANCE_SCHEMA_VERSION = 1
_MISSING = ""  # CSV cell for a null sort_premium (the final grid day)


@attrs.frozen(slots=True)
class DispersionDailyRow:
    """One grid day of the funding-dispersion series (annualized units)."""

    date: date
    n_eligible: int
    n_funded: int
    iqr: float
    std: float
    winsor_std: float
    sort_premium: float | None


@attrs.frozen(slots=True)
class SourceProvenance:
    """The upstream sources and build parameters for the committed series."""

    ctrend_panel_relpath: str
    ctrend_panel_content_sha256: str
    funding_source_url: str
    top_n: int
    max_gap_days: int
    winsor_pct: float
    n_quantiles: int
    n_coins_fetched: int
    fetched_utc: str


def _fmt(value: float) -> str:
    return repr(float(value))


def series_csv_text(rows: Sequence[DispersionDailyRow]) -> str:
    """Deterministic LF CSV text for the committed dispersion series."""
    if not rows:
        raise DispersionError("series_csv_text requires at least one row")
    seen: set[date] = set()
    for r in rows:
        if r.date in seen:
            raise DispersionError(f"duplicate dispersion row for {r.date}")
        seen.add(r.date)
        if r.n_funded < 0 or r.n_eligible < 0 or r.n_funded > r.n_eligible:
            raise DispersionError(f"{r.date}: invalid coverage counts")
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_SERIES_HEADER)
    for r in sorted(rows, key=lambda x: x.date):
        writer.writerow(
            [
                r.date.isoformat(),
                r.n_eligible,
                r.n_funded,
                _fmt(r.iqr),
                _fmt(r.std),
                _fmt(r.winsor_std),
                _MISSING if r.sort_premium is None else _fmt(r.sort_premium),
            ]
        )
    return buf.getvalue()


def write_series_csv(path: Path, rows: Sequence[DispersionDailyRow]) -> None:
    """Write the committed dispersion series fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(series_csv_text(rows), encoding="utf-8", newline="\n")


def read_series_csv(path: Path) -> list[DispersionDailyRow]:
    """Read the committed dispersion series fixture."""
    rows = list(csv.reader(StringIO(path.read_text(encoding="utf-8"))))
    if not rows or tuple(rows[0]) != _SERIES_HEADER:
        got = rows[0] if rows else None
        raise DispersionError(f"{path.name}: header {got} != {list(_SERIES_HEADER)}")
    out: list[DispersionDailyRow] = []
    seen: set[date] = set()
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != len(_SERIES_HEADER):
            raise DispersionError(f"{path.name}: expected {len(_SERIES_HEADER)} cols, got {row!r}")
        d = date.fromisoformat(row[0])
        if d in seen:
            raise DispersionError(f"{path.name}: duplicate row for {d}")
        seen.add(d)
        out.append(
            DispersionDailyRow(
                date=d,
                n_eligible=int(row[1]),
                n_funded=int(row[2]),
                iqr=float(row[3]),
                std=float(row[4]),
                winsor_std=float(row[5]),
                sort_premium=None if row[6] == _MISSING else float(row[6]),
            )
        )
    out.sort(key=lambda x: x.date)
    return out


def read_series_frame(path: Path) -> pl.DataFrame:
    """Read the committed dispersion series into the canonical polars frame, sorted by date."""
    rows = read_series_csv(path)
    if not rows:
        raise DispersionError(f"{path.name}: series is empty")
    return pl.DataFrame(
        {
            "date": [r.date for r in rows],
            "n_eligible": [r.n_eligible for r in rows],
            "n_funded": [r.n_funded for r in rows],
            "iqr": [r.iqr for r in rows],
            "std": [r.std for r in rows],
            "winsor_std": [r.winsor_std for r in rows],
            "sort_premium": [r.sort_premium for r in rows],
        },
        schema=_SERIES_SCHEMA,
    ).sort("date")


def fixture_sha256(path: Path) -> str:
    """SHA256 of the committed fixture bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_provenance_json(path: Path, provenance: SourceProvenance) -> None:
    """Write the source provenance JSON for the series."""
    payload = {"schema_version": _PROVENANCE_SCHEMA_VERSION, "provenance": attrs.asdict(provenance)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def read_provenance_json(path: Path) -> SourceProvenance:
    """Read the source provenance JSON for the series."""
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("schema_version", -1) if isinstance(data, dict) else -1
    if int(version) != _PROVENANCE_SCHEMA_VERSION:
        raise DispersionError(f"{path.name}: unsupported or malformed provenance")
    raw = data["provenance"]
    return SourceProvenance(
        ctrend_panel_relpath=str(raw["ctrend_panel_relpath"]),
        ctrend_panel_content_sha256=str(raw["ctrend_panel_content_sha256"]),
        funding_source_url=str(raw["funding_source_url"]),
        top_n=int(raw["top_n"]),
        max_gap_days=int(raw["max_gap_days"]),
        winsor_pct=float(raw["winsor_pct"]),
        n_quantiles=int(raw["n_quantiles"]),
        n_coins_fetched=int(raw["n_coins_fetched"]),
        fetched_utc=str(raw["fetched_utc"]),
    )
