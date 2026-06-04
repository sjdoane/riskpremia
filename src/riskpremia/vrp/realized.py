"""The realized-variance estimator for the VRP study (ADR 0004 PR5a).

The realized leg matched to Deribit's 30-day model-free DVOL: the variance-swap
realized variance, i.e. the ZERO-MEAN sum of squared LOG returns over a window,
annualized on the SAME 365-day basis as DVOL (`CRYPTO_ANNUALIZATION_DAYS`). No
demeaning (the variance-swap payoff is on actual squared returns, not deviations);
log returns (the log-contract replication DVOL is built on). The daily-sampling
drift term is an O(1/n) bias bounded by the in-sample trend and is deliberately not
removed, to match the swap payoff.

Two horizon conventions, both annualized as `(365 / window_days) * sum(r^2)` over a
COMPLETE window (an incomplete window is null, never partially scaled, so the
estimate cannot drift with the observation count, design review C1):
  - rv_trailing[t] = realized over days (t-W+1 .. t)   -> uses only PAST data, the
    Layer-ii tradeable input.
  - rv_forward[t]  = realized over days (t+1 .. t+W)    -> the EX-POST realized leg
    of the headline measurement (NOT tradeable; it uses future data by construction).
The two share no day for a given anchor t (forward starts t+1, trailing ends t).

The input MUST be a complete, gap-free daily UTC calendar (a gap would make a
row-windowed sum silently span more than W calendar days); a gap raises rather than
being interpolated (the loud-failure discipline; a missing crash-day close is
exactly when you must not silently fill).
"""

from __future__ import annotations

import polars as pl

from riskpremia.data.clock import CRYPTO_ANNUALIZATION_DAYS
from riskpremia.vrp.errors import VrpError

_REQUIRED = ("date", "close")


def _require_contiguous_daily(frame: pl.DataFrame) -> None:
    missing = [c for c in _REQUIRED if c not in frame.columns]
    if missing:
        raise VrpError(f"realized variance requires columns {list(_REQUIRED)}; missing {missing}")
    if frame.height < 2:
        raise VrpError(f"realized variance requires at least 2 daily closes; got {frame.height}")
    gaps = frame["date"].diff().dt.total_days().drop_nulls()
    if not bool((gaps == 1).all()):
        # surface the first offending gap rather than silently spanning it
        bad = frame.with_columns(frame["date"].diff().dt.total_days().alias("_gap")).filter(
            pl.col("_gap") != 1
        )
        first = bad.row(0, named=True) if bad.height else None
        raise VrpError(
            f"realized variance requires a gap-free daily calendar; found a non-1-day "
            f"step (first at {first}); densify or fail, do not interpolate"
        )
    if frame["close"].null_count() > 0:
        raise VrpError("realized variance found a null close in the calendar; fail, do not fill")


def realized_variance_frame(
    closes: pl.DataFrame,
    *,
    window_days: int,
    annualization_days: float = CRYPTO_ANNUALIZATION_DAYS,
) -> pl.DataFrame:
    """Return `[date, rv_trailing, rv_forward]` annualized realized variance.

    `closes` is a gap-free daily `[date (pl.Date), close (Float64)]` frame sorted
    ascending. A window is computed only when COMPLETE (all `window_days` returns
    present), null otherwise. `rv_forward[t]` is `rv_trailing[t + window_days]` (the
    same sum, re-anchored), so the forward leg reuses days strictly after `t`.

    Raises:
      VrpError: on a missing column, fewer than 2 rows, a calendar gap, a null
        close, or `window_days < 2`.
    """
    if window_days < 2:
        raise VrpError(f"realized_variance_frame requires window_days >= 2; got {window_days}")
    _require_contiguous_daily(closes)
    factor = annualization_days / window_days
    out = closes.sort("date").with_columns(
        ((pl.col("close") / pl.col("close").shift(1)).log() ** 2).alias("_r2")
    )
    # Trailing sum over the prior W returns (null until W valid returns exist, and
    # null if any return in the window is null), annualized by 365/W.
    out = out.with_columns(
        (pl.col("_r2").rolling_sum(window_size=window_days) * factor).alias("rv_trailing")
    )
    # Forward leg = the trailing sum re-anchored W rows earlier (days t+1..t+W).
    out = out.with_columns(pl.col("rv_trailing").shift(-window_days).alias("rv_forward"))
    return out.select("date", "rv_trailing", "rv_forward")
