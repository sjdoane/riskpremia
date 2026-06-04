"""Loud-failure exceptions for the variance-risk-premium study (ADR 0004).

Same discipline as `data/errors.py` and `execution/errors.py`: a domain violation
raises with the offending value rather than silently producing a wrong premium. A
`ValueError` subclass so callers can catch the family.
"""

from __future__ import annotations


class VrpError(ValueError):
    """A variance-risk-premium computation could not be performed correctly.

    Raised on a non-contiguous daily calendar (a gap the realized-variance window
    would silently span), a frame too short for the matched horizon, a missing
    required column, or an empty alignment between the implied and realized legs.
    """
