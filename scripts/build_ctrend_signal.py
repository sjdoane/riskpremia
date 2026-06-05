"""Build the committed CTREND signal artifact from the committed daily panel (Study 3, PR2).

A manual, one-time research entry point (NO network: the committed daily panel is the
anchor). It computes the full CTREND CS-C-ENet pipeline (features -> rank -> univariate
Fama-MacBeth -> elastic-net selection -> averaged forecast -> quintiles), measures the GROSS
point-in-time rank IC + the monotonic quintile spread (full-sample and on the held-out 2022+
window), and writes `artifacts/ctrend_signal.json`. Run with the dedicated venv from the
repo root:

  $env:PYTHONIOENCODING="utf-8"
  C:\\Users\\SamJD\\.venvs\\riskpremia\\Scripts\\python.exe -m scripts.build_ctrend_signal

The result is deterministic (no network, no RNG; the elastic-net solver is cyclic), so a
re-run reproduces the artifact up to a small libm/BLAS tolerance. The kill gate (PR3) reads
the same committed panel.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from riskpremia.ctrend.fixtures import daily_panel_content_sha256, read_daily_panel
from riskpremia.ctrend.signal import (
    DEFAULT_FIT_WINDOW,
    DEFAULT_L1_RATIO,
    DEFAULT_N_QUINTILES,
    ctrend_forecasts,
    quintile_spread,
    signal_rank_ic,
)
from riskpremia.ctrend.signal_artifact import (
    OOS_START,
    GrossQuality,
    SignalFingerprint,
    SignalKnobs,
    YearIC,
    build_signal_artifact,
    dump_signal_artifact,
)
from riskpremia.ctrend.universe import (
    DEFAULT_LOOKBACK_WEEKS,
    DEFAULT_MIN_HISTORY_WEEKS,
    DEFAULT_TOP_N,
    build_weekly_panel,
    pit_eligible,
)

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "tests" / "data" / "ctrend_daily_panel_usdt.csv.gz"
_ARTIFACT = _REPO / "artifacts" / "ctrend_signal.json"
_PANEL_RELPATH = _PANEL.relative_to(_REPO).as_posix()


def gross_quality(forecasts: pl.DataFrame, *, n_quintiles: int) -> GrossQuality:
    """The rank IC + the quintile spread of a forecasts frame as a `GrossQuality`."""
    ic = signal_rank_ic(forecasts)
    means = quintile_spread(forecasts, n_quintiles=n_quintiles)
    return GrossQuality(
        n_weeks=int(ic["n_weeks"]),
        mean_ic=ic["mean_ic"],
        ic_t_stat=ic["ic_t_stat"],
        frac_positive=ic["frac_positive"],
        quintile_means=tuple(means),
        quintile_spread=means[-1] - means[0],
    )


def main() -> None:
    print(f"Reading the committed daily panel {_PANEL_RELPATH} ...")
    daily = read_daily_panel(_PANEL)
    print(f"  {daily['symbol'].n_unique()} symbols, {daily.height} daily rows")

    weekly = pit_eligible(
        build_weekly_panel(daily),
        top_n=DEFAULT_TOP_N,
        lookback_weeks=DEFAULT_LOOKBACK_WEEKS,
        min_history_weeks=DEFAULT_MIN_HISTORY_WEEKS,
    )
    print("Computing the CTREND signal (features -> FM -> elastic-net selection -> quintiles) ...")
    forecasts = ctrend_forecasts(daily, weekly, fit_window=DEFAULT_FIT_WINDOW)
    weeks = forecasts["week_end"].unique().sort().to_list()
    print(f"  {forecasts.height} forecasts over {len(weeks)} weeks ({weeks[0]}..{weeks[-1]})")

    oos = forecasts.filter(pl.col("week_end") >= date.fromisoformat(OOS_START))
    full_q = gross_quality(forecasts, n_quintiles=DEFAULT_N_QUINTILES)
    oos_q = gross_quality(oos, n_quintiles=DEFAULT_N_QUINTILES)

    # Per-year IC: the regime-stability diagnostic (the gross IC is not temporally stable;
    # it inverted in 2021 and the OOS headline leans on recent regimes).
    ic_by_year: list[YearIC] = []
    for year in sorted({d.year for d in forecasts["week_end"].to_list()}):
        sub = forecasts.filter(pl.col("week_end").dt.year() == year)
        try:
            yic = signal_rank_ic(sub)
        except Exception:  # a year with too few scorable weeks is skipped
            continue
        ic_by_year.append(
            YearIC(
                year=year,
                n_weeks=int(yic["n_weeks"]),
                mean_ic=yic["mean_ic"],
                ic_t_stat=yic["ic_t_stat"],
            )
        )

    fingerprint = SignalFingerprint(
        panel_sha256=daily_panel_content_sha256(_PANEL),
        n_panel_rows=daily.height,
        panel_relpath=_PANEL_RELPATH,
    )
    knobs = SignalKnobs(
        top_n=DEFAULT_TOP_N,
        lookback_weeks=DEFAULT_LOOKBACK_WEEKS,
        min_history_weeks=DEFAULT_MIN_HISTORY_WEEKS,
        fit_window=DEFAULT_FIT_WINDOW,
        n_quintiles=DEFAULT_N_QUINTILES,
        l1_ratio=DEFAULT_L1_RATIO,
    )
    artifact = build_signal_artifact(
        full_q,
        oos_q,
        tuple(ic_by_year),
        currency_quote="USDT",
        window_start=str(weeks[0]),
        window_end=str(weeks[-1]),
        knobs=knobs,
        fingerprint=fingerprint,
    )
    dump_signal_artifact(artifact, _ARTIFACT)

    print(
        f"\n[CTREND signal] full-sample: mean IC={full_q.mean_ic:.4f} t={full_q.ic_t_stat:.2f} "
        f"frac_pos={full_q.frac_positive:.2f} n_weeks={full_q.n_weeks} "
        f"quintile spread={full_q.quintile_spread:.4f}/wk"
    )
    print(
        f"[CTREND signal] OOS {OOS_START}+: mean IC={oos_q.mean_ic:.4f} t={oos_q.ic_t_stat:.2f} "
        f"n_weeks={oos_q.n_weeks} quintile spread={oos_q.quintile_spread:.4f}/wk"
    )
    print(f"  quintile means (bottom..top): {[round(x, 4) for x in full_q.quintile_means]}")
    print("  IC by year (the regime-stability diagnostic):")
    for y in ic_by_year:
        print(f"    {y.year}: IC={y.mean_ic:+.4f} t={y.ic_t_stat:+.2f} n={y.n_weeks}")
    print(f"Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
