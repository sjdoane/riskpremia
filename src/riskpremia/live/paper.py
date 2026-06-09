"""A self-contained paper-trading engine for the Study 6 rule (no broker, no network, no money).

The account holds shares of the three proxies (the cash sleeve is held as the bill ETF, so idle
capital earns the bill exactly as the backtest assumes). A rebalance marks the book at the given
month-end prices, charges the same turnover cost the backtest charges (per side on the risk-sleeve
weight change; the cash leg is the residual and not charged, matching the backtest), and moves the
holdings to the target. State is a small JSON file so a track record accrues across months.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import attrs

from riskpremia.live.errors import LiveError


@attrs.frozen(slots=True)
class PaperAccount:
    """The simulated holdings: shares per symbol, a tiny residual cash, and the last rebalance."""

    cash: float
    positions: Mapping[str, float]
    as_of: str


@attrs.frozen(slots=True)
class Fill:
    """One simulated trade at the month-end price."""

    symbol: str
    side: str
    shares: float
    price: float
    notional: float


@attrs.frozen(slots=True)
class RebalanceResult:
    """The outcome of one monthly rebalance."""

    account: PaperAccount
    fills: tuple[Fill, ...]
    turnover: float
    cost_paid: float
    value_before: float
    value_after: float


def new_account(starting_cash: float) -> PaperAccount:
    """An empty account holding only cash, before the first rebalance."""
    if starting_cash <= 0.0:
        raise LiveError("starting cash must be positive")
    return PaperAccount(cash=starting_cash, positions={}, as_of="")


def account_value(account: PaperAccount, prices: Mapping[str, float]) -> float:
    """Mark the account to the given prices."""
    total = account.cash
    for symbol, shares in account.positions.items():
        if symbol not in prices:
            raise LiveError(f"no price for held symbol {symbol!r}")
        total += shares * prices[symbol]
    return total


def rebalance(
    account: PaperAccount,
    target_weights: Mapping[str, float],
    prices: Mapping[str, float],
    as_of: date,
    *,
    turnover_cost_per_side: float,
    charged_symbols: Mapping[str, str] | tuple[str, ...],
) -> RebalanceResult:
    """Move the account to the target weights at the given prices, charging the backtest's cost.

    `charged_symbols` is the set of risk-sleeve symbols whose weight change incurs turnover cost
    (the cash proxy is the residual and is not charged, exactly as in the backtest).
    """
    value = account_value(account, prices)
    if value <= 0.0:
        raise LiveError("cannot rebalance a non-positive account value")
    if abs(math.fsum(target_weights.values()) - 1.0) > 1e-9:
        raise LiveError(f"target weights must sum to 1, got {math.fsum(target_weights.values())}")
    for symbol in target_weights:
        if symbol not in prices:
            raise LiveError(f"no price for target symbol {symbol!r}")
        if prices[symbol] <= 0.0:
            raise LiveError(f"price for {symbol!r} must be positive")
    charged = tuple(charged_symbols)
    current_weight = {
        symbol: account.positions.get(symbol, 0.0) * prices[symbol] / value
        for symbol in target_weights
    }
    turnover = math.fsum(
        abs(target_weights[s] - current_weight.get(s, 0.0)) for s in charged
    )
    cost_fraction = turnover * turnover_cost_per_side
    if cost_fraction >= 1.0:
        raise LiveError(f"rebalance cost {cost_fraction} would wipe out the account")
    value_after = value * (1.0 - cost_fraction)
    cost_paid = value - value_after

    new_positions: dict[str, float] = {}
    fills: list[Fill] = []
    for symbol, weight in target_weights.items():
        target_shares = value_after * weight / prices[symbol]
        delta = target_shares - account.positions.get(symbol, 0.0)
        new_positions[symbol] = target_shares
        if abs(delta) > 1e-9:
            side = "buy" if delta > 0.0 else "sell"
            price = prices[symbol]
            fills.append(Fill(symbol, side, abs(delta), price, abs(delta) * price))
    new = PaperAccount(cash=0.0, positions=new_positions, as_of=as_of.isoformat())
    return RebalanceResult(new, tuple(fills), turnover, cost_paid, value, value_after)


def save_account(path: Path, account: PaperAccount) -> None:
    """Persist the account state as deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cash": account.cash, "positions": dict(account.positions), "as_of": account.as_of}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_account(path: Path) -> PaperAccount:
    """Read the account state."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise LiveError(f"{path.name}: account state is not a JSON object")
    positions = data.get("positions", {})
    if not isinstance(positions, dict):
        raise LiveError(f"{path.name}: positions must be a JSON object")
    return PaperAccount(
        cash=float(data["cash"]),
        positions={str(k): float(v) for k, v in positions.items()},
        as_of=str(data.get("as_of", "")),
    )
