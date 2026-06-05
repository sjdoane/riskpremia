"""The CTREND signal reproducibility gate (Study 3, PR2): the COMMITTED signal artifact's
gross quality reproduces OFFLINE from the committed daily panel, and the committed claim is a
positive, significant point-in-time rank IC with a monotonic quintile spread. Runs in CI (no
network), mirroring the VRP/PR1 reproduction tests.

The signal flows through scikit-learn's elastic-net selection + libm, so the recomputed IC /
spread are asserted at a tolerance (the selected set can differ in a borderline week across
platforms); the verdict-level properties (positive IC, monotonic quintiles) are asserted
robustly. The full per-(week, coin) forecast series is NOT committed; this test rebuilds it
from the committed panel + the pinned code (the VRP/PR1 discipline).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from riskpremia.ctrend.fixtures import daily_panel_content_sha256, read_daily_panel
from riskpremia.ctrend.signal import ctrend_forecasts, quintile_spread, signal_rank_ic
from riskpremia.ctrend.signal_artifact import OOS_START, load_signal_artifact
from riskpremia.ctrend.universe import build_weekly_panel, pit_eligible

_REPO = Path(__file__).resolve().parents[2]
_PANEL = _REPO / "tests" / "data" / "ctrend_daily_panel_usdt.csv.gz"
_ARTIFACT = _REPO / "artifacts" / "ctrend_signal.json"

_HAVE = _PANEL.exists() and _ARTIFACT.exists()
pytestmark = pytest.mark.skipif(
    not _HAVE, reason="the committed CTREND panel/signal are not built yet"
)

# cross-platform elastic-net-selection + libm tolerance on the averaged IC + the spread
_IC_ABS_TOL = 5e-3
_SPREAD_ABS_TOL = 3e-3


def test_committed_signal_is_a_positive_gross_signal() -> None:
    # The committed claim: a positive, significant gross IC + a monotonic quintile spread,
    # full-sample and (stronger) out-of-sample. The robust, platform-independent assertions.
    art = load_signal_artifact(_ARTIFACT)
    assert art.full_sample.mean_ic > 0.0
    assert art.full_sample.ic_t_stat > 1.5
    assert art.out_of_sample.mean_ic > 0.0
    assert art.out_of_sample.ic_t_stat > 1.5
    # the full sample is monotonic across quintiles; both windows: the top quintile is the
    # highest-returning and beats the bottom (a positive GROSS spread, before costs). The OOS
    # middle quintiles can wobble (and are all negative in the 2022+ bear market: the long
    # leg loses gross while the long-short spread is positive, the PR3 long-only tension).
    fm = list(art.full_sample.quintile_means)
    assert fm == sorted(fm)
    for gross in (art.full_sample, art.out_of_sample):
        means = list(gross.quintile_means)
        assert means[-1] == max(means)  # the top quintile is the highest-returning
        assert gross.quintile_spread > 0.0
        assert gross.quintile_spread == pytest.approx(means[-1] - means[0], abs=1e-12)
    # the honest regime-stability disclosure: the IC is NOT uniformly positive (it inverted in
    # an earlier year), so the headline reflects a regime mix, not a stable edge
    assert len(art.ic_by_year) >= 4
    assert any(y.mean_ic < 0.0 for y in art.ic_by_year)
    assert any(y.mean_ic > 0.0 for y in art.ic_by_year)


def test_committed_signal_reproduces_from_the_panel() -> None:
    art = load_signal_artifact(_ARTIFACT)
    assert art.fingerprint.panel_sha256 == daily_panel_content_sha256(_PANEL)

    daily = read_daily_panel(_PANEL)
    assert daily.height == art.fingerprint.n_panel_rows
    weekly = pit_eligible(
        build_weekly_panel(daily),
        top_n=art.knobs.top_n,
        lookback_weeks=art.knobs.lookback_weeks,
        min_history_weeks=art.knobs.min_history_weeks,
    )
    forecasts = ctrend_forecasts(
        daily, weekly, fit_window=art.knobs.fit_window, n_quintiles=art.knobs.n_quintiles
    )

    full_ic = signal_rank_ic(forecasts)
    full_spread = quintile_spread(forecasts, n_quintiles=art.knobs.n_quintiles)
    assert full_ic["mean_ic"] == pytest.approx(art.full_sample.mean_ic, abs=_IC_ABS_TOL)
    assert (full_spread[-1] - full_spread[0]) == pytest.approx(
        art.full_sample.quintile_spread, abs=_SPREAD_ABS_TOL
    )
    assert full_ic["n_weeks"] == art.full_sample.n_weeks  # the scored-week count is exact

    oos = forecasts.filter(pl.col("week_end") >= date.fromisoformat(OOS_START))
    oos_ic = signal_rank_ic(oos)
    assert oos_ic["mean_ic"] == pytest.approx(art.out_of_sample.mean_ic, abs=_IC_ABS_TOL)
    assert oos_ic["mean_ic"] > 0.0  # the gross signal holds out of sample
