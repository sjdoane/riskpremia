"""Render the Study 9 industry-trend figures from the committed panel and artifact (no network).

Needs the optional `figures` extra (matplotlib). The wealth paths are rebuilt deterministically from
the committed panel and the scorecard reads the committed artifact.
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.indtrend.figures import render_all

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "indtrend_panel.csv"
_ARTIFACT = _REPO / "artifacts" / "indtrend_gate.json"
_OUT = _REPO / "docs" / "figures"


def main() -> None:
    for p in render_all(_PANEL, _ARTIFACT, _OUT):
        print(f"Wrote {p.relative_to(_REPO).as_posix()} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
