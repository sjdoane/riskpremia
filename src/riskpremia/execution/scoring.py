"""The deflated-Sharpe scoring adapter and the return-series builders (ADR 0003 PR4b).

The reuse seam onto the vendored `analytics/sharpe.py` (PSR/DSR) and
`validation/cv.py` (the purged CPCV). Nothing here re-derives a statistic the
vendored stack already owns; it computes the realized moments of a net-of-cost
return series and hands them to `psr` / `dsr`, builds the headline and diagnostic
return series from a batch, and constructs the CPCV splitter with an embargo that
covers the holding horizon.

At this pre-signal milestone the effective trial count is 1, so the Deflated Sharpe
degenerates to `psr(sr_hat, sr_star=0)` (the vendored `dsr` does this exactly), and
that PSR(0) IS the kill number (ADR 0003 amendment B4). The headline series is the
per-trade non-overlapping net series (cost-placement-invariant, honest T); the
per-interval lumpy/amortised pair is a diagnostic and the kill reads the less
favourable of the two (amendment B1, B2).

Moment conventions (documented, not re-litigated): `sr_hat = mean / sample_std`
(ddof=1, the standard Sharpe estimator that pairs with the `sqrt(T-1)` in PSR);
`gamma_3` / `gamma_4` are the population standardized third / fourth moments
(non-excess kurtosis, normal = 3), the realized skewness and kurtosis the
`_sigma_sq` correction expects.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import attrs
import polars as pl

from riskpremia.analytics.bootstrap import politis_white_block_length
from riskpremia.analytics.sharpe import psr
from riskpremia.execution.carry import (
    funding_window_indices,
    per_interval_pnl,
    simulate_trade,
)
from riskpremia.execution.cost import VenueCostModel
from riskpremia.execution.errors import ScoringError
from riskpremia.validation.cv import CPCVSplitter, _embargo_count

_DEFAULT_EMBARGO_PCT = 0.05
# A Politis-White block length at or below this is treated as "no detectable serial
# dependence", so the non-overlapping per-trade series' T is the honest independent
# sample size (design review M3); above it, T should be deflated by the block length.
IID_BLOCK_LENGTH_CEILING = 1.0


@attrs.frozen(slots=True)
class ReturnMoments:
    """The realized moments of a return series fed to the vendored PSR/DSR."""

    sr_hat: float
    gamma_3: float
    gamma_4: float
    t_obs: int
    mean: float
    std: float


def return_moments(returns: Sequence[float]) -> ReturnMoments:
    """Compute the realized Sharpe, skewness, and kurtosis of `returns`.

    Raises:
      ScoringError: when fewer than two observations or a zero standard deviation
        (the Sharpe and the standardized moments are then undefined).
    """
    n = len(returns)
    if n < 2:
        raise ScoringError(f"return_moments requires at least 2 observations; got {n}")
    mean = math.fsum(returns) / n
    centered = [float(r) - mean for r in returns]
    m2 = math.fsum(c * c for c in centered) / n
    if m2 <= 0.0:
        raise ScoringError(
            f"return_moments got a zero-variance series (every observation == {mean}); "
            f"the Sharpe is undefined"
        )
    std_pop = math.sqrt(m2)
    std_sample = math.sqrt(math.fsum(c * c for c in centered) / (n - 1))
    m3 = math.fsum(c * c * c for c in centered) / n
    m4 = math.fsum(c * c * c * c for c in centered) / n
    return ReturnMoments(
        sr_hat=mean / std_sample,
        gamma_3=m3 / (std_pop**3),
        gamma_4=m4 / (std_pop**4),
        t_obs=n,
        mean=mean,
        std=std_sample,
    )


def effective_sample_size(returns: Sequence[float]) -> tuple[int, float]:
    """The block-deflated effective sample size and the Politis-White block length.

    Funding-regime persistence makes even the strided non-overlapping per-trade
    series serially dependent (the realized Politis-White block length is well above
    1 on the real post-ETF data, NOT near-iid), so the honest `T` for the deflated
    Sharpe is the effective sample size `floor(n / block_length)`, not the raw
    observation count. For a genuinely iid series (block length <= 1) this is a no-op
    (`T` unchanged). Returns `(effective_t, pw_block_length)`."""
    n = len(returns)
    pw = politis_white_block_length(returns)
    block = max(1.0, pw)
    return max(2, int(n // block)), pw


def psr_zero(returns: Sequence[float]) -> float:
    """The kill number for one return series: `PSR(sr_star=0)` (ADR 0003 B4).

    At `n_effective = 1` the Deflated Sharpe degenerates to this exactly (the
    vendored `dsr`), so the probability that the true Sharpe exceeds zero IS the
    pre-signal deflated headline. A value below 0.95 fails the viability bar.

    `T` is the block-deflated effective sample size (`effective_sample_size`), not the
    raw observation count, so the residual serial dependence the non-overlapping
    series still carries (funding-regime persistence) does not overstate significance
    (ADR 0003 amendment B2 correction). The realized skewness and kurtosis are taken
    on the full series; only the significance `T` is deflated.
    """
    m = return_moments(returns)
    eff_t, _ = effective_sample_size(returns)
    return psr(m.sr_hat, 0.0, eff_t, m.gamma_3, m.gamma_4)


def per_trade_net_series(batch: pl.DataFrame) -> list[float]:
    """The per-trade `net_pretax` series from a (already entry-selected) batch.

    For the non-overlapping headline this is genuinely independent trade returns;
    cost placement is irrelevant here because a closed trade's net is the same
    lumpy or amortised (ADR 0003 B2)."""
    return [float(v) for v in batch["net_pretax"].to_list()]


def per_interval_series(
    observations: pl.DataFrame,
    entries: Sequence[int],
    *,
    horizon_events: int,
    cost_model: VenueCostModel,
    amortise: bool,
    entry_taker: bool = True,
    exit_taker: bool = True,
) -> list[float]:
    """Concatenate each selected trade's H per-interval contributions.

    `amortise=False` books the round-trip cost LUMPY (entry cost on the first
    interval, exit cost on the last, via `per_interval_pnl`); `amortise=True` smears
    `round_trip / H` evenly across the H intervals. Both bake the financing flow as
    `financing / H` per interval and realize `price_pnl` at the close, so the only
    difference is the round-trip cost placement and each trade's intervals still sum
    to the same `net_pretax` (the kill reads the less favourable of the two DSRs, a
    diagnostic that is only meaningful on the NON-overlapping null, ADR 0003 B1, B3).

    The entries must be non-overlapping for the concatenation to be a clean
    per-interval timeline; the caller passes `non_overlapping_entries`.
    """
    series: list[float] = []
    fr = observations["funding_rate"]
    for entry in entries:
        trade = simulate_trade(
            observations,
            entry,
            horizon_events=horizon_events,
            cost_model=cost_model,
            entry_taker=entry_taker,
            exit_taker=exit_taker,
        )
        if amortise:
            window = funding_window_indices(entry, horizon_events)
            per_interval_cost = (trade.round_trip_cost + trade.financing_cost) / horizon_events
            parts = [float(fr[j]) - per_interval_cost for j in window]
            parts[horizon_events - 1] += trade.price_pnl
        else:
            parts = per_interval_pnl(trade, observations)
        series.extend(parts)
    return series


def make_purged_cpcv(
    n_obs: int, horizon_events: int, *, n_groups: int = 6, k_test: int = 2
) -> CPCVSplitter:
    """A purged CPCV splitter whose embargo is guaranteed to cover the H-event hold.

    ADR 0003 finding 3 + amendment B4: the vendored embargo is `floor(n * pct)`,
    blind to H, so overlapping holds within H of a test block would leak. The
    embargo is derived from the INTEGER horizon, not a float `H / n` (which can floor
    to `H - 1` on a small frame and spuriously abort): `embargo_pct = max(0.05,
    (H + 0.5) / n_obs)`, then `_embargo_count >= H` is asserted before any split.

    Note (B4): for an unconditional carry (no fitted parameter) the CPCV is
    DEGENERATE (test-fold returns equal the in-sample returns), so it is wired and
    embargo-checked here but becomes load-bearing only once a selection signal exists.

    Raises:
      ScoringError: when the required embargo would not leave a usable train set
        (`embargo_pct >= 1`), or the post-construction embargo assertion fails.
    """
    if horizon_events < 1:
        raise ScoringError(f"make_purged_cpcv requires horizon_events >= 1; got {horizon_events}")
    if n_obs < n_groups:
        raise ScoringError(
            f"make_purged_cpcv requires n_obs >= n_groups; got n_obs={n_obs}, n_groups={n_groups}"
        )
    embargo_pct = max(_DEFAULT_EMBARGO_PCT, (horizon_events + 0.5) / n_obs)
    if embargo_pct >= 1.0:
        raise ScoringError(
            f"make_purged_cpcv: the embargo needed to cover horizon_events={horizon_events} on "
            f"n_obs={n_obs} rows is {embargo_pct:.3f} >= 1 (no usable train set); use more rows"
        )
    if _embargo_count(n_obs, embargo_pct) < horizon_events:
        raise ScoringError(
            f"make_purged_cpcv: embargo_count={_embargo_count(n_obs, embargo_pct)} does not cover "
            f"horizon_events={horizon_events} (embargo_pct={embargo_pct})"
        )
    return CPCVSplitter(n_groups=n_groups, k_test=k_test, embargo_pct=embargo_pct)
