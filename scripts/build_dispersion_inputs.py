"""Build the committed funding-dispersion series for Study 7 (ADR 0009).

Network, one-time entry point. Point-in-time eligibility is read from the COMMITTED CTREND
daily panel (no spot re-fetch); the per-coin perpetual funding is fetched from the Binance
Vision funding archive for the ever-eligible top-N universe (coins with no perp funding series
are dropped and counted as a coverage diagnostic); the cross-sectional dispersion series is
built and written as a small committed fixture, with the provenance and the manifest stamp.

The committed fixture is the daily dispersion series, not the raw funding (hundreds of
checksummed zips); the raw-funding-to-series aggregation is exercised by unit tests, and the
series reproduces the artifact offline.
"""

from __future__ import annotations

import urllib.error
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from riskpremia.ctrend.fixtures import daily_panel_content_sha256, read_daily_panel
from riskpremia.ctrend.universe import build_weekly_panel, pit_eligible
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.manifest import SnapshotEntry, compute_sha256, upsert_entries
from riskpremia.data.sources.binance_vision import BinanceVisionSource
from riskpremia.dispersion.fixtures import (
    SourceProvenance,
    fixture_sha256,
    write_provenance_json,
    write_series_csv,
)
from riskpremia.dispersion.measure import build_daily_series

_REPO = Path(__file__).resolve().parents[1]
_RAW_ROOT = _REPO / "data" / "raw"
_CTREND_PANEL = _REPO / "tests" / "data" / "ctrend_daily_panel_usdt.csv.gz"
_SERIES = _REPO / "tests" / "data" / "funding_dispersion_series.csv"
_PROVENANCE = _REPO / "tests" / "data" / "funding_dispersion_sources.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"
_TOP_N = 15  # the top-N most-liquid perpetuals (a clean, bounded point-in-time dispersion universe)
_START_YM = "2022-01"  # the matured-perp-market window where the funding archive is rich
_END_YM = "2026-06"  # exclusive upper bound
_FUNDING_URL = "https://data.binance.vision/data/futures/um/monthly/fundingRate/"


def _month_start(ym: str) -> datetime:
    return datetime(int(ym[:4]), int(ym[5:7]), 1, tzinfo=UTC)


def _next_month(ym: str) -> datetime:
    year, month = int(ym[:4]), int(ym[5:7])
    if month == 12:
        return datetime(year + 1, 1, 1, tzinfo=UTC)
    return datetime(year, month + 1, 1, tzinfo=UTC)
_SERIES_NOTE = (
    "Committed daily cross-sectional funding-dispersion series for Study 7: equal-weight IQR, "
    "std, winsorized std, and the gross high-minus-low sort premium of annualized perpetual "
    "funding over the point-in-time top-N liquid universe. As-of snapshot; the SHA256 attests "
    "tamper-evidence of the committed series, not vendor byte-fidelity. The raw funding is the "
    "checksummed Binance Vision archive."
)
_PROVENANCE_NOTE = (
    "Committed provenance for tests/data/funding_dispersion_series.csv: the CTREND panel hash "
    "used for eligibility, the funding source, the build parameters, and the fetch date."
)


def main() -> None:
    window_start = _month_start(_START_YM)
    daily = read_daily_panel(_CTREND_PANEL)
    weekly = build_weekly_panel(daily)
    flagged = pit_eligible(weekly, top_n=_TOP_N)
    eligible = (
        flagged.filter(pl.col("eligible") & (pl.col("week_end") >= pl.lit(window_start.date())))
        .select("week_end", "symbol")
        .unique()
    )
    symbols = sorted(eligible["symbol"].unique().to_list())
    print(f"PIT eligible (top-{_TOP_N}, {_START_YM}+): {len(symbols)} ever-eligible symbols")

    source = BinanceVisionSource(_RAW_ROOT, max_fetch_attempts=5, retry_backoff_s=1.0)
    funding_rows: list[tuple[str, datetime, float, int]] = []
    n_with_funding = 0
    n_skipped = 0
    for i, symbol in enumerate(symbols, 1):
        months = [m for m in source.available_months(symbol) if _START_YM <= m < _END_YM]
        if not months:
            continue  # no perp funding series in the window (coverage hole)
        try:
            records = source.fetch_funding(symbol, _month_start(months[0]), _next_month(months[-1]))
        except (VenueFetchError, urllib.error.HTTPError):
            n_skipped += 1  # a rare middle-month gap; drop the coin and count it
            continue
        if not records:
            continue
        n_with_funding += 1
        for rec in records:
            funding_rows.append(
                (symbol, rec.funding_ts, float(rec.funding_rate), rec.funding_interval_hours)
            )
        if i % 25 == 0:
            print(f"  fetched {i}/{len(symbols)} symbols ({n_with_funding} with funding)")
    print(f"funding fetched: {n_with_funding}/{len(symbols)} symbols "
          f"({n_skipped} skipped), {len(funding_rows)} events")

    funding = pl.DataFrame(
        {
            "symbol": [r[0] for r in funding_rows],
            "ts": [r[1] for r in funding_rows],
            "rate": [r[2] for r in funding_rows],
            "interval_hours": [r[3] for r in funding_rows],
        },
        schema={"symbol": pl.Utf8, "ts": pl.Datetime("us", "UTC"), "rate": pl.Float64,
                "interval_hours": pl.Int64},
    )
    series = build_daily_series(funding, eligible, top_n=_TOP_N)
    write_series_csv(_SERIES, series)
    fetched = datetime.now(UTC).replace(microsecond=0)
    write_provenance_json(
        _PROVENANCE,
        SourceProvenance(
            ctrend_panel_relpath=_CTREND_PANEL.relative_to(_REPO).as_posix(),
            ctrend_panel_content_sha256=daily_panel_content_sha256(_CTREND_PANEL),
            funding_source_url=_FUNDING_URL,
            top_n=_TOP_N,
            max_gap_days=3,
            winsor_pct=0.05,
            n_quantiles=5,
            n_coins_fetched=n_with_funding,
            fetched_utc=fetched.isoformat(),
        ),
    )
    upsert_entries(
        _MANIFEST,
        (
            SnapshotEntry(
                name="funding-dispersion-series",
                venue="binance_vision",
                instrument=f"perp-funding-top{_TOP_N}-cross-section",
                kind="reproducibility_fixture",
                relpath=_SERIES.relative_to(_REPO).as_posix(),
                source_url=_FUNDING_URL,
                fetched_utc=fetched,
                sha256=compute_sha256(_SERIES),
                size_bytes=_SERIES.stat().st_size,
                rows=len(series),
                published_checksum=None,
                note=_SERIES_NOTE,
            ),
            SnapshotEntry(
                name="funding-dispersion-sources",
                venue="binance_vision",
                instrument=f"perp-funding-top{_TOP_N}-cross-section",
                kind="reproducibility_fixture",
                relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
                source_url=_FUNDING_URL,
                fetched_utc=fetched,
                sha256=compute_sha256(_PROVENANCE),
                size_bytes=_PROVENANCE.stat().st_size,
                rows=1,
                published_checksum=None,
                note=_PROVENANCE_NOTE,
            ),
        ),
    )
    print(f"Wrote {_SERIES.relative_to(_REPO).as_posix()} with {len(series)} rows")
    print(f"  date range {series[0].date.isoformat()}..{series[-1].date.isoformat()}")
    print(f"  series sha256 {fixture_sha256(_SERIES)}")
    print(f"Stamped {_MANIFEST.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
