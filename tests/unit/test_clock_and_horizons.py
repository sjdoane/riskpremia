"""The funding clock: ms normalization, dedup, interval guard, as-of join, horizons."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import polars as pl
import pytest

from riskpremia.data.clock import (
    DT_DTYPE,
    build_observation_frame,
    make_label_horizons,
    ms_to_utc,
    normalize_funding_frame,
)
from riskpremia.data.errors import FundingIntervalError, VenueFetchError
from riskpremia.data.records import FundingRecord, InstrumentId

_START_MS = 1_577_836_800_000  # 2020-01-01 00:00:00 UTC
_8H_MS = 8 * 3600 * 1000


def _funding(
    n: int,
    *,
    step_h: int = 8,
    stamp_h: int = 8,
    rate: float = -0.0001,
    venue: str = "binance_vision",
    symbol: str = "BTCUSDT",
) -> list[FundingRecord]:
    inst = InstrumentId.of(venue, symbol)
    step = step_h * 3600 * 1000
    return [
        FundingRecord(
            instrument=inst,
            funding_ts=ms_to_utc(_START_MS + i * step),
            funding_rate=Decimal(str(rate)),
            funding_interval_hours=stamp_h,
            realized=True,
        )
        for i in range(n)
    ]


def test_ms_to_utc_correct_and_guards_seconds() -> None:
    assert ms_to_utc(_START_MS) == datetime(2020, 1, 1, tzinfo=UTC)
    with pytest.raises(VenueFetchError):
        ms_to_utc(1_577_836_800)  # seconds, not ms


def test_normalize_frame_dtype_is_tz_aware_us_utc() -> None:
    frame = normalize_funding_frame(_funding(10))
    assert frame.schema["dt"] == DT_DTYPE
    assert frame.schema["dt"].time_zone == "UTC"
    assert frame["dt"].is_sorted()
    assert frame.height == 10
    assert "_ingest_idx" not in frame.columns


def test_dedup_collapses_identical_republish() -> None:
    recs = _funding(5)
    # duplicate the third event exactly (a benign re-publish)
    recs.append(recs[2])
    frame = normalize_funding_frame(recs)
    assert frame.height == 5


def test_conflicting_settled_rates_raise() -> None:
    recs = _funding(5)
    inst = recs[0].instrument
    recs.append(
        FundingRecord(
            instrument=inst,
            funding_ts=recs[2].funding_ts,
            funding_rate=Decimal("0.0099"),  # different rate, same stamp, both realized
            funding_interval_hours=8,
            realized=True,
        )
    )
    with pytest.raises(VenueFetchError):
        normalize_funding_frame(recs)


def test_gross_interval_mismatch_raises() -> None:
    # stamped 1h but the events are on an 8h grid: an order-of-magnitude mislabel.
    with pytest.raises(FundingIntervalError):
        normalize_funding_frame(_funding(10, step_h=8, stamp_h=1))


def test_multi_instrument_frame_rejected() -> None:
    recs = _funding(3, symbol="BTCUSDT") + _funding(3, symbol="ETHUSDT")
    with pytest.raises(VenueFetchError):
        normalize_funding_frame(recs)


def test_observation_join_is_backward_never_future() -> None:
    funding = normalize_funding_frame(_funding(3))  # events at 00:00, 08:00, 16:00
    event_dt = funding["dt"].to_list()
    e1 = event_dt[1]  # 08:00
    # one mark strictly before e1 (07:00 = 100.0) and one strictly after (09:00 = 999.0)
    marks = pl.DataFrame(
        {
            "period_end_ts": [e1 - timedelta(hours=1), e1 + timedelta(hours=1)],
            "mark_close": [100.0, 999.0],
        },
        schema={"period_end_ts": DT_DTYPE, "mark_close": pl.Float64},
    )
    obs = build_observation_frame(funding, marks=marks)
    # event 1 must take the EARLIER mark (100.0), never the future 999.0
    row1 = obs.filter(pl.col("dt") == e1)
    assert row1["perp_close"].to_list()[0] == 100.0


def test_basis_float64_matches_decimal_within_tolerance() -> None:
    funding = normalize_funding_frame(_funding(1))
    dt0 = funding["dt"].to_list()[0]
    marks = pl.DataFrame(
        {"period_end_ts": [dt0], "mark_close": [60000.5]},
        schema={"period_end_ts": DT_DTYPE, "mark_close": pl.Float64},
    )
    spot = pl.DataFrame(
        {"period_end_ts": [dt0], "close": [60000.0]},
        schema={"period_end_ts": DT_DTYPE, "close": pl.Float64},
    )
    obs = build_observation_frame(funding, marks=marks, spot=spot)
    got = obs["basis"].to_list()[0]
    want = float((Decimal("60000.5") - Decimal("60000.0")) / Decimal("60000.0"))
    assert abs(got - want) < 1e-9


def test_make_label_horizons_shift_dtype_parity_and_trim() -> None:
    obs = build_observation_frame(normalize_funding_frame(_funding(20)))
    trimmed, horizons = make_label_horizons(obs, horizon_events=3)
    assert trimmed.height == 17
    assert horizons.len() == 17
    assert horizons.dtype == trimmed["dt"].dtype == DT_DTYPE
    assert horizons.null_count() == 0
    full_dt = obs["dt"].to_list()
    assert horizons.to_list() == full_dt[3:]  # horizon of event i is the i+3-th instant


def test_make_label_horizons_requires_more_than_h_rows() -> None:
    obs = build_observation_frame(normalize_funding_frame(_funding(3)))
    with pytest.raises(ValueError):
        make_label_horizons(obs, horizon_events=3)
