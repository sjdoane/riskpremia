"""The pydantic IO boundary (ADR 0002): the ONLY module that imports pydantic.

Per the pydantic-at-the-boundary / polars-in-the-hot-path contract, raw vendor
rows are validated once through small frozen pydantic models here and immediately
converted to the attrs `records.py` carriers; pydantic never touches the per-event
alignment loop. Isolating it to one file makes the boundary lint a one-line
allowlist (`tests/unit/test_pydantic_boundary_lint.py`).

Review-locked (docs/research/0001-data-layer-design.md, finding 12): the immutable
Binance Vision CSV uses `extra="forbid"` (its header is exact; any new column is
corruption to surface loudly), whereas the live OKX/Hyperliquid JSON models added
in PR3 will use `extra="ignore"` (they carry venue fields like `formulaType`/
`method` and a benign additive change must not crash the live tier).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict

from riskpremia.data.clock import ms_to_utc, us_to_utc
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.records import (
    DvolCurrency,
    DvolRecord,
    FundingRecord,
    InstrumentId,
    OptionQuoteRecord,
    OptionType,
)


class BinanceFundingRow(BaseModel):
    """One row of a Binance Vision monthly funding CSV.

    Verified schema (header exactly `[calc_time, funding_interval_hours,
    last_funding_rate]`): `calc_time` is epoch milliseconds, the interval is whole
    hours (8 for BTCUSDT), the rate is a signed decimal fraction. `extra="forbid"`
    because the dump is immutable history; a new column is corruption, not a
    benign addition.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    calc_time: int
    funding_interval_hours: int
    last_funding_rate: Decimal

    def to_record(self, instrument: InstrumentId) -> FundingRecord:
        """Convert to a settled FundingRecord (a committed dump is settled history).

        `realized=True` unconditionally (a monthly dump only contains closed
        periods) and `premium=None` (the Binance dump does not expose the
        separable premium component; the ADR notes the rate is the clamped
        composite cash flow, not the pure premium).
        """
        return FundingRecord(
            instrument=instrument,
            funding_ts=ms_to_utc(self.calc_time),
            funding_rate=self.last_funding_rate,
            funding_interval_hours=self.funding_interval_hours,
            realized=True,
            premium=None,
        )


BINANCE_FUNDING_HEADER: tuple[str, ...] = (
    "calc_time",
    "funding_interval_hours",
    "last_funding_rate",
)
"""The exact, verified Binance Vision funding CSV header. A parser asserts the
incoming header equals this tuple and raises `VenueFetchError` otherwise, so a
silent schema drift cannot be parsed as if it were the known shape."""


class PydanticOKXFundingRow(BaseModel):
    """One row of OKX /api/v5/public/funding-rate-history.

    extra="ignore" (NOT "forbid"): the live OKX JSON carries venue fields
    (instType, instId, formulaType, ...) this model does not need, and a benign
    additive vendor change must not crash the live tier (design review finding
    12). The leak-prevention discipline is structural: this is the SETTLED-history
    endpoint, the source never reads the predicted /funding-rate (current)
    endpoint, and to_record uses realizedRate (the paid rate), never the
    fundingRate (predicted) field.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    fundingTime: int
    realizedRate: Decimal | None = None
    fundingRate: Decimal | None = None
    method: str | None = None

    def to_record(
        self, instrument: InstrumentId, now_ms: int, interval_hours: int
    ) -> FundingRecord | None:
        """Convert a settled funding row to a record, or None if not realized.

        PIT realized gate (design review finding 1): require realizedRate present,
        method "current_period" (the settled marker observed on every history
        row), and the settlement instant strictly before now. Uses realizedRate as
        the funding_rate (the clamped composite cash flow); premium=None (the
        history endpoint exposes no separate premium component).
        """
        if (
            self.realizedRate is None
            or self.method != "current_period"
            or self.fundingTime >= now_ms
        ):
            return None
        return FundingRecord(
            instrument=instrument,
            funding_ts=ms_to_utc(self.fundingTime),
            funding_rate=self.realizedRate,
            funding_interval_hours=interval_hours,
            realized=True,
            premium=None,
        )


class PydanticDeribitDvolRow(BaseModel):
    """One row of Deribit `public/get_volatility_index_data` (the DVOL index).

    The endpoint returns each day as a 5-element ARRAY `[ts_ms, open, high, low,
    close]`, not a dict, so `from_array` does the shape check (loud
    `VenueFetchError`) and the float-to-Decimal conversion via `str` (avoiding
    float-repr noise) before this model validates the typed fields. `extra="forbid"`
    is moot for the kwargs path but states the intent. The DVOL values are
    annualized vol percentage points.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    @classmethod
    def from_array(cls, row: object) -> PydanticDeribitDvolRow:
        """Build from the raw `[ts_ms, open, high, low, close]` array, loud on shape."""
        if not isinstance(row, list | tuple) or len(row) != 5:
            raise VenueFetchError(
                f"Deribit DVOL row must be a 5-element [ts,o,h,l,c] array; got {row!r}"
            )
        ts, o, h, lo, c = row
        return cls(
            timestamp_ms=int(ts),
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(lo)),
            close=Decimal(str(c)),
        )

    def to_record(self, currency: DvolCurrency) -> DvolRecord:
        """Convert to a DvolRecord, raising on a non-positive or inconsistent OHLC."""
        for name, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            if value <= 0:
                raise VenueFetchError(f"Deribit DVOL {name} must be positive; got {value}")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise VenueFetchError(
                f"Deribit DVOL OHLC inconsistent: o={self.open} h={self.high} "
                f"l={self.low} c={self.close}"
            )
        return DvolRecord(
            currency=currency,
            ts=ms_to_utc(self.timestamp_ms),
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
        )


