"""Loud-failure errors for the Study 6 cross-asset trend gate."""

from __future__ import annotations


class XTrendError(Exception):
    """A cross-asset trend construction or scoring failure."""
