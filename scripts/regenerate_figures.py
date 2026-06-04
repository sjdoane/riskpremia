"""Regenerate the VRP figures from the committed artifact (ADR 0004 PR5b).

No network and no data bundle: it loads `artifacts/vrp_measurement.json` and renders
the PNGs into `docs/figures/`, mirroring the sibling project's "figures regenerate
from the committed artifact" pattern. Requires the `figures` extra (matplotlib):

  $env:PYTHONIOENCODING="utf-8"
  C:\\Users\\SamJD\\.venvs\\riskpremia\\Scripts\\python.exe -m scripts.regenerate_figures

The artifact (not the PNG bytes) is the audited reproducibility contract; this script
only renders it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from riskpremia.vrp.artifact import load_artifact
from riskpremia.vrp.figures import render_all

_REPO = Path(__file__).resolve().parents[1]
_ARTIFACT = _REPO / "artifacts" / "vrp_measurement.json"
_FIGURES = _REPO / "docs" / "figures"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the VRP figures from the artifact.")
    parser.add_argument("--artifact", default=str(_ARTIFACT))
    parser.add_argument("--out", default=str(_FIGURES))
    args = parser.parse_args()

    artifact = load_artifact(Path(args.artifact))
    paths = render_all(artifact, Path(args.out))
    for p in paths:
        print(f"Wrote {p.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
