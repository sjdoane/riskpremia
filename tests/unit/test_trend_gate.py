"""Study 4 BTC/ETH trend gate units for the design-review fixes."""

from __future__ import annotations

import math
from datetime import date, timedelta

import polars as pl
import pytest

from riskpremia.execution.cost import VenueCostModel
from riskpremia.trend.errors import TrendError
from riskpremia.trend.gate import (
    DailyEquityPath,
    TrendKnobs,
    _asset_history,
    _bars_by_symbol,
    _build_weekly,
    _max_drawdown,
    _score,
    _WeeklyCalc,
)


def _model(*, spot_taker_bps: float) -> VenueCostModel:
    return VenueCostModel(
        name="unit",
        tradeable=True,
        spot_taker_bps=spot_taker_bps,
        spot_maker_bps=0.0,
        perp_taker_bps=0.0,
        perp_maker_bps=0.0,
        spot_half_spread_bps=0.0,
        perp_half_spread_bps=0.0,
        source="unit test cost model",
    )


def _synthetic_frame() -> pl.DataFrame:
    start = date(2021, 1, 1)
    rows: list[dict[str, object]] = []
    for i in range(410):
        d = start + timedelta(days=i)
        wave = 1.0 + 0.02 * math.sin(i / 7.0)
        for symbol, base in (("BTCUSDT", 100.0), ("ETHUSDT", 50.0)):
            trend = base * math.exp(0.0015 * i) * wave
            open_ = trend * (1.0 + 0.001 * math.sin(i / 3.0))
            close = trend * (1.0 + 0.001 * math.cos(i / 5.0))
            if d == date(2022, 1, 5):
                close *= 0.55
            rows.append({"date": d, "symbol": symbol, "open": open_, "close": close})
    return pl.DataFrame(
        rows,
        schema={"date": pl.Date, "symbol": pl.Utf8, "open": pl.Float64, "close": pl.Float64},
    )


def _patched_frame(changes: dict[tuple[date, str], tuple[float, float]]) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for row in _synthetic_frame().iter_rows(named=True):
        key = (row["date"], row["symbol"])
        if key in changes:
            row["open"], row["close"] = changes[key]
        rows.append(row)
    return pl.DataFrame(
        rows,
        schema={"date": pl.Date, "symbol": pl.Utf8, "open": pl.Float64, "close": pl.Float64},
    )


def test_close_equal_to_sma_is_inactive() -> None:
    start = date(2021, 1, 1)
    closes = ([99.0, 101.0] * 99) + [100.0, 100.0]
    rows = {start + timedelta(days=i): (closes[i], closes[i]) for i in range(len(closes))}
    active, _sma, _returns, _vol = _asset_history(
        rows, start + timedelta(days=len(closes) - 1), TrendKnobs()
    )

    assert active is False


def test_self_financing_cost_is_booked_before_holding_return() -> None:
    weekly, _daily = _build_weekly(
        _synthetic_frame(),
        TrendKnobs(oos_start="2022-01-01"),
        _model(spot_taker_bps=1000.0),
    )
    point = next(w for w in weekly if w.cost_fraction > 0.0 and abs(w.gross_return) > 0.001)

    assert point.net_return == pytest.approx(
        (1.0 - point.cost_fraction) * (1.0 + point.gross_return) - 1.0
    )
    assert point.net_return != pytest.approx(point.gross_return - point.cost_fraction)


def test_signal_fills_and_exits_at_monday_opens_not_closes() -> None:
    fill = date(2022, 1, 3)
    exit_ = date(2022, 1, 10)
    frame = _patched_frame(
        {
            (date(2022, 1, 2), "BTCUSDT"): (500.0, 2000.0),
            (date(2022, 1, 9), "BTCUSDT"): (600.0, 2100.0),
            (fill, "BTCUSDT"): (1000.0, 777.0),
            (exit_, "BTCUSDT"): (1300.0, 2222.0),
        }
    )

    weekly, _daily = _build_weekly(frame, TrendKnobs(oos_start="2022-01-01"), _model(
        spot_taker_bps=0.0
    ))
    point = next(w for w in weekly if w.fill_date == fill)

    assert point.signal_date == date(2022, 1, 2)
    assert point.exit_date == exit_
    assert point.asset_returns["BTCUSDT"] == pytest.approx(0.3)
    assert point.asset_returns["BTCUSDT"] != pytest.approx(2222.0 / 777.0 - 1.0)
    assert point.asset_returns["BTCUSDT"] != pytest.approx(2100.0 / 2000.0 - 1.0)


