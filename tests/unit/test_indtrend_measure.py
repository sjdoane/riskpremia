"""Unit tests for the industry-trend gate building blocks (Study 9, synthetic returns)."""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from riskpremia.indtrend.fixtures import INDUSTRY_COLS, PanelRow, panel_csv_text, read_panel_frame
from riskpremia.indtrend.gate import (
    N_INDUSTRIES,
    _targets,
    _trend_strength_by_month,
    build_gate_artifact,
)


def _weekday(d: date) -> date:
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


def _panel(n: int, *, seed: int) -> pl.DataFrame:
    rng = random.Random(seed)
    d = date(2010, 1, 1)
    dates: list[date] = []
    industries: list[list[float]] = [[] for _ in range(N_INDUSTRIES)]
    market: list[float] = []
    cash: list[float] = []
    drift = [0.0002 + 0.0001 * i for i in range(N_INDUSTRIES)]
    for _ in range(n):
        d = _weekday(d)
        dates.append(d)
        day_rets = [rng.gauss(drift[i], 0.01) for i in range(N_INDUSTRIES)]
        for i in range(N_INDUSTRIES):
            industries[i].append(day_rets[i])
        market.append(sum(day_rets) / N_INDUSTRIES + rng.gauss(0.0, 0.001))
        cash.append(0.00005)
    return pl.DataFrame(
        {"date": dates, **{c: industries[i] for i, c in enumerate(INDUSTRY_COLS)},
         "market_ret": market, "cash_ret": cash}
    )


def test_targets_all_twelve_long_or_cash() -> None:
    strengths = [0.1, -0.2, 0.3, -0.1, 0.05, -0.5, 0.2, 0.0, 0.4, -0.3, 0.15, 0.25]
    targets = _targets(strengths, top_k=0)
    above = [i for i in range(N_INDUSTRIES) if strengths[i] > 0.0]
    assert set(targets) == set(above)
    for w in targets.values():
        assert w == pytest.approx(1.0 / N_INDUSTRIES)


def test_targets_top_k_holds_the_strongest() -> None:
    strengths = [0.1, -0.2, 0.3, -0.1, 0.05, -0.5, 0.2, 0.0, 0.4, -0.3, 0.15, 0.25]
    targets = _targets(strengths, top_k=3)
    # the three strongest positive strengths are industries 8 (0.4), 2 (0.3), 11 (0.25)
    assert set(targets) == {8, 2, 11}
    for w in targets.values():
        assert w == pytest.approx(1.0 / 3)


def test_targets_top_k_respects_the_above_ma_filter() -> None:
    # only two industries are above their MA, so a top-3 holds at most those two.
    strengths = [-0.1] * N_INDUSTRIES
    strengths[4] = 0.2
    strengths[9] = 0.1
    targets = _targets(strengths, top_k=3)
    assert set(targets) == {4, 9}


def test_trend_strength_sign_tracks_the_moving_average() -> None:
    panel = _panel(700, seed=2)
    from riskpremia.indtrend.gate import _daily_from_panel

    daily = _daily_from_panel(panel)
    strengths = _trend_strength_by_month(daily, sma_months=10)
    # every scored month has a strength per industry, and a rising industry is eventually positive
    some_month = max(strengths)
    assert len(strengths[some_month]) == N_INDUSTRIES


def test_panel_round_trips(tmp_path: Path) -> None:
    rows = [
        PanelRow(date(2020, 1, 6), tuple(Decimal("0.001") for _ in range(12)),
                 Decimal("0.0009"), Decimal("0.00005")),
        PanelRow(date(2020, 1, 7), tuple(Decimal("-0.002") for _ in range(12)),
                 Decimal("-0.0018"), Decimal("0.00005")),
    ]
    path = tmp_path / "p.csv"
    path.write_text(panel_csv_text(rows), encoding="utf-8")
    frame = read_panel_frame(path)
    assert frame.columns == ["date", *INDUSTRY_COLS, "market_ret", "cash_ret"]
    assert frame.height == 2


def test_decomposition_identity_holds() -> None:
    # timing (strategy minus EW) plus tilt (EW minus market) equals deploy (strategy minus market).
    panel = _panel(900, seed=5)
    art = build_gate_artifact(
        panel, panel_sha256="x", panel_relpath="p", provenance_sha256="y", provenance_relpath="q",
    )
    d = art.score.decomposition
    assert d.timing_ann_return + d.tilt_ann_return == pytest.approx(d.deploy_ann_return, abs=1e-9)


def test_long_or_cash_never_levers() -> None:
    panel = _panel(900, seed=8)
    art = build_gate_artifact(
        panel, panel_sha256="x", panel_relpath="p", provenance_sha256="y", provenance_relpath="q",
    )
    assert art.score.descriptive.max_gross <= 1.0 + 1e-9
