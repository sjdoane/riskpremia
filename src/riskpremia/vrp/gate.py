"""The Layer-ii short-variance gate + verdict (ADR 0004 PR5f, the tradeable test).

The pre-registered tradeable layer: a systematic SHORT STRADDLE each first-of-month (a
near-ATM call + put, each delta-hedged via `simulate_option_trade`, held to expiry). The
deliverable is NOT a short-vol Sharpe; it is the regime-conditional TAIL-LOSS table plus
a cited peso shock, and the pre-registered expected outcome is a cost/peso-bounded honest
NULL (ADR 0004). The Deflated Sharpe is reported necessary-not-sufficient and is
statistically underpowered at ~42 monthly observations; it can KILL (if below the bar)
but can never RESCUE a failing tail.

Two capital bases, both conservative toward the kill (the anti-optimism bar):
  - the DSR return series divides each month's straddle net by `2 * initial_margin_fraction`
    (both short legs; high base, understates the Sharpe);
  - the tail / peso loss is reported as a multiple of the SINGLE-leg margin
    (`initial_margin_fraction`; low base, so a single-leg crash is NOT halved, design
    review C1). A loss exceeding the posted margin (multiple > 1) is account-ending.

The catastrophic tail is the DOWN crash (the short put settles inverse: `intrinsic_usd /
S_T`, so a 90% crash pays ~9x the notional). The ~42-month sample under-samples that tail
(no >50% monthly move in window), so the peso shock (design review C2) re-runs the
straddle at CITED one-day crash precedents on a representative entry. Two un-modeled terms
are carried as flags, never hidden: the path rehedge (`path_rehedge_unmodeled`, the
dominant cost) and the terminal-settlement basis (`terminal_basis_unmodeled`: the expiry
underlying is the Binance daily close, not Deribit's 08:00 settlement, and convexity makes
that understate large-move losses). Stdlib + attrs + the vendored scoring stack; the gate
artifact serializes with the same discipline as the Layer-i artifact.
"""

from __future__ import annotations

import json
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Any

import attrs

from riskpremia.data.clock import SPOT_ETF_LAUNCH
from riskpremia.data.records import OptionQuoteRecord
from riskpremia.execution.cost import DeribitOptionCostModel
from riskpremia.execution.options import simulate_option_trade
from riskpremia.execution.scoring import effective_sample_size, psr_zero, return_moments
from riskpremia.vrp.errors import VrpError

SCHEMA_VERSION = 1
_STUDY = "crypto variance risk premium (Layer ii, the cost-gated short-variance test)"
_VIABILITY_BAR = 0.95
_UNDERPOWERED_EFFECTIVE_T = 30
_SURVIVABLE_MARGIN_MULTIPLE = 1.0
"""A worst loss exceeding the posted (single-leg) margin (multiple > 1) is account-ending
for a retail trader (liquidation and beyond); the tail then fails the deploy gate."""

# Cited one-day BTC crash precedents for the peso shock (the sample under-samples the tail).
PESO_SHOCKS: tuple[tuple[float, str], ...] = (
    (0.37, "2020-03-12 'Black Thursday' (~37% one-day BTC drop)"),
    (0.50, "2021-05-19 (~50% intraday BTC drop)"),
)


@attrs.frozen(slots=True)
class StraddleTrade:
    """One month's delta-hedged short straddle, net in COIN per contract.

    `net == call_net + put_net` (each from `simulate_option_trade`, separately
    delta-hedged, which conservatively over-charges the hedge vs a net-delta hedge).
    `combined_entry_delta = call.delta + put.delta` is ~0 for a true ATM straddle (pinned,
    so a put-delta-sign error is caught). `moneyness = strike/entry_underlying - 1`
    surfaces any strike slide from ATM. Both un-modeled terms are flagged True.
    """

    entry_date: date
    expiry: datetime
    strike: float
    entry_underlying: float
    terminal_underlying: float
    hold_hours: float
    regime: str
    call_net: float
    put_net: float
    net: float
    combined_entry_delta: float
    premium_received: float
    moneyness: float
    terminal_basis_unmodeled: bool = True
    path_rehedge_unmodeled: bool = True

    def __attrs_post_init__(self) -> None:
        if self.net != self.call_net + self.put_net:
            raise VrpError(
                f"straddle net {self.net} != call_net + put_net "
                f"{self.call_net + self.put_net} on {self.entry_date}"
            )