TARDIS_OPTIONS_HEADER: tuple[str, ...] = (
    "exchange", "symbol", "timestamp", "local_timestamp", "type", "strike_price",
    "expiration", "open_interest", "last_price", "bid_price", "bid_amount", "bid_iv",
    "ask_price", "ask_amount", "ask_iv", "mark_price", "mark_iv", "underlying_index",
    "underlying_price", "delta", "gamma", "vega", "theta", "rho",
)
"""The verified Tardis Deribit `options_chain` CSV header (24 columns). A parser
asserts the incoming header equals this before reading by index, so a silent schema
drift cannot be parsed as if it were the known shape."""

# Column indices into a TARDIS_OPTIONS_HEADER row (named for legibility at the parse).
_TI_SYMBOL, _TI_TS, _TI_TYPE, _TI_STRIKE, _TI_EXPIRY = 1, 2, 4, 5, 6
_TI_OI, _TI_BID, _TI_BIDAMT, _TI_BIDIV = 7, 9, 10, 11
_TI_ASK, _TI_ASKAMT, _TI_ASKIV, _TI_MARK, _TI_MARKIV = 12, 13, 14, 15, 16
_TI_UIDX, _TI_UPX, _TI_DELTA, _TI_GAMMA, _TI_VEGA = 17, 18, 19, 20, 21

_STRIKE_RATIO_LOW = Decimal("0.01")
_STRIKE_RATIO_HIGH = Decimal("100")


def _opt_decimal(raw: str) -> Decimal | None:
    """Empty -> None, else Decimal (the wide option CSV leaves quotes/greeks blank).

    Raises:
      VenueFetchError: when a non-empty field is not a valid number.
    """
    raw = raw.strip()
    if raw == "":
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise VenueFetchError(f"Tardis option field is not a number: {raw!r}") from exc


