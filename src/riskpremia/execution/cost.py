"""The per-venue cost model for the delta-neutral two-leg carry (ADR 0003).

A frozen, fully-typed `VenueCostModel` charging both legs (spot + perpetual) on
both sides (entry + exit): exchange taker/maker fees, the bid-ask half-spread,
and the opportunity cost of the capital tied up over the hold. Per ADR 0001
decision 3 and the ADR 0003 cross-check, the cost is parameterised to a genuinely
US-tradeable venue (Kraken Futures, Hyperliquid), not the Binance data venue, so
the kill gate runs against costs a US retail trader can actually incur. Binance
and OKX are carried as NON-tradeable reference points so the gate is a
venue-cost-sensitivity surface.

Sign and units convention (load-bearing): every fraction this module returns is a
POSITIVE outflow expressed as a fraction of the single-leg notional N (the same
base the carry P&L uses for `funding_collected` and `price_pnl`, so the terms add
without a rebasing step). A round trip pays the half-spread on entry AND exit on
BOTH legs (= two full spreads) plus four exchange-fee legs. The half-spread is
charged on every execution as a deliberately conservative treatment: even a
passive (maker) attempt budgets the spread here, because true passive-fill
economics need a fill-probability model that belongs to the deferred capacity
milestone. v1 default execution is TAKER both legs both sides.

Financing carries the no-cross-margin 2N capital base (ADR 0003 amendment A1):
`financing = funding_capital_rate * capital_multiple * (hold_hours / 8760)`, with
`capital_multiple = 2.0` because both legs are funded with no spot/perp
cross-margin. It is the conservative, economically correct charge.

The fee schedules are real published base/lowest-tier numbers, verified June 2026
(see each model's `source`). The spreads are deliberately conservative provisional
assumptions (ADR 0003 finding 7): `spread_basis="assumed"` flags the model
provisional, and the immediate follow-up replaces the assumption with the median
half-spread measured from the free Binance Vision bookTicker dataset. The kill
decision reads the less favourable input, so a soft spread cannot fake a pass.
"""

from __future__ import annotations

from typing import Literal

import attrs

from riskpremia.execution.errors import CostModelError

_BPS = 10_000.0
"""One basis point is 1/10_000; a *_bps field divided by this is a fraction."""

_HOURS_PER_YEAR = 8_760.0
"""365 * 24. The financing rate is annualized, so a hold in hours scales by
hold_hours / 8760. Crypto trades 24/7, so the calendar-year hour count is exact,
not a 252-trading-day convention."""

Leg = Literal["spot", "perp"]
SpreadBasis = Literal["assumed", "measured"]


