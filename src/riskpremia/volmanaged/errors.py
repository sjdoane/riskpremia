"""Loud-failure error type for the volatility-managed market study (Study 8, ADR 0010)."""

from __future__ import annotations


class VolManagedError(RuntimeError):
    """A volatility-managed gate input or invariant was violated."""
