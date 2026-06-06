"""Build the committed cross-asset trend panel for Study 6 (ADR 0008).

Network, one-time entry point. It fetches the Kenneth French daily research factors (US
equity total return and the one-month Treasury bill rate) and the US Treasury ten-year par
yield, aligns them on the intersection of their trading days within the frozen window, writes
the small committed daily panel, records the upstream provenance, and stamps both committed
files into the snapshot manifest.

The window ends at the frozen data end-date (2026-03-31); the lower bound is the first date
both series cover (the Treasury par yield begins in 1990). The panel is an as-of snapshot:
both upstream sources restate recent data, so the SHA256 in the manifest attests
tamper-evidence of the committed series, not vendor byte-fidelity.
"""

from __future__ import annotations

import hashlib
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from riskpremia.data.manifest import SnapshotEntry, compute_sha256, upsert_entries
from riskpremia.data.sources.ken_french import _FACTORS_URL, _USER_AGENT, KenFrenchSource
from riskpremia.data.sources.treasury import FIRST_YEAR, TreasuryParYieldSource
from riskpremia.xtrend.fixtures import (
    PanelRow,
    SourceProvenance,
    fixture_sha256,
    write_panel_csv,
    write_provenance_json,
)

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "xtrend_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "xtrend_panel_sources.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"
_DATA_END = "2026-03-31"
_END_YEAR = 2026
_TREASURY_SOURCE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv (daily_treasury_yield_curve, 10 Yr column)"
)
_PANEL_NOTE = (
    "Committed cross-asset trend daily panel for Study 6: US equity total return and the "
    "one-month bill rate from the Kenneth French daily factors, and the US Treasury ten-year "
    "par yield, aligned on their common trading days from 1990. As-of snapshot; the SHA256 "
    "attests tamper-evidence of the committed series, not vendor byte-fidelity."
)
_PROVENANCE_NOTE = (
    "Committed provenance for tests/data/xtrend_panel.csv: the Kenneth French zip URL and "
    "hash, the Treasury par-yield year range, and the fetch date."
)


def _fetch_ken_french_zip() -> bytes:
    req = urllib.request.Request(_FACTORS_URL, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return bytes(resp.read())


def main() -> None:
    french_zip = _fetch_ken_french_zip()
    french_sha = hashlib.sha256(french_zip).hexdigest()
    french = KenFrenchSource(open_zip=lambda _url: french_zip).fetch_daily_factors()
    treasury = TreasuryParYieldSource().fetch_ten_year(FIRST_YEAR, _END_YEAR)

    end = datetime.fromisoformat(_DATA_END).date()
    cash_by_date = {f.date: f for f in french}
    yield_by_date = {t.date: t.ten_year for t in treasury}
    common = sorted(set(cash_by_date) & set(yield_by_date))
    common = [d for d in common if d <= end]
    if not common:
        raise RuntimeError("no overlapping French/Treasury dates in the window")

    rows: list[PanelRow] = []
    for d in common:
        factor = cash_by_date[d]
        rows.append(
            PanelRow(
                date=d,
                equity_ret=factor.market_total_return,
                cash_ret=factor.rf,
                bond_yield=yield_by_date[d],
            )
        )

    write_panel_csv(_PANEL, rows)
    fetched = datetime.now(UTC).replace(microsecond=0)
    write_provenance_json(
        _PROVENANCE,
        SourceProvenance(
            ken_french_url=_FACTORS_URL,
            ken_french_sha256=french_sha,
            treasury_start_year=FIRST_YEAR,
            treasury_end_year=_END_YEAR,
            fetched_utc=fetched.isoformat(),
        ),
    )
    upsert_entries(
        _MANIFEST,
        (
            SnapshotEntry(
                name="xtrend-panel",
                venue="public_domain",
                instrument="US-equity-TR,1m-bill,UST-10Y-par-yield",
                kind="reproducibility_fixture",
                relpath=_PANEL.relative_to(_REPO).as_posix(),
                source_url=f"{_FACTORS_URL} and {_TREASURY_SOURCE}",
                fetched_utc=fetched,
                sha256=compute_sha256(_PANEL),
                size_bytes=_PANEL.stat().st_size,
                rows=len(rows),
                published_checksum=None,
                note=_PANEL_NOTE,
            ),
            SnapshotEntry(
                name="xtrend-panel-sources",
                venue="public_domain",
                instrument="US-equity-TR,1m-bill,UST-10Y-par-yield",
                kind="reproducibility_fixture",
                relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
                source_url=f"{_FACTORS_URL} and {_TREASURY_SOURCE}",
                fetched_utc=fetched,
                sha256=compute_sha256(_PROVENANCE),
                size_bytes=_PROVENANCE.stat().st_size,
                rows=1,
                published_checksum=None,
                note=_PROVENANCE_NOTE,
            ),
        ),
    )
    print(f"Wrote {_PANEL.relative_to(_REPO).as_posix()} with {len(rows)} rows")
    print(f"  date range {common[0].isoformat()}..{common[-1].isoformat()}")
    print(f"  panel sha256 {fixture_sha256(_PANEL)}")
    print(f"Wrote {_PROVENANCE.relative_to(_REPO).as_posix()}")
    print(f"Stamped {_MANIFEST.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
