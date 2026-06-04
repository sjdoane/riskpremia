"""Loud-failure exception hierarchy for the execution + cost layer (ADR 0003).

Mirrors `data/errors.py`: every domain violation raises with the offending value
in the message rather than returning a NaN or silently producing a degenerate
trade. A silent error here would poison the net-of-cost series the kill gate
reads, so the discipline is the same as the data layer's. All are `ValueError`
subclasses so a caller can catch the family or a specific kind.
"""

from __future__ import annotations


class ExecutionError(ValueError):
    """Base class for every execution / cost-model domain violation."""


class CostModelError(ExecutionError):
    """A venue cost model was constructed with an invalid fee schedule.

    Raised on a negative fee or spread, a negative financing rate or capital
    multiple, or an empty venue name or citation source (the cited-fee-schedule
    discipline: a cost number with no provenance must not silently enter the kill
    gate).
    """


class CarryComputationError(ExecutionError):
    """A single-trade or batch carry computation could not be performed correctly.

    Raised on an out-of-range entry index (the forward funding window or the exit
    price would not exist), a non-positive horizon, a missing required column, or
    a null price at the entry or exit event (a data gap must surface loudly, not
    silently produce a garbage delta-neutral return).
    """


class ScoringError(ExecutionError):
    """A deflated-Sharpe / null-gate scoring step could not be performed correctly.

    Raised on a degenerate return series (fewer than two observations or a zero
    standard deviation, where the Sharpe and the moments are undefined), or on a
    CPCV embargo that cannot be made to cover the holding horizon. A NaN-returning
    scorer would silently produce a meaningless kill number, so these raise.
    """


class OptionPnLError(ExecutionError):
    """A per-trade short-variance option P&L could not be computed correctly (PR5e).

    Raised on a non-positive entry or terminal underlying (the inverse settlement and
    the hedge divide by the settlement price), a negative hold, an untradeable quote
    (no bid/mark/delta), an out-of-domain delta, or a P&L conservation-invariant
    violation. A NaN-returning P&L would silently poison the tail-loss table the kill
    gate reads, so these raise loudly.
    """