class PydanticTardisOptionRow(BaseModel):
    """One row of the Tardis Deribit `options_chain` CSV (ADR 0004 Layer ii).

    `extra="ignore"`: the file is a wide vendor CSV and only the load-bearing columns
    are declared. Built via `from_row` (index extraction + empty->None) so the empty
    quote/greek cells become None; `to_record` does the semantic validation (the
    put/call enum, positivity, the strike-vs-underlying sanity check, the
    microsecond->UTC conversion) and the `SYN.*` synthetic-underlying flag.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    symbol: str
    timestamp_us: int
    option_type_raw: str
    strike_price: Decimal
    expiration_us: int
    underlying_index: str
    underlying_price: Decimal
    open_interest: Decimal | None = None
    bid_price: Decimal | None = None
    bid_amount: Decimal | None = None
    bid_iv: Decimal | None = None
    ask_price: Decimal | None = None
    ask_amount: Decimal | None = None
    ask_iv: Decimal | None = None
    mark_price: Decimal | None = None
    mark_iv: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    vega: Decimal | None = None

    @classmethod
    def from_row(cls, values: list[str]) -> PydanticTardisOptionRow:
        """Build from a 24-field CSV row, loud on a wrong width or a malformed required
        field; the empty optional cells (no quote/greek) become None."""
        if len(values) != len(TARDIS_OPTIONS_HEADER):
            raise VenueFetchError(
                f"Tardis option row has {len(values)} fields, expected "
                f"{len(TARDIS_OPTIONS_HEADER)}"
            )

        def req_int(idx: int, field: str) -> int:
            try:
                return int(values[idx].strip())
            except ValueError as exc:
                raise VenueFetchError(
                    f"Tardis option {field} is not an int: {values[idx]!r}"
                ) from exc

        def req_dec(idx: int, field: str) -> Decimal:
            d = _opt_decimal(values[idx])
            if d is None:
                raise VenueFetchError(f"Tardis option {field} is required but empty")
            return d

        return cls(
            symbol=values[_TI_SYMBOL].strip(),
            timestamp_us=req_int(_TI_TS, "timestamp"),
            option_type_raw=values[_TI_TYPE].strip(),
            strike_price=req_dec(_TI_STRIKE, "strike_price"),
            expiration_us=req_int(_TI_EXPIRY, "expiration"),
            underlying_index=values[_TI_UIDX].strip(),
            underlying_price=req_dec(_TI_UPX, "underlying_price"),
            open_interest=_opt_decimal(values[_TI_OI]),
            bid_price=_opt_decimal(values[_TI_BID]),
            bid_amount=_opt_decimal(values[_TI_BIDAMT]),
            bid_iv=_opt_decimal(values[_TI_BIDIV]),
            ask_price=_opt_decimal(values[_TI_ASK]),
            ask_amount=_opt_decimal(values[_TI_ASKAMT]),
            ask_iv=_opt_decimal(values[_TI_ASKIV]),
            mark_price=_opt_decimal(values[_TI_MARK]),
            mark_iv=_opt_decimal(values[_TI_MARKIV]),
            delta=_opt_decimal(values[_TI_DELTA]),
            gamma=_opt_decimal(values[_TI_GAMMA]),
            vega=_opt_decimal(values[_TI_VEGA]),
        )

    def to_record(self, currency: DvolCurrency) -> OptionQuoteRecord:
        """Convert to an OptionQuoteRecord, raising on a bad type, non-positive
        strike/underlying, an implausible strike-vs-underlying ratio (a likely column
        misalignment), or a currency the symbol does not match."""
        if not self.symbol.startswith(f"{currency}-"):
            raise VenueFetchError(f"option {self.symbol!r} is not a {currency} instrument")
        if self.option_type_raw == "put":
            option_type: OptionType = "put"
        elif self.option_type_raw == "call":
            option_type = "call"
        else:
            raise VenueFetchError(
                f"Tardis option type must be put/call; got {self.option_type_raw!r}"
            )
        if self.strike_price <= 0:
            raise VenueFetchError(f"option strike must be positive; got {self.strike_price}")
        if self.underlying_price <= 0:
            raise VenueFetchError(
                f"option underlying_price must be positive; got {self.underlying_price}"
            )
        ratio = self.strike_price / self.underlying_price
        if not (_STRIKE_RATIO_LOW <= ratio <= _STRIKE_RATIO_HIGH):
            raise VenueFetchError(
                f"option strike {self.strike_price} implausible vs underlying "
                f"{self.underlying_price} (ratio {ratio}); likely a column misalignment"
            )
        return OptionQuoteRecord(
            currency=currency,
            instrument=self.symbol,
            option_type=option_type,
            strike=self.strike_price,
            expiry=us_to_utc(self.expiration_us),
            quote_ts=us_to_utc(self.timestamp_us),
            underlying_index=self.underlying_index,
            underlying_price=self.underlying_price,
            synthetic_underlying=self.underlying_index.startswith("SYN."),
            bid_price=self.bid_price,
            ask_price=self.ask_price,
            mark_price=self.mark_price,
            bid_amount=self.bid_amount,
            ask_amount=self.ask_amount,
            bid_iv=self.bid_iv,
            ask_iv=self.ask_iv,
            mark_iv=self.mark_iv,
            delta=self.delta,
            gamma=self.gamma,
            vega=self.vega,
            open_interest=self.open_interest,
        )
