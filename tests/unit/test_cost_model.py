"""VenueCostModel: the round-trip algebra, the maker/taker asymmetry, the
financing 2N base, the provisional flag, and the loud-failure validation (ADR 0003)."""

from __future__ import annotations

import math

import pytest

from riskpremia.execution.cost import (
    ALL_VENUES,
    BINANCE_REFERENCE,
    HYPERLIQUID,
    KRAKEN,
    OKX_REFERENCE,
    REFERENCE_VENUES,
    TRADEABLE_VENUES,
    VenueCostModel,
)
from riskpremia.execution.errors import CostModelError


def _model(**overrides: object) -> VenueCostModel:
    base: dict[str, object] = dict(
        name="unit",
        tradeable=True,
        spot_taker_bps=26.0,
        spot_maker_bps=16.0,
        perp_taker_bps=5.0,
        perp_maker_bps=2.0,
        spot_half_spread_bps=2.0,
        perp_half_spread_bps=1.5,
        source="unit-test",
    )
    base.update(overrides)
    return VenueCostModel(**base)  # type: ignore[arg-type]


def test_round_trip_is_both_legs_both_sides_taker() -> None:
    m = _model()
    # Two full spreads + four fee legs: 2*(spot_fee+spot_hs) + 2*(perp_fee+perp_hs), in fractions.
    expected = (2 * (26.0 + 2.0) + 2 * (5.0 + 1.5)) / 10_000.0
    assert math.isclose(m.round_trip_cost_fraction(), expected, abs_tol=1e-15)
    # round_trip == entry + exit (the field algebra the per-interval decomposition relies on).
    assert math.isclose(
        m.round_trip_cost_fraction(),
        m.entry_cost_fraction() + m.exit_cost_fraction(),
        abs_tol=1e-15,
    )


def test_maker_taker_asymmetry() -> None:
    m = _model()
    # Maker-in / taker-out: entry uses maker fees, exit uses taker fees.
    entry = (16.0 + 2.0 + 2.0 + 1.5) / 10_000.0  # spot_maker + perp_maker + spreads
    exit_ = (26.0 + 2.0 + 5.0 + 1.5) / 10_000.0  # spot_taker + perp_taker + spreads
    assert math.isclose(
        m.round_trip_cost_fraction(entry_taker=False, exit_taker=True),
        entry + exit_,
        abs_tol=1e-15,
    )
    # Maker both sides is strictly cheaper than taker both sides.
    maker_both = m.round_trip_cost_fraction(entry_taker=False, exit_taker=False)
    assert maker_both < m.round_trip_cost_fraction()


def test_financing_carries_the_2N_capital_base() -> None:
    m = _model(funding_capital_rate=0.04, capital_multiple=2.0)
    one_n = _model(funding_capital_rate=0.04, capital_multiple=1.0)
    hold = 24.0  # hours
    expected = 0.04 * 2.0 * (24.0 / 8760.0)
    assert math.isclose(m.financing_cost_fraction(hold_hours=hold), expected, abs_tol=1e-18)
    # The 2N base is exactly twice the 1N drag (the conservative, no-cross-margin charge).
    assert math.isclose(
        m.financing_cost_fraction(hold_hours=hold),
        2.0 * one_n.financing_cost_fraction(hold_hours=hold),
        abs_tol=1e-18,
    )
    # Linear in the hold, zero at a zero rate, zero at a zero hold.
    assert math.isclose(
        m.financing_cost_fraction(hold_hours=48.0),
        2.0 * m.financing_cost_fraction(hold_hours=24.0),
        abs_tol=1e-18,
    )
    assert _model(funding_capital_rate=0.0).financing_cost_fraction(hold_hours=100.0) == 0.0
    assert m.financing_cost_fraction(hold_hours=0.0) == 0.0


def test_financing_rejects_negative_hold() -> None:
    with pytest.raises(CostModelError, match="hold_hours"):
        _model().financing_cost_fraction(hold_hours=-1.0)


def test_provisional_flag_tracks_spread_basis() -> None:
    assert _model(spread_basis="assumed").provisional is True
    assert _model(spread_basis="measured").provisional is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("spot_taker_bps", -1.0),
        ("perp_maker_bps", -0.1),
        ("spot_half_spread_bps", -2.0),
        ("funding_capital_rate", -0.01),
        ("capital_multiple", -1.0),
    ],
)
def test_negative_inputs_raise(field: str, value: float) -> None:
    with pytest.raises(CostModelError):
        _model(**{field: value})


def test_empty_name_or_source_raises() -> None:
    with pytest.raises(CostModelError, match="name"):
        _model(name="  ")
    with pytest.raises(CostModelError, match="source"):
        _model(source="")


def test_cited_venue_registry() -> None:
    # The tradeable venues are the ones the kill gate is decided on.
    assert KRAKEN.tradeable and HYPERLIQUID.tradeable
    assert not BINANCE_REFERENCE.tradeable and not OKX_REFERENCE.tradeable
    assert TRADEABLE_VENUES == (KRAKEN, HYPERLIQUID)
    assert REFERENCE_VENUES == (BINANCE_REFERENCE, OKX_REFERENCE)
    assert ALL_VENUES == TRADEABLE_VENUES + REFERENCE_VENUES
    # Every shipped venue carries a non-empty citation and is provisional (assumed spread).
    for v in ALL_VENUES:
        assert v.source.strip()
        assert v.provisional
    # The US-tradeable venues cost MORE round-trip than the (lower-fee) reference venues,
    # which is the whole point of the venue-cost-sensitivity surface.
    assert KRAKEN.round_trip_cost_fraction() > BINANCE_REFERENCE.round_trip_cost_fraction()
