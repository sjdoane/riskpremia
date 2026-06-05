"""The 28 CTREND daily technical signals (Study 3, PR2).

Computes the paper's 28 daily indicators (Fieberg et al. JFQA 2025, Section III.B) on the
daily panel per coin (polars rolling / EWM over the (symbol, date)-sorted frame, strictly
backward = point-in-time), then samples each at the weekly rebalance date (the last daily
bar of each ISO week, matching the PR1 weekly_close). The output frame is the input the
cross-sectional CS-C-ENet (signal.py) consumes.

Faithfulness (docs/research/0003): the paper STATES the SMA lengths (3/5/10/20/50/100/200),
the 14-day RSI and stochastics, the 3-day %D, the 12/26/9 MACD, the 20-day / 2-std Bollinger
bands, and the StochRSI prose; the exact Appendix-A formulas were not obtainable, so the
canonical practitioner defaults are used for the unstated parameters (Wilder RSI, a 20-day
CCI on the typical price with the 0.015 constant, a 20-day Chaikin money flow, 12/26/9 EMAs
for the volume MACD, population std for Bollinger), each a documented convention + a PR3
robustness knob. Every signal is cross-sectionally RANKED before it enters a regression
(signal.py), so a common monotonic transform (a scale, a units choice, the EMA seed) is
rank-innocuous; the conventions matter only where they change the cross-sectional ORDER.

Conventions (pinned): EWMs use `adjust=False` (Wilder/standard recursive form) with
`min_samples=span` and `ignore_nulls=True` (so an EMA-of-an-EMA starts only once its input
exists); every rolling window uses `min_samples=window` (NULL until the full window is
available, so a just-listed coin has no signal rather than a noisy partial one); the std is
population (ddof=0, the Bollinger standard). Stdlib + polars only; no RNG; no I/O.
"""

from __future__ import annotations

import polars as pl

from riskpremia.ctrend.errors import CtrendError

SMA_LENGTHS: tuple[int, ...] = (3, 5, 10, 20, 50, 100, 200)
_RSI_PERIOD = 14
_STOCH_PERIOD = 14
_STOCH_D = 3
_CCI_PERIOD = 20
_CHAIKIN_PERIOD = 20
_BOLL_PERIOD = 20
_BOLL_K = 2.0
_MACD_FAST = 12
_MACD_SLOW = 26
_MACD_SIGNAL = 9

SIGNAL_COLUMNS: tuple[str, ...] = (
    # momentum oscillators (5)
    "rsi", "stochK", "stochD", "stochRSI", "cci",
    # price moving averages (9)
    "sma_3d", "sma_5d", "sma_10d", "sma_20d", "sma_50d", "sma_100d", "sma_200d",
    "macd", "macd_diff_signal",
    # volume (10)
    "volsma_3d", "volsma_5d", "volsma_10d", "volsma_20d", "volsma_50d", "volsma_100d",
    "volsma_200d", "volmacd", "volmacd_diff_signal", "chaikin",
    # volatility (4)
    "boll_mid", "boll_high", "boll_low", "boll_width",
)


def _ema(col: str, span: int) -> pl.Expr:
    """Per-symbol recursive EMA (adjust=False), null until `span` observations."""
    return (
        pl.col(col)
        .ewm_mean(span=span, adjust=False, min_samples=span, ignore_nulls=True)
        .over("symbol")
    )


def _ema_of(expr: pl.Expr, span: int, alias: str) -> pl.Expr:
    """EMA of an intermediate expression (used after it is materialized as a column)."""
    return (
        pl.col(alias)
        .ewm_mean(span=span, adjust=False, min_samples=span, ignore_nulls=True)
        .over("symbol")
    )


def _ppo(fast_col: str, slow_col: str) -> pl.Expr:
    """The percentage price/volume oscillator: (EMA_fast - EMA_slow) / EMA_fast."""
    fast = _ema(fast_col, _MACD_FAST)
    slow = _ema(slow_col, _MACD_SLOW)
    return (fast - slow) / fast


def _roll(col: str, op: str, window: int) -> pl.Expr:
    """A per-symbol trailing rolling reduction, null until `window` observations.

    `op` is one of mean / min / max / sum / std (std is population, ddof=0).
    """
    base = pl.col(col)
    if op == "mean":
        rolled = base.rolling_mean(window_size=window, min_samples=window)
    elif op == "min":
        rolled = base.rolling_min(window_size=window, min_samples=window)
    elif op == "max":
        rolled = base.rolling_max(window_size=window, min_samples=window)
    elif op == "sum":
        rolled = base.rolling_sum(window_size=window, min_samples=window)
    elif op == "std":
        rolled = base.rolling_std(window_size=window, min_samples=window, ddof=0)
    else:  # pragma: no cover - guards an internal typo
        raise CtrendError(f"_roll: unknown op {op!r}")
    return rolled.over("symbol")