@attrs.frozen(slots=True)
class VenueCostModel:
    """The modeled round-trip cost of a delta-neutral carry on one venue.

    All `*_bps` fields are per-execution, per-leg fee/spread rates in basis
    points; the methods convert to positive fractions of single-leg notional N.
    `tradeable` marks whether a US retail trader can actually use the venue (the
    kill gate is decided on tradeable venues; the others are reference points).
    `spread_basis` is `"assumed"` until the measured-spread follow-up lands;
    `provisional` exposes that flag so a downstream aggregate cannot publish a
    measured-looking number from an assumed spread.
    """

    name: str
    tradeable: bool
    spot_taker_bps: float
    spot_maker_bps: float
    perp_taker_bps: float
    perp_maker_bps: float
    spot_half_spread_bps: float
    perp_half_spread_bps: float
    source: str
    spread_basis: SpreadBasis = "assumed"
    funding_capital_rate: float = 0.04
    capital_multiple: float = 2.0

    def __attrs_post_init__(self) -> None:
        if not self.name.strip():
            raise CostModelError("VenueCostModel requires a non-empty name")
        if not self.source.strip():
            raise CostModelError(
                f"VenueCostModel {self.name!r} requires a non-empty source (the cited "
                f"fee-schedule + financing-rate provenance); a cost with no provenance "
                f"must not silently enter the kill gate"
            )
        bps_fields = {
            "spot_taker_bps": self.spot_taker_bps,
            "spot_maker_bps": self.spot_maker_bps,
            "perp_taker_bps": self.perp_taker_bps,
            "perp_maker_bps": self.perp_maker_bps,
            "spot_half_spread_bps": self.spot_half_spread_bps,
            "perp_half_spread_bps": self.perp_half_spread_bps,
        }
        for field_name, value in bps_fields.items():
            if value < 0.0:
                raise CostModelError(
                    f"VenueCostModel {self.name!r} requires {field_name} >= 0; got {value}"
                )
        if self.funding_capital_rate < 0.0:
            raise CostModelError(
                f"VenueCostModel {self.name!r} requires funding_capital_rate >= 0; "
                f"got {self.funding_capital_rate}"
            )
        if self.capital_multiple < 0.0:
            raise CostModelError(
                f"VenueCostModel {self.name!r} requires capital_multiple >= 0; "
                f"got {self.capital_multiple}"
            )

    @property
    def provisional(self) -> bool:
        """True while the spread is an assumed (not measured) input.

        The kill gate result built on a provisional model is labelled
        provisional-pending-measured-spread (ADR 0003 finding 7)."""
        return self.spread_basis == "assumed"

    def _leg_fee_bps(self, *, leg: Leg, taker: bool) -> float:
        if leg == "spot":
            return self.spot_taker_bps if taker else self.spot_maker_bps
        return self.perp_taker_bps if taker else self.perp_maker_bps

    def _leg_half_spread_bps(self, *, leg: Leg) -> float:
        return self.spot_half_spread_bps if leg == "spot" else self.perp_half_spread_bps

    def leg_cost_fraction(self, *, leg: Leg, taker: bool) -> float:
        """One execution of one leg: (fee + half-spread) as a fraction of N."""
        return (self._leg_fee_bps(leg=leg, taker=taker) + self._leg_half_spread_bps(leg=leg)) / _BPS

    def side_cost_fraction(self, *, taker: bool) -> float:
        """One side (open OR close) of the whole book = the spot leg + the perp leg."""
        return self.leg_cost_fraction(leg="spot", taker=taker) + self.leg_cost_fraction(
            leg="perp", taker=taker
        )

    def round_trip_cost_fraction(
        self, *, entry_taker: bool = True, exit_taker: bool = True
    ) -> float:
        """The full round-trip cost (open both legs + close both legs) as a fraction of N.

        Default is TAKER both sides (the conservative locked default). The
        entry/exit taker flags let the cost-sensitivity surface model the
        realistic maker-in / taker-out execution without forcing a single style
        across both sides. Equals `entry_cost_fraction + exit_cost_fraction` by
        construction (pinned by a test)."""
        return self.side_cost_fraction(taker=entry_taker) + self.side_cost_fraction(
            taker=exit_taker
        )

    def entry_cost_fraction(self, *, taker: bool = True) -> float:
        """The cost of opening both legs (one side), as a fraction of N."""
        return self.side_cost_fraction(taker=taker)

    def exit_cost_fraction(self, *, taker: bool = True) -> float:
        """The cost of closing both legs (one side), as a fraction of N."""
        return self.side_cost_fraction(taker=taker)

    def financing_cost_fraction(self, *, hold_hours: float) -> float:
        """The opportunity cost of the tied-up capital over the hold, fraction of N.

        `funding_capital_rate * capital_multiple * (hold_hours / 8760)` (ADR 0003
        amendment A1 + A2). `capital_multiple = 2.0` charges the no-cross-margin
        2N base; `hold_hours` is the real wall-clock hold `(dt[exit] - dt[entry])`,
        not a nominal `H * interval`, so a gap-straddling hold is not under-charged.

        Raises:
          CostModelError: when `hold_hours < 0` (a negative hold is a caller bug).
        """
        if hold_hours < 0.0:
            raise CostModelError(
                f"financing_cost_fraction requires hold_hours >= 0; got {hold_hours}"
            )
        return self.funding_capital_rate * self.capital_multiple * (hold_hours / _HOURS_PER_YEAR)


