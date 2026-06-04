"""Deribit DVOL boundary + source, offline (monkeypatched http_get). The live
end-to-end pull is the network-marked integration test."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from riskpremia.data.boundary import PydanticDeribitDvolRow
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.sources.deribit_dvol import DeribitDVOLSource

_D0_MS = 1_672_531_200_000  # 2023-01-01 UTC
_DAY_MS = 86_400_000


def test_dvol_boundary_from_array_and_to_record() -> None:
    rec = PydanticDeribitDvolRow.from_array([_D0_MS, 80.0, 85.0, 78.0, 82.0]).to_record("BTC")
    assert rec.currency == "BTC"
    assert rec.ts == datetime(2023, 1, 1, tzinfo=UTC)
    assert rec.close == Decimal("82.0")


def test_dvol_boundary_rejects_bad_rows() -> None:
    with pytest.raises(VenueFetchError, match="5-element"):
        PydanticDeribitDvolRow.from_array([_D0_MS, 80.0, 85.0, 78.0])  # too short
    with pytest.raises(VenueFetchError, match="positive"):
        PydanticDeribitDvolRow.from_array([_D0_MS, 0.0, 85.0, 78.0, 82.0]).to_record("BTC")
    with pytest.raises(VenueFetchError, match="inconsistent"):
        # close above high
        PydanticDeribitDvolRow.from_array([_D0_MS, 80.0, 85.0, 78.0, 99.0]).to_record("BTC")


def _row(day: int) -> list[float]:
    return [float(_D0_MS + day * _DAY_MS), 80.0, 85.0, 78.0, 82.0]


def test_dvol_source_parses_dedups_and_filters_half_open() -> None:
    page: dict[str, Any] = {"result": {"data": [_row(i) for i in range(5)], "continuation": None}}
    src = DeribitDVOLSource(http_get=lambda _path: page)
    recs = src.fetch_dvol("BTC", datetime(2023, 1, 1, tzinfo=UTC), datetime(2023, 1, 4, tzinfo=UTC))
    assert [r.ts.day for r in recs] == [1, 2, 3]  # Jan 4 excluded (half-open end)


def test_dvol_source_chunks_a_wide_range_deterministically() -> None:
    # A range wider than the ~1000-point cap (900-day chunks for 1D) must be fetched
    # in multiple deterministic sub-windows with strictly increasing start cursors.
    seen_starts: list[int] = []

    def http_get(path: str) -> dict[str, Any]:
        start_ms = int(path.split("start_timestamp=")[1].split("&")[0])
        seen_starts.append(start_ms)
        return {
            "result": {"data": [[float(start_ms), 80.0, 85.0, 78.0, 82.0]], "continuation": None}
        }

    src = DeribitDVOLSource(http_get=http_get)
    recs = src.fetch_dvol("BTC", datetime(2021, 1, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC))
    assert len(seen_starts) >= 3  # ~2191 days / 900 -> 3 chunks
    assert seen_starts == sorted(seen_starts)  # forward, deterministic
    assert len(set(seen_starts)) == len(seen_starts)  # no repeated cursor
    assert len(recs) == len(seen_starts)  # one distinct day per chunk, deduped + in range


def test_dvol_source_guards() -> None:
    src = DeribitDVOLSource(http_get=lambda _p: {"result": {"data": [], "continuation": None}})
    with pytest.raises(VenueFetchError, match="start < end"):
        src.fetch_dvol("BTC", datetime(2023, 1, 2, tzinfo=UTC), datetime(2023, 1, 1, tzinfo=UTC))
    with pytest.raises(VenueFetchError, match="resolution"):
        src.fetch_dvol(
            "BTC",
            datetime(2023, 1, 1, tzinfo=UTC),
            datetime(2023, 1, 2, tzinfo=UTC),
            resolution="7D",
        )
