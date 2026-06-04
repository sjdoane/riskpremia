"""The SHA256 manifest: checksum parsing, verify, and write/read round-trip."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from riskpremia.data.errors import ChecksumMismatchError, SnapshotMismatchError, VenueFetchError
from riskpremia.data.manifest import (
    SnapshotEntry,
    compute_sha256,
    load_manifest,
    parse_checksum_line,
    upsert_entries,
    verify_sha256,
    verify_snapshot,
)

# The real published Binance Vision CHECKSUM line for BTCUSDT-fundingRate-2020-01.zip.
_REAL_CHECKSUM_LINE = (
    "7f81b2f3694d13779e7e896b69d60cd61e9444d7b9f9e90df761935e1c1b76e2  "
    "BTCUSDT-fundingRate-2020-01.zip"
)


def test_parse_checksum_line_real_format() -> None:
    sha, filename = parse_checksum_line(_REAL_CHECKSUM_LINE)
    assert sha == "7f81b2f3694d13779e7e896b69d60cd61e9444d7b9f9e90df761935e1c1b76e2"
    assert filename == "BTCUSDT-fundingRate-2020-01.zip"


def test_parse_checksum_line_rejects_malformed() -> None:
    with pytest.raises(VenueFetchError):
        parse_checksum_line("not-a-checksum")
    with pytest.raises(VenueFetchError):
        parse_checksum_line("zzzz  file.zip")  # not hex


def test_compute_and_verify_sha256(tmp_path: Path) -> None:
    f = tmp_path / "blob.bin"
    f.write_bytes(b"hello riskpremia")
    expected = hashlib.sha256(b"hello riskpremia").hexdigest()
    assert compute_sha256(f) == expected
    verify_sha256(f, expected)  # no raise
    with pytest.raises(ChecksumMismatchError):
        verify_sha256(f, "0" * 64)


def _entry(name: str, sha: str, size: int, rel: str) -> SnapshotEntry:
    return SnapshotEntry(
        name=name,
        venue="binance_vision",
        instrument="BTCUSDT",
        kind="funding_rate",
        relpath=rel,
        source_url="https://data.binance.vision/x.zip",
        fetched_utc=datetime(2026, 6, 3, tzinfo=UTC),
        sha256=sha,
        size_bytes=size,
        rows=93,
        published_checksum=sha,
    )


def test_manifest_upsert_roundtrip_and_preamble(tmp_path: Path) -> None:
    path = tmp_path / "manifest.toml"
    preamble = "# header comment\n# kept verbatim\n\n# (empty until the first pull)\n"
    path.write_text(preamble, encoding="utf-8")
    e1 = _entry("b-2020-01", "a" * 64, 825, "binance_vision/BTCUSDT/x1.zip")
    e2 = _entry("a-2020-02", "b" * 64, 900, "binance_vision/BTCUSDT/x2.zip")
    upsert_entries(path, (e1, e2))

    loaded = load_manifest(path)
    assert [e.name for e in loaded] == ["a-2020-02", "b-2020-01"]  # sorted by name
    assert loaded[0].size_bytes == 900
    assert "# header comment" in path.read_text(encoding="utf-8")  # preamble preserved

    # upsert again overrides by name, preserves the other.
    e1b = _entry("b-2020-01", "c" * 64, 826, "binance_vision/BTCUSDT/x1.zip")
    upsert_entries(path, (e1b,))
    reloaded = {e.name: e for e in load_manifest(path)}
    assert reloaded["b-2020-01"].sha256 == "c" * 64
    assert reloaded["a-2020-02"].sha256 == "b" * 64


def test_verify_snapshot_detects_drift(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    (raw_root / "binance_vision" / "BTCUSDT").mkdir(parents=True)
    blob = raw_root / "binance_vision" / "BTCUSDT" / "x1.zip"
    blob.write_bytes(b"the real bytes")
    sha = compute_sha256(blob)
    entry = _entry("b-2020-01", sha, blob.stat().st_size, "binance_vision/BTCUSDT/x1.zip")
    verify_snapshot(entry, raw_root)  # no raise

    blob.write_bytes(b"tampered bytes!")  # different content
    with pytest.raises(SnapshotMismatchError):
        verify_snapshot(entry, raw_root)


def test_committed_manifest_has_vrp_fixture_snapshots() -> None:
    # The committed manifest now stamps the two VRP reproducibility fixtures (ADR 0004
    # PR5b). Assert they are present and their SHA256 matches the committed bytes, so a
    # tampered fixture is caught offline in CI (design review L1).
    repo = Path(__file__).resolve().parents[2]
    entries = {e.name: e for e in load_manifest(repo / "data" / "snapshots" / "manifest.toml")}
    assert {"deribit-dvol-BTC", "binance-vision-spot-BTCUSDT-1d"} <= set(entries)
    for entry in entries.values():
        if entry.kind == "reproducibility_fixture":
            assert entry.published_checksum is None  # live source, no vendor checksum
            assert entry.note  # provenance note travels with the fixture
            assert compute_sha256(repo / entry.relpath) == entry.sha256
            verify_snapshot(entry, repo)  # no raise


def test_note_field_roundtrips(tmp_path: Path) -> None:
    path = tmp_path / "manifest.toml"
    entry = SnapshotEntry(
        name="fix", venue="deribit", instrument="BTCUSDT", kind="reproducibility_fixture",
        relpath="tests/data/x.csv", source_url="u", fetched_utc=datetime(2026, 6, 4, tzinfo=UTC),
        sha256="a" * 64, size_bytes=10, rows=5, published_checksum=None, note="a provenance note",
    )
    upsert_entries(path, (entry,))
    loaded = load_manifest(path)
    assert loaded[0].note == "a provenance note"
    assert loaded[0].published_checksum is None


def test_upsert_preserves_commented_snapshot_marker_in_preamble(tmp_path: Path) -> None:
    # A documentation preamble that includes a commented "[[snapshot]]" example must be
    # kept verbatim; a plain str.find would match the comment and truncate the docs.
    path = tmp_path / "manifest.toml"
    path.write_text(
        '# docs\n# example block:\n# [[snapshot]]\n# name = "example"\n',
        encoding="utf-8",
    )
    upsert_entries(path, (_entry("a-2020-01", "a" * 64, 10, "binance_vision/BTCUSDT/x.zip"),))
    text = path.read_text(encoding="utf-8")
    assert "# [[snapshot]]" in text  # the commented example survived the upsert
    assert '# name = "example"' in text
    assert [x.name for x in load_manifest(path)] == ["a-2020-01"]
