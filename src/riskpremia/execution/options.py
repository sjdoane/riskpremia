"""The delta-hedged short-option transaction cost, per quote (ADR 0004 Layer ii, PR5d).

Cost-model-first: this computes what it COSTS to sell one option and statically
delta-hedge it on the perp, from a single `OptionQuoteRecord` + a `DeribitOptionCostModel`.
The per-trade short-variance P&L (premium minus the terminal payoff plus the static-hedge
P&L), the option-leg P&L-conservation invariant, the un-modeled path-rehedge guard, and
the financing/margin charge are the NEXT PR (PR5e); this module is the cost side they
build on.

Every term is a POSITIVE fraction of the underlying notional S per contract (the inverse
BTC/ETH convention; see `DeribitOptionCostModel`). S is the COST base, not the
return/capital base: a return divides the net by the posted margin
(`model.initial_margin_fraction * S`), never by S.

The entry SPREAD is the realized sell-side slippage `mark - bid` (you sell a single
option at the bid; this is the full slippage from the mark, deliberately more
conservative than the carry's half-spread, design review L4), floored by the model's
assumed minimum so a crossed/thin quote (mark <= bid) cannot model a zero spread. The
option trade fee is charged on the EXECUTED (bid) premium so it matches the cash inflow.
Held to European cash-settlement, the option is not closed by a trade (only the delivery
fee), so the perp hedge is the only round-trip leg.

Un-modeled costs (named, deferred), so the round trip is a cost FLOOR: the path rehedge
between entry and expiry (the dominant short-variance cost, ADR 0004 caveat 3); the
financing on the option + hedge margin; the Coinbase routing layer (carried at 0); and
the single-contract / touch-bid fill assumption (the modeled spread is the touch-level
`mark - bid`, not a depth-aware walk of `bid_amount` for a larger short). All are PR5e
or future refinements.
"""

from __future__ import annotations

import attrs

from riskpremia.data.records import OptionQuoteRecord
from riskpremia.execution.cost import DeribitOptionCostModel
from riskpremia.execution.errors import CostModelError


@attrs.frozen(slots=True)
class OptionCostBreakdown:
    """The modeled transaction cost of one delta-hedged short option, every term a
    fraction of the underlying notional S.

    Invariants (pinned by tests): `entry_cost == option_fee + option_spread + routing_fee
    + hedge_entry_cost`; `exit_cost == delivery_fee + hedge_exit_cost`; `round_trip_cost
    == entry_cost + exit_cost`. `spread_is_floored` is True when the assumed floor bound
    (a crossed/thin quote), so a downstream aggregate can see how often the measured
    spread was unavailable. `delivery_fee` is a CEILING and the hedge legs are a FLOOR
    (see `DeribitOptionCostModel`).
    """

    option_fee: float
    option_spread: float
    delivery_fee: float
    routing_fee: float
    hedge_entry_cost: float
    hedge_exit_cost: float
    entry_cost: float
    exit_cost: float
    round_trip_cost: float
    spread_is_floored: bool

    def __attrs_post_init__(self) -> None:
        # Self-consistency guard so a hand-constructed instance cannot lie (the gate in
        # PR5e reads this object). Exact equality holds because the producer builds each
        # aggregate with the identical left-to-right expression.
        entry = self.option_fee + self.option_spread + self.routing_fee + self.hedge_entry_cost
        exit_ = self.delivery_fee + self.hedge_exit_cost
        if self.entry_cost != entry or self.exit_cost != exit_:
            raise CostModelError(
                f"OptionCostBreakdown entry/exit do not match their components: "
                f"entry {self.entry_cost} vs {entry}, exit {self.exit_cost} vs {exit_}"
            )
        if self.round_trip_cost != self.entry_cost + self.exit_cost:
            raise CostModelError(
                f"OptionCostBreakdown round_trip {self.round_trip_cost} != entry + exit "
                f"{self.entry_cost + self.exit_cost}"
            )


def delta_hedged_option_cost(
    quote: OptionQuoteRecord,
    model: DeribitOptionCostModel,
    *,
    hedge_entry_taker: bool = True,
    hedge_exit_taker: bool = True,
) -> OptionCostBreakdown:
    """The transaction cost of selling `quote` and statically delta-hedging it.

    Requires a two-sided-enough quote (a mark, a bid to sell into, and a delta to size
    the hedge); an option with no bid is untradeable on the short side and raises rather
    than modeling a phantom fill.

    Raises:
      CostModelError: when the mark, bid, or delta is missing (untradeable), or the
        option delta magnitude exceeds 1 (a corrupt chain row).
    """
    if quote.mark_price is None:
        raise CostModelError(f"option {quote.instrument} has no mark price; cannot cost it")
    if quote.bid_price is None:
        raise CostModelError(
            f"option {quote.instrument} has no bid; untradeable on the short side"
        )
    if quote.delta is None:
        raise CostModelError(f"option {quote.instrument} has no delta; cannot size the hedge")
    abs_delta = abs(float(quote.delta))
    if abs_delta > 1.0:
        raise CostModelError(
            f"option {quote.instrument} has |delta|={abs_delta} > 1; a corrupt chain row"
        )

    mark = float(quote.mark_price)
    bid = float(quote.bid_price)
    floor = model.option_spread_floor_fraction()
    measured_spread = mark - bid  # sell a single option at the bid: the full slippage vs mark
    option_spread = max(floor, measured_spread)
    spread_is_floored = measured_spread <= floor

    option_fee = model.option_trade_fee_fraction(bid)  # the fee is on the executed premium
    delivery_fee = model.option_delivery_fee_fraction()
    routing_fee = model.routing_fee_fraction()
    hedge_entry_cost = model.hedge_side_cost_fraction(abs_delta, taker=hedge_entry_taker)
    hedge_exit_cost = model.hedge_side_cost_fraction(abs_delta, taker=hedge_exit_taker)

    entry_cost = option_fee + option_spread + routing_fee + hedge_entry_cost
    exit_cost = delivery_fee + hedge_exit_cost
    return OptionCostBreakdown(
        option_fee=option_fee,
        option_spread=option_spread,
        delivery_fee=delivery_fee,
        routing_fee=routing_fee,
        hedge_entry_cost=hedge_entry_cost,
        hedge_exit_cost=hedge_exit_cost,
        entry_cost=entry_cost,
        exit_cost=exit_cost,
        round_trip_cost=entry_cost + exit_cost,
        spread_is_floored=spread_is_floored,
    )
