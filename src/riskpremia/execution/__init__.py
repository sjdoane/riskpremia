"""Execution + cost model for the delta-neutral two-leg carry (built new).

Per rule 6 and ADR 0001, the cost model is built FIRST and a random-entry NULL
strategy is run through it before any selection logic. The model charges both
legs (spot + perpetual): exchange taker/maker fees, the half-to-full bid-ask
spread on entry AND exit, and the funding actually paid/received on the
8h funding clock. Critically (per the design review), the cost model is
parameterised to a genuinely US-tradeable venue, not the Binance-data venue, so
the kill gate is run against costs that can actually be incurred.
"""

from __future__ import annotations
