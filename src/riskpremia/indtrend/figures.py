"""Render the Study 9 industry-trend figures from the committed panel and artifact.

Render-only. matplotlib is the optional `figures` extra, imported lazily on the headless Agg
backend; the render test is skipped when it is absent. The strategy, equal-weight-always-invested,
and value-weight-market net wealth paths are rebuilt deterministically from the committed panel, and
the scorecard reads the audited PSR numbers from the committed artifact, so a regenerated PNG cannot
drift from the measurement. The honesty caveat travels on the figures: the kill is the strategy
minus its always-invested self (pure timing), and on this sample it is a clean null.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from riskpremia.indtrend.gate import (
    VIABILITY_BAR,
    IndTrendKnobs,
    _daily_from_panel,
    _market_net,
    _timing_difference,
    load_artifact_dict,
)

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
    """The strategy, always-invested equal-weight, and value-weight market net wealth (log)."""
    plt = _plt()
    knobs = IndTrendKnobs()
    daily = _daily_from_panel(panel)
    scored, _, strat, ew = _timing_difference(daily, knobs)
    _, market_net = _market_net(daily, knobs)
    xs: list[date] = list(scored)
    d = art["score"]["decomposition"]
    t = art["score"]["timing"]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(xs, _wealth(list(ew.net_total)), color="#08519c", lw=1.4,
            label="equal-weight always-invested (the timing benchmark)")
    ax.plot(xs, _wealth(list(strat.net_total)), color="#d62728", lw=1.2,
            label="trend-timed strategy (long-or-cash)")
    ax.plot(xs, _wealth(market_net), color="#7f7f7f", lw=1.0, ls="--",
            label="value-weight market")
    ax.set_yscale("log")
    ax.set_ylabel("net total-return wealth (log, $1 start)")
    ax.set_title(
        f"Industry trend net-of-market, {art['first_scored_date']} to {art['last_scored_date']}"
    )
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.25, which="both")
    fig.text(
        0.01, 0.01,
        f"The kill is the strategy MINUS its always-invested self (pure timing): PSR(0) "
        f"{t['full_psr_zero']:.2f} (bar {VIABILITY_BAR:.2f}), annualized timing "
        f"{d['timing_ann_return']:+.1%}/yr. The trend rule reduces volatility but gives up return, "
        f"so it does not beat always-invested net of cost: crash insurance, not a market-beater.",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_scorecard(art: dict[str, Any], out_path: Path) -> Path:
    """The timing-difference PSR across stress, with the net-of-bill context bar (the trap)."""
    plt = _plt()
    s = art["score"]
    t = s["timing"]
    rec = {r["name"]: r["psr_zero"] for r in s["recency"]}
    bars: list[tuple[str, float]] = [
        ("net-of-bill\n(context)", s["context"]["strategy_net_of_bill_psr_zero"]),
        ("timing full", t["full_psr_zero"]),
        ("timing monthly", t["monthly_psr_zero"]),
        ("CPCV worst", s["cpcv"]["fold_min"]),
        ("from 2000", rec.get("from_2000", 0.0)),
        ("from 2008", rec.get("from_2008", 0.0)),
        ("from 2022", rec.get("from_2022", 0.0)),
        ("deflated x128", s["deflation"]["dsr_by_trials"][-1]),
    ]
    labels = [b[0] for b in bars]
    values = [b[1] for b in bars]
    colors = ["#7f7f7f"] + ["#d62728" if v < VIABILITY_BAR else "#2ca02c" for v in values[1:]]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(labels, values, color=colors)
    ax.axhline(VIABILITY_BAR, color="black", lw=1.2, ls="--", label=f"{VIABILITY_BAR:.2f} bar")
    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel("conditional PSR(0)")
    ax.set_title("Industry trend: net-of-bill clears (equity premium); the timing kill fails")
    ax.legend(loc="center right", fontsize=8)
    ax.grid(True, axis="y", alpha=0.25)
    for tick in ax.get_xticklabels():
        tick.set_rotation(20)
        tick.set_ha("right")
    fig.text(
        0.01, 0.01,
        "The grey net-of-bill bar clears the bar on the equity premium alone (the Study 8 trap); "
        "the timing kill (strategy minus always-invested) and every stress slice are below it. The "
        "trend rule does not add timing value over always-invested net of cost.",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_all(panel_path: Path, artifact_path: Path, out_dir: Path) -> list[Path]:
    """Render every Study 9 figure into `out_dir`, returning the written paths."""
    from riskpremia.indtrend.fixtures import read_panel_frame

    panel = read_panel_frame(panel_path)
    art = load_artifact_dict(artifact_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        render_wealth(panel, art, out_dir / "indtrend_wealth.png"),
        render_scorecard(art, out_dir / "indtrend_scorecard.png"),
    ]
