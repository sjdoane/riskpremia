"""Render the Study 8 volatility-managed figures from the committed panel and artifact (no network).

Needs the optional `figures` extra (matplotlib). The managed and unmanaged wealth paths are rebuilt
deterministically from the committed Study 6 panel, and the scorecard reads the committed artifact.
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.volmanaged.factors import load_artifact_dict
from riskpremia.volmanaged.figures import render_all, render_factor_asymmetry

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "xtrend_panel.csv"
_ARTIFACT = _REPO / "artifacts" / "volmanaged_gate.json"
_ASYMMETRY = _REPO / "artifacts" / "volmanaged_factor_asymmetry.json"
_OUT = _REPO / "docs" / "figures"


def main() -> None:
    paths = render_all(_PANEL, _ARTIFACT, _OUT)
    if _ASYMMETRY.exists():
        asym = load_artifact_dict(_ASYMMETRY)
        paths.append(render_factor_asymmetry(asym, _OUT / "volmanaged_factor_asymmetry.png"))
    for p in paths:
        print(f"Wrote {p.relative_to(_REPO).as_posix()} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
