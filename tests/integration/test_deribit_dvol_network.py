"""The crypto VRP measurement end-to-end against LIVE data (network-marked, skipped
by default; run with `-m network`). The reproducibility proof for Layer i: fetch the
real Deribit DVOL index + the real Binance Vision daily spot closes, build the VRP
frame, and report the first measured variance-risk-premium number. The printed lines
are what the PR5a write-up quotes (run with `-m network -s`)."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

import pytest

from riskpremia.data.sources.binance_vision import BinanceVisionSource
from riskpremia.data.sources.deribit_dvol import DeribitDVOLSource
from riskpremia.vrp.measurement import build_vrp_frame, vrp_headline

pytestmark = pytest.mark.network

# DVOL history starts 2021-04-01; use a multi-year window. The spot leg is warmed up
# 40 days before (trailing RV) and extended 40 days after (forward RV).
_DVOL_START = datetime(2022, 1, 1, tzinfo=UTC)
_DVOL_END = datetime(2025, 6, 1, tzinfo=UTC)
_SPOT_START = datetime(2021, 11, 20, tzinfo=UTC)
_SPOT_END = datetime(2025, 7, 15, tzinfo=UTC)


def test_dvol_reachable_and_daily() -> None:
    recs = DeribitDVOLSource().fetch_dvol("BTC", _DVOL_START, datetime(2022, 1, 15, tzinfo=UTC))
    assert len(recs) >= 10  # ~daily over two weeks
    assert all(10.0 < float(r.close) < 250.0 for r in recs)  # BTC DVOL plausibility band


def test_measured_vrp_is_positive_on_real_data(tmp_path: Path) -> None:
    dvol = DeribitDVOLSource().fetch_dvol("BTC", _DVOL_START, _DVOL_END)
    spot = BinanceVisionSource(tmp_path).fetch_spot("BTCUSDT", "USDT", "1d", _SPOT_START, _SPOT_END)
    frame = build_vrp_frame(dvol, spot, window_days=30)
    h = vrp_headline(frame, window_days=30)

    print(  # noqa: T201 (the PR5a real-data exhibit)
        f"\n[BTC VRP 2022-01..2025-06, 30d] n_fwd={h.n_forward_obs} n_strided={h.n_strided} "
        f"mean_VRP_var={h.mean_phase_median:.5f} "
        f"band=[{h.mean_phase_min:.5f},{h.mean_phase_max:.5f}] "
        f"95CI=[{h.ci_low:.5f},{h.ci_high:.5f}] eff_T={h.effective_t:.0f} "
        f"pw={h.pw_block_length:.2f} frac_pos={h.frac_positive:.2f} "
        f"vol_spread={h.mean_vol_spread_forward:.4f} "
        f"pre_etf={h.mean_vrp_pre_etf:.5f} post_etf={h.mean_vrp_post_etf:.5f}"
    )

    assert len(dvol) > 1000  # multi-year daily DVOL
    assert math.isfinite(h.mean_phase_median)
    # The variance risk premium is positive on average (implied variance exceeds
    # realized): the documented BTC VRP. The CI lower bound clearing zero is the
    # measurement headline (the premium is statistically real, overlap-honest T).
    assert h.mean_phase_median > 0.0
    assert h.frac_positive > 0.5
    assert h.ci_low > 0.0
