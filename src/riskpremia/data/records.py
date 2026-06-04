"""Typed inner-loop records for the funding-carry data layer (ADR 0002).

`@attrs.frozen(slots=True)` carriers, no pydantic (that lives only in
`boundary.py`, enforced by the boundary lint). Decimal for the funding rate and
prices: funding rates are tiny signed fractions summed thousands of times, so the
boundary stays exact and the single documented cast to Float64 happens later in
the polars frame (see `clock.py`). Mirrors the pit-backtest `data/records.py`
precedent.

Review-locked field choices (docs/research/0001-data-layer-design.md): the
funding `premium` component is carried where a venue exposes it (Binance Vision
does not, Hyperliquid does) so the clamped-composite-vs-pure-premium distinction
is preserved; the perp leg carries the MARK price (funding settles on mark/index,
not trade price); the spot leg carries an explicit `quote` so the basis is a
matched-product computation, never a cross-quote artifact.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

import attrs

from riskpremia.data.errors import VenueFetchError

Venue = Literal["binance_vision", "okx", "hyperliquid", "deribit"]
"""The data-source venues. A `Literal` (not an `Enum`) so it round-trips to
TOML/JSON cleanly and stays grep-able. `deribit` is the implied-vol-index source
(DVOL) for the variance-risk-premium study (ADR 0004)."""


def derive_canonical(symbol: str) -> str:
    """Map a venue-native perp symbol to its canonical asset key (the join key).

    `BTCUSDT` (Binance), `BTC-USDT-SWAP` (OKX), and `BTC` (Hyperliquid) are the
    same economic instrument; the canonical key (`"BTC"`) is what cross-venue
    joins and the basis leg key off, never the venue's string. Handles the three
    known venue conventions deterministically and raises loudly on an unparseable
    symbol rather than guessing (the loud-failure discipline).

    Raises:
      VenueFetchError: when `symbol` matches none of the known conventions.
    """
    s = symbol.strip().upper()
    if not s:
        raise VenueFetchError("derive_canonical requires a non-empty symbol")
    # OKX style: BASE-QUOTE-SWAP (take the base).
    if "-" in s:
        base = s.split("-", 1)[0]
        if base:
            return base
        raise VenueFetchError(f"derive_canonical cannot parse OKX-style symbol {symbol!r}")
    # Binance style: BASE + stable-quote suffix. Ordered longest-first so the
    # most specific quote wins: BTCBUSD must strip BUSD (-> BTC), not USD (which
    # would wrongly yield BTCB and silently mis-key the cross-venue join).
    for quote in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(quote) and len(s) > len(quote):
            return s[: -len(quote)]
    # Hyperliquid style: bare base coin.
    if s.isalpha():
        return s
    raise VenueFetchError(
        f"derive_canonical cannot parse symbol {symbol!r}; expected a venue-native "
        f"perp symbol (BTCUSDT, BTC-USDT-SWAP, or BTC)"
    )


@attrs.frozen(slots=True)
class InstrumentId:
    """A perpetual instrument identity, canonicalized for cross-venue joins.

    `canonical` is the venue-independent asset key (e.g. `"BTC"`); construct via
    `InstrumentId.of(...)` to derive it from the venue symbol, or pass it
    explicitly when the source already knows the mapping.
    """

    venue: Venue
    symbol: str
    canonical: str

    @classmethod
    def of(cls, venue: Venue, symbol: str, canonical: str | None = None) -> InstrumentId:
        """Build an InstrumentId, deriving `canonical` from `symbol` if omitted."""
        return cls(
            venue=venue,
            symbol=symbol,
            canonical=canonical if canonical is not None else derive_canonical(symbol),
        )


@attrs.frozen(slots=True)
class FundingRecord:
    """One realized funding event on an instrument's native funding clock.

    `funding_ts` is tz-aware UTC (the settlement instant). `funding_rate` is the
    realized decimal fraction PAID over the interval (the clamped interest +
    premium composite cash flow, NOT the pure premium; see the ADR). `premium` is
    the separable premium component where the venue exposes it, else None.
    `realized` is True only when the period has settled at or before fetch time;
    a committed monthly dump is settled history (always True), a live row carries
    the venue's settled marker.
    """

    instrument: InstrumentId
    funding_ts: datetime
    funding_rate: Decimal
    funding_interval_hours: int
    realized: bool
    premium: Decimal | None = None


@attrs.frozen(slots=True)
class MarkPriceRecord:
    """A perp MARK price at a kline close (funding settles on mark/index)."""

    instrument: InstrumentId
    period_end_ts: datetime
    mark_close: Decimal


@attrs.frozen(slots=True)
class SpotPriceRecord:
    """A spot reference close for the delta-neutral leg and the basis.

    Carries the explicit `(spot_venue, spot_symbol, quote)` of the spot product
    so the basis is computed against a matched-quote product, never a cross-quote
    artifact (a USDT-margined perp must be paired with a USDT-quoted spot).
    """

    spot_venue: str
    spot_symbol: str
    quote: str
    period_end_ts: datetime
    close: Decimal


DvolCurrency = Literal["BTC", "ETH"]
"""The currencies Deribit publishes a DVOL implied-vol index for."""


@attrs.frozen(slots=True)
class DvolRecord:
    """One day of the Deribit DVOL implied-volatility index (ADR 0004).

    `close` is the daily DVOL value in ANNUALIZED VOLATILITY PERCENTAGE POINTS
    (e.g. 34.44 means a 34.44% annualized implied vol, annualized on a 365-day
    basis, model-free / variance-swap methodology). The OHLC is carried for
    completeness; the measurement uses the close. The series is LIVE / as-of (not
    immutable like the Binance Vision dumps), so reproducibility rests on a
    SHA256-stamped snapshot, not on the API being stable.
    """

    currency: DvolCurrency
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
