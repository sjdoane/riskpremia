"""Build the committed CTREND universe panel + artifact from the real Binance Vision data.

A manual, one-time research entry point (not a CI step), the CTREND analogue of
`build_vrp_artifact.py`. It enumerates the delisting-complete USDT spot universe, fetches
every tradeable coin's DAILY klines (close + USD dollar volume) concurrently, builds the
full daily -> weekly panel, computes the ever-top-N_MAX liquid set, TRIMS the daily panel
to it, proves the trim is lossless and that the committed CSV reproduces the live
eligibility, writes the committed fixture + the universe artifact, and SHA256-stamps the
fixture into the snapshot manifest. Run with the dedicated venv from the repo root:

  $env:PYTHONIOENCODING="utf-8"
  C:\\Users\\SamJD\\.venvs\\riskpremia\\Scripts\\python.exe -m scripts.build_ctrend_universe

The raw daily zips are immutable + checksummed, so a re-run is byte-identical (only the
manifest `fetched_utc` changes); the content cache under data/raw makes the ~30k-file
fetch resumable. A per-symbol fetch FAILURE is fatal (a silent drop would reintroduce
survivorship through the build harness, ADR 0005 caveat 4); a symbol with no data in the
window is simply absent (not a failure).
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from riskpremia.ctrend.artifact import PanelFingerprint, build_artifact, dump_artifact
from riskpremia.ctrend.errors import CtrendError
from riskpremia.ctrend.fixtures import (
    daily_panel_content_sha256,
    read_daily_panel,
    write_daily_panel_gz,
)
from riskpremia.ctrend.universe import (
    N_MAX_COMMITTED,
    build_daily_panel,
    build_weekly_panel,
    eligible_pairs,
    ever_eligible_symbols,
    pit_eligible,
    tradeable_universe,
    trim_daily_to,
)
from riskpremia.data.manifest import SnapshotEntry, compute_sha256, upsert_entries
from riskpremia.data.records import SpotKlineRecord
from riskpremia.data.sources.binance_vision import BinanceVisionSource

_REPO = Path(__file__).resolve().parents[1]
_PANEL_FIXTURE = _REPO / "tests" / "data" / "ctrend_daily_panel_usdt.csv.gz"
_ARTIFACT = _REPO / "artifacts" / "ctrend_universe.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"

_PANEL_RELPATH = _PANEL_FIXTURE.relative_to(_REPO).as_posix()
_SOURCE_URL = (
    "https://data.binance.vision/data/spot/monthly/klines/<SYMBOL>/1d/ "
    "(close=col4, quote_volume=col7)"
)
_NOTE = (
    "Committed in-repo reproducibility fixture (gzipped CSV date,symbol,close,dollar_volume): "
    "the delisting-complete USDT daily panel TRIMMED to the coins ever in the top-N_MAX liquid "
    "set. This sha256 is the committed .gz blob's FILE hash (tamper-evidence of the committed "
    "bytes); the artifact fingerprint pins the decompressed-CONTENT hash (the cross-platform "
    "integrity check). The raw monthly zips carry their own published checksums. Regenerate via "
    "scripts/build_ctrend_universe.py."
)


def _fetch_one(
    source: BinanceVisionSource, symbol: str, interval: str, start: datetime, end: datetime
) -> tuple[str, list[SpotKlineRecord]]:
    """Fetch one symbol's daily klines; the symbol travels with the records for logging."""
    return symbol, source.fetch_spot_klines(symbol, interval, start, end)


