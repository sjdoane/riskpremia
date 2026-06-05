"""Binance Vision source, offline (committed zip + S3-listing XML fixtures).

`urllib.request.urlopen` is monkeypatched for the listing test; the cache path
test pre-places the real committed zip so the verify + parse path runs with no
network. The live end-to-end pull is in tests/integration (network-marked).
"""

from __future__ import annotations

import hashlib
import io
import shutil
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from riskpremia.data.errors import VenueFetchError
from riskpremia.data.records import InstrumentId
from riskpremia.data.sources.binance_vision import (
    SURVIVOR_UNIVERSE,
    BinanceVisionSource,
    _kline_close_time_to_ms,
    _month_strings,
)

_FIXTURES = Path(__file__).resolve().parents[1] / "data"


def test_kline_close_time_handles_ms_and_us() -> None:
    # 2024-06-30 ms stamp passes through; the late-2024 microsecond stamp converts.
    ms = 1_719_792_000_000  # 2024-07-01 ms
    assert _kline_close_time_to_ms(ms) == ms
    us = 1_735_718_399_999_999  # 2024-12-31 23:59:59.999999 us (the format Binance switched to)
    assert _kline_close_time_to_ms(us) == us // 1000 == 1_735_718_399_999
    # A seconds stamp (10-digit) or other malformed value raises, never mis-scales.
    with pytest.raises(VenueFetchError):
        _kline_close_time_to_ms(1_719_792_000)  # seconds
_ZIP = _FIXTURES / "BTCUSDT-fundingRate-2020-01.zip"
_CHECKSUM = _FIXTURES / "BTCUSDT-fundingRate-2020-01.zip.CHECKSUM"
_S3_XML = _FIXTURES / "s3_listing_btcusdt_funding.xml"


class _FakeResp:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def test_survivor_universe_is_pre_committed() -> None:
    # Finding C4: a fixed survivor set, not a survivorship-inflated multi-coin median.
    assert SURVIVOR_UNIVERSE == ("BTCUSDT", "ETHUSDT")


def test_month_strings_window() -> None:
    s = datetime(2020, 1, 1, tzinfo=UTC)
    assert _month_strings(s, datetime(2020, 3, 1, tzinfo=UTC)) == ["2020-01", "2020-02"]
    # a sub-month window still maps to the one containing month
    assert _month_strings(s, datetime(2020, 1, 2, tzinfo=UTC)) == ["2020-01"]
    # cross-year
    assert _month_strings(datetime(2020, 12, 15, tzinfo=UTC), datetime(2021, 2, 1, tzinfo=UTC)) == [
        "2020-12",
        "2021-01",
    ]
    with pytest.raises(VenueFetchError):
        _month_strings(s, s)


def test_parse_funding_zip_real_fixture() -> None:
    src = BinanceVisionSource(Path("unused"))
    recs = src._parse_funding_zip(_ZIP, InstrumentId.of("binance_vision", "BTCUSDT"))
    assert len(recs) == 93  # 94 CSV lines minus the header
    assert recs[0].funding_ts == datetime(2020, 1, 1, tzinfo=UTC)
    assert recs[0].funding_rate == Decimal("-0.00012359")
    assert recs[0].funding_interval_hours == 8
    assert recs[0].realized is True


def test_fetch_funding_uses_cache_no_network(tmp_path: Path) -> None:
    # Pre-place the real zip + CHECKSUM so the verify + parse path runs offline.
    cache = tmp_path / "binance_vision" / "BTCUSDT"
    cache.mkdir(parents=True)
    shutil.copy(_ZIP, cache / _ZIP.name)
    shutil.copy(_CHECKSUM, cache / (_ZIP.name + ".CHECKSUM"))
    src = BinanceVisionSource(tmp_path)
    recs = src.fetch_funding(
        "BTCUSDT", datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 2, 1, tzinfo=UTC)
    )
    assert len(recs) == 93
    assert all(r.realized for r in recs)
    # window filter excludes everything outside [start, end)
    narrow = src.fetch_funding(
        "BTCUSDT", datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 2, tzinfo=UTC)
    )
    assert 0 < len(narrow) < 93


def test_fetch_funding_redownloads_on_corrupt_cache(tmp_path: Path) -> None:
    # A drifted cache (wrong bytes) is detected and, offline, the re-fetch fails
    # loudly rather than returning corrupt data.
    cache = tmp_path / "binance_vision" / "BTCUSDT"
    cache.mkdir(parents=True)
    (cache / _ZIP.name).write_bytes(b"corrupted not-a-zip")
    shutil.copy(_CHECKSUM, cache / (_ZIP.name + ".CHECKSUM"))
    src = BinanceVisionSource(tmp_path, base_url="http://127.0.0.1:0")  # unreachable
    with pytest.raises((OSError, urllib.error.URLError)):
        src.fetch_funding(
            "BTCUSDT", datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 2, 1, tzinfo=UTC)
        )