def compute_daily_features(daily: pl.DataFrame) -> pl.DataFrame:
    """Add the 28 daily signal columns to the daily panel (per symbol, strictly backward).

    Expects the PR1 daily panel `(date, symbol, close, high, low, dollar_volume)`. Returns
    the frame with the 28 `SIGNAL_COLUMNS` added, sorted by `(symbol, date)`.

    Raises:
      CtrendError: on an empty panel or a missing required column.
    """
    required = {"date", "symbol", "close", "high", "low", "dollar_volume"}
    missing = required - set(daily.columns)
    if missing:
        raise CtrendError(f"compute_daily_features missing columns {sorted(missing)}")
    if daily.height == 0:
        raise CtrendError("compute_daily_features requires a non-empty daily panel")
    df = daily.sort(["symbol", "date"])

    # ----- price + volume simple moving averages (scaled) ------------------
    sma_exprs = [
        (_roll("close", "mean", length) / pl.col("close")).alias(f"sma_{length}d")
        for length in SMA_LENGTHS
    ]
    volsma_exprs = [
        (_roll("dollar_volume", "mean", length) / pl.col("dollar_volume")).alias(
            f"volsma_{length}d"
        )
        for length in SMA_LENGTHS
    ]
    df = df.with_columns(*sma_exprs, *volsma_exprs)

    # ----- MACD / volume-MACD (PPO / PVO) + the signal-line difference ------
    df = df.with_columns(
        _ppo("close", "close").alias("macd"),
        _ppo("dollar_volume", "dollar_volume").alias("volmacd"),
    )
    df = df.with_columns(
        (pl.col("macd") - _ema_of(pl.col("macd"), _MACD_SIGNAL, "macd")).alias("macd_diff_signal"),
        (pl.col("volmacd") - _ema_of(pl.col("volmacd"), _MACD_SIGNAL, "volmacd")).alias(
            "volmacd_diff_signal"
        ),
    )

    # ----- RSI (Wilder) + StochRSI -----------------------------------------
    df = df.with_columns(pl.col("close").diff().over("symbol").alias("_delta"))
    # The first delta of each symbol is null; keep gain/loss null there (rather than 0) so the
    # Wilder EWM seeds at the first real move, not at a spurious 0 (the cleaner convention).
    df = df.with_columns(
        pl.when(pl.col("_delta").is_null())
        .then(None)
        .when(pl.col("_delta") > 0)
        .then(pl.col("_delta"))
        .otherwise(0.0)
        .alias("_gain"),
        pl.when(pl.col("_delta").is_null())
        .then(None)
        .when(pl.col("_delta") < 0)
        .then(-pl.col("_delta"))
        .otherwise(0.0)
        .alias("_loss"),
    )
    wilder_alpha = 1.0 / _RSI_PERIOD
    df = df.with_columns(
        pl.col("_gain").ewm_mean(alpha=wilder_alpha, adjust=False, min_samples=_RSI_PERIOD,
                                 ignore_nulls=True).over("symbol").alias("_avg_gain"),
        pl.col("_loss").ewm_mean(alpha=wilder_alpha, adjust=False, min_samples=_RSI_PERIOD,
                                 ignore_nulls=True).over("symbol").alias("_avg_loss"),
    )
    # RSI = 100 - 100/(1+RS); RS = avg_gain/avg_loss. avg_loss == 0 -> RSI 100 (all gains).
    df = df.with_columns(
        pl.when(pl.col("_avg_loss") == 0.0)
        .then(100.0)
        .otherwise(100.0 - 100.0 / (1.0 + pl.col("_avg_gain") / pl.col("_avg_loss")))
        .alias("rsi")
    )
    rsi_min = _roll("rsi", "min", _STOCH_PERIOD)
    rsi_max = _roll("rsi", "max", _STOCH_PERIOD)
    df = df.with_columns(
        pl.when((rsi_max - rsi_min) > 0.0)
        .then((pl.col("rsi") - rsi_min) / (rsi_max - rsi_min))
        .otherwise(None)
        .alias("stochRSI")
    )

    # ----- stochastic %K / %D ----------------------------------------------
    low_min = _roll("low", "min", _STOCH_PERIOD)
    high_max = _roll("high", "max", _STOCH_PERIOD)
    df = df.with_columns(
        pl.when((high_max - low_min) > 0.0)
        .then(100.0 * (pl.col("close") - low_min) / (high_max - low_min))
        .otherwise(None)
        .alias("stochK")
    )
    df = df.with_columns(_roll("stochK", "mean", _STOCH_D).alias("stochD"))

    # ----- CCI (typical price, mean absolute deviation) --------------------
    df = df.with_columns(((pl.col("high") + pl.col("low") + pl.col("close")) / 3.0).alias("_tp"))
    df = df.with_columns(_roll("_tp", "mean", _CCI_PERIOD).alias("_sma_tp"))
    # Mean absolute deviation over the window = mean_k |TP.shift(k) - SMA_TP_current|, the exact
    # CCI dispersion (each window value's deviation from the window mean), vectorized as the
    # average of the period shifted abs-deviations (null until the full window exists).
    mad_terms = [
        (pl.col("_tp").shift(k).over("symbol") - pl.col("_sma_tp")).abs()
        for k in range(_CCI_PERIOD)
    ]
    df = df.with_columns((pl.sum_horizontal(mad_terms) / _CCI_PERIOD).alias("_mad_tp"))
    df = df.with_columns(
        pl.when(pl.col("_mad_tp") > 0.0)
        .then((pl.col("_tp") - pl.col("_sma_tp")) / (0.015 * pl.col("_mad_tp")))
        .otherwise(None)
        .alias("cci")
    )

    # ----- Chaikin money flow (dollar-volume convention) -------------------
    # Money-flow multiplier ((C-L)-(H-C))/(H-L); CMF = sum(mult * V) / sum(V) over the window.
    mfm = pl.when((pl.col("high") - pl.col("low")) > 0.0).then(
        ((pl.col("close") - pl.col("low")) - (pl.col("high") - pl.col("close")))
        / (pl.col("high") - pl.col("low"))
    ).otherwise(0.0)
    df = df.with_columns((mfm * pl.col("dollar_volume")).alias("_mfv"))
    mfv_sum = _roll("_mfv", "sum", _CHAIKIN_PERIOD)
    vol_sum = _roll("dollar_volume", "sum", _CHAIKIN_PERIOD)
    df = df.with_columns(
        pl.when(vol_sum > 0.0).then(mfv_sum / vol_sum).otherwise(None).alias("chaikin")
    )

    # ----- Bollinger bands (scaled by close) -------------------------------
    sma20 = _roll("close", "mean", _BOLL_PERIOD)
    std20 = _roll("close", "std", _BOLL_PERIOD)
    df = df.with_columns(
        (sma20 / pl.col("close")).alias("boll_mid"),
        ((sma20 + _BOLL_K * std20) / pl.col("close")).alias("boll_high"),
        ((sma20 - _BOLL_K * std20) / pl.col("close")).alias("boll_low"),
    )
    # boll_width = (boll_high - boll_low) / boll_mid = 2*K*std/SMA (close cancels).
    df = df.with_columns(
        pl.when(sma20 > 0.0)
        .then((pl.col("boll_high") - pl.col("boll_low")) / pl.col("boll_mid"))
        .otherwise(None)
        .alias("boll_width")
    )

    helpers = [c for c in df.columns if c.startswith("_")]
    return df.drop(helpers).select(*daily.columns, *SIGNAL_COLUMNS)