def build_straddle_trade(
    call: OptionQuoteRecord,
    put: OptionQuoteRecord,
    terminal_underlying: float,
    model: DeribitOptionCostModel,
    *,
    entry_date: date,
    hold_hours: float,
) -> StraddleTrade:
    """Sell the call + put (each delta-hedged, held to expiry); sum to the straddle P&L.

    Raises:
      VrpError: on a strike/expiry/underlying mismatch between the two legs (they must be
        the same straddle), or (via the option P&L) a bad quote.
    """
    if call.option_type != "call" or put.option_type != "put":
        raise VrpError(f"build_straddle_trade needs a call and a put; got {call.option_type}, "
                       f"{put.option_type}")
    if call.strike != put.strike or call.expiry != put.expiry:
        raise VrpError(
            f"straddle legs must share strike+expiry; call {call.strike}/{call.expiry}, "
            f"put {put.strike}/{put.expiry}"
        )
    call_trade = simulate_option_trade(call, terminal_underlying, model, hold_hours=hold_hours)
    put_trade = simulate_option_trade(put, terminal_underlying, model, hold_hours=hold_hours)
    s0 = float(call.underlying_price)
    regime = "post_etf" if entry_date >= SPOT_ETF_LAUNCH.date() else "pre_etf"
    call_delta = float(call.delta) if call.delta is not None else 0.0
    put_delta = float(put.delta) if put.delta is not None else 0.0
    return StraddleTrade(
        entry_date=entry_date,
        expiry=call.expiry,
        strike=float(call.strike),
        entry_underlying=s0,
        terminal_underlying=float(terminal_underlying),
        hold_hours=hold_hours,
        regime=regime,
        call_net=call_trade.net,
        put_net=put_trade.net,
        net=call_trade.net + put_trade.net,
        combined_entry_delta=call_delta + put_delta,
        premium_received=call_trade.premium_received + put_trade.premium_received,
        moneyness=float(call.strike) / s0 - 1.0,
    )


@attrs.frozen(slots=True)
class RegimeTail:
    """The tail-loss decomposition for one regime (loss multiples vs the SINGLE-leg margin).

    `worst_loss_coin` is the worst single-month straddle loss (a positive magnitude);
    `worst_loss_margin_mult` is that loss as a multiple of `initial_margin_fraction` (the
    single-leg margin, so the crash is not halved). `max_drawdown_coin` is the worst
    peak-to-trough of the cumulative SUM of monthly coin P&L (additive; these are
    non-overlapping closed trades). `n` is small per regime, so the worst-month is a LOWER
    bound on the true tail (the peso shock covers the gap).
    """

    name: str
    n: int
    mean_net_coin: float
    frac_losing: float
    worst_loss_coin: float
    worst_loss_margin_mult: float
    max_drawdown_coin: float


