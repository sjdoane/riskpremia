"""The committed CTREND signal artifact (Study 3, PR2).

The recruiter-facing, regenerable GROSS signal-quality deliverable: the point-in-time
cross-sectional rank IC of the CTREND forecast vs the realized forward return, the
monotonic quintile spread, and the same on the held-out 2022+ window, built from the
committed daily panel. It is the analogue of the VRP Layer-i positive MEASUREMENT before
the Layer-ii gate: a positive gross IC + a monotonic spread is NECESSARY, not sufficient.
The net-of-cost Deflated-Sharpe kill gate (costs + CPCV + the trial-registry multiplicity
deflation) is PR3.

The full per-(week, coin) forecast series is NOT committed (it is a pure function of the
committed panel + the pinned code, the VRP/PR1 discipline); PR3 recomputes it. This artifact
holds only the aggregate summary + the fingerprint, and an offline test rebuilds it from the
committed panel (the IC/spread within a documented tolerance, since the elastic-net selection
flows through scikit-learn / libm and is not bit-identical across platforms). Stdlib + attrs
+ polars; no matplotlib here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import attrs

from riskpremia.ctrend.errors import CtrendError

SCHEMA_VERSION = 1
_STUDY = "crypto cross-sectional trend factor (CTREND, Study 3): the fitted signal (gross quality)"
OOS_START = "2022-01-01"
"""The held-out out-of-sample window start (ADR 0005); the gross signal is reported both
full-sample and on this window, where the published claim is genuinely tested (PR3 gates it)."""

CAVEATS: tuple[str, ...] = (
    "This is the GROSS signal quality (a point-in-time cross-sectional rank IC + a monotonic "
    "quintile spread), the necessary-not-sufficient measurement. It is NOT a Sharpe and says "
    "nothing about net-of-cost survival; the kill gate (realistic costs + event-time-purged "
    "CPCV + the trial-registry DSR deflation) is PR3.",
    "The quintile spread is the EQUAL-WEIGHT mean forward return per quintile (pre-cost), NOT "
    "the paper's value-weighted net portfolio return; the magnitudes are not directly "
    "comparable to the paper's headline.",
    "Deviations from the paper (each a PR3 trial-registry entry): equal-weight OLS (no market "
    "cap on Binance, so no value-weighted SSR); raw weekly returns (the cross-sectional "
    "intercept absorbs the common risk-free rate); the dollar-volume liquid universe; the "
    "canonical indicator conventions where the paper's Appendix A was unobtainable.",
    "Point-in-time: the forecast at week t uses only data realized at or before t-1 (the FM "
    "smoothing window and the elastic-net pool both end at t-1), so the IC is a genuine "
    "out-of-fit cross-sectional rank correlation, not an in-sample fit statistic.",
    "The IC is REGIME-DEPENDENT and not temporally stable: it was significantly NEGATIVE in "
    "2021 (the trend factor inverted) and the positive out-of-sample headline is dominated by "
    "the 2025-2026 regime (see ic_by_year). The aggregate IC reflects the regime mix of the "
    "window; the PR3 kill gate (the trial-registry DSR deflation under CPCV) must account for "
    "this non-stationarity, and the long-only top quintile loses gross in the 2022+ bear "
    "market even though the long-short spread is positive.",
)


@attrs.frozen(slots=True)
class SignalKnobs:
    """The pinned signal-construction choices (each a PR3 trial-registry entry)."""

    top_n: int
    lookback_weeks: int
    min_history_weeks: int
    fit_window: int
    n_quintiles: int
    l1_ratio: float


@attrs.frozen(slots=True)
class GrossQuality:
    """The gross signal quality over a window: the rank IC + the quintile spread."""

    n_weeks: int
    mean_ic: float
    ic_t_stat: float
    frac_positive: float
    quintile_means: tuple[float, ...]
    quintile_spread: float  # top minus bottom quintile mean forward return


@attrs.frozen(slots=True)
class YearIC:
    """The gross rank IC within one calendar year (the regime-stability diagnostic)."""

    year: int
    n_weeks: int
    mean_ic: float
    ic_t_stat: float


@attrs.frozen(slots=True)
class SignalFingerprint:
    """The content-addressed pin: the committed daily panel's decompressed-content SHA256."""

    panel_sha256: str
    n_panel_rows: int
    panel_relpath: str