# =============================================================================
# Cited venue fee schedules (base / lowest 30-day-volume tier, verified June
# 2026). The kill gate is decided on the tradeable venues; binance / okx are
# non-tradeable reference points (their live REST APIs are geo-blocked from US
# IPs, ADR 0001). Spot fees are the spot leg, perp fees the short-perp leg.
# The half-spreads are deliberately conservative provisional assumptions
# (spread_basis defaults to "assumed"); the measured-spread follow-up replaces
# them. Funding-capital opportunity cost defaults to 4% annualized (a 2026 USD
# money-market level); it is the same across venues so the surface isolates the
# fee + funding + venue-basis differences.
# =============================================================================

# A conservative provisional half-spread per leg, in bps. BTCUSDT top-of-book is
# tighter than this on liquid venues; the high value is intentional so the
# assumed-spread kill cannot be softer than a future measured one.
_SPOT_HALF_SPREAD_BPS = 2.0
_PERP_HALF_SPREAD_BPS = 1.5

KRAKEN = VenueCostModel(
    name="kraken",
    tradeable=True,
    # Kraken Pro spot base tier (<$50k 30d): maker 0.16% / taker 0.26%.
    spot_taker_bps=26.0,
    spot_maker_bps=16.0,
    # Kraken Futures single-collateral perpetual standard: maker 0.02% / taker 0.05%.
    perp_taker_bps=5.0,
    perp_maker_bps=2.0,
    spot_half_spread_bps=_SPOT_HALF_SPREAD_BPS,
    perp_half_spread_bps=_PERP_HALF_SPREAD_BPS,
    source=(
        "Kraken Pro spot fee schedule (kraken.com/features/fee-schedule) + Kraken "
        "Futures derivatives fees (support.kraken.com/articles/360048917612), base "
        "tier, verified 2026-06"
    ),
)

HYPERLIQUID = VenueCostModel(
    name="hyperliquid",
    tradeable=True,
    # The spot leg of a Hyperliquid-perp carry is bought on a US spot venue, so it
    # carries the same representative US-spot fee as Kraken Pro spot (documented
    # modeling choice; Hyperliquid's own spot market is HIP-token-focused).
    spot_taker_bps=26.0,
    spot_maker_bps=16.0,
    # Hyperliquid perpetual base tier (<$5M 14d): maker 0.015% / taker 0.045%.
    perp_taker_bps=4.5,
    perp_maker_bps=1.5,
    spot_half_spread_bps=_SPOT_HALF_SPREAD_BPS,
    perp_half_spread_bps=_PERP_HALF_SPREAD_BPS,
    source=(
        "Hyperliquid perpetual fee schedule (hyperliquid.gitbook.io/hyperliquid-docs/"
        "trading/fees), base tier; spot leg modeled at the Kraken Pro US-spot rate, "
        "verified 2026-06"
    ),
)

BINANCE_REFERENCE = VenueCostModel(
    name="binance_reference",
    tradeable=False,
    # Binance spot 0.10% / 0.10%; USD-M futures maker 0.02% / taker 0.05%.
    # NON-tradeable from a US IP (live REST geo-blocked, ADR 0001); reference only.
    spot_taker_bps=10.0,
    spot_maker_bps=10.0,
    perp_taker_bps=5.0,
    perp_maker_bps=2.0,
    spot_half_spread_bps=_SPOT_HALF_SPREAD_BPS,
    perp_half_spread_bps=_PERP_HALF_SPREAD_BPS,
    source=(
        "Binance spot + USD-M futures fee schedule, base tier; NON-tradeable from a "
        "US IP (geo-blocked), carried as a reference point, verified 2026-06"
    ),
)

OKX_REFERENCE = VenueCostModel(
    name="okx_reference",
    tradeable=False,
    # OKX spot maker 0.08% / taker 0.10%; perpetual maker 0.02% / taker 0.05%.
    # NON-tradeable from a US IP for a retail carry; reference only.
    spot_taker_bps=10.0,
    spot_maker_bps=8.0,
    perp_taker_bps=5.0,
    perp_maker_bps=2.0,
    spot_half_spread_bps=_SPOT_HALF_SPREAD_BPS,
    perp_half_spread_bps=_PERP_HALF_SPREAD_BPS,
    source=(
        "OKX spot + perpetual-swap fee schedule (okx.com/fees), base tier; carried "
        "as a non-tradeable reference point, verified 2026-06"
    ),
)

