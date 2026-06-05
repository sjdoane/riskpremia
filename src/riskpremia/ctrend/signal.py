"""The CTREND cross-sectional combined elastic-net (CS-C-ENet) signal (Study 3, PR2).

The first fitted model in the project. Implements Fieberg et al. (JFQA 2025) eq 3-11
(docs/research/0003): cross-sectionally rank each of the 28 daily signals into [-0.5, 0.5];
per signal, a weekly cross-sectional univariate Fama-MacBeth regression with 52-week
coefficient smoothing gives a univariate return forecast (eq 7-8); an elastic net over the
trailing 52-week pool SELECTS which univariate forecasts are useful (eq 10); the CTREND
forecast is the equal-weight average of the surviving (positive-weight) univariate
forecasts (eq 11); coins are then sorted into quintiles. Fit strictly point-in-time: the
forecast at week t uses only data realized at or before week t-1 (the smoothing window and
the elastic-net pool both end at t-1; including t would use the very return being
predicted, the one look-ahead foreclosed and tested).

Deviations (docs/research/0003): equal-weight OLS (the paper value-weights by market cap,
unavailable on Binance); raw weekly returns (the cross-sectional intercept absorbs the
common risk-free rate, so the slopes and the rank are unaffected to first order). The
gate-critical elastic-net SELECTION uses scikit-learn (pinned, deterministic) with an
in-repo corrected-AIC lambda choice. PR2's deliverable is the GROSS point-in-time rank IC +
the quintile spread (the VRP Layer-i analogue); the net-of-cost Deflated-Sharpe kill gate is
PR3. polars + numpy + scikit-learn; no RNG in the signal path (the solver is cyclic).
"""

from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import enet_path

from riskpremia.ctrend.errors import CtrendError
from riskpremia.ctrend.features import SIGNAL_COLUMNS, compute_weekly_features

DEFAULT_FIT_WINDOW = 52
"""The rolling window (weeks) for both the FM coefficient smoothing and the elastic-net
pool (the paper's fixed 52-week estimation window)."""
DEFAULT_N_QUINTILES = 5
DEFAULT_L1_RATIO = 0.5
"""The elastic-net L1/L2 mix (the paper's 0.5)."""
_ENET_N_ALPHAS = 50
_ENET_EPS = 1e-3
_ENET_MAX_ITER = 20000
_ENET_TOL = 1e-4
_COEF_TOL = 1e-8
"""A coefficient above this counts as selected (theta_j > 0, eq 11); the small floor avoids
a borderline coefficient flipping the averaged set across platforms."""


def rank_to_unit_interval(values: pl.Expr, by: str) -> pl.Expr:
    """Cross-sectional rank of `values` within each `by` group, mapped to [-0.5, 0.5].

    `(rank - 1) / (N - 1) - 0.5` (Kelly-Pruitt-Su / Gu-Kelly-Xiu, the closed interval),
    average-rank ties, where N is the count of NON-NULL values in the group. A group with
    fewer than 2 non-null values maps to null (no usable cross-section). Nulls stay null.
    """
    rank = values.rank(method="average").over(by)
    n = values.count().over(by)
    return (
        pl.when(n >= 2)
        .then((rank - 1.0) / (n - 1.0) - 0.5)
        .otherwise(None)
    )


def _rank_signals(frame: pl.DataFrame) -> pl.DataFrame:
    """Replace each of the 28 signal columns with its per-week cross-sectional rank map."""
    return frame.with_columns(
        *[rank_to_unit_interval(pl.col(sig), "week_end").alias(sig) for sig in SIGNAL_COLUMNS]
    )


def _univariate_fm(ranked: pl.DataFrame) -> pl.DataFrame:
    """Per (week_end, signal): the cross-sectional univariate OLS (alpha, beta) of
    forward_return on the ranked signal (eq 7), over coins with both non-null.

    Returns a long frame `(week_end, signal, alpha, beta)`, beta null where a week/signal
    has fewer than 2 paired non-null observations.
    """
    long = ranked.unpivot(
        index=["week_end", "symbol", "forward_return"],
        on=list(SIGNAL_COLUMNS),
        variable_name="signal",
        value_name="z",
    ).drop_nulls(["z", "forward_return"])
    # OLS slope via the moment formula: beta = cov(z, r) / var(z); alpha = mean(r) - beta*mean(z).
    agg = long.group_by(["week_end", "signal"]).agg(
        pl.len().alias("n"),
        pl.col("z").mean().alias("mz"),
        pl.col("forward_return").mean().alias("mr"),
        (pl.col("z") * pl.col("forward_return")).mean().alias("mzr"),
        (pl.col("z") * pl.col("z")).mean().alias("mzz"),
    )
    var_z = pl.col("mzz") - pl.col("mz") ** 2
    beta = (pl.col("mzr") - pl.col("mz") * pl.col("mr")) / var_z
    agg = agg.with_columns(
        pl.when((pl.col("n") >= 2) & (var_z > 0.0)).then(beta).otherwise(None).alias("beta")
    )
    agg = agg.with_columns((pl.col("mr") - pl.col("beta") * pl.col("mz")).alias("alpha"))
    return agg.select("week_end", "signal", "alpha", "beta").sort(["signal", "week_end"])


