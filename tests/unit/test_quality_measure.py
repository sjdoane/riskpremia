"""Unit tests for the quality-tilt gate building blocks (Study 10, synthetic returns)."""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from riskpremia.quality.fixtures import (
    FACTOR_COLS,
    PORTFOLIO_COLS,
    PanelRow,
    panel_csv_text,
    read_panel_frame,
)
from riskpremia.quality.gate import (
    QualityKnobs,
    _arrays,
    _difference,
    _ff5_attribution,
    build_gate_artifact,
)


def _weekday(d: date) -> date:
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


def _panel(
    n: int, *, seed: int, alpha_daily: float = 0.00002, rmw_beta: float = 0.3
) -> pl.DataFrame:
    rng = random.Random(seed)
    d = date(2000, 1, 1)
    dates: list[date] = []
    cols: dict[str, list[float]] = {c: [] for c in (*PORTFOLIO_COLS, *FACTOR_COLS)}
    for _ in range(n):
        d = _weekday(d)
        dates.append(d)
        mkt_rf = rng.gauss(0.0003, 0.01)
        smb = rng.gauss(0.0, 0.004)
        hml = rng.gauss(0.0, 0.004)
        rmw = rng.gauss(0.0001, 0.003)
        cma = rng.gauss(0.0, 0.003)
        rf = 0.00006
        # the high-profitability leg loads on the market and on RMW, plus a small alpha
        hi = rf + alpha_daily + 1.0 * mkt_rf + rmw_beta * rmw + rng.gauss(0.0, 0.002)
        for c, v in (("hi30_vw", hi), ("hi20_vw", hi + rng.gauss(0, 0.001)),
                     ("hi10_vw", hi + rng.gauss(0, 0.0015)), ("hi30_ew", hi + rng.gauss(0, 0.0012)),
                     ("mkt_rf", mkt_rf), ("smb", smb), ("hml", hml), ("rmw", rmw), ("cma", cma),
                     ("rf", rf)):
            cols[c].append(v)
    return pl.DataFrame({"date": dates, **cols})


def test_difference_is_net_of_market_minus_differential() -> None:
    cols = {"hi30_vw": [0.01, 0.02], "mkt_rf": [0.006, 0.008], "rf": [0.0001, 0.0001]}
    diff = _difference(cols, "hi30_vw", differential_daily=0.000004)
    assert diff[0] == pytest.approx(0.01 - (0.006 + 0.0001) - 0.000004)
    assert diff[1] == pytest.approx(0.02 - (0.008 + 0.0001) - 0.000004)


def test_ff5_attribution_recovers_a_known_alpha_and_loading() -> None:
    panel = _panel(1500, seed=3, alpha_daily=0.00002, rmw_beta=0.3)
    cols = _arrays(panel)
    att = _ff5_attribution(cols, "hi30_vw", trading_days=252.0)
    # the constructed daily alpha is 2e-5; the OLS recovers it within sampling noise
    assert att.alpha_daily == pytest.approx(0.00002, abs=1.5e-4)
    assert att.beta_mkt == pytest.approx(1.0, abs=0.05)
    assert att.beta_rmw == pytest.approx(0.3, abs=0.1)
    assert att.rmw_is_dominant is True


def test_ff5_alpha_t_stat_is_finite_and_signed() -> None:
    panel = _panel(1500, seed=11, alpha_daily=0.0001)
    att = _ff5_attribution(_arrays(panel), "hi30_vw", trading_days=252.0)
    # a clearly positive constructed alpha yields a positive t-statistic
    assert att.alpha_t_stat > 0.0


def test_panel_round_trips(tmp_path: Path) -> None:
    rows = [
        PanelRow(date(2020, 1, 6), tuple(Decimal("0.001") for _ in PORTFOLIO_COLS),
                 tuple(Decimal("0.0002") for _ in FACTOR_COLS)),
        PanelRow(date(2020, 1, 7), tuple(Decimal("-0.002") for _ in PORTFOLIO_COLS),
                 tuple(Decimal("0.0001") for _ in FACTOR_COLS)),
    ]
    path = tmp_path / "p.csv"
    path.write_text(panel_csv_text(rows), encoding="utf-8")
    frame = read_panel_frame(path)
    assert frame.columns == ["date", *PORTFOLIO_COLS, *FACTOR_COLS]
    assert frame.height == 2


def test_build_artifact_runs_on_synthetic_data() -> None:
    panel = _panel(1500, seed=7)
    art = build_gate_artifact(
        panel, panel_sha256="x", panel_relpath="p", provenance_sha256="y", provenance_relpath="q",
    )
    assert art.score.difference.gross_full_psr_zero >= art.score.difference.full_psr_zero
    assert art.cost_model.differential_annual == pytest.approx(
        art.knobs.expense_hi_annual - art.knobs.expense_mkt_annual
    )


def test_differential_cost_lowers_the_difference_psr() -> None:
    # a larger differential expense can only reduce the difference PSR (it subtracts a constant).
    panel = _panel(1500, seed=9)
    knobs_cheap = QualityKnobs(expense_hi_annual=0.0004, expense_mkt_annual=0.0004)
    knobs_dear = QualityKnobs(expense_hi_annual=0.0030, expense_mkt_annual=0.0004)
    cheap = build_gate_artifact(panel, panel_sha256="x", panel_relpath="p",
                                provenance_sha256="y", provenance_relpath="q", knobs=knobs_cheap)
    dear = build_gate_artifact(panel, panel_sha256="x", panel_relpath="p",
                               provenance_sha256="y", provenance_relpath="q", knobs=knobs_dear)
    assert dear.score.difference.full_psr_zero <= cheap.score.difference.full_psr_zero
