"""The VRP figure rendering (ADR 0004 PR5b). Skipped when matplotlib (the optional
`figures` extra) is absent, so CI (which installs only `.[dev]`) does not need it; the
figures render PURELY from a built artifact, never recomputing the bootstrap."""

from __future__ import annotations

import importlib.util
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from riskpremia.data.records import DvolRecord, SpotPriceRecord
from riskpremia.vrp.artifact import DatasetFingerprint, build_artifact
from riskpremia.vrp.measurement import build_vrp_frame, vrp_headline

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("matplotlib") is None,
    reason="matplotlib (the figures extra) is not installed",
)


def _artifact() -> object:
    d0 = datetime(2023, 12, 20, tzinfo=UTC)
    n = 80
    dvol = [DvolRecord("BTC", d0 + timedelta(days=i), *(Decimal("80"),) * 4) for i in range(n)]
    level, closes = 100.0, []
    for i in range(n):
        level *= math.exp(0.005 * (1 + (i % 4)))
        closes.append(level)
    spot = [
        SpotPriceRecord("binance_spot", "BTCUSDT", "USDT", d0 + timedelta(days=i),
                        Decimal(str(closes[i])))
        for i in range(n)
    ]
    frame = build_vrp_frame(dvol, spot, window_days=5)
    headline = vrp_headline(frame, window_days=5, n_boot=400)
    fp = DatasetFingerprint("a" * 64, "b" * 64, n, n, "x.csv", "y.csv")
    return build_artifact(frame, headline, currency="BTC", window_days=5, seed=1, n_boot=400,
                          fingerprint=fp, n_dvol_days=n, n_spot_days=n)


def test_render_all_writes_nonempty_pngs(tmp_path: Path) -> None:
    from riskpremia.vrp.figures import render_all

    paths = render_all(_artifact(), tmp_path)  # type: ignore[arg-type]
    assert len(paths) == 2
    for p in paths:
        assert p.exists()
        assert p.stat().st_size > 1000  # a real PNG, not an empty stub
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
