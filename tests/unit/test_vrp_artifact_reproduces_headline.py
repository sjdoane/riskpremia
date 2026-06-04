"""The M1 reproducibility gate (ADR 0004 PR5b): the COMMITTED artifact headline is
reproducible from a clone, OFFLINE, from the COMMITTED fixtures, and the fixtures are
tamper-evident via the snapshot manifest. This is the proof that backs the published
VRP number; it runs in CI (no network).

Cross-platform determinism (this build runs on Windows; CI on Linux): the point
estimates are pure `statistics.fmean` / `median` / comparisons over identical inputs
(the fixtures store exact Decimal strings), so they reproduce bit-for-bit. The
bootstrap CI and the Politis-White block length flow through libm (`log10`, `sqrt`,
cube root); those are not guaranteed bit-identical across platforms (the in-repo
`analytics/sharpe.py` `_phi` clamp documents `math.erf` differing between Linux and
Windows in the last place), so they are asserted at a looser 1e-6 relative tolerance.
"""

from __future__ import annotations

import math
from pathlib import Path

from riskpremia.data.manifest import compute_sha256, load_manifest, verify_snapshot
from riskpremia.vrp.artifact import load_artifact
from riskpremia.vrp.fixtures import read_dvol_csv, read_spot_csv
from riskpremia.vrp.measurement import build_vrp_frame, vrp_headline

_REPO = Path(__file__).resolve().parents[2]
_DVOL_FIXTURE = _REPO / "tests" / "data" / "deribit_dvol_btc.csv"
_SPOT_FIXTURE = _REPO / "tests" / "data" / "binance_spot_btcusdt_1d.csv"
_ARTIFACT = _REPO / "artifacts" / "vrp_measurement.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"

# Point estimates (fmean/median/comparison over identical inputs) reproduce exactly;
# bootstrap-derived quantities tolerate cross-platform libm variation.
_EXACT = 1e-12
_LIBM_REL = 1e-6


def test_committed_fixtures_reproduce_the_committed_headline() -> None:
    artifact = load_artifact(_ARTIFACT)
    dvol = read_dvol_csv(_DVOL_FIXTURE)
    spot = read_spot_csv(_SPOT_FIXTURE)
    frame = build_vrp_frame(dvol, spot, window_days=artifact.window_days)
    rebuilt = vrp_headline(
        frame,
        window_days=artifact.window_days,
        seed=artifact.inference.seed,
        n_boot=artifact.inference.n_boot,
    )
    h = artifact.headline

    # Integer counts: exact.
    assert rebuilt.n_forward_obs == h.n_forward_obs
    assert rebuilt.n_strided == h.n_strided
    assert rebuilt.window_days == h.window_days

    # Point estimates: bit-reproducible across platforms.
    for field in (
        "mean_vrp_forward", "mean_phase_median", "mean_phase_min", "mean_phase_max",
        "frac_positive", "mean_vrp_pre_etf", "mean_vrp_post_etf", "mean_vol_spread_forward",
    ):
        got, want = getattr(rebuilt, field), getattr(h, field)
        assert math.isclose(got, want, rel_tol=0, abs_tol=_EXACT), (
            f"{field}: rebuilt {got} != committed {want}"
        )

    # Bootstrap CI + Politis-White block length: looser libm tolerance.
    assert math.isclose(rebuilt.ci_low, h.ci_low, rel_tol=_LIBM_REL)
    assert math.isclose(rebuilt.ci_high, h.ci_high, rel_tol=_LIBM_REL)
    assert math.isclose(rebuilt.pw_block_length, h.pw_block_length, rel_tol=_LIBM_REL)
    # effective_t is floor(T / block); a last-place block-length difference could flip it by 1.
    assert abs(rebuilt.effective_t - h.effective_t) <= 1.0


def test_headline_is_a_statistically_real_positive_premium() -> None:
    # The published claim: a positive premium whose overlap-honest CI clears zero.
    h = load_artifact(_ARTIFACT).headline
    assert h.mean_phase_median > 0.0
    assert h.frac_positive > 0.5
    assert h.ci_low > 0.0


def test_committed_fixtures_are_tamper_evident_via_manifest() -> None:
    entries = {e.name: e for e in load_manifest(_MANIFEST)}
    assert {"deribit-dvol-BTC", "binance-vision-spot-BTCUSDT-1d"} <= set(entries)
    for entry in entries.values():
        if entry.kind == "reproducibility_fixture":
            verify_snapshot(entry, _REPO)  # raises SnapshotMismatchError on drift


def test_artifact_fingerprint_matches_committed_fixtures() -> None:
    fp = load_artifact(_ARTIFACT).fingerprint
    assert fp.dvol_sha256 == compute_sha256(_DVOL_FIXTURE)
    assert fp.spot_sha256 == compute_sha256(_SPOT_FIXTURE)
