"""Unit tests for the Kenneth French and US Treasury parsers (Study 6, no network)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from riskpremia.data.errors import VenueFetchError
from riskpremia.data.sources.ken_french import parse_daily_factors
from riskpremia.data.sources.treasury import parse_year_csv

_FRENCH_SAMPLE = """This file was created by using the 202604 CRSP database.
The Tbill return is the simple daily rate.

,Mkt-RF,SMB,HML,RF
19260701,    0.09,   -0.25,   -0.27,    0.01
19260702,    0.45,   -0.33,   -0.06,    0.01
19260706,    0.17,    0.30,   -0.39,    0.01

  Copyright 2026 Kenneth R. French
"""

_TREASURY_SAMPLE = (
    'Date,"1 Mo","3 Mo","2 Yr","10 Yr","30 Yr"\n'
    "01/02/2024,5.50,5.45,4.33,3.95,4.20\n"
    "01/03/2024,5.51,5.46,4.38,3.99,4.25\n"
)


def test_french_parses_percent_to_decimal() -> None:
    records = parse_daily_factors(_FRENCH_SAMPLE)
    assert len(records) == 3
    first = records[0]
    assert first.date == date(1926, 7, 1)
    assert first.mkt_rf == Decimal("0.09") / Decimal("100")
    assert first.rf == Decimal("0.01") / Decimal("100")
    # Market total return is Mkt-RF + RF.
    assert first.market_total_return == (Decimal("0.09") + Decimal("0.01")) / Decimal("100")


def test_french_skips_preamble_and_copyright() -> None:
    records = parse_daily_factors(_FRENCH_SAMPLE)
    assert [r.date for r in records] == [
        date(1926, 7, 1),
        date(1926, 7, 2),
        date(1926, 7, 6),
    ]


def test_french_missing_marker_raises() -> None:
    bad = _FRENCH_SAMPLE.replace("19260701,    0.09,   -0.25,   -0.27,    0.01",
                                 "19260701,  -99.99,   -0.25,   -0.27,    0.01")
    with pytest.raises(VenueFetchError):
        parse_daily_factors(bad)


def test_french_no_rows_raises() -> None:
    with pytest.raises(VenueFetchError):
        parse_daily_factors("no header here\njust text\n")


def test_treasury_locates_ten_year_by_name() -> None:
    records = parse_year_csv(_TREASURY_SAMPLE, year=2024)
    assert len(records) == 2
    assert records[0].date == date(2024, 1, 2)
    assert records[0].ten_year == Decimal("3.95") / Decimal("100")
    assert records[1].ten_year == Decimal("3.99") / Decimal("100")


def test_treasury_column_position_independent() -> None:
    # Reorder columns; the ten-year must still be found by header name.
    reordered = (
        'Date,"10 Yr","3 Mo","30 Yr"\n'
        "01/02/2024,3.95,5.45,4.20\n"
    )
    records = parse_year_csv(reordered, year=2024)
    assert records[0].ten_year == Decimal("3.95") / Decimal("100")


def test_treasury_missing_ten_year_column_raises() -> None:
    no_ten = 'Date,"3 Mo","30 Yr"\n01/02/2024,5.45,4.20\n'
    with pytest.raises(VenueFetchError):
        parse_year_csv(no_ten, year=2024)


def test_treasury_wrong_year_raises() -> None:
    with pytest.raises(VenueFetchError):
        parse_year_csv(_TREASURY_SAMPLE, year=2025)


def test_treasury_non_positive_yield_raises() -> None:
    bad = 'Date,"10 Yr"\n01/02/2024,0.00\n'
    with pytest.raises(VenueFetchError):
        parse_year_csv(bad, year=2024)
