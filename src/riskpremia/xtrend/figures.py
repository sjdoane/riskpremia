"""Render the Study 6 cross-asset trend figures from the committed artifact.

Render-only. matplotlib is the optional `figures` extra, imported lazily inside each
function with the headless Agg backend, so importing this module costs nothing when
matplotlib is absent and the rest of the package never pulls it in. The render test is
skipped when matplotlib is not installed, so CI (which installs only `.[dev]`) does not
need it. Every figure renders purely from the committed `artifacts/xtrend_gate.json`
(via `load_artifact_dict`), so a regenerated PNG can never drift from the audited result.

The honesty caveats travel on the figures as footnotes: the equity curve is total-return
wealth net of modeled costs (the gate is scored in excess of bills), and the scorecard
shows the full-sample pass alongside the regime-dependent stress (the 2022-onward slice,
the CPCV worst fold) and the per-sleeve attribution (the equity trend sleeve carries the
result; the long-Treasury sleeve is the weaker, recent-regime-sensitive part).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from riskpremia.xtrend.gate import load_artifact_dict

_PNG_METADATA = {"Software": None, "Creation Time": None}
_DPI = 150
_PASS = "#2ca02c"
_FAIL = "#d62728"


def _plt() -> Any:
    """Lazy matplotlib import, pinned to the headless Agg backend."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _recency(score: dict[str, Any], name: str) -> float | None:
    for r in score["recency"]:
        if r["name"] == name:
            return float(r["psr_zero"])
    return None


def _sleeve(score: dict[str, Any], name: str) -> float | None:
    for s in score["sleeve_attribution"]:
        if s["sleeve"] == name:
            return float(s["psr_zero"])
    return None


def render_equity(data: dict[str, Any], out_path: Path) -> Path:
    """The daily net-wealth equity curve (log) with the drawdown panel below."""
    plt = _plt()
    de = data["daily_equity"]
    dates = [date.fromisoformat(s) for s in de["date"]]
    equity = [float(x) for x in de["equity"]]
    peak = equity[0]
    drawdown: list[float] = []
    for v in equity:
        peak = max(peak, v)
        drawdown.append(1.0 - v / peak if peak > 0.0 else 0.0)
    score = data["score"]
    cagr = float(score["cagr_total"])
    max_dd = float(score["max_drawdown"])

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 6), height_ratios=[3, 1], sharex=True
    )
    ax1.plot(dates, equity, color="#1f77b4", lw=1.1)
    ax1.set_yscale("log")
    ax1.set_title(
        f"Cross-asset defensive trend: net wealth from 1.0, "
        f"{data['first_scored_date']} to {data['last_scored_date']}"
    )
    ax1.set_ylabel("net wealth (log scale)")
    ax1.grid(True, alpha=0.25, which="both")
    ax1.text(
        0.02, 0.95,
        f"CAGR {cagr:.1%}    max drawdown {max_dd:.1%}",
        transform=ax1.transAxes, va="top", fontsize=9,
        bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none"},
    )
    ax2.fill_between(dates, [-x for x in drawdown], 0.0, color=_FAIL, alpha=0.4)
    ax2.set_ylabel("drawdown")
    ax2.set_xlabel("date")
    ax2.grid(True, alpha=0.25)
    fig.text(
        0.01, 0.01,
        "Total-return net wealth, net of modeled fund costs and including bill carry. The "
        "gate is scored on returns in excess of bills; the result clears the full-sample "
        "deflated gate but is regime-dependent (weak since 2022). A classic rule validated "
        "with full rigor, not a novel edge.",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_scorecard(data: dict[str, Any], out_path: Path) -> Path:
    """Conditional PSR(0) by window and sleeve, against the 0.95 bar."""
    plt = _plt()
    score = data["score"]
    rows: list[tuple[str, float | None]] = [
        ("Full sample (daily)", float(score["full_psr_zero"])),
        ("Monthly (non-overlapping)", float(score["monthly_psr_zero"])),
        ("2008 onward", _recency(score, "from_2008")),
        ("2022 onward", _recency(score, "from_2022")),
        ("CPCV worst fold", float(score["cpcv"]["fold_min"])),
        ("Equity sleeve alone", _sleeve(score, "equity")),
        ("Long-Treasury alone", _sleeve(score, "bond")),
    ]
    present = [(label, value) for label, value in rows if value is not None]
    labels = [r[0] for r in present]
    values = [float(r[1]) for r in present if r[1] is not None]
    colors = [_PASS if v >= 0.95 else _FAIL for v in values]

    fig, ax = plt.subplots(figsize=(9, 5))
    positions = list(range(len(values)))
    ax.barh(positions, values, color=colors)
    ax.axvline(0.95, color="black", ls="--", lw=1.0, label="0.95 bar")
    ax.set_yticks(positions)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0.0, 1.02)
    ax.set_xlabel("conditional PSR(0)")
    ax.set_title("Cross-asset defensive trend: conditional PSR(0) by window and sleeve")
    for i, v in enumerate(values):
        ax.text(min(v + 0.01, 0.985), i, f"{v:.3f}", va="center", fontsize=8)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(True, axis="x", alpha=0.25)
    fig.text(
        0.01, 0.01,
        "Green clears the 0.95 bar, red is below it. The full-sample and monthly statistics "
        "pass and survive deflation; the 2022-onward slice, the CPCV worst fold, and the "
        "long-Treasury sleeve are below the bar. The equity trend sleeve carries the result.",
        fontsize=6.5, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_path, dpi=_DPI, metadata=_PNG_METADATA)
    plt.close(fig)
    return out_path


def render_all(artifact_path: Path, out_dir: Path) -> list[Path]:
    """Render every Study 6 figure into `out_dir`, returning the written paths."""
    data = load_artifact_dict(artifact_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        render_equity(data, out_dir / "xtrend_equity.png"),
        render_scorecard(data, out_dir / "xtrend_gate_scorecard.png"),
    ]
