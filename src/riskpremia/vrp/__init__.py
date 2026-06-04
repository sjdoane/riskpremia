"""The crypto variance-risk-premium (VRP) study (ADR 0004).

Layer i (this package, the reproducible measurement floor): the BTC/ETH variance
risk premium = Deribit DVOL implied variance minus matched-horizon realized variance
from the Binance Vision klines, with its regime decomposition and overlap-honest
inference. Kept separate from the carry's `execution/` + `strategy/` packages
because the measurement object is distinct (ADR 0004 caveat 2); it reuses the
vendored `analytics`/`validation` stack and the data layer verbatim.

Layer ii (the cost-gated short-variance tradeable test) is a later milestone and is
deliberately NOT in this package yet.
"""

from __future__ import annotations
