"""The committed VRP fixtures (ADR 0004 PR5b): the date/close round-trip and the
corrupted-fixture guards (the reproducibility anchor must fail loudly, not silently
produce a wrong premium)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from riskpremia.data.errors import VenueFetchError
from riskpremia.data.records import DvolRecord, SpotPriceRecord
from riskpremia.vrp.fixtures import (
    read_dvol_csv,
    read_spot_csv,
    write_dvol_csv,
    write_spot_csv,
)


def _dvol(n: int) -> list[DvolRecord]:
    d0 = datetime(2023, 1, 1, tzinfo=UTC)
    return [
        DvolRecord(
            "BTC",
            d0 + timedelta(days=i),
            *(Decimal(str(50.0 + i * 0.25)),) * 4,  # o=h=l=c so the boundary stays valid
        )
        for i in range(n)
    ]


def _spot(n: int) -> list[SpotPriceRecord]:
    d0 = datetime(2023, 1, 1, tzinfo=UTC)
    return [
        SpotPriceRecord("binance_spot", "BTCUSDT", "USDT", d0 + timedelta(days=i),
                        Decimal(str(20000.0 + i)))
        for i in range(n)
    ]


def test_dvol_fixture_roundtrip_preserves_date_and_close(tmp_path: Path) -> None:
    recs = _dvol(20)
    path = tmp_path / "dvol.csv"
    write_dvol_csv(path, recs)
    back = read_dvol_csv(path)
    assert len(back) == len(recs)
    for original, restored in zip(recs, back, strict=True):
        assert restored.ts.date() == original.ts.date()
        assert restored.close == original.close  # exact Decimal round-trip
        assert restored.currency == "BTC"


def test_spot_fixture_roundtrip_preserves_date_and_close(tmp_path: Path) -> None:
    recs = _spot(15)
    path = tmp_path / "spot.csv"
    write_spot_csv(path, recs)
    back = read_spot_csv(path)
    assert len(back) == len(recs)
    for original, restored in zip(recs, back, strict=True):
        assert restored.period_end_ts.date() == original.period_end_ts.date()
        assert restored.close == original.close
        assert (restored.spot_venue, restored.spot_symbol, restored.quote) == (
            "binance_spot", "BTCUSDT", "USDT",
        )


def test_fixtures_use_lf_newlines_and_no_cr(tmp_path: Path) -> None:
    # The committed bytes must be LF so the manifest SHA256 is cross-platform stable.
    path = tmp_path / "dvol.csv"
    write_dvol_csv(path, _dvol(5))
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")


def test_read_dvol_rejects_nonpositive_close_through_boundary(tmp_path: Path) -> None:
    # A tampered/corrupt close must raise via the pydantic boundary, not flow a wrong
    # implied variance into the headline (design review C1).
    path = tmp_path / "dvol.csv"
    path.write_text("date,dvol_close\n2023-01-01,-5.0\n", encoding="utf-8", newline="\n")
    with pytest.raises(VenueFetchError, match="positive"):
        read_dvol_csv(path)


def test_read_spot_rejects_nonpositive_close(tmp_path: Path) -> None:
    path = tmp_path / "spot.csv"
    path.write_text("date,close\n2023-01-01,0\n", encoding="utf-8", newline="\n")
    with pytest.raises(VenueFetchError, match="positive"):
        read_spot_csv(path)


def test_read_rejects_wrong_header(tmp_path: Path) -> None:
    path = tmp_path / "dvol.csv"
    path.write_text("date,wrong\n2023-01-01,50.0\n", encoding="utf-8", newline="\n")
    with pytest.raises(VenueFetchError, match="header"):
        read_dvol_csv(path)


def test_write_rejects_duplicate_date(tmp_path: Path) -> None:
    d0 = datetime(2023, 1, 1, tzinfo=UTC)
    dup = [
        DvolRecord("BTC", d0, *(Decimal("50"),) * 4),
        DvolRecord("BTC", d0 + timedelta(hours=12), *(Decimal("51"),) * 4),  # same date
    ]
    with pytest.raises(VenueFetchError, match="duplicate date"):
        write_dvol_csv(tmp_path / "dvol.csv", dup)
