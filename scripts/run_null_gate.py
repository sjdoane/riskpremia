"""Run the random-entry null through the cost model and print the first kill number.

The kill gate (ADR 0003): build the held-out post-spot-ETF BTCUSDT observation
frame from the reproducible Binance Vision dumps, run the always-on and
non-overlapping nulls through each venue's cost model across a horizon sweep and
both capital multiples, and report the early economic gate, the headline deflated
Sharpe (PSR(0)) with the lumpy/amortised diagnostic, the funding-sign regime, and
the after-tax sidebar. The kill reads the tradeable-venue cells at the conservative
capital multiple; the favourable multiple is reported so the verdict is bracketed,
not asserted (amendment B6).

This is a manual research entry point, not a CI step. Run with the dedicated venv:
  $env:PYTHONIOENCODING="utf-8"
  C:\\Users\\SamJD\\.venvs\\riskpremia\\Scripts\\python.exe -m scripts.run_null_gate

Honest framing (amendment B4): the pre-signal number is the full-sample PSR(0) on
the held-out post-ETF REGIME, not an out-of-sample-under-CPCV number. The
event-time-purged CPCV is wired and its embargo is asserted >= H, but it is
degenerate for an unconditional carry (no fitted parameter) and becomes load-bearing
only once a selection signal exists.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from riskpremia.data.clock import (
    SPOT_ETF_LAUNCH,
    build_observation_frame,
    make_label_horizons,
    marks_frame,
    normalize_funding_frame,
    spot_frame,
)
from riskpremia.data.sources.binance_vision import BinanceVisionSource
from riskpremia.execution.carry import price_pnl_contamination, simulate_batch
from riskpremia.execution.cost import ALL_VENUES, KRAKEN
from riskpremia.execution.exhibit import (
    after_tax_sidebar,
    early_gate,
    funding_sign_regime,
    gate_surface,
    headline_score,
    is_killed,
)
from riskpremia.execution.scoring import make_purged_cpcv
from riskpremia.strategy.null import non_overlapping_entries
from riskpremia.validation.trial_registry import TrialRegistry

_DEFAULT_HORIZONS = (1, 3, 9, 21, 63, 189)
_CAPITAL_MULTIPLES = (2.0, 1.0)
_VIABILITY_BAR = 0.95


def _build_post_etf_frame(cache: Path, start: datetime, end: datetime) -> pl.DataFrame:
    """Fetch + assemble the post-ETF funding + mark + spot + basis frame."""
    src = BinanceVisionSource(cache)
    funding = normalize_funding_frame(src.fetch_funding("BTCUSDT", start, end))
    warm = start - timedelta(days=2)  # warm up the price legs before the funding window
    marks = marks_frame(src.fetch_marks("BTCUSDT", "8h", warm, end))
    spot = spot_frame(src.fetch_spot("BTCUSDT", "USDT", "8h", warm, end))
    return build_observation_frame(funding, marks, spot, mark_tolerance="8h", spot_tolerance="8h")


def _fmt_bps(fraction: float) -> str:
    return f"{fraction * 1e4:8.2f}bps"


def run(observations: pl.DataFrame, registry: TrialRegistry, fingerprint: str) -> bool:
    """Print the full kill-gate surface and return True if the strategy is KILLED."""
    n = observations.height
    span = f"{observations['dt'].min()!s} .. {observations['dt'].max()!s}"
    print(f"\nObservation frame: {n} funding events ({span})")

    regime = funding_sign_regime(observations)
    print(
        f"\nFunding-sign regime (per-interval, the short collects +funding): "
        f"{regime.n_positive} positive / {regime.n_negative} negative / {regime.n_zero} zero "
        f"({regime.negative_fraction:.1%} negative); worst collecting-equity drawdown "
        f"{_fmt_bps(regime.negative_regime_drawdown)}"
    )

    # Confirm the CPCV machinery is wired with an embargo that covers the longest hold.
    longest = max(h for h in _DEFAULT_HORIZONS if h < n)
    make_purged_cpcv(n, longest)
    print(
        f"CPCV wired: embargo asserted >= H for H up to {longest} "
        f"(degenerate for an unconditional carry; load-bearing once a signal exists)"
    )

    cells = gate_surface(
        observations,
        venues=ALL_VENUES,
        horizons=_DEFAULT_HORIZONS,
        capital_multiples=_CAPITAL_MULTIPLES,
    )
    last_cm: float | None = None
    for cell in cells:
        cm = cell.score.capital_multiple
        if cm != last_cm:
            label = "conservative no-cross-margin 2N headline" if cm == 2.0 else "favourable bound"
            print(f"\n{'=' * 96}\nCAPITAL MULTIPLE = {cm} ({label})\n{'=' * 96}")
            print(f"{'venue':<18}{'trd?':<6}{'H':>4}{'n':>6}{'med_fund':>12}{'roundtrip':>12}"
                  f"{'financing':>12}{'headroom':>12}{'DSR_kill':>10}{'pass':>6}")
            last_cm = cm
        gate, score = cell.early, cell.score
        # The registry row counts this (venue, H, capital_multiple) trial for the
        # eventual multiplicity deflation and stores the realized phase-0 per-trade
        # moments + the block-deflated effective T, so the per-trade headline PSR(0)
        # is reproducible from the row; the authoritative dsr_kill (the min with the
        # lumpy diagnostic) rides in the metadata (amendment B5).
        registry.record(
            dataset_fingerprint=fingerprint,
            strategy_family="null_control",
            sr_hat=score.sr_hat_per_trade,
            t_observations=score.effective_t,
            gamma_3=score.gamma_3_per_trade,
            gamma_4=score.gamma_4_per_trade,
            metadata={
                "venue": score.venue,
                "horizon_events": score.horizon_events,
                "capital_multiple": cm,
                "dsr_kill": score.dsr_kill,
                "pw_block_length": score.pw_block_length,
            },
        )
        print(
            f"{score.venue:<18}{('yes' if score.tradeable else 'ref'):<6}{score.horizon_events:>4}"
            f"{gate.n_trades:>6}{_fmt_bps(gate.median_funding):>12}"
            f"{_fmt_bps(gate.round_trip_cost):>12}{_fmt_bps(gate.median_financing):>12}"
            f"{_fmt_bps(gate.headroom):>12}{score.dsr_kill:>10.4f}"
            f"{('Y' if score.passes else 'n'):>6}"
        )

    killed = is_killed(cells)
    favourable_pass = any(
        c.score.passes and c.score.tradeable and c.score.capital_multiple == 1.0 for c in cells
    )
    if favourable_pass:
        favourable_msg = "a tradeable cell PASSES (inspect it)"
    else:
        favourable_msg = "every tradeable cell still fails"
    print(
        f"\nBracket: at the favourable 1N capital charge, {favourable_msg} the "
        f"{_VIABILITY_BAR} bar, so the kill does not rest on the conservative 2N assumption."
    )

    # The financing-dominance and lumpy/amortised story at a representative cell (Kraken H=21).
    kraken = simulate_batch(observations, horizon_events=21, cost_model=KRAKEN)
    g = early_gate(kraken, KRAKEN, 21)
    s = headline_score(observations, kraken, horizon_events=21, cost_model=KRAKEN)
    print(
        f"\nKraken H=21 detail: funding {g.funding_annualized:.2%}/yr vs financing "
        f"{g.financing_annualized:.2%}/yr (2N opportunity cost); DSR per-trade "
        f"{s.dsr_per_trade_median:.4f} [{s.dsr_per_trade_min:.4f},{s.dsr_per_trade_max:.4f}] "
        f"lumpy {s.dsr_lumpy:.4f} amortised {s.dsr_amortised:.4f} -> kill reads {s.dsr_kill:.4f}; "
        f"PW block {s.pw_block_length:.2f} (iid_ok={s.iid_ok})"
    )
    contamination = price_pnl_contamination(kraken)
    print(
        f"price_pnl contamination: mean {contamination['mean_price_pnl']:.3e} vs mean funding "
        f"{contamination['mean_funding']:.3e} (ratio {contamination['contamination_ratio']:.3f}, "
        f"contaminated={bool(contamination['contaminated'])})"
    )
    # The after-tax sidebar is on the deployable NON-overlapping series (one trade at
    # a time), not the overlapping always-on batch (whose summed net double-counts
    # reused capital and is not a real P&L).
    nonoverlap_entries = list(non_overlapping_entries(observations.height, 21))
    nonoverlap = kraken.filter(pl.col("entry_index").is_in(nonoverlap_entries))
    tax = after_tax_sidebar(nonoverlap, ordinary_rate=0.35)
    print(
        f"after-tax sidebar (Kraken H=21 non-overlapping, illustrative 35% ordinary, "
        f"within-year offset): pre-tax {_fmt_bps(tax.pre_tax_total)} -> after-tax "
        f"{_fmt_bps(tax.after_tax_total)} over {tax.n_years} year(s)"
    )
    return killed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the funding-carry kill gate.")
    parser.add_argument("--start", default=SPOT_ETF_LAUNCH.date().isoformat(),
                        help="post-ETF window start (YYYY-MM-DD); default the spot-ETF launch")
    parser.add_argument("--end", default="2026-06-01", help="window end (YYYY-MM-DD)")
    parser.add_argument("--cache", default="data/raw", help="Binance Vision download cache dir")
    parser.add_argument("--db", default="data/null_gate_trials.db", help="trial-registry db path")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    print(f"Fetching BTCUSDT post-ETF funding + mark + spot ({start.date()} .. {end.date()}) ...")
    observations = _build_post_etf_frame(cache, start, end)
    # Sanity: the frame feeds the CPCV label contract at the longest hold.
    make_label_horizons(observations, horizon_events=1)

    registry = TrialRegistry(Path(args.db), naive_effective_n=1)
    fingerprint = f"btcusdt_post_etf_{start.date()}_{end.date()}_n{observations.height}"
    killed = run(observations, registry, fingerprint)

    print(f"\n{'=' * 96}")
    if killed:
        print("VERDICT: KILL. The naive funding carry's net-of-cost deflated Sharpe is below "
              f"{_VIABILITY_BAR} on every tradeable venue and horizon at the conservative 2N "
              "capital charge. The carry is not viable for real-money deployment as a passive "
              "always-on or random-entry strategy; any edge must come from selection, which "
              "raises the bar. This is the honest pre-registered null.")
    else:
        print("VERDICT: a tradeable cell cleared the bar at the conservative capital charge; "
              "inspect it before believing it (the trial grid then becomes a deflated family).")
    print(f"{'=' * 96}")


if __name__ == "__main__":
    main()
