"""Run the Layer-ii short-variance gate from the committed fixtures (ADR 0004 PR5f).

Offline + reproducible: it reads the committed monthly straddle-entries fixture and the
committed spot fixture (the realized expiry underlyings, looked up by expiry date), builds
the per-month delta-hedged short-straddle P&L, scores the gate, writes the committed gate
artifact, and prints the verdict, the regime-conditional tail-loss table, and the cited
peso shocks. No network (re-gather the entries with `scripts.build_vrp_entries`).

  $env:PYTHONIOENCODING="utf-8"
  C:\\Users\\SamJD\\.venvs\\riskpremia\\Scripts\\python.exe -m scripts.run_vrp_gate

The headline of the study is the Layer-i MEASUREMENT plus this tail table, never a
short-vol Sharpe; the pre-registered expected outcome is a cost/peso-bounded honest null.
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.data.manifest import compute_sha256
from riskpremia.execution.cost import DERIBIT_OPTION
from riskpremia.vrp.errors import VrpError
from riskpremia.vrp.fixtures import read_spot_close_by_date, read_straddle_entries_csv
from riskpremia.vrp.gate import StraddleEntry, build_gate_artifact, dump_gate_artifact

_REPO = Path(__file__).resolve().parents[1]
_ENTRIES = _REPO / "tests" / "data" / "vrp_straddle_entries.csv"
_SPOT = _REPO / "tests" / "data" / "binance_spot_btcusdt_1d.csv"
_ARTIFACT = _REPO / "artifacts" / "vrp_short_variance_gate.json"
_WINDOW_MONTHS = 42  # the first-of-months 2022-01..2025-06 (the VRP window)


def main() -> None:
    raw = read_straddle_entries_csv(_ENTRIES)
    spot_by_date = read_spot_close_by_date(_SPOT)
    entries: list[StraddleEntry] = []
    for entry_date, hold_hours, call, put in raw:
        expiry_date = call.expiry.date()
        if expiry_date not in spot_by_date:
            raise VrpError(
                f"the spot fixture has no close on the expiry date {expiry_date} (entry "
                f"{entry_date}); extend the spot fixture or re-gather the entries"
            )
        entries.append(
            StraddleEntry(
                entry_date=entry_date,
                call=call,
                put=put,
                terminal_underlying=spot_by_date[expiry_date],
                hold_hours=hold_hours,
            )
        )

    artifact = build_gate_artifact(
        entries,
        DERIBIT_OPTION,
        currency="BTC",
        n_entries_total=_WINDOW_MONTHS,
        n_entries_dropped=_WINDOW_MONTHS - len(entries),
        entries_sha256=compute_sha256(_ENTRIES),
        spot_sha256=compute_sha256(_SPOT),
    )
    dump_gate_artifact(artifact, _ARTIFACT)

    v = artifact.verdict
    print(f"\nLayer-ii short-variance gate (BTC, {artifact.window_start}..{artifact.window_end})")
    print(f"  entries used {artifact.n_entries_used} / {artifact.n_entries_total} "
          f"(dropped {artifact.n_entries_dropped})")
    print(f"  Deflated Sharpe {v.deflated_sharpe:.4f} (effective T {v.effective_t}, "
          f"underpowered={v.dsr_underpowered}); necessary-not-sufficient, never the headline")
    print("  regime tail (worst monthly loss; multiple of the single-leg margin):")
    for r in artifact.regimes:
        print(f"    {r.name:<9} n={r.n:>2} mean_net={r.mean_net_coin:+.4f} coin "
              f"frac_losing={r.frac_losing:.0%} worst_loss={r.worst_loss_coin:.3f} coin "
              f"({r.worst_loss_margin_mult:.1f}x margin)")
    print("  peso shocks (cited one-day crashes on a representative straddle):")
    for p in artifact.peso_shocks:
        print(f"    {p.shock_pct:.0%} crash: loss {p.loss_coin:.2f} coin "
              f"({p.loss_margin_mult:.1f}x margin) [{p.source}]")
    verdict = "NON-VIABLE" if v.non_viable else "NOT KILLED (cross-check before belief)"
    print(f"\n  VERDICT: {verdict}. Reason: {v.reason}")
    print(f"  Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
