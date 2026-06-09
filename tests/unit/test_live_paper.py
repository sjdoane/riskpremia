"""The paper-trading engine: rebalance math, the backtest's cost mechanics, and state round-trip."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from riskpremia.live.errors import LiveError
from riskpremia.live.paper import (
    account_value,
    load_account,
    new_account,
    rebalance,
    save_account,
)

_CHARGED = ("VTI", "IEF")
_PRICES = {"VTI": 100.0, "IEF": 50.0, "SGOV": 100.0}


def _rebalance(account, weights, prices=None, *, cost=0.0005):
    return rebalance(
        account, weights, prices or _PRICES, date(2026, 5, 31),
        turnover_cost_per_side=cost, charged_symbols=_CHARGED,
    )


def test_account_value_marks_cash_and_positions() -> None:
    acct = new_account(1000.0)
    assert account_value(acct, _PRICES) == pytest.approx(1000.0)
    res = _rebalance(acct, {"VTI": 0.5, "IEF": 0.5, "SGOV": 0.0}, cost=0.0)
    assert account_value(res.account, _PRICES) == pytest.approx(1000.0)


def test_first_rebalance_both_active_charges_full_entry_turnover() -> None:
    res = _rebalance(new_account(10_000.0), {"VTI": 0.5, "IEF": 0.5, "SGOV": 0.0})
    assert res.turnover == pytest.approx(1.0)  # 0.5 into VTI plus 0.5 into IEF
    assert res.cost_paid == pytest.approx(10_000.0 * 1.0 * 0.0005)
    assert res.value_after == pytest.approx(9_995.0)
    assert res.account.positions["VTI"] == pytest.approx(9_995.0 * 0.5 / 100.0)
    assert res.account.positions["IEF"] == pytest.approx(9_995.0 * 0.5 / 50.0)
    assert res.account.cash == pytest.approx(0.0)


def test_post_rebalance_weights_match_the_target() -> None:
    res = _rebalance(new_account(10_000.0), {"VTI": 0.5, "IEF": 0.0, "SGOV": 0.5}, cost=0.0)
    value = account_value(res.account, _PRICES)
    vti_w = res.account.positions["VTI"] * _PRICES["VTI"] / value
    sgov_w = res.account.positions["SGOV"] * _PRICES["SGOV"] / value
    assert vti_w == pytest.approx(0.5)
    assert sgov_w == pytest.approx(0.5)
    assert res.account.positions.get("IEF", 0.0) == pytest.approx(0.0)


def test_turnover_charges_only_the_risk_sleeves_not_cash() -> None:
    # start fully in equity, then exit equity to cash: only VTI's 0.5 weight change is charged.
    start = _rebalance(new_account(10_000.0), {"VTI": 1.0, "IEF": 0.0, "SGOV": 0.0}, cost=0.0)
    exit_to_cash = _rebalance(start.account, {"VTI": 0.0, "IEF": 0.0, "SGOV": 1.0})
    assert exit_to_cash.turnover == pytest.approx(1.0)  # VTI 1.0 -> 0.0
    # an all-cash to all-cash rebalance moves nothing chargeable
    flat = _rebalance(exit_to_cash.account, {"VTI": 0.0, "IEF": 0.0, "SGOV": 1.0})
    assert flat.turnover == pytest.approx(0.0)
    assert flat.cost_paid == pytest.approx(0.0)


def test_holding_through_a_price_move_captures_the_return() -> None:
    held = _rebalance(new_account(10_000.0), {"VTI": 1.0, "IEF": 0.0, "SGOV": 0.0}, cost=0.0)
    up = {"VTI": 110.0, "IEF": 50.0, "SGOV": 100.0}  # equity up 10 percent
    assert account_value(held.account, up) == pytest.approx(11_000.0)


def test_no_leverage_total_invested_never_exceeds_value() -> None:
    res = _rebalance(new_account(10_000.0), {"VTI": 0.5, "IEF": 0.5, "SGOV": 0.0}, cost=0.0)
    invested = sum(res.account.positions[s] * _PRICES[s] for s in res.account.positions)
    assert invested <= account_value(res.account, _PRICES) + 1e-9


def test_rejects_missing_price_and_nonpositive_value() -> None:
    with pytest.raises(LiveError):
        rebalance(new_account(1000.0), {"VTI": 1.0}, {"IEF": 50.0}, date(2026, 5, 31),
                  turnover_cost_per_side=0.0, charged_symbols=_CHARGED)
    with pytest.raises(LiveError):
        new_account(-5.0)


def test_account_state_round_trips(tmp_path: Path) -> None:
    res = _rebalance(new_account(10_000.0), {"VTI": 0.5, "IEF": 0.5, "SGOV": 0.0}, cost=0.0)
    path = tmp_path / "account.json"
    save_account(path, res.account)
    back = load_account(path)
    assert back.as_of == res.account.as_of
    assert back.positions == pytest.approx(dict(res.account.positions))
    assert back.cash == pytest.approx(res.account.cash)
