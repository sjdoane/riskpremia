"""Render the VRP measurement figures from the committed artifact (ADR 0004 PR5b).

Render-only. matplotlib is the optional `figures` extra (loose pin: nothing
determinism-critical depends on the plotting version, and the JSON artifact, not the
PNG bytes, is the audited contract). It is imported LAZILY inside each function with
the headless Agg backend, so importing this module costs nothing when matplotlib is
absent and the rest of the package (loaders, the measurement, the cost model) never
pulls it in. The render test is skipped when matplotlib is not installed, so CI (which
installs only `.[dev]`) does not need it.

Every figure renders PURELY from a pre-built `VrpArtifact` (no call to `vrp_headline`
or the bootstrap), so a regenerated PNG can never drift from the committed CI. The
honesty caveats travel ON the figure as footnotes (design review H3/H4/L2): the gap in
figure 1 is the VOL-point spread (a distinct object from the variance premium), and
the figure 2 dispersion is the phase band, with the phase-0 bootstrap CI labeled as
such rather than drawn as an error bar on the median.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from riskpremia.vrp.artifact import RegimeStat, VrpArtifact

# Suppress matplotlib's version/timestamp PNG text chunks so a re-render on the same
# platform is byte-stable (best-effort; cross-version PNG bytes may still differ, which
# is fine because the JSON artifact, not the PNG, is the reproducibility contract).
_PNG_METADATA = {"Software": None, "Creation Time": None}
_DPI = 150


def _plt() -> Any:
    """Lazy matplotlib import, pinned to the headless Agg backend."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _dates(series_dates: tuple[str, ...]) -> list[date]:
    return [date.fromisoformat(s) for s in series_dates]


def _regime(artifact: VrpArtifact, name: str) -> RegimeStat | None:
    for r in artifact.regimes:
        if r.name == name and r.n_obs > 0:
            return r
    return None


def render_dvol_vs_realized(artifact: VrpArtifact, out_path: Path) -> Path:
    """DVOL implied vol vs the matched forward realized vol (vol points), over time.

    The shaded band is the implied-minus-realized VOL-point spread; the footnote notes
    it is distinct from the variance premium (the headline) and that the legs are on
    different underlyings (the cross-underlying basis caveat).
    """
    plt = _plt()
    s = artifact.series
    all_dates = _dates(s.date)
    trip = [
        (d, dv, rv)
        for d, dv, rv in zip(all_dates, s.dvol_vol_pct, s.realized_vol_pct_forward, strict=True)
        if rv is not None
    ]
    dates_r = [t[0] for t in trip]
    dvol_r = [t[1] for t in trip]
    realized_r = [t[2] for t in trip]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(all_dates, list(s.dvol_vol_pct), color="#1f77b4", lw=1.2, label="DVOL implied vol")
    ax.plot(dates_r, realized_r, color="#d62728", lw=1.0, label="30d forward realized vol")
    ax.fill_between(
        dates_r, realized_r, dvol_r,
        where=[d >= r for d, r in zip(dvol_r, realized_r, strict=True)],
        color="#1f77b4", alpha=0.15, interpolate=True, label="implied over realized (vol spread)",
    )
    ax.set_title(
        f"{artifact.currency} implied vs realized volatility "
        f"({artifact.window_days}-day, {artifact.date_start} to {artifact.date_end})"
    )
    ax.set_ylabel("annualized volatility (percent, 365-day)")
    ax.set_xlabel("date (UTC)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.25)
    fig.text(
        0.01, 0.01,
        "Shaded band is the vol-point spread (DVOL minus forward realized vol), a "
        "distinct object from the variance premium headline; implied leg is the Deribit "
        "BTC index, realized leg the Binance spot (cross-underlying proxy).",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_vrp_decay(artifact: VrpArtifact, out_path: Path) -> Path:
    """Forward VRP (variance points) over time, with the spot-ETF regime means.

    Shows the daily forward VRP scatter (the real dispersion), the pre/post-ETF mean
    segments (the decay), and a zero line; the footnote carries the full-sample point
    estimate, the phase BAND (its honest dispersion), and the phase-0 bootstrap CI
    LABELED as such, never an error bar on the median (design review H3).
    """
    plt = _plt()
    s = artifact.series
    h = artifact.headline
    all_dates = _dates(s.date)
    pts = [(d, v) for d, v in zip(all_dates, s.vrp_forward, strict=True) if v is not None]
    dv = [p[0] for p in pts]
    vv = [p[1] for p in pts]
    etf = date.fromisoformat(artifact.etf_launch)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(dv, vv, s=5, color="#7f7f7f", alpha=0.4, label="daily forward VRP")
    ax.axhline(0.0, color="black", lw=0.8)
    ax.axvline(etf, color="#2ca02c", lw=1.0, ls="--",
               label=f"spot-ETF launch ({artifact.etf_launch})")

    start, end = all_dates[0], all_dates[-1]
    pre, post = _regime(artifact, "pre_etf"), _regime(artifact, "post_etf")
    if pre is not None:
        ax.hlines(pre.mean_vrp_forward, start, etf, color="#1f77b4", lw=2.5,
                  label=f"pre-ETF mean {pre.mean_vrp_forward:.3f}")
    if post is not None:
        ax.hlines(post.mean_vrp_forward, etf, end, color="#d62728", lw=2.5,
                  label=f"post-ETF mean {post.mean_vrp_forward:.3f}")

    ax.set_title(
        f"{artifact.currency} variance risk premium (forward, {artifact.window_days}-day)"
    )
    ax.set_ylabel("variance risk premium (annualized variance points)")
    ax.set_xlabel("date (UTC)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.25)
    fig.text(
        0.01, 0.01,
        f"Full-sample premium: median-phase mean {h.mean_phase_median:.3f}, phase band "
        f"[{h.mean_phase_min:.3f}, {h.mean_phase_max:.3f}]; phase-0 strided block-bootstrap "
        f"95% CI [{h.ci_low:.3f}, {h.ci_high:.3f}] (effective T {h.effective_t:.0f}). The "
        f"pre/post means are descriptive (no per-regime CI).",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_all(artifact: VrpArtifact, out_dir: Path) -> list[Path]:
    """Render every figure into `out_dir`, returning the written paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        render_dvol_vs_realized(artifact, out_dir / "dvol_vs_realized.png"),
        render_vrp_decay(artifact, out_dir / "vrp_decay.png"),
    ]
