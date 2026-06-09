"""Errors for the live deployment package."""

from __future__ import annotations


class LiveError(RuntimeError):
    """A live-deployment precondition was violated (bad input, too little history, bad state)."""
