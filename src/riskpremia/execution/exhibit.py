"""The reported kill-gate artifacts (ADR 0003 PR4b).

Pure functions on a simulated batch / observation frame that produce the numbers
the kill gate is read from: the early economic gate (median funding vs the
round-trip cost, per venue and horizon), the headline deflated-Sharpe (PSR(0) on
the per-trade non-overlapping series across all H strided phases, plus the
lumpy-vs-amortised per-interval diagnostic and the Politis-White iid check), the
funding-sign-regime decomposition, and the pre-tax-headline / after-tax-sidebar
split. Each artifact is scoped to its null (amendment B3): the early gate, the
sign regime, and the contamination check read the always-on book; the headline DSR
and the lumpy/amortised diagnostic read the non-overlapping book.

Every number is a fraction of single-leg notional N (the carry P&L convention),
annualized where a rate is reported. The headline DSR stays pre-tax (a personal
level-shift, finding 8); the after-tax sidebar is an illustrative annual aggregate.
"""

from __future__ import annotations

from collections.abc import Sequence

import attrs
import polars as pl

from riskpremia.execution.carry import simulate_batch
from riskpremia.execution.cost import VenueCostModel
from riskpremia.execution.errors import ScoringError
from riskpremia.execution.scoring import (
    IID_BLOCK_LENGTH_CEILING,
    effective_sample_size,
    per_interval_series,
    psr_zero,
    return_moments,
)
from riskpremia.strategy.null import non_overlapping_entries

_HOURS_PER_YEAR = 8_760.0


def _f(value: object) -> float:
    """Narrow a polars scalar aggregate (numeric or None) to float, None -> 0.0."""
    return 0.0 if value is None else float(value)  # type: ignore[arg-type]


@attrs.frozen(slots=True)
class EarlyGate:
    """The early economic gate for one (venue, horizon): does median funding clear cost?

    The break-even reads FUNDING, not gross (amendment A3). `headroom > 0` means the
    median funding collected over the hold exceeds the realized round-trip + financing
    cost (the carry clears its cost passively); `headroom <= 0` is the early kill.
    """

    venue: str
    tradeable: bool
    horizon_events: int
    capital_multiple: float
    n_trades: int
    median_funding: float
    round_trip_cost: float
    median_financing: float
    realized_cost: float
    headroom: float
    funding_annualized: float
    financing_annualized: float


def early_gate(
    always_on_batch: pl.DataFrame, cost_model: VenueCostModel, horizon_events: int
) -> EarlyGate:
    """The early economic gate on the always-on batch (every eligible entry)."""
    if always_on_batch.height == 0:
        raise ScoringError("early_gate requires a non-empty batch")
    median_funding = _f(always_on_batch["funding_collected"].median())
    median_financing = _f(always_on_batch["financing_cost"].median())
    median_hold = _f(always_on_batch["hold_hours"].median())
    round_trip = _f(always_on_batch["round_trip_cost"].max())  # constant per batch
    realized_cost = round_trip + median_financing
    ann = (_HOURS_PER_YEAR / median_hold) if median_hold > 0 else 0.0
    return EarlyGate(
        venue=cost_model.name,
        tradeable=cost_model.tradeable,
        horizon_events=horizon_events,
        capital_multiple=cost_model.capital_multiple,
        n_trades=always_on_batch.height,
        median_funding=median_funding,
        round_trip_cost=round_trip,
        median_financing=median_financing,
        realized_cost=realized_cost,
        headroom=median_funding - realized_cost,
        funding_annualized=median_funding * ann,
        financing_annualized=median_financing * ann,
    )


@attrs.frozen(slots=True)
class HeadlineScore:
    """The deflated-Sharpe kill number for one (venue, horizon).

    `dsr_per_trade_median` is PSR(0) on the per-trade non-overlapping net series at
    the median strided phase (the headline); the [min, max] band is across all H
    phases (no lucky-offset cherry-pick, M3). `dsr_lumpy` / `dsr_amortised` are the
    per-interval diagnostic; `dsr_kill = min(dsr_per_trade_median, dsr_lumpy)` is the
    less-favourable number the kill is read from (amendments B1, B2). `passes` is
    `dsr_kill >= 0.95`. `effective_t` is the block-deflated honest sample size at the
    phase-0 series (`n_trades` deflated by `pw_block_length`); `gamma_3_per_trade` /
    `gamma_4_per_trade` are the realized phase-0 per-trade moments (so the trial
    registry row is faithful to the series the DSR was computed on)."""

    venue: str
    tradeable: bool
    horizon_events: int
    capital_multiple: float
    n_trades: int
    effective_t: int
    sr_hat_per_trade: float
    gamma_3_per_trade: float
    gamma_4_per_trade: float
    dsr_per_trade_median: float
    dsr_per_trade_min: float
    dsr_per_trade_max: float
    dsr_lumpy: float
    dsr_amortised: float
    dsr_kill: float
    pw_block_length: float
    iid_ok: bool
    passes: bool


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else 0.5 * (s[mid - 1] + s[mid])