def _smooth_coeffs(fm: pl.DataFrame, window: int) -> pl.DataFrame:
    """Smooth (alpha, beta) over the trailing `window` weeks EXCLUDING the current week.

    At decision week t the smoothed coefficient is the mean of the per-week coefficients over
    weeks {t-window, ..., t-1} (eq 4-5); the `.shift(1)` excludes week t (whose forward
    return is the future being forecast, the H3 no-look-ahead boundary). Per signal, ordered
    by week. Requires the full window of non-null weekly coefficients (min_samples=window).
    """
    by = "signal"

    def _smoothed(col: str) -> pl.Expr:
        rolled = pl.col(col).rolling_mean(window_size=window, min_samples=window).over(by)
        return rolled.shift(1).over(by)

    return fm.sort([by, "week_end"]).with_columns(
        _smoothed("alpha").alias("alpha_bar"),
        _smoothed("beta").alias("beta_bar"),
    ).select("week_end", "signal", "alpha_bar", "beta_bar")


def _univariate_forecasts(ranked: pl.DataFrame, smoothed: pl.DataFrame) -> pl.DataFrame:
    """The eq-8 univariate forecasts rhat^j_i(t) = alpha_bar + beta_bar * z_j(t), wide.

    Returns `(week_end, symbol, forward_return, rhat_<signal>...)`: for each (week, coin) the
    J univariate forecasts (the as-of-week forecast, since the smoothing used only weeks < t).
    """
    long = ranked.unpivot(
        index=["week_end", "symbol", "forward_return"],
        on=list(SIGNAL_COLUMNS),
        variable_name="signal",
        value_name="z",
    )
    joined = long.join(smoothed, on=["week_end", "signal"], how="left")
    joined = joined.with_columns(
        (pl.col("alpha_bar") + pl.col("beta_bar") * pl.col("z")).alias("rhat")
    )
    wide = joined.pivot(
        values="rhat", index=["week_end", "symbol", "forward_return"], on="signal"
    )
    rhat_cols = [c for c in wide.columns if c in SIGNAL_COLUMNS]
    rename = {c: f"rhat_{c}" for c in rhat_cols}
    return wide.rename(rename).sort(["week_end", "symbol"])


def select_enet(
    x: npt.NDArray[np.float64], y: npt.NDArray[np.float64], *, l1_ratio: float = DEFAULT_L1_RATIO
) -> npt.NDArray[np.bool_]:
    """Elastic-net SELECTION (eq 10): a boolean mask of the positive-weight features.

    Fits the elastic-net path (scikit-learn `enet_path`, deterministic) on the standardized,
    centered pool, picks the regularization by corrected AIC computed in-repo
    (k = #nonzero + intercept + sigma^2; #nonzero-as-df is the standard elastic-net
    approximation), and returns `coef > tol` (theta_j > 0, the eq-11 positive-weight set).
    Returns an all-False mask if no model is identifiable (degenerate pool).
    """
    n, p = x.shape
    mask = np.zeros(p, dtype=bool)
    if n < 3:
        return mask
    x_mean = x.mean(axis=0)
    x_std = x.std(axis=0)
    x_std = np.where(x_std == 0.0, 1.0, x_std)
    xc = (x - x_mean) / x_std
    yc = y - y.mean()
    with warnings.catch_warnings():
        # The pool's forecast columns are collinear (all are return forecasts); the path can
        # hit max_iter on the least-regularized end without affecting the selected (more
        # regularized) model. Suppress the benign ConvergenceWarning under filterwarnings=error.
        warnings.simplefilter("ignore", ConvergenceWarning)
        _alphas, coefs, _ = enet_path(
            xc, yc, l1_ratio=l1_ratio, n_alphas=_ENET_N_ALPHAS, eps=_ENET_EPS,
            max_iter=_ENET_MAX_ITER, tol=_ENET_TOL,
        )
    best_aicc = math.inf
    best_coef = coefs[:, 0]
    for col in range(coefs.shape[1]):
        coef = coefs[:, col]
        resid = yc - xc @ coef
        rss = float(resid @ resid)
        nnz = int(np.count_nonzero(np.abs(coef) > _COEF_TOL))
        k = nnz + 2  # the (centered) intercept + the residual variance
        if n - k - 1 <= 0:
            continue
        aicc = -math.inf if rss <= 0.0 else (
            n * math.log(rss / n) + 2 * k + 2 * k * (k + 1) / (n - k - 1)
        )
        if aicc < best_aicc:
            best_aicc = aicc
            best_coef = coef
    return np.asarray(best_coef > _COEF_TOL, dtype=bool)


