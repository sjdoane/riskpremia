"""Unit tests for the funding-dispersion aggregation (Study 7, synthetic funding)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from riskpremia.dispersion.errors import DispersionError
from riskpremia.dispersion.measure import (
    ANNUALIZATION_HOURS,
    _quantile,
    _sort_premium,
    _winsorized_std,
    annualize,
    build_daily_series,
)

_FUNDING_SCHEMA = {
    "symbol": pl.Utf8,
    "ts": pl.Datetime("us", "UTC"),
    "rate": pl.Float64,
    "interval_hours": pl.Int64,
}


def test_annualize_uses_the_event_interval() -> None:
    # The same per-event rate annualizes higher for a shorter (4h) interval than an 8h one.
    assert annualize(0.0001, 8) == pytest.approx(0.0001 * ANNUALIZATION_HOURS / 8)
    assert annualize(0.0001, 4) == pytest.approx(2.0 * annualize(0.0001, 8))


def test_annualize_rejects_non_positive_interval() -> None:
    with pytest.raises(DispersionError):
        annualize(0.0001, 0)


def test_quantile_linear_interpolation() -> None:
    assert _quantile([0.0, 1.0, 2.0, 3.0], 0.5) == pytest.approx(1.5)
    assert _quantile([0.0, 10.0], 0.25) == pytest.approx(2.5)


def test_winsorized_std_below_raw_on_a_tail() -> None:
    import statistics

    values = [0.0, 0.0, 0.0, 0.0, 100.0]  # one extreme tail
    assert _winsorized_std(values, 0.2) < statistics.stdev(values)


def test_sort_premium_high_minus_low_next_period() -> None:
    # pairs are (today funding, next funding); sorted by today, top bucket minus bottom bucket.
    pairs = [(-3.0, -2.0), (-1.0, -1.0), (0.0, 0.0), (1.0, 1.0), (3.0, 4.0)]
    # quintiles of 5 -> bucket size 1: bottom = first (-2.0 next), top = last (4.0 next).
    assert _sort_premium(pairs, 5) == pytest.approx(4.0 - (-2.0))


def test_sort_premium_none_without_enough_coins() -> None:
    assert _sort_premium([(0.0, 0.0), (1.0, 1.0)], 5) is None


def _funding(rows: list[tuple[str, datetime, float, int]]) -> pl.DataFrame:
    return pl.DataFrame(
        {"symbol": [r[0] for r in rows], "ts": [r[1] for r in rows],
         "rate": [r[2] for r in rows], "interval_hours": [r[3] for r in rows]},
        schema=_FUNDING_SCHEMA,
    )


def _eligible(week_ends: list[date], symbols: list[str]) -> pl.DataFrame:
    pairs = [(w, s) for w in week_ends for s in symbols]
    return pl.DataFrame(
        {"week_end": [p[0] for p in pairs], "symbol": [p[1] for p in pairs]},
        schema={"week_end": pl.Date, "symbol": pl.Utf8},
    )


def _dense_funding(symbols_rates: dict[str, float], start: datetime, days: int) -> pl.DataFrame:
    rows: list[tuple[str, datetime, float, int]] = []
    for sym, rate in symbols_rates.items():
        for d in range(days):
            for h in (0, 8, 16):
                rows.append((sym, start + timedelta(days=d, hours=h), rate, 8))
    return _funding(rows)


def _week_ends(start: date, n: int) -> list[date]:
    # Sunday-ending weeks covering the span.
    out: list[date] = []
    d = start
    while len(out) < n:
        sunday = date.fromordinal(d.toordinal() - d.weekday() + 6)
        if sunday not in out:
            out.append(sunday)
        d += timedelta(days=7)
    return out


def test_build_daily_series_measures_dispersion() -> None:
    # Six coins with spread-out constant funding -> a positive, stable IQR.
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rates = {f"C{i}USDT": (i - 2) * 0.0002 for i in range(6)}
    funding = _dense_funding(rates, start, 120)
    weeks = _week_ends(date(2024, 1, 1), 20)
    eligible = _eligible(weeks, list(rates))
    series = build_daily_series(funding, eligible)
    assert len(series) > 60
    row = series[30]
    assert row.n_funded == 6
    assert row.n_eligible == 6
    assert row.iqr > 0.0
    assert row.std > 0.0


def test_coverage_counts_eligible_without_funding() -> None:
    # One eligible coin has no perp funding series: it is in n_eligible but not n_funded.
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rates = {f"C{i}USDT": (i - 2) * 0.0002 for i in range(6)}
    funding = _dense_funding(rates, start, 120)
    weeks = _week_ends(date(2024, 1, 1), 20)
    eligible = _eligible(weeks, [*rates, "NOPERPUSDT"])  # 7 eligible, only 6 funded
    series = build_daily_series(funding, eligible)
    row = series[30]
    assert row.n_eligible == 7
    assert row.n_funded == 6


def test_carry_forward_drops_a_stale_coin() -> None:
    # A coin whose funding stops well before the end is absent (carried beyond the max gap).
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rates = {f"C{i}USDT": (i - 2) * 0.0002 for i in range(6)}
    funding = _dense_funding(rates, start, 120).filter(
        ~((pl.col("symbol") == "C0USDT") & (pl.col("ts") > datetime(2024, 2, 1, tzinfo=UTC)))
    )
    weeks = _week_ends(date(2024, 1, 1), 20)
    eligible = _eligible(weeks, list(rates))
    series = build_daily_series(funding, eligible)
    late = next(r for r in series if r.date >= date(2024, 3, 1))
    assert late.n_funded == 5  # C0 dropped after its funding went stale


def test_constant_cross_section_has_zero_dispersion() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rates = {f"C{i}USDT": 0.0001 for i in range(6)}  # all identical
    funding = _dense_funding(rates, start, 120)
    weeks = _week_ends(date(2024, 1, 1), 20)
    eligible = _eligible(weeks, list(rates))
    series = build_daily_series(funding, eligible)
    assert series[30].iqr == pytest.approx(0.0, abs=1e-12)
