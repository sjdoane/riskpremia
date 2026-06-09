"""The committed panel reproduces the committed Study 10 quality-tilt artifact to the digit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from riskpremia.quality.fixtures import fixture_sha256, read_panel_frame
from riskpremia.quality.gate import artifact_to_json, build_gate_artifact, load_artifact_dict
from riskpremia.xtrend.fixtures import read_panel_frame as read_xtrend_panel

_REPO = Path(__file__).resolve().parents[2]
_PANEL = _REPO / "tests" / "data" / "quality_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "quality_panel_sources.json"
_XTREND = _REPO / "tests" / "data" / "xtrend_panel.csv"
_ARTIFACT = _REPO / "artifacts" / "quality_gate.json"


def _rebuild() -> dict[str, Any]:
    panel = read_panel_frame(_PANEL)
    xtrend = read_xtrend_panel(_XTREND)
    artifact = build_gate_artifact(
        panel,
        panel_sha256=fixture_sha256(_PANEL),
        panel_relpath=_PANEL.relative_to(_REPO).as_posix(),
        provenance_sha256=fixture_sha256(_PROVENANCE),
        provenance_relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
        xtrend_panel=xtrend,
    )
    return dict(json.loads(artifact_to_json(artifact)))


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


def test_committed_panel_reproduces_the_artifact() -> None:
    _assert_close(_rebuild(), load_artifact_dict(_ARTIFACT))


def test_fingerprint_is_tamper_evident() -> None:
    committed = load_artifact_dict(_ARTIFACT)
    assert committed["fingerprint"]["panel_sha256"] == fixture_sha256(_PANEL)
    assert committed["fingerprint"]["panel_relpath"] == "tests/data/quality_panel.csv"


def test_the_premium_is_real_but_not_a_deployable_pass() -> None:
    s = load_artifact_dict(_ARTIFACT)["score"]
    # the gross difference clears the bar (the premium is real) ...
    assert s["difference"]["gross_full_psr_zero"] >= 0.95
    # the Fama-French five-factor alpha is positive with robust-minus-weak the dominant loading
    assert s["attribution"]["alpha_ann"] > 0.0
    assert s["attribution"]["rmw_is_dominant"] is True
    assert s["attribution"]["alpha_t_stat"] > 2.0
    # ... but net of the deployable differential expense it does not clear the bar
    assert s["difference"]["full_psr_zero"] < 0.95
    # and it fails the deflation at the literature-scale minimum trial count
    assert s["deflation"]["passes_at_min_trials"] is False
    assert s["make_money_pass"] is False
    assert load_artifact_dict(_ARTIFACT)["verdict"]["non_viable"] is True


def test_the_net_of_bill_psr_is_the_equity_premium_context() -> None:
    # the high-profitability portfolio crushes the bill (the equity premium, reported as context).
    s = load_artifact_dict(_ARTIFACT)["score"]
    assert s["context"]["hi_net_of_bill_psr_zero"] > 0.95
