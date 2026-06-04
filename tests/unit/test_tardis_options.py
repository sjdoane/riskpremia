"""The Tardis Deribit option-chain loader (ADR 0004 Layer ii data layer): the boundary
parse against a VERBATIM real-row fixture, the microsecond clock, and the backward
as-of snapshot / monotonicity-robust stop / loud completeness logic on synthetic
gzipped data."""

from __future__ import annotations

import csv
import gzip
import io
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from riskpremia.data.boundary import TARDIS_OPTIONS_HEADER, PydanticTardisOptionRow
from riskpremia.data.clock import us_to_utc
from riskpremia.data.errors import VenueFetchError
from riskpremia.data.sources.tardis_options import TardisOptionChainSource

_FIXTURE = Path(__file__).resolve().parents[1] / "data" / "tardis_deribit_options_sample.csv"
_MIDNIGHT_US = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp()) * 1_000_000
_MIN = 60_000_000  # one minute in microseconds


# ----- the microsecond clock -------------------------------------------------

def test_us_to_utc_converts_and_guards() -> None:
    assert us_to_utc(1704067200027000) == datetime(2024, 1, 1, 0, 0, 0, 27000, tzinfo=UTC)
    assert us_to_utc(1727424000000000) == datetime(2024, 9, 27, 8, 0, tzinfo=UTC)  # 08:00 expiry
    with pytest.raises(VenueFetchError, match="MICROSECONDS"):
        us_to_utc(1704067200027)  # a millisecond value passed by mistake
    with pytest.raises(VenueFetchError, match="MICROSECONDS"):
        us_to_utc(1704067200)  # a seconds value


# ----- the boundary against the real-row fixture -----------------------------

def _fixture_rows() -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(_FIXTURE.read_text(encoding="utf-8").splitlines()))
    return rows[0], rows[1:]


def test_real_fixture_header_matches() -> None:
    header, _ = _fixture_rows()
    assert tuple(header) == TARDIS_OPTIONS_HEADER


def test_real_fixture_btc_options_parse() -> None:
    header, rows = _fixture_rows()
    ti_type, ti_sym = header.index("type"), header.index("symbol")
    recs = [
        PydanticTardisOptionRow.from_row(r).to_record("BTC")
        for r in rows
        if r[ti_type] in ("put", "call") and r[ti_sym].startswith("BTC-")
    ]
    assert len(recs) >= 12
    assert any(r.option_type == "put" for r in recs)
    assert any(r.option_type == "call" for r in recs)
    # the SYN.* synthetic-underlying flag is set on real SYN rows and clear on real ones
    assert any(r.synthetic_underlying for r in recs)
    assert any(not r.synthetic_underlying for r in recs)
    # an empty bid or ask becomes None (the illiquid far-OTM rows in the fixture)
    assert any(r.bid_price is None or r.ask_price is None for r in recs)
    # identity + as-of are well-formed
    for r in recs:
        assert r.expiry.tzinfo is not None and r.quote_ts.tzinfo is not None
        assert r.strike > 0 and r.underlying_price > 0
        assert r.instrument.startswith("BTC-")


def test_real_fixture_eth_rows_are_distinguishable() -> None:
    header, rows = _fixture_rows()
    ti_sym = header.index("symbol")
    eth = [r for r in rows if r[ti_sym].startswith("ETH-")]
    assert eth  # the fixture carries ETH rows the BTC loader must filter out
    # they parse under their own currency, proving the currency guard is symbol-based
    rec = PydanticTardisOptionRow.from_row(eth[0]).to_record("ETH")
    assert rec.currency == "ETH"
    with pytest.raises(VenueFetchError, match="not a BTC instrument"):
        PydanticTardisOptionRow.from_row(eth[0]).to_record("BTC")


# ----- the boundary guards ---------------------------------------------------

def _row(**over: str) -> list[str]:
    """A 24-field option row keyed by header name, blanks elsewhere."""
    base = {
        "exchange": "deribit", "symbol": "BTC-5JAN24-43000-C", "timestamp": "1704067200121000",
        "local_timestamp": "1704067200124599", "type": "call", "strike_price": "43000",
        "expiration": "1704441600000000", "mark_price": "0.0185", "underlying_index": "BTC-5JAN24",
        "underlying_price": "42485.82",
    }
    base.update(over)
    return [base.get(name, "") for name in TARDIS_OPTIONS_HEADER]


def test_boundary_empty_quote_fields_become_none() -> None:
    rec = PydanticTardisOptionRow.from_row(_row()).to_record("BTC")  # no bid/ask/iv set
    assert rec.bid_price is None and rec.ask_price is None and rec.mark_iv is None
    assert rec.mark_price is not None  # mark was set


