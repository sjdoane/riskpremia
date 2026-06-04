"""The committed VRP artifact (ADR 0004 PR5b): the build invariants, the alignment
diagnostic, regime/headline consistency, and the deterministic JSON round-trip."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from riskpremia.data.records import DvolRecord, SpotPriceRecord
from riskpremia.vrp.artifact import (
    DatasetFingerprint,
    artifact_from_dict,
    artifact_to_json,
    build_artifact,
    dump_artifact,
    load_artifact,
)
from riskpremia.vrp.measurement import build_vrp_frame, vrp_headline

_W = 5
_SEED = 20260604
_NBOOT = 400


def _dvol_and_spot(n: int) -> tuple[list[DvolRecord], list[SpotPriceRecord]]:
    d0 = datetime(2023, 12, 20, tzinfo=UTC)  # spans the 2024-01-11 ETF boundary
    dvol = [DvolRecord("BTC", d0 + timedelta(days=i), *(Decimal("80"),) * 4) for i in range(n)]
    closes, level = [], 100.0
    for i in range(n):
        level *= math.exp(0.005 * (1 + (i % 4)))
        closes.append(level)
    spot = [
        SpotPriceRecord("binance_spot", "BTCUSDT", "USDT", d0 + timedelta(days=i),
                        Decimal(str(closes[i])))
        for i in range(n)
    ]
    return dvol, spot


def _build() -> tuple:
    dvol, spot = _dvol_and_spot(80)
    frame = build_vrp_frame(dvol, spot, window_days=_W)
    headline = vrp_headline(frame, window_days=_W, seed=_SEED, n_boot=_NBOOT)
    fp = DatasetFingerprint("a" * 64, "b" * 64, len(dvol), len(spot), "x.csv", "y.csv")
    artifact = build_artifact(
        frame, headline, currency="BTC", window_days=_W, seed=_SEED, n_boot=_NBOOT,
        fingerprint=fp, n_dvol_days=len(dvol), n_spot_days=len(spot),
    )
    return artifact, frame, headline


def test_artifact_series_columns_are_aligned() -> None:
    artifact, frame, _ = _build()
    s = artifact.series
    n = frame.height
    assert len(s.date) == n
    assert len(s.dvol_vol_pct) == n
    assert len(s.realized_vol_pct_forward) == n
    assert len(s.vrp_forward) == n
    assert len(s.regime) == n
    # vrp_forward is null exactly where realized_vol_pct_forward is null (the tail).
    for vf, rv in zip(s.vrp_forward, s.realized_vol_pct_forward, strict=True):
        assert (vf is None) == (rv is None)


def test_alignment_diagnostic_counts() -> None:
    artifact, frame, headline = _build()
    a = artifact.alignment
    assert a.n_aligned_rows == frame.height
    assert a.n_forward_obs == headline.n_forward_obs
    assert a.n_realized_forward_nonnull == int(frame["rv_forward"].is_not_null().sum())
    assert a.n_dvol_days == 80 and a.n_spot_days == 80


def test_regime_means_match_headline() -> None:
    artifact, _, headline = _build()
    regimes = {r.name: r for r in artifact.regimes}
    assert {"pre_etf", "post_etf"} <= set(regimes)
    # The regime decomposition must agree with the headline's regime means exactly.
    assert math.isclose(regimes["pre_etf"].mean_vrp_forward, headline.mean_vrp_pre_etf, rel_tol=0,
                        abs_tol=1e-12)
    assert math.isclose(regimes["post_etf"].mean_vrp_forward, headline.mean_vrp_post_etf, rel_tol=0,
                        abs_tol=1e-12)


def test_inference_block_pins_regeneration_knobs() -> None:
    artifact, _, headline = _build()
    inf = artifact.inference
    assert inf.seed == _SEED and inf.n_boot == _NBOOT
    assert inf.expected_block_length == max(2.0, headline.pw_block_length)
    assert artifact.caveats  # the binding honesty caveats travel with the numbers


def test_json_roundtrip_is_exact() -> None:
    artifact, _, _ = _build()
    restored = artifact_from_dict(json.loads(artifact_to_json(artifact)))
    assert restored == artifact  # attrs equality, round-trip-exact floats


def test_json_is_deterministic_and_sorted(tmp_path: Path) -> None:
    artifact, _, _ = _build()
    text1 = artifact_to_json(artifact)
    text2 = artifact_to_json(artifact)
    assert text1 == text2  # stable across calls
    parsed = json.loads(text1)
    # sort_keys=True: top-level keys are emitted in sorted order.
    assert list(parsed.keys()) == sorted(parsed.keys())
    assert text1.endswith("\n")
    path = tmp_path / "artifact.json"
    dump_artifact(artifact, path)
    assert load_artifact(path) == artifact
    assert b"\r" not in path.read_bytes()  # LF only
