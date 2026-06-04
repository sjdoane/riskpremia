"""Per-trade carry P&L: the funding sign, the index identity, P&L conservation,
the batch/scalar parity, the static-notional price_pnl, and the wall-clock
financing (ADR 0003 PR4a). The three kill_gate-marked tests pin the invariants
whose failure would void the kill gate (the net number and the CPCV label would
then describe different trades)."""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

import polars as pl
import pytest

from riskpremia.data.clock import (
    DT_DTYPE,
    build_observation_frame,
    make_label_horizons,
    marks_frame,
    ms_to_utc,
    normalize_funding_frame,
    spot_frame,
)
from riskpremia.data.records import (
    FundingRecord,
    InstrumentId,
    MarkPriceRecord,
    SpotPriceRecord,
)
from riskpremia.execution.carry import (
    BATCH_SCALAR_ATOL,
    PRICE_PNL_CONTAMINATION_LIMIT,
    funding_window_indices,
    per_interval_pnl,
    price_pnl_contamination,
    simulate_batch,
    simulate_trade,
    valid_entry_range,
)
from riskpremia.execution.cost import KRAKEN, VenueCostModel
from riskpremia.execution.errors import CarryComputationError

_START_MS = 1_577_836_800_000
_8H_MS = 8 * 3600 * 1000

_ZERO_COST = VenueCostModel(
    name="zero",
    tradeable=True,
    spot_taker_bps=0.0,
    spot_maker_bps=0.0,
    perp_taker_bps=0.0,
    perp_maker_bps=0.0,
    spot_half_spread_bps=0.0,
    perp_half_spread_bps=0.0,
    source="test",
    funding_capital_rate=0.0,
)


def _direct_frame(
    rates: list[float | None],
    spot: list[float | None],
    perp: list[float | None],
    *,
    dts: list[datetime] | None = None,
    interval_hours: int = 8,
) -> pl.DataFrame:
    """A direct observation frame (bypasses the clock) for exact-price math tests."""
    n = len(rates)
    if dts is None:
        dts = [ms_to_utc(_START_MS + i * _8H_MS) for i in range(n)]
    return pl.DataFrame(
        {
            "dt": dts,
            "funding_rate": rates,
            "spot_close": spot,
            "perp_close": perp,
            "funding_interval_hours": [interval_hours] * n,
        },
        schema={
            "dt": DT_DTYPE,
            "funding_rate": pl.Float64,
            "spot_close": pl.Float64,
            "perp_close": pl.Float64,
            "funding_interval_hours": pl.Int32,
        },
    )


def _flat_real_frame(rate: str, n: int) -> pl.DataFrame:
    """A frame built through the REAL boundary (Decimal records -> normalize ->
    build_observation_frame) with a constant funding rate and flat prices, so the
    sign survives the actual Decimal->Float64 cast and price_pnl is exactly zero."""
    inst = InstrumentId.of("binance_vision", "BTCUSDT")
    recs = [
        FundingRecord(
            instrument=inst,
            funding_ts=ms_to_utc(_START_MS + i * _8H_MS),
            funding_rate=Decimal(rate),
            funding_interval_hours=8,
            realized=True,
        )
        for i in range(n)
    ]
    marks = marks_frame(
        [MarkPriceRecord(inst, ms_to_utc(_START_MS + i * _8H_MS), Decimal("100")) for i in range(n)]
    )
    spot = spot_frame(
        [
            SpotPriceRecord(
                "binance_vision",
                "BTCUSDT",
                "USDT",
                ms_to_utc(_START_MS + i * _8H_MS),
                Decimal("100"),
            )
            for i in range(n)
        ]
    )
    return build_observation_frame(normalize_funding_frame(recs), marks, spot)


def _oscillating_real_frame(n: int) -> pl.DataFrame:
    """An 8h-grid frame via the clock (no prices), for the index-identity test."""
    inst = InstrumentId.of("binance_vision", "BTCUSDT")
    recs = [
        FundingRecord(
            instrument=inst,
            funding_ts=ms_to_utc(_START_MS + i * _8H_MS),
            funding_rate=Decimal(str(round(-0.0001 + 0.00002 * ((i % 7) - 3), 8))),
            funding_interval_hours=8,
            realized=True,
        )
        for i in range(n)
    ]
    return build_observation_frame(normalize_funding_frame(recs))


