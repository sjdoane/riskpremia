"""Asset-agnostic performance analytics, vendored from pit-backtest.

PSR / Deflated Sharpe / MinTRL (`sharpe.py`) and the stationary block bootstrap
with the Politis-White automatic block length (`bootstrap.py`) are copied
verbatim (modulo import paths and this header) from the sibling pit-backtest
project, which holds the authoritative tests. They are stdlib-only and carry no
equity-specific assumptions, so they apply unchanged to the crypto-carry return
series. See each module's header for provenance.
"""

from __future__ import annotations
