"""Live network smoke tests for the Study 6 public-domain sources (opt-in: -m network)."""

from __future__ import annotations

from datetime import date

import pytest

from riskpremia.data.sources.ken_french import KenFrenchSource
from riskpremia.data.sources.treasury import FIRST_YEAR, TreasuryParYieldSource

pytestmark = pytest.mark.network


def test_ken_french_daily_factors_live() -> None:
    records = KenFrenchSource().fetch_daily_factors()
    assert len(records) > 20000  # decades of daily factors
    assert records[0].date.year == 1926
    assert records == sorted(records, key=lambda r: r.date)
    # Daily factors are small decimals (a few percent at most on a single day).
    assert all(abs(float(r.mkt_rf)) < 0.5 for r in records[:200])
    assert all(float(r.rf) >= 0.0 for r in records[:200])


def test_treasury_ten_year_live() -> None:
    records = TreasuryParYieldSource().fetch_ten_year(FIRST_YEAR, FIRST_YEAR)
    assert len(records) > 200  # a full year of daily observations
    assert records[0].date.year == FIRST_YEAR
    assert all(date(1990, 1, 1) <= r.date <= date(1990, 12, 31) for r in records)
    # Ten-year par yields are positive decimals, single-digit percent in 1990.
    assert all(0.0 < float(r.ten_year) < 0.2 for r in records)
