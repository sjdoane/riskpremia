"""Cross-venue funding alignment (ADR 0002, design review finding 5).

The premium and its decay are measured on the long Binance Vision history, but
the kill gate runs on OKX-realized funding (what a US trader actually receives).
This module measures the venue basis directly: the Binance-vs-OKX funding delta
on the matched settlement grid over the overlap window, so the basis is a measured
number rather than a footnote. OKX retains only about three months of public
funding history, so the delta is measured on the recent overlap and applied as an
adjustment to the longer Binance-based estimate, not computed across 2024-2026.

GOTCHA (verified live, the reason a naive timestamp join loses about half the
events): Binance Vision `calc_time` carries a few MILLISECONDS of jitter around
the settlement instant (e.g. 00:00:00.003), while OKX `fundingTime` is the clean
boundary (00:00:00.000). So the two venues must be aligned on the funding GRID
(each timestamp rounded to its funding-interval boundary), not on the raw
millisecond, before the inner join.
"""

from __future__ import annotations

import polars as pl

from riskpremia.data.errors import VenueFetchError


def binance_okx_funding_delta(
    binance: pl.DataFrame, okx: pl.DataFrame, *, interval_hours: int = 8
) -> pl.DataFrame:
    """Inner-join two normalized funding frames on the settlement grid; return the
    matched rates and their delta (binance minus okx).

    Both inputs are normalized funding frames (they carry `canonical`, `dt`,
    `funding_rate`, all on the same `pl.Datetime("us", "UTC")` event clock).
    `interval_hours` is the shared funding interval (8 for Binance/OKX): each
    `dt` is rounded to that grid so the millisecond jitter in Binance's
    `calc_time` does not break the match. The inner join then keeps only funding
    events present on BOTH venues (the overlap).

    Returns columns `canonical, dt, funding_rate_binance, funding_rate_okx,
    funding_delta`, sorted by `(canonical, dt)` with `dt` on the clean grid. A
    positive `funding_delta` means Binance funding exceeded OKX funding at that
    event (the US-tradeable venue paid less carry than the long-history data
    venue).

    Raises:
      VenueFetchError: when `interval_hours` is not a positive integer.
    """
    if interval_hours < 1:
        raise VenueFetchError(f"interval_hours must be >= 1; got {interval_hours}")
    grid = f"{interval_hours}h"

    def _leg(frame: pl.DataFrame, rate_col: str) -> pl.DataFrame:
        snapped = (
            frame.with_columns(pl.col("dt").dt.round(grid).alias("dt"))
            .select("canonical", "dt", pl.col("funding_rate").alias(rate_col))
            .unique(subset=["canonical", "dt"], keep="first", maintain_order=True)
        )
        # On a clean interval grid, snapping only removes the ms jitter and the
        # height is unchanged. A drop means two real events collapsed to one grid
        # point: the series is NOT on a clean grid (e.g. irregular early history),
        # which this overlap measurement is not valid on. Fail loudly.
        if snapped.height < frame.height:
            raise VenueFetchError(
                f"grid-snap to {grid} collapsed {frame.height - snapped.height} events; "
                f"the funding series is not on a clean {grid} grid (irregular history?)"
            )
        return snapped

    binance_leg = _leg(binance, "funding_rate_binance")
    okx_leg = _leg(okx, "funding_rate_okx")
    joined = binance_leg.join(okx_leg, on=["canonical", "dt"], how="inner")
    return joined.with_columns(
        (pl.col("funding_rate_binance") - pl.col("funding_rate_okx")).alias("funding_delta")
    ).sort(["canonical", "dt"])
