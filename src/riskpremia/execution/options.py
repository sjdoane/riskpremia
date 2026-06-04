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

PR5e adds the per-trade short-variance P&L (`simulate_option_trade`). It is accounted in
COIN per contract (the inverse settlement currency); for the inverse contract a cost
"fraction of S" IS a coin amount (1 contract = 1 coin notional = S USD), so the costs
above, the premium, the payoff, and the hedge P&L all add in coin. The option settles in
coin at the expiry price S_T: the short pays `intrinsic_usd / S_T` (NOT `/ S0`), which is
what makes the downside crash loss explode (a put at a 90% crash pays ~9x the notional);
the delta hedge is the Deribit INVERSE perp, P&L `delta * (1 - S0/S_T)` in coin. Getting
either leg wrong (a linear `/ S0` payoff or a linear hedge) understates the left tail, so
the inverse settlement is load-bearing for the peso-tail honesty the study rests on. The
PR5f Sharpe divides `net` (coin) by the posted margin (`initial_margin_fraction`, coin).
"""

from __future__ import annotations

import attrs

from riskpremia.data.records import OptionQuoteRecord, OptionType
from riskpremia.execution.cost import DeribitOptionCostModel
from riskpremia.execution.errors import CostModelError, OptionPnLError


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


@attrs.frozen(slots=True)
class OptionTradePnL:
    """The realized P&L of one delta-hedged SHORT-option trade, in COIN per contract.

    The trade: sell the option at the bid (receive `premium_received`), statically delta-
    hedge on the inverse perp, hold to European cash settlement at `terminal_underlying`,
    pay `terminal_payoff = intrinsic_usd / terminal_underlying` (the inverse coin
    settlement), and unwind the hedge. This is a crude, ENDPOINT short-variance proxy: it
    sees only the entry and expiry prices, not the path, so `path_rehedge_unmodeled` is
    always True and a downstream Sharpe must acknowledge the static-vs-continuous path-P&L
    gap (the dominant un-modeled term, ADR 0004 caveat 3) rather than read this as a
    faithful delta-hedged-variance return.

    Invariants (exact by the producer's fixed association, pinned by a test):
    `gross == (premium_received - terminal_payoff) + static_hedge_pnl`;
    `round_trip_cost == option_fee + option_spread + routing_fee + delivery_fee +
    hedge_entry_cost + hedge_exit_cost`;
    `net == (gross - round_trip_cost) - financing_cost`. `delivery_fee` is the ITM-
    conditional actual (0 for an OTM-expiring option), refining the PR5d ceiling;
    `financing_cost` is a floor (option margin only).
    """

    instrument: str
    option_type: OptionType
    strike: float
    entry_underlying: float
    terminal_underlying: float
    hold_hours: float
    premium_received: float
    terminal_payoff: float
    static_hedge_pnl: float
    option_fee: float
    option_spread: float
    delivery_fee: float
    routing_fee: float
    hedge_entry_cost: float
    hedge_exit_cost: float
    round_trip_cost: float
    financing_cost: float
    gross: float
    net: float
    path_rehedge_unmodeled: bool = True

    def __attrs_post_init__(self) -> None:
        gross = (self.premium_received - self.terminal_payoff) + self.static_hedge_pnl
        round_trip = (
            self.option_fee + self.option_spread + self.routing_fee + self.delivery_fee
            + self.hedge_entry_cost + self.hedge_exit_cost
        )
        net = (gross - round_trip) - self.financing_cost
        if self.gross != gross or self.round_trip_cost != round_trip or self.net != net:
            raise OptionPnLError(
                f"OptionTradePnL conservation violated for {self.instrument}: "
                f"gross {self.gross} vs {gross}, round_trip {self.round_trip_cost} vs "
                f"{round_trip}, net {self.net} vs {net}"
            )


def simulate_option_trade(
    quote: OptionQuoteRecord,
    terminal_underlying: float,
    model: DeribitOptionCostModel,
    *,
    hold_hours: float,
    hedge_entry_taker: bool = True,
    hedge_exit_taker: bool = True,
) -> OptionTradePnL:
    """Simulate selling `quote` delta-hedged and holding it to expiry at
    `terminal_underlying` (the realized settlement price). Returns the COIN per-contract
    P&L decomposition.

    Raises:
      OptionPnLError: on a non-positive entry or terminal underlying, a negative hold, or
        an untradeable quote (missing bid/mark/delta).
      CostModelError: on an out-of-domain option delta (|delta| > 1), via the cost helper.
    """
    if quote.bid_price is None or quote.mark_price is None or quote.delta is None:
        raise OptionPnLError(f"option {quote.instrument} is untradeable (missing bid/mark/delta)")
    s0 = float(quote.underlying_price)
    s_t = float(terminal_underlying)
    if s0 <= 0.0 or s_t <= 0.0:
        raise OptionPnLError(
            f"underlying must be positive; entry {s0}, terminal {s_t} for {quote.instrument}"
        )
    if hold_hours < 0.0:
        raise OptionPnLError(f"hold_hours must be >= 0; got {hold_hours}")

    # Entry-time costs (fee on the bid, measured spread, hedge); reuse the cost helper, then
    # swap its ceiling delivery for the ITM-conditional actual at settlement.
    breakdown = delta_hedged_option_cost(
        quote, model, hedge_entry_taker=hedge_entry_taker, hedge_exit_taker=hedge_exit_taker
    )
    strike = float(quote.strike)
    bid = float(quote.bid_price)
    delta = float(quote.delta)

    if quote.option_type == "call":
        intrinsic_usd = max(s_t - strike, 0.0)
    else:
        intrinsic_usd = max(strike - s_t, 0.0)
    terminal_payoff = intrinsic_usd / s_t  # coin: inverse cash settlement at S_T
    premium_received = bid  # coin: sell at the bid
    static_hedge_pnl = delta * (1.0 - s0 / s_t)  # coin: inverse-perp delta hedge, held static
    delivery_fee = model.option_delivery_fee_on_intrinsic(terminal_payoff)
    financing_cost = model.margin_financing_fraction(hold_hours)

    round_trip_cost = (
        breakdown.option_fee + breakdown.option_spread + breakdown.routing_fee + delivery_fee
        + breakdown.hedge_entry_cost + breakdown.hedge_exit_cost
    )
    gross = (premium_received - terminal_payoff) + static_hedge_pnl
    net = (gross - round_trip_cost) - financing_cost
    return OptionTradePnL(
        instrument=quote.instrument,
        option_type=quote.option_type,
        strike=strike,
        entry_underlying=s0,
        terminal_underlying=s_t,
        hold_hours=hold_hours,
        premium_received=premium_received,
        terminal_payoff=terminal_payoff,
        static_hedge_pnl=static_hedge_pnl,
        option_fee=breakdown.option_fee,
        option_spread=breakdown.option_spread,
        delivery_fee=delivery_fee,
        routing_fee=breakdown.routing_fee,
        hedge_entry_cost=breakdown.hedge_entry_cost,
        hedge_exit_cost=breakdown.hedge_exit_cost,
        round_trip_cost=round_trip_cost,
        financing_cost=financing_cost,
        gross=gross,
        net=net,
    )


def rehedge_cost_sensitivity(
    quote: OptionQuoteRecord, model: DeribitOptionCostModel, n_rehedges: int
) -> float:
    """A CONSERVATIVE upper bound on the un-modeled rehedge TRANSACTION cost (coin): the
    cost of `n_rehedges` perp rehedges, each charged the full `|delta|` side cost.

    The static endpoint hedge in `simulate_option_trade` ignores the path; a real book
    rehedges. This bounds only the rehedge TRANSACTION cost (and over-bounds it: a real
    rehedge trades the delta CHANGE, smaller than `|delta|`). It does NOT bound the
    static-vs-continuous PATH-P&L gap, which is the larger, signed un-modeled term (the
    headline tail table must carry that caveat, not this number).

    Raises:
      OptionPnLError: on `n_rehedges < 0` or a missing delta.
    """
    if n_rehedges < 0:
        raise OptionPnLError(f"n_rehedges must be >= 0; got {n_rehedges}")
    if quote.delta is None:
        raise OptionPnLError(f"option {quote.instrument} has no delta; cannot size rehedges")
    return n_rehedges * model.hedge_side_cost_fraction(abs(float(quote.delta)), taker=True)
