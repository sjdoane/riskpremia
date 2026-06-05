"""The CTREND PR3 gate reproduces offline from the committed daily panel.

The full forecast path flows through scikit-learn and libm, so DSR and means are compared
with a cross-platform tolerance. Verdict-level assertions are robust: the retail long-only
DSR is far below the 0.95 bar, and the academic long-short comparison also fails the
conservative CPCV-min gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from riskpremia.ctrend.fixtures import daily_panel_content_sha256, read_daily_panel
from riskpremia.ctrend.gate import build_gate_artifact, load_gate_artifact
from riskpremia.ctrend.signal import ctrend_forecasts
from riskpremia.ctrend.universe import build_weekly_panel, pit_eligible
from riskpremia.data.manifest import load_manifest, verify_snapshot

_REPO = Path(__file__).resolve().parents[2]
_PANEL = _REPO / "tests" / "data" / "ctrend_daily_panel_usdt.csv.gz"
_ARTIFACT = _REPO / "artifacts" / "ctrend_gate.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"

_HAVE = _PANEL.exists() and _ARTIFACT.exists()
pytestmark = pytest.mark.skipif(not _HAVE, reason="the committed CTREND gate is not built yet")

_DSR_ABS_TOL = 5e-2
_MEAN_ABS_TOL = 5e-3


def _rebuild():
    committed = load_gate_artifact(_ARTIFACT)
    daily = read_daily_panel(_PANEL)
    weekly = pit_eligible(
        build_weekly_panel(daily),
        top_n=committed.knobs.top_n,
        lookback_weeks=committed.knobs.lookback_weeks,
        min_history_weeks=committed.knobs.min_history_weeks,
    )
    forecasts = ctrend_forecasts(
        daily,
        weekly,
        fit_window=committed.knobs.fit_window,
        n_quintiles=committed.knobs.n_quintiles,
    )
    return build_gate_artifact(
        forecasts,
        panel_sha256=daily_panel_content_sha256(_PANEL),
        n_panel_rows=daily.height,
        panel_relpath=committed.fingerprint.panel_relpath,
        knobs=committed.knobs,
    )


def test_committed_panel_reproduces_the_ctrend_gate() -> None:
    committed = load_gate_artifact(_ARTIFACT)
    rebuilt = _rebuild()

    assert rebuilt.fingerprint.panel_sha256 == committed.fingerprint.panel_sha256
    assert rebuilt.fingerprint.n_panel_rows == committed.fingerprint.n_panel_rows
    assert rebuilt.fingerprint.forecast_sha256 == committed.fingerprint.forecast_sha256
    assert rebuilt.retail_long_only.raw_t == committed.retail_long_only.raw_t
    assert len(rebuilt.trial_records) == committed.knobs.trial_naive_effective_n
    assert rebuilt.retail_long_only.n_effective == committed.retail_long_only.n_effective
    assert rebuilt.retail_long_only.cpcv_min_dsr == pytest.approx(
        committed.retail_long_only.cpcv_min_dsr, abs=_DSR_ABS_TOL
    )
    assert rebuilt.retail_long_only.mean_net == pytest.approx(
        committed.retail_long_only.mean_net, abs=_MEAN_ABS_TOL
    )
    assert rebuilt.academic_long_short.cpcv_min_dsr == pytest.approx(
        committed.academic_long_short.cpcv_min_dsr, abs=_DSR_ABS_TOL
    )


def test_committed_verdict_is_the_pre_registered_retail_null() -> None:
    artifact = load_gate_artifact(_ARTIFACT)
    assert artifact.verdict.retail_non_viable is True
    assert artifact.retail_long_only.passes is False
    assert artifact.retail_long_only.cpcv_min_dsr < artifact.viability_bar
    assert artifact.retail_long_only.mean_net < 0.0
    # The academic comparison also fails the conservative CPCV-min gate, so the paper
    # comparison is not being used to rescue retail deployment.
    assert artifact.verdict.academic_non_viable is True
    assert artifact.academic_long_short.cpcv_min_dsr < artifact.viability_bar


def test_ctrend_panel_fixture_is_tamper_evident() -> None:
    entries = {e.name: e for e in load_manifest(_MANIFEST)}
    assert "ctrend-daily-panel-usdt" in entries
    verify_snapshot(entries["ctrend-daily-panel-usdt"], _REPO)
    artifact = load_gate_artifact(_ARTIFACT)
    assert artifact.fingerprint.panel_sha256 == daily_panel_content_sha256(_PANEL)
