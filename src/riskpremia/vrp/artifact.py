"""The committed Layer-i VRP measurement artifact (ADR 0004 PR5b).

A regenerable JSON artifact carrying the honest VRP headline, the regime
decomposition, an alignment-count diagnostic, the dataset fingerprint, the binding
caveats, and the daily series the figures render from. It holds AGGREGATE measurement
numbers plus the daily implied/realized/VRP series (no raw vendor data beyond the
daily closes the measurement is built on); the raw exchange bytes stay in the
gitignored cache, and the daily-close inputs live in the committed CSV fixtures whose
SHA256 the `fingerprint` pins.

The artifact is a PURE FUNCTION of the two committed fixtures (`vrp/fixtures.py`):
`scripts/build_vrp_artifact.py` builds it once from the real data, and an offline test
rebuilds the headline from the fixtures and asserts it matches. The figures
(`vrp/figures.py`) render PURELY from this committed artifact, never recomputing the
bootstrap, so the published PNG cannot drift from the published CI.

Determinism: serialized with `json.dumps(..., sort_keys=True, indent=2)` (round-trip-
exact float `repr`, stable key order) and written with LF (`.gitattributes` pins
`artifacts/**/*.json eol=lf`). The stochastic inference knobs (`seed`, `n_boot`, the
resolved bootstrap block length) are recorded in `inference` so the committed CI is
regenerable without relying on a function default that could later change. Stdlib +
attrs + polars only; matplotlib is NEVER imported here (the render-only dependency
lives in `figures.py`).
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

import attrs
import polars as pl

from riskpremia.data.clock import SPOT_ETF_LAUNCH
from riskpremia.vrp.errors import VrpError
from riskpremia.vrp.measurement import VrpHeadline

SCHEMA_VERSION = 1
_STUDY = "crypto variance risk premium (Layer i, the reproducible measurement floor)"
_VOL_POINTS = 100.0

CAVEATS: tuple[str, ...] = (
    "The headline is the VRP MEASUREMENT plus the regime-conditional decomposition, "
    "never a short-volatility Sharpe; the tradeable verdict is Layer ii (ADR 0004).",
    "Cross-underlying basis: the implied leg is the Deribit BTC index (DVOL), the "
    "realized leg the Binance spot close, so the premium is a cross-underlying proxy.",
    "The point estimate is the median of the W non-overlapping strided-phase means; "
    "the 95 percent CI is the block-bootstrap interval of the phase-0 strided series "
    "(overlap-honest), not the CI of the median-phase mean.",
    "The vol-point spread (figure 1) is a distinct payoff object from the variance "
    "premium (the headline); they differ by the vol-of-vol convexity gap.",
)
"""The binding honesty caveats carried WITH the numbers (design review H3/H4), so an
exhibit that travels without the README still carries them."""

_CI_METHOD = (
    "stationary block bootstrap (Politis-Romano 1994), 95 percent, on the phase-0 "
    "non-overlapping strided forward-VRP series; T deflated by the Politis-White block"
)
_POINT_ESTIMATE = "median of the W non-overlapping strided-phase means"


@attrs.frozen(slots=True)
class InferenceParams:
    """The pinned knobs that make the committed CI regenerable (design review C2)."""

    seed: int
    n_boot: int
    expected_block_length: float
    ci_method: str
    point_estimate: str


@attrs.frozen(slots=True)
class RegimeStat:
    """Descriptive forward-VRP statistics for one spot-ETF regime."""

    name: str
    n_obs: int
    mean_vrp_forward: float
    frac_positive: float
    mean_implied_vol_pct: float
    mean_realized_vol_pct: float


@attrs.frozen(slots=True)
class AlignmentCounts:
    """The build alignment diagnostic: where rows were dropped (PR5a review nit).

    Surfaces a silent join shortfall (e.g. DVOL days with no matching spot/realized
    window), so a reviewer sees the funnel from raw days to scored observations.
    """

    n_dvol_days: int
    n_spot_days: int
    n_aligned_rows: int
    n_realized_forward_nonnull: int
    n_forward_obs: int


@attrs.frozen(slots=True)
class DatasetFingerprint:
    """The content-addressed pin: the committed fixtures' SHA256s + row counts."""

    dvol_sha256: str
    spot_sha256: str
    n_dvol_rows: int
    n_spot_rows: int
    dvol_relpath: str
    spot_relpath: str


@attrs.frozen(slots=True)
class VrpSeries:
    """The daily series the figures render from (columnar; tail rv-forward is null).

    `dvol_vol_pct` is the DVOL implied vol in points; `realized_vol_pct_forward` is
    `100 * sqrt(rv_forward)` (null on the last `window_days` rows that have no forward
    window); `vrp_forward` is the variance premium (the headline object). The variance
    legs (`implied_var`, `rv_forward`) are recoverable from the vol-point columns.
    """

    date: tuple[str, ...]
    dvol_vol_pct: tuple[float, ...]
    realized_vol_pct_forward: tuple[float | None, ...]
    vrp_forward: tuple[float | None, ...]
    regime: tuple[str, ...]