def test_boundary_rejects_bad_type() -> None:
    with pytest.raises(VenueFetchError, match="put/call"):
        PydanticTardisOptionRow.from_row(_row(type="future")).to_record("BTC")


def test_boundary_rejects_nonpositive_and_implausible_strike() -> None:
    with pytest.raises(VenueFetchError, match="strike must be positive"):
        PydanticTardisOptionRow.from_row(_row(strike_price="0")).to_record("BTC")
    with pytest.raises(VenueFetchError, match="implausible"):
        # strike 43 vs underlying 42485 -> ratio ~0.001, a likely column misalignment
        PydanticTardisOptionRow.from_row(_row(strike_price="43")).to_record("BTC")


def test_boundary_rejects_wrong_width() -> None:
    with pytest.raises(VenueFetchError, match="fields"):
        PydanticTardisOptionRow.from_row(["deribit", "BTC-5JAN24-43000-C"])


# ----- the fetch_snapshot as-of / stop / completeness logic ------------------

def _gz(rows: list[list[str]]) -> bytes:
    body = ",".join(TARDIS_OPTIONS_HEADER) + "\n" + "\n".join(",".join(r) for r in rows) + "\n"
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as g:
        g.write(body.encode("utf-8"))
    return buf.getvalue()


def _quote(
    ts_us: int, strike: int, otype: str, *, mark: str = "0.05", under: str = "42000"
) -> list[str]:
    sym = f"BTC-5JAN24-{strike}-{'C' if otype == 'call' else 'P'}"
    return _row(symbol=sym, timestamp=str(ts_us), type=otype, strike_price=str(strike),
                mark_price=mark, underlying_price=under)


def _source(rows: list[list[str]]) -> TardisOptionChainSource:
    payload = _gz(rows)
    return TardisOptionChainSource(open_stream=lambda _url: io.BytesIO(payload))


def _bracketing_chain(ts_us: int) -> list[list[str]]:
    # 8 instruments bracketing underlying 42000 (strikes 30k..50k), all at ts_us.
    rows = []
    for strike in (30000, 38000, 41000, 43000, 45000, 50000):
        rows.append(_quote(ts_us, strike, "call"))
        rows.append(_quote(ts_us, strike, "put"))
    return rows


def test_fetch_snapshot_backward_as_of_last_wins() -> None:
    as_of_us = _MIDNIGHT_US + 60 * _MIN  # offset 60 min
    rows = _bracketing_chain(_MIDNIGHT_US + 30 * _MIN)
    # the same instrument quoted twice before as_of: the LATER (still <= as_of) wins
    rows.append(_quote(_MIDNIGHT_US + 20 * _MIN, 43000, "call", mark="0.10"))
    rows.append(_quote(_MIDNIGHT_US + 40 * _MIN, 43000, "call", mark="0.20"))
    # a quote AFTER as_of (within grace) must NOT be included but must not stop early
    rows.append(_quote(as_of_us + 5_000_000, 99000, "call"))
    # a quote past as_of + grace stops the read
    rows.append(_quote(as_of_us + 120 * _MIN, 100000, "put"))
    snap = _source(rows).fetch_snapshot("BTC", date(2024, 1, 1), min_instruments=4)

    assert snap.as_of == datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
    marks = {q.instrument: q.mark_price for q in snap.quotes}
    assert marks["BTC-5JAN24-43000-C"] == Decimal("0.20")  # last quote <= as_of wins
    # the post-as_of (99000) and past-stop (100000) instruments are excluded
    assert "BTC-5JAN24-99000-C" not in marks
    assert "BTC-5JAN24-100000-P" not in marks
    # sorted deterministically by (expiry, strike, option_type)
    keys = [(q.expiry, q.strike, q.option_type) for q in snap.quotes]
    assert keys == sorted(keys)


def test_fetch_snapshot_keeps_freshest_quote_on_out_of_order_rows() -> None:
    # The file is ordered by local_timestamp; the exchange timestamp is non-monotonic, so
    # the FRESHER quote can appear EARLIER in the file. The max-timestamp quote must win,
    # not the file-last one (post-impl review High).
    as_of_us = _MIDNIGHT_US + 60 * _MIN
    rows = _bracketing_chain(_MIDNIGHT_US + 30 * _MIN)
    rows.append(_quote(_MIDNIGHT_US + 50 * _MIN, 43000, "call", mark="0.50"))  # fresher, earlier
    rows.append(_quote(_MIDNIGHT_US + 45 * _MIN, 43000, "call", mark="0.40"))  # staler, later
    rows.append(_quote(as_of_us + 120 * _MIN, 100000, "put"))  # stop
    snap = _source(rows).fetch_snapshot("BTC", date(2024, 1, 1), min_instruments=4)
    marks = {q.instrument: q.mark_price for q in snap.quotes}
    assert marks["BTC-5JAN24-43000-C"] == Decimal("0.50")  # max-timestamp, not file-last


