"""Render the Study 10 quality-tilt figures from the committed panel and artifact.

Render-only. matplotlib is the optional `figures` extra, imported lazily on the headless Agg
backend; the render test is skipped when it is absent. The high-profitability and market net wealth
paths are rebuilt deterministically from the committed panel, and the scorecard reads the audited
PSR numbers from the committed artifact, so a regenerated PNG cannot drift from the measurement. The
honesty caveat travels on the figures: the profitability premium is real but thin (a positive
Fama-French alpha) and does not survive the deployable differential cost and the deflation.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from riskpremia.quality.gate import (
    EXPENSE_HI_ANNUAL,
    EXPENSE_MKT_ANNUAL,
    VIABILITY_BAR,
    load_artifact_dict,
)

_PNG_METADATA = {"Software": None, "Creation Time": None}
_DPI = 150
_TD = 252.0


def _plt() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _wealth(returns: list[float]) -> list[float]:
    out: list[float] = []
    level = 1.0
    for r in returns:
        level *= 1.0 + r
        out.append(level)
    return out


def render_wealth(panel: pl.DataFrame, art: dict[str, Any], out_path: Path) -> Path:
    """High-profitability vs market net wealth and their ratio: a thin, decaying outperformance."""
    plt = _plt()
    frame = panel.sort("date")
    xs: list[date] = list(frame["date"].to_list())
    hi = [float(x) - EXPENSE_HI_ANNUAL / _TD for x in frame["hi30_vw"].to_list()]
    mkt = [float(m) + float(r) - EXPENSE_MKT_ANNUAL / _TD
           for m, r in zip(frame["mkt_rf"].to_list(), frame["rf"].to_list(), strict=True)]
    hi_w = _wealth(hi)
    mkt_w = _wealth(mkt)
    ratio = [a / b for a, b in zip(hi_w, mkt_w, strict=True)]
    d = art["score"]["difference"]
    dec = art["score"]["decomposition"]
    a = art["score"]["attribution"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, height_ratios=[2, 1])
    ax1.plot(xs, mkt_w, color="#08519c", lw=1.3, label="value-weight market (net)")
    ax1.plot(xs, hi_w, color="#d62728", lw=1.1, label="high-profitability tercile (net)")
    ax1.set_yscale("log")
    ax1.set_ylabel("net total-return wealth (log, $1 start)")
    ax1.set_title(f"Quality tilt vs market, {art['data_start']} to {art['data_end']}")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.25, which="both")
    ax2.plot(xs, ratio, color="#7f2704", lw=1.2)
    ax2.axhline(1.0, color="black", lw=0.8, ls="--")
    ax2.set_ylabel("high-profitability / market")
    ax2.set_xlabel("date")
    ax2.grid(True, alpha=0.25)
    fig.text(
        0.01, 0.01,
        f"The operating-profitability premium is real (Fama-French five-factor alpha "
        f"{dec['ff5_alpha_ann']:+.1%}/yr, t {a['alpha_t_stat']:.1f}, robust-minus-weak dominant) "
        f"but thin: net of the deployable differential expense the difference PSR is "
        f"{d['full_psr_zero']:.2f} (bar {VIABILITY_BAR:.2f}) and the deflation kills it.",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_scorecard(art: dict[str, Any], out_path: Path) -> Path:
    """The difference PSR across stress, with the gross-vs-deployable and deflation contrast."""
    plt = _plt()
    s = art["score"]
    d = s["difference"]
    rec = {r["name"]: r["psr_zero"] for r in s["recency"]}
    bars: list[tuple[str, float]] = [
        ("gross\n(no cost)", d["gross_full_psr_zero"]),
        ("net of\ndifferential", d["full_psr_zero"]),
        ("monthly", d["monthly_psr_zero"]),
        ("CPCV worst", s["cpcv"]["fold_min"]),
        ("from 2000", rec.get("from_2000", 0.0)),
        ("from 2010", rec.get("from_2010", 0.0)),
        ("from 2022", rec.get("from_2022", 0.0)),
        ("deflated x16", s["deflation"]["dsr_at_min_trials"]),
    ]
    labels = [b[0] for b in bars]
    values = [b[1] for b in bars]
    colors = ["#7f7f7f"] + ["#d62728" if v < VIABILITY_BAR else "#2ca02c" for v in values[1:]]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(labels, values, color=colors)
    ax.axhline(VIABILITY_BAR, color="black", lw=1.2, ls="--", label=f"{VIABILITY_BAR:.2f} bar")
    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel("conditional PSR(0) of the difference")
    ax.set_title("Quality tilt: gross clears the bar; the deployable cost and deflation fail it")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, axis="y", alpha=0.25)
    for tick in ax.get_xticklabels():
        tick.set_rotation(15)
        tick.set_ha("right")
    fig.text(
        0.01, 0.01,
        "The grey gross bar clears the bar, but the deployable differential expense (quality ETF "
        "vs market ETF), the multiple-testing deflation for the mined quality factor, and the "
        "post-2010 decay all push it under: a real premium, not a deployable make-money edge.",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_all(panel_path: Path, artifact_path: Path, out_dir: Path) -> list[Path]:
    """Render every Study 10 figure into `out_dir`, returning the written paths."""
    from riskpremia.quality.fixtures import read_panel_frame

    panel = read_panel_frame(panel_path)
    art = load_artifact_dict(artifact_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        render_wealth(panel, art, out_dir / "quality_wealth.png"),
        render_scorecard(art, out_dir / "quality_scorecard.png"),
    ]
