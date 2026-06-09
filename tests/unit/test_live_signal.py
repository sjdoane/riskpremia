"""The live signal reproduces the frozen Study 6 rule, and its weighting is well-formed."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from riskpremia.live.errors import LiveError
from riskpremia.live.signal import CASH_SYMBOL, SLEEVE_SYMBOLS, target_from_levels
from riskpremia.xtrend.fixtures import read_panel_frame
from riskpremia.xtrend.gate import (
    SLEEVES,
    XTrendKnobs,
    _daily_from_panel,
    _levels,
    _monthly_close_indices,
    _signal_by_month,
    _sleeve_returns,
)

_PANEL = Path(__file__).resolve().parents[2] / "tests" / "data" / "xtrend_panel.csv"


def test_live_signal_reproduces_backtest_positions_every_month() -> None:
    # The decisive reconciliation: feeding the backtest's own month-end levels into the live signal
    # must reproduce the backtest's per-sleeve active flag at every scored month.
    panel = read_panel_frame(_PANEL)
    knobs = XTrendKnobs()
    daily = _daily_from_panel(panel, knobs)
    month_idx = _monthly_close_indices(daily.dates)
    month_end_dates = [daily.dates[i] for i in month_idx]
    eq_full = _levels(_sleeve_returns(daily, "equity"))
    bd_full = _levels(_sleeve_returns(daily, "bond"))
    eq_levels = [eq_full[i + 1] for i in month_idx]
    bd_levels = [bd_full[i + 1] for i in month_idx]
    backtest = _signal_by_month(daily, knobs.sma_months)

    seen_active = {s: set() for s in SLEEVES}
    checked = 0
    for m in range(knobs.sma_months - 1, len(month_end_dates)):
        target = target_from_levels(
            {"equity": eq_levels[: m + 1], "bond": bd_levels[: m + 1]}, month_end_dates[m], knobs
        )
        for sleeve in SLEEVES:
            assert target.sleeve_active(sleeve) == backtest[m][sleeve]
            seen_active[sleeve].add(backtest[m][sleeve])
        checked += 1
    assert checked > 100
    # the reconciliation is non-vacuous: each sleeve is both in and out across the sample
    for sleeve in SLEEVES:
        assert seen_active[sleeve] == {True, False}


def test_warmup_requires_a_full_window() -> None:
    short = [1.0] * 9  # fewer than the ten-month window
    with pytest.raises(LiveError):
        target_from_levels({"equity": short, "bond": short}, date(2020, 1, 31))


def test_strictly_above_the_average_is_required() -> None:
    flat = [100.0] * 10  # last equals its own average, so the strict rule keeps it in cash
    target = target_from_levels({"equity": flat, "bond": flat}, date(2020, 1, 31))
    assert target.n_active == 0
    assert target.weight(CASH_SYMBOL) == pytest.approx(1.0)


def test_one_active_sleeve_is_half_invested_half_cash() -> None:
    rising = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 120.0]
    flat = [100.0] * 10
    target = target_from_levels({"equity": rising, "bond": flat}, date(2020, 1, 31))
    assert target.sleeve_active("equity") is True
    assert target.sleeve_active("bond") is False
    assert target.weight(SLEEVE_SYMBOLS["equity"]) == pytest.approx(0.5)
    assert target.weight(CASH_SYMBOL) == pytest.approx(0.5)
    assert target.n_active == 1


def test_weights_always_sum_to_one() -> None:
    rising = [100.0 + i for i in range(10)]
    falling = [100.0 - i for i in range(10)]
    for eq, bd in ((rising, rising), (rising, falling), (falling, falling)):
        target = target_from_levels({"equity": eq, "bond": bd}, date(2020, 1, 31))
        assert sum(target.weights.values()) == pytest.approx(1.0)
