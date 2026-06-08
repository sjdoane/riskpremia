"""Volatility-managed market portfolio: the signal, the c-normalization, and the daily series.

Study 8 (ADR 0010, with the design-review amendment). The managed weight scales inversely to the
previous calendar month's realized variance of the daily market excess return (Moreira-Muir),
normalized so the UNCAPPED managed series matches the unmanaged full-sample volatility (the c is
computed on the uncapped series, the leverage cap is a separate friction). The daily managed and
unmanaged excess-over-bill series and their difference are built with one coherent cost model: the
expense ratio on the equity exposure, the financing spread on the levered portion, and the
per-side turnover on the continuous monthly weight change. The long-short factor variant (the
secondary) is not built here.

The market excess return is `equity_ret - cash_ret` from the committed Study 6 panel (the Kenneth
French daily market total return minus the one-month bill), so the primary needs no new data.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from datetime import date

import attrs
import polars as pl

from riskpremia.volmanaged.errors import VolManagedError

TRADING_DAYS_PER_YEAR = 252.0
LEVERAGE_CAP = 2.0
EXPENSE_ANNUAL = 0.0010
FINANCING_SPREAD_ANNUAL = 0.010  # 1.0 percent over the bill on the levered leg (primary)
TURNOVER_COST_PER_SIDE = 0.0005
EXPANDING_BURNIN_MONTHS = 60
DEFAULT_RV_MONTHS = 1
EWMA_LAMBDA = 0.94
INCEPTION_WEIGHT = 1.0  # the managed book starts holding the market (the unmanaged baseline)


@attrs.frozen(slots=True)
class VMKnobs:
    """The frozen construction knobs (one spec of the managed rule)."""

    cap: float = LEVERAGE_CAP
    expense_annual: float = EXPENSE_ANNUAL
    financing_spread_annual: float = FINANCING_SPREAD_ANNUAL
    turnover_cost_per_side: float = TURNOVER_COST_PER_SIDE
    trading_days_per_year: float = TRADING_DAYS_PER_YEAR
    rv_months: int = DEFAULT_RV_MONTHS
    estimator: str = "realized"  # "realized" (sum of squared daily) or "ewma"
    burnin_months: int = EXPANDING_BURNIN_MONTHS


@attrs.frozen(slots=True)
class VMDailySeries:
    """The aligned daily managed, unmanaged, and difference excess-over-bill series."""

    dates: tuple[date, ...]
    managed_excess: tuple[float, ...]
    unmanaged_excess: tuple[float, ...]
    difference: tuple[float, ...]
    managed_total: tuple[float, ...]  # net total return (excess plus bill), for the wealth path
    weights: tuple[float, ...]
    c_value: float
    mean_weight: float
    max_weight: float
    frac_capped: float
    frac_levered: float
    mean_turnover: float
    total_financing_cost: float
    total_turnover_cost: float
    total_expense_cost: float


def market_excess(panel: pl.DataFrame) -> tuple[list[date], list[float], list[float]]:
    """Return the sorted (dates, daily market excess returns, daily bill returns) from the panel.

    The market excess return is `equity_ret - cash_ret`; the bill return `cash_ret` is carried for
    the managed wealth path. Raises when required columns are missing or dates are not unique.
    """
    required = {"date", "equity_ret", "cash_ret"}
    missing = required - set(panel.columns)
    if missing:
        raise VolManagedError(f"panel missing required columns {sorted(missing)}")
    frame = panel.sort("date")
    dates: list[date] = []
    excess: list[float] = []
    cash: list[float] = []
    for row in frame.iter_rows(named=True):
        d = row["date"]
        if not isinstance(d, date):
            raise VolManagedError(f"expected date, got {d!r}")
        dates.append(d)
        excess.append(float(row["equity_ret"]) - float(row["cash_ret"]))
        cash.append(float(row["cash_ret"]))
    if len(set(dates)) != len(dates):
        raise VolManagedError("panel has duplicate dates")
    if len(dates) < 252 * 3:
        raise VolManagedError("panel too short for a volatility-managed study")
    return dates, excess, cash


def _month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def _month_of_day(dates: Sequence[date]) -> list[int]:
    """Map each day index to a 0-based calendar-month ordinal (monotone non-decreasing)."""
    out: list[int] = []
    m = 0
    for i, d in enumerate(dates):
        if i > 0 and _month_key(d) != _month_key(dates[i - 1]):
            m += 1
        out.append(m)
    return out


def _realized_variance(squared: Sequence[float]) -> float:
    return math.fsum(squared)


def monthly_variance(
    month_of_day: Sequence[int], excess: Sequence[float], knobs: VMKnobs
) -> dict[int, float]:
    """Variance estimate available for each month m, formed strictly from data through month m-1.

    For the realized estimator, the value is the sum of squared daily excess returns over the
    prior `rv_months` calendar months (Moreira-Muir). For the EWMA estimator, the value is the
    exponentially-weighted variance through the last day of month m-1 scaled to a monthly basis;
    the scale is immaterial because the c-normalization removes it. The first month with a full
    `rv_months` lookback is the first scorable month.
    """
    n_months = month_of_day[-1] + 1
    squared = [e * e for e in excess]
    days_in_month: dict[int, list[int]] = {}
    for i, m in enumerate(month_of_day):
        days_in_month.setdefault(m, []).append(i)
    out: dict[int, float] = {}
    if knobs.estimator == "ewma":
        var = 0.0
        seeded = False
        month_end_var: dict[int, float] = {}
        for i, sq in enumerate(squared):
            var = sq if not seeded else EWMA_LAMBDA * var + (1.0 - EWMA_LAMBDA) * sq
            seeded = True
            month_end_var[month_of_day[i]] = var  # overwritten until the month's last day
        for m in range(1, n_months):
            prev = month_end_var.get(m - 1)
            if prev is None or prev <= 0.0:
                continue
            out[m] = prev * 21.0
        return out
    if knobs.estimator != "realized":
        raise VolManagedError(f"unknown estimator {knobs.estimator!r}")
    for m in range(knobs.rv_months, n_months):
        window_days: list[int] = []
        for j in range(m - knobs.rv_months, m):
            window_days.extend(days_in_month.get(j, []))
        if not window_days:
            continue
        rv = _realized_variance([squared[i] for i in window_days])
        if rv > 0.0:
            out[m] = rv
    return out


def _raw_weight(rv: float) -> float:
    if rv <= 0.0:
        raise VolManagedError("realized variance must be positive")
    return 1.0 / rv


def _solve_c(
    scored_days: Sequence[int],
    month_of_day: Sequence[int],
    excess: Sequence[float],
    raw_weight_by_month: Mapping[int, float],
) -> float:
    """Closed-form c so the UNCAPPED managed series matches the unmanaged full-sample volatility.

    The uncapped managed excess on day t is `c * raw_weight[m(t)] * excess_t`, whose standard
    deviation is `c` times the standard deviation of `raw_weight[m(t)] * excess_t`; setting it
    equal to the unmanaged standard deviation gives c in closed form (no cap, so it is linear).
    """
    unmanaged = [excess[i] for i in scored_days]
    raw_managed = [raw_weight_by_month[month_of_day[i]] * excess[i] for i in scored_days]
    s_unmanaged = statistics.pstdev(unmanaged)
    s_raw = statistics.pstdev(raw_managed)
    if s_raw <= 0.0:
        raise VolManagedError("uncapped managed series has zero volatility")
    return s_unmanaged / s_raw


def applied_weights(
    dates: Sequence[date],
    excess: Sequence[float],
    knobs: VMKnobs,
    *,
    c_mode: str = "full_sample",
) -> dict[int, float]:
    """The applied (post-c, post-cap) weight for each scorable month.

    `c_mode="full_sample"` uses one closed-form c on the whole scored sample (the Moreira-Muir
    identifying convention, an in-sample normalization). `c_mode="expanding"` recomputes c each
    month from data strictly before that month after a burn-in (the months before the burn-in
    completes hold the market at weight 1.0); this is the real-time, point-in-time analog.
    """
    month_of_day = _month_of_day(dates)
    rv_by_month = monthly_variance(month_of_day, excess, knobs)
    raw_by_month = {m: _raw_weight(rv) for m, rv in rv_by_month.items()}
    scored_months = sorted(raw_by_month)
    if not scored_months:
        raise VolManagedError("no scorable months")
    scored_days = [i for i, m in enumerate(month_of_day) if m in raw_by_month]
    if c_mode == "full_sample":
        c = _solve_c(scored_days, month_of_day, excess, raw_by_month)
        return {m: _clip(c * raw_by_month[m], knobs.cap) for m in scored_months}
    if c_mode != "expanding":
        raise VolManagedError(f"unknown c_mode {c_mode!r}")
    first = scored_months[0]
    out: dict[int, float] = {}
    for m in scored_months:
        prior_days = [i for i in scored_days if month_of_day[i] < m]
        prior_months = m - first
        if prior_months < knobs.burnin_months or len(prior_days) < 2:
            out[m] = 1.0  # burn-in: hold the market until enough history to normalize
            continue
        c_m = _solve_c(prior_days, month_of_day, excess, raw_by_month)
        out[m] = _clip(c_m * raw_by_month[m], knobs.cap)
    return out


def _clip(value: float, cap: float) -> float:
    return max(0.0, min(cap, value))


def build_daily_series(
    dates: Sequence[date],
    excess: Sequence[float],
    cash: Sequence[float],
    knobs: VMKnobs,
    *,
    c_mode: str = "full_sample",
) -> VMDailySeries:
    """Build the daily managed, unmanaged, and difference excess series with the coherent costs.

    Managed excess (net) on day t is `w * excess_t - financing - expense - turnover`, where the
    financing spread is charged on the levered portion `max(w - 1, 0)`, the expense on the equity
    exposure `w`, and the per-side turnover on the monthly weight change `abs(w_m - w_{m-1})`.
    The unmanaged benchmark holds the market at weight 1.0 and carries the same expense, with no
    financing and no turnover. The difference is the managed minus the unmanaged, the kill series.
    """
    month_of_day = _month_of_day(dates)
    weights_by_month = applied_weights(dates, excess, knobs, c_mode=c_mode)
    c_full = (
        _solve_c(
            [i for i, m in enumerate(month_of_day) if m in weights_by_month],
            month_of_day,
            excess,
            {m: _raw_weight(rv) for m, rv in monthly_variance(month_of_day, excess, knobs).items()},
        )
        if c_mode == "full_sample"
        else math.nan
    )
    expense_daily = knobs.expense_annual / knobs.trading_days_per_year
    financing_daily = knobs.financing_spread_annual / knobs.trading_days_per_year

    out_dates: list[date] = []
    managed: list[float] = []
    unmanaged: list[float] = []
    diff: list[float] = []
    managed_total: list[float] = []
    weights: list[float] = []
    turnovers: list[float] = []
    fin_cost = 0.0
    turn_cost = 0.0
    exp_cost = 0.0
    n_capped = 0
    n_levered = 0
    current_month = -1
    w_prev = INCEPTION_WEIGHT
    for i, d in enumerate(dates):
        m = month_of_day[i]
        if m not in weights_by_month:
            continue
        w = weights_by_month[m]
        turnover_today = 0.0
        if m != current_month:
            turnover = abs(w - w_prev)
            turnover_today = turnover * knobs.turnover_cost_per_side
            turnovers.append(turnover)
            turn_cost += turnover_today
            w_prev = w
            current_month = m
        financing_today = financing_daily * max(w - 1.0, 0.0)
        managed_expense = expense_daily * w
        unmanaged_expense = expense_daily
        m_excess = w * excess[i] - financing_today - managed_expense - turnover_today
        u_excess = excess[i] - unmanaged_expense
        fin_cost += financing_today
        exp_cost += managed_expense
        if w >= knobs.cap - 1e-12:
            n_capped += 1
        if w > 1.0 + 1e-12:
            n_levered += 1
        out_dates.append(d)
        managed.append(m_excess)
        unmanaged.append(u_excess)
        diff.append(m_excess - u_excess)
        managed_total.append(m_excess + cash[i])
        weights.append(w)
    if len(diff) < 252:
        raise VolManagedError("fewer than a year of scored observations")
    n = len(weights)
    return VMDailySeries(
        dates=tuple(out_dates),
        managed_excess=tuple(managed),
        unmanaged_excess=tuple(unmanaged),
        difference=tuple(diff),
        managed_total=tuple(managed_total),
        weights=tuple(weights),
        c_value=c_full,
        mean_weight=statistics.fmean(weights),
        max_weight=max(weights),
        frac_capped=n_capped / n,
        frac_levered=n_levered / n,
        mean_turnover=statistics.fmean(turnovers) if turnovers else 0.0,
        total_financing_cost=fin_cost,
        total_turnover_cost=turn_cost,
        total_expense_cost=exp_cost,
    )
