"""Regenerate the Study 7 funding-dispersion figures from the committed series and artifact.

No network: it reads `tests/data/funding_dispersion_series.csv` and
`artifacts/funding_dispersion.json` and renders the PNGs into `docs/figures/`. Requires the
`figures` extra (matplotlib). The committed series and artifact, not the PNG bytes, are the
audited contract; this script only renders them.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from riskpremia.dispersion.figures import render_all

_REPO = Path(__file__).resolve().parents[1]
_SERIES = _REPO / "tests" / "data" / "funding_dispersion_series.csv"
_ARTIFACT = _REPO / "artifacts" / "funding_dispersion.json"
_FIGURES = _REPO / "docs" / "figures"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the Study 7 figures from the artifact.")
    parser.add_argument("--series", default=str(_SERIES))
    parser.add_argument("--artifact", default=str(_ARTIFACT))
    parser.add_argument("--out", default=str(_FIGURES))
    args = parser.parse_args()

    paths = render_all(Path(args.series), Path(args.artifact), Path(args.out))
    for p in paths:
        print(f"Wrote {p.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