def _combined_forecasts(wide: pl.DataFrame, window: int) -> pl.DataFrame:
    """The eq-10 selection + the eq-11 averaged CTREND forecast, per decision week.

    For each decision week t (with a full trailing `window`-week complete-case pool), the
    elastic net selects the useful univariate forecasts on the pool {(forward_return(m),
    rhat(m)) : m in [t-window, t-1]}, and CTREND_i(t) is the equal-weight mean of the
    selected, non-null rhat^j_i(t). A coin with no selected non-null forecast that week gets
    no CTREND (dropped from the sort). Returns `(week_end, symbol, ctrend)`.
    """
    rhat_cols = [f"rhat_{c}" for c in SIGNAL_COLUMNS]
    weeks = wide["week_end"].unique().sort().to_list()
    rows: list[dict[str, Any]] = []
    for t_idx, week in enumerate(weeks):
        if t_idx < window:
            continue
        pool_weeks = weeks[t_idx - window:t_idx]  # [t-window, t-1] inclusive
        pool = wide.filter(pl.col("week_end").is_in(pool_weeks)).drop_nulls(
            ["forward_return", *rhat_cols]
        )
        if pool.height < 3:
            continue
        x = pool.select(rhat_cols).to_numpy()
        y = pool["forward_return"].to_numpy()
        selected = select_enet(x, y)
        if not selected.any():
            continue
        sel_cols = [rhat_cols[j] for j in range(len(rhat_cols)) if selected[j]]
        current = wide.filter(pl.col("week_end") == week)
        # CTREND_i = equal-weight mean of the selected, non-null univariate forecasts.
        ctrend = current.select(
            "symbol", pl.mean_horizontal(*[pl.col(c) for c in sel_cols]).alias("ctrend")
        ).drop_nulls("ctrend")
        for symbol, value in zip(ctrend["symbol"], ctrend["ctrend"], strict=True):
            rows.append({"week_end": week, "symbol": symbol, "ctrend": float(value)})
    if not rows:
        raise CtrendError(
            "no CTREND forecasts produced; the panel may be too short for the fit window"
        )
    return pl.DataFrame(rows, schema={"week_end": pl.Date, "symbol": pl.Utf8, "ctrend": pl.Float64})


