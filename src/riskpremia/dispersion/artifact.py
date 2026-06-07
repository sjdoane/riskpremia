"""Build the funding-dispersion artifact from the committed daily series (Study 7, ADR 0009).

The daily dispersion series is the measured object; this module adds the significance and the
regime characterization with the vendored stationary-block bootstrap (the same machinery the
Study 2 variance-premium measurement used). The headline is the equal-weight cross-sectional
interquartile-range level with a confidence interval, the pre-versus-post-ETF difference, and a
decay slope. The standard deviations and the gross high-minus-low sort premium are secondary,
explicitly non-deployable, measured objects. The bootstrap is on the FULL daily series (the
dependence is funding-regime persistence, absorbed by the Politis-White block length), not a
strided series, and the reported statements are a level and a signed difference and slope, never
a vacuous clears-zero test on a positive-by-construction spread.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import attrs
import polars as pl

from riskpremia.analytics.bootstrap import politis_white_block_length, stationary_block_bootstrap
from riskpremia.dispersion.errors import DispersionError

SCHEMA_VERSION = 1
_STUDY = "Crypto funding-rate dispersion measurement (Study 7, ADR 0009)"
SPOT_ETF = date(2024, 1, 11)
BOOTSTRAP_SEED = 20260607
N_BOOT = 2000
CI_ALPHA = 0.05
DECAY_PLOT_WINDOW_DAYS = 90  # figure rolling-median smoother only; slope is OLS on raw daily IQR
TRADING_DAYS_PER_YEAR = 365.0  # crypto trades every day

CAVEATS: tuple[str, ...] = (
    "This is a descriptive measurement (like a volatility surface), explicitly NOT a tradeable "
    "verdict and NOT a positive result in the make-money sense.",
    "Non-deployable: capturing the cross-sectional funding spread requires shorting a wide "
    "altcoin-perp cross-section, which US retail cannot access, on a venue (Binance) that is not "
    "US-tradeable. No tradeable Sharpe is quoted.",
    "Each funding event is annualized by its own funding interval (basis 365 times 24) before "
    "any cross-sectional comparison, so the dispersion is not a units artifact; 4-hour and "
    "8-hour settlements are aligned onto a common daily grid by a point-in-time carry-forward.",
    "The headline is the equal-weight cross-sectional interquartile range (robust to small-cap "
    "tails); the standard deviation and the gross high-minus-low sort premium are secondary "
    "diagnostics. The universe is the point-in-time liquid spot set; not every eligible coin has "
    "a perp funding series, so a per-day coverage ratio is reported.",
)


@attrs.frozen(slots=True)
class DispersionStat:
    """A bootstrapped level statistic of a daily series."""

    label: str
    mean: float
    ci_low: float
    ci_high: float
    raw_t: int
    effective_t: int
    block_length: float


@attrs.frozen(slots=True)
class RegimeSplit:
    """The pre-versus-post-ETF dispersion level and the bootstrapped difference."""

    pre_mean: float
    post_mean: float
    n_pre: int
    n_post: int
    difference: float
    diff_ci_low: float
    diff_ci_high: float


@attrs.frozen(slots=True)
class DecaySlope:
    """The OLS slope of the daily dispersion on calendar years, with a block-bootstrap CI."""

    slope_per_year: float
    ci_low: float
    ci_high: float


@attrs.frozen(slots=True)
class Coverage:
    """The point-in-time eligible-versus-funded coverage of the universe."""

    mean_n_eligible: float
    mean_n_funded: float
    mean_coverage_ratio: float
    min_coverage_ratio: float


@attrs.frozen(slots=True)
class Knobs:
    """The frozen measurement knobs recorded in the artifact."""

    spot_etf: str
    bootstrap_seed: int
    n_boot: int
    ci_alpha: float
    decay_plot_window_days: int  # the figure rolling-median window; not the headline slope


@attrs.frozen(slots=True)
class InputFingerprint:
    """Content pin for the committed series and its provenance."""

    series_sha256: str
    series_relpath: str
    n_series_rows: int
    provenance_sha256: str
    provenance_relpath: str


@attrs.frozen(slots=True)
class DispersionArtifact:
    """The committed Study 7 measurement artifact."""

    schema_version: int
    study: str
    data_start: str
    data_end: str
    n_days: int
    knobs: Knobs
    fingerprint: InputFingerprint
    iqr_full: DispersionStat
    iqr_regime: RegimeSplit
    iqr_decay: DecaySlope
    std_full_mean: float
    winsor_std_full_mean: float
    sort_premium: DispersionStat
    coverage: Coverage
    headline: str
    caveats: tuple[str, ...]


def _percentile(values: Sequence[float], q: float) -> float:
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    return s[lo] * (1.0 - (pos - lo)) + s[hi] * (pos - lo)


def _block_length(series: Sequence[float]) -> float:
    return max(2.0, politis_white_block_length(series))


def _bootstrap_means(series: Sequence[float], *, seed: int) -> list[float]:
    paths = stationary_block_bootstrap(
        list(series), N_BOOT, expected_block_length=_block_length(series), seed=seed
    )
    return [statistics.fmean(p) for p in paths]


def _level_stat(label: str, series: Sequence[float], *, seed: int) -> DispersionStat:
    if len(series) < 2:
        raise DispersionError(f"{label}: need at least two observations")
    means = _bootstrap_means(series, seed=seed)
    block = _block_length(series)
    return DispersionStat(
        label=label,
        mean=statistics.fmean(series),
        ci_low=_percentile(means, CI_ALPHA / 2.0),
        ci_high=_percentile(means, 1.0 - CI_ALPHA / 2.0),
        raw_t=len(series),
        effective_t=max(2, int(len(series) / block)),
        block_length=block,
    )


def _regime(series: Sequence[float], etf_index: int, *, seed: int) -> RegimeSplit:
    pre = list(series[:etf_index])
    post = list(series[etf_index:])
    if len(pre) < 2 or len(post) < 2:
        raise DispersionError("each regime needs at least two observations")
    pre_means = _bootstrap_means(pre, seed=seed)
    post_means = _bootstrap_means(post, seed=seed + 1)
    diffs = [po - pr for pr, po in zip(pre_means, post_means, strict=True)]
    return RegimeSplit(
        pre_mean=statistics.fmean(pre),
        post_mean=statistics.fmean(post),
        n_pre=len(pre),
        n_post=len(post),
        difference=statistics.fmean(post) - statistics.fmean(pre),
        diff_ci_low=_percentile(diffs, CI_ALPHA / 2.0),
        diff_ci_high=_percentile(diffs, 1.0 - CI_ALPHA / 2.0),
    )


def _ols_slope(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0.0:
        raise DispersionError("decay slope has zero x-variance")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    return slope, my - slope * mx


def _decay(days_since_start: Sequence[float], series: Sequence[float], *, seed: int) -> DecaySlope:
    """OLS slope of the dispersion on calendar years, with a residual block-bootstrap CI."""
    years = [d / TRADING_DAYS_PER_YEAR for d in days_since_start]
    slope, intercept = _ols_slope(years, series)
    fitted = [intercept + slope * y for y in years]
    residuals = [s - f for s, f in zip(series, fitted, strict=True)]
    paths = stationary_block_bootstrap(
        residuals, N_BOOT, expected_block_length=_block_length(residuals), seed=seed
    )
    slopes: list[float] = []
    for resampled in paths:
        synthetic = [f + r for f, r in zip(fitted, resampled, strict=True)]
        slopes.append(_ols_slope(years, synthetic)[0])
    return DecaySlope(
        slope_per_year=slope,
        ci_low=_percentile(slopes, CI_ALPHA / 2.0),
        ci_high=_percentile(slopes, 1.0 - CI_ALPHA / 2.0),
    )


def build_artifact(
    series: pl.DataFrame,
    *,
    series_sha256: str,
    series_relpath: str,
    provenance_sha256: str,
    provenance_relpath: str,
) -> DispersionArtifact:
    """Build the Study 7 measurement artifact from the committed daily dispersion series."""
    frame = series.sort("date")
    dates: list[date] = frame["date"].to_list()
    iqr = [float(x) for x in frame["iqr"].to_list()]
    std = [float(x) for x in frame["std"].to_list()]
    winsor = [float(x) for x in frame["winsor_std"].to_list()]
    n_eligible = [int(x) for x in frame["n_eligible"].to_list()]
    n_funded = [int(x) for x in frame["n_funded"].to_list()]
    sort_pairs = [
        (d, float(v))
        for d, v in zip(dates, frame["sort_premium"].to_list(), strict=True)
        if v is not None
    ]

    etf_index = next((i for i, d in enumerate(dates) if d >= SPOT_ETF), len(dates))
    days_since = [float((d - dates[0]).days) for d in dates]

    iqr_full = _level_stat("equity_weight_iqr", iqr, seed=BOOTSTRAP_SEED)
    iqr_regime = _regime(iqr, etf_index, seed=BOOTSTRAP_SEED + 10)
    iqr_decay = _decay(days_since, iqr, seed=BOOTSTRAP_SEED + 20)
    sort_series = [v for _, v in sort_pairs]
    sort_stat = _level_stat("gross_sort_premium", sort_series, seed=BOOTSTRAP_SEED + 30)

    coverage_ratios = [f / e for e, f in zip(n_eligible, n_funded, strict=True) if e > 0]
    coverage = Coverage(
        mean_n_eligible=statistics.fmean(n_eligible),
        mean_n_funded=statistics.fmean(n_funded),
        mean_coverage_ratio=statistics.fmean(coverage_ratios),
        min_coverage_ratio=min(coverage_ratios),
    )

    headline = (
        f"Cross-sectional funding dispersion is alive but decaying and non-deployable: "
        f"post-ETF equal-weight IQR {iqr_regime.post_mean:.3f} vs pre-ETF "
        f"{iqr_regime.pre_mean:.3f} annualized (difference {iqr_regime.difference:+.3f}, "
        f"95% CI [{iqr_regime.diff_ci_low:+.3f}, {iqr_regime.diff_ci_high:+.3f}]); decay slope "
        f"{iqr_decay.slope_per_year:+.3f}/yr (95% CI [{iqr_decay.ci_low:+.3f}, "
        f"{iqr_decay.ci_high:+.3f}]). Gross high-minus-low sort premium "
        f"{sort_stat.mean:.3f} annualized, not retail-capturable."
    )
    return DispersionArtifact(
        schema_version=SCHEMA_VERSION,
        study=_STUDY,
        data_start=dates[0].isoformat(),
        data_end=dates[-1].isoformat(),
        n_days=len(dates),
        knobs=Knobs(
            spot_etf=SPOT_ETF.isoformat(),
            bootstrap_seed=BOOTSTRAP_SEED,
            n_boot=N_BOOT,
            ci_alpha=CI_ALPHA,
            decay_plot_window_days=DECAY_PLOT_WINDOW_DAYS,
        ),
        fingerprint=InputFingerprint(
            series_sha256=series_sha256,
            series_relpath=series_relpath,
            n_series_rows=frame.height,
            provenance_sha256=provenance_sha256,
            provenance_relpath=provenance_relpath,
        ),
        iqr_full=iqr_full,
        iqr_regime=iqr_regime,
        iqr_decay=iqr_decay,
        std_full_mean=statistics.fmean(std),
        winsor_std_full_mean=statistics.fmean(winsor),
        sort_premium=sort_stat,
        coverage=coverage,
        headline=headline,
        caveats=CAVEATS,
    )


def artifact_to_json(artifact: DispersionArtifact) -> str:
    """Deterministic JSON with sorted keys and strict finite values."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_artifact(artifact: DispersionArtifact, path: Path) -> None:
    """Write the committed measurement artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact_to_json(artifact), encoding="utf-8", newline="\n")


def load_artifact_dict(path: Path) -> dict[str, Any]:
    """Load the committed artifact JSON as a dict (for reproduction comparison)."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise DispersionError(f"{path.name}: artifact is not a JSON object")
    return data
