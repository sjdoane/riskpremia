"""Rebuild the committed Study 9 industry-trend gate artifact (no network).

Reads the committed industry panel (and the Study 6 panel for the redundancy comparison), rebuilds
the deterministic gate artifact, writes it to `artifacts/indtrend_gate.json`, and prints it.
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.indtrend.fixtures import fixture_sha256, read_panel_frame
from riskpremia.indtrend.gate import build_gate_artifact, dump_gate_artifact
from riskpremia.xtrend.fixtures import read_panel_frame as read_xtrend_panel

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "indtrend_panel.csv"
_PROVENANCE = _REPO / "tests" / "data" / "indtrend_panel_sources.json"
_XTREND = _REPO / "tests" / "data" / "xtrend_panel.csv"
_ARTIFACT = _REPO / "artifacts" / "indtrend_gate.json"


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
    t = s.timing
    d = s.decomposition
    ctx = s.context
    print(f"Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")
    print(f"  window {artifact.first_scored_date}..{artifact.last_scored_date} "
          f"({t.raw_t} obs, eff T {t.effective_t})")
    print(f"  PRIMARY timing-difference PSR(0): {t.full_psr_zero:.4f} (bar {s.passes_psr}); "
          f"monthly {t.monthly_psr_zero:.4f}; ann Sharpe {t.ann_sharpe:.3f}")
    print(f"  decomposition: timing {d.timing_ann_return:+.2%}/yr + tilt {d.tilt_ann_return:+.2%}"
          f"/yr = deploy {d.deploy_ann_return:+.2%}/yr (vs the market)")
    print(f"  context: strategy Sharpe {ctx.strategy_ann_sharpe:.3f}, EW {ctx.ew_ann_sharpe:.3f}, "
          f"market {ctx.market_ann_sharpe:.3f}")
    print(f"  context: net-of-bill PSR {ctx.strategy_net_of_bill_psr_zero:.4f}; "
          f"deploy-diff PSR {ctx.deploy_diff_psr_zero:.4f}")
    print(f"  strategy: time in market {s.descriptive.time_in_market:.1%}, "
          f"mean turnover {s.descriptive.mean_turnover:.3f}, "
          f"max DD {s.descriptive.max_drawdown:.1%}, CAGR {s.descriptive.cagr_total:.1%}")
    print(f"  CPCV worst fold {s.cpcv.fold_min:.4f}, median {s.cpcv.fold_median:.4f}")
    for r in s.recency:
        print(f"  recency {r.name}: PSR(0) {r.psr_zero:.4f} (raw_t {r.raw_t})")
    print(f"  deflated Sharpe {list(s.deflation.trials)}: "
          f"{[round(x, 3) for x in s.deflation.dsr_by_trials]} (v_sr {s.deflation.v_sr:.6f})")
    for c in s.cost_sensitivity:
        print(f"  turnover {c.turnover_cost_per_side*1e4:.0f}bp: PSR(0) {c.full_psr_zero:.4f}")
    rd = s.redundancy
    print(f"  redundancy vs Study 6 (n {rd.n_aligned}): timing-diff corr "
          f"{rd.timing_vs_xtrend_corr:.3f}, active-bet corr {rd.active_bet_corr:.3f}, "
          f"combo Sharpe {rd.combo_ann_sharpe:.3f}")
    print(f"  VERDICT: {artifact.verdict.headline}")
    print(f"           {artifact.verdict.reason}")


if __name__ == "__main__":
    main()
