"""Quality (profitability) tilt gate (Study 10, ADR 0012, with the design-review amendment).

Hold the high-operating-profitability value-weighted tercile and score it as the difference over
buy-and-hold the value-weight market, both deployed as ETFs so the cost is the differential expense
(quality-ETF expense minus market-ETF expense), with no separate reconstitution turnover (a static
single-portfolio hold; the French series already embeds reconstitution). The headline kill is the
full-sample conditional PSR(0) of the difference, but a clean make-money pass additionally requires
the Deflated Sharpe to clear the bar at a literature-scale trial count AND a positive Fama-French
five-factor alpha (with robust-minus-weak the dominant loading), so a beta, size, or value tilt is
not deployed mislabeled as profitability alpha. The CPCV worst fold, four recency slices, the
deflation ladder, the cost sensitivity, and the Study-6 correlation are reported.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import attrs
import numpy as np
import polars as pl

from riskpremia.analytics.sharpe import dsr, psr
from riskpremia.execution.scoring import effective_sample_size, make_purged_cpcv, return_moments
from riskpremia.quality.errors import QualityError
from riskpremia.quality.fixtures import PORTFOLIO_COLS

SCHEMA_VERSION = 1
_STUDY = "Quality (profitability) tilt (Study 10, ADR 0012)"
TRADING_DAYS_PER_YEAR = 252.0
TRADING_DAYS_PER_MONTH = 21
EXPENSE_HI_ANNUAL = 0.0015  # a quality-ETF expense ratio (QUAL-style)
EXPENSE_MKT_ANNUAL = 0.0004  # a broad-market-ETF expense ratio
DIFFERENTIAL_SENSITIVITIES: tuple[float, ...] = (0.0005, 0.0010, 0.0020)
VIABILITY_BAR = 0.95
MIN_TRIAL_COUNT_FOR_PASS = 16
TRIAL_LADDER: tuple[int, ...] = (8, 16, 32, 64, 128)
CPCV_N_GROUPS = 6
CPCV_K_TEST = 2
RECENCY_SLICES: tuple[tuple[str, str], ...] = (
    ("from_2000", "2000-01-01"), ("from_2008", "2008-01-01"),
    ("from_2010", "2010-01-01"), ("from_2022", "2022-01-01"),
)
_FF_FACTORS: tuple[str, ...] = ("mkt_rf", "smb", "hml", "rmw", "cma")

CAVEATS: tuple[str, ...] = (
    "The kill is the high-profitability-MINUS-market difference (the deployable bundle a quality "
    "ETF gives you, which cannot strip its own factor exposures), net of the DIFFERENTIAL expense "
    "(a quality ETF costs more to hold than a market ETF); the gross difference is context only.",
    "A clean make-money pass requires the difference PSR to clear the bar AND the Deflated Sharpe "
    "to clear at >= 16 trials (literature-scale for the mined quality factor) AND a positive "
    "Fama-French five-factor alpha with robust-minus-weak the dominant loading; anything less is "
    "the operating-profitability premium surviving only undeflated, not a deployable result.",
    "The Kenneth French academic operating-profitability value-weighted tercile is NOT a quality "
    "ETF (QUAL and peers use a sector-neutral composite of return-on-equity, leverage, and "
    "earnings stability over roughly 125 large caps); a tercile pass is the academic premium net "
    "of an assumed differential expense, not a QUAL guarantee.",
    "The held portfolio is static (no build-side rebalance), and the French daily series already "
    "embeds the annual end-June reconstitution, so there is no separate turnover charge.",
)


@attrs.frozen(slots=True)
class QualityKnobs:
    """The frozen construction knobs."""

    expense_hi_annual: float = EXPENSE_HI_ANNUAL
    expense_mkt_annual: float = EXPENSE_MKT_ANNUAL
    trading_days_per_year: float = TRADING_DAYS_PER_YEAR
    viability_bar: float = VIABILITY_BAR
    min_trial_count: int = MIN_TRIAL_COUNT_FOR_PASS
    portfolio: str = "hi30_vw"  # the headline high-profitability leg


@attrs.frozen(slots=True)
class CostModel:
    """The explicit cost assumptions (the deployable differential expense)."""

    expense_hi_annual: float
    expense_mkt_annual: float
    differential_annual: float
    basis: str


@attrs.frozen(slots=True)
class InputFingerprint:
    """Content pins for the committed panel and its provenance."""

    panel_sha256: str
    panel_relpath: str
    n_panel_rows: int
    provenance_sha256: str
    provenance_relpath: str


@attrs.frozen(slots=True)
class DifferenceScore:
    """The high-profitability-minus-market difference statistics (the primary kill)."""

    raw_t: int
    effective_t: int
    pw_block_length: float
    sr_hat: float
    ann_sharpe: float
    gamma_3: float
    gamma_4: float
    mean_daily: float
    full_psr_zero: float
    monthly_psr_zero: float
    n_monthly_obs: int
    gross_full_psr_zero: float  # at zero differential expense (context, not the kill)


@attrs.frozen(slots=True)
class FFAttribution:
    """The Fama-French five-factor attribution of the high-profitability excess return."""

    alpha_daily: float
    alpha_ann: float
    alpha_t_stat: float  # Newey-West (HAC) t-statistic
    beta_mkt: float
    beta_smb: float
    beta_hml: float
    beta_rmw: float
    beta_cma: float
    rmw_is_dominant: bool  # robust-minus-weak is the largest positive loading among tilt factors


@attrs.frozen(slots=True)
class Decomposition:
    """The difference decomposed: the gross difference, the five-factor alpha, and the RMW part."""

    raw_difference_ann: float
    ff5_alpha_ann: float
    rmw_component_ann: float


@attrs.frozen(slots=True)
class ContextStat:
    """Equity-premium and standalone context (not the kill)."""

    hi_net_of_bill_psr_zero: float
    hi_ann_sharpe: float
    market_ann_sharpe: float


@attrs.frozen(slots=True)
class CpcvStress:
    """Purged CPCV worst-fold stress on the difference series."""

    n_groups: int
    k_test: int
    n_splits: int
    min_test_size: int
    fold_psr_zero: tuple[float, ...]
    fold_min: float
    fold_median: float


@attrs.frozen(slots=True)
class RecencySlice:
    """A conditional PSR(0) of the difference series on a date-restricted tail."""

    name: str
    start: str
    raw_t: int
    effective_t: int
    psr_zero: float


@attrs.frozen(slots=True)
class DeflationLadder:
    """Deflated Sharpe of the difference at literature-scale trial counts (a hard gate input)."""

    v_sr: float
    variant_labels: tuple[str, ...]
    variant_sr_hat: tuple[float, ...]
    trials: tuple[int, ...]
    dsr_by_trials: tuple[float, ...]
    dsr_at_min_trials: float
    passes_at_min_trials: bool


@attrs.frozen(slots=True)
class CostSensitivity:
    """The difference PSR(0) at a differential expense."""

    differential_annual: float
    full_psr_zero: float


@attrs.frozen(slots=True)
class Redundancy:
    """Distinctness from the Study 6 cross-asset trend (the 1990-onward overlap)."""

    n_aligned: int
    difference_vs_xtrend_corr: float


@attrs.frozen(slots=True)
class QualityScore:
    """The full scored result and the kill checks."""

    difference: DifferenceScore
    attribution: FFAttribution
    decomposition: Decomposition
    context: ContextStat
    cpcv: CpcvStress
    recency: tuple[RecencySlice, ...]
    deflation: DeflationLadder
    cost_sensitivity: tuple[CostSensitivity, ...]
    redundancy: Redundancy
    passes_psr: bool
    passes_deflation: bool
    ff5_alpha_positive: bool
    regime_dependent: bool
    make_money_pass: bool


@attrs.frozen(slots=True)
class QualityVerdict:
    """The Study 10 deployment verdict."""

    non_viable: bool
    headline: str
    reason: str


@attrs.frozen(slots=True)
class QualityGateArtifact:
    """The committed Study 10 gate artifact."""

    schema_version: int
    study: str
    data_start: str
    data_end: str
    n_scored_days: int
    knobs: QualityKnobs
    cost_model: CostModel
    fingerprint: InputFingerprint
    score: QualityScore
    caveats: tuple[str, ...]
    verdict: QualityVerdict


def _arrays(panel: pl.DataFrame) -> dict[str, list[float]]:
    required = {"date", *PORTFOLIO_COLS, "mkt_rf", "smb", "hml", "rmw", "cma", "rf"}
    missing = required - set(panel.columns)
    if missing:
        raise QualityError(f"panel missing required columns {sorted(missing)}")
    frame = panel.sort("date")
    if frame.height < 252 * 5:
        raise QualityError("panel too short for a quality-tilt study")
    out: dict[str, list[float]] = {}
    for c in (*PORTFOLIO_COLS, "mkt_rf", "smb", "hml", "rmw", "cma", "rf"):
        out[c] = [float(x) for x in frame[c].to_list()]
    return out


def _dates(panel: pl.DataFrame) -> list[date]:
    return [d for d in panel.sort("date")["date"].to_list() if isinstance(d, date)]


def _difference(
    cols: dict[str, list[float]], portfolio: str, differential_daily: float
) -> list[float]:
    """The high-profitability-minus-market difference net of the differential expense."""
    hi = cols[portfolio]
    mkt_rf = cols["mkt_rf"]
    rf = cols["rf"]
    return [hi[i] - (mkt_rf[i] + rf[i]) - differential_daily for i in range(len(hi))]


def _ann_sharpe(returns: Sequence[float], trading_days: float) -> float:
    return return_moments(returns).sr_hat * math.sqrt(trading_days)


def _psr_zero(returns: Sequence[float]) -> float:
    m = return_moments(returns)
    eff_t, _ = effective_sample_size(returns)
    return psr(m.sr_hat, 0.0, eff_t, m.gamma_3, m.gamma_4)


def _newey_west_lag(n: int) -> int:
    return max(1, int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))


def _ff5_attribution(
    cols: dict[str, list[float]], portfolio: str, trading_days: float
) -> FFAttribution:
    """OLS of the high-profitability excess on the five factors, with a Newey-West alpha t-stat."""
    hi = cols[portfolio]
    rf = cols["rf"]
    y = np.array([hi[i] - rf[i] for i in range(len(hi))], dtype=float)
    factor_mat = np.column_stack([np.array(cols[f], dtype=float) for f in _FF_FACTORS])
    n = y.shape[0]
    x = np.column_stack([np.ones(n), factor_mat])
    xtx_inv = np.linalg.inv(x.T @ x)
    beta = xtx_inv @ (x.T @ y)
    resid = y - x @ beta
    scores = x * resid[:, None]
    lag = _newey_west_lag(n)
    meat = scores.T @ scores
    for ell in range(1, lag + 1):
        w = 1.0 - ell / (lag + 1.0)
        g = scores[ell:].T @ scores[:-ell]
        meat = meat + w * (g + g.T)
    cov = xtx_inv @ meat @ xtx_inv
    alpha_se = math.sqrt(max(float(cov[0, 0]), 0.0))
    alpha = float(beta[0])
    loadings = {f: float(beta[i + 1]) for i, f in enumerate(_FF_FACTORS)}
    positive_tilts = {f: loadings[f] for f in ("smb", "hml", "rmw", "cma") if loadings[f] > 0.0}
    dominant = max(positive_tilts, key=lambda k: positive_tilts[k]) if positive_tilts else None
    rmw_dominant = dominant == "rmw"
    return FFAttribution(
        alpha_daily=alpha, alpha_ann=alpha * trading_days,
        alpha_t_stat=(alpha / alpha_se if alpha_se > 0.0 else 0.0),
        beta_mkt=loadings["mkt_rf"], beta_smb=loadings["smb"], beta_hml=loadings["hml"],
        beta_rmw=loadings["rmw"], beta_cma=loadings["cma"], rmw_is_dominant=rmw_dominant,
    )


def _label_horizons(scored_dates: Sequence[date]) -> pl.Series:
    n = len(scored_dates)
    horizons = [scored_dates[min(i + TRADING_DAYS_PER_MONTH, n - 1)] for i in range(n)]
    return pl.Series("label_horizon", horizons, dtype=pl.Date)


def _cpcv_stress(dates: Sequence[date], diff: Sequence[float]) -> CpcvStress:
    obs = pl.DataFrame({"dt": list(dates)}, schema={"dt": pl.Date})
    splitter = make_purged_cpcv(
        obs.height, TRADING_DAYS_PER_MONTH, n_groups=CPCV_N_GROUPS, k_test=CPCV_K_TEST
    )
    labels = _label_horizons(dates)
    fold_scores: list[float] = []
    min_test = math.inf
    for split in splitter.split(obs, labels):
        fold_scores.append(_psr_zero([diff[i] for i in split.test_indices]))
        min_test = min(min_test, len(split.test_indices))
    return CpcvStress(
        n_groups=splitter.n_groups, k_test=CPCV_K_TEST, n_splits=len(fold_scores),
        min_test_size=int(min_test), fold_psr_zero=tuple(fold_scores),
        fold_min=min(fold_scores), fold_median=statistics.median(fold_scores),
    )


def _recency(dates: Sequence[date], diff: Sequence[float]) -> tuple[RecencySlice, ...]:
    out: list[RecencySlice] = []
    for name, start_str in RECENCY_SLICES:
        start = date.fromisoformat(start_str)
        rets = [diff[i] for i, d in enumerate(dates) if d >= start]
        if len(rets) < TRADING_DAYS_PER_MONTH * 6:
            continue
        m = return_moments(rets)
        eff_t, _ = effective_sample_size(rets)
        out.append(RecencySlice(name=name, start=start_str, raw_t=m.t_obs, effective_t=eff_t,
                                psr_zero=psr(m.sr_hat, 0.0, eff_t, m.gamma_3, m.gamma_4)))
    return tuple(out)


def _monthly_difference(
    dates: Sequence[date], hi: Sequence[float], market: Sequence[float]
) -> list[float]:
    """Non-overlapping monthly difference: compounded high-profitability minus market total."""
    out: list[float] = []
    wa = 1.0
    wb = 1.0
    current = (dates[0].year, dates[0].month)
    for i, d in enumerate(dates):
        key = (d.year, d.month)
        if key != current:
            out.append(wa - wb)
            wa = 1.0
            wb = 1.0
            current = key
        wa *= 1.0 + hi[i]
        wb *= 1.0 + market[i]
    out.append(wa - wb)
    return out


def _deflation(cols: dict[str, list[float]], knobs: QualityKnobs, differential_daily: float,
               headline_sr: float, eff_t: int, g3: float, g4: float) -> DeflationLadder:
    labels: list[str] = []
    variant_sr: list[float] = []
    for portfolio in PORTFOLIO_COLS:  # hi30_vw, hi20_vw, hi10_vw, hi30_ew (breadth + weighting)
        diff = _difference(cols, portfolio, differential_daily)
        labels.append(portfolio)
        variant_sr.append(return_moments(diff).sr_hat)
    v_sr = statistics.variance(variant_sr) if len(variant_sr) >= 2 else 0.0
    dsr_values = tuple(dsr(headline_sr, eff_t, g3, g4, v_sr, n) for n in TRIAL_LADDER)
    by_trial = dict(zip(TRIAL_LADDER, dsr_values, strict=True))
    at_min = by_trial.get(knobs.min_trial_count, dsr_values[-1])
    return DeflationLadder(
        v_sr=v_sr, variant_labels=tuple(labels), variant_sr_hat=tuple(variant_sr),
        trials=TRIAL_LADDER, dsr_by_trials=dsr_values, dsr_at_min_trials=at_min,
        passes_at_min_trials=at_min >= knobs.viability_bar,
    )


def _cost_sensitivity(
    cols: dict[str, list[float]], knobs: QualityKnobs
) -> tuple[CostSensitivity, ...]:
    out: list[CostSensitivity] = []
    for diff_annual in DIFFERENTIAL_SENSITIVITIES:
        diff = _difference(cols, knobs.portfolio, diff_annual / knobs.trading_days_per_year)
        out.append(CostSensitivity(differential_annual=diff_annual, full_psr_zero=_psr_zero(diff)))
    return tuple(out)


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        raise QualityError("pearson needs two equal-length series of length >= 2")
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    syy = math.fsum((y - my) ** 2 for y in ys)
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    if sxx <= 0.0 or syy <= 0.0:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def _redundancy(
    xtrend_panel: pl.DataFrame | None, dates: Sequence[date], diff: Sequence[float]
) -> Redundancy:
    if xtrend_panel is None:
        return Redundancy(0, 0.0)
    from riskpremia.xtrend.gate import XTrendKnobs
    from riskpremia.xtrend.gate import _daily_from_panel as _xd
    from riskpremia.xtrend.gate import _simulate as _xsim

    xsim = _xsim(_xd(xtrend_panel, XTrendKnobs()), XTrendKnobs())
    x_excess = dict(zip(xsim.scored_dates, xsim.excess, strict=True))
    idx = {d: i for i, d in enumerate(dates)}
    aligned = [d for d in dates if d in x_excess]
    if len(aligned) < TRADING_DAYS_PER_MONTH * 6:
        return Redundancy(len(aligned), 0.0)
    a = [diff[idx[d]] for d in aligned]
    b = [x_excess[d] for d in aligned]
    return Redundancy(n_aligned=len(aligned), difference_vs_xtrend_corr=_pearson(a, b))


def _score(
    panel: pl.DataFrame, knobs: QualityKnobs, xtrend_panel: pl.DataFrame | None
) -> QualityScore:
    cols = _arrays(panel)
    dates = _dates(panel)
    td = knobs.trading_days_per_year
    differential = (knobs.expense_hi_annual - knobs.expense_mkt_annual) / td
    diff = _difference(cols, knobs.portfolio, differential)
    gross = _difference(cols, knobs.portfolio, 0.0)
    dm = return_moments(diff)
    eff_t, block = effective_sample_size(diff)
    full_psr = psr(dm.sr_hat, 0.0, eff_t, dm.gamma_3, dm.gamma_4)

    exp_hi = knobs.expense_hi_annual / td
    exp_mkt = knobs.expense_mkt_annual / td
    n_days = len(dates)
    hi_net = [cols[knobs.portfolio][i] - exp_hi for i in range(n_days)]
    mkt_net = [cols["mkt_rf"][i] + cols["rf"][i] - exp_mkt for i in range(n_days)]
    monthly = _monthly_difference(dates, hi_net, mkt_net)
    mm = return_moments(monthly)
    meff, _ = effective_sample_size(monthly)
    difference = DifferenceScore(
        raw_t=dm.t_obs, effective_t=eff_t, pw_block_length=block, sr_hat=dm.sr_hat,
        ann_sharpe=dm.sr_hat * math.sqrt(td), gamma_3=dm.gamma_3, gamma_4=dm.gamma_4,
        mean_daily=dm.mean, full_psr_zero=full_psr,
        monthly_psr_zero=psr(mm.sr_hat, 0.0, meff, mm.gamma_3, mm.gamma_4),
        n_monthly_obs=len(monthly), gross_full_psr_zero=_psr_zero(gross),
    )
    attribution = _ff5_attribution(cols, knobs.portfolio, td)
    decomposition = Decomposition(
        raw_difference_ann=statistics.fmean(gross) * td, ff5_alpha_ann=attribution.alpha_ann,
        rmw_component_ann=attribution.beta_rmw * statistics.fmean(cols["rmw"]) * td,
    )
    rf = cols["rf"]
    hi_excess = [cols[knobs.portfolio][i] - exp_hi - rf[i] for i in range(n_days)]
    mkt_excess = [cols["mkt_rf"][i] - exp_mkt for i in range(n_days)]
    context = ContextStat(
        hi_net_of_bill_psr_zero=_psr_zero(hi_excess), hi_ann_sharpe=_ann_sharpe(hi_excess, td),
        market_ann_sharpe=_ann_sharpe(mkt_excess, td),
    )
    cpcv = _cpcv_stress(dates, diff)
    recency = _recency(dates, diff)
    deflation = _deflation(cols, knobs, differential, dm.sr_hat, eff_t, dm.gamma_3, dm.gamma_4)
    cost_sens = _cost_sensitivity(cols, knobs)
    redundancy = _redundancy(xtrend_panel, dates, diff)

    passes_psr = full_psr >= knobs.viability_bar
    passes_deflation = deflation.passes_at_min_trials
    ff5_alpha_positive = attribution.alpha_ann > 0.0 and attribution.rmw_is_dominant
    regime_dependent = passes_psr and (
        cpcv.fold_min < knobs.viability_bar
        or any(s.psr_zero < knobs.viability_bar for s in recency)
        or not passes_deflation
    )
    make_money_pass = (
        passes_psr and passes_deflation and ff5_alpha_positive and not regime_dependent
    )
    return QualityScore(
        difference=difference, attribution=attribution, decomposition=decomposition,
        context=context,
        cpcv=cpcv, recency=recency, deflation=deflation, cost_sensitivity=cost_sens,
        redundancy=redundancy, passes_psr=passes_psr, passes_deflation=passes_deflation,
        ff5_alpha_positive=ff5_alpha_positive, regime_dependent=regime_dependent,
        make_money_pass=make_money_pass,
    )


def _verdict(score: QualityScore) -> QualityVerdict:
    d = score.difference
    if score.make_money_pass:
        return QualityVerdict(
            non_viable=False,
            headline="NOT KILLED; the quality tilt beats the market net of differential cost",
            reason="the difference cleared the deflated bar at >= 16 trials with positive FF alpha",
        )
    if not score.passes_psr:
        return QualityVerdict(
            non_viable=True,
            headline="NON-VIABLE quality tilt; does not beat the market net of differential cost",
            reason=(
                f"difference PSR(0) {d.full_psr_zero:.3f} below {VIABILITY_BAR:.2f} at the "
                f"deployable differential expense (the gross PSR {d.gross_full_psr_zero:.3f} is "
                f"before that cost)"
            ),
        )
    return QualityVerdict(
        non_viable=True,
        headline="NON-VIABLE quality tilt; the profitability premium survives only undeflated",
        reason=(
            f"difference PSR(0) {d.full_psr_zero:.3f} clears undeflated but the Deflated Sharpe at "
            f"{score.deflation.trials[1]} trials is {score.deflation.dsr_at_min_trials:.3f} (the "
            f"mined quality factor), so it is not a deployable make-money result"
        ),
    )


def build_gate_artifact(
    panel: pl.DataFrame,
    *,
    panel_sha256: str,
    panel_relpath: str,
    provenance_sha256: str,
    provenance_relpath: str,
    knobs: QualityKnobs | None = None,
    xtrend_panel: pl.DataFrame | None = None,
) -> QualityGateArtifact:
    """Build the Study 10 quality-tilt gate artifact from the committed panel."""
    k = knobs if knobs is not None else QualityKnobs()
    score = _score(panel, k, xtrend_panel)
    data_dates = sorted(panel["date"].unique().to_list())
    return QualityGateArtifact(
        schema_version=SCHEMA_VERSION, study=_STUDY,
        data_start=data_dates[0].isoformat(), data_end=data_dates[-1].isoformat(),
        n_scored_days=panel.height, knobs=k,
        cost_model=CostModel(
            expense_hi_annual=k.expense_hi_annual, expense_mkt_annual=k.expense_mkt_annual,
            differential_annual=k.expense_hi_annual - k.expense_mkt_annual,
            basis="differential expense (quality ER minus market ER); static hold, no turnover",
        ),
        fingerprint=InputFingerprint(
            panel_sha256=panel_sha256, panel_relpath=panel_relpath, n_panel_rows=panel.height,
            provenance_sha256=provenance_sha256, provenance_relpath=provenance_relpath,
        ),
        score=score, caveats=CAVEATS, verdict=_verdict(score),
    )


def artifact_to_json(artifact: QualityGateArtifact) -> str:
    """Deterministic JSON with sorted keys and strict finite values."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_gate_artifact(artifact: QualityGateArtifact, path: Path) -> None:
    """Write the committed gate artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact_to_json(artifact), encoding="utf-8", newline="\n")


def load_artifact_dict(path: Path) -> dict[str, Any]:
    """Load the committed artifact JSON as a dict (for reproduction comparison)."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise QualityError(f"{path.name}: artifact is not a JSON object")
    return data
