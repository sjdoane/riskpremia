"""The 28 CTREND daily features, validated against independent Python computations.

Each indicator is checked against a hand/independent implementation on a fixed varied
series (the rigorous formula validation the design review required), plus the scaling
direction, the null-until-window behaviour, and point-in-time invariance (a future bar
never changes an earlier indicator).
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import polars as pl
import pytest

from riskpremia.ctrend.features import (
    SIGNAL_COLUMNS,
    compute_daily_features,
    compute_weekly_features,
)
from riskpremia.ctrend.universe import build_daily_panel
from riskpremia.data.records import InstrumentId, SpotKlineRecord

# A fixed, varied, deterministic 40-bar series (no RNG): a wave plus a drift so gains and
# losses both occur and the windows are non-degenerate.
_N = 40
_CLOSES = [100.0 + 8.0 * math.sin(i / 2.0) + 0.7 * i for i in range(_N)]
_HIGHS = [c * 1.012 for c in _CLOSES]
_LOWS = [c * 0.987 for c in _CLOSES]
_VOLS = [1_000_000.0 + 50_000.0 * math.cos(i / 3.0) + 3_000.0 * i for i in range(_N)]
_START = date(2020, 1, 6)  # a Monday


def _panel(closes: list[float], highs: list[float], lows: list[float], vols: list[float]):  # type: ignore[no-untyped-def]
    recs = [
        SpotKlineRecord(
            instrument=InstrumentId.of("binance_vision", "XUSDT"),
            period_end_ts=datetime(*(_START + timedelta(days=i)).timetuple()[:3], tzinfo=UTC),
            close=Decimal(str(closes[i])),
            high=Decimal(str(highs[i])),
            low=Decimal(str(lows[i])),
            quote_volume=Decimal(str(vols[i])),
        )
        for i in range(len(closes))
    ]
    return build_daily_panel(recs)


def _feat_at(features: pl.DataFrame, col: str, idx: int) -> float | None:
    sub = features.sort("date")
    return sub[col][idx]


def _ewm(values: list[float | None], alpha: float, min_samples: int) -> list[float | None]:
    """adjust=False recursive EWM over a series with leading None(s), ignore_nulls, with
    min_samples counted on the non-null observations (the polars `ewm_mean` convention)."""
    out: list[float | None] = []
    ema: float | None = None
    seen = 0
    for v in values:
        if v is None:
            out.append(None)
            continue
        ema = v if ema is None else alpha * v + (1 - alpha) * ema
        seen += 1
        out.append(ema if seen >= min_samples else None)
    return out


def test_sma_scaling_and_null_until_window() -> None:
    feats = compute_daily_features(_panel(_CLOSES, _HIGHS, _LOWS, _VOLS))
    # sma_3d at index 5 = mean(close[3:6]) / close[5]
    exp = (sum(_CLOSES[3:6]) / 3.0) / _CLOSES[5]
    assert _feat_at(feats, "sma_3d", 5) == pytest.approx(exp, rel=1e-12)
    # volsma_5d at index 10 = mean(vol[6:11]) / vol[10]
    exp_v = (sum(_VOLS[6:11]) / 5.0) / _VOLS[10]
    assert _feat_at(feats, "volsma_5d", 10) == pytest.approx(exp_v, rel=1e-12)
    # null until the window is available; sma_200d never available on 40 bars
    assert _feat_at(feats, "sma_20d", 18) is None  # < 20 obs
    assert _feat_at(feats, "sma_20d", 19) is not None  # exactly 20 obs
    assert feats["sma_200d"].null_count() == _N


def test_rsi_wilder_matches_independent_and_monotone_up_is_100() -> None:
    feats = compute_daily_features(_panel(_CLOSES, _HIGHS, _LOWS, _VOLS))
    # independent Wilder RSI (alpha=1/14, seeded at the first delta, min_samples=14)
    deltas: list[float | None] = [None] + [_CLOSES[i] - _CLOSES[i - 1] for i in range(1, _N)]
    gains = [None if d is None else max(d, 0.0) for d in deltas]
    losses = [None if d is None else max(-d, 0.0) for d in deltas]
    ag = _ewm(gains, 1.0 / 14, 14)  # Wilder smoothing: alpha = 1/period
    al = _ewm(losses, 1.0 / 14, 14)
    for idx in (20, 30, 39):
        if al[idx] == 0.0:
            exp = 100.0
        else:
            exp = 100.0 - 100.0 / (1.0 + ag[idx] / al[idx])  # type: ignore[operator]
        assert _feat_at(feats, "rsi", idx) == pytest.approx(exp, rel=1e-9)
    # a strictly increasing series is all gains -> RSI 100
    up = [10.0 + i for i in range(_N)]
    up_feats = compute_daily_features(
        _panel(up, [c * 1.01 for c in up], [c * 0.99 for c in up], _VOLS)
    )
    assert _feat_at(up_feats, "rsi", 39) == pytest.approx(100.0)


def test_macd_matches_independent_ppo() -> None:
    feats = compute_daily_features(_panel(_CLOSES, _HIGHS, _LOWS, _VOLS))
    ema12 = _ewm(list(_CLOSES), 2.0 / 13, 12)  # standard EMA: alpha = 2/(span+1)
    ema26 = _ewm(list(_CLOSES), 2.0 / 27, 26)
    idx = 39
    exp = (ema12[idx] - ema26[idx]) / ema12[idx]  # type: ignore[operator]
    assert _feat_at(feats, "macd", idx) == pytest.approx(exp, rel=1e-9)
    assert _feat_at(feats, "macd", 24) is None  # ema26 not yet available


def test_bollinger_exact() -> None:
    feats = compute_daily_features(_panel(_CLOSES, _HIGHS, _LOWS, _VOLS))
    idx = 30
    window = _CLOSES[idx - 19:idx + 1]
    sma20 = sum(window) / 20.0
    var = sum((x - sma20) ** 2 for x in window) / 20.0  # population (ddof=0)
    std20 = math.sqrt(var)
    assert _feat_at(feats, "boll_mid", idx) == pytest.approx(sma20 / _CLOSES[idx], rel=1e-12)
    assert _feat_at(feats, "boll_high", idx) == pytest.approx(
        (sma20 + 2 * std20) / _CLOSES[idx], rel=1e-12
    )
    assert _feat_at(feats, "boll_width", idx) == pytest.approx(4 * std20 / sma20, rel=1e-12)


def test_stochk_and_cci_and_chaikin_exact() -> None:
    feats = compute_daily_features(_panel(_CLOSES, _HIGHS, _LOWS, _VOLS))
    idx = 30
    # stochK (14-day)
    lo = min(_LOWS[idx - 13:idx + 1])
    hi = max(_HIGHS[idx - 13:idx + 1])
    exp_k = 100.0 * (_CLOSES[idx] - lo) / (hi - lo)
    assert _feat_at(feats, "stochK", idx) == pytest.approx(exp_k, rel=1e-9)
    # CCI (20-day typical-price MAD)
    tp = [(_HIGHS[i] + _LOWS[i] + _CLOSES[i]) / 3.0 for i in range(_N)]
    win = tp[idx - 19:idx + 1]
    sma_tp = sum(win) / 20.0
    mad = sum(abs(x - sma_tp) for x in win) / 20.0
    exp_cci = (tp[idx] - sma_tp) / (0.015 * mad)
    assert _feat_at(feats, "cci", idx) == pytest.approx(exp_cci, rel=1e-9)
    # Chaikin money flow (20-day, dollar-volume convention)
    mfv = [
        (((_CLOSES[i] - _LOWS[i]) - (_HIGHS[i] - _CLOSES[i])) / (_HIGHS[i] - _LOWS[i])) * _VOLS[i]
        for i in range(_N)
    ]
    exp_cmf = sum(mfv[idx - 19:idx + 1]) / sum(_VOLS[idx - 19:idx + 1])
    assert _feat_at(feats, "chaikin", idx) == pytest.approx(exp_cmf, rel=1e-9)


def test_features_are_point_in_time() -> None:
    base = compute_daily_features(_panel(_CLOSES, _HIGHS, _LOWS, _VOLS)).sort("date")
    extended = compute_daily_features(
        _panel(_CLOSES + [200.0], _HIGHS + [202.0], _LOWS + [198.0], _VOLS + [9_000_000.0])
    ).sort("date")
    # every earlier row's signals are unchanged by appending a later (very different) bar
    for col in SIGNAL_COLUMNS:
        b = base[col].to_list()
        e = extended[col].to_list()[: len(b)]
        for x, y in zip(b, e, strict=True):
            if x is None:
                assert y is None
            else:
                assert y == pytest.approx(x, rel=1e-12, abs=1e-15)


def test_weekly_sampling_takes_the_last_daily_bar_of_the_week() -> None:
    feats_daily = compute_daily_features(_panel(_CLOSES, _HIGHS, _LOWS, _VOLS)).sort("date")
    weekly = compute_weekly_features(_panel(_CLOSES, _HIGHS, _LOWS, _VOLS))
    assert set(weekly.columns) == {"week_end", "symbol", *SIGNAL_COLUMNS}
    # the first full ISO week is Mon 2020-01-06 .. Sun 2020-01-12 (indices 0..6); the weekly
    # sample is the Sunday (index 6) daily value
    wk = weekly.filter(pl.col("week_end") == date(2020, 1, 12))
    assert wk.height == 1
    assert wk["sma_3d"].item() == pytest.approx(feats_daily["sma_3d"][6], rel=1e-12)
