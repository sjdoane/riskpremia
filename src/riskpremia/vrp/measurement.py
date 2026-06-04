"""The crypto VRP measurement (Layer i, the reproducible floor; ADR 0004 PR5a).

Assembles the variance risk premium from the Deribit DVOL implied variance and the
matched-horizon realized variance (`vrp.realized`), then summarises it honestly.

Two VRP objects are computed and kept SEPARATE (ADR 0004 caveat 2):
  - `vrp_forward[t] = IV(t)^2 - RV(t+1 .. t+W)`: the EX-POST realized premium, the
    measurement HEADLINE. It uses future data by construction and is NOT a tradeable
    signal.
  - `vrp_trailing[t] = IV(t)^2 - RV(t-W+1 .. t)`: the tradeable proxy (Layer-ii
    input), using only past data.

Inference mirrors the carry study's overlap discipline (ADR 0003 finding 9, reused
here): the forward windows overlap W-1 of W days, so the daily series is heavily
autocorrelated and a naive t-stat is dishonest. The HEADLINE is therefore the
NON-OVERLAPPING strided series (every W-th day, disjoint realized windows), reported
across all W phase offsets (a band, so no lucky start date is cherry-picked), with a
block-bootstrap CI and the Politis-White block-deflated effective sample size
(`effective_sample_size`). The overlapping daily mean is reported only as a
descriptive figure.

Caveat carried at the point of computation (ADR 0004 caveat: the Deribit-index vs
Binance-spot basis): the implied leg is on Deribit's BTC index, the realized leg on
the Binance spot close, so the VRP carries a cross-underlying basis. v1 uses Binance
spot (the reproducible immutable backbone) and reports the premium as a proxy; the
basis is small off crash days and is bounded as a follow-up diagnostic.
"""

from __future__ import annotations

import statistics

import attrs
import polars as pl

from riskpremia.analytics.bootstrap import stationary_block_bootstrap
from riskpremia.data.clock import SPOT_ETF_LAUNCH
from riskpremia.data.records import DvolRecord, SpotPriceRecord
from riskpremia.execution.scoring import effective_sample_size
from riskpremia.vrp.errors import VrpError
from riskpremia.vrp.realized import realized_variance_frame

_VOL_POINTS = 100.0
"""DVOL is quoted in vol percentage points; DVOL / 100 is the annualized vol, and
(DVOL / 100) ** 2 the annualized implied variance (365-day basis, matched to RV)."""


def build_vrp_frame(
    dvol: list[DvolRecord],
    spot: list[SpotPriceRecord],
    *,
    window_days: int = 30,
) -> pl.DataFrame:
    """Align DVOL implied variance with realized variance into the daily VRP frame.

    Returns `[date, dvol_close, implied_var, rv_trailing, rv_forward, vrp_trailing,
    vrp_forward, vol_spread_forward, regime]`, inner-joined on the UTC date and
    sorted. `regime` is `pre_etf` / `post_etf` split on `SPOT_ETF_LAUNCH` (left-closed:
    the launch day is post). `vol_spread_forward = DVOL/100 - sqrt(RV_forward)` is the
    vol-point view (a DISTINCT payoff object from the variance premium, not its square
    root; they can disagree by the vol-of-vol convexity gap).

    Raises:
      VrpError: on empty inputs or an empty implied/realized alignment (the realized
        estimator separately raises on a calendar gap).
    """
    if not dvol:
        raise VrpError("build_vrp_frame requires at least one DVOL record")
    if not spot:
        raise VrpError("build_vrp_frame requires at least one spot record")
    dvol_frame = (
        pl.DataFrame(
            {"date": [r.ts.date() for r in dvol], "dvol_close": [float(r.close) for r in dvol]}
        )
        .unique("date", keep="last")
        .sort("date")
        .with_columns(((pl.col("dvol_close") / _VOL_POINTS) ** 2).alias("implied_var"))
    )
    spot_frame = (
        pl.DataFrame(
            {
                "date": [r.period_end_ts.date() for r in spot],
                "close": [float(r.close) for r in spot],
            }
        )
        .unique("date", keep="last")
        .sort("date")
    )
    realized = realized_variance_frame(spot_frame, window_days=window_days)
    etf = SPOT_ETF_LAUNCH.date()
    out = (
        dvol_frame.join(realized, on="date", how="inner")
        .sort("date")
        .with_columns(
            (pl.col("implied_var") - pl.col("rv_forward")).alias("vrp_forward"),
            (pl.col("implied_var") - pl.col("rv_trailing")).alias("vrp_trailing"),
            (pl.col("dvol_close") / _VOL_POINTS - pl.col("rv_forward").sqrt()).alias(
                "vol_spread_forward"
            ),
            pl.when(pl.col("date") >= etf)
            .then(pl.lit("post_etf"))
            .otherwise(pl.lit("pre_etf"))
            .alias("regime"),
        )
    )
    if out.height == 0:
        raise VrpError("build_vrp_frame produced an empty DVOL/realized alignment")
    return out.select(
        "date",
        "dvol_close",
        "implied_var",
        "rv_trailing",
        "rv_forward",
        "vrp_trailing",
        "vrp_forward",
        "vol_spread_forward",
        "regime",
    )