def _week_end_expr() -> pl.Expr:
    """The Sunday (ISO week end) of each daily date, matching `build_weekly_panel`."""
    monday = pl.col("date") - pl.duration(days=pl.col("date").dt.weekday() - 1)
    return (monday + pl.duration(days=6)).cast(pl.Date).alias("week_end")


def sample_weekly_features(daily_features: pl.DataFrame) -> pl.DataFrame:
    """Sample each daily signal at the last daily bar of each ISO week, per symbol.

    Returns `(week_end, symbol, <28 signal columns>)`, the value of each indicator at the
    week's last trading day (the same bar `build_weekly_panel` uses for `weekly_close`), so
    the signal at `week_end` uses only daily data at or before it (point-in-time). Sorted by
    `(symbol, week_end)`.
    """
    with_week = daily_features.with_columns(_week_end_expr())
    aggs = [pl.col(sig).sort_by("date").last().alias(sig) for sig in SIGNAL_COLUMNS]
    return (
        with_week.group_by(["symbol", "week_end"])
        .agg(*aggs)
        .sort(["symbol", "week_end"])
        .select("week_end", "symbol", *SIGNAL_COLUMNS)
    )


def compute_weekly_features(daily: pl.DataFrame) -> pl.DataFrame:
    """Daily features then weekly sampling: the `(week_end, symbol, <28>)` signal frame."""
    return sample_weekly_features(compute_daily_features(daily))
