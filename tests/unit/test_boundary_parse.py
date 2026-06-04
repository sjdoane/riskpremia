"""The pydantic IO boundary: parse the real Binance Vision funding fixture."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from riskpremia.data.boundary import BINANCE_FUNDING_HEADER, BinanceFundingRow
from riskpremia.data.records import InstrumentId

_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "BTCUSDT-fundingRate-2020-01-sample.csv"


def _read_fixture_rows() -> list[dict[str, str]]:
    with _FIXTURE.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == BINANCE_FUNDING_HEADER
        return list(reader)


def test_fixture_header_matches_verified_schema() -> None:
    with _FIXTURE.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert tuple(header) == BINANCE_FUNDING_HEADER


def test_fixture_rows_round_trip_to_records() -> None:
    rows = _read_fixture_rows()
    inst = InstrumentId.of("binance_vision", "BTCUSDT")
    records = [BinanceFundingRow(**row).to_record(inst) for row in rows]
    assert len(records) == 4
    first = records[0]
    # 1577836800000 ms == 2020-01-01 00:00:00 UTC
    assert first.funding_ts == datetime(2020, 1, 1, tzinfo=UTC)
    assert first.funding_rate == Decimal("-0.00012359")
    assert first.funding_interval_hours == 8
    assert first.realized is True
    assert first.premium is None


def test_boundary_rejects_extra_column() -> None:
    # extra="forbid": a drifted schema must fail loudly, not parse silently.
    with pytest.raises(ValidationError):
        BinanceFundingRow(
            calc_time=1577836800000,
            funding_interval_hours=8,
            last_funding_rate=Decimal("-0.00012359"),
            unexpected_new_column=1,  # type: ignore[call-arg]
        )


def test_boundary_preserves_decimal_exactly() -> None:
    row = BinanceFundingRow(
        calc_time=1577836800000, funding_interval_hours=8, last_funding_rate="0.00039858"
    )
    assert row.last_funding_rate == Decimal("0.00039858")
