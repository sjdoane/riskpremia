"""Unit tests for the constant-maturity bond total-return reconstruction (Study 6)."""

from __future__ import annotations

import math

import pytest

from riskpremia.xtrend.bonds import (
    daily_total_return,
    par_bond_duration_convexity,
    total_return_series,
)
from riskpremia.xtrend.errors import XTrendError


def test_par_bond_duration_matches_known_value() -> None:
    # A ten-year par bond at 5 percent has a modified duration near 7.8 years.
    mod_dur, convexity = par_bond_duration_convexity(0.05)
    assert mod_dur == pytest.approx(7.79, abs=0.05)
    assert convexity > 0.0


def test_duration_falls_as_yield_rises() -> None:
    low, _ = par_bond_duration_convexity(0.02)
    high, _ = par_bond_duration_convexity(0.10)
    assert low > high  # higher yield discounts later cash flows more, shortening duration


def test_flat_yield_earns_carry_only() -> None:
    # With no yield change, the one-day return is the daily coupon accrual.
    tr = daily_total_return(0.045, 0.045)
    assert tr == pytest.approx(0.045 / 252.0, rel=1e-12)


def test_rising_yield_is_a_loss_dominated_by_duration() -> None:
    tr = daily_total_return(0.045, 0.046)
    mod_dur, convexity = par_bond_duration_convexity(0.045)
    expected = 0.045 / 252.0 - mod_dur * 0.001 + 0.5 * convexity * 0.001 * 0.001
    assert tr == pytest.approx(expected, rel=1e-12)
    assert tr < 0.0


def test_falling_yield_is_a_gain() -> None:
    assert daily_total_return(0.045, 0.044) > 0.0


def test_point_in_time_uses_start_of_period_duration() -> None:
    # The duration multiplying the yield change must be the start-of-period yield's,
    # not the end-of-period yield's: the two yields give different durations.
    y_prev, y_now = 0.03, 0.08
    mod_dur_prev, convex_prev = par_bond_duration_convexity(y_prev)
    delta = y_now - y_prev
    expected = y_prev / 252.0 - mod_dur_prev * delta + 0.5 * convex_prev * delta * delta
    assert daily_total_return(y_prev, y_now) == pytest.approx(expected, rel=1e-12)


def test_total_return_series_length_and_alignment() -> None:
    yields = [0.04, 0.041, 0.039, 0.042]
    series = total_return_series(yields)
    assert len(series) == len(yields) - 1
    assert series[0] == pytest.approx(daily_total_return(0.04, 0.041), rel=1e-12)


def test_non_positive_yield_raises() -> None:
    with pytest.raises(XTrendError):
        par_bond_duration_convexity(0.0)
    with pytest.raises(XTrendError):
        daily_total_return(-0.01, 0.01)


def test_total_return_series_needs_two_points() -> None:
    with pytest.raises(XTrendError):
        total_return_series([0.04])


def test_returns_are_finite() -> None:
    for y_prev in (0.005, 0.02, 0.05, 0.10):
        for y_now in (0.005, 0.02, 0.05, 0.10):
            assert math.isfinite(daily_total_return(y_prev, y_now))