@attrs.frozen(slots=True)
class SignalArtifact:
    """The committed PR2 deliverable: the gross CTREND signal-quality summary."""

    schema_version: int
    study: str
    currency_quote: str
    window_start: str
    window_end: str
    oos_start: str
    knobs: SignalKnobs
    full_sample: GrossQuality
    out_of_sample: GrossQuality
    ic_by_year: tuple[YearIC, ...]
    fingerprint: SignalFingerprint
    caveats: tuple[str, ...]


def build_signal_artifact(
    full: GrossQuality,
    oos: GrossQuality,
    ic_by_year: tuple[YearIC, ...],
    *,
    currency_quote: str,
    window_start: str,
    window_end: str,
    knobs: SignalKnobs,
    fingerprint: SignalFingerprint,
) -> SignalArtifact:
    """Assemble the committed signal artifact from the full-sample + OOS gross quality."""
    return SignalArtifact(
        schema_version=SCHEMA_VERSION,
        study=_STUDY,
        currency_quote=currency_quote,
        window_start=window_start,
        window_end=window_end,
        oos_start=OOS_START,
        knobs=knobs,
        full_sample=full,
        out_of_sample=oos,
        ic_by_year=ic_by_year,
        fingerprint=fingerprint,
        caveats=CAVEATS,
    )


def artifact_to_json(artifact: SignalArtifact) -> str:
    """Deterministic JSON (sorted keys, round-trip-exact floats, trailing newline)."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_signal_artifact(artifact: SignalArtifact, path: Path) -> None:
    """Write the artifact JSON with LF newlines (the committed-byte contract)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact_to_json(artifact), encoding="utf-8", newline="\n")


def _req(d: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        raise CtrendError(f"signal artifact {ctx} missing required key {key!r}")
    return d[key]


def _gross_from_dict(d: dict[str, Any], ctx: str) -> GrossQuality:
    return GrossQuality(
        n_weeks=int(_req(d, "n_weeks", ctx)),
        mean_ic=float(_req(d, "mean_ic", ctx)),
        ic_t_stat=float(_req(d, "ic_t_stat", ctx)),
        frac_positive=float(_req(d, "frac_positive", ctx)),
        quintile_means=tuple(float(v) for v in _req(d, "quintile_means", ctx)),
        quintile_spread=float(_req(d, "quintile_spread", ctx)),
    )


def artifact_from_dict(data: dict[str, Any]) -> SignalArtifact:
    """Reconstruct a SignalArtifact from parsed JSON, raising loudly on a bad shape."""
    knobs = _req(data, "knobs", "root")
    fp = _req(data, "fingerprint", "root")
    return SignalArtifact(
        schema_version=int(_req(data, "schema_version", "root")),
        study=str(_req(data, "study", "root")),
        currency_quote=str(_req(data, "currency_quote", "root")),
        window_start=str(_req(data, "window_start", "root")),
        window_end=str(_req(data, "window_end", "root")),
        oos_start=str(_req(data, "oos_start", "root")),
        knobs=SignalKnobs(
            top_n=int(_req(knobs, "top_n", "knobs")),
            lookback_weeks=int(_req(knobs, "lookback_weeks", "knobs")),
            min_history_weeks=int(_req(knobs, "min_history_weeks", "knobs")),
            fit_window=int(_req(knobs, "fit_window", "knobs")),
            n_quintiles=int(_req(knobs, "n_quintiles", "knobs")),
            l1_ratio=float(_req(knobs, "l1_ratio", "knobs")),
        ),
        full_sample=_gross_from_dict(_req(data, "full_sample", "root"), "full_sample"),
        out_of_sample=_gross_from_dict(_req(data, "out_of_sample", "root"), "out_of_sample"),
        ic_by_year=tuple(
            YearIC(
                year=int(_req(y, "year", "ic_by_year")),
                n_weeks=int(_req(y, "n_weeks", "ic_by_year")),
                mean_ic=float(_req(y, "mean_ic", "ic_by_year")),
                ic_t_stat=float(_req(y, "ic_t_stat", "ic_by_year")),
            )
            for y in _req(data, "ic_by_year", "root")
        ),
        fingerprint=SignalFingerprint(
            panel_sha256=str(_req(fp, "panel_sha256", "fingerprint")),
            n_panel_rows=int(_req(fp, "n_panel_rows", "fingerprint")),
            panel_relpath=str(_req(fp, "panel_relpath", "fingerprint")),
        ),
        caveats=tuple(str(c) for c in _req(data, "caveats", "root")),
    )


def load_signal_artifact(path: Path) -> SignalArtifact:
    """Load and validate a committed signal artifact JSON into a typed object."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise CtrendError(f"signal artifact {path.name} is not a JSON object")
    return artifact_from_dict(data)
