"""Loud-failure exceptions for the CTREND study (ADR 0005).

Same discipline as `data/errors.py`, `execution/errors.py`, and `vrp/errors.py`: a domain
violation raises with the offending value rather than silently producing a wrong universe
or panel. A `ValueError` subclass so callers can catch the family.
"""

from __future__ import annotations


class CtrendError(ValueError):
    """A CTREND universe / panel computation could not be performed correctly.

    Raised on an empty or unsorted panel, a duplicate (date, symbol) row, a non-positive
    price or negative volume, an out-of-range knob (top_n, lookback, min_history), or a
    losslessness / reconciliation invariant violation in the universe build.
    """