@pytest.mark.kill_gate
def test_funding_sign_short_collects_positive_funding() -> None:
    """POSITIVE funding_rate = longs pay shorts; the delta-neutral SHORT book
    collects it. Pinned economically (a positive-funding fixture must net positive),
    neutralizing the records.py 'PAID' wording trap and the negative default fixtures."""
    obs = _flat_real_frame("0.0001", 12)
    trade = simulate_trade(obs, 0, horizon_events=3, cost_model=_ZERO_COST)
    assert trade.funding_collected > 0.0  # short COLLECTS positive funding
    assert math.isclose(trade.price_pnl, 0.0, abs_tol=1e-12)  # flat prices
    assert trade.net_pretax > 0.0  # zero cost, positive funding -> positive net
    # The magnitude is exactly the three collected rates summed.
    assert math.isclose(trade.funding_collected, 3 * 0.0001, rel_tol=1e-9)

    # And the symmetric case: negative funding means the short PAYS (collects < 0).
    obs_neg = _flat_real_frame("-0.0001", 12)
    paid = simulate_trade(obs_neg, 0, horizon_events=3, cost_model=_ZERO_COST)
    assert paid.funding_collected < 0.0
    assert paid.net_pretax < 0.0


@pytest.mark.kill_gate
def test_funding_window_index_identity() -> None:
    """The funding window for entry i is exactly range(i+1, i+H+1), and its last
    settlement is the SAME event make_label_horizons labels with dt.shift(-H)."""
    obs_full = _oscillating_real_frame(200)
    horizon = 3
    observations, horizons = make_label_horizons(obs_full, horizon_events=horizon)
    for i in (0, 1, 50, observations.height - 1):
        window = funding_window_indices(i, horizon)
        assert list(window) == list(range(i + 1, i + horizon + 1))
        # the last collected funding settles at the CPCV label horizon (dt.shift(-H))
        assert obs_full["dt"][i + horizon] == horizons[i]
        # the set of collected funding dts equals the dt slice over the window
        collected = {obs_full["dt"][j] for j in window}
        assert collected == set(obs_full["dt"][i + 1 : i + horizon + 1].to_list())


@pytest.mark.kill_gate
def test_pnl_conservation() -> None:
    """The per-interval decomposition sums back to net_pretax (the cross-check that
    proves the per-period series and the scalar P&L describe the same trade)."""
    rates = [0.0001 * (1 + (i % 5)) for i in range(20)]
    spot = [100.0 + 0.5 * i for i in range(20)]
    perp = [100.3 + 0.5 * i for i in range(20)]
    obs = _direct_frame(rates, spot, perp)  # type: ignore[arg-type]
    trade = simulate_trade(obs, 2, horizon_events=4, cost_model=KRAKEN)
    parts = per_interval_pnl(trade, obs)
    assert len(parts) == 4
    assert math.isclose(sum(parts), trade.net_pretax, abs_tol=1e-12)
    # funding_collected is exactly the window sum (the economic object).
    window = funding_window_indices(2, 4)
    assert math.isclose(
        trade.funding_collected, sum(obs["funding_rate"][j] for j in window), abs_tol=1e-12
    )


