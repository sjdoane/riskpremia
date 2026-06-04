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

TRADEABLE_VENUES: tuple[VenueCostModel, ...] = (KRAKEN, HYPERLIQUID)
"""The US-tradeable venues the kill gate is decided on."""

REFERENCE_VENUES: tuple[VenueCostModel, ...] = (BINANCE_REFERENCE, OKX_REFERENCE)
"""Non-tradeable reference venues for the cost-sensitivity surface."""

ALL_VENUES: tuple[VenueCostModel, ...] = TRADEABLE_VENUES + REFERENCE_VENUES
"""Every modeled venue, tradeable first, in a fixed deterministic order."""
