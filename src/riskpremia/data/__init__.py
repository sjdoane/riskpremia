"""Data layer for the crypto funding-carry study (built new, not vendored).

Multi-venue by design (per the week-1 spike + ADR 0001): the live Binance and
Bybit REST APIs are geo-blocked from a US IP, so the long-history reproducible
source is the Binance Vision S3 dumps (checksummed monthly funding/kline zips,
fetched with the stdlib), and the US-reachable live sources for a forward
paper-trade are OKX (realized funding + candles) and Hyperliquid (on-chain).
Raw snapshots are SHA256-stamped so a reviewer can verify byte-identical inputs.
"""

from __future__ import annotations