def test_available_months_and_retention_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    xml = _S3_XML.read_bytes()
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=0: _FakeResp(xml))
    src = BinanceVisionSource(Path("unused"))
    months = src.available_months("BTCUSDT")
    assert months[0] == "2020-01"
    assert len(months) == 77
    assert src.retention_floor("BTCUSDT") == datetime(2020, 1, 1, tzinfo=UTC)


def _make_kline_zip(path: Path, lines: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(path.name.replace(".zip", ".csv"), "\n".join(lines))


def test_parse_kline_zip_with_and_without_header(tmp_path: Path) -> None:
    src = BinanceVisionSource(Path("unused"))
    # high = col 2 (9100), low = col 3 (8900), close = col 4 (9050.5), close_time = col 6,
    # quote_asset_volume = col 7 (the USD dollar volume); all returned in the 5-tuple.
    data_row = "1577836800000,9000,9100,8900,9050.5,10,1577865599999,90500.25,0,0,0,0"
    header = "open_time,open,high,low,close,volume,close_time,qv,count,tb,tbq,ignore"
    expected = [
        (1577865599999, Decimal("9100"), Decimal("8900"), Decimal("9050.5"), Decimal("90500.25"))
    ]

    no_header = tmp_path / "k1.zip"
    _make_kline_zip(no_header, [data_row])
    assert src._parse_kline_zip(no_header) == expected

    with_header = tmp_path / "k2.zip"
    _make_kline_zip(with_header, [header, data_row])
    assert src._parse_kline_zip(with_header) == expected


def _funding_zip(month: str, rows: list[str]) -> tuple[bytes, bytes]:
    """Build a synthetic funding zip + its matching CHECKSUM line (bytes)."""
    csv_text = chr(10).join(["calc_time,funding_interval_hours,last_funding_rate", *rows, ""])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("BTCUSDT-fundingRate-" + month + ".csv", csv_text)
    zip_bytes = buf.getvalue()
    sha = hashlib.sha256(zip_bytes).hexdigest()
    checksum = (sha + "  BTCUSDT-fundingRate-" + month + ".zip" + chr(10)).encode()
    return zip_bytes, checksum


def _dispatch(mapping: dict[str, bytes]):
    def fake_urlopen(url: str, timeout: float = 0) -> _FakeResp:
        for suffix, data in mapping.items():
            if url.endswith(suffix):
                return _FakeResp(data)
        raise AssertionError("unexpected url " + url)

    return fake_urlopen


def test_fetch_funding_multi_month(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    jan_zip, jan_ck = _funding_zip("2020-01", ["1577836800000,8,-0.0001"])
    feb_zip, feb_ck = _funding_zip("2020-02", ["1580515200000,8,0.0002"])
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        _dispatch(
            {
                "BTCUSDT-fundingRate-2020-01.zip.CHECKSUM": jan_ck,
                "BTCUSDT-fundingRate-2020-01.zip": jan_zip,
                "BTCUSDT-fundingRate-2020-02.zip.CHECKSUM": feb_ck,
                "BTCUSDT-fundingRate-2020-02.zip": feb_zip,
            }
        ),
    )
    src = BinanceVisionSource(tmp_path)
    recs = src.fetch_funding(
        "BTCUSDT", datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 3, 1, tzinfo=UTC)
    )
    assert len(recs) == 2  # one row from each of the two months in the window
    assert recs[0].funding_ts.month == 1
    assert recs[1].funding_ts.month == 2


def test_corrupt_cache_recovers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache = tmp_path / "binance_vision" / "BTCUSDT"
    cache.mkdir(parents=True)
    (cache / _ZIP.name).write_bytes(b"corrupted not-a-zip")  # drifted cache
    shutil.copy(_CHECKSUM, cache / (_ZIP.name + ".CHECKSUM"))  # real (cached) checksum
    real_zip = _ZIP.read_bytes()
    monkeypatch.setattr(urllib.request, "urlopen", _dispatch({_ZIP.name: real_zip}))
    src = BinanceVisionSource(tmp_path)
    recs = src.fetch_funding(
        "BTCUSDT", datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 2, 1, tzinfo=UTC)
    )
    assert len(recs) == 93  # recovered: corrupt cache detected, re-fetched, re-verified
    repaired = hashlib.sha256((cache / _ZIP.name).read_bytes()).hexdigest()
    assert repaired == hashlib.sha256(real_zip).hexdigest()
