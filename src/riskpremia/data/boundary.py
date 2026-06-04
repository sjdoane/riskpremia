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

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from riskpremia.data.clock import ms_to_utc
from riskpremia.data.records import FundingRecord, InstrumentId


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
