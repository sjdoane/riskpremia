"""RiskPremia: a reproducible, intellectually-honest risk-premium measurement study.

Sibling to pit-backtest (the equity backtester whose recruiter-facing headline
was a reproducible honest momentum null). Lead track: crypto perpetual-futures
funding carry, delta-neutral, framed as a MEASUREMENT study. The honest question
is whether the carry survives exchange fees, the two-leg bid-ask spread, regime
gating, and the post-spot-ETF basis decay, measured on a genuinely US-tradeable
venue, not whether it harvests alpha.

The analytics + validation sub-packages are vendored (copied and attributed)
from pit-backtest because they are asset-agnostic; see each module header for
the provenance and the licence note.
"""

from __future__ import annotations

__version__ = "0.0.0"
