"""Unit tests for the volatility-managed market measurement (Study 8, synthetic returns)."""

from __future__ import annotations

import random
import statistics
from datetime import date, timedelta

import polars as pl
import pytest

from riskpremia.volmanaged.errors import VolManagedError
from riskpremia.volmanaged.measure import (
    VMKnobs,
    _clip,
    _month_of_day,
    build_daily_series,
    market_excess,
    monthly_variance,
)


def _next_weekday(d: date) -> date:
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


def _panel(n_days: int, *, seed: int, daily_vol: float = 0.01) -> pl.DataFrame:
    rng = random.Random(seed)
    d = date(2015, 1, 1)
    dates: list[date] = []
    equity: list[float] = []
    cash: list[float] = []
    for _ in range(n_days):
        d = _next_weekday(d)
        dates.append(d)
        # a mild volatility regime so realized variance actually varies month to month
        vol = daily_vol * (1.5 if (d.month % 3 == 0) else 0.7)
        equity.append(rng.gauss(0.0004, vol) + 0.00005)
        cash.append(0.00005)
    return pl.DataFrame(
        {"date": dates, "equity_ret": equity, "cash_ret": cash},
        schema={"date": pl.Date, "equity_ret": pl.Float64, "cash_ret": pl.Float64},
    )


def test_clip_floors_and_caps() -> None:
    assert _clip(2.5, 2.0) == 2.0
    assert _clip(-0.1, 2.0) == 0.0
    assert _clip(0.7, 2.0) == 0.7


def test_month_of_day_increments_on_month_change() -> None:
    days = [date(2020, 1, 30), date(2020, 1, 31), date(2020, 2, 3), date(2020, 3, 2)]
    assert _month_of_day(days) == [0, 0, 1, 2]


def test_monthly_variance_is_prior_month_sum_of_squares() -> None:
    # two months: month 0 has three days, month 1 inherits month 0's realized variance.
    days = [date(2020, 1, 6), date(2020, 1, 7), date(2020, 1, 8), date(2020, 2, 3)]
    excess = [0.01, -0.02, 0.03, 0.05]
    mov = _month_of_day(days)
    rv = monthly_variance(mov, excess, VMKnobs(rv_months=1))
    assert rv[1] == pytest.approx(0.01**2 + 0.02**2 + 0.03**2)
    assert 0 not in rv  # the first month has no prior month


def test_market_excess_is_equity_minus_cash() -> None:
    panel = _panel(800, seed=1)
    dates, excess, cash = market_excess(panel)
    assert len(dates) == 800
    first = panel.sort("date").row(0, named=True)
    assert excess[0] == pytest.approx(float(first["equity_ret"]) - float(first["cash_ret"]))
    assert cash[0] == pytest.approx(float(first["cash_ret"]))


def test_market_excess_rejects_short_panel() -> None:
    with pytest.raises(VolManagedError):
        market_excess(_panel(100, seed=1))


def test_c_normalization_matches_uncapped_volatility() -> None:
    # With a very high cap (no clipping) and zero costs, the managed and unmanaged full-sample
    # volatilities are equal by the c-normalization construction.
    panel = _panel(900, seed=7)
    dates, excess, cash = market_excess(panel)
    knobs = VMKnobs(
        cap=1000.0, expense_annual=0.0, financing_spread_annual=0.0, turnover_cost_per_side=0.0
    )
    series = build_daily_series(dates, excess, cash, knobs)
    assert statistics.pstdev(series.managed_excess) == pytest.approx(
        statistics.pstdev(series.unmanaged_excess), rel=1e-6
    )


def test_applied_weight_respects_the_cap() -> None:
    panel = _panel(900, seed=3)
    dates, excess, cash = market_excess(panel)
    series = build_daily_series(dates, excess, cash, VMKnobs(cap=2.0))
    assert series.max_weight <= 2.0 + 1e-12
    assert min(series.weights) >= 0.0
    assert 0.5 < series.mean_weight < 1.5  # c-normalization centres the weight near one


def test_financing_cost_lowers_the_difference_mean() -> None:
    # A higher financing spread on the levered leg reduces the managed minus unmanaged mean.
    panel = _panel(900, seed=5)
    dates, excess, cash = market_excess(panel)
    cheap = build_daily_series(dates, excess, cash, VMKnobs(financing_spread_annual=0.0))
    dear = build_daily_series(dates, excess, cash, VMKnobs(financing_spread_annual=0.05))
    assert statistics.fmean(dear.difference) < statistics.fmean(cheap.difference)
    assert dear.total_financing_cost > cheap.total_financing_cost


def test_difference_is_managed_minus_unmanaged() -> None:
    panel = _panel(820, seed=9)
    dates, excess, cash = market_excess(panel)
    series = build_daily_series(dates, excess, cash, VMKnobs())
    for i in range(0, len(series.difference), 37):
        assert series.difference[i] == pytest.approx(
            series.managed_excess[i] - series.unmanaged_excess[i]
        )


def test_expanding_c_burns_in_at_unit_weight() -> None:
    # Before the burn-in completes the expanding-c rule holds the market at weight 1.0.
    panel = _panel(900, seed=11)
    dates, excess, cash = market_excess(panel)
    series = build_daily_series(dates, excess, cash, VMKnobs(burnin_months=120), c_mode="expanding")
    assert series.weights[0] == pytest.approx(1.0)
