"""Venue data sources (ADR 0002).

Each source fetches and parses one venue's raw data into the typed records of
`riskpremia.data.records`; the `clock` module normalizes those records into the
CPCV-ready frames. PR2 ships `BinanceVisionSource` (the long-history reproducible
backbone); the live OKX source lands in PR3.
"""

from __future__ import annotations
