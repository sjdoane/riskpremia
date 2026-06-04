"""The per-trade delta-neutral carry P&L and the vectorised batch (ADR 0003).

The trade: enter just AFTER the funding settlement at `dt[i]` (long spot N, short
perp N), collect the funding the short receives over the next H settlements, close
both legs at the settlement `dt[i+H]`. No RNG, no IO. The null, the per-period
series, the CPCV glue, and the kill number are PR4b; this module is the per-trade
math everything downstream is built on.

The central invariant (ADR 0003, the kill_gate-marked section): the funding window
for entry `i` is exactly `range(i+1, i+H+1)`, and its last index `i+H` is the same
event `make_label_horizons` labels with `dt.shift(-H)`, so the per-trade return and
the event-time-purged CPCV label score the SAME economic object. `funding_window_indices`
is the single source of truth for that window; the scalar guard and the batch slice
both derive their bounds from it, so a future off-by-one cannot let one path
silently book a truncated-window trade the other rejects.

Sign convention (ADR 0003 finding 1, pinned by an economic-direction fixture, not
this comment): `funding_rate` positive means longs PAY shorts. The delta-neutral
book is SHORT the perp, so it COLLECTS positive funding:
`funding_collected = + sum(funding_rate[i+1 .. i+H])`.

Units (load-bearing): every P&L term is a fraction of the single-leg notional N
(funding and the two price legs are returns on N; the cost fractions are on the
same N), so the terms add without a rebasing step. `financing_cost` carries the
no-cross-margin 2N base inside `capital_multiple` (cost.py).

`price_pnl` is the equal-notional static-notional basis-convergence term (ADR
finding 4). v1 holds both legs with no intra-hold rebalance, so it is an
approximation with a signed (short-gamma) bias; `gross` includes it for the DSR
series, but the early economic gate reads `funding_collected` alone (ADR amendment
A3), and the real-data bound reports the SIGNED `mean(price_pnl)` so a proxy that
pads the carry is detectable.
"""

from __future__ import annotations

from datetime import datetime

import attrs
import polars as pl

from riskpremia.execution.cost import VenueCostModel
from riskpremia.execution.errors import CarryComputationError

_REQUIRED_COLUMNS = ("dt", "funding_rate", "spot_close", "perp_close")
"""Columns `simulate_trade` / `simulate_batch` read; a missing one raises rather
than producing a null-filled result. `build_observation_frame` supplies all four."""

_MICROSECONDS_PER_HOUR = 3_600_000_000.0
"""The hold duration is computed from integer microseconds (the `dt` dtype is
`Datetime("us")`) in BOTH the scalar and the batch path, so they are numerically
identical. Reading whole seconds would truncate the few-ms jitter Binance carries
around the settlement instant, making the batch financing disagree with the scalar
by up to a second of hold (a determinism defect at the batch/scalar parity check)."""

# The batch funding sum (polars rolling_sum) and the scalar funding sum (Python
# left-to-right) sum the same H terms with different associativity, so they agree
# only to floating-point rounding, never bit-for-bit. The batch/scalar parity test
# asserts agreement within this absolute tolerance; it is NOT tightened to exact
# equality (that would flake on the real long BTCUSDT frame, where a multi-year
# mostly-positive funding series accumulates cancellation).
BATCH_SCALAR_ATOL = 1e-12


def funding_window_indices(entry_index: int, horizon_events: int) -> range:
    """The funding settlements entry `entry_index` collects: `range(i+1, i+H+1)`.

    The single source of truth for the carry window. Entry is just after the
    settlement at `dt[entry_index]` (so `funding_rate[entry_index]` is NOT
    collected); the first collected funding is `funding_rate[entry_index+1]`; the
    last is `funding_rate[entry_index+H]`, settling at `dt[entry_index+H]`, the
    same event `make_label_horizons` labels (the index identity).

    Raises:
      CarryComputationError: when `horizon_events < 1` or `entry_index < 0`.
    """
    if horizon_events < 1:
        raise CarryComputationError(
            f"funding_window_indices requires horizon_events >= 1; got {horizon_events}"
        )
    if entry_index < 0:
        raise CarryComputationError(
            f"funding_window_indices requires entry_index >= 0; got {entry_index}"
        )
    return range(entry_index + 1, entry_index + horizon_events + 1)


