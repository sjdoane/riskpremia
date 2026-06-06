"""Build the committed BTC/ETH daily OHLC fixture for Study 4.

Network, one-time entry point. It fetches Binance Vision daily spot klines for BTCUSDT
and ETHUSDT, writes the small committed fixture used by PR6a, records the upstream zip
checksums in a committed JSON provenance file, and stamps both committed files into the
snapshot manifest.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from riskpremia.data.manifest import (
    SnapshotEntry,
    compute_sha256,
    parse_checksum_line,
    upsert_entries,
)
from riskpremia.data.sources.binance_vision import BinanceVisionSource, _month_strings
from riskpremia.trend.fixtures import (
    SourceFile,
    TrendDailyBar,
    write_bars_csv,
    write_source_files_json,
)

_REPO = Path(__file__).resolve().parents[1]
_RAW_ROOT = _REPO / "data" / "raw"
_BARS = _REPO / "tests" / "data" / "btc_eth_daily_ohlc.csv"
_SOURCES = _REPO / "tests" / "data" / "btc_eth_daily_ohlc_sources.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"
_SYMBOLS = ("BTCUSDT", "ETHUSDT")
_INTERVAL = "1d"
_START = datetime(2019, 1, 1, tzinfo=UTC)
_END = datetime(2026, 6, 1, tzinfo=UTC)
_SOURCE_URL = (
    "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/ and ETHUSDT/1d/"
)
_BARS_NOTE = (
    "Committed BTC/ETH daily OHLC fixture for Study 4. The signal forms after Sunday "
    "close and fills at Monday open, so both open and close are required. Upstream "
    "Binance Vision zip paths, file hashes, and published checksums are recorded in "
    "tests/data/btc_eth_daily_ohlc_sources.json."
)
_SOURCES_NOTE = (
    "Committed provenance file listing every Binance Vision monthly spot-kline zip used "
    "to build tests/data/btc_eth_daily_ohlc.csv, including each vendor CHECKSUM hash."
)


def _source_files(source: BinanceVisionSource) -> tuple[SourceFile, ...]:
    files: list[SourceFile] = []
    wanted = set(_month_strings(_START, _END))
    for symbol in _SYMBOLS:
        available = set(source.available_spot_months(symbol, _INTERVAL))
        for month in sorted(wanted & available):
            relpath = f"binance_vision/{symbol}/spot/{symbol}-{_INTERVAL}-{month}.zip"
            path = _RAW_ROOT / relpath
            checksum_path = path.with_name(path.name + ".CHECKSUM")
            published, filename = parse_checksum_line(checksum_path.read_text(encoding="utf-8"))
            if filename != path.name:
                raise RuntimeError(f"{checksum_path.name} refers to {filename}, not {path.name}")
            files.append(
                SourceFile(
                    symbol=symbol,
                    month=month,
                    relpath=relpath,
                    file_sha256=compute_sha256(path),
                    published_checksum=published,
                )
            )
    return tuple(files)


def main() -> None:
    source = BinanceVisionSource(_RAW_ROOT, max_fetch_attempts=4, retry_backoff_s=1.0)
    bars: list[TrendDailyBar] = []
    for symbol in _SYMBOLS:
        records = source.fetch_spot_klines(symbol, _INTERVAL, _START, _END)
        if not records:
            raise RuntimeError(f"no records fetched for {symbol}")
        for rec in records:
            if rec.open is None:
                raise RuntimeError(f"{symbol} {rec.period_end_ts.date()}: missing open")
            bars.append(
                TrendDailyBar(
                    date=rec.period_end_ts.date(),
                    symbol=symbol,
                    open=rec.open,
                    close=rec.close,
                )
            )

    sources = _source_files(source)
    write_bars_csv(_BARS, bars)
    write_source_files_json(_SOURCES, sources)
    fetched = datetime.now(UTC).replace(microsecond=0)
    upsert_entries(
        _MANIFEST,
        (
            SnapshotEntry(
                name="btc-eth-daily-ohlc",
                venue="binance_vision",
                instrument="BTCUSDT,ETHUSDT",
                kind="reproducibility_fixture",
                relpath=_BARS.relative_to(_REPO).as_posix(),
                source_url=_SOURCE_URL,
                fetched_utc=fetched,
                sha256=compute_sha256(_BARS),
                size_bytes=_BARS.stat().st_size,
                rows=len(bars),
                published_checksum=None,
                note=_BARS_NOTE,
            ),
            SnapshotEntry(
                name="btc-eth-daily-ohlc-sources",
                venue="binance_vision",
                instrument="BTCUSDT,ETHUSDT",
                kind="reproducibility_fixture",
                relpath=_SOURCES.relative_to(_REPO).as_posix(),
                source_url=_SOURCE_URL,
                fetched_utc=fetched,
                sha256=compute_sha256(_SOURCES),
                size_bytes=_SOURCES.stat().st_size,
                rows=len(sources),
                published_checksum=None,
                note=_SOURCES_NOTE,
            ),
        ),
    )
    print(f"Wrote {_BARS.relative_to(_REPO).as_posix()} with {len(bars)} rows")
    print(f"Wrote {_SOURCES.relative_to(_REPO).as_posix()} with {len(sources)} source files")
    print(f"Stamped {_MANIFEST.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
