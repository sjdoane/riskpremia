"""The Tardis Deribit option-chain loader against LIVE data (network-marked, skipped
by default; run with `-m network`). The reproducibility proof for the Layer-ii data
layer: stream a real first-of-month BTC chain, bounded (never the full ~1.8 GB), and
confirm the backward as-of snapshot is point-in-time honest (no quote later than the
entry instant) and brackets the underlying."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from riskpremia.data.sources.tardis_options import TardisOptionChainSource

pytestmark = pytest.mark.network


def test_fetch_real_btc_first_of_month_snapshot() -> None:
    # A short as-of offset keeps the streamed slice small (~1/72 of the day) while still
    # covering the liquid ATM region; the loader stops as soon as it passes the cutoff.
    snap = TardisOptionChainSource().fetch_snapshot(
        "BTC", date(2024, 1, 1), as_of_offset_minutes=20
    )
    assert snap.currency == "BTC"
    assert snap.as_of == datetime(2024, 1, 1, 0, 20, tzinfo=UTC)
    assert len(snap.quotes) >= 50  # a real BTC chain at the top of the day is hundreds

    has_put = any(q.option_type == "put" for q in snap.quotes)
    has_call = any(q.option_type == "call" for q in snap.quotes)
    assert has_put and has_call

    strikes = [float(q.strike) for q in snap.quotes]
    unders = sorted(float(q.underlying_price) for q in snap.quotes)
    mid = unders[len(unders) // 2]
    assert min(strikes) < mid < max(strikes)  # the ATM region is present

    for q in snap.quotes:
        assert q.strike > 0 and q.underlying_price > 0
        assert q.expiry > snap.as_of  # only not-yet-expired options
        assert q.quote_ts <= snap.as_of  # backward as-of: never a future quote (no look-ahead)
        assert q.instrument.startswith("BTC-")

    print(  # noqa: T201 (the PR5c real-data exhibit)
        f"\n[Tardis BTC {snap.snapshot_date} as_of {snap.as_of}] {len(snap.quotes)} instruments, "
        f"underlying ~{mid:.0f}, strikes {min(strikes):.0f}..{max(strikes):.0f}, "
        f"{sum(q.synthetic_underlying for q in snap.quotes)} on a SYN.* index"
    )
