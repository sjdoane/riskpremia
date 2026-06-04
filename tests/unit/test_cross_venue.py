"""The Binance-vs-OKX funding delta (the venue-basis measurement)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from riskpremia.data.clock import ms_to_utc, normalize_funding_frame
from riskpremia.data.cross_venue import binance_okx_funding_delta
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.records import FundingRecord, InstrumentId

_BASE_MS = 1780531200000
_STEP_MS = 8 * 3600 * 1000


def _funding(venue: str, symbol: str, rates: list[float], n_offset: int = 0) -> list[FundingRecord]:
    inst = InstrumentId.of(venue, symbol)
    return [
        FundingRecord(
            instrument=inst,
            funding_ts=ms_to_utc(_BASE_MS + (i + n_offset) * _STEP_MS),
            funding_rate=Decimal(str(r)),
            funding_interval_hours=8,
            realized=True,
        )
        for i, r in enumerate(rates)
    ]


def test_delta_inner_joins_on_canonical_dt_and_subtracts() -> None:
    # Binance BTCUSDT and OKX BTC-USDT-SWAP share canonical "BTC" and the dt grid.
    binance = normalize_funding_frame(
        _funding("binance_vision", "BTCUSDT", [0.0001, 0.0002, 0.0003])
    )
    okx = normalize_funding_frame(_funding("okx", "BTC-USDT-SWAP", [0.00008, 0.00015, 0.00031]))
    delta = binance_okx_funding_delta(binance, okx)
    assert delta.columns == [
        "canonical", "dt", "funding_rate_binance", "funding_rate_okx", "funding_delta"
    ]
    assert delta.height == 3
    assert delta["canonical"].unique().to_list() == ["BTC"]
    # delta = binance - okx, element-wise on the matched grid
    got = delta["funding_delta"].to_list()
    assert abs(got[0] - (0.0001 - 0.00008)) < 1e-12
    assert abs(got[2] - (0.0003 - 0.00031)) < 1e-12


def test_delta_keeps_only_the_overlap() -> None:
    # Binance has 5 events; OKX (recent-only) overlaps the last 3.
    binance = normalize_funding_frame(_funding("binance_vision", "BTCUSDT", [0.0001] * 5))
    okx = normalize_funding_frame(_funding("okx", "BTC-USDT-SWAP", [0.00009] * 3, n_offset=2))
    delta = binance_okx_funding_delta(binance, okx)
    assert delta.height == 3  # only the overlapping events survive the inner join
    assert delta["dt"].min() == ms_to_utc(_BASE_MS + 2 * _STEP_MS)


def test_delta_is_sorted() -> None:
    binance = normalize_funding_frame(_funding("binance_vision", "BTCUSDT", [0.0001, 0.0002]))
    okx = normalize_funding_frame(_funding("okx", "BTC-USDT-SWAP", [0.00009, 0.00018]))
    delta = binance_okx_funding_delta(binance, okx)
    assert delta["dt"].is_sorted()


def _rec(venue: str, symbol: str, ms: int, rate: str) -> FundingRecord:
    return FundingRecord(
        instrument=InstrumentId.of(venue, symbol),
        funding_ts=ms_to_utc(ms),
        funding_rate=Decimal(rate),
        funding_interval_hours=8,
        realized=True,
    )


def test_delta_snaps_millisecond_jitter_to_grid() -> None:
    # Binance calc_time jitters a few ms past the settlement instant; OKX is on it.
    binance = normalize_funding_frame(
        [
            _rec("binance_vision", "BTCUSDT", _BASE_MS + 3, "0.0001"),
            _rec("binance_vision", "BTCUSDT", _BASE_MS + _STEP_MS + 1, "0.0002"),
        ]
    )
    okx = normalize_funding_frame(
        [
            _rec("okx", "BTC-USDT-SWAP", _BASE_MS, "0.00009"),
            _rec("okx", "BTC-USDT-SWAP", _BASE_MS + _STEP_MS, "0.00019"),
        ]
    )
    delta = binance_okx_funding_delta(binance, okx)
    assert delta.height == 2  # both align after grid-snapping despite the ms jitter
    assert delta["dt"].to_list() == [ms_to_utc(_BASE_MS), ms_to_utc(_BASE_MS + _STEP_MS)]


def test_delta_raises_when_grid_snap_collapses_real_events() -> None:
    # A mostly-8h series with one extra event 2h after the 08:00 boundary passes
    # normalize (median gap ~8h) but the +08:00 and +10:00 events both snap to the
    # 08:00 grid point, so the delta must fail loudly rather than silently merge.
    hour = 3600 * 1000
    binance = normalize_funding_frame(
        [
            _rec("binance_vision", "BTCUSDT", _BASE_MS, "0.0001"),
            _rec("binance_vision", "BTCUSDT", _BASE_MS + 8 * hour, "0.0002"),
            _rec("binance_vision", "BTCUSDT", _BASE_MS + 10 * hour, "0.0003"),
            _rec("binance_vision", "BTCUSDT", _BASE_MS + 16 * hour, "0.0004"),
            _rec("binance_vision", "BTCUSDT", _BASE_MS + 24 * hour, "0.0005"),
        ]
    )
    okx = normalize_funding_frame([_rec("okx", "BTC-USDT-SWAP", _BASE_MS, "0.00009")])
    with pytest.raises(VenueFetchError):
        binance_okx_funding_delta(binance, okx)
