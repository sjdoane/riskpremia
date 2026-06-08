"""Unit + reproduction tests for the Study 8 factor-asymmetry secondary."""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from riskpremia.volmanaged.factors import (
    FACTOR_NAMES,
    FactorPanelRow,
    _score_factor,
    build_asymmetry_artifact,
    factor_panel_csv_text,
    fixture_sha256,
    load_artifact_dict,
    read_factor_panel_frame,
)
from riskpremia.volmanaged.gate import load_artifact_dict as load_market

_REPO = Path(__file__).resolve().parents[2]
_PANEL = _REPO / "tests" / "data" / "volmanaged_factor_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "volmanaged_factor_sources.json"
_MARKET = _REPO / "artifacts" / "volmanaged_gate.json"
_ARTIFACT = _REPO / "artifacts" / "volmanaged_factor_asymmetry.json"


def _weekday(d: date) -> date:
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


def _factor_series(n: int, *, seed: int) -> tuple[list[date], list[float]]:
    rng = random.Random(seed)
    d = date(2015, 1, 1)
    dates: list[date] = []
    rets: list[float] = []
    for _ in range(n):
        d = _weekday(d)
        vol = 0.006 * (1.6 if d.month % 3 == 0 else 0.6)
        dates.append(d)
        rets.append(rng.gauss(0.0001, vol))
    return dates, rets


def test_factor_panel_csv_round_trips(tmp_path: Path) -> None:
    rows = [
        FactorPanelRow(date(2020, 1, 6), Decimal("0.001"), Decimal("-0.002"), Decimal("0.0003"),
                       Decimal("0.0004"), Decimal("0.005")),
        FactorPanelRow(date(2020, 1, 7), Decimal("0.002"), Decimal("0.001"), Decimal("-0.0001"),
                       Decimal("0.0002"), Decimal("-0.003")),
    ]
    path = tmp_path / "fp.csv"
    path.write_text(factor_panel_csv_text(rows), encoding="utf-8")
    frame = read_factor_panel_frame(path)
    assert frame.columns == ["date", *FACTOR_NAMES]
    assert frame.height == 2
    assert frame["wml"].to_list()[0] == pytest.approx(0.005)


def test_score_factor_difference_is_managed_minus_unmanaged() -> None:
    dates, rets = _factor_series(1600, seed=4)  # past the 60-month expanding-c burn-in
    result = _score_factor("wml", dates, rets)
    assert result.name == "wml"
    assert result.raw_t > 1400
    assert 0.0 <= result.difference_expanding_psr_zero <= 1.0
    assert 0.0 <= result.difference_full_psr_zero <= 1.0
    # the cap drag plus the cost drag plus the gross equals the net (the decomposition closes)
    decomposed = (
        result.gross_uncapped_ann_return + result.cap_drag_ann_return + result.cost_drag_ann_return
    )
    assert decomposed == pytest.approx(result.net_ann_return, abs=1e-9)


def test_asymmetry_decision_rule_uniform_null() -> None:
    # Build the artifact from a synthetic panel with the market failing (psr below the bar).
    rows: list[FactorPanelRow] = []
    rng = random.Random(99)
    d = date(2010, 1, 1)
    for _ in range(1600):  # past the 60-month expanding-c burn-in
        d = _weekday(d)
        vals = [Decimal(str(round(rng.gauss(0.0, 0.006), 6))) for _ in FACTOR_NAMES]
        rows.append(FactorPanelRow(d, *vals))
    frame = pl.DataFrame(
        {"date": [r.date for r in rows],
         **{n: [float(getattr(r, n)) for r in rows] for n in FACTOR_NAMES}}
    )
    art = build_asymmetry_artifact(
        frame, market_difference_psr=0.45, panel_sha256="x", panel_relpath="p",
        provenance_sha256="y", provenance_relpath="q",
    )
    assert art.market_passes is False
    assert art.asymmetry_confirmed is False  # market did not pass, so it is not confirmed
    assert len(art.factors) == len(FACTOR_NAMES)


def _assert_close(a: Any, b: Any, path: str = "") -> None:
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), f"keys differ at {path}"
        for k in a:
            _assert_close(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), f"list mismatch at {path}"
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _assert_close(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-12), f"float mismatch at {path}: {a} != {b}"
    else:
        assert a == b, f"value mismatch at {path}: {a!r} != {b!r}"


def test_committed_panel_reproduces_the_asymmetry_artifact() -> None:
    committed = load_artifact_dict(_ARTIFACT)
    panel = read_factor_panel_frame(_PANEL)
    market_psr = float(load_market(_MARKET)["score"]["difference"]["full_psr_zero"])
    rebuilt = build_asymmetry_artifact(
        panel, market_difference_psr=market_psr,
        panel_sha256=fixture_sha256(_PANEL), panel_relpath="tests/data/volmanaged_factor_panel.csv",
        provenance_sha256=fixture_sha256(_PROVENANCE),
        provenance_relpath="tests/data/volmanaged_factor_sources.json",
    )
    from riskpremia.volmanaged.factors import artifact_to_json

    _assert_close(dict(json.loads(artifact_to_json(rebuilt))), committed)


def test_the_result_is_a_uniform_null_robust_to_the_real_time_c() -> None:
    committed = load_artifact_dict(_ARTIFACT)
    assert committed["market_passes"] is False
    assert committed["n_factors_failing"] == len(FACTOR_NAMES)  # every factor fails too
    by_name = {f["name"]: f for f in committed["factors"]}
    # momentum has the largest gross volatility-timing alpha (the Barroso-Santa-Clara effect)
    assert by_name["wml"]["gross_uncapped_ann_return"] == max(
        f["gross_uncapped_ann_return"] for f in committed["factors"]
    )
    # but the full-sample-c WML standout does not survive the real-time expanding-window c: its
    # out-of-sample PSR collapses well below the full-sample one (a look-ahead artifact).
    assert by_name["wml"]["difference_expanding_psr_zero"] < 0.6
    assert (
        by_name["wml"]["difference_expanding_psr_zero"]
        < by_name["wml"]["difference_full_psr_zero"] - 0.2
    )
    # every factor stays below the bar under the real-time c too (the null is robust out-of-sample)
    for f in committed["factors"]:
        assert f["difference_expanding_psr_zero"] < 0.95
