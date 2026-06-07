"""Regenerate the Study 6 cross-asset trend figures from the committed artifact.

No network and no data bundle: it loads `artifacts/xtrend_gate.json` and renders the PNGs
into `docs/figures/`. Requires the `figures` extra (matplotlib):

  $env:PYTHONIOENCODING="utf-8"
  C:\\Users\\SamJD\\.venvs\\riskpremia\\Scripts\\python.exe -m scripts.regenerate_xtrend_figures

The JSON artifact, not the PNG bytes, is the audited reproducibility contract; this script
only renders it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from riskpremia.xtrend.figures import render_all

_REPO = Path(__file__).resolve().parents[1]
_ARTIFACT = _REPO / "artifacts" / "xtrend_gate.json"
_FIGURES = _REPO / "docs" / "figures"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the Study 6 figures from the artifact.")
    parser.add_argument("--artifact", default=str(_ARTIFACT))
    parser.add_argument("--out", default=str(_FIGURES))
    args = parser.parse_args()

    paths = render_all(Path(args.artifact), Path(args.out))
    for p in paths:
        print(f"Wrote {p.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