def test_batch_matches_scalar_and_the_entry_boundary() -> None:
    rates = [0.00005 * ((i % 9) - 4) for i in range(60)]
    spot = [100.0 + math.sin(i) for i in range(60)]
    perp = [100.4 + math.sin(i) * 1.01 for i in range(60)]
    obs = _direct_frame(rates, spot, perp)  # type: ignore[arg-type]
    horizon = 5
    batch = simulate_batch(obs, horizon_events=horizon, cost_model=KRAKEN)
    # exactly the valid entries, no silent truncation
    assert batch.height == obs.height - horizon
    assert batch.height == len(valid_entry_range(obs.height, horizon))
    for row in batch.iter_rows(named=True):
        scalar = simulate_trade(obs, row["entry_index"], horizon_events=horizon, cost_model=KRAKEN)
        assert abs(row["funding_collected"] - scalar.funding_collected) < BATCH_SCALAR_ATOL
        assert abs(row["price_pnl"] - scalar.price_pnl) < BATCH_SCALAR_ATOL
        assert abs(row["net_pretax"] - scalar.net_pretax) < BATCH_SCALAR_ATOL
        assert abs(row["hold_hours"] - scalar.hold_hours) < 1e-9
        assert row["exit_index"] == row["entry_index"] + horizon
    # the boundary: the last valid entry works, the first invalid one raises.
    simulate_trade(obs, obs.height - horizon - 1, horizon_events=horizon, cost_model=KRAKEN)
    with pytest.raises(CarryComputationError, match="exit"):
        simulate_trade(obs, obs.height - horizon, horizon_events=horizon, cost_model=KRAKEN)


def test_field_algebra_invariants() -> None:
    rates = [0.0001 * (1 + (i % 5)) for i in range(20)]
    spot = [100.0 + 0.5 * i for i in range(20)]
    perp = [100.3 + 0.4 * i for i in range(20)]
    obs = _direct_frame(rates, spot, perp)  # type: ignore[arg-type]
    t = simulate_trade(obs, 3, horizon_events=4, cost_model=KRAKEN)
    assert math.isclose(t.round_trip_cost, t.entry_cost + t.exit_cost, abs_tol=1e-18)
    assert math.isclose(t.gross, t.funding_collected + t.price_pnl, abs_tol=1e-15)
    assert math.isclose(
        t.net_pretax, t.gross - t.round_trip_cost - t.financing_cost, abs_tol=1e-15
    )


def test_static_notional_price_pnl_is_delta_neutral_on_equal_moves() -> None:
    # Identical spot and perp paths -> the long-spot and short-perp legs cancel.
    path = [100.0 + i for i in range(10)]
    obs = _direct_frame([0.0] * 10, path, path)  # type: ignore[arg-type]
    flat = simulate_trade(obs, 0, horizon_events=3, cost_model=_ZERO_COST)
    assert abs(flat.price_pnl) < 1e-12
    # Perp rallies while spot is flat (basis widens) -> the short perp loses.
    perp_up = [100.0 + i for i in range(10)]
    obs2 = _direct_frame([0.0] * 10, [100.0] * 10, perp_up)  # type: ignore[arg-type]
    widen = simulate_trade(obs2, 0, horizon_events=3, cost_model=_ZERO_COST)
    assert widen.price_pnl < 0.0


def test_financing_uses_real_wall_clock_hold_not_nominal() -> None:
    # An irregular gap (the 3rd interval is 16h, not 8h): a hold spanning it is longer
    # than the nominal H*interval, so the wall-clock financing is larger (conservative).
    base = _START_MS
    h = _8H_MS
    dts = [
        ms_to_utc(base),
        ms_to_utc(base + h),
        ms_to_utc(base + 2 * h),
        ms_to_utc(base + 4 * h),  # 16h gap here
        ms_to_utc(base + 5 * h),
        ms_to_utc(base + 6 * h),
    ]
    obs = _direct_frame([0.0] * 6, [100.0] * 6, [100.0] * 6, dts=dts)  # type: ignore[arg-type]
    trade = simulate_trade(obs, 1, horizon_events=2, cost_model=KRAKEN)  # exit at idx 3
    assert math.isclose(trade.hold_hours, 24.0, abs_tol=1e-6)  # (base+4h) - (base+1h) = 24h
    expected = KRAKEN.funding_capital_rate * KRAKEN.capital_multiple * (24.0 / 8760.0)
    assert math.isclose(trade.financing_cost, expected, abs_tol=1e-15)
    nominal = KRAKEN.funding_capital_rate * KRAKEN.capital_multiple * (16.0 / 8760.0)
    assert trade.financing_cost > nominal  # the nominal H*interval would under-charge


