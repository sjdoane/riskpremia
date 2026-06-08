"""Render the Study 8 volatility-managed market figures from the committed panel and artifact.

Render-only. matplotlib is the optional `figures` extra, imported lazily on the headless Agg
backend; the render test is skipped when it is absent. The managed and unmanaged net wealth paths
are rebuilt deterministically from the committed Study 6 panel (the primary needs no new data), and
the scorecard reads the audited PSR numbers from the committed artifact, so a regenerated PNG
cannot drift from the measurement. The honesty caveat travels on the figures: the kill is the
managed-minus-unmanaged difference, and on this sample volatility timing does not beat buy-and-hold
net of cost (a clean Cederburg replication).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from riskpremia.volmanaged.gate import VIABILITY_BAR, load_artifact_dict
from riskpremia.volmanaged.measure import VMKnobs, build_daily_series, market_excess

_PNG_METADATA = {"Software": None, "Creation Time": None}
_DPI = 150


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
    """Managed vs unmanaged net wealth and their ratio: the two paths overlap (no value-add)."""
    plt = _plt()
    dates, excess, cash = market_excess(panel)
    series = build_daily_series(dates, excess, cash, VMKnobs(), c_mode="full_sample")
    cashes = [series.managed_total[i] - series.managed_excess[i] for i in range(len(series.dates))]
    unmanaged_total = [series.unmanaged_excess[i] + cashes[i] for i in range(len(series.dates))]
    managed_wealth = _wealth(list(series.managed_total))
    unmanaged_wealth = _wealth(unmanaged_total)
    ratio = [m / u for m, u in zip(managed_wealth, unmanaged_wealth, strict=True)]
    xs: list[date] = list(series.dates)
    d = art["score"]["difference"]
    g = art["score"]["gross"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, height_ratios=[2, 1])
    ax1.plot(xs, unmanaged_wealth, color="#08519c", lw=1.4, label="unmanaged market (buy-and-hold)")
    ax1.plot(xs, managed_wealth, color="#d62728", lw=1.2, label="volatility-managed market")
    ax1.set_yscale("log")
    ax1.set_ylabel("net total-return wealth (log, $1 start)")
    ax1.set_title(
        f"Volatility-managed vs unmanaged US market, net of cost, "
        f"{art['first_scored_date']} to {art['last_scored_date']}"
    )
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.25, which="both")

    ax2.plot(xs, ratio, color="#7f2704", lw=1.2)
    ax2.axhline(1.0, color="black", lw=0.8, ls="--")
    ax2.set_ylabel("managed / unmanaged")
    ax2.set_xlabel("date")
    ax2.grid(True, alpha=0.25)
    fig.text(
        0.01, 0.01,
        f"The kill is the managed-MINUS-unmanaged difference: PSR(0) {d['full_psr_zero']:.2f} "
        f"(bar {VIABILITY_BAR:.2f}). A real gross timing alpha "
        f"({g['uncapped_costless_ann_return']:+.1%}/yr at equal vol) dies on the 2.0x retail "
        f"leverage cap ({g['cap_drag_ann_return']:+.1%}/yr, the dominant drag) and costs "
        f"({g['cost_drag_ann_return']:+.1%}/yr): a clean Cederburg replication, not a cost trick.",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_scorecard(art: dict[str, Any], out_path: Path) -> Path:
    """The difference-series PSR(0) across every stress dimension, all below the 0.95 bar."""
    plt = _plt()
    s = art["score"]
    d = s["difference"]
    rec = {r["name"]: r["psr_zero"] for r in s["recency"]}
    caps = {c["cap"]: c["full_psr_zero"] for c in s["cap_sensitivity"]}
    bars: list[tuple[str, float]] = [
        ("full", d["full_psr_zero"]),
        ("monthly", d["monthly_psr_zero"]),
        ("expanding-c", s["expanding_c"]["full_psr_zero"]),
        ("CPCV worst", s["cpcv"]["fold_min"]),
        ("from 2008", rec.get("from_2008", 0.0)),
        ("from 2022", rec.get("from_2022", 0.0)),
        ("deflated x128", s["deflation"]["dsr_by_trials"][-1]),
        ("cap 1.0", caps.get(1.0, 0.0)),
        ("cap 1.5", caps.get(1.5, 0.0)),
        ("cap 2.0", caps.get(2.0, 0.0)),
    ]
    labels = [b[0] for b in bars]
    values = [b[1] for b in bars]
    colors = ["#d62728" if v < VIABILITY_BAR else "#2ca02c" for v in values]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(labels, values, color=colors)
    ax.axhline(
        VIABILITY_BAR, color="black", lw=1.2, ls="--", label=f"{VIABILITY_BAR:.2f} viability bar"
    )
    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel("conditional PSR(0) of the managed-minus-unmanaged difference")
    ax.set_title("Volatility-managed market: the difference gate fails on every stress dimension")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, axis="y", alpha=0.25)
    for tick in ax.get_xticklabels():
        tick.set_rotation(30)
        tick.set_ha("right")
    fig.text(
        0.01, 0.01,
        "Every reading of the deployability kill (the difference over buy-and-hold) sits below the "
        "0.95 bar, including the real-time expanding-window c and the deflated Sharpe: the null is "
        "robust, not a single unlucky slice.",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_all(panel_path: Path, artifact_path: Path, out_dir: Path) -> list[Path]:
    """Render every Study 8 figure into `out_dir`, returning the written paths."""
    from riskpremia.xtrend.fixtures import read_panel_frame

    panel = read_panel_frame(panel_path)
    art = load_artifact_dict(artifact_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        render_wealth(panel, art, out_dir / "volmanaged_wealth.png"),
        render_scorecard(art, out_dir / "volmanaged_scorecard.png"),
    ]
