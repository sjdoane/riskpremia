"""Build the committed Layer-i VRP artifact + figures fixtures from the real data.

A manual, one-time research entry point (not a CI step), the VRP analogue of
`run_null_gate.py`. It fetches the live Deribit DVOL index + the Binance Vision daily
spot closes, writes the committed CSV fixtures, PROVES the committed fixtures reproduce
the live headline (the fidelity check), builds the regenerable JSON artifact, and
SHA256-stamps both fixtures into the snapshot manifest (ADR 0004 PR5b, the M1 gating
item). Run with the dedicated venv from the repo root:

  $env:PYTHONIOENCODING="utf-8"
  C:\\Users\\SamJD\\.venvs\\riskpremia\\Scripts\\python.exe -m scripts.build_vrp_artifact

DVOL is a LIVE / as-of series: a re-run may produce slightly different closes (and a
refreshed manifest stamp), which is expected. The COMMITTED fixtures + artifact are
the pinned reference; the offline test reproduces the committed headline from them.
After running, render the figures with `scripts.regenerate_figures`.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from riskpremia.data.manifest import SnapshotEntry, compute_sha256, upsert_entries
from riskpremia.data.records import DvolRecord, SpotPriceRecord
from riskpremia.data.sources.binance_vision import BinanceVisionSource
from riskpremia.data.sources.deribit_dvol import DeribitDVOLSource
from riskpremia.vrp.artifact import DatasetFingerprint, build_artifact, dump_artifact
from riskpremia.vrp.fixtures import (
    read_dvol_csv,
    read_spot_csv,
    write_dvol_csv,
    write_spot_csv,
)
from riskpremia.vrp.measurement import VrpHeadline, build_vrp_frame, vrp_headline

_REPO = Path(__file__).resolve().parents[1]
_DVOL_FIXTURE = _REPO / "tests" / "data" / "deribit_dvol_btc.csv"
_SPOT_FIXTURE = _REPO / "tests" / "data" / "binance_spot_btcusdt_1d.csv"
_ARTIFACT = _REPO / "artifacts" / "vrp_measurement.json"
_MANIFEST = _REPO / "data" / "snapshots" / "manifest.toml"

_DVOL_SOURCE_URL = (
    "https://www.deribit.com/api/v2/public/get_volatility_index_data "
    "(currency=BTC, resolution=1D)"
)
_SPOT_SOURCE_URL = (
    "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/ (close = column 4)"
)
_DVOL_NOTE = (
    "Committed in-repo reproducibility fixture (date,dvol_close). DVOL is a live/as-of "
    "series with no published checksum; this SHA256 attests tamper-evidence of the "
    "committed daily closes, not vendor byte-fidelity. Regenerate via "
    "scripts/build_vrp_artifact.py."
)
_SPOT_NOTE = (
    "Committed in-repo reproducibility fixture (date,close), a daily-close extract of "
    "the Binance Vision spot klines (BTCUSDT, 1d). Pinned so the headline reproduces "
    "offline from a clone; the underlying monthly zips carry their own published "
    "checksums."
)


def _headline(
    dvol: list[DvolRecord], spot: list[SpotPriceRecord], *, window: int, seed: int, n_boot: int
) -> tuple[VrpHeadline, pl.DataFrame]:
    frame = build_vrp_frame(dvol, spot, window_days=window)
    return vrp_headline(frame, window_days=window, seed=seed, n_boot=n_boot), frame


def _stamp(
    name: str, relpath: str, path: Path, url: str, note: str, rows: int, when: datetime
) -> SnapshotEntry:
    return SnapshotEntry(
        name=name,
        venue="deribit" if "deribit" in name else "binance_vision",
        instrument="BTCUSDT",
        kind="reproducibility_fixture",
        relpath=relpath,
        source_url=url,
        fetched_utc=when,
        sha256=compute_sha256(path),
        size_bytes=path.stat().st_size,
        rows=rows,
        published_checksum=None,
        note=note,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the committed VRP measurement artifact.")
    parser.add_argument("--dvol-start", default="2022-01-01")
    parser.add_argument("--dvol-end", default="2025-06-01")
    parser.add_argument("--spot-start", default="2021-11-20")
    parser.add_argument("--spot-end", default="2025-07-15")
    parser.add_argument("--window", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260604)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--cache", default=str(_REPO / "data" / "raw"))
    args = parser.parse_args()

    window, seed, n_boot = args.window, args.seed, args.n_boot
    dvol_start = datetime.fromisoformat(args.dvol_start).replace(tzinfo=UTC)
    dvol_end = datetime.fromisoformat(args.dvol_end).replace(tzinfo=UTC)
    spot_start = datetime.fromisoformat(args.spot_start).replace(tzinfo=UTC)
    spot_end = datetime.fromisoformat(args.spot_end).replace(tzinfo=UTC)
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    print(f"Fetching Deribit DVOL (BTC, {dvol_start.date()}..{dvol_end.date()}) ...")
    dvol_live = DeribitDVOLSource().fetch_dvol("BTC", dvol_start, dvol_end)
    print(f"Fetching Binance Vision spot (BTCUSDT 1d, {spot_start.date()}..{spot_end.date()}) ...")
    spot_live = BinanceVisionSource(cache).fetch_spot(
        "BTCUSDT", "USDT", "1d", spot_start, spot_end
    )
    print(f"  DVOL rows={len(dvol_live)}  spot rows={len(spot_live)}")

    # Write the committed fixtures, then PROVE they reproduce the live headline exactly
    # (the H1 fidelity check): the committed anchor equals the live extraction at build.
    write_dvol_csv(_DVOL_FIXTURE, dvol_live)
    write_spot_csv(_SPOT_FIXTURE, spot_live)
    dvol_fix = read_dvol_csv(_DVOL_FIXTURE)
    spot_fix = read_spot_csv(_SPOT_FIXTURE)

    h_live, _ = _headline(dvol_live, spot_live, window=window, seed=seed, n_boot=n_boot)
    h_fix, frame_fix = _headline(dvol_fix, spot_fix, window=window, seed=seed, n_boot=n_boot)
    if h_live != h_fix:
        raise SystemExit(
            "FIDELITY FAILURE: the committed fixtures do not reproduce the live headline; "
            f"live={h_live} fixture={h_fix}"
        )
    print("Fidelity check PASSED: committed fixtures reproduce the live headline exactly.")

    fingerprint = DatasetFingerprint(
        dvol_sha256=compute_sha256(_DVOL_FIXTURE),
        spot_sha256=compute_sha256(_SPOT_FIXTURE),
        n_dvol_rows=len(dvol_fix),
        n_spot_rows=len(spot_fix),
        dvol_relpath=_DVOL_FIXTURE.relative_to(_REPO).as_posix(),
        spot_relpath=_SPOT_FIXTURE.relative_to(_REPO).as_posix(),
    )
    artifact = build_artifact(
        frame_fix,
        h_fix,
        currency="BTC",
        window_days=window,
        seed=seed,
        n_boot=n_boot,
        fingerprint=fingerprint,
        n_dvol_days=len(dvol_fix),
        n_spot_days=len(spot_fix),
    )
    dump_artifact(artifact, _ARTIFACT)

    when = datetime.now(UTC).replace(microsecond=0)
    upsert_entries(
        _MANIFEST,
        (
            _stamp("deribit-dvol-BTC", fingerprint.dvol_relpath, _DVOL_FIXTURE,
                   _DVOL_SOURCE_URL, _DVOL_NOTE, len(dvol_fix), when),
            _stamp("binance-vision-spot-BTCUSDT-1d", fingerprint.spot_relpath, _SPOT_FIXTURE,
                   _SPOT_SOURCE_URL, _SPOT_NOTE, len(spot_fix), when),
        ),
    )

    h = artifact.headline
    print(
        f"\n[BTC VRP {artifact.date_start}..{artifact.date_end}, {window}d] "
        f"median-phase mean={h.mean_phase_median:.5f} "
        f"band=[{h.mean_phase_min:.5f},{h.mean_phase_max:.5f}] "
        f"phase0 95CI=[{h.ci_low:.5f},{h.ci_high:.5f}] eff_T={h.effective_t:.0f} "
        f"frac_pos={h.frac_positive:.2f} pre_etf={h.mean_vrp_pre_etf:.5f} "
        f"post_etf={h.mean_vrp_post_etf:.5f}"
    )
    print(f"Wrote {_ARTIFACT.relative_to(_REPO).as_posix()}")
    print(f"Wrote {fingerprint.dvol_relpath} + {fingerprint.spot_relpath}")
    print(f"Stamped both fixtures into {_MANIFEST.relative_to(_REPO).as_posix()}")
    print("Next: render the figures with `python -m scripts.regenerate_figures`.")


if __name__ == "__main__":
    main()
