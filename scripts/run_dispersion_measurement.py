"""Rebuild the committed Study 7 funding-dispersion artifact (no network).

Reads the committed daily dispersion series and its provenance, rebuilds the deterministic
measurement artifact (bootstrap CIs, the regime split, the decay), writes it to
`artifacts/funding_dispersion.json`, and prints the headline.
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.dispersion.artifact import build_artifact, dump_artifact
from riskpremia.dispersion.fixtures import fixture_sha256, read_series_frame

_REPO = Path(__file__).resolve().parents[1]
_SERIES = _REPO / "tests" / "data" / "funding_dispersion_series.csv"
_PROVENANCE = _REPO / "tests" / "data" / "funding_dispersion_sources.json"
_ARTIFACT = _REPO / "artifacts" / "funding_dispersion.json"


def main() -> None:
    series = read_series_frame(_SERIES)
    artifact = build_artifact(
        series,
        series_sha256=fixture_sha256(_SERIES),
        series_relpath=_SERIES.relative_to(_REPO).as_posix(),
        provenance_sha256=fixture_sha256(_PROVENANCE),
        provenance_relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
    )
    dump_artifact(artifact, _ARTIFACT)
    a = artifact
    print(f"Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")
    print(f"  window {a.data_start}..{a.data_end} ({a.n_days} grid days)")
    cov = a.coverage
    print(f"  coverage: mean {cov.mean_n_funded:.1f}/{cov.mean_n_eligible:.1f} funded "
          f"({cov.mean_coverage_ratio:.0%}; min {cov.min_coverage_ratio:.0%})")
    iq = a.iqr_full
    print(f"  equal-weight IQR (annualized funding): mean {iq.mean:.3f} "
          f"95% CI [{iq.ci_low:.3f}, {iq.ci_high:.3f}] (eff T {iq.effective_t})")
    rg = a.iqr_regime
    print(f"  regime: pre-ETF {rg.pre_mean:.3f}, post-ETF {rg.post_mean:.3f}, "
          f"diff {rg.difference:+.3f} 95% CI [{rg.diff_ci_low:+.3f}, {rg.diff_ci_high:+.3f}]")
    print(f"  decay slope {a.iqr_decay.slope_per_year:+.3f}/yr 95% CI "
          f"[{a.iqr_decay.ci_low:+.3f}, {a.iqr_decay.ci_high:+.3f}]")
    print(f"  secondary std {a.std_full_mean:.3f}, winsorized std {a.winsor_std_full_mean:.3f}")
    print(f"  secondary gross sort premium {a.sort_premium.mean:+.3f} 95% CI "
          f"[{a.sort_premium.ci_low:+.3f}, {a.sort_premium.ci_high:+.3f}] (non-capturable)")
    print(f"  HEADLINE: {a.headline}")


if __name__ == "__main__":
    main()
