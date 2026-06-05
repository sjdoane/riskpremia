"""CTREND PR3 gate units: turnover cost and missing-return handling."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from riskpremia.ctrend.gate import _build_portfolio_series
from riskpremia.execution.cost import VenueCostModel


def _model(*, spot_taker_bps: float = 0.0, spot_maker_bps: float = 0.0) -> VenueCostModel:
    return VenueCostModel(
        name="test_spot",
        tradeable=True,
        spot_taker_bps=spot_taker_bps,
        spot_maker_bps=spot_maker_bps,
        perp_taker_bps=0.0,
        perp_maker_bps=0.0,
        spot_half_spread_bps=0.0,
        perp_half_spread_bps=0.0,
        source="unit test synthetic cost model",
    )


def test_long_only_turnover_charges_entry_and_rebalance_cost() -> None:
    start = date(2022, 1, 2)
    frame = pl.DataFrame(
        {
            "week_end": [start, start, start + timedelta(days=7), start + timedelta(days=7)],
            "symbol": ["A", "B", "A", "B"],
            "ctrend": [1.0, 0.0, 0.0, 1.0],
            "quintile": [1, 0, 0, 1],
            "forward_return": [0.10, 0.0, 0.0, 0.20],
        }
    )
    series = _build_portfolio_series(
        frame,
        portfolio="long_only_top",
        execution="taker",
        missing_policy="delisting_loss",
        cost_model=_model(spot_taker_bps=100.0),
        n_quintiles=2,
        oos_start=start,
    )

    assert [p.turnover for p in series.points] == pytest.approx([1.0, 2.0])
    assert [p.cost for p in series.points] == pytest.approx([0.01, 0.02])
    assert [p.net_return for p in series.points] == pytest.approx([0.09, 0.18])


def test_missing_selected_forward_return_is_counted_as_delisting_loss() -> None:
    start = date(2022, 1, 2)
    frame = pl.DataFrame(
        {
            "week_end": [start, start, start, start, start + timedelta(days=7),
                         start + timedelta(days=7)],
            "symbol": ["A", "B", "C", "D", "A", "B"],
            "ctrend": [3.0, 2.0, 1.0, 0.0, 1.0, 0.0],
            "quintile": [1, 1, 0, 0, 1, 0],
            "forward_return": [None, 0.20, 0.0, 0.0, 0.10, 0.0],
        }
    )
    headline = _build_portfolio_series(
        frame,
        portfolio="long_only_top",
        execution="taker",
        missing_policy="delisting_loss",
        cost_model=_model(),
        n_quintiles=2,
        oos_start=start,
    )
    favourable = _build_portfolio_series(
        frame,
        portfolio="long_only_top",
        execution="taker",
        missing_policy="drop_and_renormalize",
        cost_model=_model(),
        n_quintiles=2,
        oos_start=start,
    )

    assert headline.missing_returns == 1
    assert headline.points[0].gross_return == pytest.approx(-0.40)
    assert headline.points[0].n_missing_returns == 1
    assert favourable.missing_returns == 0
    assert favourable.points[0].gross_return == pytest.approx(0.20)
