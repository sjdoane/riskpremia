"""The delta-hedged short-option cost model (ADR 0004 Layer ii, PR5d): the Deribit fee
rules, the cost decomposition + invariants, the loud guards, and a deterministic
real-data pin on the committed Tardis sample fixture."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from riskpremia.data.boundary import PydanticTardisOptionRow
from riskpremia.data.records import OptionQuoteRecord
from riskpremia.execution.cost import DERIBIT_OPTION, DeribitOptionCostModel
from riskpremia.execution.errors import CostModelError
from riskpremia.execution.options import delta_hedged_option_cost

_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "tardis_deribit_options_sample.csv"
_BPS = 10_000.0


# ----- the cost model: validation + fee rules --------------------------------

def test_model_rejects_bad_fields() -> None:
    base = dict(
        name="x", tradeable=False, source="cited", option_fee_bps=3.0,
        option_fee_premium_cap=0.125, option_delivery_bps=1.5, option_spread_floor_bps=5.0,
        perp_taker_bps=5.0, perp_maker_bps=0.0, perp_half_spread_bps=1.5,
    )
    DeribitOptionCostModel(**base)  # no raise
    with pytest.raises(CostModelError, match="non-empty name"):
        DeribitOptionCostModel(**{**base, "name": " "})
    with pytest.raises(CostModelError, match="non-empty source"):
        DeribitOptionCostModel(**{**base, "source": ""})
    with pytest.raises(CostModelError, match="option_fee_bps >= 0"):
        DeribitOptionCostModel(**{**base, "option_fee_bps": -1.0})
    with pytest.raises(CostModelError, match="premium_cap"):
        DeribitOptionCostModel(**{**base, "option_fee_premium_cap": 1.5})
    with pytest.raises(CostModelError, match="initial_margin_fraction"):
        DeribitOptionCostModel(**{**base, "initial_margin_fraction": 0.0})


def test_option_trade_fee_min_rule() -> None:
    m = DERIBIT_OPTION
    # A normal-premium option: the 0.03%-of-underlying leg binds (3 bps < 12.5% of premium).
    assert m.option_trade_fee_fraction(0.05) == pytest.approx(3.0 / _BPS)
    # A cheap deep-OTM option: the 12.5%-of-premium CAP binds (12.5% * 0.001 = 0.000125).
    assert m.option_trade_fee_fraction(0.001) == pytest.approx(0.125 * 0.001)
    with pytest.raises(CostModelError, match="premium_fraction >= 0"):
        m.option_trade_fee_fraction(-0.01)


def test_hedge_round_trip_is_entry_plus_exit() -> None:
    m = DERIBIT_OPTION
    rt = m.hedge_round_trip_fraction(0.4, entry_taker=True, exit_taker=False)
    assert rt == m.hedge_side_cost_fraction(0.4, taker=True) + m.hedge_side_cost_fraction(
        0.4, taker=False
    )
    # maker rebate modeled at 0, so a maker side is cheaper than a taker side by the fee.
    maker = m.hedge_side_cost_fraction(0.4, taker=False)
    assert maker < m.hedge_side_cost_fraction(0.4, taker=True)
    with pytest.raises(CostModelError, match="abs_delta >= 0"):
        m.hedge_side_cost_fraction(-0.1, taker=True)


def test_deribit_option_is_flagged_not_us_retail_tradeable() -> None:
    assert DERIBIT_OPTION.tradeable is False  # the binding deploy caveat (ADR 0001 C1 analogue)
    assert "Coinbase" in DERIBIT_OPTION.source and "0.03%" in DERIBIT_OPTION.source


# ----- the cost helper: decomposition, invariants, guards --------------------

def _quote(**over: object) -> OptionQuoteRecord:
    base: dict[str, object] = dict(
        currency="BTC", instrument="BTC-5JAN24-43000-C", option_type="call",
        strike=Decimal("43000"), expiry=datetime(2024, 1, 5, 8, tzinfo=UTC),
        quote_ts=datetime(2024, 1, 1, tzinfo=UTC), underlying_index="BTC-5JAN24",
        underlying_price=Decimal("42485.82"), synthetic_underlying=False,
        bid_price=Decimal("0.018"), mark_price=Decimal("0.0185"), delta=Decimal("0.43"),
    )
    base.update(over)
    return OptionQuoteRecord(**base)  # type: ignore[arg-type]


def test_cost_breakdown_invariants() -> None:
    cost = delta_hedged_option_cost(_quote(), DERIBIT_OPTION)
    assert cost.entry_cost == (
        cost.option_fee + cost.option_spread + cost.routing_fee + cost.hedge_entry_cost
    )
    assert cost.exit_cost == cost.delivery_fee + cost.hedge_exit_cost
    assert cost.round_trip_cost == cost.entry_cost + cost.exit_cost
    flat = (
        cost.option_fee + cost.option_spread + cost.delivery_fee + cost.routing_fee
        + cost.hedge_entry_cost + cost.hedge_exit_cost
    )
    assert abs(cost.round_trip_cost - flat) < 1e-15
    assert cost.round_trip_cost > 0.0


def test_fee_is_on_the_executed_bid_not_mark() -> None:
    # The fee is charged on the bid (the executed premium), not the mark.
    quote = _quote(bid_price=Decimal("0.0006"), mark_price=Decimal("0.0007"), delta=Decimal("0.02"))
    cost = delta_hedged_option_cost(quote, DERIBIT_OPTION)
    assert cost.option_fee == pytest.approx(0.125 * 0.0006)  # the cap binds on the bid premium


def test_spread_is_measured_then_floored() -> None:
    # A wide measured spread is used as-is.
    wide = delta_hedged_option_cost(_quote(bid_price=Decimal("0.010"), mark_price=Decimal("0.020")),
                                    DERIBIT_OPTION)
    assert wide.option_spread == pytest.approx(0.010) and not wide.spread_is_floored
    # A crossed/thin quote (mark <= bid) is floored, never a zero/negative spread.
    crossed = delta_hedged_option_cost(_quote(bid_price=Decimal("0.020"),
                                              mark_price=Decimal("0.019")), DERIBIT_OPTION)
    assert crossed.option_spread == pytest.approx(DERIBIT_OPTION.option_spread_floor_fraction())
    assert crossed.spread_is_floored and crossed.option_spread > 0.0


def test_cost_requires_tradeable_quote() -> None:
    with pytest.raises(CostModelError, match="no bid"):
        delta_hedged_option_cost(_quote(bid_price=None), DERIBIT_OPTION)
    with pytest.raises(CostModelError, match="no mark"):
        delta_hedged_option_cost(_quote(mark_price=None), DERIBIT_OPTION)
    with pytest.raises(CostModelError, match="no delta"):
        delta_hedged_option_cost(_quote(delta=None), DERIBIT_OPTION)
    with pytest.raises(CostModelError, match=r"\|delta\|"):
        delta_hedged_option_cost(_quote(delta=Decimal("1.5")), DERIBIT_OPTION)


# ----- a deterministic real-data pin on the committed Tardis sample fixture ---

def _fixture_quotes() -> dict[str, OptionQuoteRecord]:
    rows = list(csv.reader(_FIXTURE.read_text(encoding="utf-8").splitlines()))
    header = rows[0]
    ti_type, ti_sym = header.index("type"), header.index("symbol")
    out: dict[str, OptionQuoteRecord] = {}
    for r in rows[1:]:
        if r[ti_type] in ("put", "call") and r[ti_sym].startswith("BTC-"):
            rec = PydanticTardisOptionRow.from_row(r).to_record("BTC")
            out[rec.instrument] = rec
    return out


def test_real_fixture_atm_and_deep_otm_costs() -> None:
    quotes = _fixture_quotes()
    # The ATM call (bid 0.018, mark 0.0185, delta 0.43217): the 0.03% fee leg binds.
    atm = delta_hedged_option_cost(quotes["BTC-5JAN24-43000-C"], DERIBIT_OPTION)
    assert atm.option_fee == pytest.approx(3.0 / _BPS)  # 0.03% of underlying < 12.5% of premium
    assert 0.0 < atm.round_trip_cost < 0.01  # a sane sub-1%-of-S round trip
    # The cheap deep-OTM call (bid 0.0006): the 12.5%-of-premium cap binds instead.
    otm = delta_hedged_option_cost(quotes["BTC-5JAN24-51000-C"], DERIBIT_OPTION)
    assert otm.option_fee == pytest.approx(0.125 * 0.0006)
    assert otm.round_trip_cost < atm.round_trip_cost  # cheaper option, smaller hedge + fee


def test_real_fixture_untradeable_options_raise() -> None:
    quotes = _fixture_quotes()
    # The far-OTM 160000 put has an empty bid in the fixture: untradeable on the short side.
    with pytest.raises(CostModelError, match="no bid"):
        delta_hedged_option_cost(quotes["BTC-27SEP24-160000-P"], DERIBIT_OPTION)