@attrs.frozen(slots=True)
class VrpHeadline:
    """The honest VRP measurement summary (variance points unless noted).

    `mean_phase_median` (the median of the W non-overlapping strided-phase means) is
    the HEADLINE mean premium; `[mean_phase_min, mean_phase_max]` is the phase band.
    `ci_low/ci_high` is the block-bootstrap 95% CI of the canonical (phase-0)
    non-overlapping strided mean; `effective_t` is its Politis-White block-deflated
    sample size. `mean_vrp_forward` is the overlapping daily mean (descriptive only).
    """

    window_days: int
    n_forward_obs: int
    n_strided: int
    mean_vrp_forward: float
    mean_phase_median: float
    mean_phase_min: float
    mean_phase_max: float
    ci_low: float
    ci_high: float
    effective_t: float
    pw_block_length: float
    frac_positive: float
    mean_vrp_pre_etf: float
    mean_vrp_post_etf: float
    mean_vol_spread_forward: float


def _percentile(sorted_values: list[float], q: float) -> float:
    """The q-quantile of an already-sorted list by the nearest-rank index."""
    idx = min(len(sorted_values) - 1, max(0, int(q * len(sorted_values))))
    return sorted_values[idx]


def vrp_headline(
    vrp_frame: pl.DataFrame, *, window_days: int = 30, seed: int = 20260604, n_boot: int = 2000
) -> VrpHeadline:
    """Summarise the VRP honestly on the NON-OVERLAPPING strided forward series.

    Raises:
      VrpError: when there are fewer than `2 * window_days` non-null forward-VRP
        observations (too few to form a non-overlapping series).
    """
    fwd = vrp_frame.filter(pl.col("vrp_forward").is_not_null()).sort("date")
    series = [float(v) for v in fwd["vrp_forward"].to_list()]
    if len(series) < 2 * window_days:
        raise VrpError(
            f"vrp_headline needs >= {2 * window_days} non-null forward-VRP observations; "
            f"got {len(series)}"
        )

    # Non-overlapping strided phases: each offset gives disjoint W-day realized windows.
    phase_means = [
        statistics.fmean(series[phase::window_days])
        for phase in range(window_days)
        if len(series[phase::window_days]) >= 2
    ]
    # The canonical phase-0 strided series carries the CI + the block-deflated T.
    canonical = series[0::window_days]
    eff_t, pw = effective_sample_size(canonical)
    boot = stationary_block_bootstrap(
        canonical, n_boot, expected_block_length=max(2.0, pw), seed=seed
    )
    boot_means = sorted(statistics.fmean(path) for path in boot)

    pre = [float(v) for v in fwd.filter(pl.col("regime") == "pre_etf")["vrp_forward"].to_list()]
    post = [float(v) for v in fwd.filter(pl.col("regime") == "post_etf")["vrp_forward"].to_list()]
    # `fwd` is already filtered to non-null forward VRP, and vol_spread is null on
    # exactly the same rows (both null iff rv_forward is null), so these are the same
    # row set as `series` (no separate drop_nulls that could desynchronise the means).
    vol_spread = [float(v) for v in fwd["vol_spread_forward"].to_list()]

    return VrpHeadline(
        window_days=window_days,
        n_forward_obs=len(series),
        n_strided=len(canonical),
        mean_vrp_forward=statistics.fmean(series),
        mean_phase_median=statistics.median(phase_means),
        mean_phase_min=min(phase_means),
        mean_phase_max=max(phase_means),
        ci_low=_percentile(boot_means, 0.025),
        ci_high=_percentile(boot_means, 0.975),
        effective_t=float(eff_t),
        pw_block_length=pw,
        frac_positive=sum(1 for v in series if v > 0) / len(series),
        mean_vrp_pre_etf=statistics.fmean(pre) if pre else float("nan"),
        mean_vrp_post_etf=statistics.fmean(post) if post else float("nan"),
        mean_vol_spread_forward=statistics.fmean(vol_spread) if vol_spread else float("nan"),
    )
