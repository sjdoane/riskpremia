"""The per-trade short-variance option P&L (ADR 0004 Layer ii, PR5e): the inverse coin
settlement (the load-bearing crash-tail correctness), the hedge sign, the conservation
invariant, the ITM-conditional delivery, the margin financing, and the rehedge guard."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from riskpremia.data.boundary import PydanticTardisOptionRow
from riskpremia.data.records import OptionQuoteRecord
from riskpremia.execution.cost import DERIBIT_OPTION
from riskpremia.execution.errors import CostModelError, OptionPnLError
from riskpremia.execution.options import (
    OptionTradePnL,
    delta_hedged_option_cost,
    rehedge_cost_sensitivity,
    simulate_option_trade,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "tardis_deribit_options_sample.csv"
_BPS = 10_000.0


def _quote(**over: object) -> OptionQuoteRecord:
    base: dict[str, object] = dict(
        currency="BTC", instrument="BTC-5JAN24-100-C", option_type="call",
        strike=Decimal("100"), expiry=datetime(2024, 1, 5, 8, tzinfo=UTC),
        quote_ts=datetime(2024, 1, 1, tzinfo=UTC), underlying_index="BTC-5JAN24",
        underlying_price=Decimal("100"), synthetic_underlying=False,
        bid_price=Decimal("0.04"), mark_price=Decimal("0.041"), delta=Decimal("0.5"),
    )
    base.update(over)
    return OptionQuoteRecord(**base)  # type: ignore[arg-type]


# ----- the cost model's PR5e methods -----------------------------------------

def test_delivery_fee_is_itm_conditional() -> None:
    m = DERIBIT_OPTION
    assert m.option_delivery_fee_on_intrinsic(0.0) == 0.0  # OTM-expiring pays no delivery
    # a small ITM value: the 12.5% cap binds (0.125 * 0.0005 < 0.00015)
    assert m.option_delivery_fee_on_intrinsic(0.0005) == pytest.approx(0.125 * 0.0005)
    # a large ITM value: the flat rate binds
    assert m.option_delivery_fee_on_intrinsic(5.0) == pytest.approx(1.5 / _BPS)
    with pytest.raises(CostModelError, match="intrinsic_fraction >= 0"):
        m.option_delivery_fee_on_intrinsic(-0.1)


def test_margin_financing_is_a_floor_on_the_option_margin() -> None:
    m = DERIBIT_OPTION
    # rate * margin_fraction * (hold/year): 0.04 * 0.15 * (8760/8760) = 0.006 for one year
    assert m.margin_financing_fraction(8760.0) == pytest.approx(0.04 * 0.15)
    assert m.margin_financing_fraction(0.0) == 0.0
    with pytest.raises(CostModelError, match="hold_hours >= 0"):
        m.margin_financing_fraction(-1.0)


# ----- signs and the inverse settlement --------------------------------------

def test_short_call_signs_flat_up_down() -> None:
    # Flat: keep the premium. Up: big loss. Down (call OTM): the static hedge loses.
    flat = simulate_option_trade(_quote(), 100.0, DERIBIT_OPTION, hold_hours=96.0)
    assert flat.terminal_payoff == 0.0 and flat.static_hedge_pnl == 0.0
    assert flat.gross == pytest.approx(0.04)  # premium kept

    up = simulate_option_trade(_quote(), 200.0, DERIBIT_OPTION, hold_hours=96.0)
    assert up.terminal_payoff == pytest.approx(100.0 / 200.0)  # inverse: intrinsic_usd / S_T
    assert up.static_hedge_pnl == pytest.approx(0.5 * (1.0 - 100.0 / 200.0))
    assert up.gross < 0.0  # a 2x up-move is a loss for the short call

    down = simulate_option_trade(_quote(), 50.0, DERIBIT_OPTION, hold_hours=96.0)
    assert down.terminal_payoff == 0.0  # the call expires OTM
    assert down.static_hedge_pnl == pytest.approx(0.5 * (1.0 - 100.0 / 50.0))  # < 0, hedge loses
    assert down.gross < 0.0


def test_inverse_settlement_makes_the_put_crash_tail_explode() -> None:
    # THE load-bearing test: a short put settled inverse pays intrinsic_usd / S_T, so a
    # 90% crash pays ~9x the notional, not ~0.9x (the linear /S0 error). The catastrophic
    # peso tail must be visible to the gate.
    put = _quote(instrument="BTC-5JAN24-100-P", option_type="put", strike=Decimal("100"),
                 delta=Decimal("-0.5"))
    crash = simulate_option_trade(put, 10.0, DERIBIT_OPTION, hold_hours=96.0)  # S_T = S0 / 10
    assert crash.terminal_payoff == pytest.approx(90.0 / 10.0)  # = 9.0 coin (inverse), not 0.9
    assert crash.static_hedge_pnl == pytest.approx(-0.5 * (1.0 - 100.0 / 10.0))  # +4.5, hedge gains
    assert crash.net < -3.0  # a multi-x-of-notional loss, the peso tail


# ----- the conservation invariant --------------------------------------------

def test_conservation_holds_and_a_tampered_record_raises() -> None:
    trade = simulate_option_trade(_quote(), 130.0, DERIBIT_OPTION, hold_hours=96.0)
    assert trade.gross == (trade.premium_received - trade.terminal_payoff) + trade.static_hedge_pnl
    assert trade.net == (trade.gross - trade.round_trip_cost) - trade.financing_cost
    assert trade.path_rehedge_unmodeled is True
    # a hand-constructed inconsistent record is rejected by the post-init guard
    with pytest.raises(OptionPnLError, match="conservation"):
        OptionTradePnL(
            instrument="x", option_type="call", strike=100.0, entry_underlying=100.0,
            terminal_underlying=100.0, hold_hours=1.0, premium_received=0.04,
            terminal_payoff=0.0, static_hedge_pnl=0.0, option_fee=0.0003, option_spread=0.0005,
            delivery_fee=0.0, routing_fee=0.0, hedge_entry_cost=0.0, hedge_exit_cost=0.0,
            round_trip_cost=0.0008, financing_cost=0.0, gross=0.04, net=999.0,  # wrong net
        )


def test_round_trip_uses_itm_delivery_not_the_ceiling() -> None:
    # An OTM-expiring trade pays 0 delivery, below the PR5d ceiling.
    ceiling = delta_hedged_option_cost(_quote(), DERIBIT_OPTION).delivery_fee
    otm = simulate_option_trade(_quote(), 50.0, DERIBIT_OPTION, hold_hours=96.0)  # call OTM at 50
    assert otm.delivery_fee == 0.0 < ceiling
    assert otm.round_trip_cost == pytest.approx(
        otm.option_fee + otm.option_spread + otm.routing_fee + otm.hedge_entry_cost
        + otm.hedge_exit_cost  # + 0 delivery
    )


# ----- guards + the rehedge sensitivity --------------------------------------

def test_simulate_guards() -> None:
    with pytest.raises(OptionPnLError, match="underlying must be positive"):
        simulate_option_trade(_quote(), 0.0, DERIBIT_OPTION, hold_hours=96.0)
    with pytest.raises(OptionPnLError, match="hold_hours must be >= 0"):
        simulate_option_trade(_quote(), 100.0, DERIBIT_OPTION, hold_hours=-1.0)
    with pytest.raises(OptionPnLError, match="untradeable"):
        simulate_option_trade(_quote(bid_price=None), 100.0, DERIBIT_OPTION, hold_hours=96.0)


def test_rehedge_cost_sensitivity_bounds_transaction_cost() -> None:
    q = _quote(delta=Decimal("0.4"))
    one = DERIBIT_OPTION.hedge_side_cost_fraction(0.4, taker=True)
    assert rehedge_cost_sensitivity(q, DERIBIT_OPTION, 30) == pytest.approx(30 * one)
    assert rehedge_cost_sensitivity(q, DERIBIT_OPTION, 0) == 0.0
    with pytest.raises(OptionPnLError, match="n_rehedges must be >= 0"):
        rehedge_cost_sensitivity(q, DERIBIT_OPTION, -1)


# ----- a real-fixture crash-tail pin -----------------------------------------

def _fixture_quote(instrument: str) -> OptionQuoteRecord:
    rows = list(csv.reader(_FIXTURE.read_text(encoding="utf-8").splitlines()))
    header = rows[0]
    ti_sym = header.index("symbol")
    for r in rows[1:]:
        if r[ti_sym] == instrument:
            return PydanticTardisOptionRow.from_row(r).to_record("BTC")
    raise AssertionError(f"{instrument} not in the fixture")


def test_real_fixture_put_crash_tail() -> None:
    # A real tradeable put (BTC-29MAR24-43000-P, bid 0.0995, delta -0.405, underlying 44198)
    # driven to a 90% crash: the inverse settlement produces a catastrophic loss.
    put = _fixture_quote("BTC-29MAR24-43000-P")
    s0 = float(put.underlying_price)
    crash = simulate_option_trade(put, s0 / 10.0, DERIBIT_OPTION, hold_hours=24.0 * 30)
    # intrinsic_usd = 43000 - s0/10; payoff = that / (s0/10), a large coin amount
    assert crash.terminal_payoff > 5.0  # multiple times the notional
    assert crash.net < -3.0  # the account-ending peso loss the tail table must surface
    # a no-move expiry keeps the premium (minus costs), a small positive or near-zero
    calm = simulate_option_trade(put, s0, DERIBIT_OPTION, hold_hours=24.0 * 30)
    assert calm.gross > crash.gross  # the crash is far worse than the calm path
