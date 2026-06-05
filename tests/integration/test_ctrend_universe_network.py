"""The CTREND universe layer end-to-end against the LIVE Binance Vision S3 bucket
(network-marked, skipped by default; run with `-m network`). The real-data proof for PR1:
the enumeration is delisting-complete, the exclusion filter works on the live universe, and
a real multi-symbol daily fetch resamples to a weekly panel with USD dollar volume.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from riskpremia.ctrend.universe import (
    build_daily_panel,
    build_weekly_panel,
    classify_exclusion,
    listed_bases_of,
    tradeable_universe,
)
from riskpremia.data.sources.binance_vision import BinanceVisionSource

pytestmark = pytest.mark.network


def test_enumeration_is_delisting_complete(tmp_path: Path) -> None:
    src = BinanceVisionSource(tmp_path)
    symbols = src.list_spot_symbols("USDT")
    assert len(symbols) > 500  # the full USDT spot universe (probed ~664 in 2026-06)
    # famously-delisted coins are RETAINED in the bucket (the survivorship-safe source)
    assert "LUNAUSDT" in symbols
    assert "FTTUSDT" in symbols
    # every returned symbol ends in the quote
    assert all(s.endswith("USDT") for s in symbols)


def test_exclusion_filter_on_the_live_universe(tmp_path: Path) -> None:
    src = BinanceVisionSource(tmp_path)
    symbols = src.list_spot_symbols("USDT")
    bases = listed_bases_of(symbols)
    kept = set(tradeable_universe(symbols))
    # a real, liquid coin is kept
    assert "BTCUSDT" in kept and "ETHUSDT" in kept
    # a real stablecoin pair present in the live bucket is excluded
    assert "USDCUSDT" in symbols
    assert classify_exclusion("USDCUSDT", bases) == "stablecoin_or_fiat"
    assert "USDCUSDT" not in kept
    # any leveraged token in the (delisting-complete) bucket is excluded
    leveraged = [s for s in symbols if classify_exclusion(s, bases) == "leveraged_token"]
    assert leveraged, "expected some delisted Binance leveraged tokens retained in the bucket"
    assert all(s not in kept for s in leveraged)
    # any non-standard (non-ASCII) novelty symbol present is excluded (the live bucket has one)
    non_standard = [s for s in symbols if classify_exclusion(s, bases) == "non_standard_ticker"]
    assert all(s not in kept for s in non_standard)
    assert len(kept) < len(symbols)  # the filter dropped something


def test_fetch_btc_daily_klines_resample_to_weekly(tmp_path: Path) -> None:
    src = BinanceVisionSource(tmp_path)
    start = datetime(2024, 6, 1, tzinfo=UTC)
    end = datetime(2024, 8, 1, tzinfo=UTC)
    recs = src.fetch_spot_klines("BTCUSDT", "1d", start, end)
    assert len(recs) >= 55  # ~61 daily bars over two months
    assert all(r.close > 0 for r in recs)
    assert all(r.quote_volume > 0 for r in recs)  # BTC always has USD dollar volume
    weekly = build_weekly_panel(build_daily_panel(recs))
    assert weekly.height >= 7  # ~8-9 weekly bars over two months
    assert (weekly["weekly_dollar_volume"] > 0).all()
    # consecutive interior weeks have a non-null return
    interior = weekly.filter(weekly["weekly_return"].is_not_null())
    assert interior.height >= 5


def test_fetch_a_delisted_coin_has_bounded_history(tmp_path: Path) -> None:
    # SRM (Serum) was liquid through 2022 and genuinely delisted on Binance after the Nov-2022
    # FTX collapse, with NO ticker reuse (unlike LUNA -> Luna 2.0 or FTT, which the bucket shows
    # trading to the present). Its spot-kline dumps exist for the period it traded
    # (delisting-complete) and its month range does NOT extend to the present (a dead coin).
    src = BinanceVisionSource(tmp_path)
    months = src.available_spot_months("SRMUSDT", "1d")
    assert months, "SRMUSDT daily dumps should exist (delisting-complete bucket)"
    assert months[-1] < "2023-06"  # stopped after the Nov-2022 FTX collapse (a genuine delisting)
    recs = src.fetch_spot_klines(
        "SRMUSDT", "1d", datetime(2022, 1, 1, tzinfo=UTC), datetime(2022, 3, 1, tzinfo=UTC)
    )
    assert len(recs) >= 50  # it traded actively in early 2022
    assert all(r.quote_volume > 0 for r in recs)
