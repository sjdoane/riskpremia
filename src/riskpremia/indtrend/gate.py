"""Industry-trend net-of-market gate (Study 9, ADR 0011, with the design-review amendment).

Each of the 12 value-weighted Kenneth French industries is held long when its total-return index is
above its ten-month moving average at the prior month-end, else its one-twelfth of capital earns the
one-month bill (Study 6's frozen no-fit rule on 12 sleeves). The headline kill is the full-sample
conditional PSR(0) of the strategy MINUS its own always-invested equal-weight buy-and-hold (the pure
trend-timing value); the strategy minus the value-weight market is the deployable context and the
equal-weight-minus-value-weight tilt is the bridge (the identity strategy-minus-VW = timing + tilt
is exposed). The stress (CPCV worst fold, 2000/2008/2022 recency, a deflation ladder) and the cost
sensitivity all read the timing-difference series.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import attrs
import polars as pl

from riskpremia.analytics.sharpe import dsr, psr
from riskpremia.execution.scoring import effective_sample_size, make_purged_cpcv, return_moments
from riskpremia.indtrend.errors import IndTrendError
from riskpremia.indtrend.fixtures import INDUSTRY_COLS

SCHEMA_VERSION = 1
_STUDY = "Industry-trend net-of-market (Study 9, ADR 0011)"
N_INDUSTRIES = 12
SMA_MONTHS = 10
SMA_VARIANTS: tuple[int, ...] = (6, 8, 10, 12)
TOP_K_VARIANT = 6
TRADING_DAYS_PER_YEAR = 252.0
TRADING_DAYS_PER_MONTH = 21
EXPENSE_ANNUAL = 0.0010
TURNOVER_COST_PER_SIDE = 0.0005
TURNOVER_SENSITIVITIES: tuple[float, ...] = (0.0005, 0.0010, 0.0020)
VIABILITY_BAR = 0.95
TRIAL_LADDER: tuple[int, ...] = (16, 32, 64, 128)
CPCV_N_GROUPS = 6
CPCV_K_TEST = 2
RECENCY_SLICES: tuple[tuple[str, str], ...] = (
    ("from_2000", "2000-01-01"), ("from_2008", "2008-01-01"), ("from_2022", "2022-01-01"),
)

CAVEATS: tuple[str, ...] = (
    "The kill is the strategy MINUS its own always-invested equal-weight buy-and-hold (pure "
    "trend-timing). A long-only equity strategy beats the bill on the equity premium, and beats "
    "the value-weight market partly on a static equal-weight tilt, so neither is the timing test.",
    "The strategy-minus-value-weight-market difference is reported as deployable context (does "
    "this beat holding the market?); the equal-weight-minus-value-weight tilt is the bridge, and "
    "strategy-minus-VW equals timing plus tilt by construction.",
    "The ten-month rule is frozen verbatim from Study 6 with no re-optimization for this universe; "
    "the moving-average-length and top-k breadth variants are a deflation family, not a search.",
    "Costs are 5 bps per side on the continuous monthly weight change plus a 0.10 percent annual "
    "expense on held industry notional (inactive sleeves earn the bill with no expense); a 10 and "
    "20 bps turnover sensitivity is reported because 12 sector funds churn more than two sleeves.",
)


@attrs.frozen(slots=True)
class IndTrendKnobs:
    """The frozen construction knobs."""

    sma_months: int = SMA_MONTHS
    trading_days_per_year: float = TRADING_DAYS_PER_YEAR
    expense_annual: float = EXPENSE_ANNUAL
    turnover_cost_per_side: float = TURNOVER_COST_PER_SIDE
    viability_bar: float = VIABILITY_BAR
    top_k: int = 0  # 0 = the all-12 long-or-cash strategy; k>0 holds the top-k by trend strength


@attrs.frozen(slots=True)
class CostModel:
    """The explicit cost assumptions."""

    expense_annual: float
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
class DifferenceScore:
    """The timing-difference series statistics (the primary kill)."""

    raw_t: int
    effective_t: int
    pw_block_length: float
    sr_hat: float
    ann_sharpe: float
    gamma_3: float
    gamma_4: float
    mean_daily: float
    full_psr_zero: float
    monthly_psr_zero: float
    n_monthly_obs: int


@attrs.frozen(slots=True)
class Decomposition:
    """Annualized arithmetic means making the timing-vs-tilt attribution auditable."""

    timing_ann_return: float  # strategy minus equal-weight always-invested (the kill)
    tilt_ann_return: float  # equal-weight always-invested minus value-weight market (the bridge)
    deploy_ann_return: float  # strategy minus value-weight market (the deployable context)


@attrs.frozen(slots=True)
class ContextStat:
    """Standalone and net-of-bill context (equity-premium and tilt dominated, not the kill)."""

    strategy_ann_sharpe: float
    ew_ann_sharpe: float
    market_ann_sharpe: float
    strategy_net_of_bill_psr_zero: float
    deploy_diff_psr_zero: float


@attrs.frozen(slots=True)
class Descriptive:
    """Descriptive properties of the strategy path and its realized costs."""

    time_in_market: float
    mean_turnover: float
    total_cost_paid: float
    total_cost_share: float
    max_drawdown: float
    cagr_total: float
    max_gross: float


@attrs.frozen(slots=True)
class CpcvStress:
    """Purged CPCV worst-fold stress on the timing-difference series."""

    n_groups: int
    k_test: int
    n_splits: int
    min_test_size: int
    fold_psr_zero: tuple[float, ...]
    fold_min: float
    fold_median: float


@attrs.frozen(slots=True)
class RecencySlice:
    """A conditional PSR(0) of the timing-difference series on a date-restricted tail."""

    name: str
    start: str
    raw_t: int
    effective_t: int
    psr_zero: float


@attrs.frozen(slots=True)
class DeflationLadder:
    """Deflated Sharpe of the timing difference at literature-scale trial counts."""

    v_sr: float
    variant_labels: tuple[str, ...]
    variant_sr_hat: tuple[float, ...]
    trials: tuple[int, ...]
    dsr_by_trials: tuple[float, ...]


@attrs.frozen(slots=True)
class CostSensitivity:
    """The timing-difference PSR(0) at a per-side turnover cost."""

    turnover_cost_per_side: float
    full_psr_zero: float
    total_cost_share: float


@attrs.frozen(slots=True)
class Redundancy:
    """Distinctness from the Study 6 cross-asset trend (on the 1990-onward overlap)."""

    n_aligned: int
    timing_vs_xtrend_corr: float
    active_bet_corr: float
    combo_ann_sharpe: float


@attrs.frozen(slots=True)
class IndTrendScore:
    """The full scored result and the kill checks."""

    timing: DifferenceScore
    decomposition: Decomposition
    context: ContextStat
    descriptive: Descriptive
    cpcv: CpcvStress
    recency: tuple[RecencySlice, ...]
    deflation: DeflationLadder
    cost_sensitivity: tuple[CostSensitivity, ...]
    redundancy: Redundancy
    passes_psr: bool
    passes: bool
    regime_dependent: bool


@attrs.frozen(slots=True)
class IndTrendVerdict:
    """The Study 9 deployment verdict."""

    non_viable: bool
    headline: str
    reason: str


@attrs.frozen(slots=True)
class IndTrendGateArtifact:
    """The committed Study 9 gate artifact."""

    schema_version: int
    study: str
    data_start: str
    data_end: str
    first_scored_date: str
    last_scored_date: str
    n_scored_days: int
    knobs: IndTrendKnobs
    cost_model: CostModel
    fingerprint: InputFingerprint
    score: IndTrendScore
    caveats: tuple[str, ...]
    verdict: IndTrendVerdict


@attrs.frozen(slots=True)
class _Daily:
    """Aligned daily series derived from the committed panel."""

    dates: tuple[date, ...]
    industry_ret: tuple[tuple[float, ...], ...]  # per industry, the daily return series
    market_ret: tuple[float, ...]
    cash_ret: tuple[float, ...]


@attrs.frozen(slots=True)
class _Sim:
    """The output of one daily simulation (the strategy or the always-invested benchmark)."""

    net_total: tuple[float, ...]  # daily net total return
    active_fraction: tuple[float, ...]  # fraction of capital in equities that day
    total_cost_paid: float
    turnovers: tuple[float, ...]
    time_in_market: float
    max_gross: float
    equity_path: tuple[float, ...]


def _daily_from_panel(panel: pl.DataFrame) -> _Daily:
    required = {"date", "market_ret", "cash_ret", *INDUSTRY_COLS}
    missing = required - set(panel.columns)
    if missing:
        raise IndTrendError(f"panel missing required columns {sorted(missing)}")
    frame = panel.sort("date")
    dates = [d for d in frame["date"].to_list() if isinstance(d, date)]
    if len(dates) != frame.height:
        raise IndTrendError("panel has non-date rows")
    if len(dates) < TRADING_DAYS_PER_MONTH * (SMA_MONTHS + 3):
        raise IndTrendError("panel too short to form a ten-month signal and score a tail")
    industry_ret = tuple(tuple(float(x) for x in frame[c].to_list()) for c in INDUSTRY_COLS)
    return _Daily(
        dates=tuple(dates),
        industry_ret=industry_ret,
        market_ret=tuple(float(x) for x in frame["market_ret"].to_list()),
        cash_ret=tuple(float(x) for x in frame["cash_ret"].to_list()),
    )


def _month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def _monthly_close_indices(dates: Sequence[date]) -> list[int]:
    out: list[int] = []
    for i in range(len(dates)):
        if i + 1 == len(dates) or _month_key(dates[i + 1]) != _month_key(dates[i]):
            out.append(i)
    return out


def _month_of_day(dates: Sequence[date]) -> list[int]:
    out: list[int] = []
    m = 0
    for i in range(len(dates)):
        if i > 0 and _month_key(dates[i]) != _month_key(dates[i - 1]):
            m += 1
        out.append(m)
    return out


def _levels(returns: Sequence[float]) -> list[float]:
    level = 1.0
    out = [1.0]
    for r in returns:
        level *= 1.0 + r
        out.append(level)
    return out


def _trend_strength_by_month(daily: _Daily, sma_months: int) -> dict[int, list[float]]:
    """At each monthly index m, the per-industry level-over-SMA ratio minus 1 (negative if below).

    A positive value means the industry is above its `sma_months` moving average at month-end m
    (the signal that governs month m+1). The ratio doubles as the top-k ranking key.
    """
    month_idx = _monthly_close_indices(daily.dates)
    out: dict[int, list[float]] = {}
    industry_levels = [_levels(daily.industry_ret[i]) for i in range(N_INDUSTRIES)]
    monthly_levels = [[lv[j + 1] for j in month_idx] for lv in industry_levels]
    for m in range(sma_months - 1, len(month_idx)):
        strengths: list[float] = []
        for i in range(N_INDUSTRIES):
            sma = statistics.fmean(monthly_levels[i][m - sma_months + 1 : m + 1])
            strengths.append(monthly_levels[i][m] / sma - 1.0 if sma > 0.0 else -1.0)
        out[m] = strengths
    return out


def _targets(strengths: list[float], top_k: int) -> dict[int, float]:
    """The per-industry target weight for a month from the trend strengths and breadth knob."""
    above = [i for i in range(N_INDUSTRIES) if strengths[i] > 0.0]
    if top_k <= 0:
        return {i: 1.0 / N_INDUSTRIES for i in above}
    chosen = sorted(above, key=lambda i: strengths[i], reverse=True)[:top_k]
    return {i: 1.0 / top_k for i in chosen}


def _simulate(daily: _Daily, knobs: IndTrendKnobs, *, always_invested: bool) -> _Sim:
    month_idx = _monthly_close_indices(daily.dates)
    if len(month_idx) <= knobs.sma_months:
        raise IndTrendError("not enough months to form a signal and score the next month")
    strengths = _trend_strength_by_month(daily, knobs.sma_months)
    month_of_day = _month_of_day(daily.dates)
    expense_daily = knobs.expense_annual / knobs.trading_days_per_year
    first_scored_month = knobs.sma_months

    weights: dict[int, float] = {}
    holdings: dict[int, float] = {}
    cash_value = 1.0
    total = 1.0
    current_month = -1
    cost_paid = 0.0
    in_market_days = 0
    max_gross = 0.0
    started = False

    net_total: list[float] = []
    active_fraction: list[float] = []
    turnovers: list[float] = []
    equity_path: list[float] = []

    for i in range(len(daily.dates)):
        mo = month_of_day[i]
        if mo < first_scored_month:
            continue
        total_prev = total
        if mo != current_month:
            if always_invested:
                targets = {j: 1.0 / N_INDUSTRIES for j in range(N_INDUSTRIES)}
            else:
                targets = _targets(strengths.get(mo - 1, [0.0] * N_INDUSTRIES), knobs.top_k)
            invested = math.fsum(targets.values())
            target_cash = 1.0 - invested
            prior = {**{j: 0.0 for j in targets}, **weights}
            turnover = math.fsum(
                abs(targets.get(j, 0.0) - prior.get(j, 0.0)) for j in set(targets) | set(prior)
            ) if started else invested
            cost_fraction = turnover * knobs.turnover_cost_per_side
            total_after = total_prev * (1.0 - cost_fraction)
            cost_paid += total_prev * cost_fraction
            holdings = {j: total_after * w for j, w in targets.items()}
            cash_value = total_after * target_cash
            weights = dict(targets)
            current_month = mo
            turnovers.append(turnover)
            max_gross = max(max_gross, invested)
        expense_dollars = 0.0
        new_holdings: dict[int, float] = {}
        for j, h in holdings.items():
            grown = h * (1.0 + daily.industry_ret[j][i])
            expense_dollars += grown * expense_daily
            new_holdings[j] = grown * (1.0 - expense_daily)
        holdings = new_holdings
        cash_value *= 1.0 + daily.cash_ret[i]
        total = math.fsum(holdings.values()) + cash_value
        if total_prev <= 0.0 or total <= 0.0:
            raise IndTrendError(f"portfolio wealth went non-positive on {daily.dates[i]}")
        net_return = total / total_prev - 1.0
        cost_paid += expense_dollars
        weights = {j: h / total for j, h in holdings.items()}
        invested_now = math.fsum(weights.values())
        net_total.append(net_return)
        active_fraction.append(invested_now)
        equity_path.append(total)
        if invested_now > 1e-9:
            in_market_days += 1
        started = True

    if len(net_total) < TRADING_DAYS_PER_MONTH * 12:
        raise IndTrendError("fewer than a year of scored observations")
    return _Sim(
        net_total=tuple(net_total),
        active_fraction=tuple(active_fraction),
        total_cost_paid=cost_paid,
        turnovers=tuple(turnovers),
        time_in_market=in_market_days / len(net_total),
        max_gross=max_gross,
        equity_path=tuple(equity_path),
    )


def _scored_dates(daily: _Daily, knobs: IndTrendKnobs) -> list[date]:
    month_of_day = _month_of_day(daily.dates)
    return [daily.dates[i] for i in range(len(daily.dates)) if month_of_day[i] >= knobs.sma_months]


def _market_net(daily: _Daily, knobs: IndTrendKnobs) -> tuple[list[date], list[float]]:
    """The value-weight market net total return over the scored window (the same flat expense)."""
    expense_daily = knobs.expense_annual / knobs.trading_days_per_year
    month_of_day = _month_of_day(daily.dates)
    out_d: list[date] = []
    out_r: list[float] = []
    for i in range(len(daily.dates)):
        if month_of_day[i] < knobs.sma_months:
            continue
        out_d.append(daily.dates[i])
        out_r.append(daily.market_ret[i] - expense_daily)
    return out_d, out_r


def _compound(returns: Sequence[float]) -> float:
    wealth = 1.0
    for r in returns:
        wealth *= 1.0 + r
    return wealth - 1.0


def _max_drawdown(equity: Sequence[float]) -> float:
    peak = equity[0] if equity else 1.0
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0.0:
            worst = max(worst, 1.0 - v / peak)
    return worst


def _cagr(total_return: float, start: date, end: date) -> float:
    years = max((end - start).days / 365.0, 1e-12)
    if total_return <= -1.0:
        return -1.0
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def _ann_sharpe(returns: Sequence[float], trading_days: float) -> float:
    return return_moments(returns).sr_hat * math.sqrt(trading_days)


def _psr_zero(returns: Sequence[float]) -> float:
    m = return_moments(returns)
    eff_t, _ = effective_sample_size(returns)
    return psr(m.sr_hat, 0.0, eff_t, m.gamma_3, m.gamma_4)


def _label_horizons(scored_dates: Sequence[date]) -> pl.Series:
    n = len(scored_dates)
    horizons = [scored_dates[min(i + TRADING_DAYS_PER_MONTH, n - 1)] for i in range(n)]
    return pl.Series("label_horizon", horizons, dtype=pl.Date)


def _monthly_difference(
    scored_dates: Sequence[date], a: Sequence[float], b: Sequence[float]
) -> list[float]:
    """Non-overlapping monthly difference of two daily return series (a compounded minus b)."""
    out: list[float] = []
    wa = 1.0
    wb = 1.0
    current = _month_key(scored_dates[0])
    for i, d in enumerate(scored_dates):
        key = _month_key(d)
        if key != current:
            out.append(wa - wb)
            wa = 1.0
            wb = 1.0
            current = key
        wa *= 1.0 + a[i]
        wb *= 1.0 + b[i]
    out.append(wa - wb)
    return out


def _cpcv_stress(scored_dates: Sequence[date], diff: Sequence[float]) -> CpcvStress:
    obs = pl.DataFrame({"dt": list(scored_dates)}, schema={"dt": pl.Date})
    splitter = make_purged_cpcv(
        obs.height, TRADING_DAYS_PER_MONTH, n_groups=CPCV_N_GROUPS, k_test=CPCV_K_TEST
    )
    labels = _label_horizons(scored_dates)
    fold_scores: list[float] = []
    min_test = math.inf
    for split in splitter.split(obs, labels):
        fold_scores.append(_psr_zero([diff[i] for i in split.test_indices]))
        min_test = min(min_test, len(split.test_indices))
    return CpcvStress(
        n_groups=splitter.n_groups, k_test=CPCV_K_TEST, n_splits=len(fold_scores),
        min_test_size=int(min_test), fold_psr_zero=tuple(fold_scores),
        fold_min=min(fold_scores), fold_median=statistics.median(fold_scores),
    )


def _recency(scored_dates: Sequence[date], diff: Sequence[float]) -> tuple[RecencySlice, ...]:
    out: list[RecencySlice] = []
    for name, start_str in RECENCY_SLICES:
        start = date.fromisoformat(start_str)
        rets = [diff[i] for i, d in enumerate(scored_dates) if d >= start]
        if len(rets) < TRADING_DAYS_PER_MONTH * 6:
            continue
        m = return_moments(rets)
        eff_t, _ = effective_sample_size(rets)
        out.append(RecencySlice(name=name, start=start_str, raw_t=m.t_obs, effective_t=eff_t,
                                psr_zero=psr(m.sr_hat, 0.0, eff_t, m.gamma_3, m.gamma_4)))
    return tuple(out)


def _timing_difference(
    daily: _Daily, knobs: IndTrendKnobs
) -> tuple[list[date], list[float], _Sim, _Sim]:
    """The strategy and equal-weight-always-invested sims and their daily timing difference."""
    strat = _simulate(daily, knobs, always_invested=False)
    ew = _simulate(daily, knobs, always_invested=True)
    scored = _scored_dates(daily, knobs)
    diff = [strat.net_total[i] - ew.net_total[i] for i in range(len(scored))]
    return scored, diff, strat, ew


def _deflation(daily: _Daily, knobs: IndTrendKnobs, headline_sr: float, eff_t: int,
               g3: float, g4: float) -> DeflationLadder:
    labels: list[str] = []
    variant_sr: list[float] = []
    for months in SMA_VARIANTS:
        _, diff, _, _ = _timing_difference(daily, attrs.evolve(knobs, sma_months=months, top_k=0))
        labels.append(f"ma{months}")
        variant_sr.append(return_moments(diff).sr_hat)
    _, diff_k, _, _ = _timing_difference(daily, attrs.evolve(knobs, top_k=TOP_K_VARIANT))
    labels.append(f"top{TOP_K_VARIANT}")
    variant_sr.append(return_moments(diff_k).sr_hat)
    v_sr = statistics.variance(variant_sr) if len(variant_sr) >= 2 else 0.0
    dsr_values = tuple(dsr(headline_sr, eff_t, g3, g4, v_sr, n) for n in TRIAL_LADDER)
    return DeflationLadder(
        v_sr=v_sr, variant_labels=tuple(labels), variant_sr_hat=tuple(variant_sr),
        trials=TRIAL_LADDER, dsr_by_trials=dsr_values,
    )


def _cost_sensitivity(daily: _Daily, knobs: IndTrendKnobs) -> tuple[CostSensitivity, ...]:
    out: list[CostSensitivity] = []
    for cps in TURNOVER_SENSITIVITIES:
        k = attrs.evolve(knobs, turnover_cost_per_side=cps)
        _, diff, strat, _ = _timing_difference(daily, k)
        net_terminal = _compound(list(strat.net_total))
        share = math.inf if net_terminal <= 0.0 else strat.total_cost_paid / (net_terminal + 1e-12)
        out.append(CostSensitivity(turnover_cost_per_side=cps, full_psr_zero=_psr_zero(diff),
                                   total_cost_share=share))
    return tuple(out)


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        raise IndTrendError("pearson needs two equal-length series of length >= 2")
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    syy = math.fsum((y - my) ** 2 for y in ys)
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    if sxx <= 0.0 or syy <= 0.0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def _redundancy(
    xtrend_panel: pl.DataFrame | None, scored: Sequence[date], diff: Sequence[float],
    active_fraction: Sequence[float], knobs: IndTrendKnobs,
) -> Redundancy:
    """Distinctness from Study 6: align by date on the 1990-onward overlap, bet-level numbers."""
    if xtrend_panel is None:
        return Redundancy(0, 0.0, 0.0, 0.0)
    from riskpremia.xtrend.gate import XTrendKnobs
    from riskpremia.xtrend.gate import _daily_from_panel as _xd
    from riskpremia.xtrend.gate import _signal_by_month as _xsig
    from riskpremia.xtrend.gate import _simulate as _xsim

    xk = XTrendKnobs()
    xdaily = _xd(xtrend_panel, xk)
    xsim = _xsim(xdaily, xk)
    x_excess = dict(zip(xsim.scored_dates, xsim.excess, strict=True))
    xsig = _xsig(xdaily, xk.sma_months)
    xmonth = _month_of_day(list(xdaily.dates))
    equity_active = {
        d: (1.0 if xsig.get(xmonth[k] - 1, {}).get("equity", False) else 0.0)
        for k, d in enumerate(xdaily.dates)
    }
    idx = {d: i for i, d in enumerate(scored)}
    aligned = [d for d in scored if d in x_excess and d in equity_active]
    if len(aligned) < TRADING_DAYS_PER_MONTH * 6:
        return Redundancy(len(aligned), 0.0, 0.0, 0.0)
    td = knobs.trading_days_per_year
    diff_a = [diff[idx[d]] for d in aligned]
    act_a = [active_fraction[idx[d]] for d in aligned]
    xex = [x_excess[d] for d in aligned]
    xact = [equity_active[d] for d in aligned]
    combo = [0.5 * diff[idx[d]] + 0.5 * x_excess[d] for d in aligned]
    return Redundancy(
        n_aligned=len(aligned),
        timing_vs_xtrend_corr=_pearson(diff_a, xex),
        active_bet_corr=_pearson(act_a, xact),
        combo_ann_sharpe=_ann_sharpe(combo, td),
    )


def _score(daily: _Daily, knobs: IndTrendKnobs, xtrend_panel: pl.DataFrame | None) -> IndTrendScore:
    scored, timing_diff, strat, ew = _timing_difference(daily, knobs)
    _, market_net = _market_net(daily, knobs)
    deploy_diff = [strat.net_total[i] - market_net[i] for i in range(len(scored))]
    tilt_diff = [ew.net_total[i] - market_net[i] for i in range(len(scored))]
    # strategy net-of-bill excess (the Study 6 metric, context only)
    month_of_day = _month_of_day(daily.dates)
    cash_scored = [
        daily.cash_ret[i] for i in range(len(daily.dates)) if month_of_day[i] >= knobs.sma_months
    ]
    strat_excess = [strat.net_total[i] - cash_scored[i] for i in range(len(scored))]

    dm = return_moments(timing_diff)
    eff_t, block = effective_sample_size(timing_diff)
    full_psr = psr(dm.sr_hat, 0.0, eff_t, dm.gamma_3, dm.gamma_4)
    monthly = _monthly_difference(scored, [s for s in strat.net_total], [e for e in ew.net_total])
    mm = return_moments(monthly)
    meff, _ = effective_sample_size(monthly)
    timing = DifferenceScore(
        raw_t=dm.t_obs, effective_t=eff_t, pw_block_length=block, sr_hat=dm.sr_hat,
        ann_sharpe=dm.sr_hat * math.sqrt(knobs.trading_days_per_year), gamma_3=dm.gamma_3,
        gamma_4=dm.gamma_4, mean_daily=dm.mean, full_psr_zero=full_psr,
        monthly_psr_zero=psr(mm.sr_hat, 0.0, meff, mm.gamma_3, mm.gamma_4),
        n_monthly_obs=len(monthly),
    )
    td = knobs.trading_days_per_year
    decomposition = Decomposition(
        timing_ann_return=statistics.fmean(timing_diff) * td,
        tilt_ann_return=statistics.fmean(tilt_diff) * td,
        deploy_ann_return=statistics.fmean(deploy_diff) * td,
    )
    ew_excess = [ew.net_total[i] - cash_scored[i] for i in range(len(scored))]
    market_excess = [market_net[i] - cash_scored[i] for i in range(len(scored))]
    context = ContextStat(
        strategy_ann_sharpe=_ann_sharpe(strat_excess, td),
        ew_ann_sharpe=_ann_sharpe(ew_excess, td),
        market_ann_sharpe=_ann_sharpe(market_excess, td),
        strategy_net_of_bill_psr_zero=_psr_zero(strat_excess),
        deploy_diff_psr_zero=_psr_zero(deploy_diff),
    )
    net_total = _compound(strat.net_total)
    cost_share = math.inf if net_total <= 0.0 else strat.total_cost_paid / (net_total + 1e-12)
    descriptive = Descriptive(
        time_in_market=strat.time_in_market,
        mean_turnover=statistics.fmean(strat.turnovers) if strat.turnovers else 0.0,
        total_cost_paid=strat.total_cost_paid, total_cost_share=cost_share,
        max_drawdown=_max_drawdown(strat.equity_path),
        cagr_total=_cagr(net_total, scored[0], scored[-1]), max_gross=strat.max_gross,
    )
    cpcv = _cpcv_stress(scored, timing_diff)
    recency = _recency(scored, timing_diff)
    deflation = _deflation(daily, knobs, dm.sr_hat, eff_t, dm.gamma_3, dm.gamma_4)
    cost_sens = _cost_sensitivity(daily, knobs)
    redundancy = _redundancy(xtrend_panel, scored, timing_diff, strat.active_fraction, knobs)

    passes_psr = full_psr >= knobs.viability_bar
    passes = passes_psr and descriptive.max_gross <= 1.0 + 1e-9
    regime_dependent = passes and (
        cpcv.fold_min < knobs.viability_bar
        or any(s.psr_zero < knobs.viability_bar for s in recency)
        or deflation.dsr_by_trials[-1] < knobs.viability_bar
    )
    return IndTrendScore(
        timing=timing, decomposition=decomposition, context=context, descriptive=descriptive,
        cpcv=cpcv, recency=recency, deflation=deflation, cost_sensitivity=cost_sens,
        redundancy=redundancy, passes_psr=passes_psr, passes=passes,
        regime_dependent=regime_dependent,
    )


def _verdict(score: IndTrendScore) -> IndTrendVerdict:
    t = score.timing
    if not score.passes_psr:
        return IndTrendVerdict(
            non_viable=True,
            headline="NON-VIABLE industry trend; timing does not beat always-invested net of cost",
            reason=(
                f"timing-difference PSR(0) {t.full_psr_zero:.3f} below {VIABILITY_BAR:.2f} "
                f"(annualized timing {score.decomposition.timing_ann_return:+.2%}/yr): a "
                f"long-or-cash trend is crash insurance, not a market-beater, the expected null"
            ),
        )
    if score.regime_dependent:
        return IndTrendVerdict(
            non_viable=False,
            headline="NOT KILLED but regime-dependent; cross-check before belief",
            reason=(
                "timing-difference gate passed but a stress slice (CPCV, recency, or deflation) "
                "is below the bar"
            ),
        )
    return IndTrendVerdict(
        non_viable=False,
        headline="NOT KILLED; industry-trend timing beats always-invested net of cost",
        reason="all pre-registered kill checks passed and the stress diagnostics held",
    )


def build_gate_artifact(
    panel: pl.DataFrame,
    *,
    panel_sha256: str,
    panel_relpath: str,
    provenance_sha256: str,
    provenance_relpath: str,
    knobs: IndTrendKnobs | None = None,
    xtrend_panel: pl.DataFrame | None = None,
) -> IndTrendGateArtifact:
    """Build the Study 9 industry-trend gate artifact from the committed panel."""
    k = knobs if knobs is not None else IndTrendKnobs()
    daily = _daily_from_panel(panel)
    scored = _scored_dates(daily, k)
    score = _score(daily, k, xtrend_panel)
    data_dates = sorted(panel["date"].unique().to_list())
    return IndTrendGateArtifact(
        schema_version=SCHEMA_VERSION, study=_STUDY,
        data_start=data_dates[0].isoformat(), data_end=data_dates[-1].isoformat(),
        first_scored_date=scored[0].isoformat(), last_scored_date=scored[-1].isoformat(),
        n_scored_days=len(scored), knobs=k,
        cost_model=CostModel(
            expense_annual=k.expense_annual, turnover_cost_per_side=k.turnover_cost_per_side,
            basis="0.10%/yr expense on held notional + per-side turnover on the weight change",
        ),
        fingerprint=InputFingerprint(
            panel_sha256=panel_sha256, panel_relpath=panel_relpath, n_panel_rows=panel.height,
            provenance_sha256=provenance_sha256, provenance_relpath=provenance_relpath,
        ),
        score=score, caveats=CAVEATS, verdict=_verdict(score),
    )


def artifact_to_json(artifact: IndTrendGateArtifact) -> str:
    """Deterministic JSON with sorted keys and strict finite values."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_gate_artifact(artifact: IndTrendGateArtifact, path: Path) -> None:
    """Write the committed gate artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact_to_json(artifact), encoding="utf-8", newline="\n")


def load_artifact_dict(path: Path) -> dict[str, Any]:
    """Load the committed artifact JSON as a dict (for reproduction comparison)."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise IndTrendError(f"{path.name}: artifact is not a JSON object")
    return data
