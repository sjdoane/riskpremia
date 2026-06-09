"""The levels file and the journal: round-trips, ordering guards, and the value history."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from riskpremia.live.errors import LiveError
from riskpremia.live.journal import append_row, read_journal, row_from, value_history
from riskpremia.live.levels import (
    LevelRow,
    append_level,
    read_levels,
    sleeve_levels,
    write_levels_csv,
)
from riskpremia.live.paper import new_account, rebalance
from riskpremia.live.signal import target_from_levels


def _levels(n: int) -> list[LevelRow]:
    return [LevelRow(date(2020, 1, 1).replace(month=((i % 12) + 1), year=2020 + i // 12),
                     100.0 + i, 50.0 + i, 100.0) for i in range(n)]


def test_levels_round_trip(tmp_path: Path) -> None:
    rows = _levels(12)
    path = tmp_path / "levels.csv"
    write_levels_csv(path, rows)
    back = read_levels(path)
    assert len(back) == 12
    assert back[0].date == rows[0].date
    assert back[-1].equity == pytest.approx(rows[-1].equity)
    sl = sleeve_levels(back)
    assert set(sl) == {"equity", "bond"}
    assert len(sl["equity"]) == 12


def test_append_rejects_out_of_order_duplicate_and_gap(tmp_path: Path) -> None:
    path = tmp_path / "levels.csv"
    write_levels_csv(path, _levels(3))  # Jan, Feb, Mar 2020
    last = read_levels(path)[-1]
    with pytest.raises(LiveError):
        append_level(path, LevelRow(last.date, 1.0, 1.0, 1.0))  # duplicate date
    with pytest.raises(LiveError):
        append_level(path, LevelRow(date(2020, 6, 30), 1.0, 1.0, 1.0))  # skips Apr and May
    good = LevelRow(date(2020, 4, 30), 200.0, 60.0, 100.0)  # the consecutive next month
    append_level(path, good)
    assert read_levels(path)[-1].date == good.date


def test_read_levels_rejects_a_month_gap(tmp_path: Path) -> None:
    path = tmp_path / "gap.csv"
    path.write_text(
        "date,vti,ief,sgov\n2020-01-31,100,50,100\n2020-03-31,101,50,100\n",  # February missing
        encoding="utf-8",
    )
    with pytest.raises(LiveError):
        read_levels(path)


def test_levels_reject_nonpositive(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("date,vti,ief,sgov\n2020-01-31,100.0,-1.0,100.0\n", encoding="utf-8")
    with pytest.raises(LiveError):
        read_levels(path)


def test_journal_round_trip_and_value_history(tmp_path: Path) -> None:
    rows = _levels(11)
    target = target_from_levels(sleeve_levels(rows), rows[-1].date)
    prices = {"VTI": rows[-1].equity, "IEF": rows[-1].bond, "SGOV": rows[-1].cash}
    result = rebalance(new_account(10_000.0), target.weights, prices, rows[-1].date,
                       turnover_cost_per_side=0.0005, charged_symbols=("VTI", "IEF"))
    path = tmp_path / "journal.csv"
    append_row(path, row_from(target, result))
    append_row(path, row_from(target, result, note="second"))
    back = read_journal(path)
    assert len(back) == 2
    assert back[0]["date"] == rows[-1].date.isoformat()
    assert back[1]["note"] == "second"
    history = value_history(back)
    assert len(history) == 2
    assert history[0] == pytest.approx(result.value_after)
