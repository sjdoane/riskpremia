"""The committed Study 6 panel reproduces the committed gate artifact (offline)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from riskpremia.data.manifest import compute_sha256, load_manifest, verify_snapshot
from riskpremia.xtrend.fixtures import fixture_sha256, read_panel_frame
from riskpremia.xtrend.gate import artifact_to_json, build_gate_artifact, load_artifact_dict

_REPO = Path(__file__).resolve().parents[2]
_PANEL = _REPO / "tests" / "data" / "xtrend_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "xtrend_panel_sources.json"
_ARTIFACT = _REPO / "artifacts" / "xtrend_gate.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"


def _assert_json_close(a: Any, b: Any, *, path: str = "$") -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), f"{path}: key mismatch {a.keys()} != {b.keys()}"
        for key in a:
            _assert_json_close(a[key], b[key], path=f"{path}.{key}")
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _assert_json_close(x, y, path=f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12), f"{path}: {a} != {b}"
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


def _rebuild() -> str:
    panel = read_panel_frame(_PANEL)
    artifact = build_gate_artifact(
        panel,
        panel_sha256=fixture_sha256(_PANEL),
        panel_relpath=_PANEL.relative_to(_REPO).as_posix(),
        provenance_sha256=fixture_sha256(_PROVENANCE),
        provenance_relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
    )
    return artifact_to_json(artifact)


def test_committed_panel_reproduces_the_gate() -> None:
    rebuilt = json.loads(_rebuild())
    committed = load_artifact_dict(_ARTIFACT)
    _assert_json_close(rebuilt, committed)


def test_gate_is_deterministic() -> None:
    assert _rebuild() == _rebuild()


def test_panel_is_tamper_evident() -> None:
    entries = {e.name: e for e in load_manifest(_MANIFEST)}
    verify_snapshot(entries["xtrend-panel"], _REPO)
    verify_snapshot(entries["xtrend-panel-sources"], _REPO)
    committed = load_artifact_dict(_ARTIFACT)
    assert committed["fingerprint"]["panel_sha256"] == compute_sha256(_PANEL)


def test_verdict_matches_pre_registered_primary_gate() -> None:
    committed = load_artifact_dict(_ARTIFACT)
    score = committed["score"]
    # The pre-registered primary gate is the full-sample conditional PSR(0) >= 0.95.
    if score["full_psr_zero"] >= 0.95 and score["passes_drawdown"] and score["passes_cost_share"]:
        assert committed["verdict"]["non_viable"] is False
    else:
        assert committed["verdict"]["non_viable"] is True
