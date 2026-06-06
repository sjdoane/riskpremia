"""Study 4 fixture parsing and tamper-evident hashes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from riskpremia.trend.errors import TrendError
from riskpremia.trend.fixtures import (
    SourceFile,
    TrendDailyBar,
    fixture_sha256,
    read_bars_frame,
    read_source_files_json,
    write_bars_csv,
    write_source_files_json,
)


def test_bars_fixture_round_trips_with_open_and_close(tmp_path: Path) -> None:
    path = tmp_path / "bars.csv"
    write_bars_csv(
        path,
        [
            TrendDailyBar(date(2022, 1, 2), "ETHUSDT", Decimal("10.1"), Decimal("10.5")),
            TrendDailyBar(date(2022, 1, 2), "BTCUSDT", Decimal("20.1"), Decimal("20.5")),
        ],
    )
    frame = read_bars_frame(path)

    assert frame.columns == ["date", "symbol", "open", "close"]
    assert frame["symbol"].to_list() == ["BTCUSDT", "ETHUSDT"]
    assert fixture_sha256(path)


def test_bars_fixture_rejects_duplicate_symbol_date(tmp_path: Path) -> None:
    path = tmp_path / "bars.csv"
    rows = [
        TrendDailyBar(date(2022, 1, 2), "BTCUSDT", Decimal("20.1"), Decimal("20.5")),
        TrendDailyBar(date(2022, 1, 2), "BTCUSDT", Decimal("21.1"), Decimal("21.5")),
    ]

    with pytest.raises(TrendError, match="duplicate bar"):
        write_bars_csv(path, rows)


def test_bars_fixture_reader_rejects_duplicate_symbol_date(tmp_path: Path) -> None:
    path = tmp_path / "bars.csv"
    path.write_text(
        "date,symbol,open,close\n"
        "2022-01-02,BTCUSDT,20.1,20.5\n"
        "2022-01-02,BTCUSDT,21.1,21.5\n",
        encoding="utf-8",
    )

    with pytest.raises(TrendError, match="duplicate bar"):
        read_bars_frame(path)


def test_source_file_provenance_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "sources.json"
    write_source_files_json(
        path,
        (
            SourceFile(
                symbol="BTCUSDT",
                month="2022-01",
                relpath="binance_vision/BTCUSDT/spot/BTCUSDT-1d-2022-01.zip",
                file_sha256="a" * 64,
                published_checksum="b" * 64,
            ),
        ),
    )

    loaded = read_source_files_json(path)
    assert loaded[0].symbol == "BTCUSDT"
    assert loaded[0].published_checksum == "b" * 64
