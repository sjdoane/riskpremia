"""Binance Vision end-to-end against the LIVE S3 dumps (network-marked, skipped
by default; run with `-m network`). This is the reproducibility proof on real
data: it lists S3, downloads + checksum-verifies the immutable funding zip, and
builds a funding + mark + spot + basis observation frame.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from riskpremia.data.clock import (
    build_observation_frame,
    make_label_horizons,
    marks_frame,
    normalize_funding_frame,
    spot_frame,
)
from riskpremia.data.sources.binance_vision import BinanceVisionSource

pytestmark = pytest.mark.network


def test_funding_2020_01_matches_committed_fixture(tmp_path: Path) -> None:
    src = BinanceVisionSource(tmp_path)
    recs = src.fetch_funding(
        "BTCUSDT", datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 2, 1, tzinfo=UTC)
    )
    assert len(recs) == 93  # same count as the committed offline fixture
    assert recs[0].funding_interval_hours == 8


def test_funding_mark_spot_basis_post_etf(tmp_path: Path) -> None:
    src = BinanceVisionSource(tmp_path)
    start = datetime(2024, 6, 1, tzinfo=UTC)
    end = datetime(2024, 7, 1, tzinfo=UTC)
    funding = normalize_funding_frame(src.fetch_funding("BTCUSDT", start, end))
    # Warm-up the price legs one day before the funding window so the first
    # funding event has a mark/spot at-or-before it (the backward as-of join is
    # PIT-safe and returns null when no prior price exists, the realistic study
    # pattern is to fetch a price warm-up rather than leak a future price).
    warm = start - timedelta(days=1)
    marks = marks_frame(src.fetch_marks("BTCUSDT", "8h", warm, end))
    spot = spot_frame(src.fetch_spot("BTCUSDT", "USDT", "8h", warm, end))
    obs = build_observation_frame(
        funding, marks, spot, mark_tolerance="8h", spot_tolerance="8h"
    )
    assert obs.height > 80  # ~3 funding events/day for a month
    # the perp mark and spot joined, and the basis is finite and small
    assert obs["perp_close"].null_count() == 0
    assert obs["spot_close"].null_count() == 0
    assert obs["basis"].abs().max() < 0.05  # perp-spot basis is single-digit percent
    # the whole thing feeds CPCV
    observations, horizons = make_label_horizons(obs, horizon_events=3)
    assert horizons.len() == observations.height
