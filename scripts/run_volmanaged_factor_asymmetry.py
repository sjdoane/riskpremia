"""Rebuild the committed Study 8 factor-asymmetry artifact (no network).

Reads the committed factor panel and the Study 8 market gate artifact (for the market difference
PSR), scores each managed-minus-unmanaged factor difference, writes the asymmetry artifact to
`artifacts/volmanaged_factor_asymmetry.json`, and prints the finding.
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.volmanaged.factors import (
    build_asymmetry_artifact,
    dump_asymmetry_artifact,
    fixture_sha256,
    load_artifact_dict,
    read_factor_panel_frame,
)

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "volmanaged_factor_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "volmanaged_factor_sources.json"
_MARKET = _REPO / "artifacts" / "volmanaged_gate.json"
_ARTIFACT = _REPO / "artifacts" / "volmanaged_factor_asymmetry.json"


def main() -> None:
    panel = read_factor_panel_frame(_PANEL)
    market = load_artifact_dict(_MARKET)
    market_psr = float(market["score"]["difference"]["full_psr_zero"])
    artifact = build_asymmetry_artifact(
        panel,
        market_difference_psr=market_psr,
        panel_sha256=fixture_sha256(_PANEL),
        panel_relpath=_PANEL.relative_to(_REPO).as_posix(),
        provenance_sha256=fixture_sha256(_PROVENANCE),
        provenance_relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
    )
    dump_asymmetry_artifact(artifact, _ARTIFACT)
    print(f"Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")
    print(f"  window {artifact.data_start}..{artifact.data_end} ({artifact.n_scored_days} obs)")
    print(f"  market difference PSR(0) {artifact.market_difference_psr_zero:.4f} "
          f"(passes {artifact.market_passes})")
    for f in artifact.factors:
        print(f"  {f.name.upper():4s} PSR(0) full {f.difference_full_psr_zero:.4f} / "
              f"expanding {f.difference_expanding_psr_zero:.4f} (pass {f.passes}); "
              f"gross {f.gross_uncapped_ann_return:+.2%}/yr -> net {f.net_ann_return:+.2%}")
    print(f"  {artifact.n_factors_failing}/{len(artifact.factors)} factors fail; "
          f"asymmetry confirmed {artifact.asymmetry_confirmed}")
    print(f"  FINDING: {artifact.finding}")


if __name__ == "__main__":
    main()