def headline_score(
    observations: pl.DataFrame,
    always_on_batch: pl.DataFrame,
    *,
    horizon_events: int,
    cost_model: VenueCostModel,
    entry_taker: bool = True,
    exit_taker: bool = True,
) -> HeadlineScore:
    """The headline deflated-Sharpe (PSR(0)) for one (venue, horizon).

    The per-trade non-overlapping net series is scored at every strided phase (the
    batch row at position `entry_index` carries that entry's `net_pretax`); the
    lumpy-vs-amortised per-interval diagnostic is computed at phase 0; the kill reads
    the less favourable of the median-phase per-trade DSR and the lumpy per-interval
    DSR. `always_on_batch` must be the full batch over `range(0, height-H)` so its
    row positions equal the entry indices.

    Raises:
      ScoringError: when no phase yields at least two non-overlapping trades.
    """
    height = always_on_batch.height + horizon_events
    net = always_on_batch["net_pretax"]
    phase_dsr: list[float] = []
    n_trades_phase0 = 0

    for phase in range(horizon_events):
        entries = list(non_overlapping_entries(height, horizon_events, phase=phase))
        if len(entries) < 2:
            continue
        series = [float(v) for v in net.gather(entries).to_list()]
        phase_dsr.append(psr_zero(series))
        if phase == 0:
            n_trades_phase0 = len(entries)
    if not phase_dsr:
        raise ScoringError(
            f"headline_score: no strided phase yields >= 2 non-overlapping trades for "
            f"horizon_events={horizon_events} on {height} rows"
        )

    # The lumpy-vs-amortised per-interval diagnostic (phase 0 non-overlapping).
    phase0 = list(non_overlapping_entries(height, horizon_events, phase=0))
    lumpy = per_interval_series(
        observations, phase0, horizon_events=horizon_events, cost_model=cost_model,
        amortise=False, entry_taker=entry_taker, exit_taker=exit_taker,
    )
    amortised = per_interval_series(
        observations, phase0, horizon_events=horizon_events, cost_model=cost_model,
        amortise=True, entry_taker=entry_taker, exit_taker=exit_taker,
    )
    dsr_lumpy = psr_zero(lumpy)
    dsr_amortised = psr_zero(amortised)

    dsr_per_trade_median = _median(phase_dsr)
    dsr_kill = min(dsr_per_trade_median, dsr_lumpy)
    # The phase-0 series is the canonical non-overlapping series; its block-deflated T
    # and realized moments are what the headline DSR and the registry row stand on.
    phase0_net = [float(v) for v in net.gather(phase0).to_list()]
    effective_t, pw_block = effective_sample_size(phase0_net)
    phase0_moments = return_moments(phase0_net)
    return HeadlineScore(
        venue=cost_model.name,
        tradeable=cost_model.tradeable,
        horizon_events=horizon_events,
        capital_multiple=cost_model.capital_multiple,
        n_trades=n_trades_phase0,
        effective_t=effective_t,
        sr_hat_per_trade=phase0_moments.sr_hat,
        gamma_3_per_trade=phase0_moments.gamma_3,
        gamma_4_per_trade=phase0_moments.gamma_4,
        dsr_per_trade_median=dsr_per_trade_median,
        dsr_per_trade_min=min(phase_dsr),
        dsr_per_trade_max=max(phase_dsr),
        dsr_lumpy=dsr_lumpy,
        dsr_amortised=dsr_amortised,
        dsr_kill=dsr_kill,
        pw_block_length=pw_block,
        iid_ok=bool(pw_block <= IID_BLOCK_LENGTH_CEILING),
        passes=dsr_kill >= 0.95,
    )


@attrs.frozen(slots=True)
class SignRegime:
    """The funding-sign-regime decomposition (amendment B3, finding 11).

    The per-interval funding the short collects is `+funding_rate`; this buckets the
    intervals by funding sign so a paying regime is not averaged into a collecting
    regime. `negative_regime_drawdown` is the worst peak-to-trough of the cumulative
    collected-funding equity (which falls during negative-funding stretches)."""

    n_positive: int
    n_negative: int
    n_zero: int
    mean_collected_positive: float
    mean_collected_negative: float
    negative_fraction: float
    negative_regime_drawdown: float