def test_fetch_snapshot_drops_already_expired_contracts() -> None:
    as_of_us = _MIDNIGHT_US + 60 * _MIN
    rows = _bracketing_chain(_MIDNIGHT_US + 30 * _MIN)
    expired_us = _MIDNIGHT_US - 3600 * 1_000_000  # an expiry one hour before midnight (settled)
    expired = _row(
        symbol="BTC-1JAN24-42000-C", timestamp=str(_MIDNIGHT_US + 30 * _MIN), type="call",
        strike_price="42000", expiration=str(expired_us),
        underlying_index="BTC-1JAN24", underlying_price="42000", mark_price="0.001",
    )
    rows.append(expired)
    rows.append(_quote(as_of_us + 120 * _MIN, 100000, "put"))  # stop
    snap = _source(rows).fetch_snapshot("BTC", date(2024, 1, 1), min_instruments=4)
    assert all(q.instrument != "BTC-1JAN24-42000-C" for q in snap.quotes)
    assert all(q.expiry > snap.as_of for q in snap.quotes)


def test_fetch_snapshot_raises_when_as_of_not_covered() -> None:
    # every row is before as_of, so the file never "reaches" as_of -> truncated guard
    rows = _bracketing_chain(_MIDNIGHT_US + 10 * _MIN)
    with pytest.raises(VenueFetchError, match="did not cover"):
        _source(rows).fetch_snapshot("BTC", date(2024, 1, 1), as_of_offset_minutes=60,
                                     min_instruments=4)


def test_fetch_snapshot_raises_on_thin_chain() -> None:
    as_of_us = _MIDNIGHT_US + 60 * _MIN
    rows = [_quote(_MIDNIGHT_US + 30 * _MIN, 41000, "call"),
            _quote(_MIDNIGHT_US + 30 * _MIN, 43000, "put"),
            _quote(as_of_us + 120 * _MIN, 50000, "put")]  # reaches as_of, then stops
    with pytest.raises(VenueFetchError, match="thin"):
        _source(rows).fetch_snapshot("BTC", date(2024, 1, 1))  # default min_instruments=20


def test_fetch_snapshot_raises_when_strikes_do_not_bracket() -> None:
    as_of_us = _MIDNIGHT_US + 60 * _MIN
    # all strikes far ABOVE the underlying 42000 -> ATM region missing
    rows = [_quote(_MIDNIGHT_US + 30 * _MIN, s, "call") for s in (90000, 95000, 100000, 110000)]
    rows.append(_quote(as_of_us + 120 * _MIN, 120000, "put"))
    with pytest.raises(VenueFetchError, match="bracket"):
        _source(rows).fetch_snapshot("BTC", date(2024, 1, 1), min_instruments=4)


def test_fetch_snapshot_rejects_non_first_of_month() -> None:
    with pytest.raises(VenueFetchError, match="first-of-month"):
        _source([]).fetch_snapshot("BTC", date(2024, 1, 2))


def test_fetch_snapshot_filters_currency_and_noptions() -> None:
    as_of_us = _MIDNIGHT_US + 60 * _MIN
    rows = _bracketing_chain(_MIDNIGHT_US + 30 * _MIN)
    # an ETH option and a future-shaped row must be ignored by a BTC fetch
    eth = _row(symbol="ETH-5JAN24-2100-P", timestamp=str(_MIDNIGHT_US + 30 * _MIN), type="put",
               strike_price="2100", underlying_index="ETH-5JAN24", underlying_price="2291")
    fut = _row(symbol="BTC-PERPETUAL", timestamp=str(_MIDNIGHT_US + 30 * _MIN), type="",
               strike_price="", underlying_index="BTC-PERPETUAL", underlying_price="42000")
    rows = [eth, fut, *rows, _quote(as_of_us + 120 * _MIN, 100000, "put")]
    snap = _source(rows).fetch_snapshot("BTC", date(2024, 1, 1), min_instruments=4)
    assert all(q.currency == "BTC" and q.instrument.startswith("BTC-") for q in snap.quotes)
    assert all(q.option_type in ("put", "call") for q in snap.quotes)
