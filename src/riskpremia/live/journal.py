"""The monthly journal: one appended row per rebalance, the live audit trail.

Every monthly run appends one row with the two sleeve readings (level, moving average, flag), the
target weights, and the paper account marks. This is the out-of-sample track record and the input
to the deployment kill criterion (a sustained drawdown breach).
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

import attrs

from riskpremia.live.errors import LiveError
from riskpremia.live.paper import RebalanceResult
from riskpremia.live.signal import CASH_SYMBOL, SLEEVE_SYMBOLS, TargetAllocation

JOURNAL_HEADER: tuple[str, ...] = (
    "date", "equity_level", "equity_sma", "equity_active", "bond_level", "bond_sma", "bond_active",
    "vti_weight", "ief_weight", "sgov_weight", "n_active", "value_before", "value_after",
    "cost_paid", "note",
)


@attrs.frozen(slots=True)
class JournalRow:
    """One month's journal record."""

    date: str
    equity_level: float
    equity_sma: float
    equity_active: bool
    bond_level: float
    bond_sma: float
    bond_active: bool
    vti_weight: float
    ief_weight: float
    sgov_weight: float
    n_active: int
    value_before: float
    value_after: float
    cost_paid: float
    note: str

    def as_cells(self) -> list[str]:
        return [
            self.date, f"{self.equity_level:.6f}", f"{self.equity_sma:.6f}",
            str(self.equity_active), f"{self.bond_level:.6f}", f"{self.bond_sma:.6f}",
            str(self.bond_active), f"{self.vti_weight:.4f}", f"{self.ief_weight:.4f}",
            f"{self.sgov_weight:.4f}", str(self.n_active), f"{self.value_before:.2f}",
            f"{self.value_after:.2f}", f"{self.cost_paid:.4f}", self.note,
        ]


def row_from(target: TargetAllocation, result: RebalanceResult, *, note: str = "") -> JournalRow:
    """Assemble a journal row from a target allocation and the paper rebalance it produced."""
    by_sleeve = {s.sleeve: s for s in target.sleeves}
    if "equity" not in by_sleeve or "bond" not in by_sleeve:
        raise LiveError("target allocation is missing a sleeve")
    eq = by_sleeve["equity"]
    bd = by_sleeve["bond"]
    return JournalRow(
        date=target.as_of, equity_level=eq.level, equity_sma=eq.sma, equity_active=eq.active,
        bond_level=bd.level, bond_sma=bd.sma, bond_active=bd.active,
        vti_weight=target.weight(SLEEVE_SYMBOLS["equity"]),
        ief_weight=target.weight(SLEEVE_SYMBOLS["bond"]),
        sgov_weight=target.weight(CASH_SYMBOL), n_active=target.n_active,
        value_before=result.value_before, value_after=result.value_after,
        cost_paid=result.cost_paid, note=note,
    )


def append_row(path: Path, row: JournalRow) -> None:
    """Append one journal row, writing the header if the file is new."""
    is_new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        if is_new:
            writer.writerow(JOURNAL_HEADER)
        writer.writerow(row.as_cells())


def read_journal(path: Path) -> list[dict[str, str]]:
    """Read the journal back as a list of string-keyed dict rows."""
    text = path.read_text(encoding="utf-8")
    reader = csv.reader(text.splitlines())
    rows = list(reader)
    if not rows or tuple(rows[0]) != JOURNAL_HEADER:
        raise LiveError(f"{path.name}: unexpected journal header")
    out: list[dict[str, str]] = []
    for raw in rows[1:]:
        if not raw:
            continue
        if len(raw) != len(JOURNAL_HEADER):
            raise LiveError(f"{path.name}: expected {len(JOURNAL_HEADER)} columns, got {raw!r}")
        out.append(dict(zip(JOURNAL_HEADER, raw, strict=True)))
    return out


def value_history(journal: Sequence[dict[str, str]]) -> list[float]:
    """The post-rebalance account values over time (for the drawdown check)."""
    return [float(r["value_after"]) for r in journal]
