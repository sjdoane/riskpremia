"""OKX + the venue delta against LIVE endpoints (network-marked, skipped by
default; run with `-m network`). Verifies the US-reachable kill-gate venue and
the Binance-vs-OKX funding-basis measurement on the recent overlap.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from riskpremia.data.clock import normalize_funding_frame
from riskpremia.data.cross_venue import binance_okx_funding_delta
from riskpremia.data.sources.binance_vision import BinanceVisionSource
from riskpremia.data.sources.okx import OKXSource

pytestmark = pytest.mark.network


def test_okx_fetch_recent_window() -> None:
    src = OKXSource()
    now = datetime.now(UTC)
    start = now - timedelta(days=10)
    end = now - timedelta(days=1)
    recs = src.fetch_funding("BTC-USDT-SWAP", start, end)
    assert len(recs) > 15  # ~3 funding events/day over ~9 days
    assert all(r.funding_interval_hours == 8 and r.realized for r in recs)
    assert all(start <= r.funding_ts < end for r in recs)


def test_okx_retention_is_recent_only() -> None:
    # OKX public funding history pages back about 3 months, then exhausts.
    floor = OKXSource().retention_floor("BTC-USDT-SWAP")
    assert floor is not None
    age_days = (datetime.now(UTC) - floor).days
    assert 45 < age_days < 200  # recent-only: months, not years


def test_binance_okx_funding_delta_live(tmp_path: Path) -> None:
    # A recent month both venues cover (within OKX's ~3-month retention).
    start = datetime(2026, 4, 1, tzinfo=UTC)
    end = datetime(2026, 5, 1, tzinfo=UTC)
    binance = normalize_funding_frame(
        BinanceVisionSource(tmp_path).fetch_funding("BTCUSDT", start, end)
    )
    okx = normalize_funding_frame(OKXSource().fetch_funding("BTC-USDT-SWAP", start, end))
    delta = binance_okx_funding_delta(binance, okx)
    assert delta.height > 80  # after grid-snapping, ~all of a month's 8h events align
    # the venue basis between the data venue and the tradeable venue is small
    median_abs = delta.select(pl.col("funding_delta").abs().median()).item()
    assert median_abs < 0.001  # under 0.1% per 8h
