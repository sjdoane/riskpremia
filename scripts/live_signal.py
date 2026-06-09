"""Print this month's Study 6 target allocation from the committed levels (no network, no state).

Reads the month-end levels file (defaulting to the committed seed) and prints the frozen-rule signal
and target weights. Read-only: it changes nothing and places nothing. Use it to see the current
long-or-cash decision before running the paper rebalance.
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.live.levels import read_levels, sleeve_levels
from riskpremia.live.signal import target_from_levels

_REPO = Path(__file__).resolve().parents[1]
_SEED = _REPO / "tests" / "data" / "live_levels_seed.csv"
_LIVE = _REPO / "live_state" / "levels.csv"


def main() -> None:
    path = _LIVE if _LIVE.exists() else _SEED
    rows = read_levels(path)
    target = target_from_levels(sleeve_levels(rows), rows[-1].date)
    print(f"Study 6 signal from {path.relative_to(_REPO).as_posix()} as of {target.as_of}")
    for s in target.sleeves:
        state = "ABOVE its average, HOLD" if s.active else "below its average, to cash"
        print(f"  {s.sleeve:6s} ({s.symbol}): {s.level:.4f} vs 10mo avg {s.sma:.4f} -> {state}")
    print("  target weights: " + ", ".join(f"{sym} {w:.0%}" for sym, w in target.weights.items()))
    print(f"  {target.n_active} of {len(target.sleeves)} sleeves invested")


if __name__ == "__main__":
    main()
