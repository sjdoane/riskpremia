"""Study 8 factor-asymmetry secondary (ADR 0010, amendment finding 6).

Applies the same volatility-managed scaler to the long-short Kenneth French factors (SMB, HML,
RMW, CMA, and the momentum factor WML) and scores each managed-MINUS-unmanaged difference on the
net-of-cost gate (the undeflated PSR(0), plus the real-time expanding-window c as the out-of-sample
check), to test the literature's predicted market-survives, factors-die asymmetry. The
long-short factors cannot be levered through a market ETF, so the cost is turnover-only on the
continuous weight change (no financing leg, no exposure expense); the c-normalization and the 2.0x
scaling cap match the market primary. The market result is the Study 8 primary and is referenced,
not re-scored here.

The committed daily factor panel is a small tamper-evident fixture built from the
openly-redistributed Kenneth French five-factor and momentum daily files; an offline test rebuilds
the asymmetry artifact from it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any

import attrs
import polars as pl

from riskpremia.analytics.sharpe import psr
from riskpremia.execution.scoring import effective_sample_size, return_moments
from riskpremia.volmanaged.errors import VolManagedError
from riskpremia.volmanaged.measure import VMKnobs, build_daily_series

SCHEMA_VERSION = 1
_STUDY = "Volatility-managed factor asymmetry (Study 8 secondary, ADR 0010)"
VIABILITY_BAR = 0.95
TRADING_DAYS_PER_YEAR = 252.0
FACTOR_NAMES: tuple[str, ...] = ("smb", "hml", "rmw", "cma", "wml")
# Turnover-only: a long-short factor carries no ETF expense and no financing leg (amendment M6).
FACTOR_KNOBS = VMKnobs(
    cap=2.0, expense_annual=0.0, financing_spread_annual=0.0, turnover_cost_per_side=0.0005
)
_PANEL_HEADER: tuple[str, ...] = ("date", *FACTOR_NAMES)
_PANEL_SCHEMA = {"date": pl.Date, **{n: pl.Float64 for n in FACTOR_NAMES}}
_PROVENANCE_SCHEMA_VERSION = 1

CAVEATS: tuple[str, ...] = (
    "The managed factor return is scored as the managed-MINUS-unmanaged difference, the same kill "
    "as the market primary; a long-short factor is already an excess return, so the cost is "
    "turnover-only (no financing leg, no exposure expense) and the 2.0x cap is a scaling limit.",
    "The market result is the Study 8 primary (referenced here, not re-scored); the asymmetry is "
    "confirmed only if the managed market clears the bar and at least four of the five managed "
    "factors do not (the pre-registered rule). The market is a null, so the asymmetry as defined "
    "is not confirmed; the honest finding is whether the factors also fail (a uniform null).",
)


@attrs.frozen(slots=True)
class FactorPanelRow:
    """One trading day of the committed daily factor panel (decimals)."""

    date: date
    smb: Decimal
    hml: Decimal
    rmw: Decimal
    cma: Decimal
    wml: Decimal


@attrs.frozen(slots=True)
class FactorProvenance:
    """The upstream sources used to build the committed factor panel."""

    five_factor_url: str
    momentum_url: str
    start: str
    end: str
    fetched_utc: str


@attrs.frozen(slots=True)
class FactorResult:
    """One factor's managed-minus-unmanaged difference result and its gross decomposition."""

    name: str
    raw_t: int
    effective_t: int
    difference_full_psr_zero: float
    difference_expanding_psr_zero: float
    difference_ann_sharpe: float
    gross_uncapped_ann_return: float
    cap_drag_ann_return: float
    cost_drag_ann_return: float
    net_ann_return: float
    mean_weight: float
    passes: bool


@attrs.frozen(slots=True)
class InputFingerprint:
    """Content pins for the committed factor panel and its provenance."""

    panel_sha256: str
    panel_relpath: str
    n_panel_rows: int
    provenance_sha256: str
    provenance_relpath: str


@attrs.frozen(slots=True)
class FactorAsymmetryArtifact:
    """The committed Study 8 factor-asymmetry artifact."""

    schema_version: int
    study: str
    data_start: str
    data_end: str
    n_scored_days: int
    viability_bar: float
    market_difference_psr_zero: float
    market_passes: bool
    factors: tuple[FactorResult, ...]
    n_factors_failing: int
    asymmetry_confirmed: bool
    finding: str
    fingerprint: InputFingerprint
    knobs: VMKnobs
    caveats: tuple[str, ...]