def _fetch_universe(
    source: BinanceVisionSource,
    symbols: tuple[str, ...],
    interval: str,
    start: datetime,
    end: datetime,
    *,
    workers: int,
) -> list[SpotKlineRecord]:
    """Concurrently fetch every symbol; a fetch failure is fatal (no silent drop, M3)."""
    records: list[SpotKlineRecord] = []
    n_with_data = 0
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_one, source, s, interval, start, end): s for s in symbols
        }
        for fut in as_completed(futures):
            symbol = futures[fut]
            try:
                _sym, recs = fut.result()
            except Exception as exc:  # fatal: a silent drop would reintroduce survivorship
                raise CtrendError(
                    f"fetch failed for {symbol!r} ({type(exc).__name__}: {exc}); a fetch "
                    f"failure is fatal so a tradeable coin is never silently dropped"
                ) from exc
            records.extend(recs)
            done += 1
            if recs:
                n_with_data += 1
            if done % 50 == 0 or done == len(symbols):
                print(f"  fetched {done}/{len(symbols)} symbols ({n_with_data} with data)")
    print(f"  total daily rows: {len(records)} across {n_with_data} symbols with data")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the committed CTREND universe panel.")
    parser.add_argument("--quote", default="USDT")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--start", default="2019-01-01")
    parser.add_argument("--end", default="2026-06-01")
    parser.add_argument("--top-n", type=int, default=100)
    parser.add_argument("--lookback-weeks", type=int, default=4)
    parser.add_argument("--min-history-weeks", type=int, default=8)
    parser.add_argument("--n-max", type=int, default=N_MAX_COMMITTED)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cache", default=str(_REPO / "data" / "raw"))
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=0,
        help="cap the candidate count for a fast pipeline smoke test (0 = the full universe)",
    )
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
    lookback, min_hist, top_n, n_max = (
        args.lookback_weeks, args.min_history_weeks, args.top_n, args.n_max,
    )
    knobs = {"lookback_weeks": lookback, "min_history_weeks": min_hist}
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    source = BinanceVisionSource(cache, max_fetch_attempts=4, retry_backoff_s=1.0)

    print(f"Enumerating {args.quote} spot symbols (delisting-complete) ...")
    enumerated = source.list_spot_symbols(args.quote)
    candidates = tradeable_universe(enumerated, quote=args.quote)
    print(f"  enumerated={len(enumerated)}  tradeable (post-exclusion)={len(candidates)}")
    if args.max_symbols > 0:
        candidates = candidates[: args.max_symbols]
        print(f"  SMOKE TEST: capped to the first {len(candidates)} candidates")

    print(f"Fetching daily klines ({args.interval}, {start.date()}..{end.date()}) ...")
    records = _fetch_universe(
        source, candidates, args.interval, start, end, workers=args.workers
    )
    if not records:
        raise CtrendError("no daily records fetched; check the window and the network")

    daily_full = build_daily_panel(records)
    weekly_full = build_weekly_panel(daily_full)
    ever = ever_eligible_symbols(
        weekly_full, top_n=n_max, lookback_weeks=lookback, min_history_weeks=min_hist
    )
    print(f"  daily rows={daily_full.height}  symbols={daily_full['symbol'].n_unique()}  "
          f"ever-top-{n_max}={len(ever)}")

    daily_trimmed = trim_daily_to(daily_full, ever)
    weekly_trimmed = build_weekly_panel(daily_trimmed)

    # Losslessness assertion (design review): trimming to ever-top-N_MAX must not change any
    # week's top-N_MAX selection.
    full_pairs = eligible_pairs(weekly_full, top_n=n_max, **knobs)
    trimmed_pairs = eligible_pairs(weekly_trimmed, top_n=n_max, **knobs)
    if full_pairs != trimmed_pairs:
        raise CtrendError(
            f"trim is NOT lossless at top_n={n_max}: "
            f"{len(full_pairs ^ trimmed_pairs)} differing (week, symbol) eligibility pairs"
        )
    print(f"  losslessness OK: {len(full_pairs)} eligible (week, symbol) pairs preserved at "
          f"top_n={n_max}")

    committed_records = [r for r in records if r.instrument.symbol in set(ever)]
    write_daily_panel_gz(_PANEL_FIXTURE, committed_records)
    daily_committed = read_daily_panel(_PANEL_FIXTURE)
    weekly_committed = build_weekly_panel(daily_committed)

    # Fidelity: the committed CSV reproduces the live top-N eligibility exactly.
    live_top_n = eligible_pairs(weekly_full, top_n=top_n, **knobs)
    committed_top_n = eligible_pairs(weekly_committed, top_n=top_n, **knobs)
    if live_top_n != committed_top_n:
        raise CtrendError(
            f"FIDELITY FAILURE: the committed panel does not reproduce the live top-{top_n} "
            f"eligibility ({len(live_top_n ^ committed_top_n)} differing pairs)"
        )
    print(f"  fidelity OK: committed panel reproduces the live top-{top_n} eligibility "
          f"({len(committed_top_n)} pairs)")

    flagged = pit_eligible(weekly_committed, top_n=top_n, **knobs)
    fingerprint = PanelFingerprint(
        panel_sha256=daily_panel_content_sha256(_PANEL_FIXTURE),  # the decompressed-content SHA
        n_panel_rows=daily_committed.height,
        panel_relpath=_PANEL_RELPATH,
    )
    artifact = build_artifact(
        flagged,
        daily_committed,
        enumerated,
        quote=args.quote,
        interval=args.interval,
        top_n=top_n,
        lookback_weeks=lookback,
        min_history_weeks=min_hist,
        n_max_committed=n_max,
        fingerprint=fingerprint,
    )
    dump_artifact(artifact, _ARTIFACT)

    when = datetime.now(UTC).replace(microsecond=0)
    upsert_entries(
        _MANIFEST,
        (
            SnapshotEntry(
                name="ctrend-daily-panel-usdt",
                venue="binance_vision",
                instrument=f"USDT spot universe ({artifact.n_symbols_in_committed_panel} coins)",
                kind="reproducibility_fixture",
                relpath=_PANEL_RELPATH,
                source_url=_SOURCE_URL,
                fetched_utc=when,
                sha256=compute_sha256(_PANEL_FIXTURE),  # the committed .gz blob's file SHA
                size_bytes=_PANEL_FIXTURE.stat().st_size,
                rows=daily_committed.height,
                published_checksum=None,
                note=_NOTE,
            ),
        ),
    )

    size_mb = _PANEL_FIXTURE.stat().st_size / 1_000_000
    print(
        f"\n[CTREND universe {artifact.window_start}..{artifact.window_end}] "
        f"enumerated={artifact.n_symbols_enumerated} excluded={artifact.n_symbols_excluded} "
        f"committed={artifact.n_symbols_in_committed_panel} ever_top_{top_n}="
        f"{artifact.n_ever_eligible} weeks={artifact.n_weeks}"
    )
    with pl.Config(tbl_rows=6):
        print(flagged.filter(pl.col("eligible")).group_by("week_end").len().sort("week_end").tail(3))
    print(f"Wrote {_PANEL_RELPATH} ({size_mb:.1f} MB)")
    print(f"Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")
    print(f"Stamped the panel into {_MANIFEST.relative_to(_REPO).as_posix()}")


if __name__ == "__main__":
    main()
