"""Errors for the BTC/ETH slow-trend study."""

from __future__ import annotations


class TrendError(ValueError):
    """Raised when the Study 4 trend gate sees invalid data or an invalid artifact."""
