"""Rebuild the committed Study 8 volatility-managed market gate artifact (no network).

Reads the committed Study 6 daily panel (the Kenneth French daily market total return and the
one-month bill; the managed-market primary needs no new data) and its provenance, rebuilds the
deterministic gate artifact, writes it to `artifacts/volmanaged_gate.json`, and prints the verdict.
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.volmanaged.gate import build_gate_artifact, dump_gate_artifact
from riskpremia.xtrend.fixtures import fixture_sha256, read_panel_frame

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "xtrend_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "xtrend_panel_sources.json"
_ARTIFACT = _REPO / "artifacts" / "volmanaged_gate.json"


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
    d = s.difference
    print(f"Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")
    print(f"  window {artifact.first_scored_date}..{artifact.last_scored_date} "
          f"({d.raw_t} obs, eff T {d.effective_t})")
    print(f"  c {s.descriptive.c_value:.4g}, mean weight {s.descriptive.mean_weight:.3f}, "
          f"max {s.descriptive.max_weight:.2f}, capped {s.descriptive.frac_capped:.1%}, "
          f"levered {s.descriptive.frac_levered:.1%}")
    print(f"  PRIMARY difference PSR(0): {d.full_psr_zero:.4f} (bar {s.passes_psr}); "
          f"monthly {d.monthly_psr_zero:.4f} ({d.n_monthly_obs} mo); ann Sharpe {d.ann_sharpe:.3f}")
    print(f"  context: managed Sharpe {s.context.managed_ann_sharpe:.3f} "
          f"(PSR {s.context.managed_psr_zero:.4f}), unmanaged Sharpe "
          f"{s.context.unmanaged_ann_sharpe:.3f} (PSR {s.context.unmanaged_psr_zero:.4f})")
    g = s.gross
    print(f"  gross timing alpha {g.uncapped_costless_ann_return:+.2%}/yr (Sharpe "
          f"{g.uncapped_costless_ann_sharpe:.3f}) -> cap drag {g.cap_drag_ann_return:+.2%} -> "
          f"cost drag {g.cost_drag_ann_return:+.2%} -> net {g.net_ann_return:+.2%}/yr")
    print(f"  expanding-c difference PSR(0): {s.expanding_c.full_psr_zero:.4f} "
          f"(mean weight {s.expanding_c.mean_weight:.3f})")
    print(f"  CPCV worst fold {s.cpcv.fold_min:.4f}, median {s.cpcv.fold_median:.4f}")
    for r in s.recency:
        print(f"  recency {r.name}: PSR(0) {r.psr_zero:.4f} (raw_t {r.raw_t})")
    print(f"  deflated Sharpe {list(s.deflation.trials)}: "
          f"{[round(x, 3) for x in s.deflation.dsr_by_trials]} (v_sr {s.deflation.v_sr:.6f})")
    for c in s.cap_sensitivity:
        print(f"  cap {c.cap:.1f}: diff PSR(0) {c.full_psr_zero:.4f} (mean w {c.mean_weight:.3f})")
    for f in s.financing_sensitivity:
        print(f"  financing {f.spread_annual:.1%}: difference PSR(0) {f.full_psr_zero:.4f}")
    rd = s.redundancy
    print(f"  redundancy vs Study 6 (n {rd.n_aligned}): level {rd.managed_vs_xtrend_corr:.3f}, "
          f"diff {rd.difference_vs_xtrend_corr:.3f}, active-bet {rd.active_bet_corr:.3f}")
    print(f"  combo Sharpe {rd.combo_ann_sharpe:.3f} vs managed {rd.managed_ann_sharpe:.3f} / "
          f"xtrend {rd.xtrend_ann_sharpe:.3f}")
    print(f"  VERDICT: {artifact.verdict.headline}")
    print(f"           {artifact.verdict.reason}")


if __name__ == "__main__":
    main()
