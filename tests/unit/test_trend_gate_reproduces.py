"""The committed Study 4 gate reproduces offline from the committed fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from riskpremia.data.manifest import compute_sha256, load_manifest, verify_snapshot
from riskpremia.trend.fixtures import fixture_sha256, read_bars_frame, read_source_files_json
from riskpremia.trend.gate import artifact_to_json, build_gate_artifact, load_gate_artifact

_REPO = Path(__file__).resolve().parents[2]
_BARS = _REPO / "tests" / "data" / "btc_eth_daily_ohlc.csv"
_SOURCES = _REPO / "tests" / "data" / "btc_eth_daily_ohlc_sources.json"
_ARTIFACT = _REPO / "artifacts" / "btc_eth_trend_gate.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"

_HAVE = _BARS.exists() and _SOURCES.exists() and _ARTIFACT.exists()
pytestmark = pytest.mark.skipif(not _HAVE, reason="the committed Study 4 gate is not built yet")


def _assert_json_close(actual: Any, expected: Any, *, path: str = "artifact") -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert set(actual) == set(expected), path
        for key in expected:
            _assert_json_close(actual[key], expected[key], path=f"{path}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), path
        assert len(actual) == len(expected), path
        for i, (a_item, e_item) in enumerate(zip(actual, expected, strict=True)):
            _assert_json_close(a_item, e_item, path=f"{path}[{i}]")
        return
    if isinstance(expected, float):
        assert isinstance(actual, int | float), path
        assert float(actual) == pytest.approx(expected, rel=1e-12, abs=1e-12), path
        return
    assert actual == expected, path


def _rebuild():
    bars = read_bars_frame(_BARS)
    sources = read_source_files_json(_SOURCES)
    return build_gate_artifact(
        bars,
        bars_sha256=fixture_sha256(_BARS),
        bars_relpath="tests/data/btc_eth_daily_ohlc.csv",
        sources_sha256=compute_sha256(_SOURCES),
        sources_relpath="tests/data/btc_eth_daily_ohlc_sources.json",
        sources=sources,
    )


def test_committed_fixtures_reproduce_the_trend_gate() -> None:
    committed = load_gate_artifact(_ARTIFACT)
    rebuilt = _rebuild()

    assert rebuilt.fingerprint.bars_sha256 == committed.fingerprint.bars_sha256
    assert rebuilt.fingerprint.sources_sha256 == committed.fingerprint.sources_sha256
    assert rebuilt.last_signal_date == committed.last_signal_date
    assert rebuilt.last_fill_date == committed.last_fill_date
    assert rebuilt.last_exit_date == committed.last_exit_date
    assert rebuilt.score.raw_t == committed.score.raw_t
    assert rebuilt.score.cpcv_min_psr_stress == pytest.approx(
        committed.score.cpcv_min_psr_stress, abs=1e-6
    )
    assert rebuilt.score.max_drawdown == pytest.approx(committed.score.max_drawdown, abs=1e-12)
    assert rebuilt.verdict.non_viable == committed.verdict.non_viable
    _assert_json_close(
        json.loads(artifact_to_json(rebuilt)),
        json.loads(_ARTIFACT.read_text(encoding="utf-8")),
    )


def test_trend_fixtures_are_tamper_evident() -> None:
    entries = {e.name: e for e in load_manifest(_MANIFEST)}
    assert {"btc-eth-daily-ohlc", "btc-eth-daily-ohlc-sources"} <= set(entries)
    verify_snapshot(entries["btc-eth-daily-ohlc"], _REPO)
    verify_snapshot(entries["btc-eth-daily-ohlc-sources"], _REPO)
    artifact = load_gate_artifact(_ARTIFACT)
    assert artifact.fingerprint.bars_sha256 == compute_sha256(_BARS)
    assert artifact.fingerprint.sources_sha256 == compute_sha256(_SOURCES)
