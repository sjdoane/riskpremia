"""The CTREND CS-C-ENet signal units: the rank transform, the univariate Fama-MacBeth, the
H3 smoothing-window boundary (no look-ahead), the elastic-net selection, the combined
forecast PIT property, the quintile sort, and the gross IC / spread.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
import polars as pl
import pytest

from riskpremia.ctrend.features import SIGNAL_COLUMNS
from riskpremia.ctrend.signal import (
    _combined_forecasts,
    _smooth_coeffs,
    _univariate_fm,
    assign_quintiles,
    ctrend_forecasts,
    quintile_spread,
    rank_to_unit_interval,
    select_enet,
    signal_rank_ic,
)
from riskpremia.ctrend.universe import build_daily_panel, build_weekly_panel, pit_eligible
from riskpremia.data.records import InstrumentId, SpotKlineRecord


def test_rank_to_unit_interval_maps_and_handles_small_n() -> None:
    frame = pl.DataFrame(
        {
            "week_end": [date(2024, 1, 7)] * 4 + [date(2024, 1, 14)],
            "x": [10.0, 20.0, 30.0, 40.0, 99.0],
        }
    )
    out = frame.with_columns(rank_to_unit_interval(pl.col("x"), "week_end").alias("z"))
    z = out.filter(pl.col("week_end") == date(2024, 1, 7)).sort("x")["z"].to_list()
    assert z == pytest.approx([-0.5, -1 / 6, 1 / 6, 0.5])  # (rank-1)/(N-1) - 0.5 for N=4
    # a single-observation week maps to null (no usable cross-section)
    assert out.filter(pl.col("week_end") == date(2024, 1, 14))["z"].item() is None


def test_rank_transform_ties_are_averaged() -> None:
    frame = pl.DataFrame({"week_end": [date(2024, 1, 7)] * 3, "x": [5.0, 5.0, 9.0]})
    z = frame.with_columns(rank_to_unit_interval(pl.col("x"), "week_end").alias("z")).sort("x")["z"]
    # the two tied lowest share the average rank 1.5 -> (1.5-1)/2 - 0.5 = -0.25; top -> +0.5
    assert z.to_list() == pytest.approx([-0.25, -0.25, 0.5])


def _ranked_frame(week: date, z: list[float], fwd: list[float]) -> pl.DataFrame:
    """A ranked frame for one week with 'rsi' carrying z and the other 27 signals null."""
    n = len(z)
    cols: dict[str, object] = {
        "week_end": [week] * n,
        "symbol": [f"C{i}" for i in range(n)],
        "forward_return": fwd,
    }
    for sig in SIGNAL_COLUMNS:
        cols[sig] = z if sig == "rsi" else [None] * n
    return pl.DataFrame(cols)


def test_univariate_fm_recovers_known_slope() -> None:
    z = [-0.5, -0.25, 0.0, 0.25, 0.5]
    fwd = [1.0 + 2.0 * v for v in z]  # forward_return = 1 + 2 z exactly
    fm = _univariate_fm(_ranked_frame(date(2024, 1, 7), z, fwd))
    rsi = fm.filter(pl.col("signal") == "rsi")
    assert rsi["beta"].item() == pytest.approx(2.0, rel=1e-9)
    assert rsi["alpha"].item() == pytest.approx(1.0, rel=1e-9)
    # the all-null signals produce no regression rows
    assert fm.filter(pl.col("signal") == "cci").height == 0


def test_smoothing_excludes_the_current_week() -> None:
    # one signal, beta = 1..10 over 10 weeks; smoothed beta at week t must be the mean of the
    # 3 PRIOR weeks (t-3..t-1), never including week t (the H3 no-look-ahead boundary).
    weeks = [date(2024, 1, 7) + timedelta(weeks=i) for i in range(10)]
    fm = pl.DataFrame(
        {
            "week_end": weeks,
            "signal": ["rsi"] * 10,
            "alpha": [0.0] * 10,
            "beta": [float(i + 1) for i in range(10)],
        }
    )
    smoothed = _smooth_coeffs(fm, window=3).sort("week_end")
    # at index 5 (beta would be 6): mean(beta[2],beta[3],beta[4]) = mean(3,4,5) = 4
    assert smoothed["beta_bar"][5] == pytest.approx(4.0)
    # at index 3: the 3 priors beta[0..2] = mean(1,2,3) = 2 (week 3's own beta excluded)
    assert smoothed["beta_bar"][3] == pytest.approx(2.0)
    # fewer than 3 prior weeks before index 3 -> null
    assert smoothed["beta_bar"][2] is None


def test_select_enet_keeps_the_predictor_drops_noise() -> None:
    n = 200
    t = np.linspace(0.0, 1.0, n)
    x0 = np.sin(2 * np.pi * t)  # the genuine predictor
    x1 = np.cos(3 * np.pi * t)
    x2 = np.sin(5 * np.pi * t)
    x3 = t**2 - t
    x4 = np.cos(7 * np.pi * t)
    x = np.column_stack([x0, x1, x2, x3, x4]).astype(np.float64)
    y = (2.0 * x0 + 0.001 * x1).astype(np.float64)  # y is essentially x0
    selected = select_enet(x, y)
    assert bool(selected[0]) is True  # the predictor is kept (theta > 0)
    assert int(selected.sum()) < x.shape[1]  # not everything is selected (noise dropped)


def _wide_forecasts(n_weeks: int, n_coins: int, *, base: float) -> pl.DataFrame:
    """A wide forecast frame (all 28 rhat columns) for the PIT check, deterministic.

    Each coin has a distinct score s; the forward return and the rhat forecasts both track s
    (with small per-week wobble), so the elastic net reliably selects (a non-empty signal).
    """
    weeks = [date(2024, 1, 7) + timedelta(weeks=w) for w in range(n_weeks)]
    rows: list[dict[str, object]] = []
    for w, week in enumerate(weeks):
        for c in range(n_coins):
            s = c / (n_coins - 1) - 0.5  # coin score in [-0.5, 0.5]
            row: dict[str, object] = {
                "week_end": week,
                "symbol": f"C{c}",
                "forward_return": 0.1 * s + 0.002 * math.sin(w + 1),
            }
            for j, sig in enumerate(SIGNAL_COLUMNS):
                row[f"rhat_{sig}"] = base + 0.05 * s + 0.0005 * math.cos(w + j)
            rows.append(row)
    return pl.DataFrame(rows)


def test_combined_forecasts_is_point_in_time() -> None:
    wide = _wide_forecasts(12, 8, base=0.01)
    base_fc = _combined_forecasts(wide, window=3).sort(["week_end", "symbol"])
    # append a later week with wildly different forecasts + returns
    extra = _wide_forecasts(13, 8, base=0.01).filter(
        pl.col("week_end") == date(2024, 1, 7) + timedelta(weeks=12)
    ).with_columns(pl.col("forward_return") * 50.0)
    extended = _combined_forecasts(pl.concat([wide, extra]), window=3).sort(["week_end", "symbol"])
    earlier = base_fc["week_end"].max()
    a = base_fc.filter(pl.col("week_end") <= earlier)
    b = extended.filter(pl.col("week_end") <= earlier)
    assert a.equals(b)  # earlier forecasts are untouched by the later week


def test_assign_quintiles_top_is_highest_and_deterministic() -> None:
    fc = pl.DataFrame(
        {
            "week_end": [date(2024, 1, 7)] * 10,
            "symbol": [f"C{i}" for i in range(10)],
            "ctrend": [float(i) for i in range(10)],
        }
    )
    q = assign_quintiles(fc, n_quintiles=5).sort("ctrend")
    quints = q["quintile"].to_list()
    assert quints == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]  # 10 coins / 5 = 2 per quintile, ascending
    assert q.filter(pl.col("quintile") == 4)["ctrend"].min() == 8.0  # top quintile = highest


def test_signal_rank_ic_and_spread_on_a_known_signal() -> None:
    # ctrend perfectly orders the forward return each week -> IC = 1, monotone spread
    rows: list[dict[str, object]] = []
    for w in range(6):
        for c in range(10):
            rows.append(
                {
                    "week_end": date(2024, 1, 7) + timedelta(weeks=w),
                    "symbol": f"C{c}",
                    "ctrend": float(c),
                    "forward_return": float(c) * 0.01,
                }
            )
    fc = assign_quintiles(pl.DataFrame(rows), n_quintiles=5)
    ic = signal_rank_ic(fc)
    assert ic["mean_ic"] == pytest.approx(1.0)
    assert ic["frac_positive"] == 1.0
    spread = quintile_spread(fc)
    assert spread == sorted(spread)  # monotonically increasing
    assert spread[-1] > spread[0]


def _coin_panel(symbol: str, closes: list[float], vols: list[float], start: date):  # type: ignore[no-untyped-def]
    out = []
    for i, c in enumerate(closes):
        d = start + timedelta(days=i)
        out.append(
            SpotKlineRecord(
                instrument=InstrumentId.of("binance_vision", symbol),
                period_end_ts=datetime(d.year, d.month, d.day, tzinfo=UTC),
                close=Decimal(str(c)),
                high=Decimal(str(c * 1.01)),
                low=Decimal(str(c * 0.99)),
                quote_volume=Decimal(str(vols[i])),
            )
        )
    return out


def test_ctrend_forecasts_end_to_end_structure_and_pit() -> None:
    # 30 coins, 360 daily bars (enough for sma_200d + a short fit window + a pool the 28-feature
    # elastic net can select on), deterministic, with a DISTINCT per-coin geometric drift so the
    # cross-section carries a strong momentum signal the trend features capture.
    n_coins = 30
    start = date(2021, 1, 4)  # a Monday
    recs = []
    for c in range(n_coins):
        drift = -0.004 + (0.008 / (n_coins - 1)) * c  # distinct daily drift (-0.4% .. +0.4%)
        closes = [100.0 * (1.0 + drift) ** i * (1.0 + 0.01 * math.sin(i / 5.0)) for i in range(360)]
        # distinct per-coin volume SHAPE (a scale per coin cancels in the SMA ratio, so vary the
        # shape) so the volume signals are cross-sectionally non-degenerate
        vols = [
            1_000_000.0 * (1.0 + 0.4 * math.sin((i + c * 4) / 11.0)) + 5_000.0 * i
            for i in range(360)
        ]
        recs.extend(_coin_panel(f"C{c}USDT", closes, vols, start))
    daily = build_daily_panel(recs)
    weekly = pit_eligible(build_weekly_panel(daily), top_n=n_coins, min_history_weeks=8)
    fc = ctrend_forecasts(daily, weekly, fit_window=4, n_quintiles=5)
    assert set(fc.columns) >= {"week_end", "symbol", "ctrend", "quintile", "forward_return"}
    assert fc.height > 0
    assert fc["ctrend"].null_count() == 0
    # PIT: dropping the last 3 weeks of daily data must not change the earlier forecasts
    cutoff = daily["date"].max() - timedelta(days=21)
    fc_short = ctrend_forecasts(
        daily.filter(pl.col("date") <= cutoff),
        pit_eligible(
            build_weekly_panel(daily.filter(pl.col("date") <= cutoff)),
            top_n=n_coins,
            min_history_weeks=8,
        ),
        fit_window=4,
        n_quintiles=5,
    )
    common = fc_short["week_end"].max()
    a = fc.filter(pl.col("week_end") < common).select("week_end", "symbol", "ctrend").sort(
        ["week_end", "symbol"]
    )
    b = fc_short.filter(pl.col("week_end") < common).select("week_end", "symbol", "ctrend").sort(
        ["week_end", "symbol"]
    )
    assert a.height > 0
    for x, y in zip(a["ctrend"].to_list(), b["ctrend"].to_list(), strict=True):
        assert y == pytest.approx(x, rel=1e-9, abs=1e-12)
