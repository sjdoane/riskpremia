"""The committed Study 7 dispersion series reproduces the committed artifact (offline)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from riskpremia.data.manifest import compute_sha256, load_manifest, verify_snapshot
from riskpremia.dispersion.artifact import artifact_to_json, build_artifact, load_artifact_dict
from riskpremia.dispersion.fixtures import fixture_sha256, read_series_frame

_REPO = Path(__file__).resolve().parents[2]
_SERIES = _REPO / "tests" / "data" / "funding_dispersion_series.csv"
_PROVENANCE = _REPO / "tests" / "data" / "funding_dispersion_sources.json"
_ARTIFACT = _REPO / "artifacts" / "funding_dispersion.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"


def _assert_json_close(a: Any, b: Any, *, path: str = "$") -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), f"{path}: key mismatch"
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
    series = read_series_frame(_SERIES)
    artifact = build_artifact(
        series,
        series_sha256=fixture_sha256(_SERIES),
        series_relpath=_SERIES.relative_to(_REPO).as_posix(),
        provenance_sha256=fixture_sha256(_PROVENANCE),
        provenance_relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
    )
    return artifact_to_json(artifact)


def test_committed_series_reproduces_the_artifact() -> None:
    _assert_json_close(json.loads(_rebuild()), load_artifact_dict(_ARTIFACT))


def test_artifact_is_deterministic() -> None:
    assert _rebuild() == _rebuild()


def test_series_is_tamper_evident() -> None:
    entries = {e.name: e for e in load_manifest(_MANIFEST)}
    verify_snapshot(entries["funding-dispersion-series"], _REPO)
    verify_snapshot(entries["funding-dispersion-sources"], _REPO)
    assert load_artifact_dict(_ARTIFACT)["fingerprint"]["series_sha256"] == compute_sha256(_SERIES)


def test_measurement_is_non_deployable_framing() -> None:
    # The honesty guardrail: the artifact must not headline a tradeable Sharpe; it must state
    # non-deployability and the decay.
    data = load_artifact_dict(_ARTIFACT)
    headline = data["headline"].lower()
    assert "non-deployable" in headline or "not retail-capturable" in headline
    assert "sharpe" not in headline
