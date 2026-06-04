"""Loud-failure exception hierarchy for the data layer (ADR 0002).

Every domain violation raises with the offending value in the message, the
discipline inherited from pit-backtest (a NaN/silent-skip anti-pattern would
propagate into the funding series and poison the kill gate). All are
`ValueError` subclasses so a caller can catch the family or a specific kind.
"""

from __future__ import annotations


class DataLayerError(ValueError):
    """Base class for every data-layer domain violation."""


class VenueFetchError(DataLayerError):
    """A venue response or file did not match its expected shape or schema.

    Used for an unexpected CSV header, an out-of-range epoch, a dedup conflict
    between two settled rows at the same funding stamp, or a canonical-symbol
    that cannot be parsed.
    """


class ChecksumMismatchError(DataLayerError):
    """A downloaded file's SHA256 did not match the published or recorded hash."""


class FundingIntervalError(DataLayerError):
    """The funding interval is null or grossly inconsistent with the observed gap.

    Raised when `funding_interval_hours` is missing, or when the empirical modal
    gap between consecutive funding stamps differs from the stamped interval by
    an order of magnitude (a venue/interval mislabel, e.g. a 1h series stamped
    8h). A small in-band mismatch is a recorded diagnostic, not an error, because
    Binance early history is genuinely irregular (about 3 per day, not a clean
    8h grid).
    """


class SnapshotMismatchError(DataLayerError):
    """An on-disk raw snapshot's SHA256 or size drifted from the manifest entry."""


class RetentionDepthError(DataLayerError):
    """A requested window is not fully covered by the available data tiers.

    Guards the kill-gate invariant that the held-out post-spot-ETF window is
    covered by the live tier and the pre-ETF baseline by the long-history
    backbone, so the study never silently runs on a one-sided short series.
    """
