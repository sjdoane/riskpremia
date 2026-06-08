"""The committed Study 6 panel reproduces the committed Study 8 gate artifact to the digit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from riskpremia.volmanaged.gate import artifact_to_json, build_gate_artifact, load_artifact_dict
from riskpremia.xtrend.fixtures import fixture_sha256, read_panel_frame

_REPO = Path(__file__).resolve().parents[2]
_PANEL = _REPO / "tests" / "data" / "xtrend_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "xtrend_panel_sources.json"
_ARTIFACT = _REPO / "artifacts" / "volmanaged_gate.json"


def _rebuild() -> dict[str, Any]:
    panel = read_panel_frame(_PANEL)
    artifact = build_gate_artifact(
        panel,
        panel_sha256=fixture_sha256(_PANEL),
        panel_relpath=_PANEL.relative_to(_REPO).as_posix(),
        provenance_sha256=fixture_sha256(_PROVENANCE),
        provenance_relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
    )
    import json

    return dict(json.loads(artifact_to_json(artifact)))


def _assert_close(a: Any, b: Any, path: str = "") -> None:
    if isinstance(a, dict):
        assert isinstance(b, dict), f"type mismatch at {path}"
        assert set(a) == set(b), f"keys differ at {path}: {set(a) ^ set(b)}"
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
    committed = load_artifact_dict(_ARTIFACT)
    rebuilt = _rebuild()
    _assert_close(rebuilt, committed)


def test_fingerprint_is_tamper_evident() -> None:
    committed = load_artifact_dict(_ARTIFACT)
    assert committed["fingerprint"]["panel_sha256"] == fixture_sha256(_PANEL)
    assert committed["fingerprint"]["panel_relpath"] == "tests/data/xtrend_panel.csv"


def test_the_verdict_is_an_honest_non_viable_difference_null() -> None:
    # The kill is the managed-minus-unmanaged difference, and on this sample it is below the bar.
    committed = load_artifact_dict(_ARTIFACT)
    score = committed["score"]
    assert committed["verdict"]["non_viable"] is True
    assert score["passes_psr"] is False
    assert score["difference"]["full_psr_zero"] < 0.95
    # the expanding-window (real-time) c agrees with the full-sample verdict
    assert score["expanding_c"]["full_psr_zero"] < 0.95
    # the standalone managed Sharpe is the equity premium, not the kill: it is reported as context
    assert score["context"]["managed_ann_sharpe"] > 0.0


def test_difference_is_near_orthogonal_to_study_six() -> None:
    # The redundancy objection is answered: the difference series is near-uncorrelated with the
    # Study 6 cross-asset trend, even though the level correlation is high by construction.
    committed = load_artifact_dict(_ARTIFACT)
    rd = committed["score"]["redundancy"]
    assert abs(rd["difference_vs_xtrend_corr"]) < 0.25
    assert rd["managed_vs_xtrend_corr"] > 0.5
