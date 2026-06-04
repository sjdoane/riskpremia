"""Typed records: canonicalization, construction, immutability."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import attrs
import pytest

from riskpremia.data.errors import VenueFetchError
from riskpremia.data.records import (
    FundingRecord,
    InstrumentId,
    derive_canonical,
)


def test_derive_canonical_handles_three_venue_conventions() -> None:
    assert derive_canonical("BTCUSDT") == "BTC"
    assert derive_canonical("ETHUSDT") == "ETH"
    assert derive_canonical("BTC-USDT-SWAP") == "BTC"
    assert derive_canonical("BTC") == "BTC"
    assert derive_canonical("solusdc") == "SOL"
    # BUSD must be stripped before USD (longest-quote-wins), not yield "BTCB".
    assert derive_canonical("BTCBUSD") == "BTC"


def test_derive_canonical_rejects_unparseable() -> None:
    with pytest.raises(VenueFetchError):
        derive_canonical("")
    with pytest.raises(VenueFetchError):
        derive_canonical("123!@#")


def test_instrument_id_of_derives_canonical() -> None:
    inst = InstrumentId.of("binance_vision", "BTCUSDT")
    assert inst.canonical == "BTC"
    explicit = InstrumentId.of("okx", "BTC-USDT-SWAP", canonical="BTC")
    assert explicit.canonical == "BTC"
    assert explicit.symbol == "BTC-USDT-SWAP"


def test_records_are_frozen() -> None:
    inst = InstrumentId.of("binance_vision", "BTCUSDT")
    rec = FundingRecord(
        instrument=inst,
        funding_ts=datetime(2020, 1, 1, tzinfo=UTC),
        funding_rate=Decimal("-0.00012359"),
        funding_interval_hours=8,
        realized=True,
    )
    with pytest.raises(attrs.exceptions.FrozenInstanceError):
        rec.funding_rate = Decimal("0")  # type: ignore[misc]
    assert rec.premium is None