@attrs.frozen(slots=True)
class VrpArtifact:
    """The committed Layer-i measurement deliverable."""

    schema_version: int
    study: str
    currency: str
    window_days: int
    date_start: str
    date_end: str
    etf_launch: str
    inference: InferenceParams
    headline: VrpHeadline
    regimes: tuple[RegimeStat, ...]
    alignment: AlignmentCounts
    fingerprint: DatasetFingerprint
    caveats: tuple[str, ...]
    series: VrpSeries


def _regime_stat(vrp_frame: pl.DataFrame, name: str) -> RegimeStat:
    """Descriptive forward-VRP stats for one regime (forward-VRP-non-null rows)."""
    sub = vrp_frame.filter((pl.col("regime") == name) & pl.col("vrp_forward").is_not_null())
    n = sub.height
    if n == 0:
        nan = float("nan")
        return RegimeStat(name, 0, nan, nan, nan, nan)
    vrp = [float(v) for v in sub["vrp_forward"].to_list()]
    # vrp_forward is non-null iff rv_forward is non-null, so the realized leg is safe.
    return RegimeStat(
        name=name,
        n_obs=n,
        mean_vrp_forward=statistics.fmean(vrp),
        frac_positive=sum(1 for v in vrp if v > 0) / n,
        mean_implied_vol_pct=statistics.fmean(float(v) for v in sub["dvol_close"].to_list()),
        mean_realized_vol_pct=statistics.fmean(
            _VOL_POINTS * math.sqrt(float(v)) for v in sub["rv_forward"].to_list()
        ),
    )


def build_artifact(
    vrp_frame: pl.DataFrame,
    headline: VrpHeadline,
    *,
    currency: str,
    window_days: int,
    seed: int,
    n_boot: int,
    fingerprint: DatasetFingerprint,
    n_dvol_days: int,
    n_spot_days: int,
) -> VrpArtifact:
    """Assemble the committed artifact from the built frame and its honest headline.

    `n_dvol_days` / `n_spot_days` are the unique input day counts (passed by the
    caller, which holds the records) so the alignment diagnostic can show the funnel.
    """
    if vrp_frame.height == 0:
        raise VrpError("build_artifact requires a non-empty VRP frame")
    dates = [d.isoformat() for d in vrp_frame["date"].to_list()]
    rv_forward = vrp_frame["rv_forward"].to_list()
    realized_vol_pct = tuple(
        None if v is None else _VOL_POINTS * math.sqrt(float(v)) for v in rv_forward
    )
    vrp_forward = tuple(
        None if v is None else float(v) for v in vrp_frame["vrp_forward"].to_list()
    )
    series = VrpSeries(
        date=tuple(dates),
        dvol_vol_pct=tuple(float(v) for v in vrp_frame["dvol_close"].to_list()),
        realized_vol_pct_forward=realized_vol_pct,
        vrp_forward=vrp_forward,
        regime=tuple(str(v) for v in vrp_frame["regime"].to_list()),
    )
    alignment = AlignmentCounts(
        n_dvol_days=n_dvol_days,
        n_spot_days=n_spot_days,
        n_aligned_rows=vrp_frame.height,
        n_realized_forward_nonnull=int(vrp_frame["rv_forward"].is_not_null().sum()),
        n_forward_obs=headline.n_forward_obs,
    )
    inference = InferenceParams(
        seed=seed,
        n_boot=n_boot,
        expected_block_length=max(2.0, headline.pw_block_length),
        ci_method=_CI_METHOD,
        point_estimate=_POINT_ESTIMATE,
    )
    return VrpArtifact(
        schema_version=SCHEMA_VERSION,
        study=_STUDY,
        currency=currency,
        window_days=window_days,
        date_start=dates[0],
        date_end=dates[-1],
        etf_launch=SPOT_ETF_LAUNCH.date().isoformat(),
        inference=inference,
        headline=headline,
        regimes=(_regime_stat(vrp_frame, "pre_etf"), _regime_stat(vrp_frame, "post_etf")),
        alignment=alignment,
        fingerprint=fingerprint,
        caveats=CAVEATS,
        series=series,
    )


