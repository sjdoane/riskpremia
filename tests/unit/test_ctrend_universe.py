"""The CTREND universe layer, offline (synthetic panels): the PIT / survivorship spine.

Attacks the load-bearing honesty properties: point-in-time liquidity selection (no
look-ahead), the tie-break direction, min-history gating, the gap-safe weekly return, the
explicit forward return, and the losslessness of the committed-panel trim.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import polars as pl
import pytest

from riskpremia.ctrend.errors import CtrendError
from riskpremia.ctrend.universe import (
    build_daily_panel,
    build_weekly_panel,
    classify_exclusion,
    eligible_pairs,
    ever_eligible_symbols,
    excluded_symbols,
    is_leveraged_token,
    listed_bases_of,
    pit_eligible,
    tradeable_universe,
    trim_daily_to,
)
from riskpremia.data.records import InstrumentId, SpotKlineRecord


def _rec(
    symbol: str,
    d: date,
    close: float,
    volume: float,
    high: float | None = None,
    low: float | None = None,
) -> SpotKlineRecord:
    c = Decimal(str(close))
    return SpotKlineRecord(
        instrument=InstrumentId.of("binance_vision", symbol),
        period_end_ts=datetime(d.year, d.month, d.day, tzinfo=UTC),
        close=c,
        high=c if high is None else Decimal(str(high)),
        low=c if low is None else Decimal(str(low)),
        quote_volume=Decimal(str(volume)),
    )


def _week(symbol: str, monday: date, close: float, volume: float) -> list[SpotKlineRecord]:
    """Seven daily bars (Mon..Sun) with the given weekly close + total dollar volume.

    All seven closes equal `close` (so the Sunday close == the weekly close), and the full
    `volume` sits on the Monday bar with 0 elsewhere (so the weekly sum == `volume`).
    """
    out: list[SpotKlineRecord] = []
    for i in range(7):
        out.append(_rec(symbol, monday + timedelta(days=i), close, volume if i == 0 else 0.0))
    return out


_MON = date(2024, 1, 1)  # a Monday


def _weeks(symbol: str, specs: list[tuple[int, float, float]]) -> list[SpotKlineRecord]:
    """`specs` is a list of (week_offset_from_MON, close, volume); emits the daily bars."""
    out: list[SpotKlineRecord] = []
    for offset, close, volume in specs:
        out.extend(_week(symbol, _MON + timedelta(weeks=offset), close, volume))
    return out


# ----- the exclusion filter --------------------------------------------------


def test_exclusion_filter_stables_leveraged_and_real_coins() -> None:
    symbols = [
        "BTCUSDT", "ETHUSDT", "JUPUSDT", "USDCUSDT", "TUSDUSDT", "EURUSDT",
        "BTCUPUSDT", "BTCDOWNUSDT", "ETHBULLUSDT", "ETHBEARUSDT", "BTC3LUSDT", "1000SHIBUSDT",
    ]
    bases = listed_bases_of(symbols)
    # real coins kept (JUP ends in UP but "J" is not a listed base; 1000SHIB is an instrument)
    assert classify_exclusion("BTCUSDT", bases) is None
    assert classify_exclusion("JUPUSDT", bases) is None
    assert classify_exclusion("1000SHIBUSDT", bases) is None
    # stablecoins / fiat excluded
    assert classify_exclusion("USDCUSDT", bases) == "stablecoin_or_fiat"
    assert classify_exclusion("TUSDUSDT", bases) == "stablecoin_or_fiat"
    assert classify_exclusion("EURUSDT", bases) == "stablecoin_or_fiat"
    # leveraged tokens excluded (UP/DOWN need the listed-base test; BTC is listed)
    assert classify_exclusion("BTCUPUSDT", bases) == "leveraged_token"
    assert classify_exclusion("BTCDOWNUSDT", bases) == "leveraged_token"
    assert classify_exclusion("ETHBULLUSDT", bases) == "leveraged_token"
    assert classify_exclusion("ETHBEARUSDT", bases) == "leveraged_token"
    assert classify_exclusion("BTC3LUSDT", bases) == "leveraged_token"

    kept = tradeable_universe(symbols)
    assert "BTCUSDT" in kept and "JUPUSDT" in kept and "1000SHIBUSDT" in kept
    assert "USDCUSDT" not in kept and "BTCUPUSDT" not in kept and "ETHBULLUSDT" not in kept
    dropped = dict(excluded_symbols(symbols))
    assert dropped["USDCUSDT"] == "stablecoin_or_fiat"
    assert dropped["BTCUPUSDT"] == "leveraged_token"


def test_non_standard_ticker_excluded() -> None:
    # Binance Vision carries a few non-ASCII novelty symbols (a CJK-named promo token) that
    # are not coins and cannot even be ASCII-encoded into an S3 URL. Unicode escapes keep
    # this source file ASCII; cjk below is the exact symbol that the first full build hit.
    cjk = chr(0x5E01) + chr(0x5B89) + chr(0x4EBA) + chr(0x751F) + "USDT"  # the real promo token
    non_ascii = "FOO" + chr(0x00E9) + "USDT"  # an accented base
    bases = listed_bases_of(["BTCUSDT", cjk])
    assert classify_exclusion(cjk, bases) == "non_standard_ticker"
    assert classify_exclusion(non_ascii, bases) == "non_standard_ticker"
    kept = tradeable_universe(["BTCUSDT", cjk])
    assert kept == ("BTCUSDT",)
    assert dict(excluded_symbols(["BTCUSDT", cjk]))[cjk] == "non_standard_ticker"


def test_leveraged_up_down_needs_listed_base() -> None:
    # "JUP" ends in UP but is a real coin because "J" is not a base; "BTCUP" -> "BTC" is.
    assert not is_leveraged_token("JUP", frozenset({"BTC", "ETH", "JUP"}))
    assert is_leveraged_token("BTCUP", frozenset({"BTC", "BTCUP"}))
    # "BTC" not present -> "BTCUP" is not recognized as a leveraged token
    assert not is_leveraged_token("BTCUP", frozenset({"BTCUP"}))
    assert is_leveraged_token("ETH3L", frozenset({"ETH"}))


# ----- the daily panel -------------------------------------------------------


def test_build_daily_panel_dedup_sort_and_guards() -> None:
    recs = [
        _rec("BTCUSDT", date(2024, 1, 2), 100.0, 5.0),
        _rec("BTCUSDT", date(2024, 1, 1), 99.0, 4.0),
        _rec("AAAUSDT", date(2024, 1, 1), 1.0, 9.0),
        _rec("BTCUSDT", date(2024, 1, 2), 101.0, 6.0),  # a (date,symbol) duplicate; keep last
    ]
    panel = build_daily_panel(recs)
    assert panel.columns == ["date", "symbol", "close", "high", "low", "dollar_volume"]
    assert panel["symbol"].to_list() == ["AAAUSDT", "BTCUSDT", "BTCUSDT"]  # sorted (symbol, date)
    btc_jan2 = panel.filter((pl.col("symbol") == "BTCUSDT") & (pl.col("date") == date(2024, 1, 2)))
    assert btc_jan2["close"].item() == 101.0  # the last duplicate won

    with pytest.raises(CtrendError):
        build_daily_panel([_rec("BTCUSDT", date(2024, 1, 1), 0.0, 1.0)])  # non-positive close
    with pytest.raises(CtrendError):
        build_daily_panel([_rec("BTCUSDT", date(2024, 1, 1), 1.0, -1.0)])  # negative volume
    with pytest.raises(CtrendError):  # high < low (inconsistent OHLC)
        build_daily_panel([_rec("BTCUSDT", date(2024, 1, 1), 10.0, 1.0, high=9.0, low=11.0)])
    with pytest.raises(CtrendError):  # close above high
        build_daily_panel([_rec("BTCUSDT", date(2024, 1, 1), 10.0, 1.0, high=9.5, low=8.0)])


# ----- the weekly resample + returns -----------------------------------------


def test_weekly_resample_close_volume_and_returns() -> None:
    specs = [(0, 100.0, 70.0), (1, 110.0, 80.0), (2, 99.0, 60.0)]
    daily = build_daily_panel(_weeks("BTCUSDT", specs))
    weekly = build_weekly_panel(daily).sort("week_end")
    assert weekly["week_end"].to_list() == [date(2024, 1, 7), date(2024, 1, 14), date(2024, 1, 21)]
    assert weekly["weekly_close"].to_list() == [100.0, 110.0, 99.0]
    assert weekly["weekly_dollar_volume"].to_list() == [70.0, 80.0, 60.0]
    assert weekly["n_days"].to_list() == [7, 7, 7]
    rets = weekly["weekly_return"].to_list()
    assert rets[0] is None  # first week has no prior
    assert rets[1] == pytest.approx(0.10)  # 110/100 - 1
    assert rets[2] == pytest.approx(99 / 110 - 1)
    # forward_return(t) == weekly_return(t+1)
    fwd = weekly["forward_return"].to_list()
    assert fwd[0] == pytest.approx(0.10)
    assert fwd[1] == pytest.approx(99 / 110 - 1)
    assert fwd[2] is None  # last week has no forward


def test_weekly_return_is_null_across_a_gap() -> None:
    # weeks 0 and 1 present, week 2 missing, week 3 present: the week-3 return spans a gap.
    specs = [(0, 100.0, 70.0), (1, 110.0, 80.0), (3, 120.0, 50.0)]
    daily = build_daily_panel(_weeks("BTCUSDT", specs))
    weekly = build_weekly_panel(daily).sort("week_end")
    assert weekly["week_end"].to_list() == [date(2024, 1, 7), date(2024, 1, 14), date(2024, 1, 28)]
    rets = weekly["weekly_return"].to_list()
    assert rets[1] == pytest.approx(0.10)  # consecutive: 110/100 - 1
    assert rets[2] is None  # 2024-01-28 minus 2024-01-14 == 14 days, not 7: gap -> null
    assert weekly["gap_before"].to_list() == [False, False, True]
    # forward_return at the pre-gap week is null too (its next row's return is gap-nulled)
    assert weekly["forward_return"].to_list()[1] is None


# ----- the point-in-time eligibility -----------------------------------------


def _three_symbol_weekly() -> pl.DataFrame:
    recs: list[SpotKlineRecord] = []
    # AAA highest volume, BBB middle, CCC lowest, over 10 weeks; all consecutive.
    for sym, vol in (("AAAUSDT", 300.0), ("BBBUSDT", 200.0), ("CCCUSDT", 100.0)):
        recs.extend(_weeks(sym, [(w, 10.0 + w, vol) for w in range(10)]))
    return build_weekly_panel(build_daily_panel(recs))


def test_pit_eligible_top_n_and_min_history() -> None:
    weekly = _three_symbol_weekly()
    flagged = pit_eligible(weekly, top_n=2, lookback_weeks=4, min_history_weeks=8)
    # weeks 0..6 have < 8 bars -> nobody rankable -> nobody eligible
    early = flagged.filter(pl.col("week_end") <= date(2024, 1, 7) + timedelta(weeks=6))
    assert early["eligible"].sum() == 0
    # week 7 (the 8th bar) onward: top-2 by volume = AAA, BBB; CCC excluded
    late = flagged.filter(pl.col("week_end") >= date(2024, 1, 7) + timedelta(weeks=7))
    elig = late.filter(pl.col("eligible"))["symbol"].unique().to_list()
    assert set(elig) == {"AAAUSDT", "BBBUSDT"}
    assert "CCCUSDT" not in elig


def test_pit_eligible_tie_break_is_symbol_ascending() -> None:
    # three symbols with IDENTICAL volume; top_n=2 must select the two ascending symbols.
    recs: list[SpotKlineRecord] = []
    for sym in ("ZED", "MID", "ALP"):
        recs.extend(_weeks(sym + "USDT", [(w, 10.0, 500.0) for w in range(10)]))
    flagged = pit_eligible(build_weekly_panel(build_daily_panel(recs)), top_n=2,
                           lookback_weeks=4, min_history_weeks=8)
    wk = flagged.filter(pl.col("week_end") == date(2024, 1, 7) + timedelta(weeks=9))
    elig = set(wk.filter(pl.col("eligible"))["symbol"].to_list())
    assert elig == {"ALPUSDT", "MIDUSDT"}  # ascending wins the tie, ZEDUSDT dropped


def test_pit_eligible_is_point_in_time_no_lookahead() -> None:
    weekly = _three_symbol_weekly()
    base = pit_eligible(weekly, top_n=2, lookback_weeks=4, min_history_weeks=8)
    base_early = base.filter(pl.col("week_end") <= date(2024, 1, 7) + timedelta(weeks=8)).select(
        "week_end", "symbol", "eligible"
    )
    # Append a LATER week where CCC suddenly dominates volume; earlier weeks must NOT change.
    extra = build_weekly_panel(
        build_daily_panel(
            [r for sym, vol in (("AAAUSDT", 300.0), ("BBBUSDT", 200.0), ("CCCUSDT", 100.0))
             for r in _weeks(sym, [(w, 10.0 + w, vol) for w in range(10)])]
            + _week("CCCUSDT", _MON + timedelta(weeks=10), 99.0, 9_999_999.0)
        )
    )
    after = pit_eligible(extra, top_n=2, lookback_weeks=4, min_history_weeks=8)
    after_early = after.filter(pl.col("week_end") <= date(2024, 1, 7) + timedelta(weeks=8)).select(
        "week_end", "symbol", "eligible"
    )
    assert base_early.sort(["week_end", "symbol"]).equals(after_early.sort(["week_end", "symbol"]))


def test_trim_is_lossless_for_top_n_le_n_max() -> None:
    # 5 symbols; the two lowest-volume never enter the top-3. ever-top-3 trim must preserve
    # the top-2 and top-3 eligibility exactly.
    recs: list[SpotKlineRecord] = []
    for sym, vol in (("AAA", 500.0), ("BBB", 400.0), ("CCC", 300.0), ("DDD", 20.0), ("EEE", 10.0)):
        recs.extend(_weeks(sym + "USDT", [(w, 10.0, vol) for w in range(12)]))
    weekly_full = build_weekly_panel(build_daily_panel(recs))
    daily_full = build_daily_panel(recs)
    ever = ever_eligible_symbols(weekly_full, top_n=3, lookback_weeks=4, min_history_weeks=8)
    assert set(ever) == {"AAAUSDT", "BBBUSDT", "CCCUSDT"}  # DDD, EEE never top-3
    weekly_trim = build_weekly_panel(trim_daily_to(daily_full, ever))
    for n in (2, 3):
        assert eligible_pairs(weekly_full, top_n=n, lookback_weeks=4, min_history_weeks=8) == (
            eligible_pairs(weekly_trim, top_n=n, lookback_weeks=4, min_history_weeks=8)
        )


def test_pit_eligible_rejects_bad_knobs() -> None:
    weekly = _three_symbol_weekly()
    for bad in ({"top_n": 0}, {"lookback_weeks": 0}, {"min_history_weeks": 0}):
        with pytest.raises(CtrendError):
            pit_eligible(weekly, **bad)  # type: ignore[arg-type]
