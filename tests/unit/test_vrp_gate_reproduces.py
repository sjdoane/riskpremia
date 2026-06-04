"""The Layer-ii gate reproducibility gate (ADR 0004 PR5f): the COMMITTED gate artifact is
reproducible OFFLINE from the committed straddle-entries + spot fixtures, and the verdict
is the pre-registered NON-VIABLE null. Runs in CI (no network).

Determinism mirrors the Layer-i reproduction: the tail table and the peso are pure
fmean/min/sum over identical inputs (bit-reproducible cross-platform); the Deflated Sharpe
flows through libm (`sharpe.py`), so it is asserted at a looser tolerance. The verdict is a
boolean dominated by a DSR of ~0.30 (far below 0.95) and a tail of ~2.7x margin, so it is
robust to any last-place drift."""

from __future__ import annotations

import math
from pathlib import Path

from riskpremia.data.manifest import compute_sha256, load_manifest, verify_snapshot
from riskpremia.execution.cost import DERIBIT_OPTION
from riskpremia.vrp.fixtures import read_spot_close_by_date, read_straddle_entries_csv
from riskpremia.vrp.gate import StraddleEntry, build_gate_artifact, load_gate_artifact

_REPO = Path(__file__).resolve().parents[2]
_ENTRIES = _REPO / "tests" / "data" / "vrp_straddle_entries.csv"
_SPOT = _REPO / "tests" / "data" / "binance_spot_btcusdt_1d.csv"
_ARTIFACT = _REPO / "artifacts" / "vrp_short_variance_gate.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"
_WINDOW_MONTHS = 42


def _rebuild():  # type: ignore[no-untyped-def]
    raw = read_straddle_entries_csv(_ENTRIES)
    spot = read_spot_close_by_date(_SPOT)
    entries = [
        StraddleEntry(entry_date=d, call=c, put=p, terminal_underlying=spot[c.expiry.date()],
                      hold_hours=h)
        for d, h, c, p in raw
    ]
    return build_gate_artifact(
        entries, DERIBIT_OPTION, currency="BTC", n_entries_total=_WINDOW_MONTHS,
        n_entries_dropped=_WINDOW_MONTHS - len(entries),
        entries_sha256=compute_sha256(_ENTRIES), spot_sha256=compute_sha256(_SPOT),
    )


def test_committed_fixtures_reproduce_the_gate() -> None:
    committed = load_gate_artifact(_ARTIFACT)
    rebuilt = _rebuild()

    assert rebuilt.verdict.non_viable == committed.verdict.non_viable
    assert rebuilt.n_entries_used == committed.n_entries_used
    assert math.isclose(rebuilt.verdict.deflated_sharpe, committed.verdict.deflated_sharpe,
                        rel_tol=1e-6)
    # the tail table + peso are pure float arithmetic: bit-reproducible
    by_name = {r.name: r for r in rebuilt.regimes}
    for cr in committed.regimes:
        rr = by_name[cr.name]
        assert rr.n == cr.n
        assert math.isclose(rr.worst_loss_coin, cr.worst_loss_coin, rel_tol=0, abs_tol=1e-12)
        assert math.isclose(rr.mean_net_coin, cr.mean_net_coin, rel_tol=0, abs_tol=1e-12)
    for rp, cp in zip(rebuilt.peso_shocks, committed.peso_shocks, strict=True):
        assert rp.shock_pct == cp.shock_pct
        assert math.isclose(rp.loss_coin, cp.loss_coin, rel_tol=0, abs_tol=1e-12)


def test_committed_verdict_is_the_pre_registered_null() -> None:
    a = load_gate_artifact(_ARTIFACT)
    assert a.verdict.non_viable is True
    assert a.verdict.deflated_sharpe < 0.95  # the necessary condition fails
    # the tail is account-ending: the worst loss (in-sample or peso) exceeds the margin
    assert a.verdict.worst_loss_margin_mult > 1.0
    assert all(p.loss_margin_mult > 1.0 for p in a.peso_shocks)  # both cited crashes wipe out


def test_entries_fixture_is_tamper_evident() -> None:
    entries = {e.name: e for e in load_manifest(_MANIFEST)}
    assert "vrp-straddle-entries" in entries
    verify_snapshot(entries["vrp-straddle-entries"], _REPO)  # raises on drift
    a = load_gate_artifact(_ARTIFACT)
    assert a.entries_sha256 == compute_sha256(_ENTRIES)
    assert a.spot_sha256 == compute_sha256(_SPOT)