def valid_entry_range(height: int, horizon_events: int) -> range:
    """The entry indices with a complete forward window AND an in-range exit price.

    Derived from `funding_window_indices`: entry `i` is valid iff its window's last
    index `i+H` is a valid row (`i+H <= height-1`), i.e. `i in range(0, height-H)`.
    Both the scalar guard and the batch slice use this, so the boundary lives in
    one place (ADR 0003 PR4a finding 1)."""
    if horizon_events < 1:
        raise CarryComputationError(
            f"valid_entry_range requires horizon_events >= 1; got {horizon_events}"
        )
    return range(0, max(0, height - horizon_events))


@attrs.frozen(slots=True)
class TradePnL:
    """The P&L of one delta-neutral carry trade, every term a fraction of notional N.

    Invariants (pinned by tests, exact since each is a single addition with no
    cancellation): `round_trip_cost == entry_cost + exit_cost`;
    `gross == funding_collected + price_pnl`;
    `net_pretax == gross - round_trip_cost - financing_cost`.
    """

    entry_index: int
    exit_index: int
    horizon_events: int
    hold_hours: float
    funding_collected: float
    spot_leg_pnl: float
    perp_leg_pnl: float
    price_pnl: float
    entry_cost: float
    exit_cost: float
    round_trip_cost: float
    financing_cost: float
    gross: float
    net_pretax: float


def _cell_float(value: object, *, column: str, index: int) -> float:
    """Narrow a polars scalar cell to a non-null float, or raise loudly.

    Reading `frame[col][i]` returns a broadly-typed value; this narrows it to
    `float` at the one point of use (mirrors `clock._scalar_float`) and converts a
    null price/rate into a loud `CarryComputationError` rather than a silent NaN.
    """
    if value is None:
        raise CarryComputationError(
            f"carry computation hit a null {column!r} at row {index} (a data gap; the "
            f"study warms up the price legs before the funding window so entry/exit "
            f"prices are non-null). Refusing to produce a garbage delta-neutral return."
        )
    return float(value)  # type: ignore[arg-type]


def _hold_hours(dt_entry: datetime, dt_exit: datetime) -> float:
    """Wall-clock hold in hours between the entry and exit settlements (ADR A2).

    Computed from integer microseconds (not whole seconds) so it equals the batch
    path's `dt.total_microseconds() / 3.6e9` bit-for-bit, preserving batch/scalar
    parity in the presence of the venue's sub-second settlement jitter.
    """
    delta = dt_exit - dt_entry
    microseconds = delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
    return microseconds / _MICROSECONDS_PER_HOUR


def _require_columns(observations: pl.DataFrame) -> None:
    missing = [c for c in _REQUIRED_COLUMNS if c not in observations.columns]
    if missing:
        raise CarryComputationError(
            f"carry computation requires columns {list(_REQUIRED_COLUMNS)}; missing "
            f"{missing} (got {observations.columns})"
        )


