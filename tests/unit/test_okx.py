"""OKX live funding source, offline (injected http_get + now_fn, no network)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from riskpremia.data.boundary import PydanticOKXFundingRow
from riskpremia.data.clock import ms_to_utc
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.records import InstrumentId
from riskpremia.data.sources.okx import OKXSource

_BASE_MS = 1780531200000  # 2026-06-04 00:00 UTC (a real OKX fundingTime)
_STEP_MS = 8 * 3600 * 1000


def _okx_rows(n: int = 10) -> list[dict[str, str]]:
    return [
        {
            "fundingTime": str(_BASE_MS - i * _STEP_MS),
            "realizedRate": "0.0001",
            "fundingRate": "0.0001",
            "method": "current_period",
            "instType": "SWAP",
            "formulaType": "withRate",
        }
        for i in range(n)
    ]


def _fake_get(rows: list[dict[str, str]], per_page: int = 100):
    def get(path: str) -> dict[str, object]:
        after = int(path.split("after=")[1].split("&")[0])
        older = sorted(
            (r for r in rows if int(r["fundingTime"]) < after),
            key=lambda r: -int(r["fundingTime"]),
        )
        return {"data": older[:per_page]}

    return get


def test_realized_gate_keeps_settled_drops_future_and_invalid() -> None:
    inst = InstrumentId.of("okx", "BTC-USDT-SWAP")
    now_ms = _BASE_MS + _STEP_MS  # strictly after the latest settled event

    def rec(**fields: object):
        return PydanticOKXFundingRow(**fields).to_record(inst, now_ms, 8)

    settled = rec(
        fundingTime=_BASE_MS, realizedRate="0.0001", fundingRate="0.0001",
        method="current_period", instType="SWAP",
    )
    assert settled is not None
    assert settled.funding_rate == Decimal("0.0001")  # uses realizedRate, not fundingRate
    assert settled.funding_ts == ms_to_utc(_BASE_MS)
    assert settled.realized is True and settled.premium is None
    assert rec(fundingTime=now_ms + 1, realizedRate="0.0001", method="current_period") is None
    assert rec(fundingTime=_BASE_MS, method="current_period") is None  # missing realizedRate
    assert rec(fundingTime=_BASE_MS, realizedRate="0.0001", method="next_period") is None


def test_okx_boundary_ignores_extra_fields() -> None:
    # extra="ignore": OKX's instType/formulaType/instId must not crash the row.
    row = PydanticOKXFundingRow(
        fundingTime=_BASE_MS, realizedRate="0.0001", method="current_period",
        instType="SWAP", instId="BTC-USDT-SWAP", formulaType="withRate",
    )
    assert row.fundingTime == _BASE_MS


def test_fetch_funding_windows_single_page() -> None:
    now = datetime(2026, 6, 5, tzinfo=UTC)
    src = OKXSource(now_fn=lambda: now, http_get=_fake_get(_okx_rows(10)))
    start = datetime(2026, 6, 2, tzinfo=UTC)
    end = datetime(2026, 6, 5, tzinfo=UTC)
    recs = src.fetch_funding("BTC-USDT-SWAP", start, end)
    assert len(recs) == 7  # 06-02 00:00 .. 06-04 16:00 at 8h
    assert all(start <= r.funding_ts < end for r in recs)
    assert all(r.funding_interval_hours == 8 and r.realized for r in recs)
    assert all(r.funding_rate == Decimal("0.0001") for r in recs)


def test_fetch_funding_paginates_multiple_pages() -> None:
    now = datetime(2026, 6, 5, tzinfo=UTC)
    src = OKXSource(now_fn=lambda: now, http_get=_fake_get(_okx_rows(10), per_page=3))
    # wide window so the loop must page through all 10 rows in chunks of 3
    recs = src.fetch_funding(
        "BTC-USDT-SWAP", datetime(2026, 5, 30, tzinfo=UTC), datetime(2026, 6, 5, tzinfo=UTC)
    )
    assert len(recs) == 10
    # strictly descending fetch order, all unique
    assert len({r.funding_ts for r in recs}) == 10


def test_fetch_funding_rejects_bad_window() -> None:
    src = OKXSource(
        now_fn=lambda: datetime(2026, 6, 5, tzinfo=UTC), http_get=_fake_get(_okx_rows())
    )
    same = datetime(2026, 6, 5, tzinfo=UTC)
    with pytest.raises(VenueFetchError):
        src.fetch_funding("BTC-USDT-SWAP", same, same)


def test_retention_floor_returns_oldest() -> None:
    rows = _okx_rows(10)
    now = datetime(2026, 6, 5, tzinfo=UTC)
    src = OKXSource(now_fn=lambda: now, http_get=_fake_get(rows, per_page=3))
    floor = src.retention_floor("BTC-USDT-SWAP")
    assert floor == ms_to_utc(min(int(r["fundingTime"]) for r in rows))


def test_available_months_spans_retention_window() -> None:
    now = datetime(2026, 6, 5, tzinfo=UTC)
    src = OKXSource(now_fn=lambda: now, http_get=_fake_get(_okx_rows(10), per_page=3))
    # 10 rows of 8h from 2026-06-04 back to 2026-06-01 -> the single month June
    assert src.available_months("BTC-USDT-SWAP") == ("2026-06",)
