"""Build the committed daily factor panel for the Study 8 factor-asymmetry secondary (ADR 0010).

Network, one-time entry point. Fetches the Kenneth French five-factor and momentum daily files
(the same openly-redistributed library as Study 6), joins them on the trading day, restricts to the
1990-onward era of the market primary, and writes a small committed fixture plus the provenance and
the manifest stamp. The asymmetry artifact is rebuilt offline from this fixture.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from riskpremia.data.manifest import SnapshotEntry, compute_sha256, upsert_entries
from riskpremia.data.sources.ken_french import KenFrenchFactorsSource
from riskpremia.volmanaged.factors import (
    FactorPanelRow,
    FactorProvenance,
    fixture_sha256,
    write_factor_panel_csv,
    write_factor_provenance_json,
)

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "volmanaged_factor_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "volmanaged_factor_sources.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"
_START = date(1990, 1, 1)
_FIVE_FACTOR_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
)
_MOMENTUM_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Momentum_Factor_daily_CSV.zip"
)
_NOTE = (
    "Committed daily Kenneth French factor panel (SMB, HML, RMW, CMA, WML) for the Study 8 "
    "factor-asymmetry secondary, 1990 onward. As-of snapshot; the SHA256 attests tamper-evidence "
    "of the committed series. The five-factor and momentum daily files are openly redistributed."
)
_PROV_NOTE = "Committed provenance for tests/data/volmanaged_factor_panel.csv."


def main() -> None:
    source = KenFrenchFactorsSource()
    five = source.fetch_five_factor_daily()
    mom = {r.date: r.mom for r in source.fetch_momentum_daily()}
    print(f"fetched {len(five)} five-factor days, {len(mom)} momentum days")
    rows: list[FactorPanelRow] = []
    for r in five:
        if r.date < _START or r.date not in mom:
            continue
        rows.append(
            FactorPanelRow(date=r.date, smb=r.smb, hml=r.hml, rmw=r.rmw, cma=r.cma, wml=mom[r.date])
        )
    if not rows:
        raise SystemExit("no overlapping factor days after 1990")
    rows.sort(key=lambda x: x.date)
    write_factor_panel_csv(_PANEL, rows)
    fetched = datetime.now(UTC).replace(microsecond=0)
    write_factor_provenance_json(
        _PROVENANCE,
        FactorProvenance(
            five_factor_url=_FIVE_FACTOR_URL, momentum_url=_MOMENTUM_URL,
            start=rows[0].date.isoformat(), end=rows[-1].date.isoformat(),
            fetched_utc=fetched.isoformat(),
        ),
    )
    upsert_entries(
        _MANIFEST,
        (
            SnapshotEntry(
                name="volmanaged-factor-panel", venue="ken_french",
                instrument="five-factor-plus-momentum-daily", kind="reproducibility_fixture",
                relpath=_PANEL.relative_to(_REPO).as_posix(), source_url=_FIVE_FACTOR_URL,
                fetched_utc=fetched, sha256=compute_sha256(_PANEL), rows=len(rows),
                size_bytes=_PANEL.stat().st_size, published_checksum=None, note=_NOTE,
            ),
            SnapshotEntry(
                name="volmanaged-factor-sources", venue="ken_french",
                instrument="five-factor-plus-momentum-daily", kind="reproducibility_fixture",
                relpath=_PROVENANCE.relative_to(_REPO).as_posix(), source_url=_MOMENTUM_URL,
                fetched_utc=fetched, sha256=compute_sha256(_PROVENANCE), rows=1,
                size_bytes=_PROVENANCE.stat().st_size, published_checksum=None, note=_PROV_NOTE,
            ),
        ),
    )
    print(f"Wrote {_PANEL.relative_to(_REPO).as_posix()} with {len(rows)} rows "
          f"({rows[0].date.isoformat()}..{rows[-1].date.isoformat()})")
    print(f"  panel sha256 {fixture_sha256(_PANEL)}")
    print(f"Stamped {_MANIFEST.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