def assign_quintiles(
    forecasts: pl.DataFrame, *, n_quintiles: int = DEFAULT_N_QUINTILES
) -> pl.DataFrame:
    """Assign each (week, coin) a 0-based quintile on CTREND (highest CTREND = top quintile).

    Equal-count bins by within-week CTREND rank, the top `1/n` the long quintile
    (`quintile == n_quintiles - 1`). Deterministic: ascending-CTREND rank, symbol-ascending
    tie-break (the PR1 convention); a week with fewer than `n_quintiles` coins is dropped
    (cannot form the quantiles).
    """
    ranked = forecasts.sort(["week_end", "ctrend", "symbol"]).with_columns(
        pl.int_range(pl.len()).over("week_end").alias("_rank0"),
        pl.len().over("week_end").alias("_n"),
    )
    ranked = ranked.filter(pl.col("_n") >= n_quintiles)
    quintile = (pl.col("_rank0") * n_quintiles // pl.col("_n")).clip(0, n_quintiles - 1)
    return ranked.with_columns(quintile.cast(pl.Int32).alias("quintile")).drop("_rank0", "_n")


def ctrend_forecasts(
    daily: pl.DataFrame,
    weekly_eligible: pl.DataFrame,
    *,
    fit_window: int = DEFAULT_FIT_WINDOW,
    n_quintiles: int = DEFAULT_N_QUINTILES,
) -> pl.DataFrame:
    """The full CTREND pipeline: features -> rank -> FM -> elastic net -> CTREND -> quintiles.

    `weekly_eligible` is the `pit_eligible(build_weekly_panel(daily))` frame (carrying
    `week_end, symbol, eligible, forward_return`). Returns `(week_end, symbol, ctrend,
    quintile, forward_return)` for the eligible coins on the post-burn-in weeks.

    Raises:
      CtrendError: on missing inputs or a panel too short for the fit window.
    """
    needed = {"week_end", "symbol", "eligible", "forward_return"}
    missing = needed - set(weekly_eligible.columns)
    if missing:
        raise CtrendError(f"ctrend_forecasts: weekly_eligible missing {sorted(missing)}")

    features = compute_weekly_features(daily)
    elig = weekly_eligible.filter(pl.col("eligible")).select("week_end", "symbol", "forward_return")
    frame = elig.join(features, on=["week_end", "symbol"], how="left").sort(["week_end", "symbol"])

    ranked = _rank_signals(frame)
    fm = _univariate_fm(ranked)
    smoothed = _smooth_coeffs(fm, fit_window)
    wide = _univariate_forecasts(ranked, smoothed)
    ctrend = _combined_forecasts(wide, fit_window)

    out = ctrend.join(
        weekly_eligible.select("week_end", "symbol", "forward_return"),
        on=["week_end", "symbol"],
        how="left",
    )
    return assign_quintiles(out, n_quintiles=n_quintiles).sort(["week_end", "symbol"])


def _spearman(a: list[float], b: list[float]) -> float | None:
    """Spearman rank correlation of two equal-length lists (None if < 3 or degenerate)."""
    n = len(a)
    if n < 3:
        return None
    ra = _ranks(a)
    rb = _ranks(b)
    mean_a = sum(ra) / n
    mean_b = sum(rb) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb, strict=True))
    var_a = sum((x - mean_a) ** 2 for x in ra)
    var_b = sum((y - mean_b) ** 2 for y in rb)
    if var_a <= 0.0 or var_b <= 0.0:
        return None
    return cov / math.sqrt(var_a * var_b)


def _ranks(values: list[float]) -> list[float]:
    """Average ranks (1-based) of `values`, ties shared (for Spearman)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def signal_rank_ic(forecasts: pl.DataFrame) -> dict[str, float]:
    """The point-in-time cross-sectional rank IC of CTREND vs the realized forward return.

    Per week, the Spearman correlation of `ctrend` with `forward_return` over the eligible
    coins (both non-null), averaged over the scored weeks. A positive mean IC is the gross,
    necessary-not-sufficient signal-quality proof (PR2; the net-of-cost gate is PR3).
    """
    valid = forecasts.drop_nulls(["ctrend", "forward_return"])
    ics: list[float] = []
    for (_week,), sub in valid.group_by(["week_end"], maintain_order=True):
        ic = _spearman(
            [float(v) for v in sub["ctrend"].to_list()],
            [float(v) for v in sub["forward_return"].to_list()],
        )
        if ic is not None:
            ics.append(ic)
    if not ics:
        raise CtrendError("signal_rank_ic found no scorable weeks")
    mean_ic = sum(ics) / len(ics)
    std_ic = math.sqrt(sum((x - mean_ic) ** 2 for x in ics) / len(ics)) if len(ics) > 1 else 0.0
    return {
        "mean_ic": mean_ic,
        "n_weeks": float(len(ics)),
        "ic_t_stat": (mean_ic / (std_ic / math.sqrt(len(ics)))) if std_ic > 0.0 else 0.0,
        "frac_positive": sum(1 for x in ics if x > 0.0) / len(ics),
    }


def quintile_spread(
    forecasts: pl.DataFrame, *, n_quintiles: int = DEFAULT_N_QUINTILES
) -> list[float]:
    """The equal-weight mean forward return per CTREND quintile (0 = bottom .. n-1 = top).

    The monotonicity + the top-minus-bottom spread is the gross signal-quality exhibit (PR2);
    the returns are pre-cost and equal-weight, NOT the paper's value-weighted net portfolio.
    """
    valid = forecasts.drop_nulls(["quintile", "forward_return"])
    means = (
        valid.group_by("quintile")
        .agg(pl.col("forward_return").mean().alias("mean_fwd"))
        .sort("quintile")
    )
    out = [0.0] * n_quintiles
    for q, m in zip(means["quintile"], means["mean_fwd"], strict=True):
        if 0 <= int(q) < n_quintiles:
            out[int(q)] = float(m)
    return out
