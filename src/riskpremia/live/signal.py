"""The live monthly target allocation, computed by the FROZEN backtest rule.

The active/inactive decision for each sleeve comes from `signal_from_monthly_levels`, the exact
function the gated backtest uses, so the deployed signal cannot drift from what was tested. The
weighting (one over the number of sleeves per active sleeve, the rest in the cash proxy) is the
weighting in the backtest simulator. This module adds no new rule logic; it only adapts the frozen
rule to observed month-end proxy levels and emits a target allocation plus the context to journal.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from datetime import date

import attrs

from riskpremia.live.errors import LiveError
from riskpremia.xtrend.gate import SLEEVES, XTrendKnobs, signal_from_monthly_levels

# The faithful deployable proxies for the backtest sleeves (ADR 0008, the deployment runbook). The
# bond sleeve is the ten-year maturity, so IEF (7-10yr) is the match, not the 20yr-plus TLT.
SLEEVE_SYMBOLS: Mapping[str, str] = {"equity": "VTI", "bond": "IEF"}
CASH_SYMBOL = "SGOV"
PER_ACTIVE_WEIGHT = 1.0 / len(SLEEVES)


@attrs.frozen(slots=True)
class SleeveSignal:
    """One sleeve's month-end reading: its level, its moving average, and the resulting flag."""

    sleeve: str
    symbol: str
    level: float
    sma: float
    active: bool


@attrs.frozen(slots=True)
class TargetAllocation:
    """The target the next month should hold: per-symbol weights and the per-sleeve context."""

    as_of: str
    sleeves: tuple[SleeveSignal, ...]
    weights: Mapping[str, float]
    n_active: int

    def weight(self, symbol: str) -> float:
        return self.weights.get(symbol, 0.0)

    def sleeve_active(self, sleeve: str) -> bool:
        for s in self.sleeves:
            if s.sleeve == sleeve:
                return s.active
        raise LiveError(f"unknown sleeve {sleeve!r}")


def target_from_levels(
    sleeve_levels: Mapping[str, Sequence[float]],
    as_of: date,
    knobs: XTrendKnobs | None = None,
) -> TargetAllocation:
    """Build the target allocation from each sleeve's month-end level series.

    `sleeve_levels` maps each sleeve name to its full month-end level history (oldest first). The
    active flag at the latest month is taken straight from the frozen rule; the moving average is
    recomputed identically for display and journaling.
    """
    k = knobs if knobs is not None else XTrendKnobs()
    sleeves: list[SleeveSignal] = []
    weights: dict[str, float] = {}
    n_active = 0
    active_weight_total = 0.0
    for sleeve in SLEEVES:
        if sleeve not in sleeve_levels:
            raise LiveError(f"missing levels for sleeve {sleeve!r}")
        levels = list(sleeve_levels[sleeve])
        if len(levels) < k.sma_months:
            raise LiveError(
                f"sleeve {sleeve!r} needs {k.sma_months} month-end levels, got {len(levels)}"
            )
        m_last = len(levels) - 1
        active = signal_from_monthly_levels(levels, k.sma_months)[m_last]
        sma = statistics.fmean(levels[m_last - k.sma_months + 1 : m_last + 1])
        symbol = SLEEVE_SYMBOLS[sleeve]
        sleeves.append(SleeveSignal(sleeve, symbol, levels[m_last], sma, active))
        w = PER_ACTIVE_WEIGHT if active else 0.0
        weights[symbol] = w
        active_weight_total += w
        if active:
            n_active += 1
    weights[CASH_SYMBOL] = 1.0 - active_weight_total
    return TargetAllocation(
        as_of=as_of.isoformat(), sleeves=tuple(sleeves), weights=weights, n_active=n_active
    )
