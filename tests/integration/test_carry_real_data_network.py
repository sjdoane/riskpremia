"""The static-notional price_pnl bound on the REAL BTCUSDT post-ETF frame
(network-marked, skipped by default; run with `-m network`).

ADR 0003 finding 4 + amendment A3: v1's `price_pnl` is a static-notional
basis-convergence APPROXIMATION with a signed (short-gamma) bias, so it is not
enough to know it is small in magnitude; the SIGNED mean must be small relative to
the funding it would otherwise pad. This builds the real held-out post-ETF frame
through the actual data layer, runs the vectorised batch, and asserts the proxy is
not contaminating the carry. The printed lines are the numbers the PR4a write-up
quotes (run with `-m network -s`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from riskpremia.data.clock import (
    build_observation_frame,
    make_label_horizons,
    marks_frame,
    normalize_funding_frame,
    spot_frame,
)
from riskpremia.data.sources.binance_vision import BinanceVisionSource
from riskpremia.execution.carry import (
    BATCH_SCALAR_ATOL,
    PRICE_PNL_CONTAMINATION_LIMIT,
    price_pnl_contamination,
    simulate_batch,
    simulate_trade,
)
from riskpremia.execution.cost import KRAKEN

pytestmark = pytest.mark.network


def _post_etf_frame(tmp_path: Path) -> pl.DataFrame:
    src = BinanceVisionSource(tmp_path)
    start = datetime(2024, 6, 1, tzinfo=UTC)
    end = datetime(2024, 9, 1, tzinfo=UTC)
    funding = normalize_funding_frame(src.fetch_funding("BTCUSDT", start, end))
    warm = start - timedelta(days=1)
    marks = marks_frame(src.fetch_marks("BTCUSDT", "8h", warm, end))
    spot = spot_frame(src.fetch_spot("BTCUSDT", "USDT", "8h", warm, end))
    return build_observation_frame(funding, marks, spot, mark_tolerance="8h", spot_tolerance="8h")


@pytest.mark.parametrize("horizon", [1, 3, 21])
def test_price_pnl_does_not_pad_the_carry(tmp_path: Path, horizon: int) -> None:
    obs = _post_etf_frame(tmp_path)
    batch = simulate_batch(obs, horizon_events=horizon, cost_model=KRAKEN)
    diag = price_pnl_contamination(batch)

    print(  # noqa: T201 (the PR4a real-data exhibit)
        f"\n[BTCUSDT 2024-06..09 post-ETF, H={horizon}] n={batch.height} "
        f"median_funding={diag['median_funding']:.6e} mean_funding={diag['mean_funding']:.6e} "
        f"median|price_pnl|={diag['median_abs_price_pnl']:.6e} "
        f"mean_price_pnl={diag['mean_price_pnl']:.6e} "
        f"p95|price_pnl|={diag['p95_abs_price_pnl']:.6e} ratio={diag['contamination_ratio']:.3f}"
    )

    # Sanity: post-ETF BTC funding is overwhelmingly positive (longs pay), so the
    # short book collects on average.
    assert diag["mean_funding"] > 0.0
    # The contamination guard (ADR A3): the SIGNED mean price_pnl must be only a
    # trivial fraction of the funding it would otherwise pad, else the static-
    # notional proxy is contaminating the kill number and v1 must be flagged.
    assert diag["contaminated"] == 0.0, (
        f"mean(price_pnl)={diag['mean_price_pnl']:.3e} is a non-trivial fraction of "
        f"mean(funding)={diag['mean_funding']:.3e} (ratio {diag['contamination_ratio']:.3f} "
        f">= {PRICE_PNL_CONTAMINATION_LIMIT}); the static-notional proxy is padding the carry"
    )
    # The CPCV label and the batch describe the same trimmed frame length.
    observations, horizons = make_label_horizons(obs, horizon_events=horizon)
    assert batch.height == observations.height == horizons.len()

    # Batch-vs-scalar parity holds on the REAL long frame (not only the synthetic
    # unit fixtures), at the documented tolerance: spot-check every ~40th entry.
    for i in range(0, batch.height, 40):
        scalar = simulate_trade(obs, i, horizon_events=horizon, cost_model=KRAKEN)
        row = batch.row(i, named=True)
        assert abs(row["funding_collected"] - scalar.funding_collected) < BATCH_SCALAR_ATOL
        assert abs(row["net_pretax"] - scalar.net_pretax) < BATCH_SCALAR_ATOL
