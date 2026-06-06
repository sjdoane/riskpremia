"""Surgical logic tests for the cross-asset trend gate (Study 6, synthetic panels)."""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import date, timedelta

import polars as pl
import pytest

from riskpremia.execution.errors import ScoringError
from riskpremia.xtrend.gate import artifact_to_json, build_gate_artifact

_SCHEMA = {
    "date": pl.Date,
    "equity_ret": pl.Float64,
    "cash_ret": pl.Float64,
    "bond_yield": pl.Float64,
}


def _business_days(start: date, count: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _panel(
    dates: Sequence[date],
    equity: Sequence[float],
    cash: Sequence[float],
    yields: Sequence[float],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "date": list(dates),
            "equity_ret": list(equity),
            "cash_ret": list(cash),
            "bond_yield": list(yields),
        },
        schema=_SCHEMA,
    )


def _build(panel: pl.DataFrame):  # type: ignore[no-untyped-def]
    return build_gate_artifact(
        panel,
        panel_sha256="x",
        panel_relpath="p",
        provenance_sha256="y",
        provenance_relpath="q",
    )


def _random_panel(n: int, seed: int) -> pl.DataFrame:
    rng = random.Random(seed)
    dates = _business_days(date(2000, 1, 3), n)
    equity = [rng.gauss(0.0003, 0.011) for _ in range(n)]
    cash = [0.00008] * n
    y = 0.045
    yields: list[float] = []
    for _ in range(n):
        y += rng.gauss(0.0, 0.0008)
        y = max(0.006, min(0.12, y))
        yields.append(y)
    return _panel(dates, equity, cash, yields)


def test_sustained_downtrend_goes_all_cash_and_is_unscoreable() -> None:
    # A monotonic decline keeps every sleeve below its moving average, so the rule sits in
    # cash; the excess-of-bills return is then identically zero, and the gate correctly
    # refuses to score a zero-variance series rather than reporting a spurious Sharpe. This
    # validates both the long-or-cash logic and the excess-of-bills construction (cash earns
    # exactly the bill, so its excess return is zero).
    n = 760
    dates = _business_days(date(2000, 1, 3), n)
    equity = [-0.0006] * n
    cash = [0.0001] * n
    yields = [0.03 + 0.00004 * i for i in range(n)]  # rising yield -> falling bond level
    with pytest.raises(ScoringError):
        _build(_panel(dates, equity, cash, yields))


def test_costs_make_net_below_gross() -> None:
    art = _build(_random_panel(3000, seed=7))
    assert art.score.total_cost_paid > 0.0
    assert art.score.compounded_net_total_gain < art.score.compounded_gross_total_gain


def test_excess_excludes_bill_carry() -> None:
    art = _build(_random_panel(3000, seed=11))
    # The total return includes bill carry; the excess series removes it.
    assert art.score.bill_carry_gain > 0.0
    assert art.score.compounded_net_total_gain > art.score.compounded_net_excess_gain


def test_deterministic_rebuild() -> None:
    panel = _random_panel(2500, seed=3)
    assert artifact_to_json(_build(panel)) == artifact_to_json(_build(panel))


def test_no_look_ahead_truncation_invariance() -> None:
    # The strategy's early daily marks must not change when later data is removed: a frozen
    # backward-looking rule cannot see the future.
    full = _random_panel(3200, seed=5)
    prefix = full.head(full.height - 300)
    art_full = _build(full)
    art_prefix = _build(prefix)
    full_eq = dict(zip(art_full.daily_equity.date, art_full.daily_equity.equity, strict=True))
    prefix_eq = dict(zip(art_prefix.daily_equity.date, art_prefix.daily_equity.equity, strict=True))
    # The daily_equity dates are ISO strings, which sort chronologically. Compare on dates
    # present in both, excluding the prefix's final two months (the partial boundary month
    # plus the month whose signal would differ at the truncation edge).
    last_prefix = date.fromisoformat(max(prefix_eq))
    cutoff = (last_prefix - timedelta(days=62)).isoformat()
    shared = [d for d in prefix_eq if d in full_eq and d <= cutoff]
    assert len(shared) > 1500
    for d in shared:
        assert full_eq[d] == pytest.approx(prefix_eq[d], rel=1e-12, abs=1e-12)
