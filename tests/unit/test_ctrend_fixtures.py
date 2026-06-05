"""The committed CTREND daily-panel fixture: round-trip, guards, and LF byte-stability."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from riskpremia.ctrend.errors import CtrendError
from riskpremia.ctrend.fixtures import (
    daily_panel_content_sha256,
    read_daily_panel,
    write_daily_panel_csv,
    write_daily_panel_gz,
)
from riskpremia.ctrend.universe import build_daily_panel
from riskpremia.data.records import InstrumentId, SpotKlineRecord


def _rec(symbol: str, day: int, close: str, vol: str) -> SpotKlineRecord:
    return SpotKlineRecord(
        instrument=InstrumentId.of("binance_vision", symbol),
        period_end_ts=datetime(2024, 1, day, tzinfo=UTC),
        close=Decimal(close),
        quote_volume=Decimal(vol),
    )


def test_round_trip_reproduces_the_daily_panel(tmp_path: Path) -> None:
    records = [
        _rec("BTCUSDT", 1, "42000.12345678", "1000000.5"),
        _rec("BTCUSDT", 2, "42500.0", "2000000.25"),
        _rec("AAAUSDT", 1, "0.00001234", "0"),  # a microcap close + a zero-volume day
    ]
    path = tmp_path / "panel.csv"
    write_daily_panel_csv(path, records)
    reloaded = read_daily_panel(path)
    expected = build_daily_panel(records)
    assert reloaded.equals(expected)
    # the exact Decimal strings survived (read back through float == build's float cast)
    assert reloaded.filter(
        reloaded["symbol"] == "AAAUSDT"
    )["close"].item() == float(Decimal("0.00001234"))


def test_gz_round_trip_is_deterministic(tmp_path: Path) -> None:
    records = [
        _rec("BTCUSDT", 1, "42000.12345678", "1000000.5"),
        _rec("AAAUSDT", 1, "0.00001234", "0"),
    ]
    gz = tmp_path / "panel.csv.gz"
    write_daily_panel_gz(gz, records)
    assert gz.read_bytes()[:2] == b"\x1f\x8b"  # gzip magic
    assert read_daily_panel(gz).equals(build_daily_panel(records))  # decompress -> same frame
    # mtime=0 makes the gz byte-identical across runs (committed-blob stability), and the
    # decompressed-content SHA is the cross-platform integrity pin
    gz2 = tmp_path / "panel2.csv.gz"
    write_daily_panel_gz(gz2, records)
    assert gz.read_bytes() == gz2.read_bytes()
    assert daily_panel_content_sha256(gz) == daily_panel_content_sha256(gz2)


def test_trailing_zeros_are_stripped_losslessly(tmp_path: Path) -> None:
    path = tmp_path / "panel.csv"
    write_daily_panel_csv(path, [_rec("BTCUSDT", 1, "4.83900000", "343688450.68410000")])
    text = path.read_text()
    assert "BTCUSDT,4.839,343688450.6841\n" in text  # trailing zeros gone
    assert "4.83900000" not in text
    # lossless: the stripped value reads back to the identical float
    assert read_daily_panel(path)["close"].item() == float(Decimal("4.83900000"))


def test_written_bytes_are_lf_only(tmp_path: Path) -> None:
    path = tmp_path / "panel.csv"
    write_daily_panel_csv(path, [_rec("BTCUSDT", 1, "100", "5")])
    raw = path.read_bytes()
    assert b"\r" not in raw  # LF only (cross-platform SHA stability)
    assert raw.startswith(b"date,symbol,close,dollar_volume\n")


def test_write_rejects_bad_records(tmp_path: Path) -> None:
    path = tmp_path / "panel.csv"
    with pytest.raises(CtrendError):
        write_daily_panel_csv(path, [])  # empty
    with pytest.raises(CtrendError):
        write_daily_panel_csv(path, [_rec("BTCUSDT", 1, "0", "5")])  # non-positive close
    with pytest.raises(CtrendError):
        write_daily_panel_csv(path, [_rec("BTCUSDT", 1, "100", "-5")])  # negative volume


def test_read_rejects_bad_header_and_corrupt_close(tmp_path: Path) -> None:
    bad_header = tmp_path / "bad.csv"
    bad_header.write_text("date,symbol,price,vol\n2024-01-01,BTCUSDT,100,5\n", newline="\n")
    with pytest.raises(CtrendError):
        read_daily_panel(bad_header)
    # a tampered close (non-positive) is caught on read via build_daily_panel's guard
    corrupt = tmp_path / "corrupt.csv"
    corrupt.write_text("date,symbol,close,dollar_volume\n2024-01-01,BTCUSDT,0,5\n", newline="\n")
    with pytest.raises(CtrendError):
        read_daily_panel(corrupt)
