"""Loud-failure error type for the industry-trend study (Study 9, ADR 0011)."""

from __future__ import annotations


class IndTrendError(RuntimeError):
    """An industry-trend gate input or invariant was violated."""