def test_missing_column_raises() -> None:
    obs = pl.DataFrame(
        {"dt": [ms_to_utc(_START_MS)], "funding_rate": [0.0001]},
        schema={"dt": DT_DTYPE, "funding_rate": pl.Float64},
    )
    with pytest.raises(CarryComputationError, match="columns"):
        simulate_trade(obs, 0, horizon_events=1, cost_model=KRAKEN)


def test_null_price_raises_loudly() -> None:
    obs = _direct_frame([0.0001] * 5, [100.0, None, 100.0, 100.0, 100.0], [100.0] * 5)  # type: ignore[arg-type]
    with pytest.raises(CarryComputationError, match="null"):
        simulate_trade(obs, 1, horizon_events=2, cost_model=KRAKEN)


def test_batch_null_price_in_range_raises() -> None:
    spot: list[float | None] = [100.0] * 8
    spot[2] = None  # a data gap inside the valid entry range
    obs = _direct_frame([0.0001] * 8, spot, [100.0] * 8)
    with pytest.raises(CarryComputationError, match="null"):
        simulate_batch(obs, horizon_events=2, cost_model=KRAKEN)


def test_batch_null_funding_rate_in_range_raises() -> None:
    # The batch must reject an interior null FUNDING rate too (the scalar path does),
    # or the same input would diverge between the two paths and a gap would silently
    # shrink the trade count when PR4b takes median()/mean().
    rates: list[float | None] = [0.0001] * 8
    rates[3] = None
    obs = _direct_frame(rates, [100.0] * 8, [100.0] * 8)
    with pytest.raises(CarryComputationError, match="funding"):
        simulate_batch(obs, horizon_events=2, cost_model=KRAKEN)


def test_price_pnl_contamination_guard() -> None:
    # A clean frame: the signed mean price_pnl is a trivial fraction of the funding.
    clean = pl.DataFrame(
        {"funding_collected": [1e-4, 1.2e-4, 0.8e-4], "price_pnl": [1e-6, -2e-6, 3e-6]}
    )
    diag = price_pnl_contamination(clean)
    assert diag["contamination_ratio"] < PRICE_PNL_CONTAMINATION_LIMIT
    assert diag["contaminated"] == 0.0
    # A contaminated frame: a positive signed mean price_pnl half the size of funding.
    dirty = pl.DataFrame(
        {"funding_collected": [1e-4, 1e-4, 1e-4], "price_pnl": [5e-5, 5e-5, 5e-5]}
    )
    assert price_pnl_contamination(dirty)["contaminated"] == 1.0
    # A degenerate zero-mean-funding frame cannot read as clean (infinite ratio).
    degenerate = pl.DataFrame(
        {"funding_collected": [1e-4, -1e-4], "price_pnl": [2e-6, 2e-6]}
    )
    assert price_pnl_contamination(degenerate)["contaminated"] == 1.0
    # And it works on a real batch output (a flat-price frame -> price_pnl == 0).
    obs = _direct_frame([0.0001] * 12, [100.0] * 12, [100.0] * 12)  # type: ignore[arg-type]
    batch = simulate_batch(obs, horizon_events=3, cost_model=_ZERO_COST)
    assert price_pnl_contamination(batch)["mean_price_pnl"] == 0.0


def test_price_pnl_contamination_empty_raises() -> None:
    empty = pl.DataFrame(
        {"funding_collected": [], "price_pnl": []},
        schema={"funding_collected": pl.Float64, "price_pnl": pl.Float64},
    )
    with pytest.raises(CarryComputationError, match="non-empty"):
        price_pnl_contamination(empty)


def test_horizon_below_one_raises() -> None:
    with pytest.raises(CarryComputationError):
        funding_window_indices(0, 0)
    obs = _direct_frame([0.0001] * 5, [100.0] * 5, [100.0] * 5)  # type: ignore[arg-type]
    with pytest.raises(CarryComputationError):
        simulate_batch(obs, horizon_events=0, cost_model=KRAKEN)
