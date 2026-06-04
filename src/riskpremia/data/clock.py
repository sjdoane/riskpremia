"""The funding-event clock and the CPCV-ready frame construction (ADR 0002).

The determinism heart of the data layer: a single ms-to-UTC chokepoint, the
canonical funding-event frame (sorted, realized-aware deduped, interval-checked),
the backward as-of price join (point-in-time safe), and the per-event label
horizons that feed the vendored event-time-purged CPCV. Stdlib + polars only, no
I/O, no module-level RNG, no set iteration.

The single Decimal-to-Float64 cast happens here when the typed records become the
polars frame: funding rates are exact Decimal at the boundary, then Float64 in the
frame because the analytics stack (PSR/DSR, bootstrap) consumes floats. The cast
is the one documented precision commitment.

Review-locked invariants (docs/research/0001-data-layer-design.md): `dt` is
`pl.Datetime("us", "UTC")` TZ-AWARE everywhere so the CPCV dtype-parity gate
holds; dedup is realized-aware (a benign live re-publish collapses, two settled
rows that disagree raise); the interval check hard-raises only on a null interval
or an order-of-magnitude mismatch, because Binance early history is genuinely
irregular; the label horizon is the i+H-th settlement instant with the trailing H
rows dropped from frame and horizons together.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import polars as pl

from riskpremia.data.errors import FundingIntervalError, VenueFetchError
from riskpremia.data.records import FundingRecord, MarkPriceRecord, SpotPriceRecord

# UTC (datetime.UTC, the stdlib singleton) is the single timezone the whole layer
# normalizes to; crypto trades 24/7 with no market calendar.

DT_DTYPE = pl.Datetime("us", "UTC")
"""The canonical event-timestamp dtype. Pinned so the observation frame `dt` and
the `label_horizons` series share an identical dtype (the cv.py parity gate
rejects a mismatch, including tz-aware vs naive)."""

SPOT_ETF_LAUNCH = datetime(2024, 1, 11, tzinfo=UTC)
"""The US spot bitcoin ETF launch (2024-01-11), the single source of truth for
the pre-ETF / post-ETF regime boundary the decay headline and the held-out kill
gate split on. Pinned here so no module hardcodes the date independently."""

CRYPTO_ANNUALIZATION_DAYS = 365.0
"""The single source of truth for the annualization day-count. Crypto trades 24/7
with no market calendar, and Deribit annualizes DVOL on a 365-day basis (verified:
the expected daily move is DVOL / sqrt(365)), so the realized-variance estimator
MUST use the same 365 to match implied (a 252-vs-365 mismatch is a ~1.45x error on
the variance premium). Both the implied and realized legs read this constant."""

_MS_LOWER = 1_000_000_000_000
"""Epoch-ms lower guard (about 2001-09); a value below this is almost certainly
seconds, not milliseconds, and is rejected rather than silently mis-scaled."""
_MS_UPPER = 100_000_000_000_000
"""Epoch-ms upper guard (about 5138); a value above this is malformed."""

_GROSS_INTERVAL_LOW = 0.5
_GROSS_INTERVAL_HIGH = 2.0
"""The in-band tolerance for the median-gap vs stamped-interval ratio. Outside
[0.5, 2.0] is an order-of-magnitude mislabel and raises; inside is a recorded
diagnostic, not an error (Binance early history is about 3 per day, not 8h)."""


def ms_to_utc(ms: int) -> datetime:
    """Convert an epoch-millisecond integer to a tz-aware UTC datetime.

    The single ms-to-UTC normalizer the whole layer routes through. Range-guards
    against an epoch passed in seconds (a common vendor-doc trap) rather than
    silently producing a 1970-era timestamp.

    Raises:
      VenueFetchError: when `ms` is outside the plausible epoch-millisecond range.
    """
    if not (_MS_LOWER <= ms < _MS_UPPER):
        raise VenueFetchError(
            f"ms_to_utc expects epoch MILLISECONDS in [{_MS_LOWER}, {_MS_UPPER}); "
            f"got {ms} (a value this small is likely seconds, not ms)"
        )
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def _funding_records_to_frame(records: Sequence[FundingRecord]) -> pl.DataFrame:
    """Build the raw (pre-normalization) funding frame from typed records.

    This is the single Decimal-to-Float64 cast site (`funding_rate`, `premium`).
    Adds a stable `_ingest_idx` so the later dedup is order-deterministic.
    """
    if len(records) == 0:
        raise VenueFetchError("_funding_records_to_frame requires at least one record")
    return pl.DataFrame(
        {
            "dt": [r.funding_ts for r in records],
            "venue": [r.instrument.venue for r in records],
            "symbol": [r.instrument.symbol for r in records],
            "canonical": [r.instrument.canonical for r in records],
            "funding_rate": [float(r.funding_rate) for r in records],
            "funding_interval_hours": [r.funding_interval_hours for r in records],
            "premium": [None if r.premium is None else float(r.premium) for r in records],
            "realized": [r.realized for r in records],
            "_ingest_idx": list(range(len(records))),
        },
        schema={
            "dt": DT_DTYPE,
            "venue": pl.Utf8,
            "symbol": pl.Utf8,
            "canonical": pl.Utf8,
            "funding_rate": pl.Float64,
            "funding_interval_hours": pl.Int32,
            "premium": pl.Float64,
            "realized": pl.Boolean,
            "_ingest_idx": pl.Int64,
        },
    )


def normalize_funding_frame(records: Sequence[FundingRecord]) -> pl.DataFrame:
    """Build the canonical, sorted, deduped, interval-checked funding frame.

    One instrument per call (cross-venue joins happen later). Steps: cast records
    to the frame, reject a multi-instrument mix, raise on any null interval,
    detect settled-row conflicts (two `realized` rows at one stamp with differing
    rates), dedup realized-aware (prefer the settled row, then the earliest
    ingest), sort by `dt`, and hard-raise only on an order-of-magnitude
    interval-vs-gap mismatch.

    Returns a frame with columns `dt, venue, symbol, canonical, funding_rate,
    funding_interval_hours, premium, realized`, sorted by `dt` ascending. The
    `_ingest_idx` helper column is dropped.

    Raises:
      VenueFetchError: on a multi-instrument frame or a settled-row rate conflict.
      FundingIntervalError: on a null interval or a gross interval mismatch.
    """
    frame = _funding_records_to_frame(records)

    distinct_instruments = frame.select("venue", "symbol").unique().height
    if distinct_instruments != 1:
        raise VenueFetchError(
            f"normalize_funding_frame is single-instrument; got "
            f"{distinct_instruments} distinct (venue, symbol) pairs"
        )

    if frame["funding_interval_hours"].null_count() > 0:
        raise FundingIntervalError(
            "normalize_funding_frame found a null funding_interval_hours; the "
            "interval must be carried as data on every row"
        )

    # Settled-row conflict: two realized rows at the same stamp with differing
    # rates is genuine corruption (a benign re-publish has an identical rate).
    realized = frame.filter(pl.col("realized"))
    conflicts = (
        realized.group_by("dt")
        .agg(pl.col("funding_rate").n_unique().alias("_n"))
        .filter(pl.col("_n") > 1)
    )
    if conflicts.height > 0:
        bad_dt = conflicts.sort("dt")["dt"].to_list()[0]
        raise VenueFetchError(
            f"normalize_funding_frame found conflicting settled funding rates at "
            f"the same stamp (first offending dt={bad_dt}); refusing to dedup a "
            f"genuine vendor inconsistency"
        )

    # Realized-aware dedup: prefer the settled row, then the earliest ingest, so
    # a live re-fetch that refines an estimate to a final value keeps the final.
    deduped = (
        frame.sort(["dt", "realized", "_ingest_idx"], descending=[False, True, False])
        .unique(subset=["dt"], keep="first", maintain_order=True)
        .sort("dt")
        .drop("_ingest_idx")
    )

    _check_interval_not_gross(deduped)
    return deduped


def _scalar_float(value: Any) -> float | None:
    """Coerce a polars scalar aggregate (a numeric value or None) to float or None.

    Polars scalar reducers (`min`, `median`, `max`, `mode().min()`) are typed as a
    broad `int | float | Decimal | ... | None` union; this narrows the numeric
    runtime value to `float` at the single point of use, keeping mypy --strict
    clean without scattering casts.
    """
    if value is None:
        return None
    return float(value)


def _median_gap_hours(frame: pl.DataFrame) -> float | None:
    """The median gap in hours between consecutive funding stamps (None if < 2)."""
    if frame.height < 2:
        return None
    gaps = frame["dt"].diff().dt.total_seconds().drop_nulls() / 3600.0
    return _scalar_float(gaps.median())


def _check_interval_not_gross(frame: pl.DataFrame) -> None:
    """Hard-raise only when the median inter-event gap is an order of magnitude
    off the stamped interval (a venue/interval mislabel). Smaller mismatches are
    expected on irregular early history and are left to the diagnostic."""
    if frame.height < 3:
        return
    stamped = _scalar_float(frame["funding_interval_hours"].mode().min())
    if stamped is None or stamped <= 0:
        return
    median_gap = _median_gap_hours(frame)
    if median_gap is None or median_gap <= 0:
        return
    ratio = median_gap / stamped
    if not (_GROSS_INTERVAL_LOW <= ratio <= _GROSS_INTERVAL_HIGH):
        raise FundingIntervalError(
            f"funding interval mislabel: stamped {stamped:.0f}h but the median gap "
            f"is {median_gap:.2f}h (ratio {ratio:.2f} outside "
            f"[{_GROSS_INTERVAL_LOW}, {_GROSS_INTERVAL_HIGH}])"
        )


def funding_interval_diagnostics(frame: pl.DataFrame) -> dict[str, float]:
    """Report the stamped interval, the median observed gap, and the in-band
    mismatch fraction, for the committed derived artifact (the diagnostic the
    interval check deliberately does NOT raise on)."""
    if frame.height < 2:
        return {"stamped_interval_hours": 0.0, "median_gap_hours": 0.0, "mismatch_fraction": 0.0}
    stamped = _scalar_float(frame["funding_interval_hours"].mode().min()) or 0.0
    gaps_hours = frame["dt"].diff().dt.total_seconds().drop_nulls() / 3600.0
    median_gap = _median_gap_hours(frame) or 0.0
    # Fraction of gaps more than 25% off the stamped interval.
    n_gaps = gaps_hours.len()
    off = gaps_hours.filter((gaps_hours - stamped).abs() > 0.25 * stamped).len()
    mismatch_fraction = off / n_gaps if n_gaps else 0.0
    return {
        "stamped_interval_hours": stamped,
        "median_gap_hours": median_gap,
        "mismatch_fraction": mismatch_fraction,
    }


def marks_frame(records: Sequence[MarkPriceRecord]) -> pl.DataFrame:
    """Build the perp-mark price frame (`period_end_ts`, `mark_close`) for the join.

    Deduped on `period_end_ts` (the as-of join precondition) and sorted; the
    Decimal mark price is cast to Float64 here, the documented price cast site.
    """
    if len(records) == 0:
        return pl.DataFrame(schema={"period_end_ts": DT_DTYPE, "mark_close": pl.Float64})
    frame = pl.DataFrame(
        {
            "period_end_ts": [r.period_end_ts for r in records],
            "mark_close": [float(r.mark_close) for r in records],
        },
        schema={"period_end_ts": DT_DTYPE, "mark_close": pl.Float64},
    )
    return frame.unique(
        subset=["period_end_ts"], keep="last", maintain_order=True
    ).sort("period_end_ts")


def spot_frame(records: Sequence[SpotPriceRecord]) -> pl.DataFrame:
    """Build the spot reference frame (`period_end_ts`, `close`) for the join.

    Deduped on `period_end_ts` and sorted; same single Float64 cast. The matched
    `(spot_venue, spot_symbol, quote)` provenance lives on the records; this frame
    carries only what the basis computation needs.
    """
    if len(records) == 0:
        return pl.DataFrame(schema={"period_end_ts": DT_DTYPE, "close": pl.Float64})
    frame = pl.DataFrame(
        {
            "period_end_ts": [r.period_end_ts for r in records],
            "close": [float(r.close) for r in records],
        },
        schema={"period_end_ts": DT_DTYPE, "close": pl.Float64},
    )
    return frame.unique(
        subset=["period_end_ts"], keep="last", maintain_order=True
    ).sort("period_end_ts")


def build_observation_frame(
    funding: pl.DataFrame,
    marks: pl.DataFrame | None = None,
    spot: pl.DataFrame | None = None,
    *,
    mark_tolerance: str | None = None,
    spot_tolerance: str | None = None,
) -> pl.DataFrame:
    """Join perp mark and spot prices onto each funding event (PIT-safe as-of).

    Each funding event at `dt` carries the LAST mark/spot close at or before `dt`
    via a backward `join_asof` (structurally incapable of pulling a future
    price). `marks`/`spot` may be None (the columns are then null), which is what
    the PR1 contract test uses. `mark_tolerance`/`spot_tolerance` (e.g. "8h")
    reject a join that reaches too far back across a data gap.

    Returns the CPCV-ready frame sorted by `dt`: `dt, venue, symbol, canonical,
    funding_rate, funding_interval_hours, perp_close, spot_close, basis`. `basis`
    is `(perp_close - spot_close) / spot_close`, null where either leg is null.
    `perp_close` is the MARK price (funding settles on mark, not trade price).

    Precondition: each price frame has a unique `period_end_ts`. Kline/spot closes
    are unique by construction, so the PR2 price sources dedup at the source; a
    duplicate close stamp would make the backward `join_asof` tie-break on input
    order, which this hot path deliberately does not guard (the source does).
    """
    obs = funding.sort("dt")

    if marks is not None:
        m = marks.sort("period_end_ts").select(
            pl.col("period_end_ts").alias("_m_ts"),
            pl.col("mark_close").cast(pl.Float64).alias("perp_close"),
        )
        obs = obs.join_asof(
            m, left_on="dt", right_on="_m_ts", strategy="backward", tolerance=mark_tolerance
        )
    else:
        obs = obs.with_columns(pl.lit(None, dtype=pl.Float64).alias("perp_close"))

    if spot is not None:
        s = spot.sort("period_end_ts").select(
            pl.col("period_end_ts").alias("_s_ts"),
            pl.col("close").cast(pl.Float64).alias("spot_close"),
        )
        obs = obs.join_asof(
            s, left_on="dt", right_on="_s_ts", strategy="backward", tolerance=spot_tolerance
        )
    else:
        obs = obs.with_columns(pl.lit(None, dtype=pl.Float64).alias("spot_close"))

    obs = obs.with_columns(
        ((pl.col("perp_close") - pl.col("spot_close")) / pl.col("spot_close")).alias("basis")
    )
    return obs.select(
        "dt",
        "venue",
        "symbol",
        "canonical",
        "funding_rate",
        "funding_interval_hours",
        "perp_close",
        "spot_close",
        "basis",
    ).sort("dt")


def make_label_horizons(
    observations: pl.DataFrame, *, horizon_events: int
) -> tuple[pl.DataFrame, pl.Series]:
    """Return (trimmed observations, label_horizons) for the vendored CPCV.

    The carry label of the event at row i is the funding earned over the next
    `horizon_events` (H) intervals; that return is fully observed once the i+H-th
    funding settles, so the label horizon is `dt.shift(-H)` (the i+H-th settlement
    instant). The trailing H rows have no complete forward window and are dropped
    from BOTH the frame and the horizons together, so there is no partial label
    and the cv.py length-parity / dtype / non-null gate holds.

    Raises:
      ValueError: when `horizon_events < 1` or the frame has at most H rows.
      VenueFetchError: when the constructed horizons violate the CPCV contract
        (dtype mismatch, null, or length parity), a should-never-happen guard
        that fails loudly rather than letting cv.py raise downstream.
    """
    if horizon_events < 1:
        raise ValueError(f"make_label_horizons requires horizon_events >= 1; got {horizon_events}")
    if observations.height > 0 and not observations["dt"].is_sorted():
        # shift(-H) assumes ascending order; an unsorted frame would silently
        # produce wrong horizons (a partial-lookahead foot-gun on a public fn).
        raise VenueFetchError(
            "make_label_horizons requires observations sorted by dt ascending; "
            "build_observation_frame returns a sorted frame"
        )
    n = observations.height
    if n <= horizon_events:
        raise ValueError(
            f"make_label_horizons requires more than horizon_events rows; got "
            f"{n} rows for horizon_events={horizon_events}"
        )
    keep = n - horizon_events
    horizons_full = observations["dt"].shift(-horizon_events)
    trimmed = observations.head(keep)
    horizons = horizons_full.head(keep).rename("label_horizon")

    if horizons.dtype != trimmed["dt"].dtype:
        raise VenueFetchError(
            f"label horizons dtype {horizons.dtype} does not match dt dtype "
            f"{trimmed['dt'].dtype}; the CPCV parity gate would reject this"
        )
    if horizons.null_count() != 0:
        raise VenueFetchError(
            f"label horizons carry {horizons.null_count()} nulls after the trailing-H drop"
        )
    if horizons.len() != trimmed.height:
        raise VenueFetchError(
            f"label horizons length {horizons.len()} != observations height {trimmed.height}"
        )
    return trimmed, horizons


def label_horizon_gap_diagnostics(
    observations: pl.DataFrame, horizons: pl.Series, *, horizon_events: int
) -> dict[str, float]:
    """Report the max wall-clock span of any H-event horizon vs the nominal
    H * interval, so outage-straddling labels (a missing funding event makes a
    shift(-H) span more real time than intended) are visible in the artifact."""
    if observations.height == 0:
        return {"max_span_hours": 0.0, "nominal_span_hours": 0.0, "span_ratio": 0.0}
    spans_hours = (horizons - observations["dt"]).dt.total_seconds() / 3600.0
    max_span = _scalar_float(spans_hours.max()) or 0.0
    interval = _scalar_float(observations["funding_interval_hours"].mode().min()) or 0.0
    nominal = interval * horizon_events
    return {
        "max_span_hours": max_span,
        "nominal_span_hours": nominal,
        "span_ratio": (max_span / nominal) if nominal else 0.0,
    }