def simulate_trade(
    observations: pl.DataFrame,
    entry_index: int,
    *,
    horizon_events: int,
    cost_model: VenueCostModel,
    entry_taker: bool = True,
    exit_taker: bool = True,
) -> TradePnL:
    """Simulate one delta-neutral carry trade entered at `entry_index`.

    Reads the funding window `range(entry_index+1, entry_index+H+1)` and the entry
    /exit prices at `entry_index` / `entry_index+H`. Costs default to TAKER both
    legs both sides (the conservative locked default). Financing uses the real
    wall-clock hold `dt[exit] - dt[entry]` on the 2N capital base.

    Raises:
      CarryComputationError: on a missing column, a horizon below 1, an
        out-of-range entry (no complete window or no in-range exit price), or a
        null price at the entry or exit event.
    """
    _require_columns(observations)
    height = observations.height
    window = funding_window_indices(entry_index, horizon_events)
    if window.stop > height:
        raise CarryComputationError(
            f"entry_index={entry_index} with horizon_events={horizon_events} needs the "
            f"settlement at index {window.stop - 1} (exit), but the frame has {height} "
            f"rows; valid entries are {valid_entry_range(height, horizon_events)}"
        )
    exit_index = entry_index + horizon_events

    fr = observations["funding_rate"]
    funding_collected = float(
        sum(_cell_float(fr[j], column="funding_rate", index=j) for j in window)
    )

    spot = observations["spot_close"]
    perp = observations["perp_close"]
    spot_e = _cell_float(spot[entry_index], column="spot_close", index=entry_index)
    spot_x = _cell_float(spot[exit_index], column="spot_close", index=exit_index)
    perp_e = _cell_float(perp[entry_index], column="perp_close", index=entry_index)
    perp_x = _cell_float(perp[exit_index], column="perp_close", index=exit_index)
    spot_leg_pnl = (spot_x - spot_e) / spot_e
    perp_leg_pnl = -(perp_x - perp_e) / perp_e
    price_pnl = spot_leg_pnl + perp_leg_pnl

    dt_col = observations["dt"]
    dt_e = dt_col[entry_index]
    dt_x = dt_col[exit_index]
    if dt_e is None or dt_x is None:
        raise CarryComputationError(
            f"carry computation hit a null dt at entry {entry_index} or exit {exit_index}"
        )
    if not (isinstance(dt_e, datetime) and isinstance(dt_x, datetime)):
        raise CarryComputationError(
            f"carry computation read a non-datetime dt at entry {entry_index} / exit {exit_index}"
        )
    hold_hours = _hold_hours(dt_e, dt_x)

    entry_cost = cost_model.entry_cost_fraction(taker=entry_taker)
    exit_cost = cost_model.exit_cost_fraction(taker=exit_taker)
    round_trip_cost = entry_cost + exit_cost
    financing_cost = cost_model.financing_cost_fraction(hold_hours=hold_hours)

    gross = funding_collected + price_pnl
    net_pretax = gross - round_trip_cost - financing_cost

    return TradePnL(
        entry_index=entry_index,
        exit_index=exit_index,
        horizon_events=horizon_events,
        hold_hours=hold_hours,
        funding_collected=funding_collected,
        spot_leg_pnl=spot_leg_pnl,
        perp_leg_pnl=perp_leg_pnl,
        price_pnl=price_pnl,
        entry_cost=entry_cost,
        exit_cost=exit_cost,
        round_trip_cost=round_trip_cost,
        financing_cost=financing_cost,
        gross=gross,
        net_pretax=net_pretax,
    )


def per_interval_pnl(trade: TradePnL, observations: pl.DataFrame) -> list[float]:
    """Decompose a trade into its H per-interval contributions (a conservation harness).

    This exists ONLY to cross-check that the scalar `net_pretax` equals the sum of
    its per-interval pieces (the kill_gate P&L-conservation test); it is NOT the
    PR4b per-period series and does not pre-commit that series' cost placement. The
    once-per-trade entry / exit costs are booked lumpy (entry on the first interval,
    exit on the last, with `price_pnl` realized at the close); the financing flow is
    spread evenly across the H intervals so each contribution is interpretable.

    By construction `sum(per_interval_pnl(trade)) == trade.net_pretax`.
    """
    _require_columns(observations)
    h = trade.horizon_events
    window = funding_window_indices(trade.entry_index, h)
    fr = observations["funding_rate"]
    financing_per_interval = trade.financing_cost / h
    contributions = [
        _cell_float(fr[j], column="funding_rate", index=j) - financing_per_interval for j in window
    ]
    contributions[0] -= trade.entry_cost
    contributions[h - 1] += trade.price_pnl - trade.exit_cost
    return contributions


