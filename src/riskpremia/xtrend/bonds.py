"""Constant-maturity Treasury total-return reconstruction (Study 6, ADR 0008).

The headline long-Treasury sleeve is reconstructed from a single daily constant-maturity
yield series (the US Treasury ten-year par yield, the original source of FRED's DGS10).
The frozen daily total-return formula, point-in-time by construction, is:

    TR_t = y_{t-1} * dt  -  D(y_{t-1}) * (y_t - y_{t-1})  +  0.5 * C(y_{t-1}) * (y_t - y_{t-1})^2

where dt is the daily accrual fraction, and D and C are the modified duration and convexity
(in years and years squared) of a par bond priced at the start-of-period yield y_{t-1}, with
maturity M and semiannual coupons equal to y_{t-1}. The carry term and the duration and
convexity use the start-of-period yield, which is known when the position is formed; only the
yield change uses the end-of-period yield. Duration and convexity are computed by exact
summation over the par bond cash flows (no closed-form transcription), so the formula is
auditable term by term.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from riskpremia.xtrend.errors import XTrendError

# Frozen conventions (ADR 0008): a ten-year par bond, semiannual coupons, 252 trading days.
MATURITY_YEARS: float = 10.0
COUPON_FREQUENCY: int = 2
TRADING_DAYS_PER_YEAR: float = 252.0
DAILY_ACCRUAL: float = 1.0 / TRADING_DAYS_PER_YEAR


def par_bond_duration_convexity(
    annual_yield: float,
    *,
    maturity_years: float = MATURITY_YEARS,
    frequency: int = COUPON_FREQUENCY,
) -> tuple[float, float]:
    """Modified duration (years) and convexity (years squared) of a par coupon bond.

    The bond has face 1, annual yield `annual_yield` (a decimal, e.g. 0.05 for five
    percent), maturity `maturity_years`, and a per-period coupon equal to the per-period
    yield (so the bond prices at par). Duration and convexity are computed by exact
    summation over the cash flows, then converted from periods to years.

    Raises:
      XTrendError: if the yield is not strictly positive or the maturity or frequency
        are not positive (the par-bond cash-flow model needs a positive periodic yield).
    """
    if not math.isfinite(annual_yield) or annual_yield <= 0.0:
        raise XTrendError(f"par-bond yield must be finite and positive; got {annual_yield!r}")
    if maturity_years <= 0.0 or frequency <= 0:
        raise XTrendError("par-bond maturity and frequency must be positive")
    n_periods = int(round(maturity_years * frequency))
    if n_periods < 1:
        raise XTrendError("par-bond needs at least one coupon period")
    i = annual_yield / frequency  # periodic yield equals periodic coupon for a par bond
    price = 0.0
    mac_periods = 0.0
    convexity_periods = 0.0
    for t in range(1, n_periods + 1):
        cash_flow = i + 1.0 if t == n_periods else i
        discount = (1.0 + i) ** (-t)
        present_value = cash_flow * discount
        price += present_value
        mac_periods += t * present_value
        convexity_periods += t * (t + 1) * cash_flow * (1.0 + i) ** (-(t + 2))
    if price <= 0.0:
        raise XTrendError("par-bond price collapsed to non-positive")
    mac_periods /= price
    convexity_periods /= price
    modified_duration_years = (mac_periods / (1.0 + i)) / frequency
    convexity_years = convexity_periods / (frequency * frequency)
    return modified_duration_years, convexity_years


def daily_total_return(
    yield_prev: float,
    yield_now: float,
    *,
    maturity_years: float = MATURITY_YEARS,
    accrual: float = DAILY_ACCRUAL,
) -> float:
    """One day of constant-maturity Treasury total return, point-in-time.

    `yield_prev` and `yield_now` are decimal yields (e.g. 0.045 for 4.5 percent). The
    carry and the duration and convexity use `yield_prev`, the start-of-period yield;
    only the yield change uses `yield_now`.
    """
    modified_duration, convexity = par_bond_duration_convexity(
        yield_prev, maturity_years=maturity_years
    )
    delta_yield = yield_now - yield_prev
    carry = yield_prev * accrual
    price_return = -modified_duration * delta_yield + 0.5 * convexity * delta_yield * delta_yield
    return carry + price_return


def total_return_series(
    yields: Sequence[float],
    *,
    maturity_years: float = MATURITY_YEARS,
    accrual: float = DAILY_ACCRUAL,
) -> list[float]:
    """Daily total returns aligned to `yields[1:]` (the first day has no prior yield).

    `yields` is a date-ordered decimal yield series. The return for day `k` uses
    `yields[k-1]` as the start-of-period yield and `yields[k]` as the end-of-period yield,
    so the output has one fewer element than the input.
    """
    if len(yields) < 2:
        raise XTrendError("total_return_series needs at least two yields")
    return [
        daily_total_return(
            yields[k - 1], yields[k], maturity_years=maturity_years, accrual=accrual
        )
        for k in range(1, len(yields))
    ]