@attrs.frozen(slots=True)
class DeribitOptionCostModel:
    """The modeled transaction cost of a DELTA-HEDGED SHORT option on Deribit (ADR 0004
    Layer ii). A sibling to `VenueCostModel` for the option leg + its perp delta hedge.

    Convention (load-bearing, design review C1): every cost method returns a POSITIVE
    fraction of the UNDERLYING notional S per contract. Deribit BTC/ETH options are
    INVERSE (coin-settled); one contract is one unit of underlying and the premium is
    quoted in coin, so the premium itself is a fraction of S (premium/S = the coin
    price) and every cost adds coherently on the S base, mirroring `carry.py`'s
    fraction-of-N. **S is the COST base, NOT the return/capital base.** A short option
    is margined, not fully funded, so the eventual Sharpe in PR5e must divide the net
    P&L (a fraction of S) by the MARGIN posted (`initial_margin_fraction * S`), never by
    S; this field pins that base here so the units cannot drift in PR5e.

    This model costs the SHORT (premium-receiver) side: you sell the option at the bid,
    pay the option trade fee, statically delta-hedge on the perp, hold to European
    cash-settlement, pay the delivery fee, and unwind the hedge (design review L2). The
    long side has the same fee but buys at the ask.

    Conservatism placement (design review): the option entry spread is MEASURED from the
    chain (the realized bid-vs-mark slippage, a strength over the carry's assumed
    spread) with an assumed floor for crossed/thin quotes; the delivery fee here is a
    CEILING (the un-capped flat rate; PR5e charges it ITM-conditional on the actual
    intrinsic, so the OTM majority that expire worthless pay ~0); the static entry+exit
    hedge is a FLOOR on the true delta-management cost (the path rehedge between entry
    and expiry is the dominant UN-modeled term, ADR 0004 caveat 3, a PR5e diagnostic);
    the perp maker rebate is modeled at 0; financing on the option margin + the hedge
    margin is deferred to PR5e with the capital base. The Coinbase-routing fee layer is
    carried as a field at 0 (no published retail schedule yet).

    Fee schedule verified + cited June 2026 (see `source`). `tradeable=False`: US retail
    cannot directly trade Deribit; the regulated path (Coinbase Financial Markets, CFTC-
    cleared May 2026) is institutional-live / retail-coming-soon, a binding deploy caveat
    (the ADR 0001 C1 US-tradeable-venue analogue).
    """

    name: str
    tradeable: bool
    source: str
    option_fee_bps: float
    option_fee_premium_cap: float
    option_delivery_bps: float
    option_spread_floor_bps: float
    perp_taker_bps: float
    perp_maker_bps: float
    perp_half_spread_bps: float
    routing_fee_bps: float = 0.0
    initial_margin_fraction: float = 0.15
    funding_capital_rate: float = 0.04

    def __attrs_post_init__(self) -> None:
        if not self.name.strip():
            raise CostModelError("DeribitOptionCostModel requires a non-empty name")
        if not self.source.strip():
            raise CostModelError(
                f"DeribitOptionCostModel {self.name!r} requires a non-empty source (the "
                f"cited fee-schedule provenance)"
            )
        nonneg = {
            "option_fee_bps": self.option_fee_bps,
            "option_delivery_bps": self.option_delivery_bps,
            "option_spread_floor_bps": self.option_spread_floor_bps,
            "perp_taker_bps": self.perp_taker_bps,
            "perp_maker_bps": self.perp_maker_bps,
            "perp_half_spread_bps": self.perp_half_spread_bps,
            "routing_fee_bps": self.routing_fee_bps,
        }
        for field_name, value in nonneg.items():
            if value < 0.0:
                raise CostModelError(
                    f"DeribitOptionCostModel {self.name!r} requires {field_name} >= 0; got {value}"
                )
        if not (0.0 <= self.option_fee_premium_cap <= 1.0):
            raise CostModelError(
                f"DeribitOptionCostModel {self.name!r} requires option_fee_premium_cap in "
                f"[0, 1] (a fraction of premium); got {self.option_fee_premium_cap}"
            )
        if not (0.0 < self.initial_margin_fraction <= 1.0):
            raise CostModelError(
                f"DeribitOptionCostModel {self.name!r} requires initial_margin_fraction in "
                f"(0, 1]; got {self.initial_margin_fraction}"
            )
        if self.funding_capital_rate < 0.0:
            raise CostModelError(
                f"DeribitOptionCostModel {self.name!r} requires funding_capital_rate >= 0; "
                f"got {self.funding_capital_rate}"
            )

    def option_trade_fee_fraction(self, premium_fraction: float) -> float:
        """The option trade fee (charged once, on entry), as a fraction of S.

        `min(option_fee_bps/1e4, option_fee_premium_cap * premium_fraction)`, the Deribit
        `min(0.03% of underlying, 12.5% of premium)` rule (maker == taker for options).
        `premium_fraction` is the EXECUTED premium in coin terms (= premium/S); pass the
        BID for a short sale so the fee is on the same premium as the cash inflow.

        Raises:
          CostModelError: when `premium_fraction < 0`.
        """
        if premium_fraction < 0.0:
            raise CostModelError(
                f"option_trade_fee_fraction requires premium_fraction >= 0; got {premium_fraction}"
            )
        return min(self.option_fee_bps / _BPS, self.option_fee_premium_cap * premium_fraction)

    def option_delivery_fee_fraction(self) -> float:
        """A CEILING on the settlement delivery fee, fraction of S (the un-capped flat
        `option_delivery_bps`). PR5e replaces it with the ITM-conditional charge
        `min(option_delivery_bps/1e4, 0.125 * intrinsic/S)`, which is ~0 for the OTM
        majority; this flat ceiling deliberately over-charges (the safe direction)."""
        return self.option_delivery_bps / _BPS

    def routing_fee_fraction(self) -> float:
        """The US-access routing layer (Coinbase Financial Markets), fraction of S.

        Carried at 0 pending a published retail routing schedule, so the model is a cost
        FLOOR for the future US-retail-accessible path (design review M1)."""
        return self.routing_fee_bps / _BPS

    def option_spread_floor_fraction(self) -> float:
        """The assumed minimum option entry-spread cost, fraction of S (a conservative
        floor that also catches a crossed/stale quote where mark <= bid)."""
        return self.option_spread_floor_bps / _BPS

    def hedge_side_cost_fraction(self, abs_delta: float, *, taker: bool) -> float:
        """One side (entry OR exit) of the perp delta hedge on `|delta| * S` notional, as
        a fraction of S. The maker rebate is modeled at 0 (conservative).

        Raises:
          CostModelError: when `abs_delta < 0`.
        """
        if abs_delta < 0.0:
            raise CostModelError(
                f"hedge_side_cost_fraction requires abs_delta >= 0; got {abs_delta}"
            )
        fee = self.perp_taker_bps if taker else self.perp_maker_bps
        return abs_delta * (fee + self.perp_half_spread_bps) / _BPS

    def hedge_round_trip_fraction(
        self, abs_delta: float, *, entry_taker: bool = True, exit_taker: bool = True
    ) -> float:
        """The hedge entry + exit cost (a FLOOR; the path rehedge is un-modeled), frac of S.

        Equals `hedge_side_cost_fraction(entry) + hedge_side_cost_fraction(exit)` by
        construction (pinned by a test)."""
        return self.hedge_side_cost_fraction(abs_delta, taker=entry_taker) + (
            self.hedge_side_cost_fraction(abs_delta, taker=exit_taker)
        )

    def option_delivery_fee_on_intrinsic(self, intrinsic_fraction: float) -> float:
        """The ACTUAL settlement delivery fee given the terminal coin intrinsic (PR5e
        refinement of the `option_delivery_fee_fraction` ceiling): `min(delivery rate,
        12.5% of the settlement value)`. An OTM option expires worthless
        (`intrinsic_fraction == 0`) and pays 0; an ITM option pays the capped rate.
        `intrinsic_fraction` is the coin settlement value `intrinsic_usd / S_T` (the same
        coin base as the premium, NOT divided by S0).

        Raises:
          CostModelError: when `intrinsic_fraction < 0`.
        """
        if intrinsic_fraction < 0.0:
            raise CostModelError(
                f"option_delivery_fee_on_intrinsic requires intrinsic_fraction >= 0; "
                f"got {intrinsic_fraction}"
            )
        capped = self.option_fee_premium_cap * intrinsic_fraction
        return min(self.option_delivery_bps / _BPS, capped)

    def margin_financing_fraction(self, hold_hours: float) -> float:
        """The opportunity cost of the posted option margin over the hold, in coin (a
        FLOOR): `funding_capital_rate * initial_margin_fraction * (hold_hours / 8760)`.

        This charges only the SHORT-OPTION initial margin; the delta-hedge perp's own
        margin financing is NOT added, so this is a lower bound on total financing (the
        hedge reduces portfolio margin under Deribit's cross/portfolio margining, but the
        hedge-leg financing is deferred). Reported as a floor, not a conservative charge.

        Raises:
          CostModelError: when `hold_hours < 0`.
        """
        if hold_hours < 0.0:
            raise CostModelError(
                f"margin_financing_fraction requires hold_hours >= 0; got {hold_hours}"
            )
        margin = self.initial_margin_fraction
        return self.funding_capital_rate * margin * (hold_hours / _HOURS_PER_YEAR)


