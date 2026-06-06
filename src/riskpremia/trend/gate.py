"""BTC/ETH slow-trend allocation gate (Study 4, PR6a).

This module implements the ADR 0006 no-fit rule after the design-review fixes:
the signal is known only after the Sunday close, the trade fills at Monday open,
costs are booked before the holding period, drawdown is measured on a daily
mark-to-market equity path, and the statistic is labelled as conditional PSR(0).
CPCV is retained as a pre-registered worst-regime stress, not as fitted-model
validation.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal, cast

import attrs
import polars as pl

from riskpremia.analytics.sharpe import psr
from riskpremia.execution.cost import KRAKEN, VenueCostModel
from riskpremia.execution.scoring import effective_sample_size, make_purged_cpcv, return_moments
from riskpremia.trend.errors import TrendError
from riskpremia.trend.fixtures import SourceFile

SCHEMA_VERSION = 1
OOS_START = "2022-01-01"
VIABILITY_BAR = 0.95
MAX_DRAWDOWN_BAR = 0.35
MAX_COST_SHARE = 0.25
TARGET_VOL = 0.25
VOL_LOOKBACK_DAYS = 60
SMA_DAYS = 200
CRYPTO_ANNUALIZATION_DAYS = 365.0
SYMBOLS: tuple[str, str] = ("BTCUSDT", "ETHUSDT")
COST_VENUE = "kraken"
_STUDY = "BTC/ETH slow trend with cash and volatility cap (Study 4, PR6a)"
_CASH_RETURN = 0.0

EquityPointKind = Literal["fill_after_cost", "daily_close", "exit_open"]

CAVEATS: tuple[str, ...] = (
    "The headline cash proxy is zero-yield cash, a conservative lower bound. A pass must "
    "not claim it needed T-bill yield; a later cash-yield sensitivity is separate.",
    "The statistic is conditional PSR(0) for one frozen no-fit rule. The CPCV-min value is "
    "a worst-regime stress gate, not fitted-model validation.",
    "The data venue is Binance Vision USDT spot. A pass is provisional until a US spot USD "
    "venue rebuild confirms the signal and returns near the 200-day threshold.",
    "The signal is known after the Sunday UTC daily close and fills at Monday open. Rows "
    "without complete fill and exit opens are not scored.",
)


@attrs.frozen(slots=True)
class TrendKnobs:
    """The frozen PR6a construction and kill knobs."""

    oos_start: str = OOS_START
    sma_days: int = SMA_DAYS
    vol_lookback_days: int = VOL_LOOKBACK_DAYS
    target_vol: float = TARGET_VOL
    annualization_days: float = CRYPTO_ANNUALIZATION_DAYS
    max_notional: float = 1.0
    cost_venue: str = COST_VENUE
    cash_return: float = _CASH_RETURN
    viability_bar: float = VIABILITY_BAR
    max_drawdown_bar: float = MAX_DRAWDOWN_BAR
    max_cost_share: float = MAX_COST_SHARE


@attrs.frozen(slots=True)
class CostVenue:
    """The explicit spot-cost venue used by the headline."""

    name: str
    spot_taker_cost: float
    spread_basis: str
    provisional: bool
    source: str


@attrs.frozen(slots=True)
class InputFingerprint:
    """Content pins for the committed fixture and its upstream zip provenance."""

    bars_sha256: str
    bars_relpath: str
    n_bar_rows: int
    sources_sha256: str
    sources_relpath: str
    n_source_files: int
    source_checksums_sha256: str


@attrs.frozen(slots=True)
class WeeklyTrendPoint:
    """One executable weekly rebalance and holding period."""

    signal_date: str
    fill_date: str
    exit_date: str
    btc_active: bool
    eth_active: bool
    btc_target_weight: float
    eth_target_weight: float
    cash_target_weight: float
    btc_pretrade_weight: float
    eth_pretrade_weight: float
    turnover: float
    cost_fraction: float
    cost_paid: float
    btc_return: float
    eth_return: float
    gross_return: float
    net_return: float
    estimated_vol: float
    corr_one_vol: float
    active_assets: int
    target_gross: float
    pretrade_gross: float


@attrs.frozen(slots=True)
class DailyEquityPath:
    """The daily mark-to-market equity path used for drawdown."""

    date: tuple[str, ...]
    kind: tuple[EquityPointKind, ...]
    equity: tuple[float, ...]


@attrs.frozen(slots=True)
class CpcvStress:
    """Purged CPCV split PSRs, labelled as regime stress."""

    n_groups: int
    k_test: int
    n_splits: int
    min_train_size: int
    min_test_size: int
    split_psr_zero: tuple[float, ...]


@attrs.frozen(slots=True)
class BuyHoldDiagnostic:
    """The simple BTC/ETH buy-and-hold comparator, diagnostic only."""

    total_return: float
    cagr: float
    max_drawdown: float


@attrs.frozen(slots=True)
class TrendScore:
    """The scored OOS result and kill checks."""

    raw_t: int
    effective_t: int
    pw_block_length: float
    sr_hat: float
    gamma_3: float
    gamma_4: float
    mean_net: float
    full_psr_zero: float
    cpcv_min_psr_stress: float
    cpcv_median_psr_stress: float
    cpcv_max_psr_stress: float
    compounded_gross_gain: float
    compounded_net_gain: float
    total_cost_paid: float
    total_cost_share: float
    arithmetic_cost_share: float
    max_drawdown: float
    daily_realized_vol: float
    time_in_market: float
    mean_turnover: float
    total_turnover: float
    max_target_gross: float
    max_pretrade_gross: float
    mean_active_assets: float
    post_etf_total_return: float
    cagr: float
    passes_psr_stress: bool
    passes_drawdown: bool
    passes_cost_share: bool
    passes_notional: bool
    passes: bool
    cpcv: CpcvStress


@attrs.frozen(slots=True)
class TrendVerdict:
    """The PR6a deployment verdict."""

    non_viable: bool
    headline: str
    reason: str


@attrs.frozen(slots=True)
class TrendGateArtifact:
    """The committed PR6a gate artifact."""

    schema_version: int
    study: str
    data_start: str
    data_end: str
    first_signal_date: str
    first_fill_date: str
    last_signal_date: str
    last_fill_date: str
    last_exit_date: str
    knobs: TrendKnobs
    cost_venue: CostVenue
    fingerprint: InputFingerprint
    score: TrendScore
    buy_hold: BuyHoldDiagnostic
    weekly: tuple[WeeklyTrendPoint, ...]
    daily_equity: DailyEquityPath
    verdict: TrendVerdict
    caveats: tuple[str, ...]


@attrs.frozen(slots=True)
class _WeeklyCalc:
    signal_date: date
    fill_date: date
    exit_date: date
    target: dict[str, float]
    pretrade: dict[str, float]
    turnover: float
    cost_fraction: float
    cost_paid: float
    asset_returns: dict[str, float]
    gross_return: float
    net_return: float
    estimated_vol: float
    corr_one_vol: float
    active_assets: int
    wealth_before: float


def _cost_venue(model: VenueCostModel) -> CostVenue:
    if model.name != COST_VENUE:
        raise TrendError(f"PR6a headline cost venue must be {COST_VENUE!r}; got {model.name!r}")
    return CostVenue(
        name=model.name,
        spot_taker_cost=model.leg_cost_fraction(leg="spot", taker=True),
        spread_basis=model.spread_basis,
        provisional=model.provisional,
        source=model.source,
    )


def _bars_by_symbol(bars: pl.DataFrame) -> dict[str, dict[date, tuple[float, float]]]:
    required = {"date", "symbol", "open", "close"}
    missing = required - set(bars.columns)
    if missing:
        raise TrendError(f"bars frame missing required columns {sorted(missing)}")
    out: dict[str, dict[date, tuple[float, float]]] = {s: {} for s in SYMBOLS}
    for row in bars.sort(["symbol", "date"]).iter_rows(named=True):
        symbol = str(row["symbol"])
        if symbol not in out:
            continue
        d = row["date"]
        if not isinstance(d, date):
            raise TrendError(f"expected date, got {d!r}")
        open_ = float(row["open"])
        close = float(row["close"])
        if open_ <= 0.0 or close <= 0.0:
            raise TrendError(f"{symbol} {d}: open and close must be positive")
        out[symbol][d] = (open_, close)
    for symbol, rows in out.items():
        if not rows:
            raise TrendError(f"bars fixture has no rows for {symbol}")
    return out


def _close(rows: Mapping[date, tuple[float, float]], d: date) -> float | None:
    pair = rows.get(d)
    return None if pair is None else pair[1]


def _open(rows: Mapping[date, tuple[float, float]], d: date) -> float | None:
    pair = rows.get(d)
    return None if pair is None else pair[0]


def _strict_close_window(
    rows: Mapping[date, tuple[float, float]], end: date, n_closes: int
) -> list[float] | None:
    start = end - timedelta(days=n_closes - 1)
    closes: list[float] = []
    for i in range(n_closes):
        value = _close(rows, start + timedelta(days=i))
        if value is None:
            return None
        closes.append(value)
    return closes


def _sample_var(values: Sequence[float]) -> float:
    if len(values) < 2:
        raise TrendError("sample variance requires at least two values")
    mean = statistics.fmean(values)
    return math.fsum((v - mean) * (v - mean) for v in values) / (len(values) - 1)


def _sample_cov(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        raise TrendError("sample covariance requires aligned series with at least two values")
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    return math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (len(xs) - 1)


def _asset_history(
    rows: Mapping[date, tuple[float, float]], signal_date: date, knobs: TrendKnobs
) -> tuple[bool, float, list[float], float]:
    sma_closes = _strict_close_window(rows, signal_date, knobs.sma_days)
    vol_closes = _strict_close_window(rows, signal_date, knobs.vol_lookback_days + 1)
    signal_close = _close(rows, signal_date)
    if sma_closes is None or vol_closes is None or signal_close is None:
        return False, float("nan"), [], float("nan")
    sma = statistics.fmean(sma_closes)
    if not signal_close > sma:
        return False, sma, [], float("nan")
    log_returns = [
        math.log(vol_closes[i] / vol_closes[i - 1]) for i in range(1, len(vol_closes))
    ]
    if len(log_returns) != knobs.vol_lookback_days or any(
        not math.isfinite(r) for r in log_returns
    ):
        return False, sma, [], float("nan")
    var = _sample_var(log_returns)
    vol = math.sqrt(var * knobs.annualization_days) if var > 0.0 else float("nan")
    if not math.isfinite(vol) or vol <= 0.0:
        return False, sma, [], float("nan")
    return True, sma, log_returns, vol


def _targets_for_signal(
    by_symbol: Mapping[str, Mapping[date, tuple[float, float]]],
    signal_date: date,
    knobs: TrendKnobs,
) -> tuple[dict[str, float], float, float, int]:
    active: dict[str, tuple[list[float], float]] = {}
    for symbol in SYMBOLS:
        is_active, _sma, returns, vol = _asset_history(by_symbol[symbol], signal_date, knobs)
        if is_active:
            active[symbol] = (returns, vol)
    if not active:
        return {}, 0.0, 0.0, 0

    inv = {s: 1.0 / v for s, (_r, v) in active.items()}
    inv_sum = math.fsum(inv.values())
    base = {s: inv[s] / inv_sum for s in inv}

    if len(active) == 1:
        symbol = next(iter(active))
        port_vol = active[symbol][1]
        corr_one_vol = port_vol
    else:
        btc_r, btc_vol = active["BTCUSDT"]
        eth_r, eth_vol = active["ETHUSDT"]
        btc_var = _sample_var(btc_r) * knobs.annualization_days
        eth_var = _sample_var(eth_r) * knobs.annualization_days
        cov = _sample_cov(btc_r, eth_r) * knobs.annualization_days
        wb = base["BTCUSDT"]
        we = base["ETHUSDT"]
        port_var = wb * wb * btc_var + we * we * eth_var + 2.0 * wb * we * cov
        if not math.isfinite(port_var) or port_var <= 0.0:
            return {}, 0.0, 0.0, 0
        port_vol = math.sqrt(port_var)
        corr_one_vol = wb * btc_vol + we * eth_vol

    scale = min(knobs.max_notional, knobs.target_vol / port_vol)
    if not math.isfinite(scale) or scale < 0.0:
        return {}, 0.0, 0.0, 0
    target = {s: w * scale for s, w in base.items()}
    gross = math.fsum(target.values())
    if gross > knobs.max_notional + 1e-12:
        raise TrendError(f"target gross notional {gross} exceeds cap {knobs.max_notional}")
    return target, port_vol * scale, corr_one_vol * scale, len(active)


def _candidate_signal_dates(
    by_symbol: Mapping[str, Mapping[date, tuple[float, float]]]
) -> list[date]:
    dates = sorted(set(by_symbol["BTCUSDT"]) & set(by_symbol["ETHUSDT"]))
    return [d for d in dates if d.weekday() == 6]


def _complete_period(
    by_symbol: Mapping[str, Mapping[date, tuple[float, float]]], fill: date, exit_: date
) -> bool:
    for symbol in SYMBOLS:
        if _open(by_symbol[symbol], fill) is None or _open(by_symbol[symbol], exit_) is None:
            return False
    return True


def _asset_return(
    by_symbol: Mapping[str, Mapping[date, tuple[float, float]]],
    symbol: str,
    fill: date,
    exit_: date,
) -> float:
    start = _open(by_symbol[symbol], fill)
    end = _open(by_symbol[symbol], exit_)
    if start is None or end is None:
        raise TrendError(f"{symbol}: missing fill or exit open for {fill} to {exit_}")
    return end / start - 1.0


def _max_drawdown(equity: Sequence[float]) -> float:
    peak = 1.0
    worst = 0.0
    for value in equity:
        if value > peak:
            peak = value
        if peak > 0.0:
            worst = max(worst, 1.0 - value / peak)
    return worst


def _daily_realized_vol(equity: Sequence[float]) -> float:
    closes = [v for v in equity if v > 0.0]
    if len(closes) < 3:
        return float("nan")
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    return math.sqrt(_sample_var(rets) * CRYPTO_ANNUALIZATION_DAYS)


def _build_weekly(
    bars: pl.DataFrame, knobs: TrendKnobs, cost_model: VenueCostModel
) -> tuple[tuple[_WeeklyCalc, ...], DailyEquityPath]:
    if knobs.cash_return != _CASH_RETURN:
        raise TrendError("PR6a cash_return is fixed at zero-yield cash")
    by_symbol = _bars_by_symbol(bars)
    oos = date.fromisoformat(knobs.oos_start)
    cost = cost_model.leg_cost_fraction(leg="spot", taker=True)
    pretrade = {s: 0.0 for s in SYMBOLS}
    wealth = 1.0
    weekly: list[_WeeklyCalc] = []
    equity_dates: list[str] = []
    equity_kinds: list[EquityPointKind] = []
    equity_values: list[float] = []

    for signal_date in _candidate_signal_dates(by_symbol):
        fill = signal_date + timedelta(days=1)
        exit_ = fill + timedelta(days=7)
        if fill < oos or not _complete_period(by_symbol, fill, exit_):
            continue
        target, est_vol, corr_one, active_count = _targets_for_signal(by_symbol, signal_date, knobs)
        full_target = {s: target.get(s, 0.0) for s in SYMBOLS}
        turnover = math.fsum(abs(full_target[s] - pretrade[s]) for s in SYMBOLS)
        cost_fraction = turnover * cost
        if cost_fraction >= 1.0:
            raise TrendError(f"rebalance cost {cost_fraction} wipes out capital on {fill}")
        asset_returns = {s: _asset_return(by_symbol, s, fill, exit_) for s in SYMBOLS}
        holding = math.fsum(full_target[s] * asset_returns[s] for s in SYMBOLS)
        net = (1.0 - cost_fraction) * (1.0 + holding) - 1.0
        cost_paid = wealth * cost_fraction
        start_wealth = wealth * (1.0 - cost_fraction)

        equity_dates.append(fill.isoformat())
        equity_kinds.append("fill_after_cost")
        equity_values.append(start_wealth)
        cash_weight = max(0.0, 1.0 - math.fsum(full_target.values()))
        d = fill
        while d < exit_:
            value = start_wealth * cash_weight
            for symbol in SYMBOLS:
                close = _close(by_symbol[symbol], d)
                open_ = _open(by_symbol[symbol], fill)
                if close is None or open_ is None:
                    raise TrendError(f"{symbol}: missing daily mark for {d}")
                value += start_wealth * full_target[symbol] * (close / open_)
            equity_dates.append(d.isoformat())
            equity_kinds.append("daily_close")
            equity_values.append(value)
            d += timedelta(days=1)
        exit_value = start_wealth * (1.0 + holding)
        equity_dates.append(exit_.isoformat())
        equity_kinds.append("exit_open")
        equity_values.append(exit_value)

        weekly.append(
            _WeeklyCalc(
                signal_date=signal_date,
                fill_date=fill,
                exit_date=exit_,
                target=full_target,
                pretrade=dict(pretrade),
                turnover=turnover,
                cost_fraction=cost_fraction,
                cost_paid=cost_paid,
                asset_returns=asset_returns,
                gross_return=holding,
                net_return=net,
                estimated_vol=est_vol,
                corr_one_vol=corr_one,
                active_assets=active_count,
                wealth_before=wealth,
            )
        )

        denom = 1.0 + holding
        if denom <= 0.0:
            raise TrendError(f"portfolio lost all capital before next rebalance on {exit_}")
        pretrade = {s: full_target[s] * (1.0 + asset_returns[s]) / denom for s in SYMBOLS}
        wealth *= 1.0 + net

    if len(weekly) < 2:
        raise TrendError("trend gate produced fewer than two OOS weekly observations")
    return tuple(weekly), DailyEquityPath(
        date=tuple(equity_dates),
        kind=tuple(equity_kinds),
        equity=tuple(equity_values),
    )


def _weekly_point(calc: _WeeklyCalc) -> WeeklyTrendPoint:
    return WeeklyTrendPoint(
        signal_date=calc.signal_date.isoformat(),
        fill_date=calc.fill_date.isoformat(),
        exit_date=calc.exit_date.isoformat(),
        btc_active=calc.target["BTCUSDT"] > 0.0,
        eth_active=calc.target["ETHUSDT"] > 0.0,
        btc_target_weight=calc.target["BTCUSDT"],
        eth_target_weight=calc.target["ETHUSDT"],
        cash_target_weight=max(0.0, 1.0 - math.fsum(calc.target.values())),
        btc_pretrade_weight=calc.pretrade["BTCUSDT"],
        eth_pretrade_weight=calc.pretrade["ETHUSDT"],
        turnover=calc.turnover,
        cost_fraction=calc.cost_fraction,
        cost_paid=calc.cost_paid,
        btc_return=calc.asset_returns["BTCUSDT"],
        eth_return=calc.asset_returns["ETHUSDT"],
        gross_return=calc.gross_return,
        net_return=calc.net_return,
        estimated_vol=calc.estimated_vol,
        corr_one_vol=calc.corr_one_vol,
        active_assets=calc.active_assets,
        target_gross=math.fsum(calc.target.values()),
        pretrade_gross=math.fsum(calc.pretrade.values()),
    )


def _label_horizons(weekly: Sequence[_WeeklyCalc]) -> pl.Series:
    return pl.Series("label_horizon", [w.exit_date for w in weekly], dtype=pl.Date)


def _cpcv_stress(weekly: Sequence[_WeeklyCalc]) -> CpcvStress:
    obs = pl.DataFrame({"dt": [w.fill_date for w in weekly]}, schema={"dt": pl.Date})
    splitter = make_purged_cpcv(obs.height, 1, n_groups=6, k_test=2)
    split_scores: list[float] = []
    min_train = math.inf
    min_test = math.inf
    for split in splitter.split(obs, _label_horizons(weekly)):
        rets = [weekly[i].net_return for i in split.test_indices]
        moments = return_moments(rets)
        effective_t, _block = effective_sample_size(rets)
        split_scores.append(psr(moments.sr_hat, 0.0, effective_t, moments.gamma_3, moments.gamma_4))
        min_train = min(min_train, len(split.train_indices))
        min_test = min(min_test, len(split.test_indices))
    return CpcvStress(
        n_groups=splitter.n_groups,
        k_test=2,
        n_splits=len(split_scores),
        min_train_size=int(min_train),
        min_test_size=int(min_test),
        split_psr_zero=tuple(split_scores),
    )


def _compound(returns: Sequence[float]) -> float:
    wealth = 1.0
    for ret in returns:
        wealth *= 1.0 + ret
    return wealth - 1.0


def _cagr(total_return: float, start: date, end: date) -> float:
    years = max((end - start).days / 365.0, 1e-12)
    if total_return <= -1.0:
        return -1.0
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def _score(weekly: Sequence[_WeeklyCalc], daily: DailyEquityPath, knobs: TrendKnobs) -> TrendScore:
    net_returns = [w.net_return for w in weekly]
    gross_returns = [w.gross_return for w in weekly]
    moments = return_moments(net_returns)
    effective_t, block = effective_sample_size(net_returns)
    full_psr = psr(moments.sr_hat, 0.0, effective_t, moments.gamma_3, moments.gamma_4)
    cpcv = _cpcv_stress(weekly)
    gross_gain = _compound(gross_returns)
    net_gain = _compound(net_returns)
    total_cost_paid = math.fsum(w.cost_paid for w in weekly)
    cost_share = math.inf if gross_gain <= 0.0 else total_cost_paid / gross_gain
    mean_gross = statistics.fmean(gross_returns)
    mean_cost = statistics.fmean(w.cost_fraction for w in weekly)
    arithmetic_cost_share = math.inf if mean_gross <= 0.0 else mean_cost / mean_gross
    max_dd = _max_drawdown(daily.equity)
    cpcv_min = min(cpcv.split_psr_zero)
    cpcv_median = statistics.median(cpcv.split_psr_zero)
    cpcv_max = max(cpcv.split_psr_zero)
    max_target = max(math.fsum(w.target.values()) for w in weekly)
    max_pretrade = max(math.fsum(w.pretrade.values()) for w in weekly)
    start = weekly[0].fill_date
    end = weekly[-1].exit_date
    passes_psr = cpcv_min >= knobs.viability_bar
    passes_drawdown = max_dd <= knobs.max_drawdown_bar
    passes_cost = math.isfinite(cost_share) and cost_share <= knobs.max_cost_share
    passes_notional = max_target <= knobs.max_notional + 1e-12 and max_pretrade <= 1.05
    return TrendScore(
        raw_t=moments.t_obs,
        effective_t=effective_t,
        pw_block_length=block,
        sr_hat=moments.sr_hat,
        gamma_3=moments.gamma_3,
        gamma_4=moments.gamma_4,
        mean_net=moments.mean,
        full_psr_zero=full_psr,
        cpcv_min_psr_stress=cpcv_min,
        cpcv_median_psr_stress=cpcv_median,
        cpcv_max_psr_stress=cpcv_max,
        compounded_gross_gain=gross_gain,
        compounded_net_gain=net_gain,
        total_cost_paid=total_cost_paid,
        total_cost_share=cost_share,
        arithmetic_cost_share=arithmetic_cost_share,
        max_drawdown=max_dd,
        daily_realized_vol=_daily_realized_vol(daily.equity),
        time_in_market=statistics.fmean(1.0 if math.fsum(w.target.values()) > 0.0 else 0.0
                                        for w in weekly),
        mean_turnover=statistics.fmean(w.turnover for w in weekly),
        total_turnover=math.fsum(w.turnover for w in weekly),
        max_target_gross=max_target,
        max_pretrade_gross=max_pretrade,
        mean_active_assets=statistics.fmean(w.active_assets for w in weekly),
        post_etf_total_return=_compound(
            [w.net_return for w in weekly if w.fill_date >= date(2024, 1, 11)]
        ),
        cagr=_cagr(net_gain, start, end),
        passes_psr_stress=passes_psr,
        passes_drawdown=passes_drawdown,
        passes_cost_share=passes_cost,
        passes_notional=passes_notional,
        passes=passes_psr and passes_drawdown and passes_cost and passes_notional,
        cpcv=cpcv,
    )


def _buy_hold(
    bars: pl.DataFrame, start: date, end: date
) -> BuyHoldDiagnostic:
    by_symbol = _bars_by_symbol(bars)
    start_prices = {s: _open(by_symbol[s], start) for s in SYMBOLS}
    if any(v is None for v in start_prices.values()):
        raise TrendError(f"buy-hold missing start opens on {start}")
    weights = {s: 0.5 for s in SYMBOLS}
    equity: list[float] = []
    d = start
    while d < end:
        value = 0.0
        for symbol in SYMBOLS:
            sp = start_prices[symbol]
            close = _close(by_symbol[symbol], d)
            if sp is None or close is None:
                continue
            value += weights[symbol] * (close / sp)
        if value > 0.0:
            equity.append(value)
        d += timedelta(days=1)
    exit_value = 0.0
    for symbol in SYMBOLS:
        sp = start_prices[symbol]
        open_ = _open(by_symbol[symbol], end)
        if sp is None or open_ is None:
            raise TrendError(f"buy-hold missing exit open on {end}")
        exit_value += weights[symbol] * (open_ / sp)
    equity.append(exit_value)
    if not equity:
        raise TrendError("buy-hold diagnostic has no daily equity")
    total = equity[-1] - 1.0
    return BuyHoldDiagnostic(
        total_return=total,
        cagr=_cagr(total, start, end),
        max_drawdown=_max_drawdown(equity),
    )


def _source_checksums_sha256(sources: Sequence[SourceFile]) -> str:
    h = json.dumps([attrs.asdict(s) for s in sources], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(h.encode("utf-8")).hexdigest()


def _equity_kind(value: object) -> EquityPointKind:
    text = str(value)
    if text not in {"fill_after_cost", "daily_close", "exit_open"}:
        raise TrendError(f"unknown daily equity point kind {text!r}")
    return cast(EquityPointKind, text)


def _verdict(score: TrendScore, knobs: TrendKnobs) -> TrendVerdict:
    reasons: list[str] = []
    if not score.passes_psr_stress:
        reasons.append(
            f"CPCV stress PSR {score.cpcv_min_psr_stress:.3f} below {knobs.viability_bar:.2f}"
        )
    if not score.passes_drawdown:
        reasons.append(
            f"daily max drawdown {score.max_drawdown:.1%} above {knobs.max_drawdown_bar:.1%}"
        )
    if not score.passes_cost_share:
        reasons.append(
            f"cost share {score.total_cost_share:.1%} above {knobs.max_cost_share:.1%}"
        )
    if not score.passes_notional:
        reasons.append("notional cap or drift check failed")
    if reasons:
        return TrendVerdict(
            non_viable=True,
            headline="NON-VIABLE BTC/ETH slow-trend honest null",
            reason="; ".join(reasons),
        )
    return TrendVerdict(
        non_viable=False,
        headline="NOT KILLED on the BTC/ETH slow-trend gate, cross-check before belief",
        reason="all pre-registered Study 4 PR6a kill checks passed",
    )


def build_gate_artifact(
    bars: pl.DataFrame,
    *,
    bars_sha256: str,
    bars_relpath: str,
    sources_sha256: str,
    sources_relpath: str,
    sources: Sequence[SourceFile],
    knobs: TrendKnobs | None = None,
    cost_model: VenueCostModel = KRAKEN,
) -> TrendGateArtifact:
    """Build the PR6a gate artifact from the committed BTC/ETH fixture."""
    k = knobs if knobs is not None else TrendKnobs()
    cost_venue = _cost_venue(cost_model)
    weekly_raw, daily_path = _build_weekly(bars, k, cost_model)
    score = _score(weekly_raw, daily_path, k)
    weekly = tuple(_weekly_point(w) for w in weekly_raw)
    data_dates = sorted(bars["date"].unique().to_list())
    if not data_dates:
        raise TrendError("bars frame has no dates")
    buy_hold = _buy_hold(bars, weekly_raw[0].fill_date, weekly_raw[-1].exit_date)
    fingerprint = InputFingerprint(
        bars_sha256=bars_sha256,
        bars_relpath=bars_relpath,
        n_bar_rows=bars.height,
        sources_sha256=sources_sha256,
        sources_relpath=sources_relpath,
        n_source_files=len(sources),
        source_checksums_sha256=_source_checksums_sha256(sources),
    )
    return TrendGateArtifact(
        schema_version=SCHEMA_VERSION,
        study=_STUDY,
        data_start=data_dates[0].isoformat(),
        data_end=data_dates[-1].isoformat(),
        first_signal_date=weekly_raw[0].signal_date.isoformat(),
        first_fill_date=weekly_raw[0].fill_date.isoformat(),
        last_signal_date=weekly_raw[-1].signal_date.isoformat(),
        last_fill_date=weekly_raw[-1].fill_date.isoformat(),
        last_exit_date=weekly_raw[-1].exit_date.isoformat(),
        knobs=k,
        cost_venue=cost_venue,
        fingerprint=fingerprint,
        score=score,
        buy_hold=buy_hold,
        weekly=weekly,
        daily_equity=daily_path,
        verdict=_verdict(score, k),
        caveats=CAVEATS,
    )


def artifact_to_json(artifact: TrendGateArtifact) -> str:
    """Deterministic JSON with sorted keys and strict finite values."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_gate_artifact(artifact: TrendGateArtifact, path: Path) -> None:
    """Write the committed gate artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact_to_json(artifact), encoding="utf-8", newline="\n")


def _req(d: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        raise TrendError(f"trend artifact {ctx} missing key {key!r}")
    return d[key]


def _knobs(d: dict[str, Any]) -> TrendKnobs:
    return TrendKnobs(
        oos_start=str(_req(d, "oos_start", "knobs")),
        sma_days=int(_req(d, "sma_days", "knobs")),
        vol_lookback_days=int(_req(d, "vol_lookback_days", "knobs")),
        target_vol=float(_req(d, "target_vol", "knobs")),
        annualization_days=float(_req(d, "annualization_days", "knobs")),
        max_notional=float(_req(d, "max_notional", "knobs")),
        cost_venue=str(_req(d, "cost_venue", "knobs")),
        cash_return=float(_req(d, "cash_return", "knobs")),
        viability_bar=float(_req(d, "viability_bar", "knobs")),
        max_drawdown_bar=float(_req(d, "max_drawdown_bar", "knobs")),
        max_cost_share=float(_req(d, "max_cost_share", "knobs")),
    )


def _score_from_dict(d: dict[str, Any]) -> TrendScore:
    cpcv = _req(d, "cpcv", "score")
    return TrendScore(
        raw_t=int(_req(d, "raw_t", "score")),
        effective_t=int(_req(d, "effective_t", "score")),
        pw_block_length=float(_req(d, "pw_block_length", "score")),
        sr_hat=float(_req(d, "sr_hat", "score")),
        gamma_3=float(_req(d, "gamma_3", "score")),
        gamma_4=float(_req(d, "gamma_4", "score")),
        mean_net=float(_req(d, "mean_net", "score")),
        full_psr_zero=float(_req(d, "full_psr_zero", "score")),
        cpcv_min_psr_stress=float(_req(d, "cpcv_min_psr_stress", "score")),
        cpcv_median_psr_stress=float(_req(d, "cpcv_median_psr_stress", "score")),
        cpcv_max_psr_stress=float(_req(d, "cpcv_max_psr_stress", "score")),
        compounded_gross_gain=float(_req(d, "compounded_gross_gain", "score")),
        compounded_net_gain=float(_req(d, "compounded_net_gain", "score")),
        total_cost_paid=float(_req(d, "total_cost_paid", "score")),
        total_cost_share=float(_req(d, "total_cost_share", "score")),
        arithmetic_cost_share=float(_req(d, "arithmetic_cost_share", "score")),
        max_drawdown=float(_req(d, "max_drawdown", "score")),
        daily_realized_vol=float(_req(d, "daily_realized_vol", "score")),
        time_in_market=float(_req(d, "time_in_market", "score")),
        mean_turnover=float(_req(d, "mean_turnover", "score")),
        total_turnover=float(_req(d, "total_turnover", "score")),
        max_target_gross=float(_req(d, "max_target_gross", "score")),
        max_pretrade_gross=float(_req(d, "max_pretrade_gross", "score")),
        mean_active_assets=float(_req(d, "mean_active_assets", "score")),
        post_etf_total_return=float(_req(d, "post_etf_total_return", "score")),
        cagr=float(_req(d, "cagr", "score")),
        passes_psr_stress=bool(_req(d, "passes_psr_stress", "score")),
        passes_drawdown=bool(_req(d, "passes_drawdown", "score")),
        passes_cost_share=bool(_req(d, "passes_cost_share", "score")),
        passes_notional=bool(_req(d, "passes_notional", "score")),
        passes=bool(_req(d, "passes", "score")),
        cpcv=CpcvStress(
            n_groups=int(_req(cpcv, "n_groups", "cpcv")),
            k_test=int(_req(cpcv, "k_test", "cpcv")),
            n_splits=int(_req(cpcv, "n_splits", "cpcv")),
            min_train_size=int(_req(cpcv, "min_train_size", "cpcv")),
            min_test_size=int(_req(cpcv, "min_test_size", "cpcv")),
            split_psr_zero=tuple(float(x) for x in _req(cpcv, "split_psr_zero", "cpcv")),
        ),
    )


def load_gate_artifact(path: Path) -> TrendGateArtifact:
    """Load the committed trend gate artifact enough for reproduction tests."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TrendError(f"{path.name}: artifact is not a JSON object")
    fp = _req(data, "fingerprint", "root")
    cv = _req(data, "cost_venue", "root")
    verdict = _req(data, "verdict", "root")
    de = _req(data, "daily_equity", "root")
    return TrendGateArtifact(
        schema_version=int(_req(data, "schema_version", "root")),
        study=str(_req(data, "study", "root")),
        data_start=str(_req(data, "data_start", "root")),
        data_end=str(_req(data, "data_end", "root")),
        first_signal_date=str(_req(data, "first_signal_date", "root")),
        first_fill_date=str(_req(data, "first_fill_date", "root")),
        last_signal_date=str(_req(data, "last_signal_date", "root")),
        last_fill_date=str(_req(data, "last_fill_date", "root")),
        last_exit_date=str(_req(data, "last_exit_date", "root")),
        knobs=_knobs(_req(data, "knobs", "root")),
        cost_venue=CostVenue(
            name=str(_req(cv, "name", "cost_venue")),
            spot_taker_cost=float(_req(cv, "spot_taker_cost", "cost_venue")),
            spread_basis=str(_req(cv, "spread_basis", "cost_venue")),
            provisional=bool(_req(cv, "provisional", "cost_venue")),
            source=str(_req(cv, "source", "cost_venue")),
        ),
        fingerprint=InputFingerprint(
            bars_sha256=str(_req(fp, "bars_sha256", "fingerprint")),
            bars_relpath=str(_req(fp, "bars_relpath", "fingerprint")),
            n_bar_rows=int(_req(fp, "n_bar_rows", "fingerprint")),
            sources_sha256=str(_req(fp, "sources_sha256", "fingerprint")),
            sources_relpath=str(_req(fp, "sources_relpath", "fingerprint")),
            n_source_files=int(_req(fp, "n_source_files", "fingerprint")),
            source_checksums_sha256=str(_req(fp, "source_checksums_sha256", "fingerprint")),
        ),
        score=_score_from_dict(_req(data, "score", "root")),
        buy_hold=BuyHoldDiagnostic(
            total_return=float(_req(_req(data, "buy_hold", "root"), "total_return", "buy_hold")),
            cagr=float(_req(_req(data, "buy_hold", "root"), "cagr", "buy_hold")),
            max_drawdown=float(
                _req(_req(data, "buy_hold", "root"), "max_drawdown", "buy_hold")
            ),
        ),
        weekly=tuple(
            WeeklyTrendPoint(**w) for w in _req(data, "weekly", "root")
        ),
        daily_equity=DailyEquityPath(
            date=tuple(str(x) for x in _req(de, "date", "daily_equity")),
            kind=tuple(_equity_kind(x) for x in _req(de, "kind", "daily_equity")),
            equity=tuple(float(x) for x in _req(de, "equity", "daily_equity")),
        ),
        verdict=TrendVerdict(
            non_viable=bool(_req(verdict, "non_viable", "verdict")),
            headline=str(_req(verdict, "headline", "verdict")),
            reason=str(_req(verdict, "reason", "verdict")),
        ),
        caveats=tuple(str(x) for x in _req(data, "caveats", "root")),
    )
