"""Loud-failure error type for the quality-tilt study (Study 10, ADR 0012)."""

from __future__ import annotations


class QualityError(RuntimeError):
    """A quality-tilt gate input or invariant was violated."""
