"""Render the Study 7 funding-dispersion figures from the committed series and artifact.

Render-only. matplotlib is the optional `figures` extra, imported lazily on the headless Agg
backend; the render test is skipped when it is absent. The figures render from the committed
daily series (the dispersion time series) and the committed artifact (the regime means, the
decay, and the bootstrap confidence intervals), so a regenerated PNG cannot drift from the
audited measurement. The honesty caveats travel on the figures: the dispersion is a measured
object that is decaying and non-deployable (no tradeable Sharpe), and the universe coverage is
shown.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from riskpremia.dispersion.artifact import SPOT_ETF, load_artifact_dict
from riskpremia.dispersion.fixtures import read_series_frame

_PNG_METADATA = {"Software": None, "Creation Time": None}
_DPI = 150


def _plt() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _rolling_median(frame: pl.DataFrame, column: str, window: int) -> list[float | None]:
    return frame[column].rolling_median(window_size=window, min_samples=window // 2).to_list()


def render_dispersion(series: pl.DataFrame, art: dict[str, Any], out_path: Path) -> Path:
    """The daily equal-weight cross-sectional funding IQR, with the rolling median and regimes."""
    plt = _plt()
    window = int(art["knobs"]["decay_plot_window_days"])
    dates: list[date] = series["date"].to_list()
    iqr = [float(x) for x in series["iqr"].to_list()]
    roll = _rolling_median(series, "iqr", window)
    regime = art["iqr_regime"]
    decay = art["iqr_decay"]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, iqr, color="#9ecae1", lw=0.8, label="daily IQR")
    ax.plot(dates, roll, color="#08519c", lw=1.8, label=f"{window}-day rolling median")
    ax.axvline(SPOT_ETF, color="#2ca02c", lw=1.0, ls="--", label="spot-ETF launch")
    ax.hlines(regime["pre_mean"], dates[0], SPOT_ETF, color="#d62728", lw=2.2,
              label=f"pre-ETF mean {regime['pre_mean']:.2f}")
    ax.hlines(regime["post_mean"], SPOT_ETF, dates[-1], color="#ff7f0e", lw=2.2,
              label=f"post-ETF mean {regime['post_mean']:.2f}")
    ax.set_title(
        f"Cross-sectional perpetual-funding dispersion (equal-weight IQR, annualized), "
        f"{art['data_start']} to {art['data_end']}"
    )
    ax.set_ylabel("cross-sectional IQR of annualized funding")
    ax.set_xlabel("date (UTC)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.25)
    fig.text(
        0.01, 0.01,
        f"Measured object, not a strategy: the top-15 most-liquid perpetuals (point-in-time). "
        f"Dispersion is alive but decaying (regime difference "
        f"{regime['difference']:+.2f}, 95% CI [{regime['diff_ci_low']:+.2f}, "
        f"{regime['diff_ci_high']:+.2f}]; slope {decay['slope_per_year']:+.2f}/yr). Capturing it "
        f"needs shorting a wide alt-perp cross-section US retail cannot access; not deployable.",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_sort_premium(series: pl.DataFrame, art: dict[str, Any], out_path: Path) -> Path:
    """The secondary gross high-minus-low funding sort premium over time (non-capturable)."""
    plt = _plt()
    pairs = [
        (d, float(v))
        for d, v in zip(series["date"].to_list(), series["sort_premium"].to_list(), strict=True)
        if v is not None
    ]
    window = int(art["knobs"]["decay_plot_window_days"])
    dates = [p[0] for p in pairs]
    prem = [p[1] for p in pairs]
    sub = pl.DataFrame({"sort_premium": prem})
    roll = _rolling_median(sub, "sort_premium", window)
    stat = art["sort_premium"]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, prem, color="#c7c7c7", lw=0.7, label="daily gross sort premium")
    ax.plot(dates, roll, color="#7f2704", lw=1.8, label=f"{window}-day rolling median")
    ax.axhline(0.0, color="black", lw=0.8)
    ax.axvline(SPOT_ETF, color="#2ca02c", lw=1.0, ls="--", label="spot-ETF launch")
    ax.set_title("Gross high-minus-low funding sort premium (secondary, non-capturable)")
    ax.set_ylabel("annualized funding spread (high minus low quintile)")
    ax.set_xlabel("date (UTC)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.25)
    fig.text(
        0.01, 0.01,
        f"Full-sample mean {stat['mean']:+.2f} annualized (95% CI [{stat['ci_low']:+.2f}, "
        f"{stat['ci_high']:+.2f}]). This is the dispersion expressed as a long-short carry; it is "
        f"NOT retail-capturable (it requires shorting a wide alt-perp cross-section on a non-US "
        f"venue) and is reported as a measured object, never a tradeable edge.",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_all(series_path: Path, artifact_path: Path, out_dir: Path) -> list[Path]:
    """Render every Study 7 figure into `out_dir`, returning the written paths."""
    series = read_series_frame(series_path)
    art = load_artifact_dict(artifact_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        render_dispersion(series, art, out_dir / "funding_dispersion_iqr.png"),
        render_sort_premium(series, art, out_dir / "funding_dispersion_sort_premium.png"),
    ]
