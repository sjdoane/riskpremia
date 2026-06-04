"""Gather the committed monthly short-straddle entries for the Layer-ii gate (ADR 0004
PR5f). A manual, one-time network entry point (the VRP analogue of build_vrp_artifact).

For each first-of-month across the VRP window it fetches the free Tardis Deribit chain,
selects the near-ATM strike (nearest the Deribit forward) at the expiry closest to entry +
30 days that has BOTH a tradeable call and put, and records the two quotes. Months with no
tradeable ATM straddle are DROPPED LOUDLY and counted (the funnel is a diagnostic, not a
silent filter; a missing ATM put on a stress date is signal). The selected entries are
written to a committed CSV fixture and SHA256-stamped into the manifest; the realized
expiry underlying is NOT stored here (the gate looks it up from the committed spot fixture
by the expiry date), so the gate reproduces offline from the two committed fixtures.

  $env:PYTHONIOENCODING="utf-8"
  C:\\Users\\SamJD\\.venvs\\riskpremia\\Scripts\\python.exe -m scripts.build_vrp_entries

Then run the gate with `scripts.run_vrp_gate`.
"""

from __future__ import annotations

import statistics
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from riskpremia.data.manifest import SnapshotEntry, compute_sha256, upsert_entries
from riskpremia.data.records import OptionQuoteRecord
from riskpremia.data.sources.tardis_options import OptionChainSnapshot, TardisOptionChainSource
from riskpremia.vrp.fixtures import StraddleEntryRow, write_straddle_entries_csv

_REPO = Path(__file__).resolve().parents[1]
_FIXTURE = _REPO / "tests" / "data" / "vrp_straddle_entries.csv"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"
_TARGET_DAYS = 30
_AS_OF_OFFSET_MIN = 30


def _first_of_months(start: date, end: date) -> list[date]:
    out: list[date] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(date(y, m, 1))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _select_straddle(
    snapshot: OptionChainSnapshot,
) -> tuple[OptionQuoteRecord, OptionQuoteRecord] | None:
    """The near-ATM call + put at the expiry nearest as_of + 30 days, both tradeable."""
    as_of = snapshot.as_of
    target = as_of + timedelta(days=_TARGET_DAYS)
    expiries = sorted({q.expiry for q in snapshot.quotes if q.expiry > as_of})
    if not expiries:
        return None
    expiry = min(expiries, key=lambda e: abs((e - target).total_seconds()))
    legs = [q for q in snapshot.quotes if q.expiry == expiry]

    def tradeable(q: OptionQuoteRecord) -> bool:
        return q.bid_price is not None and q.mark_price is not None and q.delta is not None

    calls = {q.strike: q for q in legs if q.option_type == "call" and tradeable(q)}
    puts = {q.strike: q for q in legs if q.option_type == "put" and tradeable(q)}
    both = set(calls) & set(puts)
    if not both:
        return None
    underlying = statistics.median(float(q.underlying_price) for q in legs)
    strike = min(both, key=lambda k: abs(float(k) - underlying))
    return calls[strike], puts[strike]


def main() -> None:
    months = _first_of_months(date(2022, 1, 1), date(2025, 6, 1))
    source = TardisOptionChainSource()
    entries: list[StraddleEntryRow] = []
    dropped: list[tuple[date, str]] = []

    for d in months:
        try:
            snapshot = source.fetch_snapshot("BTC", d, as_of_offset_minutes=_AS_OF_OFFSET_MIN)
        except Exception as exc:  # noqa: BLE001 - record the drop, keep gathering
            dropped.append((d, f"fetch failed: {type(exc).__name__}"))
            print(f"  {d}: DROPPED ({type(exc).__name__}: {exc})")
            continue
        picked = _select_straddle(snapshot)
        if picked is None:
            dropped.append((d, "no tradeable ATM straddle"))
            print(f"  {d}: DROPPED (no tradeable ATM straddle)")
            continue
        call, put = picked
        hold_hours = (call.expiry - snapshot.as_of).total_seconds() / 3600.0
        entries.append((d, hold_hours, call, put))
        moneyness = float(call.strike) / float(call.underlying_price) - 1.0
        print(f"  {d}: K={call.strike} exp={call.expiry.date()} hold={hold_hours / 24:.0f}d "
              f"moneyness={moneyness:+.3f} call_bid={call.bid_price} put_bid={put.bid_price}")

    if not entries:
        raise SystemExit("no straddle entries gathered; aborting")
    write_straddle_entries_csv(_FIXTURE, entries)
    when = datetime.now(UTC).replace(microsecond=0)
    upsert_entries(
        _MANIFEST,
        (
            SnapshotEntry(
                name="vrp-straddle-entries",
                venue="tardis",
                instrument="BTCUSDT",
                kind="reproducibility_fixture",
                relpath=_FIXTURE.relative_to(_REPO).as_posix(),
                source_url=(
                    "https://datasets.tardis.dev/v1/deribit/options_chain/ (first-of-month; "
                    "near-ATM call+put at the ~30d expiry per month)"
                ),
                fetched_utc=when,
                sha256=compute_sha256(_FIXTURE),
                size_bytes=_FIXTURE.stat().st_size,
                rows=len(entries),
                published_checksum=None,
                note=(
                    "Committed in-repo reproducibility fixture: the selected monthly "
                    "short-straddle entry quotes for the Layer-ii gate; the realized expiry "
                    "underlying is looked up from the committed spot fixture by expiry date."
                ),
            ),
        ),
    )
    print(f"\nGathered {len(entries)} straddle entries, dropped {len(dropped)} "
          f"of {len(months)} months.")
    for d, why in dropped:
        print(f"  dropped {d}: {why}")
    print(f"Wrote {_FIXTURE.relative_to(_REPO).as_posix()} + stamped {_MANIFEST.name}.")
    print("Next: run the gate with `python -m scripts.run_vrp_gate`.")


if __name__ == "__main__":
    main()
