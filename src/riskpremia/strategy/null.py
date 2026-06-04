"""Entry-selection policies for the random-entry NULL (ADR 0003 PR4b).

A "null" here is the absence of selection skill: a delta-neutral carry that enters
on a fixed or random schedule rather than on any funding/regime signal. If the
carry is not clearly better than a null after realistic costs, there is no edge to
build a signal on (rule 6, the inverted build order). No signal logic lives here;
this module only chooses WHICH funding events are trade entries, and every policy
draws from `valid_entry_range` (the single source of truth) so it can never emit an
entry the simulator would reject.

The three nulls (ADR 0003 amendment B2, B3):
- always-on: every eligible event is an entry (overlapping holds). Drives the early
  economic gate, the funding-sign-regime decomposition, and the contamination check.
- non-overlapping: entries strided by H (genuinely independent closed trades). The
  HEADLINE DSR series; reported across all H phases so no lucky offset is cherry-picked.
- random subset: a seeded random.Random draw from the valid range, a schedule-
  robustness control (the kill must not depend on the entry schedule).
"""

from __future__ import annotations

import random

from riskpremia.execution.carry import valid_entry_range
from riskpremia.execution.errors import CarryComputationError


def always_on_entries(height: int, horizon_events: int) -> range:
    """Every eligible funding event is an entry: `range(0, height-H)` (ADR B3).

    The always-on passive carry, the headline null the early economic gate is
    literally about. Its holds overlap (entry i and i+1 share H-1 intervals), so it
    is NOT used for the DSR T (see `non_overlapping_entries`)."""
    return valid_entry_range(height, horizon_events)


def non_overlapping_entries(height: int, horizon_events: int, *, phase: int = 0) -> range:
    """Entries strided by H from `phase`: genuinely independent closed trades.

    The headline DSR series (ADR B2): consecutive entries share no funding interval,
    so `T = len(...)` is the honest independent-trade count. `phase` in `[0, H)`
    selects the strided offset; the gate reports the DSR across all H phases so the
    headline is not one lucky offset (design review M3).

    Raises:
      CarryComputationError: when `phase` is outside `[0, horizon_events)`.
    """
    if not (0 <= phase < horizon_events):
        raise CarryComputationError(
            f"non_overlapping_entries requires 0 <= phase < horizon_events; got "
            f"phase={phase}, horizon_events={horizon_events}"
        )
    valid = valid_entry_range(height, horizon_events)
    # Stride by H starting at `phase`, staying within the valid range.
    return range(phase, valid.stop, horizon_events)


def non_overlapping_phase_count(horizon_events: int) -> int:
    """The number of distinct strided phases (= H), for the phase-robustness band."""
    if horizon_events < 1:
        raise CarryComputationError(
            f"non_overlapping_phase_count requires horizon_events >= 1; got {horizon_events}"
        )
    return horizon_events


def random_subset_entries(
    height: int, horizon_events: int, *, count: int, seed: int
) -> list[int]:
    """A seeded random subset of `count` valid entries, sorted ascending.

    A schedule-robustness control: random entry timing should give the same kill as
    the fixed schedules (the kill must not depend on the schedule). Drawn without
    replacement from `valid_entry_range` with a seeded `random.Random` (the only
    randomness in the gate; determinism rule 8), then sorted so the downstream order
    is deterministic. The count is matched to the non-overlapping headline's trade
    count by the caller until a real signal exists to match (ADR B2, design review L3).

    Raises:
      CarryComputationError: on a non-int (or bool) seed, a non-positive count, or a
        count exceeding the number of valid entries (an over-draw).
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise CarryComputationError(
            f"random_subset_entries requires an int seed; got {type(seed).__name__}"
        )
    valid = valid_entry_range(height, horizon_events)
    if count < 1:
        raise CarryComputationError(f"random_subset_entries requires count >= 1; got {count}")
    if count > len(valid):
        raise CarryComputationError(
            f"random_subset_entries count={count} exceeds the {len(valid)} valid entries "
            f"for height={height}, horizon_events={horizon_events}"
        )
    rng = random.Random(seed)
    return sorted(rng.sample(range(valid.start, valid.stop), count))
