"""The committed panel reproduces the committed Study 9 industry-trend artifact to the digit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from riskpremia.indtrend.fixtures import fixture_sha256, read_panel_frame
from riskpremia.indtrend.gate import artifact_to_json, build_gate_artifact, load_artifact_dict
from riskpremia.xtrend.fixtures import read_panel_frame as read_xtrend_panel

_REPO = Path(__file__).resolve().parents[2]
_PANEL = _REPO / "tests" / "data" / "indtrend_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "indtrend_panel_sources.json"
_XTREND = _REPO / "tests" / "data" / "xtrend_panel.csv"
_ARTIFACT = _REPO / "artifacts" / "indtrend_gate.json"


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
    assert committed["fingerprint"]["panel_relpath"] == "tests/data/indtrend_panel.csv"


def test_the_verdict_is_an_honest_timing_null() -> None:
    s = load_artifact_dict(_ARTIFACT)["score"]
    # the kill is the timing difference (strategy minus always-invested), and it is below the bar
    assert load_artifact_dict(_ARTIFACT)["verdict"]["non_viable"] is True
    assert s["passes_psr"] is False
    assert s["timing"]["full_psr_zero"] < 0.95
    # the net-of-bill PSR is high (the equity premium, the Study 8 trap), reported only as context
    assert s["context"]["strategy_net_of_bill_psr_zero"] > 0.95


def test_decomposition_identity_holds_on_the_committed_artifact() -> None:
    d = load_artifact_dict(_ARTIFACT)["score"]["decomposition"]
    assert d["timing_ann_return"] + d["tilt_ann_return"] == pytest.approx(
        d["deploy_ann_return"], abs=1e-9
    )


def test_active_bet_correlation_with_study_six_is_reported() -> None:
    # the timing signals co-move with Study 6 (a high active-bet correlation), the honest
    # redundancy finding; the difference series themselves are near-uncorrelated.
    rd = load_artifact_dict(_ARTIFACT)["score"]["redundancy"]
    assert rd["n_aligned"] > 1000
    assert rd["active_bet_corr"] > 0.3
