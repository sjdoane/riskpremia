"""The point-in-time, delisting-complete multi-coin universe (CTREND Study 3, PR1).

The data foundation the signal (PR2) and the backtest + kill gate (PR3) consume. It
turns the delisting-complete Binance Vision DAILY spot klines into (i) a daily panel
(close + USD dollar volume per coin) that PR2 computes the 28 daily technical signals on,
and (ii) a weekly rebalance grid (returns + a point-in-time liquid-universe eligibility
flag) that PR3 backtests. The design is reviewed in docs/research/0002-ctrend-universe-
design.md; the load-bearing honesty properties are PIT liquidity selection (no
look-ahead), delisting handled by absence (no survivorship), and a gap-safe weekly return.

Why daily AND weekly: the paper computes its signals on DAILY bars (a 14-day RSI, 3- to
200-day SMAs) but rebalances WEEKLY. So the universe stores daily price + volume and
derives the weekly grid from it. The committed reproducibility anchor is the daily panel;
the weekly grid + the eligibility are pure functions of it (computed here, never
separately committed, so they cannot drift).

Deviations from the paper, forced by the data and documented (ADR 0005 caveats): the
universe is screened by trailing USD DOLLAR VOLUME (Binance has no market cap, the
paper's screen), and stablecoin/fiat pairs + leveraged tokens are excluded (a
dollar-volume-ranked universe would otherwise be dominated by pegs, and the paper's
"coins" are not pegs or decaying derivatives).

Stdlib + polars only; no RNG; no I/O (the source/build script do the fetching). The single
documented Decimal -> Float64 cast happens at the daily-panel build, mirroring `clock.py`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import polars as pl

from riskpremia.ctrend.errors import CtrendError
from riskpremia.data.records import SpotKlineRecord, derive_canonical

# ----- universe-definition knobs (each a PR2/PR3 trial-registry entry) --------

DEFAULT_QUOTE = "USDT"
DEFAULT_TOP_N = 100
"""The liquid-universe size (the paper's Table 8 'top 100 liquid' subset; 20 per quintile)."""
DEFAULT_LOOKBACK_WEEKS = 4
"""Trailing weekly bars averaged for the liquidity rank (a ~1-month ADV proxy)."""
DEFAULT_MIN_HISTORY_WEEKS = 8
"""Minimum weekly bars a coin must have (up to and including week t) to be rankable, so a
one-week listing volume spike cannot enter the universe."""
N_MAX_COMMITTED = 120
"""The committed-panel trim ceiling: the panel retains every coin ever in the top-N_MAX,
so the eligibility for any top-N (N <= N_MAX) reproduces offline from the committed panel
(the losslessness argument, asserted in the build)."""

_WEEK_DAYS = 7

# ----- the exclusion filter (deterministic, documented; ADR 0005) ------------

STABLE_OR_FIAT: frozenset[str] = frozenset(
    {
        # USD stablecoins (a USD peg has no trend signal and would dominate a
        # dollar-volume-ranked universe).
        "USDC", "BUSD", "TUSD", "FDUSD", "USDP", "DAI", "UST", "USTC", "GUSD", "USDD",
        "USD1", "PYUSD", "USDE", "SUSD", "FRAX", "LUSD", "USDS", "FDUSDT",
        # Fiat (a fiat-vs-USDT pair is an FX rate, not a coin).
        "EUR", "GBP", "AUD", "TRY", "BRL", "RUB", "JPY", "AEUR", "EURI", "USTRY",
    }
)
"""Stablecoin / fiat BASES excluded from the universe. Hand-curated and necessarily
incomplete; the build emits the full excluded list into the artifact so a missed peg is
visible to a reviewer (design review M4). Verified June 2026."""

_LEVERAGED_SUFFIXES: tuple[str, ...] = ("BULL", "BEAR", "3L", "3S", "4L", "4S", "5L", "5S")
"""Binance leveraged-token base suffixes excluded unconditionally (no real coin ends in
these). UP / DOWN are handled separately (they need the listed-base disambiguation)."""

EXCLUDED_STABLE = "stablecoin_or_fiat"
EXCLUDED_LEVERAGED = "leveraged_token"
EXCLUDED_NON_STANDARD = "non_standard_ticker"

_STANDARD_TICKER = re.compile(r"[A-Z0-9]+")
"""A standard crypto ticker base is ASCII uppercase-alphanumeric (BTC, ETH, 1000SHIB).
The Binance Vision bucket carries a few non-ASCII novelty symbols (e.g. a CJK-named promo
token) that are not coins in the paper's sense and cannot even be ASCII-encoded into an S3
URL; they are excluded as non-standard."""


def symbol_base(symbol: str, quote: str = DEFAULT_QUOTE) -> str:
    """The base asset of a quote-suffixed symbol (`BTCUSDT` -> `BTC`)."""
    if symbol.endswith(quote) and len(symbol) > len(quote):
        return symbol[: -len(quote)]
    return symbol


def is_leveraged_token(base: str, listed_bases: frozenset[str]) -> bool:
    """Whether `base` is a Binance leveraged token, given the set of listed bases.

    BULL / BEAR / nL / nS suffixes are leveraged unconditionally. UP / DOWN are leveraged
    only when the base minus the suffix is itself a listed base (so `BTCUP` -> `BTC` is
    listed -> leveraged, while `JUP` -> `J` is not a base -> a real coin, kept). This
    listed-base disambiguation is what avoids the JUP / SUPER false positives.
    """
    if any(base.endswith(suffix) and base != suffix for suffix in _LEVERAGED_SUFFIXES):
        return True
    for suffix in ("UP", "DOWN"):
        if base.endswith(suffix) and base != suffix:
            stem = base[: -len(suffix)]
            if stem in listed_bases:
                return True
    return False


def classify_exclusion(
    symbol: str, listed_bases: frozenset[str], *, quote: str = DEFAULT_QUOTE
) -> str | None:
    """The exclusion reason for `symbol`, or None if it is a tradeable coin.

    Returns `EXCLUDED_NON_STANDARD`, `EXCLUDED_STABLE`, `EXCLUDED_LEVERAGED`, or None. A
    non-standard (non-ASCII / non-alphanumeric) ticker is rejected first (it is not a coin
    and cannot be fetched); then stable/fiat (a stablecoin named like a leveraged token is
    still a stablecoin); then leveraged tokens.
    """
    base = symbol_base(symbol, quote)
    if _STANDARD_TICKER.fullmatch(base) is None:
        return EXCLUDED_NON_STANDARD
    if base in STABLE_OR_FIAT:
        return EXCLUDED_STABLE
    if is_leveraged_token(base, listed_bases):
        return EXCLUDED_LEVERAGED
    return None


def listed_bases_of(symbols: Sequence[str], *, quote: str = DEFAULT_QUOTE) -> frozenset[str]:
    """The set of all bases in `symbols` (for the leveraged-token disambiguation)."""
    return frozenset(symbol_base(s, quote) for s in symbols)


def tradeable_universe(symbols: Sequence[str], *, quote: str = DEFAULT_QUOTE) -> tuple[str, ...]:
    """The enumerated symbols minus stablecoins/fiat and leveraged tokens, sorted."""
    bases = listed_bases_of(symbols, quote=quote)
    kept = [s for s in symbols if classify_exclusion(s, bases, quote=quote) is None]
    return tuple(sorted(set(kept)))


def excluded_symbols(
    symbols: Sequence[str], *, quote: str = DEFAULT_QUOTE
) -> tuple[tuple[str, str], ...]:
    """The excluded `(symbol, reason)` pairs, sorted by symbol (for the artifact, M4)."""
    bases = listed_bases_of(symbols, quote=quote)
    out: list[tuple[str, str]] = []
    for s in sorted(set(symbols)):
        reason = classify_exclusion(s, bases, quote=quote)
        if reason is not None:
            out.append((s, reason))
    return tuple(out)


# ----- the daily panel + the weekly grid -------------------------------------

_DAILY_SCHEMA = {
    "date": pl.Date,
    "symbol": pl.Utf8,
    "close": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "dollar_volume": pl.Float64,
}


def _min_float(frame: pl.DataFrame, column: str) -> float | None:
    """The minimum of a numeric column as a float, or None on an empty column.

    `Series.min()` is typed as a broad scalar union; the column is Float64, so the runtime
    value is a float or None. Narrowing through `Any` at this single point keeps mypy
    --strict clean (the `clock.py` `_scalar_float` precedent).
    """
    value: Any = frame[column].min()
    return None if value is None else float(value)


def build_daily_panel(records: Sequence[SpotKlineRecord]) -> pl.DataFrame:
    """Assemble the canonical daily panel `(date, symbol, close, high, low, dollar_volume)`.

    The single documented Decimal -> Float64 cast site. Deduped on `(date, symbol)`
    (keeping the last, a benign re-publish), sorted by `(symbol, date)`. Raises on a
    non-positive low/close, a negative dollar volume, or an inconsistent OHLC bar
    (high < low, or the close outside [low, high]) (corrupt data).
    """
    if len(records) == 0:
        raise CtrendError("build_daily_panel requires at least one record")
    frame = pl.DataFrame(
        {
            "date": [r.period_end_ts.date() for r in records],
            "symbol": [r.instrument.symbol for r in records],
            "close": [float(r.close) for r in records],
            "high": [float(r.high) for r in records],
            "low": [float(r.low) for r in records],
            "dollar_volume": [float(r.quote_volume) for r in records],
        },
        schema=_DAILY_SCHEMA,
    )
    min_low = _min_float(frame, "low")
    if min_low is not None and min_low <= 0.0:
        raise CtrendError(f"build_daily_panel got a non-positive low ({min_low})")
    min_close = _min_float(frame, "close")
    if min_close is not None and min_close <= 0.0:
        raise CtrendError(f"build_daily_panel got a non-positive close ({min_close})")
    min_vol = _min_float(frame, "dollar_volume")
    if min_vol is not None and min_vol < 0.0:
        raise CtrendError(f"build_daily_panel got a negative dollar_volume ({min_vol})")
    bad = frame.filter(
        (pl.col("high") < pl.col("low"))
        | (pl.col("close") > pl.col("high"))
        | (pl.col("close") < pl.col("low"))
    )
    if bad.height > 0:
        row = bad.row(0, named=True)
        raise CtrendError(
            f"build_daily_panel got an inconsistent OHLC bar (close not in [low, high] or "
            f"high < low): {row['symbol']} {row['date']} "
            f"close={row['close']} high={row['high']} low={row['low']}"
        )
    return (
        frame.unique(subset=["date", "symbol"], keep="last", maintain_order=True)
        .sort(["symbol", "date"])
    )


def _canonical_frame(symbols: Sequence[str]) -> pl.DataFrame:
    """A `(symbol, canonical)` lookup frame (canonical is informational, never a key)."""
    uniq = sorted(set(symbols))
    return pl.DataFrame(
        {"symbol": uniq, "canonical": [derive_canonical(s) for s in uniq]},
        schema={"symbol": pl.Utf8, "canonical": pl.Utf8},
    )


def build_weekly_panel(daily: pl.DataFrame) -> pl.DataFrame:
    """Resample the daily panel to a weekly grid (week ending Sunday UTC).

    For each `(symbol, week_end)`: `weekly_close` is the last daily close in the week,
    `weekly_dollar_volume` is the sum of daily dollar volume, `n_days` the daily-bar
    count. Then, within symbol sorted by week_end: `weekly_return(t) = close(t)/close(t-1)
    - 1` is NULL across a non-consecutive-week gap (a halt is never mislabeled as a
    one-week return), and `forward_return(t)` is `weekly_return` shifted -1 (the holding
    return over (t, t+1] that PR3 must use, named so the same-bar look-ahead is hard to
    hit). `canonical` is informational. Columns are returned sorted by `(symbol,
    week_end)`.

    Raises:
      CtrendError: on an empty daily panel.
    """
    if daily.height == 0:
        raise CtrendError("build_weekly_panel requires a non-empty daily panel")
    monday = pl.col("date") - pl.duration(days=pl.col("date").dt.weekday() - 1)
    with_week = daily.with_columns((monday + pl.duration(days=6)).cast(pl.Date).alias("week_end"))
    weekly = (
        with_week.group_by(["symbol", "week_end"])
        .agg(
            pl.col("close").sort_by("date").last().alias("weekly_close"),
            pl.col("dollar_volume").sum().alias("weekly_dollar_volume"),
            pl.len().alias("n_days"),
        )
        .sort(["symbol", "week_end"])
        .join(_canonical_frame(daily["symbol"].to_list()), on="symbol", how="left")
    )
    weekly = weekly.with_columns(
        pl.col("week_end").diff().dt.total_days().over("symbol").alias("_gap_days"),
        (pl.col("weekly_close") / pl.col("weekly_close").shift(1).over("symbol") - 1.0).alias(
            "_raw_return"
        ),
    )
    weekly = weekly.with_columns(
        pl.when(pl.col("_gap_days") == _WEEK_DAYS)
        .then(pl.col("_raw_return"))
        .otherwise(None)
        .alias("weekly_return"),
        (pl.col("_gap_days").is_not_null() & (pl.col("_gap_days") != _WEEK_DAYS)).alias(
            "gap_before"
        ),
    )
    weekly = weekly.with_columns(
        pl.col("weekly_return").shift(-1).over("symbol").alias("forward_return")
    )
    return weekly.drop("_gap_days", "_raw_return").select(
        "week_end",
        "symbol",
        "canonical",
        "weekly_close",
        "weekly_dollar_volume",
        "n_days",
        "weekly_return",
        "forward_return",
        "gap_before",
    ).sort(["symbol", "week_end"])


# ----- the point-in-time liquidity eligibility (the load-bearing PIT spine) ---


def pit_eligible(
    weekly: pl.DataFrame,
    *,
    top_n: int = DEFAULT_TOP_N,
    lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS,
    min_history_weeks: int = DEFAULT_MIN_HISTORY_WEEKS,
) -> pl.DataFrame:
    """Mark the point-in-time liquid top-`top_n` universe per week.

    For each symbol (sorted by week_end): `n_weekly_bars` is the count of weekly bars up
    to and including week t, and `trailing_dollar_volume` is the backward rolling mean of
    `weekly_dollar_volume` over the last `lookback_weeks` bars ENDING at week t (strictly
    point-in-time; uses only data at or before t). A symbol is `rankable` at week t if it
    has at least `min_history_weeks` weekly bars up to t. Within each week, the rankable
    symbols are ranked by `trailing_dollar_volume` descending, tie-broken by `symbol`
    ascending, and the top `top_n` are `eligible`.

    All windows are counted in WEEKLY BARS (== calendar weeks absent a trading halt); the
    rank reads only data at or before t. Delisting is handled by absence: after a coin's
    last bar it has no row, so it is not eligible, but its earlier weeks still rank.

    Adds `n_weekly_bars`, `trailing_dollar_volume`, `rankable`, `liquidity_rank` (0-based
    among rankable within the week, null for non-rankable), and `eligible`. Returned
    sorted by `(week_end, symbol)`.

    Raises:
      CtrendError: on a non-positive knob, or an empty/unsorted panel.
    """
    if top_n < 1:
        raise CtrendError(f"pit_eligible requires top_n >= 1; got {top_n}")
    if lookback_weeks < 1:
        raise CtrendError(f"pit_eligible requires lookback_weeks >= 1; got {lookback_weeks}")
    if min_history_weeks < 1:
        raise CtrendError(f"pit_eligible requires min_history_weeks >= 1; got {min_history_weeks}")
    if weekly.height == 0:
        raise CtrendError("pit_eligible requires a non-empty weekly panel")

    by_symbol = weekly.sort(["symbol", "week_end"])
    by_symbol = by_symbol.with_columns(
        pl.col("week_end").cum_count().over("symbol").alias("n_weekly_bars"),
        pl.col("weekly_dollar_volume")
        .rolling_mean(window_size=lookback_weeks, min_samples=1)
        .over("symbol")
        .alias("trailing_dollar_volume"),
    )
    by_symbol = by_symbol.with_columns(
        (pl.col("n_weekly_bars") >= min_history_weeks).alias("rankable")
    )

    # Rank within each week among rankable rows only. Sorting by (week_end asc,
    # trailing_dollar_volume desc, symbol asc) puts each week's rows in descending-volume,
    # then ascending-symbol order; the cumulative count of rankable rows in that order is
    # the 0-based liquidity rank. The explicit per-key descending flags avoid the
    # struct.rank(descending=True) trap that would tie-break the symbol the wrong way
    # (design review C2). The ascending symbol therefore wins a volume tie.
    ranked = by_symbol.sort(
        ["week_end", "trailing_dollar_volume", "symbol"], descending=[False, True, False]
    )
    ranked = ranked.with_columns(
        pl.when(pl.col("rankable"))
        .then(pl.col("rankable").cast(pl.Int64).cum_sum().over("week_end") - 1)
        .otherwise(None)
        .alias("liquidity_rank")
    )
    ranked = ranked.with_columns(
        (pl.col("rankable") & (pl.col("liquidity_rank") < top_n)).alias("eligible")
    )
    return ranked.sort(["week_end", "symbol"])


def ever_eligible_symbols(
    weekly: pl.DataFrame,
    *,
    top_n: int = N_MAX_COMMITTED,
    lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS,
    min_history_weeks: int = DEFAULT_MIN_HISTORY_WEEKS,
) -> tuple[str, ...]:
    """The union over all weeks of the top-`top_n` eligible symbols, sorted.

    Defaulting `top_n` to `N_MAX_COMMITTED` gives the committed-panel trim set: every coin
    ever in the top-N_MAX, so any top-N (N <= N_MAX) reproduces from the trimmed panel.
    """
    flagged = pit_eligible(
        weekly, top_n=top_n, lookback_weeks=lookback_weeks, min_history_weeks=min_history_weeks
    )
    eligible = flagged.filter(pl.col("eligible"))["symbol"].unique().to_list()
    return tuple(sorted(eligible))


def eligible_pairs(weekly: pl.DataFrame, **kwargs: int) -> set[tuple[str, str]]:
    """The set of eligible `(week_end_iso, symbol)` pairs (for the losslessness check)."""
    flagged = pit_eligible(weekly, **kwargs)
    sub = flagged.filter(pl.col("eligible")).select(
        pl.col("week_end").cast(pl.Utf8), pl.col("symbol")
    )
    return {(str(w), str(s)) for w, s in zip(sub["week_end"], sub["symbol"], strict=True)}


def trim_daily_to(daily: pl.DataFrame, symbols: Sequence[str]) -> pl.DataFrame:
    """Restrict the daily panel to `symbols` (the ever-top-N_MAX committed set)."""
    keep = pl.Series("symbol", sorted(set(symbols)), dtype=pl.Utf8)
    return daily.filter(pl.col("symbol").is_in(keep)).sort(["symbol", "date"])


def eligible_count_per_week(flagged: pl.DataFrame) -> pl.DataFrame:
    """The number of eligible symbols per week (a `(week_end, n_eligible)` frame)."""
    return (
        flagged.filter(pl.col("eligible"))
        .group_by("week_end")
        .agg(pl.len().alias("n_eligible"))
        .sort("week_end")
    )
