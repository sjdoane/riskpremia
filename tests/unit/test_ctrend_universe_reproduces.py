"""The CTREND universe reproducibility gate (ADR 0005 PR1): the COMMITTED universe
artifact is reproducible OFFLINE from the committed daily panel, the panel is
tamper-evident, and the survivorship / point-in-time properties hold on the real data.
Runs in CI (no network), mirroring `tests/unit/test_vrp_gate_reproduces.py`.

The panel-derived fields (the eligible-by-week breadth, the ever-eligible count, the
delisting proof, the row/week counts, the fingerprint) are pure functions of the committed
daily panel, so they are rebuilt and asserted equal to the committed artifact. The
build-time provenance fields (the enumerated count, the excluded list) are recorded, not
re-derived offline.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from riskpremia.ctrend.artifact import KNOWN_DELISTED, UniverseArtifact, load_artifact
from riskpremia.ctrend.fixtures import daily_panel_content_sha256, read_daily_panel
from riskpremia.ctrend.universe import (
    build_weekly_panel,
    eligible_count_per_week,
    pit_eligible,
)
from riskpremia.data.manifest import load_manifest, verify_snapshot

_REPO = Path(__file__).resolve().parents[2]
_PANEL = _REPO / "tests" / "data" / "ctrend_daily_panel_usdt.csv.gz"
_ARTIFACT = _REPO / "artifacts" / "ctrend_universe.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"

_HAVE_ARTIFACT = _PANEL.exists() and _ARTIFACT.exists()
pytestmark = pytest.mark.skipif(
    not _HAVE_ARTIFACT, reason="the committed CTREND panel/artifact are not built yet"
)


def _rebuild_flagged(art: UniverseArtifact):  # type: ignore[no-untyped-def]
    daily = read_daily_panel(_PANEL)
    weekly = build_weekly_panel(daily)
    flagged = pit_eligible(
        weekly,
        top_n=art.top_n,
        lookback_weeks=art.lookback_weeks,
        min_history_weeks=art.min_history_weeks,
    )
    return flagged, daily


def test_committed_panel_reproduces_the_artifact() -> None:
    art = load_artifact(_ARTIFACT)
    flagged, daily = _rebuild_flagged(art)

    # the per-week eligible breadth reproduces exactly (the universe at each week t)
    by_week = eligible_count_per_week(flagged)
    assert tuple(str(w) for w in by_week["week_end"].to_list()) == art.eligible_by_week.week_end
    assert tuple(int(n) for n in by_week["n_eligible"].to_list()) == art.eligible_by_week.n_eligible

    # the ever-eligible count, the panel shape, and the week count reproduce
    ever = flagged.filter(flagged["eligible"])["symbol"].n_unique()
    assert ever == art.n_ever_eligible
    assert daily.height == art.fingerprint.n_panel_rows
    assert daily["symbol"].n_unique() == art.n_symbols_in_committed_panel
    assert flagged["week_end"].n_unique() == art.n_weeks


def test_panel_is_tamper_evident() -> None:
    art = load_artifact(_ARTIFACT)
    # the artifact pins the decompressed-CONTENT SHA (cross-platform stable)
    assert art.fingerprint.panel_sha256 == daily_panel_content_sha256(_PANEL)
    # the manifest stamps the committed .gz blob's FILE SHA (verify_snapshot hashes the file)
    entries = {e.name: e for e in load_manifest(_MANIFEST)}
    assert "ctrend-daily-panel-usdt" in entries
    verify_snapshot(entries["ctrend-daily-panel-usdt"], _REPO)  # raises on drift


def test_delisting_proof_shows_dead_coins_retained() -> None:
    # Survivorship proof on the real committed panel: at least one famously-delisted coin
    # is present in the panel AND stopped trading before the window end (a dead coin is
    # retained with a historical last week, not silently dropped).
    art = load_artifact(_ARTIFACT)
    proof = {p.symbol: p for p in art.delisting_proof}
    assert set(proof) == set(KNOWN_DELISTED)
    present = [p for p in art.delisting_proof if p.present]
    assert present, "expected at least one known-delisted coin in the liquid committed panel"
    window_end = date.fromisoformat(art.window_end)
    stopped_early = [
        p
        for p in present
        if p.last_week is not None and date.fromisoformat(p.last_week) < window_end
    ]
    assert stopped_early, (
        "expected at least one delisted coin whose last trading week precedes the window end "
        "(the survivorship-completeness proof)"
    )


def test_committed_verdict_properties() -> None:
    # The PR1 deliverable invariants the downstream study relies on.
    art = load_artifact(_ARTIFACT)
    assert art.top_n <= art.n_max_committed  # the committed trim covers the study's top-N
    assert art.n_symbols_excluded > 0  # stablecoins / leveraged tokens were dropped
    assert art.n_symbols_in_committed_panel <= art.n_symbols_enumerated
    # recent weeks should fill the liquid universe to ~top_n (breadth exists post-2021)
    recent = art.eligible_by_week.n_eligible[-1]
    assert recent >= min(art.top_n, 50)
