"""The option cost model against LIVE data (network-marked, skipped by default; run with
`-m network`). Fetch a real first-of-month BTC chain, pick the most at-the-money
tradeable call, and confirm its delta-hedged cost is sane and the invariants hold on a
real quote (the cost-model real-data proof, ADR 0004 Layer ii PR5d)."""

from __future__ import annotations

from datetime import date

import pytest

from riskpremia.data.records import OptionQuoteRecord
from riskpremia.data.sources.tardis_options import TardisOptionChainSource
from riskpremia.execution.cost import DERIBIT_OPTION
from riskpremia.execution.options import delta_hedged_option_cost

pytestmark = pytest.mark.network


def _moneyness(quote: OptionQuoteRecord) -> float:
    return abs(float(quote.strike) / float(quote.underlying_price) - 1.0)


def test_cost_a_real_near_atm_call() -> None:
    snap = TardisOptionChainSource().fetch_snapshot(
        "BTC", date(2024, 1, 1), as_of_offset_minutes=20
    )
    tradeable = [
        q
        for q in snap.quotes
        if q.option_type == "call" and q.bid_price is not None and q.mark_price is not None
        and q.delta is not None
    ]
    assert tradeable, "expected at least one tradeable call in a real BTC chain"
    atm = min(tradeable, key=_moneyness)

    cost = delta_hedged_option_cost(atm, DERIBIT_OPTION)
    assert cost.round_trip_cost == cost.entry_cost + cost.exit_cost
    assert 0.0 < cost.round_trip_cost < 0.05  # a sane sub-5%-of-S round trip near the money
    assert cost.option_fee > 0.0 and cost.hedge_entry_cost > 0.0

    print(  # noqa: T201 (the PR5d real-data exhibit)
        f"\n[Deribit option cost, {atm.instrument}] bid={atm.bid_price} mark={atm.mark_price} "
        f"delta={atm.delta} -> round_trip {cost.round_trip_cost * 1e4:.1f} bps of underlying "
        f"(fee {cost.option_fee * 1e4:.1f}, spread {cost.option_spread * 1e4:.1f}, "
        f"hedge {(cost.hedge_entry_cost + cost.hedge_exit_cost) * 1e4:.1f}, "
        f"delivery {cost.delivery_fee * 1e4:.1f}); "
        f"premium received {float(atm.bid_price) * 1e4:.0f} bps of underlying"
    )
