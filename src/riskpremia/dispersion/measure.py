"""The cross-sectional funding-dispersion aggregation (Study 7, ADR 0009).

Turns per-coin perpetual funding events and the point-in-time eligibility into the daily
dispersion series. The frozen method: annualize each event with its own funding interval, carry
each coin's annualized rate forward onto a fixed common daily grid (a point-in-time backward
join, rejected across a multi-day gap), restrict to the point-in-time eligible coins each day,
and compute the equal-weight cross-sectional dispersion (interquartile range, standard
deviation, winsorized standard deviation) plus the secondary gross high-minus-low sort premium
realized over the next period. The raw-funding-to-series aggregation lives here and is exercised
by unit tests on synthetic funding; the artifact (bootstrap, regime split, decay) is built from
the resulting series in `artifact.py`.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import date, datetime

import polars as pl

from riskpremia.data.clock import CRYPTO_ANNUALIZATION_DAYS
from riskpremia.dispersion.errors import DispersionError
from riskpremia.dispersion.fixtures import DispersionDailyRow

ANNUALIZATION_HOURS = CRYPTO_ANNUALIZATION_DAYS * 24.0  # 8760, single-sourced
DEFAULT_TOP_N = 50
DEFAULT_MAX_GAP_DAYS = 3
DEFAULT_WINSOR_PCT = 0.05
DEFAULT_N_QUANTILES = 5
MIN_CROSS_SECTION = 5  # a day needs at least this many funded coins to be measured

# One day's carried cross-section: (symbol, annualized funding, next-period annualized funding).
_DayGroup = tuple[date, list[tuple[str, float | None, float | None]]]

_FUNDING_SCHEMA = {
    "symbol": pl.Utf8,
    "ts": pl.Datetime("us", "UTC"),
    "rate": pl.Float64,
    "interval_hours": pl.Int64,
}


def annualize(rate: float, interval_hours: float) -> float:
    """Annualize a per-event funding rate via its own interval (basis 365 * 24 = 8760)."""
    if interval_hours <= 0.0:
        raise DispersionError(f"funding interval must be positive; got {interval_hours}")
    return rate * ANNUALIZATION_HOURS / interval_hours


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile on an already-sorted sequence."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _winsorized_std(values: Sequence[float], pct: float) -> float:
    if len(values) < 2:
        return float("nan")
    s = sorted(values)
    lo = _quantile(s, pct)
    hi = _quantile(s, 1.0 - pct)
    clipped = [min(max(v, lo), hi) for v in values]
    return statistics.stdev(clipped)


def _sort_premium(
    pairs: Sequence[tuple[float, float | None]], n_quantiles: int
) -> float | None:
    """Gross high-minus-low next-period funding premium for one day.

    `pairs` is (today's annualized funding, next-period annualized funding) per funded coin.
    Coins are sorted by today's funding into `n_quantiles` buckets; the premium is the mean
    next-period funding of the top bucket minus that of the bottom bucket, over the coins whose
    next-period funding is observed. Returns None if either bucket has no observed next period.
    """
    if len(pairs) < n_quantiles:
        return None
    ordered = sorted(pairs, key=lambda p: p[0])
    bucket = max(1, len(ordered) // n_quantiles)
    bottom = [nxt for _, nxt in ordered[:bucket] if nxt is not None]
    top = [nxt for _, nxt in ordered[-bucket:] if nxt is not None]
    if not bottom or not top:
        return None
    return statistics.fmean(top) - statistics.fmean(bottom)


def _week_end_expr() -> pl.Expr:
    """The Sunday-ending week of each `date`, matching the CTREND weekly grid."""
    monday = pl.col("date") - pl.duration(days=pl.col("date").dt.weekday() - 1)
    return (monday + pl.duration(days=6)).cast(pl.Date).alias("week_end")


def _carried_grid(
    funding: pl.DataFrame, grid_dates: list[date], max_gap_days: int
) -> pl.DataFrame:
    """Carry each coin's annualized funding forward onto the daily grid (point-in-time)."""
    symbols = sorted(funding["symbol"].unique().to_list())
    grid = pl.DataFrame({"date": grid_dates}, schema={"date": pl.Date})
    cross = grid.join(pl.DataFrame({"symbol": symbols}, schema={"symbol": pl.Utf8}), how="cross")
    cross = cross.with_columns(
        pl.col("date").cast(pl.Datetime("us")).dt.replace_time_zone("UTC").alias("grid_ts")
    ).sort(["symbol", "grid_ts"])
    events = funding.with_columns(
        annualize_expr().alias("annualized")
    ).select("symbol", "ts", "annualized").sort(["symbol", "ts"])
    carried = cross.join_asof(
        events,
        left_on="grid_ts",
        right_on="ts",
        by="symbol",
        strategy="backward",
        tolerance=f"{max_gap_days}d",
        check_sortedness=False,  # both frames are pre-sorted; the by-group check is noisy
    )
    return carried.select("date", "symbol", "annualized").sort(["symbol", "date"])


def annualize_expr() -> pl.Expr:
    """Polars expression annualizing `rate` by `interval_hours` (basis 8760)."""
    return pl.col("rate") * ANNUALIZATION_HOURS / pl.col("interval_hours")


def build_daily_series(
    funding: pl.DataFrame,
    eligible: pl.DataFrame,
    *,
    top_n: int = DEFAULT_TOP_N,
    max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
    winsor_pct: float = DEFAULT_WINSOR_PCT,
    n_quantiles: int = DEFAULT_N_QUANTILES,
) -> list[DispersionDailyRow]:
    """Build the daily cross-sectional funding-dispersion series.

    `funding` columns: symbol, ts (UTC), rate, interval_hours (the per-event raw funding).
    `eligible` columns: week_end (Date), symbol (the point-in-time eligible spot coins per week,
    the count of which is the coverage denominator; not every eligible coin has a perp funding
    series). `top_n` is informational here (the eligibility is already screened upstream).
    """
    if funding.height == 0 or eligible.height == 0:
        raise DispersionError("build_daily_series requires non-empty funding and eligibility")
    funding = funding.cast(_FUNDING_SCHEMA)  # type: ignore[arg-type]
    if funding.filter(pl.col("interval_hours") <= 0).height > 0:
        raise DispersionError("funding has a non-positive interval")
    first = funding["ts"].min()
    last = funding["ts"].max()
    if not isinstance(first, datetime) or not isinstance(last, datetime):
        raise DispersionError("funding timestamps are not datetimes")
    grid_dates = [
        d.date() for d in pl.datetime_range(
            first.date(), last.date(), interval="1d", eager=True, time_zone="UTC"
        ).to_list()
    ]
    carried = _carried_grid(funding, grid_dates, max_gap_days)
    carried = carried.with_columns(
        pl.col("annualized").shift(-1).over("symbol").alias("annualized_next"),
        _week_end_expr(),
    )
    eligible_pairs = eligible.select("week_end", "symbol").unique()
    eligible_set = {(w, s) for w, s in zip(eligible_pairs["week_end"], eligible_pairs["symbol"],
                                           strict=True)}
    n_eligible_by_week = {
        w: int(n) for w, n in zip(
            eligible_pairs.group_by("week_end").len().sort("week_end")["week_end"],
            eligible_pairs.group_by("week_end").len().sort("week_end")["len"],
            strict=True,
        )
    }
    rows: list[DispersionDailyRow] = []
    for day, group in _by_date(carried):
        week_end = _sunday_week_end(day)
        n_eligible = n_eligible_by_week.get(week_end, 0)
        if n_eligible == 0:
            continue
        funded = [
            (a, nxt)
            for sym, a, nxt in group
            if a is not None and (week_end, sym) in eligible_set
        ]
        if len(funded) < MIN_CROSS_SECTION:
            continue
        values = [a for a, _ in funded]
        s = sorted(values)
        iqr = _quantile(s, 0.75) - _quantile(s, 0.25)
        std = statistics.stdev(values)
        rows.append(
            DispersionDailyRow(
                date=day,
                n_eligible=n_eligible,
                n_funded=len(funded),
                iqr=iqr,
                std=std,
                winsor_std=_winsorized_std(values, winsor_pct),
                sort_premium=_sort_premium(funded, n_quantiles),
            )
        )
    if len(rows) < 60:
        raise DispersionError("dispersion series has too few measured days")
    rows.sort(key=lambda r: r.date)
    return rows


def _sunday_week_end(day: date) -> date:
    monday = day.toordinal() - day.weekday()
    return date.fromordinal(monday + 6)


def _by_date(carried: pl.DataFrame) -> list[_DayGroup]:
    """Group the carried grid by date into (date, [(symbol, annualized, annualized_next)])."""
    out: list[_DayGroup] = []
    current: date | None = None
    bucket: list[tuple[str, float | None, float | None]] = []
    for row in carried.sort(["date", "symbol"]).iter_rows(named=True):
        d = row["date"]
        if not isinstance(d, date):
            raise DispersionError(f"expected date, got {d!r}")
        if d != current:
            if current is not None:
                out.append((current, bucket))
            current = d
            bucket = []
        bucket.append((str(row["symbol"]), row["annualized"], row["annualized_next"]))
    if current is not None:
        out.append((current, bucket))
    return out
