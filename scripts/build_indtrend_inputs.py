"""Build the committed daily panel for the industry-trend study (Study 9, ADR 0011).

Network, one-time entry point. Fetches the Kenneth French 12-industry daily value-weighted
portfolios and the daily research factors (the same library as Studies 6 and 8), joins them on the
trading day, and writes a committed SHA256-stamped panel (the 12 industry total returns, the
value-weight market total return `Mkt-RF + RF`, and the one-month bill) plus the provenance and the
manifest stamp. The raw zip bytes are fetched once, hashed for the provenance, and parsed in place.
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
from riskpremia.data.sources.ken_french import (
    KenFrench12IndustrySource,
    KenFrenchSource,
)
from riskpremia.indtrend.fixtures import (
    PanelRow,
    SourceProvenance,
    fixture_sha256,
    write_panel_csv,
    write_provenance_json,
)

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "indtrend_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "indtrend_panel_sources.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"
_INDUSTRY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "12_Industry_Portfolios_daily_CSV.zip"
)
_FACTORS_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_daily_CSV.zip"
)
_UA = "riskpremia cross-asset-trend research (https://github.com/sjdoane/riskpremia)"
_NOTE = (
    "Committed daily Kenneth French 12-industry value-weighted panel (12 industries + the "
    "value-weight market + the one-month bill) for the Study 9 industry-trend study. As-of "
    "snapshot; the SHA256 attests tamper-evidence of the committed series."
)
_PROV_NOTE = "Committed provenance for tests/data/indtrend_panel.csv."


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
    ind_bytes = _fetch_raw(_INDUSTRY_URL)
    fac_bytes = _fetch_raw(_FACTORS_URL)
    ind_sha = hashlib.sha256(ind_bytes).hexdigest()
    fac_sha = hashlib.sha256(fac_bytes).hexdigest()
    industry_source = KenFrench12IndustrySource(open_zip=lambda _u: ind_bytes)
    industries = industry_source.fetch_value_weighted_daily()
    factors = KenFrenchSource(open_zip=lambda _u: fac_bytes).fetch_daily_factors()
    print(f"fetched {len(industries)} industry days, {len(factors)} factor days")

    market = {f.date: (f.mkt_rf + f.rf, f.rf) for f in factors}  # (market total return, bill)
    rows: list[PanelRow] = []
    for r in industries:
        if r.date not in market:
            continue
        mkt, rf = market[r.date]
        rows.append(PanelRow(date=r.date, industries=r.returns, market_ret=mkt, cash_ret=rf))
    if not rows:
        raise SystemExit("no overlapping industry/factor days")
    rows.sort(key=lambda x: x.date)
    write_panel_csv(_PANEL, rows)
    fetched = datetime.now(UTC).replace(microsecond=0)
    write_provenance_json(
        _PROVENANCE,
        SourceProvenance(
            industry_url=_INDUSTRY_URL, industry_sha256=ind_sha,
            factors_url=_FACTORS_URL, factors_sha256=fac_sha, fetched_utc=fetched.isoformat(),
        ),
    )
    upsert_entries(
        _MANIFEST,
        (
            SnapshotEntry(
                name="indtrend-panel", venue="ken_french", instrument="12-industry-vw-daily",
                kind="reproducibility_fixture", relpath=_PANEL.relative_to(_REPO).as_posix(),
                source_url=_INDUSTRY_URL, fetched_utc=fetched, sha256=compute_sha256(_PANEL),
                rows=len(rows), size_bytes=_PANEL.stat().st_size, published_checksum=None,
                note=_NOTE,
            ),
            SnapshotEntry(
                name="indtrend-sources", venue="ken_french", instrument="12-industry-vw-daily",
                kind="reproducibility_fixture", relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
                source_url=_FACTORS_URL, fetched_utc=fetched, sha256=compute_sha256(_PROVENANCE),
                rows=1, size_bytes=_PROVENANCE.stat().st_size, published_checksum=None,
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