def simulate_batch(
    observations: pl.DataFrame,
    *,
    horizon_events: int,
    cost_model: VenueCostModel,
    entry_taker: bool = True,
    exit_taker: bool = True,
) -> pl.DataFrame:
    """Vectorised per-trade P&L for every valid entry `i in range(0, height-H)`.

    Polars-vectorised equivalent of `simulate_trade` over all entries (the object
    PR4b runs the always-on null and the cost-sensitivity surface on). Returns one
    row per valid entry, in `entry_index` order, with the entry `dt`, the
    `horizon_dt` (= the CPCV label `dt.shift(-H)`), the P&L terms, and the costs.

    Funding is summed with `rolling_sum(H).shift(-H)` so each row sums exactly the
    H terms `funding_rate[i+1 .. i+H]` (the same window as the scalar path, with
    minimal cancellation); the tail rows where the window runs off the end carry a
    null funding sum and are dropped by the `head(height - H)` slice.

    Raises:
      CarryComputationError: on a missing column, a horizon below 1, a frame with
        no valid entry, or a null price within the valid entry range (a data gap).
    """
    _require_columns(observations)
    if horizon_events < 1:
        raise CarryComputationError(
            f"simulate_batch requires horizon_events >= 1; got {horizon_events}"
        )
    height = observations.height
    entries = valid_entry_range(height, horizon_events)
    if len(entries) == 0:
        raise CarryComputationError(
            f"simulate_batch needs more than horizon_events={horizon_events} rows; got {height}"
        )

    h = horizon_events
    rate_per_year = cost_model.funding_capital_rate * cost_model.capital_multiple
    entry_cost = cost_model.entry_cost_fraction(taker=entry_taker)
    exit_cost = cost_model.exit_cost_fraction(taker=exit_taker)
    round_trip_cost = entry_cost + exit_cost

    spot_e = pl.col("spot_close")
    spot_x = pl.col("spot_close").shift(-h)
    perp_e = pl.col("perp_close")
    perp_x = pl.col("perp_close").shift(-h)
    hold_hours = (
        pl.col("dt").shift(-h) - pl.col("dt")
    ).dt.total_microseconds() / _MICROSECONDS_PER_HOUR

    # Every expression evaluates over the FULL frame (so the forward shift / rolling
    # window read the real later rows), then head() keeps only the valid entries.
    batch = (
        observations.with_row_index("entry_index")
        .with_columns(
            # funding_rate[i+1 .. i+H]: the trailing H-window sum read H rows ahead.
            pl.col("funding_rate")
            .rolling_sum(window_size=h)
            .shift(-h)
            .alias("funding_collected"),
            ((spot_x - spot_e) / spot_e).alias("spot_leg_pnl"),
            (-(perp_x - perp_e) / perp_e).alias("perp_leg_pnl"),
            pl.col("dt").alias("entry_dt"),
            pl.col("dt").shift(-h).alias("horizon_dt"),
            hold_hours.alias("hold_hours"),
        )
        .head(len(entries))
        .with_columns(
            pl.col("entry_index").cast(pl.Int64),
            (pl.col("entry_index").cast(pl.Int64) + h).alias("exit_index"),
            pl.lit(h, dtype=pl.Int64).alias("horizon_events"),
            (pl.col("spot_leg_pnl") + pl.col("perp_leg_pnl")).alias("price_pnl"),
            pl.lit(entry_cost).alias("entry_cost"),
            pl.lit(exit_cost).alias("exit_cost"),
            pl.lit(round_trip_cost).alias("round_trip_cost"),
            (pl.col("hold_hours") * (rate_per_year / 8_760.0)).alias("financing_cost"),
        )
        .with_columns((pl.col("funding_collected") + pl.col("price_pnl")).alias("gross"))
        .with_columns(
            (pl.col("gross") - pl.col("round_trip_cost") - pl.col("financing_cost")).alias(
                "net_pretax"
            )
        )
    )

    # A null within the valid range (tail nulls are already dropped by head() above)
    # is an interior data gap: a missing entry/exit price OR a missing funding rate
    # inside the window. The scalar path raises on both, so the batch must too, or
    # the two paths would diverge on the same input and a gap would silently shrink
    # the trade count when PR4b takes median()/mean() (which skip nulls).
    null_rows = batch.filter(
        pl.col("spot_leg_pnl").is_null()
        | pl.col("perp_leg_pnl").is_null()
        | pl.col("funding_collected").is_null()
    )
    if null_rows.height > 0:
        first_bad = null_rows["entry_index"].to_list()[0]
        raise CarryComputationError(
            f"simulate_batch found {null_rows.height} entries with a null price or funding "
            f"rate within the valid range (first at entry_index={first_bad}); a data gap. "
            f"Warm up / gap-fill the price and funding legs before running the batch."
        )

    return batch.select(
        "entry_index",
        "exit_index",
        "horizon_events",
        "entry_dt",
        "horizon_dt",
        "hold_hours",
        "funding_collected",
        "spot_leg_pnl",
        "perp_leg_pnl",
        "price_pnl",
        "entry_cost",
        "exit_cost",
        "round_trip_cost",
        "financing_cost",
        "gross",
        "net_pretax",
    )