def test_daily_drawdown_reads_intraperiod_marks() -> None:
    weekly, daily = _build_weekly(
        _synthetic_frame(),
        TrendKnobs(oos_start="2022-01-01"),
        _model(spot_taker_bps=0.0),
    )

    assert weekly
    assert "daily_close" in daily.kind
    assert _max_drawdown(daily.equity) > 0.0
    assert min(daily.equity) < max(daily.equity)


def test_daily_drawdown_catches_midweek_crash_with_endpoint_recovery() -> None:
    fill = date(2022, 1, 3)
    crash = date(2022, 1, 5)
    exit_ = date(2022, 1, 10)
    changes: dict[tuple[date, str], tuple[float, float]] = {}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        changes[(fill, symbol)] = (100.0, 100.0)
        changes[(crash, symbol)] = (100.0, 1.0)
        changes[(exit_, symbol)] = (100.0, 100.0)
    frame = _patched_frame(changes)

    weekly, daily = _build_weekly(frame, TrendKnobs(oos_start="2022-01-01"), _model(
        spot_taker_bps=0.0
    ))
    first = next(w for w in weekly if w.fill_date == fill)
    crash_marks = [
        equity
        for dt, kind, equity in zip(daily.date, daily.kind, daily.equity, strict=True)
        if dt == crash.isoformat() and kind == "daily_close"
    ]

    assert sum(first.target.values()) == pytest.approx(1.0)
    assert first.gross_return == pytest.approx(0.0)
    assert crash_marks and min(crash_marks) < 0.05
    assert _max_drawdown(daily.equity) > 0.95


def test_cash_return_is_fixed_at_zero_yield_cash() -> None:
    with pytest.raises(TrendError, match="zero-yield cash"):
        _build_weekly(
            _synthetic_frame(),
            TrendKnobs(oos_start="2022-01-01", cash_return=0.01),
            _model(spot_taker_bps=0.0),
        )


def test_target_notional_never_exceeds_cap() -> None:
    weekly, _daily = _build_weekly(
        _synthetic_frame(),
        TrendKnobs(oos_start="2022-01-01"),
        _model(spot_taker_bps=0.0),
    )

    assert max(sum(w.target.values()) for w in weekly) <= 1.0 + 1e-12
    assert all(sum(w.pretrade.values()) <= 1.05 for w in weekly)


def test_bars_by_symbol_requires_btc_and_eth() -> None:
    frame = pl.DataFrame(
        {"date": [date(2022, 1, 1)], "symbol": ["BTCUSDT"], "open": [1.0], "close": [1.0]},
        schema={"date": pl.Date, "symbol": pl.Utf8, "open": pl.Float64, "close": pl.Float64},
    )
    with pytest.raises(ValueError):
        _bars_by_symbol(frame)


def test_cost_share_fails_when_compounded_gross_edge_is_not_positive() -> None:
    start = date(2022, 1, 3)
    weekly = []
    equity = []
    for i in range(24):
        fill = start + timedelta(days=7 * i)
        weekly.append(
            _WeeklyCalc(
                signal_date=fill - timedelta(days=1),
                fill_date=fill,
                exit_date=fill + timedelta(days=7),
                target={"BTCUSDT": 0.5, "ETHUSDT": 0.5},
                pretrade={"BTCUSDT": 0.5, "ETHUSDT": 0.5},
                turnover=0.1,
                cost_fraction=0.001,
                cost_paid=0.001,
                asset_returns={"BTCUSDT": -0.01 - i * 0.0001, "ETHUSDT": -0.012},
                gross_return=-0.011 - i * 0.0001,
                net_return=-0.012 - i * 0.0001,
                estimated_vol=0.25,
                corr_one_vol=0.25,
                active_assets=2,
                wealth_before=1.0 - i * 0.005,
            )
        )
        equity.append(1.0 - i * 0.005)

    score = _score(
        weekly,
        DailyEquityPath(
            date=tuple((start + timedelta(days=i)).isoformat() for i in range(24)),
            kind=tuple("daily_close" for _ in range(24)),
            equity=tuple(equity),
        ),
        TrendKnobs(),
    )

    assert math.isinf(score.total_cost_share)
    assert score.passes_cost_share is False