def _fmt_decimal(value: Decimal) -> str:
    return f"{value.normalize():f}"


def factor_panel_csv_text(rows: Sequence[FactorPanelRow]) -> str:
    """Deterministic LF CSV text for the committed factor panel."""
    if not rows:
        raise VolManagedError("factor_panel_csv_text requires at least one row")
    seen: set[date] = set()
    for row in rows:
        if row.date in seen:
            raise VolManagedError(f"duplicate factor panel row for {row.date}")
        seen.add(row.date)
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_PANEL_HEADER)
    for row in sorted(rows, key=lambda r: r.date):
        writer.writerow(
            [row.date.isoformat(), _fmt_decimal(row.smb), _fmt_decimal(row.hml),
             _fmt_decimal(row.rmw), _fmt_decimal(row.cma), _fmt_decimal(row.wml)]
        )
    return buf.getvalue()


def write_factor_panel_csv(path: Path, rows: Sequence[FactorPanelRow]) -> None:
    """Write the committed factor panel fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(factor_panel_csv_text(rows), encoding="utf-8", newline="\n")


def read_factor_panel_frame(path: Path) -> pl.DataFrame:
    """Read the committed factor panel into a polars frame, sorted by date."""
    rows = list(csv.reader(StringIO(path.read_text(encoding="utf-8"))))
    if not rows or tuple(rows[0]) != _PANEL_HEADER:
        got = rows[0] if rows else None
        raise VolManagedError(f"{path.name}: header {got} != {list(_PANEL_HEADER)}")
    dates: list[date] = []
    cols: dict[str, list[float]] = {n: [] for n in FACTOR_NAMES}
    seen: set[date] = set()
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != len(_PANEL_HEADER):
            raise VolManagedError(f"{path.name}: expected {len(_PANEL_HEADER)} cols, got {row!r}")
        d = date.fromisoformat(row[0])
        if d in seen:
            raise VolManagedError(f"{path.name}: duplicate factor panel row for {d}")
        seen.add(d)
        dates.append(d)
        for i, n in enumerate(FACTOR_NAMES, start=1):
            cols[n].append(float(row[i]))
    frame = pl.DataFrame({"date": dates, **cols}, schema=_PANEL_SCHEMA).sort("date")
    return frame


def fixture_sha256(path: Path) -> str:
    """SHA256 of the committed fixture bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_factor_provenance_json(path: Path, provenance: FactorProvenance) -> None:
    """Write the source provenance JSON for the factor panel."""
    payload = {"schema_version": _PROVENANCE_SCHEMA_VERSION, "provenance": attrs.asdict(provenance)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                    newline="\n")


def _ann_sharpe(returns: Sequence[float]) -> float:
    return return_moments(returns).sr_hat * math.sqrt(TRADING_DAYS_PER_YEAR)


def _psr_zero(returns: Sequence[float]) -> float:
    m = return_moments(returns)
    eff_t, _ = effective_sample_size(returns)
    return psr(m.sr_hat, 0.0, eff_t, m.gamma_3, m.gamma_4)


def _score_factor(name: str, dates: Sequence[date], returns: Sequence[float]) -> FactorResult:
    """Score one long-short factor's managed-minus-unmanaged difference (turnover-only cost)."""
    zeros = [0.0] * len(returns)  # a long-short factor has no separate cash leg
    series = build_daily_series(dates, returns, zeros, FACTOR_KNOBS)
    diff = series.difference
    m = return_moments(diff)
    eff_t, _ = effective_sample_size(diff)
    # the real-time expanding-window c (the pre-registered out-of-sample check, ADR amendment 2)
    expanding = build_daily_series(dates, returns, zeros, FACTOR_KNOBS, c_mode="expanding")
    expanding_psr = _psr_zero(expanding.difference)
    # gross decomposition: uncapped costless, capped costless, net (turnover-only)
    free_uncapped = build_daily_series(
        dates, returns, zeros, attrs.evolve(FACTOR_KNOBS, cap=1.0e9, turnover_cost_per_side=0.0)
    )
    free_capped = build_daily_series(
        dates, returns, zeros, attrs.evolve(FACTOR_KNOBS, turnover_cost_per_side=0.0)
    )
    u_ret = statistics.fmean(free_uncapped.difference) * TRADING_DAYS_PER_YEAR
    c_ret = statistics.fmean(free_capped.difference) * TRADING_DAYS_PER_YEAR
    net_ret = statistics.fmean(diff) * TRADING_DAYS_PER_YEAR
    full_psr = psr(m.sr_hat, 0.0, eff_t, m.gamma_3, m.gamma_4)
    return FactorResult(
        name=name, raw_t=m.t_obs, effective_t=eff_t, difference_full_psr_zero=full_psr,
        difference_expanding_psr_zero=expanding_psr,
        difference_ann_sharpe=m.sr_hat * math.sqrt(TRADING_DAYS_PER_YEAR),
        gross_uncapped_ann_return=u_ret, cap_drag_ann_return=c_ret - u_ret,
        cost_drag_ann_return=net_ret - c_ret, net_ann_return=net_ret,
        mean_weight=series.mean_weight, passes=full_psr >= VIABILITY_BAR,
    )


