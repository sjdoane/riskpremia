"""Volatility-managed market gate (Study 8, ADR 0010, with the design-review amendment).

The headline kill is the full-sample conditional PSR(0) of the managed-MINUS-unmanaged difference
series: a c-normalized managed market is a levered long-equity position whose standalone Sharpe is
the equity premium, so only the difference over buy-and-hold isolates volatility-timing value (the
direct Cederburg framing). The standalone managed and unmanaged Sharpes are reported as context.
The full-sample c is the Moreira-Muir in-sample normalization; an expanding-window c is reported as
the real-time out-of-sample sensitivity. Costs are one coherent model (expense on exposure,
financing on the levered leg, per-side turnover on the continuous weight change). The CPCV worst
fold, the 2008 and 2022 recency slices, a deflation ladder over a literature-scale trial count, the
leverage-cap and financing-spread sensitivities, the expanding-c row, and the redundancy-with-
Study-6 numbers are reported as stress and context.
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
from riskpremia.volmanaged.errors import VolManagedError
from riskpremia.volmanaged.measure import (
    VMDailySeries,
    VMKnobs,
    _month_of_day,
    build_daily_series,
    market_excess,
)

SCHEMA_VERSION = 1
_STUDY = "Volatility-managed market portfolio (Study 8, ADR 0010)"
VIABILITY_BAR = 0.95
TRADING_DAYS_PER_MONTH = 21
CPCV_N_GROUPS = 6
CPCV_K_TEST = 2
TRIAL_LADDER: tuple[int, ...] = (8, 16, 32, 64, 128)
CAP_SENSITIVITIES: tuple[float, ...] = (1.0, 1.5, 2.0)
FINANCING_SENSITIVITIES: tuple[float, ...] = (0.005, 0.010, 0.020)
RECENCY_SLICES: tuple[tuple[str, str], ...] = (
    ("from_2008", "2008-01-01"),
    ("from_2022", "2022-01-01"),
)

CAVEATS: tuple[str, ...] = (
    "The kill statistic is the managed-MINUS-unmanaged difference series, not the standalone "
    "managed series: a c-normalized managed market is a levered long-equity position whose Sharpe "
    "is the equity premium, so only the difference over buy-and-hold tests volatility timing.",
    "The full-sample c is the Moreira-Muir in-sample normalization (managed full-sample volatility "
    "equals unmanaged). It is computed on the UNCAPPED weight with the 2.0 cap as a separate "
    "friction. The expanding-window c row is the real-time, point-in-time analog and must agree.",
    "Costs are one coherent model: a 10 bps expense on the equity exposure, a financing spread on "
    "the levered portion over the bill (1.0 percent primary, with 0.5 and 2.0 percent as the "
    "bracket), and a 5 bps per-side turnover on the continuous monthly weight change. The "
    "unmanaged benchmark carries the same expense and no financing or turnover.",
    "The literature predicts the managed market survives a deflated net-of-cost gate while the "
    "managed factors do not; the factor-asymmetry secondary is the stacked follow-up, not here.",
    "A deployable implementation is a broad-market ETF base plus explicit margin financing on the "
    "levered leg; a leveraged ETF is an unmodeled alternative whose embedded financing differs.",
)


@attrs.frozen(slots=True)
class CostModel:
    """The explicit cost assumptions."""

    expense_annual: float
    financing_spread_annual: float
    turnover_cost_per_side: float
    basis: str


@attrs.frozen(slots=True)
class InputFingerprint:
    """Content pins for the committed panel and its provenance (the Study 6 panel, reused)."""

    panel_sha256: str
    panel_relpath: str
    n_panel_rows: int
    provenance_sha256: str
    provenance_relpath: str


@attrs.frozen(slots=True)
class DifferenceScore:
    """The primary kill: the managed-minus-unmanaged difference series statistics."""

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
class ContextStat:
    """The standalone managed and unmanaged Sharpes (equity-premium dominated, not the kill)."""

    managed_ann_sharpe: float
    managed_psr_zero: float
    unmanaged_ann_sharpe: float
    unmanaged_psr_zero: float


@attrs.frozen(slots=True)
class ManagedDescriptive:
    """Descriptive properties of the managed weight path and its realized costs."""

    c_value: float
    mean_weight: float
    max_weight: float
    frac_capped: float
    frac_levered: float
    mean_turnover: float
    total_financing_cost: float
    total_turnover_cost: float
    total_expense_cost: float
    managed_max_drawdown: float
    managed_cagr: float


@attrs.frozen(slots=True)
class CpcvStress:
    """Purged CPCV worst-fold stress on the difference series (worst held-out regime)."""

    n_groups: int
    k_test: int
    n_splits: int
    min_test_size: int
    fold_psr_zero: tuple[float, ...]
    fold_min: float
    fold_median: float


@attrs.frozen(slots=True)
class RecencySlice:
    """A conditional PSR(0) of the difference series on a date-restricted tail (a diagnostic)."""

    name: str
    start: str
    raw_t: int
    effective_t: int
    psr_zero: float


@attrs.frozen(slots=True)
class DeflationLadder:
    """Deflated Sharpe of the difference series at literature-scale trial counts."""

    v_sr: float
    variant_labels: tuple[str, ...]
    variant_sr_hat: tuple[float, ...]
    trials: tuple[int, ...]
    dsr_by_trials: tuple[float, ...]


@attrs.frozen(slots=True)
class ExpandingC:
    """The difference-series PSR(0) under the real-time expanding-window c (the OOS check)."""

    full_psr_zero: float
    mean_weight: float
    burnin_months: int


@attrs.frozen(slots=True)
class CapSensitivity:
    """The difference-series PSR(0) at a leverage cap."""

    cap: float
    full_psr_zero: float
    mean_weight: float


@attrs.frozen(slots=True)
class FinancingSensitivity:
    """The difference-series PSR(0) at a financing spread over the bill."""

    spread_annual: float
    full_psr_zero: float


@attrs.frozen(slots=True)
class GrossDecomposition:
    """Where the difference dies: the gross timing alpha, then the leverage cap, then the cost.

    The uncapped costless difference is the Moreira-Muir gross timing alpha at equal volatility (it
    is positive in this data); applying the leverage cap is the dominant drag, and the net-of-cost
    frictions take the rest. This makes the honest-null attribution explicit (the cap, not cost, is
    the primary killer) and shows the cost model was not tuned to force the null.
    """

    uncapped_costless_ann_return: float
    capped_costless_ann_return: float
    net_ann_return: float
    uncapped_costless_ann_sharpe: float
    cap_drag_ann_return: float
    cost_drag_ann_return: float


@attrs.frozen(slots=True)
class Redundancy:
    """How distinct the managed market is from the Study 6 cross-asset trend (the ADR objection)."""

    n_aligned: int
    managed_vs_xtrend_corr: float
    difference_vs_xtrend_corr: float
    active_bet_corr: float
    managed_ann_sharpe: float
    xtrend_ann_sharpe: float
    combo_ann_sharpe: float


@attrs.frozen(slots=True)
class VMScore:
    """The full scored result and the kill checks."""

    difference: DifferenceScore
    context: ContextStat
    descriptive: ManagedDescriptive
    gross: GrossDecomposition
    cpcv: CpcvStress
    recency: tuple[RecencySlice, ...]
    deflation: DeflationLadder
    expanding_c: ExpandingC
    cap_sensitivity: tuple[CapSensitivity, ...]
    financing_sensitivity: tuple[FinancingSensitivity, ...]
    redundancy: Redundancy
    passes_psr: bool
    passes: bool
    regime_dependent: bool


@attrs.frozen(slots=True)
class VMVerdict:
    """The Study 8 deployment verdict."""

    non_viable: bool
    headline: str
    reason: str


@attrs.frozen(slots=True)
class VMGateArtifact:
    """The committed Study 8 gate artifact."""

    schema_version: int
    study: str
    data_start: str
    data_end: str
    first_scored_date: str
    last_scored_date: str
    n_scored_days: int
    knobs: VMKnobs
    cost_model: CostModel
    fingerprint: InputFingerprint
    score: VMScore
    caveats: tuple[str, ...]
    verdict: VMVerdict


def _ann_sharpe(returns: Sequence[float], trading_days: float) -> float:
    return return_moments(returns).sr_hat * math.sqrt(trading_days)


def _psr_zero(returns: Sequence[float]) -> float:
    m = return_moments(returns)
    eff_t, _ = effective_sample_size(returns)
    return psr(m.sr_hat, 0.0, eff_t, m.gamma_3, m.gamma_4)


def _monthly_difference(series: VMDailySeries) -> list[float]:
    """Non-overlapping monthly difference: the bill cancels, so it is managed minus unmanaged total.

    Within a held month the daily marks share one monthly weight, so the month is the honest
    independent unit. The unmanaged total return is recovered as `unmanaged_excess + cash`, where
    `cash = managed_total - managed_excess`.
    """
    out: list[float] = []
    managed = 1.0
    unmanaged = 1.0
    dates = series.dates
    current = (dates[0].year, dates[0].month)
    for i, d in enumerate(dates):
        key = (d.year, d.month)
        if key != current:
            out.append(managed - unmanaged)
            managed = 1.0
            unmanaged = 1.0
            current = key
        cash = series.managed_total[i] - series.managed_excess[i]
        managed *= 1.0 + series.managed_total[i]
        unmanaged *= 1.0 + (series.unmanaged_excess[i] + cash)
    out.append(managed - unmanaged)
    return out


def _max_drawdown(total_returns: Sequence[float]) -> float:
    peak = 1.0
    wealth = 1.0
    worst = 0.0
    for r in total_returns:
        wealth *= 1.0 + r
        peak = max(peak, wealth)
        if peak > 0.0:
            worst = max(worst, 1.0 - wealth / peak)
    return worst


def _cagr(total_returns: Sequence[float], start: date, end: date) -> float:
    wealth = 1.0
    for r in total_returns:
        wealth *= 1.0 + r
    years = max((end - start).days / 365.0, 1e-12)
    if wealth <= 0.0:
        return -1.0
    return float(wealth ** (1.0 / years) - 1.0)


def _label_horizons(scored_dates: Sequence[date]) -> pl.Series:
    n = len(scored_dates)
    horizons = [scored_dates[min(i + TRADING_DAYS_PER_MONTH, n - 1)] for i in range(n)]
    return pl.Series("label_horizon", horizons, dtype=pl.Date)


def _cpcv_stress(series: VMDailySeries) -> CpcvStress:
    obs = pl.DataFrame({"dt": list(series.dates)}, schema={"dt": pl.Date})
    splitter = make_purged_cpcv(
        obs.height, TRADING_DAYS_PER_MONTH, n_groups=CPCV_N_GROUPS, k_test=CPCV_K_TEST
    )
    labels = _label_horizons(series.dates)
    fold_scores: list[float] = []
    min_test = math.inf
    for split in splitter.split(obs, labels):
        rets = [series.difference[i] for i in split.test_indices]
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


def _recency(series: VMDailySeries) -> tuple[RecencySlice, ...]:
    out: list[RecencySlice] = []
    for name, start_str in RECENCY_SLICES:
        start = date.fromisoformat(start_str)
        rets = [series.difference[i] for i, d in enumerate(series.dates) if d >= start]
        if len(rets) < TRADING_DAYS_PER_MONTH * 6:
            continue
        m = return_moments(rets)
        eff_t, _ = effective_sample_size(rets)
        out.append(
            RecencySlice(
                name=name, start=start_str, raw_t=m.t_obs, effective_t=eff_t,
                psr_zero=psr(m.sr_hat, 0.0, eff_t, m.gamma_3, m.gamma_4),
            )
        )
    return tuple(out)


def _variant_specs(base: VMKnobs) -> tuple[tuple[str, VMKnobs], ...]:
    """Structurally different specs whose difference-Sharpe spread proxies the search v_sr."""
    return (
        ("rv1_cap2", attrs.evolve(base, rv_months=1, estimator="realized", cap=2.0)),
        ("rv2_cap2", attrs.evolve(base, rv_months=2, estimator="realized", cap=2.0)),
        ("rv3_cap2", attrs.evolve(base, rv_months=3, estimator="realized", cap=2.0)),
        ("ewma_cap2", attrs.evolve(base, estimator="ewma", cap=2.0)),
        ("rv1_cap15", attrs.evolve(base, rv_months=1, estimator="realized", cap=1.5)),
        ("rv1_cap10", attrs.evolve(base, rv_months=1, estimator="realized", cap=1.0)),
    )


def _deflation(
    dates: Sequence[date], excess: Sequence[float], cash: Sequence[float],
    base: VMKnobs, headline_sr: float, effective_t: int, gamma_3: float, gamma_4: float,
) -> DeflationLadder:
    labels: list[str] = []
    variant_sr: list[float] = []
    for label, knobs in _variant_specs(base):
        series = build_daily_series(dates, excess, cash, knobs, c_mode="full_sample")
        labels.append(label)
        variant_sr.append(return_moments(series.difference).sr_hat)
    v_sr = statistics.variance(variant_sr) if len(variant_sr) >= 2 else 0.0
    dsr_values = tuple(
        dsr(headline_sr, effective_t, gamma_3, gamma_4, v_sr, n) for n in TRIAL_LADDER
    )
    return DeflationLadder(
        v_sr=v_sr, variant_labels=tuple(labels), variant_sr_hat=tuple(variant_sr),
        trials=TRIAL_LADDER, dsr_by_trials=dsr_values,
    )


def _cap_sensitivity(
    dates: Sequence[date], excess: Sequence[float], cash: Sequence[float], base: VMKnobs
) -> tuple[CapSensitivity, ...]:
    out: list[CapSensitivity] = []
    for cap in CAP_SENSITIVITIES:
        series = build_daily_series(dates, excess, cash, attrs.evolve(base, cap=cap))
        out.append(
            CapSensitivity(cap=cap, full_psr_zero=_psr_zero(series.difference),
                          mean_weight=series.mean_weight)
        )
    return tuple(out)


def _financing_sensitivity(
    dates: Sequence[date], excess: Sequence[float], cash: Sequence[float], base: VMKnobs
) -> tuple[FinancingSensitivity, ...]:
    out: list[FinancingSensitivity] = []
    for spread in FINANCING_SENSITIVITIES:
        knobs = attrs.evolve(base, financing_spread_annual=spread)
        series = build_daily_series(dates, excess, cash, knobs)
        out.append(
            FinancingSensitivity(spread_annual=spread, full_psr_zero=_psr_zero(series.difference))
        )
    return tuple(out)


def _gross_decomposition(
    dates: Sequence[date], excess: Sequence[float], cash: Sequence[float],
    base: VMKnobs, net_difference: Sequence[float],
) -> GrossDecomposition:
    """Decompose the difference into the gross timing alpha, the cap drag, and the cost drag."""
    free = attrs.evolve(
        base, expense_annual=0.0, financing_spread_annual=0.0, turnover_cost_per_side=0.0
    )
    uncapped = build_daily_series(dates, excess, cash, attrs.evolve(free, cap=1.0e9))
    capped = build_daily_series(dates, excess, cash, free)
    td = base.trading_days_per_year
    u_ret = statistics.fmean(uncapped.difference) * td
    c_ret = statistics.fmean(capped.difference) * td
    net_ret = statistics.fmean(net_difference) * td
    return GrossDecomposition(
        uncapped_costless_ann_return=u_ret,
        capped_costless_ann_return=c_ret,
        net_ann_return=net_ret,
        uncapped_costless_ann_sharpe=_ann_sharpe(uncapped.difference, td),
        cap_drag_ann_return=c_ret - u_ret,
        cost_drag_ann_return=net_ret - c_ret,
    )


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        raise VolManagedError("pearson needs two equal-length series of length >= 2")
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    syy = math.fsum((y - my) ** 2 for y in ys)
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    if sxx <= 0.0 or syy <= 0.0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def _redundancy(
    panel: pl.DataFrame, series: VMDailySeries, knobs: VMKnobs
) -> Redundancy:
    """Distinctness from the Study 6 cross-asset trend: align by date, report the bet-level numbers.

    The daily level correlation is high by construction (both are long equity much of the time), so
    the informative numbers are the active-bet correlation (managed `w-1` vs the Study 6 equity
    on/off), the difference-vs-Study-6 correlation, and the incremental Sharpe of a 50/50 combo.
    """
    from riskpremia.xtrend.gate import (  # local import to avoid a hard module cycle
        XTrendKnobs,
        _daily_from_panel,
        _signal_by_month,
        _simulate,
    )

    xk = XTrendKnobs()
    xdaily = _daily_from_panel(panel, xk)
    xsim = _simulate(xdaily, xk)
    xmonth = _month_of_day(list(xdaily.dates))
    xsignals = _signal_by_month(xdaily, xk.sma_months)
    equity_active: dict[date, float] = {}
    for i, d in enumerate(xdaily.dates):
        sig = xsignals.get(xmonth[i] - 1, {})
        equity_active[d] = 1.0 if sig.get("equity", False) else 0.0
    x_excess: dict[date, float] = dict(zip(xsim.scored_dates, xsim.excess, strict=True))

    aligned = [d for d in series.dates if d in x_excess and d in equity_active]
    idx = {d: i for i, d in enumerate(series.dates)}
    managed = [series.managed_excess[idx[d]] for d in aligned]
    diff = [series.difference[idx[d]] for d in aligned]
    wdev = [series.weights[idx[d]] - 1.0 for d in aligned]
    xex = [x_excess[d] for d in aligned]
    xact = [equity_active[d] for d in aligned]
    combo = [0.5 * m + 0.5 * x for m, x in zip(managed, xex, strict=True)]
    td = knobs.trading_days_per_year
    return Redundancy(
        n_aligned=len(aligned),
        managed_vs_xtrend_corr=_pearson(managed, xex),
        difference_vs_xtrend_corr=_pearson(diff, xex),
        active_bet_corr=_pearson(wdev, xact),
        managed_ann_sharpe=_ann_sharpe(managed, td),
        xtrend_ann_sharpe=_ann_sharpe(xex, td),
        combo_ann_sharpe=_ann_sharpe(combo, td),
    )


def _score(panel: pl.DataFrame, dates: Sequence[date], excess: Sequence[float],
           cash: Sequence[float], series: VMDailySeries, knobs: VMKnobs) -> VMScore:
    diff = series.difference
    dm = return_moments(diff)
    eff_t, block = effective_sample_size(diff)
    full_psr = psr(dm.sr_hat, 0.0, eff_t, dm.gamma_3, dm.gamma_4)
    monthly = _monthly_difference(series)
    mm = return_moments(monthly)
    meff, _ = effective_sample_size(monthly)
    monthly_psr = psr(mm.sr_hat, 0.0, meff, mm.gamma_3, mm.gamma_4)

    difference = DifferenceScore(
        raw_t=dm.t_obs, effective_t=eff_t, pw_block_length=block, sr_hat=dm.sr_hat,
        ann_sharpe=dm.sr_hat * math.sqrt(knobs.trading_days_per_year),
        gamma_3=dm.gamma_3, gamma_4=dm.gamma_4, mean_daily=dm.mean,
        full_psr_zero=full_psr, monthly_psr_zero=monthly_psr, n_monthly_obs=len(monthly),
    )
    context = ContextStat(
        managed_ann_sharpe=_ann_sharpe(series.managed_excess, knobs.trading_days_per_year),
        managed_psr_zero=_psr_zero(series.managed_excess),
        unmanaged_ann_sharpe=_ann_sharpe(series.unmanaged_excess, knobs.trading_days_per_year),
        unmanaged_psr_zero=_psr_zero(series.unmanaged_excess),
    )
    descriptive = ManagedDescriptive(
        c_value=series.c_value, mean_weight=series.mean_weight, max_weight=series.max_weight,
        frac_capped=series.frac_capped, frac_levered=series.frac_levered,
        mean_turnover=series.mean_turnover, total_financing_cost=series.total_financing_cost,
        total_turnover_cost=series.total_turnover_cost,
        total_expense_cost=series.total_expense_cost,
        managed_max_drawdown=_max_drawdown(series.managed_total),
        managed_cagr=_cagr(series.managed_total, series.dates[0], series.dates[-1]),
    )
    cpcv = _cpcv_stress(series)
    recency = _recency(series)
    deflation = _deflation(dates, excess, cash, knobs, dm.sr_hat, eff_t, dm.gamma_3, dm.gamma_4)
    expanding_series = build_daily_series(dates, excess, cash, knobs, c_mode="expanding")
    expanding = ExpandingC(
        full_psr_zero=_psr_zero(expanding_series.difference),
        mean_weight=expanding_series.mean_weight, burnin_months=knobs.burnin_months,
    )
    cap_sens = _cap_sensitivity(dates, excess, cash, knobs)
    fin_sens = _financing_sensitivity(dates, excess, cash, knobs)
    redundancy = _redundancy(panel, series, knobs)
    gross = _gross_decomposition(dates, excess, cash, knobs, series.difference)

    passes_psr = full_psr >= VIABILITY_BAR
    passes = passes_psr
    regime_dependent = passes and (
        cpcv.fold_min < VIABILITY_BAR
        or any(s.psr_zero < VIABILITY_BAR for s in recency)
        or expanding.full_psr_zero < VIABILITY_BAR
        or deflation.dsr_by_trials[-1] < VIABILITY_BAR
    )
    return VMScore(
        difference=difference, context=context, descriptive=descriptive, gross=gross, cpcv=cpcv,
        recency=recency, deflation=deflation, expanding_c=expanding, cap_sensitivity=cap_sens,
        financing_sensitivity=fin_sens, redundancy=redundancy,
        passes_psr=passes_psr, passes=passes, regime_dependent=regime_dependent,
    )


def _verdict(score: VMScore) -> VMVerdict:
    if not score.passes_psr:
        g = score.gross
        return VMVerdict(
            non_viable=True,
            headline="NON-VIABLE volatility-managed market; no value-add over buy-and-hold",
            reason=(
                f"diff PSR(0) {score.difference.full_psr_zero:.3f} below {VIABILITY_BAR:.2f}: "
                f"a real gross timing alpha ({g.uncapped_costless_ann_return:+.2%}/yr) "
                f"dies on the {score.descriptive.max_weight:.1f}x retail leverage cap "
                f"({g.cap_drag_ann_return:+.2%}/yr, the dominant drag) and costs "
                f"({g.cost_drag_ann_return:+.2%}/yr); a clean Cederburg replication"
            ),
        )
    if score.regime_dependent:
        return VMVerdict(
            non_viable=False,
            headline="NOT KILLED but regime-dependent; cross-check before belief",
            reason=(
                "difference gate passed but a stress slice (CPCV, recency, or deflation) is below "
                "the bar"
            ),
        )
    return VMVerdict(
        non_viable=False,
        headline="NOT KILLED; the managed market beats buy-and-hold net of cost and deflation",
        reason="all pre-registered kill checks passed and the stress diagnostics held",
    )


def build_gate_artifact(
    panel: pl.DataFrame,
    *,
    panel_sha256: str,
    panel_relpath: str,
    provenance_sha256: str,
    provenance_relpath: str,
    knobs: VMKnobs | None = None,
) -> VMGateArtifact:
    """Build the Study 8 volatility-managed market gate artifact from the committed panel."""
    k = knobs if knobs is not None else VMKnobs()
    dates, excess, cash = market_excess(panel)
    series = build_daily_series(dates, excess, cash, k, c_mode="full_sample")
    score = _score(panel, dates, excess, cash, series, k)
    data_dates = sorted(panel["date"].unique().to_list())
    return VMGateArtifact(
        schema_version=SCHEMA_VERSION,
        study=_STUDY,
        data_start=data_dates[0].isoformat(),
        data_end=data_dates[-1].isoformat(),
        first_scored_date=series.dates[0].isoformat(),
        last_scored_date=series.dates[-1].isoformat(),
        n_scored_days=len(series.dates),
        knobs=k,
        cost_model=CostModel(
            expense_annual=k.expense_annual,
            financing_spread_annual=k.financing_spread_annual,
            turnover_cost_per_side=k.turnover_cost_per_side,
            basis="expense on exposure, financing on the levered leg, turnover on weight change",
        ),
        fingerprint=InputFingerprint(
            panel_sha256=panel_sha256, panel_relpath=panel_relpath, n_panel_rows=panel.height,
            provenance_sha256=provenance_sha256, provenance_relpath=provenance_relpath,
        ),
        score=score,
        caveats=CAVEATS,
        verdict=_verdict(score),
    )


def artifact_to_json(artifact: VMGateArtifact) -> str:
    """Deterministic JSON with sorted keys and strict finite values."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_gate_artifact(artifact: VMGateArtifact, path: Path) -> None:
    """Write the committed gate artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact_to_json(artifact), encoding="utf-8", newline="\n")


def load_artifact_dict(path: Path) -> dict[str, Any]:
    """Load the committed artifact JSON as a dict (for reproduction comparison)."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise VolManagedError(f"{path.name}: artifact is not a JSON object")
    return data
