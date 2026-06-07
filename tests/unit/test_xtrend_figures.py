"""The Study 6 figure rendering. Skipped when matplotlib (the optional `figures` extra) is
absent, so CI (which installs only `.[dev]`) does not need it; the figures render purely from
the committed artifact, never recomputing the gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("matplotlib") is None,
    reason="matplotlib (the figures extra) is not installed",
)

_REPO = Path(__file__).resolve().parents[2]
_ARTIFACT = _REPO / "artifacts" / "xtrend_gate.json"


def test_render_all_writes_nonempty_pngs(tmp_path: Path) -> None:
    from riskpremia.xtrend.figures import render_all

    paths = render_all(_ARTIFACT, tmp_path)
    assert len(paths) == 2
    for p in paths:
        assert p.exists()
        assert p.stat().st_size > 1000  # a real PNG, not an empty stub
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
