"""Rebuild the committed Study 10 quality-tilt gate artifact (no network).

Reads the committed quality panel (and the Study 6 panel for the redundancy comparison), rebuilds
the deterministic gate artifact, writes it to `artifacts/quality_gate.json`, and prints the verdict.
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.quality.fixtures import fixture_sha256, read_panel_frame
from riskpremia.quality.gate import build_gate_artifact, dump_gate_artifact
from riskpremia.xtrend.fixtures import read_panel_frame as read_xtrend_panel

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "quality_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "quality_panel_sources.json"
_XTREND = _REPO / "tests" / "data" / "xtrend_panel.csv"
_ARTIFACT = _REPO / "artifacts" / "quality_gate.json"


def main() -> None:
    panel = read_panel_frame(_PANEL)
    xtrend_panel = read_xtrend_panel(_XTREND) if _XTREND.exists() else None
    artifact = build_gate_artifact(
        panel,
        panel_sha256=fixture_sha256(_PANEL),
        panel_relpath=_PANEL.relative_to(_REPO).as_posix(),
        provenance_sha256=fixture_sha256(_PROVENANCE),
        provenance_relpath=_PROVENANCE.relative_to(_REPO).as_posix(),
        xtrend_panel=xtrend_panel,
    )
    dump_gate_artifact(artifact, _ARTIFACT)
    s = artifact.score
    d = s.difference
    a = s.attribution
    print(f"Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")
    print(f"  window {artifact.data_start}..{artifact.data_end} "
          f"({d.raw_t} obs, eff T {d.effective_t})")
    print(f"  PRIMARY difference PSR(0): {d.full_psr_zero:.4f} (bar {s.passes_psr}); "
          f"gross (no cost) {d.gross_full_psr_zero:.4f}; monthly {d.monthly_psr_zero:.4f}; "
          f"ann Sharpe {d.ann_sharpe:.3f}")
    print(f"  decomposition: raw diff {s.decomposition.raw_difference_ann:+.2%}/yr, "
          f"FF5 alpha {s.decomposition.ff5_alpha_ann:+.2%}/yr (t {a.alpha_t_stat:.2f}), "
          f"RMW component {s.decomposition.rmw_component_ann:+.2%}/yr")
    print(f"  FF5 loadings: mkt {a.beta_mkt:.3f}, smb {a.beta_smb:.3f}, hml {a.beta_hml:.3f}, "
          f"rmw {a.beta_rmw:.3f}, cma {a.beta_cma:.3f} (rmw dominant {a.rmw_is_dominant})")
    print(f"  context: hi net-of-bill PSR {s.context.hi_net_of_bill_psr_zero:.4f}, "
          f"hi Sharpe {s.context.hi_ann_sharpe:.3f}, mkt Sharpe {s.context.market_ann_sharpe:.3f}")
    print(f"  CPCV worst fold {s.cpcv.fold_min:.4f}, median {s.cpcv.fold_median:.4f}")
    for r in s.recency:
        print(f"  recency {r.name}: PSR(0) {r.psr_zero:.4f} (raw_t {r.raw_t})")
    print(f"  deflated Sharpe {list(s.deflation.trials)}: "
          f"{[round(x, 3) for x in s.deflation.dsr_by_trials]} (v_sr {s.deflation.v_sr:.6f}); "
          f"passes@{artifact.knobs.min_trial_count} {s.deflation.passes_at_min_trials}")
    for c in s.cost_sensitivity:
        print(f"  differential {c.differential_annual:.2%}: PSR(0) {c.full_psr_zero:.4f}")
    print(f"  redundancy vs Study 6 (n {s.redundancy.n_aligned}): "
          f"diff corr {s.redundancy.difference_vs_xtrend_corr:.3f}")
    print(f"  make-money pass: {s.make_money_pass}")
    print(f"  VERDICT: {artifact.verdict.headline}")
    print(f"           {artifact.verdict.reason}")


if __name__ == "__main__":
    main()
