"""Run one month's paper rebalance of the Study 6 rule (no network, no broker, no real money).

Once a month, after appending the new month-end levels (scripts.build_live_levels or by hand), run
this to mark the simulated account at the latest month-end prices, rebalance to the frozen-rule
target with the backtest's turnover cost, append a journal row, and save the state. The account
starts fresh now; the levels history only feeds the ten-month signal window, so this is forward
paper trading, not a replay of the backtest. State lives under live_state/ (gitignored).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from riskpremia.live.journal import append_row, row_from
from riskpremia.live.levels import prices_at, read_levels, sleeve_levels
from riskpremia.live.paper import load_account, new_account, rebalance, save_account
from riskpremia.live.signal import SLEEVE_SYMBOLS, target_from_levels
from riskpremia.xtrend.gate import XTrendKnobs

_REPO = Path(__file__).resolve().parents[1]
_SEED = _REPO / "tests" / "data" / "live_levels_seed.csv"
_STATE = _REPO / "live_state"
_LEVELS = _STATE / "levels.csv"
_ACCOUNT = _STATE / "account.json"
_JOURNAL = _STATE / "journal.csv"

# The notional paper capital, used only to seed the account on the very first run.
STARTING_CASH = 10_000.0
_CHARGED = (SLEEVE_SYMBOLS["equity"], SLEEVE_SYMBOLS["bond"])


def main() -> None:
    _STATE.mkdir(parents=True, exist_ok=True)
    if not _LEVELS.exists():
        shutil.copyfile(_SEED, _LEVELS)
        print(f"Initialized {_LEVELS.relative_to(_REPO).as_posix()} from the committed seed")
    rows = read_levels(_LEVELS)
    latest = rows[-1]

    account = load_account(_ACCOUNT) if _ACCOUNT.exists() else new_account(STARTING_CASH)
    if account.as_of == latest.date.isoformat():
        print(f"Already rebalanced for {latest.date}; append a new month and rerun. No change.")
        return

    knobs = XTrendKnobs()
    target = target_from_levels(sleeve_levels(rows), latest.date, knobs)
    prices = prices_at(rows, len(rows) - 1)
    result = rebalance(
        account, target.weights, prices, latest.date,
        turnover_cost_per_side=knobs.turnover_cost_per_side, charged_symbols=_CHARGED,
    )
    save_account(_ACCOUNT, result.account)
    append_row(_JOURNAL, row_from(target, result))

    print(f"Paper rebalance for month-end {latest.date}")
    for s in target.sleeves:
        flag = "HOLD" if s.active else "to cash"
        print(f"  {s.sleeve:6s} ({s.symbol}): {s.level:.4f} vs {s.sma:.4f} -> {flag}")
    print("  target: " + ", ".join(f"{sym} {w:.0%}" for sym, w in target.weights.items()))
    print(f"  value {result.value_before:,.2f} -> {result.value_after:,.2f} "
          f"(turnover {result.turnover:.2f}, cost {result.cost_paid:,.2f})")
    for f in result.fills:
        print(f"    {f.side:4s} {f.shares:.4f} {f.symbol} @ {f.price:.4f} ({f.notional:,.2f})")
    print(f"  journal -> {_JOURNAL.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
