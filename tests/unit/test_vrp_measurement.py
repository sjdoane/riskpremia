"""The VRP measurement (ADR 0004 PR5a): the matched-horizon realized-variance
conventions, the forward/trailing no-look-ahead identity, the loud gap guard, and
the non-overlapping strided headline."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import polars as pl
import pytest

from riskpremia.data.records import DvolRecord, SpotPriceRecord
from riskpremia.vrp.errors import VrpError
from riskpremia.vrp.measurement import build_vrp_frame, vrp_headline
from riskpremia.vrp.realized import realized_variance_frame

_ANN = 365.0


def _closes(n: int, log_ret: float) -> pl.DataFrame:
    d0 = date(2023, 1, 1)
    return pl.DataFrame(
        {
            "date": [d0 + timedelta(days=i) for i in range(n)],
            "close": [100.0 * math.exp(log_ret * i) for i in range(n)],
        },
        schema={"date": pl.Date, "close": pl.Float64},
    )


def test_realized_variance_matched_horizon_and_annualization() -> None:
    # A constant daily log return c -> every complete window has RV_ann == 365 * c^2.
    c, window = 0.02, 30
    rv = realized_variance_frame(_closes(80, c), window_days=window)
    trailing = rv["rv_trailing"].to_list()
    forward = rv["rv_forward"].to_list()
    assert trailing[window - 1] is None  # window touches the null first-return row
    for v in trailing[window:]:
        assert v is not None and abs(v - _ANN * c * c) < 1e-12
    # forward[t] re-anchors trailing[t+window] (days t+1..t+W), valid through n-1-W.
    for t in range(80 - window):
        assert forward[t] is not None and abs(forward[t] - _ANN * c * c) < 1e-12


def test_realized_forward_trailing_reanchor_identity() -> None:
    # forward[t] must equal trailing[t+window] exactly (the same sum, re-anchored),
    # so the forward leg uses days strictly after t and shares no day with trailing[t].
    rv = realized_variance_frame(_closes(50, 0.013), window_days=7)
    trailing = rv["rv_trailing"].to_list()
    forward = rv["rv_forward"].to_list()
    for t in range(50 - 7):
        if forward[t] is not None:
            assert trailing[t + 7] is not None
            assert abs(forward[t] - trailing[t + 7]) < 1e-15


def test_realized_gap_raises_loudly() -> None:
    d0 = date(2023, 1, 1)
    days = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10]  # missing day 5 -> a 2-day step
    frame = pl.DataFrame(
        {"date": [d0 + timedelta(days=i) for i in days], "close": [100.0] * len(days)},
        schema={"date": pl.Date, "close": pl.Float64},
    )
    with pytest.raises(VrpError, match="gap-free"):
        realized_variance_frame(frame, window_days=3)


def _dvol_and_spot(
    n: int, dvol_points: float, log_rets: list[float]
) -> tuple[list[DvolRecord], list[SpotPriceRecord]]:
    d0 = datetime(2023, 1, 1, tzinfo=UTC)
    dp = Decimal(str(dvol_points))
    dvol = [DvolRecord("BTC", d0 + timedelta(days=i), dp, dp, dp, dp) for i in range(n)]
    closes, level = [], 100.0
    for i in range(n):
        level *= math.exp(log_rets[i])
        closes.append(level)
    spot = [
        SpotPriceRecord(
            "binance_spot", "BTCUSDT", "USDT", d0 + timedelta(days=i), Decimal(str(closes[i]))
        )
        for i in range(n)
    ]
    return dvol, spot


def test_build_vrp_frame_exact_decomposition() -> None:
    # Constant implied vol 80 (IV^2 = 0.64) and constant realized vol -> VRP exact.
    window, n, c = 5, 60, 0.01
    dvol, spot = _dvol_and_spot(n, 80.0, [c] * n)
    frame = build_vrp_frame(dvol, spot, window_days=window)
    iv2, rv = 0.64, _ANN * c * c
    assert "vrp_forward" in frame.columns and "vrp_trailing" in frame.columns
    fwd = [v for v in frame["vrp_forward"].to_list() if v is not None]
    assert fwd and all(abs(v - (iv2 - rv)) < 1e-9 for v in fwd)


def test_vrp_headline_positive_premium_and_ci() -> None:
    window, n = 5, 80
    # Mildly varying returns so the VRP series is non-degenerate but stays positive.
    rets = [0.005 * (1 + (i % 4)) for i in range(n)]
    dvol, spot = _dvol_and_spot(n, 80.0, rets)
    frame = build_vrp_frame(dvol, spot, window_days=window)
    h = vrp_headline(frame, window_days=window, n_boot=400)
    assert h.frac_positive == 1.0  # IV^2=0.64 dwarfs the realized variance here
    assert h.mean_phase_min > 0 and h.mean_phase_median > 0
    assert h.ci_low <= h.mean_phase_median <= h.ci_high
    assert h.effective_t >= 2 and h.n_strided >= 2


def test_vrp_headline_needs_enough_observations() -> None:
    dvol, spot = _dvol_and_spot(20, 80.0, [0.01] * 20)
    frame = build_vrp_frame(dvol, spot, window_days=5)
    with pytest.raises(VrpError, match="non-null forward-VRP"):
        vrp_headline(frame, window_days=30)  # far too few obs for a 30-day stride


def test_vrp_regime_split_on_etf_launch() -> None:
    # Dates spanning 2024-01-11: rows before are pre_etf, on/after are post_etf.
    d0 = datetime(2023, 12, 20, tzinfo=UTC)
    n = 60
    dp = Decimal("80")
    dvol = [DvolRecord("BTC", d0 + timedelta(days=i), dp, dp, dp, dp) for i in range(n)]
    spot = [
        SpotPriceRecord(
            "binance_spot", "BTCUSDT", "USDT", d0 + timedelta(days=i), Decimal(str(100.0 + i))
        )
        for i in range(n)
    ]
    frame = build_vrp_frame(dvol, spot, window_days=5)
    regimes = dict(zip(frame["date"].to_list(), frame["regime"].to_list(), strict=True))
    assert regimes[date(2024, 1, 10)] == "pre_etf"
    assert regimes[date(2024, 1, 11)] == "post_etf"  # launch day is post (left-closed)