def funding_sign_regime(observations: pl.DataFrame) -> SignRegime:
    """Decompose the per-interval collected funding by sign (always-on book)."""
    rates = [float(v) for v in observations["funding_rate"].to_list() if v is not None]
    pos = [r for r in rates if r > 0.0]
    neg = [r for r in rates if r < 0.0]
    n_zero = sum(1 for r in rates if r == 0.0)
    # Cumulative collected-funding equity and its worst peak-to-trough drawdown.
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rates:
        equity += r  # the short collects +funding_rate each interval
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    n_total = len(rates)
    return SignRegime(
        n_positive=len(pos),
        n_negative=len(neg),
        n_zero=n_zero,
        mean_collected_positive=(sum(pos) / len(pos)) if pos else 0.0,
        mean_collected_negative=(sum(neg) / len(neg)) if neg else 0.0,
        negative_fraction=(len(neg) / n_total) if n_total else 0.0,
        negative_regime_drawdown=max_dd,
    )


@attrs.frozen(slots=True)
class AfterTax:
    """The after-tax deployment sidebar (illustrative; the headline stays pre-tax).

    Annual aggregate with within-year loss offset at a short-term-ordinary rate.
    Illustrative only: it assumes uniform ordinary treatment of both legs and ignores
    the perp-leg (section 1256) vs spot-leg (property) tax asymmetry, wash-sale
    questions, and cross-year carryforward. Not tax advice (finding 8, design L2)."""

    ordinary_rate: float
    pre_tax_total: float
    after_tax_total: float
    tax_drag: float
    n_years: int


def after_tax_sidebar(always_on_batch: pl.DataFrame, *, ordinary_rate: float) -> AfterTax:
    """Annual-aggregate after-tax net, with within-year loss offset (illustrative)."""
    if not (0.0 <= ordinary_rate < 1.0):
        raise ScoringError(
            f"after_tax_sidebar requires 0 <= ordinary_rate < 1; got {ordinary_rate}"
        )
    by_year = (
        always_on_batch.with_columns(pl.col("entry_dt").dt.year().alias("_year"))
        .group_by("_year")
        .agg(pl.col("net_pretax").sum().alias("_annual_net"))
        .sort("_year")
    )
    pre_tax_total = 0.0
    after_tax_total = 0.0
    for annual_net in (float(v) for v in by_year["_annual_net"].to_list()):
        pre_tax_total += annual_net
        # Within-year offset: a positive annual net is taxed; a loss is not refunded
        # (no cross-year carryforward modeled), so it passes through unchanged.
        after_tax_total += annual_net * (1.0 - ordinary_rate) if annual_net > 0.0 else annual_net
    return AfterTax(
        ordinary_rate=ordinary_rate,
        pre_tax_total=pre_tax_total,
        after_tax_total=after_tax_total,
        tax_drag=pre_tax_total - after_tax_total,
        n_years=by_year.height,
    )


@attrs.frozen(slots=True)
class SurfaceCell:
    """One (venue, horizon, capital_multiple) cell of the cost-sensitivity surface."""

    early: EarlyGate
    score: HeadlineScore


def gate_surface(
    observations: pl.DataFrame,
    *,
    venues: Sequence[VenueCostModel],
    horizons: Sequence[int],
    capital_multiples: Sequence[float],
    entry_taker: bool = True,
    exit_taker: bool = True,
) -> list[SurfaceCell]:
    """The full venue x horizon x capital-multiple cost-sensitivity surface.

    For each combination it simulates the always-on batch once and derives the early
    gate and the headline deflated-Sharpe. A (venue, horizon) whose frame is too
    short for the horizon is skipped. The result is a deterministic, ordered list a
    caller prints, records to the trial registry, or reads the verdict from."""
    cells: list[SurfaceCell] = []
    for capital_multiple in capital_multiples:
        for venue in venues:
            model = attrs.evolve(venue, capital_multiple=capital_multiple)
            for horizon in horizons:
                # Need at least 2 non-overlapping trades at phase 0 (height > 2H), or
                # headline_score would raise; skip the cell rather than crash the surface.
                if observations.height <= 2 * horizon:
                    continue
                batch = simulate_batch(
                    observations,
                    horizon_events=horizon,
                    cost_model=model,
                    entry_taker=entry_taker,
                    exit_taker=exit_taker,
                )
                cells.append(
                    SurfaceCell(
                        early=early_gate(batch, model, horizon),
                        score=headline_score(
                            observations,
                            batch,
                            horizon_events=horizon,
                            cost_model=model,
                            entry_taker=entry_taker,
                            exit_taker=exit_taker,
                        ),
                    )
                )
    return cells


def is_killed(cells: Sequence[SurfaceCell]) -> bool:
    """True when NO tradeable cell at the conservative 2N capital charge clears the bar.

    The kill reads the tradeable venues at `capital_multiple == 2.0` (amendment B5,
    B6); a single passing tradeable-conservative cell means the carry is not killed
    and that cell must be inspected (the grid then becomes a deflated trial family)."""
    return not any(
        cell.score.passes and cell.score.tradeable and cell.score.capital_multiple == 2.0
        for cell in cells
    )