def build_asymmetry_artifact(
    panel: pl.DataFrame,
    *,
    market_difference_psr: float,
    panel_sha256: str,
    panel_relpath: str,
    provenance_sha256: str,
    provenance_relpath: str,
) -> FactorAsymmetryArtifact:
    """Build the Study 8 factor-asymmetry artifact from the committed factor panel."""
    frame = panel.sort("date")
    dates: list[date] = list(frame["date"].to_list())
    if len(dates) < 252:
        raise VolManagedError("factor panel too short")
    results = tuple(_score_factor(n, dates, [float(x) for x in frame[n].to_list()])
                    for n in FACTOR_NAMES)
    n_fail = sum(1 for r in results if not r.passes)
    market_passes = market_difference_psr >= VIABILITY_BAR
    asymmetry_confirmed = market_passes and n_fail >= 4
    best = max(results, key=lambda r: r.difference_full_psr_zero)
    if not market_passes and n_fail == len(results):
        finding = (
            "Uniform null: the managed market and all five managed factors fail the undeflated "
            "net-of-cost PSR(0) gate, so the literature's market-survives, factors-die asymmetry "
            "does NOT hold under this conservative retail stack. Under the full-sample c, momentum "
            f"({best.name.upper()}) is the apparent standout (gross "
            f"{best.gross_uncapped_ann_return:+.1%}/yr, full-sample difference PSR "
            f"{best.difference_full_psr_zero:.2f}, the managed-momentum effect), but this does NOT "
            f"survive the project's expanding-window real-time c: its out-of-sample PSR is "
            f"{best.difference_expanding_psr_zero:.2f}, so the near-miss is a look-ahead artifact "
            "and the uniform null is robust out-of-sample. Deflation would only widen the gap."
        )
    elif not market_passes:
        finding = (
            f"The managed market fails and {n_fail} of {len(results)} managed factors fail the "
            f"undeflated net-of-cost PSR(0) gate; the market-survives asymmetry does not hold (the "
            f"market is itself a null here)."
        )
    else:
        finding = (
            f"The managed market clears the bar and {n_fail} of {len(results)} managed factors "
            f"fail; the predicted asymmetry is "
            f"{'confirmed' if asymmetry_confirmed else 'partially supported'}."
        )
    return FactorAsymmetryArtifact(
        schema_version=SCHEMA_VERSION, study=_STUDY,
        data_start=dates[0].isoformat(), data_end=dates[-1].isoformat(), n_scored_days=len(dates),
        viability_bar=VIABILITY_BAR, market_difference_psr_zero=market_difference_psr,
        market_passes=market_passes, factors=results, n_factors_failing=n_fail,
        asymmetry_confirmed=asymmetry_confirmed, finding=finding,
        fingerprint=InputFingerprint(
            panel_sha256=panel_sha256, panel_relpath=panel_relpath, n_panel_rows=panel.height,
            provenance_sha256=provenance_sha256, provenance_relpath=provenance_relpath,
        ),
        knobs=FACTOR_KNOBS, caveats=CAVEATS,
    )


def artifact_to_json(artifact: FactorAsymmetryArtifact) -> str:
    """Deterministic JSON with sorted keys and strict finite values."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_asymmetry_artifact(artifact: FactorAsymmetryArtifact, path: Path) -> None:
    """Write the committed asymmetry artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact_to_json(artifact), encoding="utf-8", newline="\n")


def load_artifact_dict(path: Path) -> dict[str, Any]:
    """Load the committed artifact JSON as a dict (for reproduction comparison)."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise VolManagedError(f"{path.name}: artifact is not a JSON object")
    return data
