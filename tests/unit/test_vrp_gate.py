"""The Layer-ii short-variance gate (ADR 0004 PR5f): the straddle P&L + invariants, the
inverse crash tail, the regime tail table, the cited peso shock, the DSR subordination
(a high DSR can never rescue a failing tail), the verdict, and the artifact round-trip."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from riskpremia.data.records import OptionQuoteRecord, OptionType
from riskpremia.execution.cost import DERIBIT_OPTION
from riskpremia.vrp.errors import VrpError
from riskpremia.vrp.gate import (
    StraddleEntry,
    build_gate_artifact,
    build_straddle_trade,
    gate_artifact_to_json,
    load_gate_artifact,
)


def _leg(option_type: OptionType, s0: float, strike: float, delta: float) -> OptionQuoteRecord:
    return OptionQuoteRecord(
        currency="BTC", instrument=f"BTC-TEST-{option_type}", option_type=option_type,
        strike=Decimal(str(strike)), expiry=datetime(2024, 2, 1, 8, tzinfo=UTC),
        quote_ts=datetime(2024, 1, 1, 1, tzinfo=UTC), underlying_index="BTC",
        underlying_price=Decimal(str(s0)), synthetic_underlying=False,
        bid_price=Decimal("0.030"), mark_price=Decimal("0.031"), delta=Decimal(str(delta)),
    )


def _entry(entry_date: date, s0: float, terminal: float) -> StraddleEntry:
    return StraddleEntry(
        entry_date=entry_date, call=_leg("call", s0, s0, 0.5), put=_leg("put", s0, s0, -0.5),
        terminal_underlying=terminal, hold_hours=720.0,
    )


def _build(entries: list[StraddleEntry]):  # type: ignore[no-untyped-def]
    return build_gate_artifact(
        entries, DERIBIT_OPTION, currency="BTC", n_entries_total=42,
        n_entries_dropped=42 - len(entries), entries_sha256="a" * 64, spot_sha256="b" * 64,
    )


# ----- the straddle trade + invariants ---------------------------------------

def test_straddle_net_is_sum_and_atm_delta_cancels() -> None:
    e = _entry(date(2024, 1, 5), 100.0, 101.0)  # 2024-01-05 is before the 2024-01-11 launch
    trade = build_straddle_trade(e.call, e.put, e.terminal_underlying, DERIBIT_OPTION,
                                 entry_date=e.entry_date, hold_hours=720.0)
    assert trade.net == trade.call_net + trade.put_net
    assert abs(trade.combined_entry_delta) < 1e-9  # +0.5 + (-0.5) cancel at ATM
    assert trade.regime == "pre_etf"


def test_regime_split_on_etf_launch() -> None:
    pre = _build([_entry(date(2023, 12, 1), 100.0, 101.0), _entry(date(2024, 1, 5), 100.0, 99.0)])
    assert all(r.name != "post_etf" or r.n == 0 for r in pre.regimes)
    post = _build([_entry(date(2024, 2, 1), 100.0, 101.0), _entry(date(2024, 3, 1), 100.0, 99.0)])
    post_tail = next(r for r in post.regimes if r.name == "post_etf")
    assert post_tail.n == 2


def test_inverse_crash_tail_is_catastrophic() -> None:
    e = _entry(date(2024, 1, 1), 100.0, 10.0)  # a 90% crash
    trade = build_straddle_trade(e.call, e.put, e.terminal_underlying, DERIBIT_OPTION,
                                 entry_date=e.entry_date, hold_hours=720.0)
    assert trade.net < -3.0  # the short put settles inverse: a multi-x-of-notional loss


# ----- the gate: tail table, peso, DSR subordination, verdict ----------------

def _passing_dsr_entries() -> list[StraddleEntry]:
    # Near-flat months: the straddle keeps almost all premium with tiny variance, so the
    # DSR is high (passing), yet the cited peso crash must still kill on the tail (review H3).
    out: list[StraddleEntry] = []
    for i in range(10):
        d = date(2023 + (10 + i - 1) // 12, ((10 + i - 1) % 12) + 1, 1)
        move = 1.0 + (0.003 if i % 2 == 0 else -0.003)  # tiny, varied (non-zero variance)
        out.append(_entry(d, 100.0, 100.0 * move))
    return out


def test_high_dsr_cannot_rescue_a_failing_tail() -> None:
    v = _build(_passing_dsr_entries()).verdict
    # The near-flat months give a PASSING DSR; the cited peso crash makes the tail
    # unsurvivable, so the verdict is still NON-VIABLE (a high DSR can never rescue it, H3).
    assert v.dsr_passes is True
    assert not v.tail_survivable
    assert v.non_viable and "even if the DSR clears the bar" in v.reason


def test_peso_shocks_are_cited_and_explode() -> None:
    artifact = _build(_passing_dsr_entries())
    assert len(artifact.peso_shocks) == 2
    for p in artifact.peso_shocks:
        assert p.source and p.loss_margin_mult > 1.0  # cited; loses more than the margin
    by_shock = {p.shock_pct: p.loss_margin_mult for p in artifact.peso_shocks}
    assert by_shock[0.50] > by_shock[0.37]  # the deeper crash loses more


def test_regime_table_has_all_pre_post() -> None:
    artifact = _build(_passing_dsr_entries())
    assert {r.name for r in artifact.regimes} == {"all", "pre_etf", "post_etf"}
    all_tail = next(r for r in artifact.regimes if r.name == "all")
    assert all_tail.n == artifact.n_entries_used


def test_gate_requires_two_entries() -> None:
    with pytest.raises(VrpError, match=">= 2 straddle entries"):
        _build([_entry(date(2024, 1, 1), 100.0, 100.0)])


def test_gate_artifact_json_roundtrip() -> None:
    artifact = _build(_passing_dsr_entries())
    text = gate_artifact_to_json(artifact)
    assert list(json.loads(text).keys()) == sorted(json.loads(text).keys())  # sorted keys
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "gate.json"
        p.write_text(text, encoding="utf-8")
        assert load_gate_artifact(p) == artifact
