"""Run the BTC/ETH slow-trend gate from the committed fixture."""

from __future__ import annotations

from pathlib import Path

from riskpremia.data.manifest import compute_sha256
from riskpremia.trend.fixtures import (
    fixture_sha256,
    read_bars_frame,
    read_source_files_json,
)
from riskpremia.trend.gate import build_gate_artifact, dump_gate_artifact

_REPO = Path(__file__).resolve().parents[1]
_BARS = _REPO / "tests" / "data" / "btc_eth_daily_ohlc.csv"
_SOURCES = _REPO / "tests" / "data" / "btc_eth_daily_ohlc_sources.json"
_ARTIFACT = _REPO / "artifacts" / "btc_eth_trend_gate.json"


def main() -> None:
    bars = read_bars_frame(_BARS)
    sources = read_source_files_json(_SOURCES)
    artifact = build_gate_artifact(
        bars,
        bars_sha256=fixture_sha256(_BARS),
        bars_relpath=_BARS.relative_to(_REPO).as_posix(),
        sources_sha256=compute_sha256(_SOURCES),
        sources_relpath=_SOURCES.relative_to(_REPO).as_posix(),
        sources=sources,
    )
    dump_gate_artifact(artifact, _ARTIFACT)
    s = artifact.score
    print(f"\nBTC/ETH trend gate ({artifact.first_fill_date} to {artifact.last_exit_date})")
    print(
        f"  mean_net={s.mean_net:+.4%}/week, full_PSR={s.full_psr_zero:.4f}, "
        f"CPCV_stress_min={s.cpcv_min_psr_stress:.4f}"
    )
    print(
        f"  max_drawdown={s.max_drawdown:.2%}, cost_share={s.total_cost_share:.2%}, "
        f"total_return={s.compounded_net_gain:.2%}, cagr={s.cagr:.2%}"
    )
    print(f"  VERDICT: {artifact.verdict.headline}. {artifact.verdict.reason}")
    print(f"  Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
