"""Data layer for the crypto funding-carry study (built new, not vendored).

Multi-venue by design (per the week-1 spike + ADR 0001/0002): the live Binance and
Bybit REST APIs are geo-blocked from a US IP, so the long-history reproducible
source is the Binance Vision S3 dumps (checksummed monthly funding/kline zips,
fetched with the stdlib), and the US-reachable live sources for a forward
paper-trade are OKX (realized funding + candles) and Hyperliquid (on-chain).
Raw snapshots are SHA256-stamped so a reviewer can verify byte-identical inputs.

PR1 ships the typed core (records, the pydantic IO boundary, the funding-event
clock + CPCV-ready frame, the SHA256 manifest); the venue fetchers land in PR2/PR3.
"""

from __future__ import annotations

from riskpremia.data.clock import (
    SPOT_ETF_LAUNCH,
    build_observation_frame,
    make_label_horizons,
    ms_to_utc,
    normalize_funding_frame,
)
from riskpremia.data.errors import (
    ChecksumMismatchError,
    DataLayerError,
    FundingIntervalError,
    RetentionDepthError,
    SnapshotMismatchError,
    VenueFetchError,
)
from riskpremia.data.manifest import (
    SnapshotEntry,
    compute_sha256,
    load_manifest,
    parse_checksum_line,
    upsert_entries,
    verify_sha256,
    verify_snapshot,
)
from riskpremia.data.records import (
    FundingRecord,
    InstrumentId,
    MarkPriceRecord,
    SpotPriceRecord,
    Venue,
    derive_canonical,
)

__all__ = [
    "SPOT_ETF_LAUNCH",
    "ChecksumMismatchError",
    "DataLayerError",
    "FundingIntervalError",
    "FundingRecord",
    "InstrumentId",
    "MarkPriceRecord",
    "RetentionDepthError",
    "SnapshotEntry",
    "SnapshotMismatchError",
    "SpotPriceRecord",
    "Venue",
    "VenueFetchError",
    "build_observation_frame",
    "compute_sha256",
    "derive_canonical",
    "load_manifest",
    "make_label_horizons",
    "ms_to_utc",
    "normalize_funding_frame",
    "parse_checksum_line",
    "upsert_entries",
    "verify_sha256",
    "verify_snapshot",
]