# A signed-mean price_pnl that is a non-trivial fraction of the mean funding flags
# the static-notional proxy as padding the carry (ADR 0003 amendment A3). The
# realized post-ETF ratio is single-digit percent; this is the line above which
# the kill number is treated as contaminated by the proxy rather than clean.
PRICE_PNL_CONTAMINATION_LIMIT = 0.25


def price_pnl_contamination(batch: pl.DataFrame) -> dict[str, float]:
    """Diagnostics for the static-notional `price_pnl` bias (ADR 0003 A3).

    `price_pnl` is a static-notional approximation with a signed (short-gamma)
    bias, so a magnitude bound is not enough: a positive SIGNED mean that is a
    non-trivial fraction of the mean funding means the proxy is padding the carry,
    and the kill number built on `gross = funding + price_pnl` is contaminated. The
    `contamination_ratio` is `|mean(price_pnl)| / |mean(funding_collected)|`;
    `contaminated` is `True` when it meets or exceeds `PRICE_PNL_CONTAMINATION_LIMIT`.

    Returns the median / mean funding, the median `|price_pnl|`, the signed mean
    `price_pnl`, the 95th-percentile `|price_pnl|`, the ratio, and the flag. Raises
    nothing (a diagnostic), but a zero mean funding yields an infinite ratio so a
    degenerate frame cannot read as clean.

    Raises:
      CarryComputationError: when `batch` is empty (no trades to diagnose).
    """
    if batch.height == 0:
        raise CarryComputationError("price_pnl_contamination requires a non-empty batch")
    mean_funding = float(batch["funding_collected"].mean())  # type: ignore[arg-type]
    mean_price = float(batch["price_pnl"].mean())  # type: ignore[arg-type]
    ratio = abs(mean_price) / abs(mean_funding) if mean_funding != 0.0 else float("inf")
    return {
        "median_funding": float(batch["funding_collected"].median()),  # type: ignore[arg-type]
        "mean_funding": mean_funding,
        "median_abs_price_pnl": float(batch["price_pnl"].abs().median()),  # type: ignore[arg-type]
        "mean_price_pnl": mean_price,
        "p95_abs_price_pnl": float(batch["price_pnl"].abs().quantile(0.95)),  # type: ignore[arg-type]
        "contamination_ratio": ratio,
        "contaminated": float(ratio >= PRICE_PNL_CONTAMINATION_LIMIT),
    }
