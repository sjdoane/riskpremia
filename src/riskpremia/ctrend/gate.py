"""The CTREND net-of-cost gate and verdict (Study 3, PR3).

This is the ADR 0005 kill gate for the first fitted signal in the project. The input
forecast frame is recomputed from the committed daily panel; this module turns those
weekly forecasts into equal-weight quintile portfolios, charges realistic spot turnover
costs, records the realized trial family, and scores the OOS 2022+ net returns with the
vendored DSR stack under event-time-purged CPCV.

The retail headline is the long-only top quintile. The academic top-minus-bottom
long-short is reported separately and cannot rescue a failing long-only retail result.
The long-short short leg is a comparison to the paper, not a deployable retail claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import tempfile
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import attrs
import polars as pl

from riskpremia.analytics.sharpe import dsr
from riskpremia.ctrend.errors import CtrendError
from riskpremia.execution.cost import TRADEABLE_VENUES, VenueCostModel
from riskpremia.execution.scoring import effective_sample_size, make_purged_cpcv, return_moments
from riskpremia.validation.trial_registry import TrialRegistry

SCHEMA_VERSION = 1
OOS_START = "2022-01-01"
VIABILITY_BAR = 0.95
TRIAL_NAIVE_EFFECTIVE_N = 8
MISSING_RETURN_LOSS = -1.0
_STUDY = "crypto cross-sectional trend factor (CTREND, Study 3): net-of-cost gate"
_STRATEGY_FAMILY = "ctrend_gate_pr3"

PortfolioKind = Literal["long_only_top", "long_short_top_minus_bottom"]
ExecutionStyle = Literal["taker", "maker"]
MissingReturnPolicy = Literal["delisting_loss", "drop_and_renormalize"]

PRIMARY_PORTFOLIO: PortfolioKind = "long_only_top"
ACADEMIC_PORTFOLIO: PortfolioKind = "long_short_top_minus_bottom"
PRIMARY_EXECUTION: ExecutionStyle = "taker"
PRIMARY_MISSING_POLICY: MissingReturnPolicy = "delisting_loss"

CAVEATS: tuple[str, ...] = (
    "The retail headline is the LONG-ONLY top quintile. The long-short top-minus-bottom "
    "series is the academic comparison to the paper and is not a deployable retail claim: "
    "bottom-quintile alt shorts require borrow, listing, and squeeze/delisting modeling.",
    "The Binance liquid universe is not a US-venue listing intersection. A pass would need "
    "a US-listed-universe rebuild before belief; a fail remains a no-deploy result for this "
    "liquid-universe replication.",
    "The spot half-spread is the carry study's provisional 2 bps assumption, which is "
    "favourable for a top-100 alt basket. Failing under this low-cost assumption is robust "
    "to wider measured alt spreads; any pass would require a measured spread rebuild.",
    "Missing selected forward returns are treated as a -100% delisting loss in the headline "
    "and counted. A favourable drop-and-renormalize sensitivity is recorded in the trial "
    "ledger but does not drive the verdict.",
    "The gate statistic is the minimum purged CPCV test-fold DSR on the 2022+ OOS weekly "
    "series, not only the full-window DSR. This deliberately prices regime instability in "
    "the anti-false-pass direction.",
)


@attrs.frozen(slots=True)
class GateKnobs:
    """The pinned construction and scoring choices for the PR3 gate."""

    top_n: int
    lookback_weeks: int
    min_history_weeks: int
    fit_window: int
    n_quintiles: int
    oos_start: str = OOS_START
    missing_return_loss: float = MISSING_RETURN_LOSS
    trial_naive_effective_n: int = TRIAL_NAIVE_EFFECTIVE_N


@attrs.frozen(slots=True)
class CostVenue:
    """The spot-only cost view of a carry `VenueCostModel`."""

    name: str
    tradeable: bool
    spot_taker_cost: float
    spot_maker_cost: float
    spread_basis: str
    provisional: bool
    source: str


@attrs.frozen(slots=True)
class GateFingerprint:
    """Content fingerprints for the committed inputs and generated forecast/series."""

    panel_sha256: str
    n_panel_rows: int
    panel_relpath: str
    n_forecast_rows: int
    forecast_sha256: str


@attrs.frozen(slots=True)
class WeeklySeries:
    """The weekly portfolio series carried in the artifact for reproduction and figures."""

    week_end: tuple[str, ...]
    gross_return: tuple[float, ...]
    turnover: tuple[float, ...]
    cost: tuple[float, ...]
    net_return: tuple[float, ...]
    n_long: tuple[int, ...]
    n_short: tuple[int, ...]
    n_missing_returns: tuple[int, ...]


@attrs.frozen(slots=True)
class TrialRecord:
    """One realized design-family variant recorded into the trial ledger."""

    portfolio: PortfolioKind
    execution: ExecutionStyle
    missing_policy: MissingReturnPolicy
    sr_hat: float
    gamma_3: float
    gamma_4: float
    raw_t: int
    effective_t: int
    pw_block_length: float
    mean_gross: float
    mean_net: float
    mean_turnover: float
    total_cost: float
    missing_returns: int
    dropped_weeks: int
    series_sha256: str


@attrs.frozen(slots=True)
class CpcvSummary:
    """The event-time-purged CPCV settings and split-level DSRs for a portfolio."""

    n_groups: int
    k_test: int
    horizon_events: int
    n_splits: int
    expected_path_count: int
    min_train_size: int
    min_test_size: int
    split_dsrs: tuple[float, ...]


@attrs.frozen(slots=True)
class PortfolioScore:
    """The scored OOS gate result for one primary portfolio."""

    portfolio: PortfolioKind
    execution: ExecutionStyle
    missing_policy: MissingReturnPolicy
    raw_t: int
    effective_t: int
    pw_block_length: float
    sr_hat: float
    gamma_3: float
    gamma_4: float
    mean_gross: float
    mean_net: float
    mean_turnover: float
    total_cost: float
    missing_returns: int
    dropped_weeks: int
    n_effective: int
    v_sr: float
    full_oos_dsr: float
    cpcv_min_dsr: float
    cpcv_median_dsr: float
    cpcv_max_dsr: float
    passes: bool
    series_sha256: str
    cpcv: CpcvSummary
    series: WeeklySeries


@attrs.frozen(slots=True)
class GateVerdict:
    """The retail and academic verdicts from the PR3 gate."""

    retail_non_viable: bool
    academic_non_viable: bool
    retail_reason: str
    academic_reason: str
    headline: str


@attrs.frozen(slots=True)
class GateArtifact:
    """The committed CTREND PR3 gate artifact."""

    schema_version: int
    study: str
    window_start: str
    window_end: str
    viability_bar: float
    knobs: GateKnobs
    fingerprint: GateFingerprint
    cost_venues: tuple[CostVenue, ...]
    trial_records: tuple[TrialRecord, ...]
    retail_long_only: PortfolioScore
    academic_long_short: PortfolioScore
    verdict: GateVerdict
    caveats: tuple[str, ...]


@attrs.frozen(slots=True)
class _WeeklyPoint:
    week_end: date
    gross_return: float
    turnover: float
    cost: float
    net_return: float
    n_long: int
    n_short: int
    n_missing_returns: int


@attrs.frozen(slots=True)
class _BacktestSeries:
    portfolio: PortfolioKind
    execution: ExecutionStyle
    missing_policy: MissingReturnPolicy
    points: tuple[_WeeklyPoint, ...]
    missing_returns: int
    dropped_weeks: int

    @property
    def net_returns(self) -> list[float]:
        return [p.net_return for p in self.points]

    @property
    def gross_returns(self) -> list[float]:
        return [p.gross_return for p in self.points]

    @property
    def turnovers(self) -> list[float]:
        return [p.turnover for p in self.points]

    @property
    def costs(self) -> list[float]:
        return [p.cost for p in self.points]


def cost_venues(models: Sequence[VenueCostModel] = TRADEABLE_VENUES) -> tuple[CostVenue, ...]:
    """Return the spot-only cost table for the tradeable venue models."""
    return tuple(
        CostVenue(
            name=m.name,
            tradeable=m.tradeable,
            spot_taker_cost=m.leg_cost_fraction(leg="spot", taker=True),
            spot_maker_cost=m.leg_cost_fraction(leg="spot", taker=False),
            spread_basis=m.spread_basis,
            provisional=m.provisional,
            source=m.source,
        )
        for m in models
    )


def _format_float(value: float) -> str:
    return format(value, ".17g")


def _series_hash(points: Sequence[_WeeklyPoint]) -> str:
    h = hashlib.sha256()
    for p in points:
        parts = (
            p.week_end.isoformat(),
            _format_float(p.gross_return),
            _format_float(p.turnover),
            _format_float(p.cost),
            _format_float(p.net_return),
            str(p.n_long),
            str(p.n_short),
            str(p.n_missing_returns),
        )
        h.update(("|".join(parts) + "\n").encode("utf-8"))
    return h.hexdigest()


def forecast_frame_sha256(forecasts: pl.DataFrame) -> str:
    """A deterministic audit hash of the score-driving forecast frame.

    The raw CTREND float can drift at the last bit across BLAS/libm paths while leaving
    quintile membership and every scored gate number unchanged. Hash the gate inputs that
    actually drive the portfolio: `(week_end, symbol, quintile, forward_return)`.
    """
    required = {"week_end", "symbol", "ctrend", "quintile", "forward_return"}
    missing = required - set(forecasts.columns)
    if missing:
        raise CtrendError(f"forecast_frame_sha256 missing columns {sorted(missing)}")
    h = hashlib.sha256()
    ordered = forecasts.select("week_end", "symbol", "quintile", "forward_return").sort(
        ["week_end", "symbol"]
    )
    for row in ordered.iter_rows(named=True):
        fwd = row["forward_return"]
        parts = (
            str(row["week_end"]),
            str(row["symbol"]),
            str(int(row["quintile"])),
            "" if fwd is None else _format_float(float(fwd)),
        )
        h.update(("|".join(parts) + "\n").encode("utf-8"))
    return h.hexdigest()


def _cost_fraction(model: VenueCostModel, execution: ExecutionStyle) -> float:
    return model.leg_cost_fraction(leg="spot", taker=execution == "taker")


def _selected_weights(
    rows: list[dict[str, object]],
    portfolio: PortfolioKind,
    n_quintiles: int,
    *,
    missing_policy: MissingReturnPolicy,
) -> tuple[dict[str, float], int, int, bool]:
    top_q = n_quintiles - 1
    top = [r for r in rows if _row_quintile(r) == top_q]
    bottom = [r for r in rows if _row_quintile(r) == 0]

    if missing_policy == "drop_and_renormalize":
        top = [r for r in top if r["forward_return"] is not None]
        bottom = [r for r in bottom if r["forward_return"] is not None]

    if portfolio == "long_only_top":
        if not top:
            return {}, 0, 0, True
        return {str(r["symbol"]): 1.0 / len(top) for r in top}, len(top), 0, False

    if not top or not bottom:
        return {}, len(top), len(bottom), True
    weights = {str(r["symbol"]): 0.5 / len(top) for r in top}
    weights.update({str(r["symbol"]): -0.5 / len(bottom) for r in bottom})
    return weights, len(top), len(bottom), False


def _row_quintile(row: dict[str, object]) -> int:
    value = row["quintile"]
    if isinstance(value, int):
        return value
    raise CtrendError(f"expected an integer quintile, got {value!r}")


def _build_portfolio_series(
    forecasts: pl.DataFrame,
    *,
    portfolio: PortfolioKind,
    execution: ExecutionStyle,
    missing_policy: MissingReturnPolicy,
    cost_model: VenueCostModel,
    n_quintiles: int,
    oos_start: date,
) -> _BacktestSeries:
    required = {"week_end", "symbol", "quintile", "forward_return"}
    missing = required - set(forecasts.columns)
    if missing:
        raise CtrendError(f"_build_portfolio_series missing columns {sorted(missing)}")
    oos = forecasts.filter(pl.col("week_end") >= oos_start).sort(["week_end", "symbol"])
    if oos.height == 0:
        raise CtrendError(f"no CTREND forecasts on or after OOS start {oos_start}")

    points: list[_WeeklyPoint] = []
    prev: dict[str, float] = {}
    dropped_weeks = 0
    missing_returns = 0
    one_side_cost = _cost_fraction(cost_model, execution)

    for week in oos["week_end"].unique().sort().to_list():
        sub = oos.filter(pl.col("week_end") == week)
        rows = sub.to_dicts()
        weights, n_long, n_short, drop_week = _selected_weights(
            rows, portfolio, n_quintiles, missing_policy=missing_policy
        )
        if drop_week:
            dropped_weeks += 1
            continue

        row_by_symbol = {str(r["symbol"]): r for r in rows}
        selected = [row_by_symbol[s] for s in weights]
        if all(r["forward_return"] is None for r in selected):
            dropped_weeks += 1
            continue

        gross = 0.0
        week_missing: set[str] = set()
        for symbol, weight in weights.items():
            value = row_by_symbol[symbol]["forward_return"]
            if value is None:
                if missing_policy == "delisting_loss":
                    ret = MISSING_RETURN_LOSS
                    week_missing.add(symbol)
                else:  # pragma: no cover - drop policy filters missing rows before weighting
                    continue
            else:
                ret = float(value)
            gross += weight * ret

        turnover = math.fsum(
            abs(weights.get(symbol, 0.0) - prev.get(symbol, 0.0))
            for symbol in set(weights) | set(prev)
        )
        cost = turnover * one_side_cost
        points.append(
            _WeeklyPoint(
                week_end=week,
                gross_return=gross,
                turnover=turnover,
                cost=cost,
                net_return=gross - cost,
                n_long=n_long,
                n_short=n_short,
                n_missing_returns=len(week_missing),
            )
        )
        missing_returns += len(week_missing)
        if week_missing:
            prev = {s: w for s, w in weights.items() if s not in week_missing}
        else:
            prev = weights

    if len(points) < 2:
        raise CtrendError(
            f"portfolio {portfolio}/{execution}/{missing_policy} produced fewer than 2 "
            f"OOS weeks ({len(points)})"
        )
    return _BacktestSeries(
        portfolio=portfolio,
        execution=execution,
        missing_policy=missing_policy,
        points=tuple(points),
        missing_returns=missing_returns,
        dropped_weeks=dropped_weeks,
    )


def _trial_record(series: _BacktestSeries) -> TrialRecord:
    moments = return_moments(series.net_returns)
    effective_t, pw_block = effective_sample_size(series.net_returns)
    return TrialRecord(
        portfolio=series.portfolio,
        execution=series.execution,
        missing_policy=series.missing_policy,
        sr_hat=moments.sr_hat,
        gamma_3=moments.gamma_3,
        gamma_4=moments.gamma_4,
        raw_t=moments.t_obs,
        effective_t=effective_t,
        pw_block_length=pw_block,
        mean_gross=statistics.fmean(series.gross_returns),
        mean_net=moments.mean,
        mean_turnover=statistics.fmean(series.turnovers),
        total_cost=math.fsum(series.costs),
        missing_returns=series.missing_returns,
        dropped_weeks=series.dropped_weeks,
        series_sha256=_series_hash(series.points),
    )


def _trial_n_and_variance(
    records: Sequence[TrialRecord], dataset_fingerprint: str
) -> tuple[int, float]:
    """Record the realized trial family through TrialRegistry and return its DSR inputs."""
    with tempfile.TemporaryDirectory(prefix="riskpremia-ctrend-trials-") as td:
        registry = TrialRegistry(Path(td) / "trials.db", naive_effective_n=TRIAL_NAIVE_EFFECTIVE_N)
        for record in records:
            registry.record(
                dataset_fingerprint=dataset_fingerprint,
                strategy_family=_STRATEGY_FAMILY,
                sr_hat=record.sr_hat,
                t_observations=record.effective_t,
                gamma_3=record.gamma_3,
                gamma_4=record.gamma_4,
                metadata={
                    "portfolio": record.portfolio,
                    "execution": record.execution,
                    "missing_policy": record.missing_policy,
                    "raw_t": record.raw_t,
                    "effective_t": record.effective_t,
                    "pw_block_length": record.pw_block_length,
                    "series_sha256": record.series_sha256,
                },
            )
        return registry.effective_n_and_sr_variance(dataset_fingerprint, _STRATEGY_FAMILY)


def _label_horizons(points: Sequence[_WeeklyPoint]) -> pl.Series:
    """One-week label horizon for the CPCV purge contract."""
    return pl.Series(
        "label_horizon", [p.week_end + timedelta(days=7) for p in points], dtype=pl.Date
    )


def _cpcv_summary(
    series: _BacktestSeries,
    *,
    v_sr: float,
    n_effective: int,
    n_groups: int = 6,
    k_test: int = 2,
) -> CpcvSummary:
    obs = pl.DataFrame({"dt": [p.week_end for p in series.points]}, schema={"dt": pl.Date})
    splitter = make_purged_cpcv(obs.height, 1, n_groups=n_groups, k_test=k_test)
    dsrs: list[float] = []
    min_train = math.inf
    min_test = math.inf
    for split in splitter.split(obs, _label_horizons(series.points)):
        test_returns = [series.points[i].net_return for i in split.test_indices]
        moments = return_moments(test_returns)
        effective_t, _ = effective_sample_size(test_returns)
        dsrs.append(dsr(moments.sr_hat, effective_t, moments.gamma_3, moments.gamma_4, v_sr,
                        n_effective))
        min_train = min(min_train, len(split.train_indices))
        min_test = min(min_test, len(split.test_indices))
    if not dsrs:
        raise CtrendError("CPCV produced no splits")
    return CpcvSummary(
        n_groups=splitter.n_groups,
        k_test=k_test,
        horizon_events=1,
        n_splits=len(dsrs),
        expected_path_count=splitter.expected_path_count(),
        min_train_size=int(min_train),
        min_test_size=int(min_test),
        split_dsrs=tuple(dsrs),
    )


def _weekly_series(series: _BacktestSeries) -> WeeklySeries:
    return WeeklySeries(
        week_end=tuple(p.week_end.isoformat() for p in series.points),
        gross_return=tuple(p.gross_return for p in series.points),
        turnover=tuple(p.turnover for p in series.points),
        cost=tuple(p.cost for p in series.points),
        net_return=tuple(p.net_return for p in series.points),
        n_long=tuple(p.n_long for p in series.points),
        n_short=tuple(p.n_short for p in series.points),
        n_missing_returns=tuple(p.n_missing_returns for p in series.points),
    )


def _portfolio_score(
    series: _BacktestSeries,
    record: TrialRecord,
    *,
    v_sr: float,
    n_effective: int,
) -> PortfolioScore:
    moments = return_moments(series.net_returns)
    cpcv = _cpcv_summary(series, v_sr=v_sr, n_effective=n_effective)
    full = dsr(moments.sr_hat, record.effective_t, moments.gamma_3, moments.gamma_4, v_sr,
               n_effective)
    cpcv_min = min(cpcv.split_dsrs)
    cpcv_median = statistics.median(cpcv.split_dsrs)
    cpcv_max = max(cpcv.split_dsrs)
    return PortfolioScore(
        portfolio=series.portfolio,
        execution=series.execution,
        missing_policy=series.missing_policy,
        raw_t=moments.t_obs,
        effective_t=record.effective_t,
        pw_block_length=record.pw_block_length,
        sr_hat=moments.sr_hat,
        gamma_3=moments.gamma_3,
        gamma_4=moments.gamma_4,
        mean_gross=record.mean_gross,
        mean_net=record.mean_net,
        mean_turnover=record.mean_turnover,
        total_cost=record.total_cost,
        missing_returns=record.missing_returns,
        dropped_weeks=record.dropped_weeks,
        n_effective=n_effective,
        v_sr=v_sr,
        full_oos_dsr=full,
        cpcv_min_dsr=cpcv_min,
        cpcv_median_dsr=cpcv_median,
        cpcv_max_dsr=cpcv_max,
        passes=cpcv_min >= VIABILITY_BAR,
        series_sha256=record.series_sha256,
        cpcv=cpcv,
        series=_weekly_series(series),
    )


def _verdict(retail: PortfolioScore, academic: PortfolioScore) -> GateVerdict:
    retail_non_viable = not retail.passes
    academic_non_viable = not academic.passes
    if retail_non_viable:
        retail_reason = (
            f"retail long-only top quintile CPCV-min DSR {retail.cpcv_min_dsr:.3f} is "
            f"below the {VIABILITY_BAR:.2f} bar"
        )
    else:
        retail_reason = (
            "retail long-only clears the bar; this would require a pass-review before belief "
            "because venue listing and measured alt spreads are not yet modeled"
        )
    if academic_non_viable:
        academic_reason = (
            f"academic long-short CPCV-min DSR {academic.cpcv_min_dsr:.3f} is below the "
            f"{VIABILITY_BAR:.2f} bar"
        )
    else:
        academic_reason = (
            "academic long-short clears the bar, but it does not rescue retail deployment "
            "without borrow, listing, and short-cost modeling"
        )
    headline = (
        "NON-VIABLE retail long-only honest null"
        if retail_non_viable
        else "NOT KILLED on the retail long-only gate, cross-check before belief"
    )
    return GateVerdict(
        retail_non_viable=retail_non_viable,
        academic_non_viable=academic_non_viable,
        retail_reason=retail_reason,
        academic_reason=academic_reason,
        headline=headline,
    )


def build_gate_artifact(
    forecasts: pl.DataFrame,
    *,
    panel_sha256: str,
    n_panel_rows: int,
    panel_relpath: str,
    knobs: GateKnobs,
    cost_model: VenueCostModel | None = None,
) -> GateArtifact:
    """Build the CTREND PR3 gate artifact from a recomputed forecast frame."""
    chosen_model = cost_model if cost_model is not None else TRADEABLE_VENUES[0]
    oos_start = date.fromisoformat(knobs.oos_start)
    variants: list[_BacktestSeries] = []
    executions: tuple[ExecutionStyle, ...] = ("taker", "maker")
    missing_policies: tuple[MissingReturnPolicy, ...] = (
        "delisting_loss",
        "drop_and_renormalize",
    )
    for portfolio in (PRIMARY_PORTFOLIO, ACADEMIC_PORTFOLIO):
        for execution in executions:
            for missing_policy in missing_policies:
                variants.append(
                    _build_portfolio_series(
                        forecasts,
                        portfolio=portfolio,
                        execution=execution,
                        missing_policy=missing_policy,
                        cost_model=chosen_model,
                        n_quintiles=knobs.n_quintiles,
                        oos_start=oos_start,
                    )
                )

    records = tuple(_trial_record(series) for series in variants)
    forecast_hash = forecast_frame_sha256(forecasts)
    n_effective, v_sr = _trial_n_and_variance(records, forecast_hash)
    by_key = {
        (series.portfolio, series.execution, series.missing_policy): (series, record)
        for series, record in zip(variants, records, strict=True)
    }
    retail_series, retail_record = by_key[(PRIMARY_PORTFOLIO, PRIMARY_EXECUTION,
                                           PRIMARY_MISSING_POLICY)]
    academic_series, academic_record = by_key[(ACADEMIC_PORTFOLIO, PRIMARY_EXECUTION,
                                               PRIMARY_MISSING_POLICY)]
    retail = _portfolio_score(retail_series, retail_record, v_sr=v_sr, n_effective=n_effective)
    academic = _portfolio_score(academic_series, academic_record, v_sr=v_sr,
                                n_effective=n_effective)
    weeks = retail.series.week_end
    if not weeks:
        raise CtrendError("retail series is empty")
    return GateArtifact(
        schema_version=SCHEMA_VERSION,
        study=_STUDY,
        window_start=weeks[0],
        window_end=weeks[-1],
        viability_bar=VIABILITY_BAR,
        knobs=knobs,
        fingerprint=GateFingerprint(
            panel_sha256=panel_sha256,
            n_panel_rows=n_panel_rows,
            panel_relpath=panel_relpath,
            n_forecast_rows=forecasts.height,
            forecast_sha256=forecast_hash,
        ),
        cost_venues=cost_venues(),
        trial_records=records,
        retail_long_only=retail,
        academic_long_short=academic,
        verdict=_verdict(retail, academic),
        caveats=CAVEATS,
    )


def gate_artifact_to_json(artifact: GateArtifact) -> str:
    """Deterministic JSON (sorted keys, round-trip-exact floats, trailing newline)."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_gate_artifact(artifact: GateArtifact, path: Path) -> None:
    """Write the gate artifact JSON with LF newlines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(gate_artifact_to_json(artifact), encoding="utf-8", newline="\n")


def _req(d: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        raise CtrendError(f"gate artifact {ctx} missing required key {key!r}")
    return d[key]


def _knobs(d: dict[str, Any]) -> GateKnobs:
    return GateKnobs(
        top_n=int(_req(d, "top_n", "knobs")),
        lookback_weeks=int(_req(d, "lookback_weeks", "knobs")),
        min_history_weeks=int(_req(d, "min_history_weeks", "knobs")),
        fit_window=int(_req(d, "fit_window", "knobs")),
        n_quintiles=int(_req(d, "n_quintiles", "knobs")),
        oos_start=str(_req(d, "oos_start", "knobs")),
        missing_return_loss=float(_req(d, "missing_return_loss", "knobs")),
        trial_naive_effective_n=int(_req(d, "trial_naive_effective_n", "knobs")),
    )


def _cost_venue(d: dict[str, Any]) -> CostVenue:
    return CostVenue(
        name=str(_req(d, "name", "cost_venue")),
        tradeable=bool(_req(d, "tradeable", "cost_venue")),
        spot_taker_cost=float(_req(d, "spot_taker_cost", "cost_venue")),
        spot_maker_cost=float(_req(d, "spot_maker_cost", "cost_venue")),
        spread_basis=str(_req(d, "spread_basis", "cost_venue")),
        provisional=bool(_req(d, "provisional", "cost_venue")),
        source=str(_req(d, "source", "cost_venue")),
    )


def _trial_record_from_dict(d: dict[str, Any]) -> TrialRecord:
    return TrialRecord(
        portfolio=str(_req(d, "portfolio", "trial_record")),  # type: ignore[arg-type]
        execution=str(_req(d, "execution", "trial_record")),  # type: ignore[arg-type]
        missing_policy=str(_req(d, "missing_policy", "trial_record")),  # type: ignore[arg-type]
        sr_hat=float(_req(d, "sr_hat", "trial_record")),
        gamma_3=float(_req(d, "gamma_3", "trial_record")),
        gamma_4=float(_req(d, "gamma_4", "trial_record")),
        raw_t=int(_req(d, "raw_t", "trial_record")),
        effective_t=int(_req(d, "effective_t", "trial_record")),
        pw_block_length=float(_req(d, "pw_block_length", "trial_record")),
        mean_gross=float(_req(d, "mean_gross", "trial_record")),
        mean_net=float(_req(d, "mean_net", "trial_record")),
        mean_turnover=float(_req(d, "mean_turnover", "trial_record")),
        total_cost=float(_req(d, "total_cost", "trial_record")),
        missing_returns=int(_req(d, "missing_returns", "trial_record")),
        dropped_weeks=int(_req(d, "dropped_weeks", "trial_record")),
        series_sha256=str(_req(d, "series_sha256", "trial_record")),
    )


def _weekly_series_from_dict(d: dict[str, Any]) -> WeeklySeries:
    return WeeklySeries(
        week_end=tuple(str(x) for x in _req(d, "week_end", "series")),
        gross_return=tuple(float(x) for x in _req(d, "gross_return", "series")),
        turnover=tuple(float(x) for x in _req(d, "turnover", "series")),
        cost=tuple(float(x) for x in _req(d, "cost", "series")),
        net_return=tuple(float(x) for x in _req(d, "net_return", "series")),
        n_long=tuple(int(x) for x in _req(d, "n_long", "series")),
        n_short=tuple(int(x) for x in _req(d, "n_short", "series")),
        n_missing_returns=tuple(int(x) for x in _req(d, "n_missing_returns", "series")),
    )


def _cpcv_from_dict(d: dict[str, Any]) -> CpcvSummary:
    return CpcvSummary(
        n_groups=int(_req(d, "n_groups", "cpcv")),
        k_test=int(_req(d, "k_test", "cpcv")),
        horizon_events=int(_req(d, "horizon_events", "cpcv")),
        n_splits=int(_req(d, "n_splits", "cpcv")),
        expected_path_count=int(_req(d, "expected_path_count", "cpcv")),
        min_train_size=int(_req(d, "min_train_size", "cpcv")),
        min_test_size=int(_req(d, "min_test_size", "cpcv")),
        split_dsrs=tuple(float(x) for x in _req(d, "split_dsrs", "cpcv")),
    )


def _portfolio_score_from_dict(d: dict[str, Any]) -> PortfolioScore:
    return PortfolioScore(
        portfolio=str(_req(d, "portfolio", "score")),  # type: ignore[arg-type]
        execution=str(_req(d, "execution", "score")),  # type: ignore[arg-type]
        missing_policy=str(_req(d, "missing_policy", "score")),  # type: ignore[arg-type]
        raw_t=int(_req(d, "raw_t", "score")),
        effective_t=int(_req(d, "effective_t", "score")),
        pw_block_length=float(_req(d, "pw_block_length", "score")),
        sr_hat=float(_req(d, "sr_hat", "score")),
        gamma_3=float(_req(d, "gamma_3", "score")),
        gamma_4=float(_req(d, "gamma_4", "score")),
        mean_gross=float(_req(d, "mean_gross", "score")),
        mean_net=float(_req(d, "mean_net", "score")),
        mean_turnover=float(_req(d, "mean_turnover", "score")),
        total_cost=float(_req(d, "total_cost", "score")),
        missing_returns=int(_req(d, "missing_returns", "score")),
        dropped_weeks=int(_req(d, "dropped_weeks", "score")),
        n_effective=int(_req(d, "n_effective", "score")),
        v_sr=float(_req(d, "v_sr", "score")),
        full_oos_dsr=float(_req(d, "full_oos_dsr", "score")),
        cpcv_min_dsr=float(_req(d, "cpcv_min_dsr", "score")),
        cpcv_median_dsr=float(_req(d, "cpcv_median_dsr", "score")),
        cpcv_max_dsr=float(_req(d, "cpcv_max_dsr", "score")),
        passes=bool(_req(d, "passes", "score")),
        series_sha256=str(_req(d, "series_sha256", "score")),
        cpcv=_cpcv_from_dict(_req(d, "cpcv", "score")),
        series=_weekly_series_from_dict(_req(d, "series", "score")),
    )


def load_gate_artifact(path: Path) -> GateArtifact:
    """Load and validate a committed CTREND gate artifact JSON."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise CtrendError(f"gate artifact {path.name} is not a JSON object")
    fp = _req(data, "fingerprint", "root")
    verdict = _req(data, "verdict", "root")
    return GateArtifact(
        schema_version=int(_req(data, "schema_version", "root")),
        study=str(_req(data, "study", "root")),
        window_start=str(_req(data, "window_start", "root")),
        window_end=str(_req(data, "window_end", "root")),
        viability_bar=float(_req(data, "viability_bar", "root")),
        knobs=_knobs(_req(data, "knobs", "root")),
        fingerprint=GateFingerprint(
            panel_sha256=str(_req(fp, "panel_sha256", "fingerprint")),
            n_panel_rows=int(_req(fp, "n_panel_rows", "fingerprint")),
            panel_relpath=str(_req(fp, "panel_relpath", "fingerprint")),
            n_forecast_rows=int(_req(fp, "n_forecast_rows", "fingerprint")),
            forecast_sha256=str(_req(fp, "forecast_sha256", "fingerprint")),
        ),
        cost_venues=tuple(_cost_venue(v) for v in _req(data, "cost_venues", "root")),
        trial_records=tuple(
            _trial_record_from_dict(t) for t in _req(data, "trial_records", "root")
        ),
        retail_long_only=_portfolio_score_from_dict(_req(data, "retail_long_only", "root")),
        academic_long_short=_portfolio_score_from_dict(
            _req(data, "academic_long_short", "root")
        ),
        verdict=GateVerdict(
            retail_non_viable=bool(_req(verdict, "retail_non_viable", "verdict")),
            academic_non_viable=bool(_req(verdict, "academic_non_viable", "verdict")),
            retail_reason=str(_req(verdict, "retail_reason", "verdict")),
            academic_reason=str(_req(verdict, "academic_reason", "verdict")),
            headline=str(_req(verdict, "headline", "verdict")),
        ),
        caveats=tuple(str(c) for c in _req(data, "caveats", "root")),
    )