DERIBIT_OPTION = DeribitOptionCostModel(
    name="deribit_option",
    # US retail cannot directly trade Deribit; the Coinbase Financial Markets path (CFTC-
    # cleared May 2026) is institutional-live / retail-coming-soon, so False today.
    tradeable=False,
    option_fee_bps=3.0,  # 0.03% of the underlying index (maker == taker for options)
    option_fee_premium_cap=0.125,  # the fee is capped at 12.5% of the option premium
    option_delivery_bps=1.5,  # 0.015% of the underlying (settlement), un-capped ceiling here
    option_spread_floor_bps=5.0,  # assumed conservative minimum option entry-spread cost
    # The delta hedge is modeled SAME-VENUE on the Deribit perpetual (the natural hedge
    # for a Deribit option). Maker rebate (0.025%) dropped to 0 (conservative).
    perp_taker_bps=5.0,
    perp_maker_bps=0.0,
    perp_half_spread_bps=_PERP_HALF_SPREAD_BPS,
    routing_fee_bps=0.0,
    initial_margin_fraction=0.15,  # assumed conservative short-option IM pin; PR5e refines
    source=(
        "Deribit BTC/ETH options (inverse, coin-settled): trading fee min(0.03% of the "
        "underlying index, 12.5% of premium), maker == taker (support.deribit.com Fees + "
        "insights.deribit.com); delivery fee 0.015% of underlying capped at 12.5% of value, "
        "daily options exempt (support.deribit.com Settlement). Delta-hedge leg on the "
        "Deribit perpetual: taker 0.05% / maker rebate 0.025% (modeled at 0). US retail "
        "access via Coinbase Financial Markets (CFTC-cleared May 2026, institutional-live / "
        "retail-coming-soon); routing_fee carried at 0 pending a published retail schedule. "
        "initial_margin_fraction is an assumed conservative pin of Deribit's SPAN-style "
        "short-option IM (PR5e refines per position). Verified 2026-06"
    ),
)
"""The canonical crypto options venue cost model (the only liquid BTC/ETH options book).
`tradeable=False` reflects current US-retail access; the kill gate reads the flag."""


TRADEABLE_VENUES: tuple[VenueCostModel, ...] = (KRAKEN, HYPERLIQUID)
"""The US-tradeable venues the kill gate is decided on."""

REFERENCE_VENUES: tuple[VenueCostModel, ...] = (BINANCE_REFERENCE, OKX_REFERENCE)
"""Non-tradeable reference venues for the cost-sensitivity surface."""

ALL_VENUES: tuple[VenueCostModel, ...] = TRADEABLE_VENUES + REFERENCE_VENUES
"""Every modeled venue, tradeable first, in a fixed deterministic order."""
