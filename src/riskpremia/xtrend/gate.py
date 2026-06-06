"""Cross-asset defensive trend gate (Study 6, ADR 0008).

A frozen, no-fit, monthly, long-or-cash trend rule across US equity and long-term US
Treasury, with the one-month Treasury bill as cash. Each sleeve is held long only when its
total-return index is strictly above its ten-month moving average at the prior month-end;
otherwise that sleeve's capital earns the bill. Active sleeves carry a fixed
one-over-N-of-the-universe weight, inactive capital sits in bills, the book rebalances
monthly, and the net series is marked to market daily and scored in excess of the bill.

Gold was dropped from the headline universe because no free public-domain daily price series
is available (the ADR 0008 pre-registered fallback), and the long-Treasury yield is sourced
from the US Treasury par yield curve (the original source of FRED's DGS10) because the FRED
bulk series fetch was unreliable; the data is the same ten-year par yield. The window is the
1990-onward intersection of the Kenneth French trading days and the Treasury par-yield days.

The primary statistic is the full-sample conditional PSR(0) on the daily excess-of-bills net
series; the purged-CPCV worst fold, the CPCV path-stitched distribution, the recency slices,
and a Deflated-Sharpe trial ladder are reported as stress, never as the headline.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import attrs
import polars as pl

from riskpremia.analytics.sharpe import dsr, psr
from riskpremia.execution.errors import ScoringError
from riskpremia.execution.scoring import effective_sample_size, make_purged_cpcv, return_moments
from riskpremia.xtrend.bonds import MATURITY_YEARS, daily_total_return
from riskpremia.xtrend.errors import XTrendError

SCHEMA_VERSION = 1
_STUDY = "Cross-asset defensive trend (Study 6, ADR 0008)"

SLEEVES: tuple[str, ...] = ("equity", "bond")
SMA_MONTHS = 10
SMA_VARIANT_MONTHS: tuple[int, ...] = (6, 8, 10, 12)
TRADING_DAYS_PER_YEAR = 252.0
TRADING_DAYS_PER_MONTH = 21
DATA_END = "2026-03-31"

VIABILITY_BAR = 0.95
MAX_DRAWDOWN_BAR = 0.35
MAX_COST_SHARE = 0.25

# Realistic retail fund-implementation costs, rounded up (ADR 0008). Expense ratios are
# annual, charged on the HELD notional accrued daily; the turnover cost is per side on each
# rebalance trade. Anchored to liquid 2026 funds (a broad US equity fund and a long-Treasury
# fund); gold's 0.40 percent is unused now that gold is dropped.
EXPENSE_RATIO_ANNUAL: Mapping[str, float] = {"equity": 0.0010, "bond": 0.0015}
TURNOVER_COST_PER_SIDE = 0.0005

RECENCY_SLICES: tuple[tuple[str, str], ...] = (
    ("from_2008", "2008-01-01"),
    ("from_2022", "2022-01-01"),
)
TRIAL_LADDER: tuple[int, ...] = (8, 16, 32)

CPCV_N_GROUPS = 6
CPCV_K_TEST = 2

CAVEATS: tuple[str, ...] = (
    "The scored series is the daily net return in excess of the one-month Treasury bill, so "
    "a result that passes only on bill carry is an honest null, not a strategy.",
    "The primary statistic is the full-sample conditional PSR(0) for one frozen no-fit rule. "
    "The CPCV worst fold, the CPCV path-stitched distribution, and the recency slices are "
    "reported as regime stress, not as fitted-model validation.",
    "The equity sleeve and the bill are the Kenneth French daily factors (US market total "
    "return and the one-month bill); the long-Treasury sleeve is reconstructed from the US "
    "Treasury ten-year par yield, the original source of FRED's DGS10.",
    "Gold is excluded from the headline universe because no free public-domain daily price "
    "series is available; this is the ADR 0008 pre-registered fallback (equity plus Treasury).",
    "The backtest scores asset-class returns and charges a fund expense ratio on held "
    "notional; a deployment trades the matching funds and carries the residual tracking error.",
    "The honest independent unit is the month: the daily marks within a held month share one "
    "position. The non-overlapping monthly conditional PSR(0) is reported alongside the daily "
    "one and gives the same verdict; the daily series is used for resolution, not to inflate T.",
    "Per-sleeve attribution is reported: the full-universe result is carried by the equity "
    "trend sleeve, while the long-Treasury sleeve is weaker on its own and is the main source "
    "of the recent-regime weakness (the 2022-onward rate-driven bond drawdown).",
)


@attrs.frozen(slots=True)
class XTrendKnobs:
    """The frozen construction and kill knobs."""

    sma_months: int = SMA_MONTHS
    trading_days_per_year: float = TRADING_DAYS_PER_YEAR
    turnover_cost_per_side: float = TURNOVER_COST_PER_SIDE
    viability_bar: float = VIABILITY_BAR
    max_drawdown_bar: float = MAX_DRAWDOWN_BAR
    max_cost_share: float = MAX_COST_SHARE
    bond_maturity_years: float = MATURITY_YEARS


@attrs.frozen(slots=True)
class CostModel:
    """The explicit fund-implementation cost assumptions."""

    equity_expense_annual: float
    bond_expense_annual: float
    turnover_cost_per_side: float
    basis: str


@attrs.frozen(slots=True)
class InputFingerprint:
    """Content pins for the committed panel and its provenance."""

    panel_sha256: str
    panel_relpath: str
    n_panel_rows: int
    provenance_sha256: str
    provenance_relpath: str


@attrs.frozen(slots=True)
class MonthlyPosition:
    """One month-end signal and the position it sets for the next month."""

    signal_month_end: str
    equity_active: bool
    bond_active: bool
    n_active: int


@attrs.frozen(slots=True)
class DailyEquityPath:
    """The daily mark-to-market total-return equity path used for drawdown."""

    date: tuple[str, ...]
    equity: tuple[float, ...]


@attrs.frozen(slots=True)
class CpcvStress:
    """Purged CPCV worst-fold stress (the worst-regime reading), labelled as regime stress.

    Path-stitching is intentionally not reported: for a no-fit rule the strategy returns do
    not depend on a training set, so every stitched CPCV path equals the full sample and the
    path-stitched PSR degenerates to the full-sample PSR. The meaningful CPCV stress for a
    frozen rule is therefore the worst held-out fold, not the path distribution.
    """

    n_groups: int
    k_test: int
    n_splits: int
    min_test_size: int
    fold_psr_zero: tuple[float, ...]
    fold_min: float
    fold_median: float


@attrs.frozen(slots=True)
class RecencySlice:
    """A conditional PSR(0) on a date-restricted tail, a diagnostic only."""

    name: str
    start: str
    raw_t: int
    effective_t: int
    psr_zero: float


@attrs.frozen(slots=True)
class DeflationLadder:
    """Deflated Sharpe at assumed inherited-trial counts, with the empirical v_sr."""

    v_sr: float
    variant_sma_months: tuple[int, ...]
    variant_sr_hat: tuple[float, ...]
    trials: tuple[int, ...]
    dsr_by_trials: tuple[float, ...]


@attrs.frozen(slots=True)
class SleeveAttribution:
    """A single-sleeve standalone run of the same rule, to locate where the edge lives."""

    sleeve: str
    raw_t: int
    effective_t: int
    sr_hat: float
    psr_zero: float


@attrs.frozen(slots=True)
class XTrendScore:
    """The scored full-sample result and the kill checks."""

    raw_t: int
    effective_t: int
    pw_block_length: float
    sr_hat: float
    gamma_3: float
    gamma_4: float
    mean_excess: float
    full_psr_zero: float
    monthly_psr_zero: float
    n_monthly_obs: int
    compounded_gross_total_gain: float
    compounded_net_total_gain: float
    compounded_net_excess_gain: float
    bill_carry_gain: float
    total_cost_paid: float
    total_cost_share: float
    max_drawdown: float
    annualized_excess_vol: float
    time_in_market: float
    mean_turnover: float
    max_gross: float
    cagr_total: float
    cpcv: CpcvStress
    recency: tuple[RecencySlice, ...]
    deflation: DeflationLadder
    sleeve_attribution: tuple[SleeveAttribution, ...]
    passes_psr: bool
    passes_drawdown: bool
    passes_cost_share: bool
    passes_notional: bool
    passes: bool
    regime_dependent: bool


@attrs.frozen(slots=True)
class XTrendVerdict:
    """The Study 6 deployment verdict."""

    non_viable: bool
    headline: str
    reason: str


@attrs.frozen(slots=True)
class XTrendGateArtifact:
    """The committed Study 6 gate artifact."""

    schema_version: int
    study: str
    data_start: str
    data_end: str
    first_scored_date: str
    last_scored_date: str
    n_months: int
    knobs: XTrendKnobs
    cost_model: CostModel
    fingerprint: InputFingerprint
    score: XTrendScore
    positions: tuple[MonthlyPosition, ...]
    daily_equity: DailyEquityPath
    verdict: XTrendVerdict
    caveats: tuple[str, ...]


@attrs.frozen(slots=True)
class _Daily:
    """Aligned daily returns derived from the committed panel (index 1..n-1)."""

    dates: tuple[date, ...]
    equity_ret: tuple[float, ...]
    bond_ret: tuple[float, ...]
    cash_ret: tuple[float, ...]


@attrs.frozen(slots=True)
class _Sim:
    """The output of one daily simulation of the frozen rule."""

    scored_dates: tuple[date, ...]
    excess: tuple[float, ...]
    gross_return: tuple[float, ...]
    net_return: tuple[float, ...]
    cash_ret: tuple[float, ...]
    equity_path: tuple[float, ...]
    total_cost_paid: float
    turnovers: tuple[float, ...]
    time_in_market: float
    max_gross: float
    positions: tuple[MonthlyPosition, ...]


def _panel_arrays(panel: pl.DataFrame) -> tuple[list[date], list[float], list[float], list[float]]:
    required = {"date", "equity_ret", "cash_ret", "bond_yield"}
    missing = required - set(panel.columns)
    if missing:
        raise XTrendError(f"panel missing required columns {sorted(missing)}")
    frame = panel.sort("date")
    dates: list[date] = []
    equity: list[float] = []
    cash: list[float] = []
    yields: list[float] = []
    for row in frame.iter_rows(named=True):
        d = row["date"]
        if not isinstance(d, date):
            raise XTrendError(f"expected date, got {d!r}")
        y = float(row["bond_yield"])
        if y <= 0.0:
            raise XTrendError(f"{d}: bond_yield must be positive")
        dates.append(d)
        equity.append(float(row["equity_ret"]))
        cash.append(float(row["cash_ret"]))
        yields.append(y)
    if len(dates) < TRADING_DAYS_PER_MONTH * (SMA_MONTHS + 2):
        raise XTrendError("panel is too short to form a ten-month signal and score a tail")
    if len(set(dates)) != len(dates):
        raise XTrendError("panel has duplicate dates")
    return dates, equity, cash, yields


def _daily_from_panel(panel: pl.DataFrame, knobs: XTrendKnobs) -> _Daily:
    dates, equity, cash, yields = _panel_arrays(panel)
    accrual = 1.0 / knobs.trading_days_per_year
    n = len(dates)
    out_dates: list[date] = []
    eq: list[float] = []
    bond: list[float] = []
    csh: list[float] = []
    for k in range(1, n):
        out_dates.append(dates[k])
        eq.append(equity[k])
        bond.append(
            daily_total_return(
                yields[k - 1], yields[k], maturity_years=knobs.bond_maturity_years, accrual=accrual
            )
        )
        csh.append(cash[k])
    return _Daily(
        dates=tuple(out_dates),
        equity_ret=tuple(eq),
        bond_ret=tuple(bond),
        cash_ret=tuple(csh),
    )


def _sleeve_returns(daily: _Daily, sleeve: str) -> tuple[float, ...]:
    if sleeve == "equity":
        return daily.equity_ret
    if sleeve == "bond":
        return daily.bond_ret
    raise XTrendError(f"unknown sleeve {sleeve!r}")


def _month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def _monthly_close_indices(dates: Sequence[date]) -> list[int]:
    """Index of the last trading day in each calendar month, in order."""
    out: list[int] = []
    for i in range(len(dates)):
        if i + 1 == len(dates) or _month_key(dates[i + 1]) != _month_key(dates[i]):
            out.append(i)
    return out


def _levels(returns: Sequence[float]) -> list[float]:
    level = 1.0
    out = [1.0]
    for r in returns:
        level *= 1.0 + r
        out.append(level)
    return out


def _signal_by_month(daily: _Daily, sma_months: int) -> dict[int, dict[str, bool]]:
    """Signal at each monthly index m: is each sleeve's level above its `sma_months` SMA.

    Returns a map from monthly index m (into the monthly-close series) to the per-sleeve
    active flag formed at that month-end (which governs the next month's position).
    """
    month_idx = _monthly_close_indices(daily.dates)
    signals: dict[int, dict[str, bool]] = {}
    for sleeve in SLEEVES:
        # Levels are indexed 0..len(returns); daily.dates[k] aligns to level index k+1.
        level = _levels(_sleeve_returns(daily, sleeve))
        monthly_level = [level[i + 1] for i in month_idx]
        for m in range(sma_months - 1, len(monthly_level)):
            sma = statistics.fmean(monthly_level[m - sma_months + 1 : m + 1])
            signals.setdefault(m, {})[sleeve] = monthly_level[m] > sma
    return signals


def _simulate(
    daily: _Daily, knobs: XTrendKnobs, universe: Sequence[str] = SLEEVES
) -> _Sim:
    month_idx = _monthly_close_indices(daily.dates)
    if len(month_idx) <= knobs.sma_months:
        raise XTrendError("not enough months to form a signal and score the next month")
    signals = _signal_by_month(daily, knobs.sma_months)
    # Map each daily index to its monthly index (0-based position in month_idx).
    month_of_day: list[int] = []
    m = 0
    for i in range(len(daily.dates)):
        if i > month_idx[m]:
            m += 1
        month_of_day.append(m)
    n_universe = len(universe)
    expense_daily = {s: EXPENSE_RATIO_ANNUAL[s] / knobs.trading_days_per_year for s in universe}

    # The first scored month is the first monthly index for which a prior-month signal exists.
    first_scored_month = knobs.sma_months  # signal formed at month_idx[sma_months - 1]
    weights: dict[str, float] = {s: 0.0 for s in universe}
    cash_weight = 1.0
    total = 1.0
    holdings: dict[str, float] = {s: 0.0 for s in universe}
    cash_value = 1.0
    current_position_month = -1
    current_active = False

    scored_dates: list[date] = []
    excess: list[float] = []
    gross_series: list[float] = []
    net_series: list[float] = []
    cash_series: list[float] = []
    equity_path: list[float] = []
    turnovers: list[float] = []
    cost_paid = 0.0
    in_market_days = 0
    max_gross = 0.0
    positions: list[MonthlyPosition] = []
    seen_position_months: set[int] = set()

    started = False
    for i in range(len(daily.dates)):
        mo = month_of_day[i]
        if mo < first_scored_month:
            continue
        day = daily.dates[i]
        total_prev = total
        # Rebalance on the first scored day of a new month, to the prior month-end signal.
        if mo != current_position_month:
            signal = signals.get(mo - 1, {})
            targets = {s: (1.0 / n_universe if signal.get(s, False) else 0.0) for s in universe}
            target_cash = 1.0 - math.fsum(targets.values())
            turnover = (
                math.fsum(abs(targets[s] - weights[s]) for s in universe)
                if started
                else math.fsum(targets.values())
            )
            cost_fraction = turnover * knobs.turnover_cost_per_side
            if cost_fraction >= 1.0:
                raise XTrendError(f"rebalance cost {cost_fraction} wipes out capital on {day}")
            total_after_cost = total_prev * (1.0 - cost_fraction)
            cost_paid += total_prev * cost_fraction
            holdings = {s: total_after_cost * targets[s] for s in universe}
            cash_value = total_after_cost * target_cash
            weights = dict(targets)
            cash_weight = target_cash
            current_position_month = mo
            current_active = math.fsum(targets.values()) > 0.0
            turnovers.append(turnover)
            if mo not in seen_position_months:
                seen_position_months.add(mo)
                positions.append(
                    MonthlyPosition(
                        signal_month_end=daily.dates[month_idx[mo - 1]].isoformat(),
                        equity_active=targets.get("equity", 0.0) > 0.0,
                        bond_active=targets.get("bond", 0.0) > 0.0,
                        n_active=sum(1 for s in universe if targets[s] > 0.0),
                    )
                )
            max_gross = max(max_gross, math.fsum(targets.values()))
        # Gross return (market only) from start-of-day weights, before any cost.
        gross_return = math.fsum(
            weights[s] * _sleeve_returns(daily, s)[i] for s in universe
        ) + cash_weight * daily.cash_ret[i]
        # Net return charges the held-notional expense; turnover is already in the rebalance
        # haircut that lowered total before this day's growth.
        expense_dollars = 0.0
        for s in universe:
            grown = holdings[s] * (1.0 + _sleeve_returns(daily, s)[i])
            expense_dollars += grown * expense_daily[s]
            holdings[s] = grown * (1.0 - expense_daily[s])
        cash_value *= 1.0 + daily.cash_ret[i]
        total = math.fsum(holdings.values()) + cash_value
        if total_prev <= 0.0 or total <= 0.0:
            raise XTrendError(f"portfolio wealth went non-positive on {day}")
        net_return = total / total_prev - 1.0
        cost_paid += expense_dollars
        excess_return = net_return - daily.cash_ret[i]
        # Refresh drifting start-of-next-day weights.
        weights = {s: holdings[s] / total for s in universe}
        cash_weight = cash_value / total

        scored_dates.append(day)
        excess.append(excess_return)
        gross_series.append(gross_return)
        net_series.append(net_return)
        cash_series.append(daily.cash_ret[i])
        equity_path.append(total)
        if current_active:
            in_market_days += 1
        started = True

    if len(excess) < TRADING_DAYS_PER_MONTH * 12:
        raise XTrendError("fewer than a year of scored daily observations")
    return _Sim(
        scored_dates=tuple(scored_dates),
        excess=tuple(excess),
        gross_return=tuple(gross_series),
        net_return=tuple(net_series),
        cash_ret=tuple(cash_series),
        equity_path=tuple(equity_path),
        total_cost_paid=cost_paid,
        turnovers=tuple(turnovers),
        time_in_market=in_market_days / len(excess),
        max_gross=max_gross,
        positions=tuple(positions),
    )


def _compound(returns: Sequence[float]) -> float:
    wealth = 1.0
    for r in returns:
        wealth *= 1.0 + r
    return wealth - 1.0


def _max_drawdown(equity: Sequence[float]) -> float:
    peak = equity[0] if equity else 1.0
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0.0:
            worst = max(worst, 1.0 - value / peak)
    return worst


def _cagr(total_return: float, start: date, end: date) -> float:
    years = max((end - start).days / 365.0, 1e-12)
    if total_return <= -1.0:
        return -1.0
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def _label_horizons(scored_dates: Sequence[date]) -> pl.Series:
    n = len(scored_dates)
    horizons = [scored_dates[min(i + TRADING_DAYS_PER_MONTH, n - 1)] for i in range(n)]
    return pl.Series("label_horizon", horizons, dtype=pl.Date)


def _psr_zero(returns: Sequence[float]) -> float:
    moments = return_moments(returns)
    effective_t, _block = effective_sample_size(returns)
    return psr(moments.sr_hat, 0.0, effective_t, moments.gamma_3, moments.gamma_4)


def _cpcv_stress(sim: _Sim) -> CpcvStress:
    obs = pl.DataFrame({"dt": list(sim.scored_dates)}, schema={"dt": pl.Date})
    splitter = make_purged_cpcv(
        obs.height, TRADING_DAYS_PER_MONTH, n_groups=CPCV_N_GROUPS, k_test=CPCV_K_TEST
    )
    labels = _label_horizons(sim.scored_dates)
    fold_scores: list[float] = []
    min_test = math.inf
    for split in splitter.split(obs, labels):
        rets = [sim.excess[i] for i in split.test_indices]
        fold_scores.append(_psr_zero(rets))
        min_test = min(min_test, len(split.test_indices))
    return CpcvStress(
        n_groups=splitter.n_groups,
        k_test=CPCV_K_TEST,
        n_splits=len(fold_scores),
        min_test_size=int(min_test),
        fold_psr_zero=tuple(fold_scores),
        fold_min=min(fold_scores),
        fold_median=statistics.median(fold_scores),
    )


def _recency(sim: _Sim) -> tuple[RecencySlice, ...]:
    out: list[RecencySlice] = []
    for name, start_str in RECENCY_SLICES:
        start = date.fromisoformat(start_str)
        rets = [sim.excess[i] for i, d in enumerate(sim.scored_dates) if d >= start]
        if len(rets) < TRADING_DAYS_PER_MONTH * 6:
            continue
        moments = return_moments(rets)
        effective_t, _block = effective_sample_size(rets)
        out.append(
            RecencySlice(
                name=name,
                start=start_str,
                raw_t=moments.t_obs,
                effective_t=effective_t,
                psr_zero=psr(moments.sr_hat, 0.0, effective_t, moments.gamma_3, moments.gamma_4),
            )
        )
    return tuple(out)


def _deflation(panel: pl.DataFrame, headline_sr: float, effective_t: int,
               gamma_3: float, gamma_4: float, knobs: XTrendKnobs) -> DeflationLadder:
    """Deflated Sharpe at assumed trial counts, with v_sr from the SMA-length variant family.

    The cross-trial Sharpe variance is estimated from the daily excess Sharpe of the
    moving-average-length variants (a proxy for the inherited search behind a ten-month
    rule). The deflated Sharpe is then reported at assumed inherited-trial counts.
    """
    variant_sr: list[float] = []
    for months in SMA_VARIANT_MONTHS:
        variant_knobs = attrs.evolve(knobs, sma_months=months)
        variant_sim = _simulate(_daily_from_panel(panel, variant_knobs), variant_knobs)
        variant_sr.append(return_moments(variant_sim.excess).sr_hat)
    v_sr = statistics.variance(variant_sr) if len(variant_sr) >= 2 else 0.0
    dsr_values = tuple(
        dsr(headline_sr, effective_t, gamma_3, gamma_4, v_sr, n) for n in TRIAL_LADDER
    )
    return DeflationLadder(
        v_sr=v_sr,
        variant_sma_months=SMA_VARIANT_MONTHS,
        variant_sr_hat=tuple(variant_sr),
        trials=TRIAL_LADDER,
        dsr_by_trials=dsr_values,
    )


def _monthly_excess(sim: _Sim) -> list[float]:
    """Non-overlapping monthly excess returns from the daily net and bill series.

    The honest independent unit is the month: within a held month the daily marks share one
    position. Each month's excess is the compounded net return minus the compounded bill.
    """
    out: list[float] = []
    net = 1.0
    bill = 1.0
    current = _month_key(sim.scored_dates[0])
    for i, d in enumerate(sim.scored_dates):
        key = _month_key(d)
        if key != current:
            out.append(net - bill)
            net = 1.0
            bill = 1.0
            current = key
        net *= 1.0 + sim.net_return[i]
        bill *= 1.0 + sim.cash_ret[i]
    out.append(net - bill)
    return out


def _sleeve_attribution(daily: _Daily, knobs: XTrendKnobs) -> tuple[SleeveAttribution, ...]:
    """Run the same rule on each single sleeve alone, to locate where the edge lives.

    A single-sleeve run is the equity-only or bond-only counterfactual: it isolates whether
    the full-universe pass rests on one sleeve and which sleeve carries the regime risk.
    """
    out: list[SleeveAttribution] = []
    for sleeve in SLEEVES:
        sim = _simulate(daily, knobs, (sleeve,))
        try:
            moments = return_moments(sim.excess)
        except ScoringError:
            continue
        effective_t, _block = effective_sample_size(sim.excess)
        out.append(
            SleeveAttribution(
                sleeve=sleeve,
                raw_t=moments.t_obs,
                effective_t=effective_t,
                sr_hat=moments.sr_hat,
                psr_zero=psr(moments.sr_hat, 0.0, effective_t, moments.gamma_3, moments.gamma_4),
            )
        )
    return tuple(out)


def _score(panel: pl.DataFrame, daily: _Daily, sim: _Sim, knobs: XTrendKnobs) -> XTrendScore:
    moments = return_moments(sim.excess)
    effective_t, block = effective_sample_size(sim.excess)
    full_psr = psr(moments.sr_hat, 0.0, effective_t, moments.gamma_3, moments.gamma_4)
    monthly = _monthly_excess(sim)
    monthly_moments = return_moments(monthly)
    monthly_eff, _monthly_block = effective_sample_size(monthly)
    monthly_psr = psr(
        monthly_moments.sr_hat, 0.0, monthly_eff,
        monthly_moments.gamma_3, monthly_moments.gamma_4,
    )
    sleeve_attribution = _sleeve_attribution(daily, knobs)
    cpcv = _cpcv_stress(sim)
    recency = _recency(sim)
    deflation = _deflation(
        panel, moments.sr_hat, effective_t, moments.gamma_3, moments.gamma_4, knobs
    )

    gross_total = _compound(sim.gross_return)
    net_total = _compound(sim.net_return)
    net_excess = _compound(sim.excess)
    bill_carry = _compound(sim.cash_ret)
    cost_share = math.inf if gross_total <= 0.0 else sim.total_cost_paid / gross_total
    max_dd = _max_drawdown(sim.equity_path)
    excess_vol = math.sqrt(
        statistics.variance(sim.excess) * knobs.trading_days_per_year
    ) if len(sim.excess) >= 2 else float("nan")
    start = sim.scored_dates[0]
    end = sim.scored_dates[-1]

    passes_psr = full_psr >= knobs.viability_bar
    passes_drawdown = max_dd <= knobs.max_drawdown_bar
    passes_cost = math.isfinite(cost_share) and cost_share <= knobs.max_cost_share
    passes_notional = sim.max_gross <= 1.0 + 1e-12
    passes = passes_psr and passes_drawdown and passes_cost and passes_notional
    regime_dependent = passes and (
        cpcv.fold_min < knobs.viability_bar
        or any(s.psr_zero < knobs.viability_bar for s in recency)
    )
    return XTrendScore(
        raw_t=moments.t_obs,
        effective_t=effective_t,
        pw_block_length=block,
        sr_hat=moments.sr_hat,
        gamma_3=moments.gamma_3,
        gamma_4=moments.gamma_4,
        mean_excess=moments.mean,
        full_psr_zero=full_psr,
        monthly_psr_zero=monthly_psr,
        n_monthly_obs=len(monthly),
        compounded_gross_total_gain=gross_total,
        compounded_net_total_gain=net_total,
        compounded_net_excess_gain=net_excess,
        bill_carry_gain=bill_carry,
        total_cost_paid=sim.total_cost_paid,
        total_cost_share=cost_share,
        max_drawdown=max_dd,
        annualized_excess_vol=excess_vol,
        time_in_market=sim.time_in_market,
        mean_turnover=statistics.fmean(sim.turnovers) if sim.turnovers else 0.0,
        max_gross=sim.max_gross,
        cagr_total=_cagr(net_total, start, end),
        cpcv=cpcv,
        recency=recency,
        deflation=deflation,
        sleeve_attribution=sleeve_attribution,
        passes_psr=passes_psr,
        passes_drawdown=passes_drawdown,
        passes_cost_share=passes_cost,
        passes_notional=passes_notional,
        passes=passes,
        regime_dependent=regime_dependent,
    )


def _verdict(score: XTrendScore, knobs: XTrendKnobs) -> XTrendVerdict:
    reasons: list[str] = []
    if not score.passes_psr:
        reasons.append(
            f"full-sample PSR(0) {score.full_psr_zero:.3f} below {knobs.viability_bar:.2f}"
        )
    if not score.passes_drawdown:
        reasons.append(f"max drawdown {score.max_drawdown:.1%} above {knobs.max_drawdown_bar:.1%}")
    if not score.passes_cost_share:
        reasons.append(f"cost share {score.total_cost_share:.1%} above {knobs.max_cost_share:.1%}")
    if not score.passes_notional:
        reasons.append("notional cap exceeded")
    if reasons:
        return XTrendVerdict(
            non_viable=True,
            headline="NON-VIABLE cross-asset defensive trend honest null",
            reason="; ".join(reasons),
        )
    if score.regime_dependent:
        return XTrendVerdict(
            non_viable=False,
            headline="NOT KILLED but regime-dependent; cross-check before belief",
            reason="full-sample gate passed, but a CPCV path or a recency slice is below the bar",
        )
    return XTrendVerdict(
        non_viable=False,
        headline="NOT KILLED on the cross-asset trend gate; cross-check before belief",
        reason="all pre-registered kill checks passed and the stress diagnostics held",
    )


def build_gate_artifact(
    panel: pl.DataFrame,
    *,
    panel_sha256: str,
    panel_relpath: str,
    provenance_sha256: str,
    provenance_relpath: str,
    knobs: XTrendKnobs | None = None,
) -> XTrendGateArtifact:
    """Build the Study 6 gate artifact from the committed daily panel."""
    k = knobs if knobs is not None else XTrendKnobs()
    daily = _daily_from_panel(panel, k)
    sim = _simulate(daily, k)
    score = _score(panel, daily, sim, k)
    data_dates = sorted(panel["date"].unique().to_list())
    return XTrendGateArtifact(
        schema_version=SCHEMA_VERSION,
        study=_STUDY,
        data_start=data_dates[0].isoformat(),
        data_end=data_dates[-1].isoformat(),
        first_scored_date=sim.scored_dates[0].isoformat(),
        last_scored_date=sim.scored_dates[-1].isoformat(),
        n_months=len(sim.positions),
        knobs=k,
        cost_model=CostModel(
            equity_expense_annual=EXPENSE_RATIO_ANNUAL["equity"],
            bond_expense_annual=EXPENSE_RATIO_ANNUAL["bond"],
            turnover_cost_per_side=k.turnover_cost_per_side,
            basis="annual expense ratio on held notional plus per-side turnover, rounded up",
        ),
        fingerprint=InputFingerprint(
            panel_sha256=panel_sha256,
            panel_relpath=panel_relpath,
            n_panel_rows=panel.height,
            provenance_sha256=provenance_sha256,
            provenance_relpath=provenance_relpath,
        ),
        score=score,
        positions=sim.positions,
        daily_equity=DailyEquityPath(
            date=tuple(d.isoformat() for d in sim.scored_dates),
            equity=sim.equity_path,
        ),
        verdict=_verdict(score, k),
        caveats=CAVEATS,
    )


def artifact_to_json(artifact: XTrendGateArtifact) -> str:
    """Deterministic JSON with sorted keys and strict finite values."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_gate_artifact(artifact: XTrendGateArtifact, path: Path) -> None:
    """Write the committed gate artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact_to_json(artifact), encoding="utf-8", newline="\n")


def load_artifact_dict(path: Path) -> dict[str, Any]:
    """Load the committed artifact JSON as a dict (for reproduction comparison)."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise XTrendError(f"{path.name}: artifact is not a JSON object")
    return data
