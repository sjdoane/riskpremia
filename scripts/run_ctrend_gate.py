"""Run the CTREND net-of-cost gate from the committed panel (ADR 0005 PR3).

Offline + reproducible: read the committed USDT daily panel, rebuild the weekly PIT
universe and CTREND forecasts, charge realistic spot turnover costs, score the OOS 2022+
weekly returns under CPCV, and write `artifacts/ctrend_gate.json`.

Run with the dedicated venv:
  $env:PYTHONIOENCODING="utf-8"
  C:\\Users\\SamJD\\.venvs\\riskpremia\\Scripts\\python.exe -m scripts.run_ctrend_gate
"""

from __future__ import annotations

from pathlib import Path

from riskpremia.ctrend.fixtures import daily_panel_content_sha256, read_daily_panel
from riskpremia.ctrend.gate import GateKnobs, build_gate_artifact, dump_gate_artifact
from riskpremia.ctrend.signal import DEFAULT_FIT_WINDOW, DEFAULT_N_QUINTILES, ctrend_forecasts
from riskpremia.ctrend.universe import (
    DEFAULT_LOOKBACK_WEEKS,
    DEFAULT_MIN_HISTORY_WEEKS,
    DEFAULT_TOP_N,
    build_weekly_panel,
    pit_eligible,
)

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "ctrend_daily_panel_usdt.csv.gz"
_ARTIFACT = _REPO / "artifacts" / "ctrend_gate.json"


def main() -> None:
    daily = read_daily_panel(_PANEL)
    weekly = pit_eligible(
        build_weekly_panel(daily),
        top_n=DEFAULT_TOP_N,
        lookback_weeks=DEFAULT_LOOKBACK_WEEKS,
        min_history_weeks=DEFAULT_MIN_HISTORY_WEEKS,
    )
    forecasts = ctrend_forecasts(
        daily, weekly, fit_window=DEFAULT_FIT_WINDOW, n_quintiles=DEFAULT_N_QUINTILES
    )
    knobs = GateKnobs(
        top_n=DEFAULT_TOP_N,
        lookback_weeks=DEFAULT_LOOKBACK_WEEKS,
        min_history_weeks=DEFAULT_MIN_HISTORY_WEEKS,
        fit_window=DEFAULT_FIT_WINDOW,
        n_quintiles=DEFAULT_N_QUINTILES,
    )
    artifact = build_gate_artifact(
        forecasts,
        panel_sha256=daily_panel_content_sha256(_PANEL),
        n_panel_rows=daily.height,
        panel_relpath="tests/data/ctrend_daily_panel_usdt.csv.gz",
        knobs=knobs,
    )
    dump_gate_artifact(artifact, _ARTIFACT)

    retail = artifact.retail_long_only
    academic = artifact.academic_long_short
    print(f"\nCTREND PR3 gate ({artifact.window_start}..{artifact.window_end})")
    print(
        f"  retail long-only: mean_net={retail.mean_net:+.4%}/week, "
        f"turnover={retail.mean_turnover:.2f}/week, full_DSR={retail.full_oos_dsr:.4f}, "
        f"CPCV_min_DSR={retail.cpcv_min_dsr:.4f}"
    )
    print(
        f"  academic long-short: mean_net={academic.mean_net:+.4%}/week, "
        f"turnover={academic.mean_turnover:.2f}/week, full_DSR={academic.full_oos_dsr:.4f}, "
        f"CPCV_min_DSR={academic.cpcv_min_dsr:.4f}"
    )
    print(
        f"  trial family: n_effective={retail.n_effective}, v_sr={retail.v_sr:.6f}, "
        f"records={len(artifact.trial_records)}"
    )
    print(f"\n  VERDICT: {artifact.verdict.headline}. {artifact.verdict.retail_reason}")
    print(f"  Academic comparison: {artifact.verdict.academic_reason}")
    print(f"  Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