def _regime_tail(trades: list[StraddleTrade], name: str, *, single_leg_margin: float) -> RegimeTail:
    sub = trades if name == "all" else [t for t in trades if t.regime == name]
    n = len(sub)
    if n == 0:
        return RegimeTail(name, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    nets = [t.net for t in sub]
    worst = min(nets)  # most negative net
    worst_loss = max(0.0, -worst)
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for v in nets:
        equity += v
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return RegimeTail(
        name=name,
        n=n,
        mean_net_coin=statistics.fmean(nets),
        frac_losing=sum(1 for v in nets if v < 0.0) / n,
        worst_loss_coin=worst_loss,
        worst_loss_margin_mult=worst_loss / single_leg_margin,
        max_drawdown_coin=max_dd,
    )


@attrs.frozen(slots=True)
class PesoShock:
    """A cited one-day crash shock on a representative straddle (design review C2).

    Deterministic and reproducible: the representative entry's straddle re-run at
    `terminal = entry_underlying * (1 - shock_pct)`. `loss_margin_mult` is the loss as a
    multiple of the single-leg margin. NOT visible to the DSR (the peso problem).
    """

    shock_pct: float
    source: str
    loss_coin: float
    loss_margin_mult: float


def _peso_shock(
    call: OptionQuoteRecord,
    put: OptionQuoteRecord,
    model: DeribitOptionCostModel,
    *,
    entry_date: date,
    hold_hours: float,
    single_leg_margin: float,
    shock_pct: float,
    source: str,
) -> PesoShock:
    terminal = float(call.underlying_price) * (1.0 - shock_pct)
    straddle = build_straddle_trade(
        call, put, terminal, model, entry_date=entry_date, hold_hours=hold_hours
    )
    loss = max(0.0, -straddle.net)
    return PesoShock(
        shock_pct=shock_pct,
        source=source,
        loss_coin=loss,
        loss_margin_mult=loss / single_leg_margin,
    )


@attrs.frozen(slots=True)
class GateVerdict:
    """The deploy verdict from the frozen ADR 0004 criterion.

    `non_viable` is True if the DSR is below the bar OR the worst tail loss (the larger of
    the in-sample worst month and the cited peso shocks) exceeds the posted margin. A high
    DSR can never make `non_viable` False on its own (design review H3).
    """

    deflated_sharpe: float
    effective_t: int
    pw_block_length: float
    dsr_underpowered: bool
    dsr_passes: bool
    worst_loss_margin_mult: float
    tail_survivable: bool
    non_viable: bool
    reason: str


@attrs.frozen(slots=True)
class StraddleEntry:
    """One month's selected short-straddle entry (the committed-fixture-reconstructed
    quotes + the realized expiry underlying), the input to the gate."""

    entry_date: date
    call: OptionQuoteRecord
    put: OptionQuoteRecord
    terminal_underlying: float
    hold_hours: float


@attrs.frozen(slots=True)
class GateSeries:
    """The per-month straddle series (for reproduction + the deferred figures)."""

    entry_date: tuple[str, ...]
    net_coin: tuple[float, ...]
    net_return: tuple[float, ...]
    regime: tuple[str, ...]
    moneyness: tuple[float, ...]


CAVEATS: tuple[str, ...] = (
    "The headline is the VRP MEASUREMENT (Layer i) plus this regime-conditional tail-loss "
    "table, NEVER a short-volatility Sharpe. The Deflated Sharpe is reported for "
    "completeness and is statistically UNDERPOWERED at ~42 monthly observations; it can "
    "kill but cannot rescue a failing tail.",
    "The deploy verdict rests on the tail: a short straddle's down crash settles inverse "
    "(the put pays intrinsic_usd / S_T), so the loss exceeds the posted margin. The ~42-"
    "month sample under-samples the catastrophic tail, so the peso shock re-runs the "
    "straddle at CITED one-day crash precedents.",
    "Un-modeled costs (both bias toward a false pass and are NOT in the DSR): the "
    "path-rehedge slippage between entry and expiry (the dominant short-variance cost); "
    "and the terminal settlement basis (the expiry underlying is the Binance daily close, "
    "not Deribit's 08:00 settlement, and convexity makes that understate large-move losses).",
    "Deribit options are not yet US-retail-tradeable (Coinbase Financial Markets is "
    "institutional-live / retail-coming-soon); CPCV is not run (~18 post-ETF monthly "
    "observations cannot support a purged-embargoed cross-validation), so the DSR is the "
    "full-sample PSR(0) on the regime (ADR 0004 pre-registration).",
)


def _verdict(
    deflated_sharpe: float,
    effective_t: int,
    pw_block_length: float,
    worst_loss_margin_mult: float,
) -> GateVerdict:
    dsr_passes = deflated_sharpe >= _VIABILITY_BAR
    tail_survivable = worst_loss_margin_mult <= _SURVIVABLE_MARGIN_MULTIPLE
    non_viable = (not dsr_passes) or (not tail_survivable)
    if not tail_survivable and not dsr_passes:
        reason = "DSR below the bar AND the tail loss exceeds the posted margin"
    elif not tail_survivable:
        reason = (
            f"the worst tail loss is {worst_loss_margin_mult:.1f}x the posted margin "
            f"(account-ending), so the short variance is not retail-survivable even if the "
            f"DSR clears the bar (the peso problem the DSR cannot price)"
        )
    elif not dsr_passes:
        reason = f"DSR {deflated_sharpe:.3f} is below the {_VIABILITY_BAR} bar"
    else:
        reason = (
            "BOTH the DSR clears the bar AND the worst modeled tail is within the posted "
            "margin; a surprising PASS that must be cross-checked before belief (verify it "
            "is not the doubled-margin or terminal-basis artifact, and note the un-modeled "
            "path rehedge + terminal basis are NOT in the DSR, so a marginal pass is inside "
            "the un-modeled error bar; this is not a deploy green-light)"
        )
    return GateVerdict(
        deflated_sharpe=deflated_sharpe,
        effective_t=effective_t,
        pw_block_length=pw_block_length,
        dsr_underpowered=effective_t < _UNDERPOWERED_EFFECTIVE_T,
        dsr_passes=dsr_passes,
        worst_loss_margin_mult=worst_loss_margin_mult,
        tail_survivable=tail_survivable,
        non_viable=non_viable,
        reason=reason,
    )


@attrs.frozen(slots=True)
class GateArtifact:
    """The committed Layer-ii gate deliverable (the verdict + the tail table)."""

    schema_version: int
    study: str
    currency: str
    window_start: str
    window_end: str
    n_entries_total: int
    n_entries_used: int
    n_entries_dropped: int
    entries_sha256: str
    spot_sha256: str
    return_base: float
    single_leg_margin: float
    regimes: tuple[RegimeTail, ...]
    in_sample_worst_loss_coin: float
    in_sample_worst_loss_margin_mult: float
    peso_shocks: tuple[PesoShock, ...]
    verdict: GateVerdict
    caveats: tuple[str, ...]
    series: GateSeries


def build_gate_artifact(
    entries: list[StraddleEntry],
    model: DeribitOptionCostModel,
    *,
    currency: str,
    n_entries_total: int,
    n_entries_dropped: int,
    entries_sha256: str,
    spot_sha256: str,
) -> GateArtifact:
    """Build the gate artifact from the selected monthly straddle entries.

    Raises:
      VrpError: when fewer than 2 straddles survive (too few to score the series).
    """
    if len(entries) < 2:
        raise VrpError(
            f"the gate needs >= 2 straddle entries to score; got {len(entries)} "
            f"(the both-legs-tradeable filter may have thinned the ~42-month sample)"
        )
    single_leg_margin = model.initial_margin_fraction
    return_base = 2.0 * model.initial_margin_fraction

    trades = [
        build_straddle_trade(
            e.call, e.put, e.terminal_underlying, model,
            entry_date=e.entry_date, hold_hours=e.hold_hours,
        )
        for e in entries
    ]
    trades.sort(key=lambda t: t.entry_date)
    returns = [t.net / return_base for t in trades]
    deflated_sharpe = psr_zero(returns)
    effective_t, pw_block = effective_sample_size(returns)
    _ = return_moments(returns)  # raises loudly on a degenerate (zero-variance) series

    regimes = tuple(
        _regime_tail(trades, name, single_leg_margin=single_leg_margin)
        for name in ("all", "pre_etf", "post_etf")
    )
    all_tail = regimes[0]

    # The peso shock on a REPRESENTATIVE entry: the post-ETF straddle whose put delta is
    # closest to -0.5 (the most-ATM post-ETF entry; fall back to all entries pre-ETF).
    post = [e for e in entries if e.entry_date >= SPOT_ETF_LAUNCH.date()]
    pool = post if post else entries
    representative = min(
        pool, key=lambda e: abs((float(e.put.delta) if e.put.delta is not None else 0.0) + 0.5)
    )
    peso = tuple(
        _peso_shock(
            representative.call, representative.put, model,
            entry_date=representative.entry_date, hold_hours=representative.hold_hours,
            single_leg_margin=single_leg_margin, shock_pct=pct, source=src,
        )
        for pct, src in PESO_SHOCKS
    )

    worst_margin_mult = max(
        [all_tail.worst_loss_margin_mult] + [p.loss_margin_mult for p in peso]
    )
    verdict = _verdict(deflated_sharpe, effective_t, pw_block, worst_margin_mult)

    series = GateSeries(
        entry_date=tuple(t.entry_date.isoformat() for t in trades),
        net_coin=tuple(t.net for t in trades),
        net_return=tuple(t.net / return_base for t in trades),
        regime=tuple(t.regime for t in trades),
        moneyness=tuple(t.moneyness for t in trades),
    )
    return GateArtifact(
        schema_version=SCHEMA_VERSION,
        study=_STUDY,
        currency=currency,
        window_start=trades[0].entry_date.isoformat(),
        window_end=trades[-1].entry_date.isoformat(),
        n_entries_total=n_entries_total,
        n_entries_used=len(trades),
        n_entries_dropped=n_entries_dropped,
        entries_sha256=entries_sha256,
        spot_sha256=spot_sha256,
        return_base=return_base,
        single_leg_margin=single_leg_margin,
        regimes=regimes,
        in_sample_worst_loss_coin=all_tail.worst_loss_coin,
        in_sample_worst_loss_margin_mult=all_tail.worst_loss_margin_mult,
        peso_shocks=peso,
        verdict=verdict,
        caveats=CAVEATS,
        series=series,
    )


def gate_artifact_to_json(artifact: GateArtifact) -> str:
    """Deterministic JSON (sorted keys, round-trip-exact floats, trailing newline)."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_gate_artifact(artifact: GateArtifact, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(gate_artifact_to_json(artifact), encoding="utf-8", newline="\n")


def _req(d: dict[str, Any], key: str) -> Any:
    if key not in d:
        raise VrpError(f"gate artifact missing required key {key!r}")
    return d[key]


def load_gate_artifact(path: Path) -> GateArtifact:
    """Load + validate a committed gate artifact JSON into a typed GateArtifact."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise VrpError(f"gate artifact {path.name} is not a JSON object")
    v = _req(data, "verdict")
    s = _req(data, "series")
    return GateArtifact(
        schema_version=int(_req(data, "schema_version")),
        study=str(_req(data, "study")),
        currency=str(_req(data, "currency")),
        window_start=str(_req(data, "window_start")),
        window_end=str(_req(data, "window_end")),
        n_entries_total=int(_req(data, "n_entries_total")),
        n_entries_used=int(_req(data, "n_entries_used")),
        n_entries_dropped=int(_req(data, "n_entries_dropped")),
        entries_sha256=str(_req(data, "entries_sha256")),
        spot_sha256=str(_req(data, "spot_sha256")),
        return_base=float(_req(data, "return_base")),
        single_leg_margin=float(_req(data, "single_leg_margin")),
        regimes=tuple(
            RegimeTail(
                name=str(_req(r, "name")), n=int(_req(r, "n")),
                mean_net_coin=float(_req(r, "mean_net_coin")),
                frac_losing=float(_req(r, "frac_losing")),
                worst_loss_coin=float(_req(r, "worst_loss_coin")),
                worst_loss_margin_mult=float(_req(r, "worst_loss_margin_mult")),
                max_drawdown_coin=float(_req(r, "max_drawdown_coin")),
            )
            for r in _req(data, "regimes")
        ),
        in_sample_worst_loss_coin=float(_req(data, "in_sample_worst_loss_coin")),
        in_sample_worst_loss_margin_mult=float(_req(data, "in_sample_worst_loss_margin_mult")),
        peso_shocks=tuple(
            PesoShock(
                shock_pct=float(_req(p, "shock_pct")), source=str(_req(p, "source")),
                loss_coin=float(_req(p, "loss_coin")),
                loss_margin_mult=float(_req(p, "loss_margin_mult")),
            )
            for p in _req(data, "peso_shocks")
        ),
        verdict=GateVerdict(
            deflated_sharpe=float(_req(v, "deflated_sharpe")),
            effective_t=int(_req(v, "effective_t")),
            pw_block_length=float(_req(v, "pw_block_length")),
            dsr_underpowered=bool(_req(v, "dsr_underpowered")),
            dsr_passes=bool(_req(v, "dsr_passes")),
            worst_loss_margin_mult=float(_req(v, "worst_loss_margin_mult")),
            tail_survivable=bool(_req(v, "tail_survivable")),
            non_viable=bool(_req(v, "non_viable")),
            reason=str(_req(v, "reason")),
        ),
        caveats=tuple(str(c) for c in _req(data, "caveats")),
        series=GateSeries(
            entry_date=tuple(str(x) for x in _req(s, "entry_date")),
            net_coin=tuple(float(x) for x in _req(s, "net_coin")),
            net_return=tuple(float(x) for x in _req(s, "net_return")),
            regime=tuple(str(x) for x in _req(s, "regime")),
            moneyness=tuple(float(x) for x in _req(s, "moneyness")),
        ),
    )