def artifact_to_json(artifact: VrpArtifact) -> str:
    """Deterministic JSON (sorted keys, round-trip-exact floats, trailing newline).

    `allow_nan=False` makes a non-finite value (e.g. an empty regime's NaN mean) raise
    at write time rather than emit a bare `NaN` token that strict JSON parsers reject
    (the loud-failure discipline; the shipped full-range artifact has no empty regime).
    """
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_artifact(artifact: VrpArtifact, path: Path) -> None:
    """Write the artifact JSON with LF newlines (the committed-byte contract)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact_to_json(artifact), encoding="utf-8", newline="\n")


def _req(d: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        raise VrpError(f"artifact {ctx} missing required key {key!r}")
    return d[key]


def _nullable_floats(values: Any) -> tuple[float | None, ...]:
    return tuple(None if v is None else float(v) for v in values)


def artifact_from_dict(data: dict[str, Any]) -> VrpArtifact:
    """Reconstruct a VrpArtifact from the parsed JSON, raising loudly on a bad shape."""
    inf = _req(data, "inference", "root")
    head = _req(data, "headline", "root")
    align = _req(data, "alignment", "root")
    fp = _req(data, "fingerprint", "root")
    ser = _req(data, "series", "root")
    regimes = _req(data, "regimes", "root")
    return VrpArtifact(
        schema_version=int(_req(data, "schema_version", "root")),
        study=str(_req(data, "study", "root")),
        currency=str(_req(data, "currency", "root")),
        window_days=int(_req(data, "window_days", "root")),
        date_start=str(_req(data, "date_start", "root")),
        date_end=str(_req(data, "date_end", "root")),
        etf_launch=str(_req(data, "etf_launch", "root")),
        inference=InferenceParams(
            seed=int(_req(inf, "seed", "inference")),
            n_boot=int(_req(inf, "n_boot", "inference")),
            expected_block_length=float(_req(inf, "expected_block_length", "inference")),
            ci_method=str(_req(inf, "ci_method", "inference")),
            point_estimate=str(_req(inf, "point_estimate", "inference")),
        ),
        headline=VrpHeadline(
            window_days=int(_req(head, "window_days", "headline")),
            n_forward_obs=int(_req(head, "n_forward_obs", "headline")),
            n_strided=int(_req(head, "n_strided", "headline")),
            mean_vrp_forward=float(_req(head, "mean_vrp_forward", "headline")),
            mean_phase_median=float(_req(head, "mean_phase_median", "headline")),
            mean_phase_min=float(_req(head, "mean_phase_min", "headline")),
            mean_phase_max=float(_req(head, "mean_phase_max", "headline")),
            ci_low=float(_req(head, "ci_low", "headline")),
            ci_high=float(_req(head, "ci_high", "headline")),
            effective_t=float(_req(head, "effective_t", "headline")),
            pw_block_length=float(_req(head, "pw_block_length", "headline")),
            frac_positive=float(_req(head, "frac_positive", "headline")),
            mean_vrp_pre_etf=float(_req(head, "mean_vrp_pre_etf", "headline")),
            mean_vrp_post_etf=float(_req(head, "mean_vrp_post_etf", "headline")),
            mean_vol_spread_forward=float(_req(head, "mean_vol_spread_forward", "headline")),
        ),
        regimes=tuple(
            RegimeStat(
                name=str(_req(r, "name", "regime")),
                n_obs=int(_req(r, "n_obs", "regime")),
                mean_vrp_forward=float(_req(r, "mean_vrp_forward", "regime")),
                frac_positive=float(_req(r, "frac_positive", "regime")),
                mean_implied_vol_pct=float(_req(r, "mean_implied_vol_pct", "regime")),
                mean_realized_vol_pct=float(_req(r, "mean_realized_vol_pct", "regime")),
            )
            for r in regimes
        ),
        alignment=AlignmentCounts(
            n_dvol_days=int(_req(align, "n_dvol_days", "alignment")),
            n_spot_days=int(_req(align, "n_spot_days", "alignment")),
            n_aligned_rows=int(_req(align, "n_aligned_rows", "alignment")),
            n_realized_forward_nonnull=int(_req(align, "n_realized_forward_nonnull", "alignment")),
            n_forward_obs=int(_req(align, "n_forward_obs", "alignment")),
        ),
        fingerprint=DatasetFingerprint(
            dvol_sha256=str(_req(fp, "dvol_sha256", "fingerprint")),
            spot_sha256=str(_req(fp, "spot_sha256", "fingerprint")),
            n_dvol_rows=int(_req(fp, "n_dvol_rows", "fingerprint")),
            n_spot_rows=int(_req(fp, "n_spot_rows", "fingerprint")),
            dvol_relpath=str(_req(fp, "dvol_relpath", "fingerprint")),
            spot_relpath=str(_req(fp, "spot_relpath", "fingerprint")),
        ),
        caveats=tuple(str(c) for c in _req(data, "caveats", "root")),
        series=VrpSeries(
            date=tuple(str(d) for d in _req(ser, "date", "series")),
            dvol_vol_pct=tuple(float(v) for v in _req(ser, "dvol_vol_pct", "series")),
            realized_vol_pct_forward=_nullable_floats(
                _req(ser, "realized_vol_pct_forward", "series")
            ),
            vrp_forward=_nullable_floats(_req(ser, "vrp_forward", "series")),
            regime=tuple(str(r) for r in _req(ser, "regime", "series")),
        ),
    )


def load_artifact(path: Path) -> VrpArtifact:
    """Load and validate a committed artifact JSON into a typed VrpArtifact."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise VrpError(f"artifact {path.name} is not a JSON object")
    return artifact_from_dict(data)
