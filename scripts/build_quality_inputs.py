"""Build the committed daily panel for the quality-tilt study (Study 10, ADR 0012).

Network, one-time entry point. Fetches the Kenneth French operating-profitability daily portfolios
and the five-factor daily file (the same library as Studies 8 and 9), joins them on the trading day,
and writes a committed SHA256-stamped panel (the high-profitability tercile/quintile/decile and the
equal-weight high tercile, plus the five Fama-French factors and the bill) with the provenance and
the manifest stamp. The raw zip bytes are fetched once, hashed for the provenance, and parsed.
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from riskpremia.data.errors import VenueFetchError
from riskpremia.data.manifest import SnapshotEntry, compute_sha256, upsert_entries
from riskpremia.data.sources.ken_french import KenFrenchFactorsSource, KenFrenchOPSource
from riskpremia.quality.fixtures import (
    PanelRow,
    SourceProvenance,
    fixture_sha256,
    write_panel_csv,
    write_provenance_json,
)

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "quality_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "quality_panel_sources.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"
_OP_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "Portfolios_Formed_on_OP_Daily_CSV.zip"
)
_FIVE_FACTOR_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
)
_UA = "riskpremia quality research (https://github.com/sjdoane/riskpremia)"
_NOTE = (
    "Committed daily Kenneth French operating-profitability panel (high-profitability VW "
    "tercile/quintile/decile + EW high tercile + the five factors + the bill) for the Study 10 "
    "quality tilt. As-of snapshot; the SHA256 attests tamper-evidence of the committed series."
)
_PROV_NOTE = "Committed provenance for tests/data/quality_panel.csv."


def _fetch_raw(url: str, *, attempts: int = 4, backoff: float = 2.0) -> bytes:
    last: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return bytes(resp.read())
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(backoff * (i + 1))
    raise VenueFetchError(f"fetch failed after {attempts} attempts: {url}") from last


def main() -> None:
    op_bytes = _fetch_raw(_OP_URL)
    ff_bytes = _fetch_raw(_FIVE_FACTOR_URL)
    op_sha = hashlib.sha256(op_bytes).hexdigest()
    ff_sha = hashlib.sha256(ff_bytes).hexdigest()
    op = KenFrenchOPSource(open_zip=lambda _u: op_bytes).fetch_op_daily()
    factors = KenFrenchFactorsSource(open_zip=lambda _u: ff_bytes).fetch_five_factor_daily()
    print(f"fetched {len(op)} OP days, {len(factors)} five-factor days")

    fac = {f.date: f for f in factors}
    rows: list[PanelRow] = []
    for r in op:
        f = fac.get(r.date)
        if f is None:
            continue
        rows.append(
            PanelRow(
                date=r.date,
                portfolios=(r.hi30_vw, r.hi20_vw, r.hi10_vw, r.hi30_ew),
                factors=(f.mkt_rf, f.smb, f.hml, f.rmw, f.cma, f.rf),
            )
        )
    if not rows:
        raise SystemExit("no overlapping OP/factor days")
    rows.sort(key=lambda x: x.date)
    write_panel_csv(_PANEL, rows)
    fetched = datetime.now(UTC).replace(microsecond=0)
    write_provenance_json(
        _PROVENANCE,
        SourceProvenance(
            op_url=_OP_URL, op_sha256=op_sha, five_factor_url=_FIVE_FACTOR_URL,
            five_factor_sha256=ff_sha, fetched_utc=fetched.isoformat(),
        ),
    )
    upsert_entries(
        _MANIFEST,
        (
            SnapshotEntry(
                name="quality-panel", venue="ken_french", instrument="op-daily-plus-five-factor",
                kind="reproducibility_fixture", relpath=_PANEL.relative_to(_REPO).as_posix(),
                source_url=_OP_URL, fetched_utc=fetched, sha256=compute_sha256(_PANEL),
                rows=len(rows), size_bytes=_PANEL.stat().st_size, published_checksum=None,
                note=_NOTE,
            ),
            SnapshotEntry(
                name="quality-sources", venue="ken_french", instrument="op-daily-plus-five-factor",
                kind="reproducibility_fixture", relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
                source_url=_FIVE_FACTOR_URL, fetched_utc=fetched, rows=1,
                sha256=compute_sha256(_PROVENANCE), size_bytes=_PROVENANCE.stat().st_size,
                published_checksum=None,
                note=_PROV_NOTE,
            ),
        ),
    )
    print(f"Wrote {_PANEL.relative_to(_REPO).as_posix()} with {len(rows)} rows "
          f"({rows[0].date.isoformat()}..{rows[-1].date.isoformat()})")
    print(f"  panel sha256 {fixture_sha256(_PANEL)}")
    print(f"Stamped {_MANIFEST.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
