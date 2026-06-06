"""Rebuild the committed Study 6 cross-asset trend gate artifact (no network).

Reads the committed daily panel and its provenance, rebuilds the deterministic gate
artifact, writes it to `artifacts/xtrend_gate.json`, and prints the verdict.
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.xtrend.fixtures import fixture_sha256, read_panel_frame
from riskpremia.xtrend.gate import build_gate_artifact, dump_gate_artifact

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "xtrend_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "xtrend_panel_sources.json"
_ARTIFACT = _REPO / "artifacts" / "xtrend_gate.json"


def main() -> None:
    panel = read_panel_frame(_PANEL)
    artifact = build_gate_artifact(
        panel,
        panel_sha256=fixture_sha256(_PANEL),
        panel_relpath=_PANEL.relative_to(_REPO).as_posix(),
        provenance_sha256=fixture_sha256(_PROVENANCE),
        provenance_relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
    )
    dump_gate_artifact(artifact, _ARTIFACT)
    s = artifact.score
    print(f"Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")
    print(f"  window {artifact.first_scored_date}..{artifact.last_scored_date} ({s.raw_t} obs)")
    print(f"  months {artifact.n_months}, time in market {s.time_in_market:.1%}")
    print(f"  mean excess/day {s.mean_excess:.6f}, ann excess vol {s.annualized_excess_vol:.1%}")
    print(f"  full-sample conditional PSR(0): {s.full_psr_zero:.4f} (bar {s.passes_psr})")
    print(f"  monthly non-overlapping PSR(0): {s.monthly_psr_zero:.4f} ({s.n_monthly_obs} months)")
    for a in s.sleeve_attribution:
        print(f"  sleeve {a.sleeve} standalone PSR(0): {a.psr_zero:.4f} (sr_hat {a.sr_hat:.5f})")
    print(f"  CPCV worst fold PSR(0): {s.cpcv.fold_min:.4f}, median {s.cpcv.fold_median:.4f}")
    for r in s.recency:
        print(f"  recency {r.name}: PSR(0) {r.psr_zero:.4f} (raw_t {r.raw_t})")
    print(f"  deflated Sharpe ladder {list(s.deflation.trials)}: "
          f"{[round(x, 3) for x in s.deflation.dsr_by_trials]} (v_sr {s.deflation.v_sr:.6f})")
    print(f"  net excess gain {s.compounded_net_excess_gain:.1%}, "
          f"net total gain {s.compounded_net_total_gain:.1%}, bill carry {s.bill_carry_gain:.1%}")
    print(f"  max drawdown {s.max_drawdown:.1%}, cost share {s.total_cost_share:.1%}, "
          f"CAGR {s.cagr_total:.1%}")
    print(f"  VERDICT: {artifact.verdict.headline}")
    print(f"           {artifact.verdict.reason}")


if __name__ == "__main__":
    main()
