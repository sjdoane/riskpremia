"""SHA256 snapshot manifest: the data-layer determinism invariant (ADR 0002).

Raw vendor bytes are gitignored but SHA256-stamped into a committed
`data/snapshots/manifest.toml`, so a reviewer re-fetches, verifies byte-identity,
and regenerates the headline. This module reads, writes (a hand-rolled
array-of-tables emitter, no `tomli-w` dependency), and verifies that manifest, and
parses the sibling `.CHECKSUM` files Binance publishes alongside each dump.

Schema is the committed `[[snapshot]]` array-of-tables (kept over the pit-backtest
nested-table shape because it fits per-file content addressing with a source URL,
the review-locked decision). Stdlib only (`hashlib`, `tomllib`).
"""

from __future__ import annotations

import hashlib
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

import attrs

from riskpremia.data.errors import ChecksumMismatchError, SnapshotMismatchError, VenueFetchError

_CHUNK = 1024 * 1024
_SHA256_HEX_LEN = 64


def compute_sha256(path: Path) -> str:
    """Streaming SHA256 of a file's bytes (lowercase hex), 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksum_line(text: str) -> tuple[str, str]:
    """Parse a published `sha256  filename` CHECKSUM line into (sha256, filename).

    Verified Binance Vision format is the GNU `sha256sum` convention: 64 lowercase
    hex characters, two spaces, then the filename (e.g.
    `7f81b2f3...  BTCUSDT-fundingRate-2020-01.zip`). Tolerates a single space too.

    Raises:
      VenueFetchError: when the line is not a valid checksum line.
    """
    stripped = text.strip()
    parts = stripped.split(maxsplit=1)
    if len(parts) != 2:
        raise VenueFetchError(f"parse_checksum_line: not a 'sha256  filename' line: {text!r}")
    sha, filename = parts[0].lower(), parts[1].strip()
    # GNU sha256sum binary mode prefixes the filename with '*'; drop it so the
    # name matches the on-disk file (Binance Vision uses text mode, no marker).
    if filename.startswith("*"):
        filename = filename[1:]
    if len(sha) != _SHA256_HEX_LEN or any(c not in "0123456789abcdef" for c in sha):
        raise VenueFetchError(f"parse_checksum_line: {sha!r} is not 64 hex chars")
    if not filename:
        raise VenueFetchError(f"parse_checksum_line: empty filename in {text!r}")
    return sha, filename


def verify_sha256(path: Path, expected: str) -> None:
    """Raise ChecksumMismatchError if `path`'s SHA256 does not match `expected`."""
    actual = compute_sha256(path)
    if actual != expected.lower():
        raise ChecksumMismatchError(
            f"SHA256 mismatch for {path.name}: expected {expected.lower()}, got {actual}"
        )


@attrs.frozen(slots=True)
class SnapshotEntry:
    """One raw snapshot's content-addressed record.

    `relpath` locates the raw file under the (gitignored) raw root.
    `published_checksum` carries the vendor's own SHA256 where it exists (Binance),
    so a reviewer sees both the vendor commitment and ours. `rows` is the parsed
    record count where known.
    """

    name: str
    venue: str
    instrument: str
    kind: str
    relpath: str
    source_url: str
    fetched_utc: datetime
    sha256: str
    size_bytes: int
    rows: int | None = None
    published_checksum: str | None = None


def _entry_from_toml(table: dict[str, Any]) -> SnapshotEntry:
    """Build a SnapshotEntry from one parsed `[[snapshot]]` table, validating types."""
    required = (
        "name", "venue", "instrument", "kind", "relpath",
        "source_url", "fetched_utc", "sha256", "size_bytes",
    )
    for key in required:
        if key not in table:
            raise VenueFetchError(f"manifest [[snapshot]] missing required key {key!r}: {table!r}")
    fetched = table["fetched_utc"]
    if not isinstance(fetched, datetime):
        raise VenueFetchError(f"manifest fetched_utc must be a TOML datetime; got {fetched!r}")
    return SnapshotEntry(
        name=str(table["name"]),
        venue=str(table["venue"]),
        instrument=str(table["instrument"]),
        kind=str(table["kind"]),
        relpath=str(table["relpath"]),
        source_url=str(table["source_url"]),
        fetched_utc=fetched,
        sha256=str(table["sha256"]),
        size_bytes=int(table["size_bytes"]),
        rows=None if table.get("rows") is None else int(table["rows"]),
        published_checksum=(
            None if table.get("published_checksum") is None else str(table["published_checksum"])
        ),
    )


def load_manifest(path: Path) -> tuple[SnapshotEntry, ...]:
    """Load all `[[snapshot]]` entries, sorted by name (deterministic order)."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    tables = data.get("snapshot", [])
    entries = [_entry_from_toml(t) for t in tables]
    return tuple(sorted(entries, key=lambda e: e.name))


def verify_snapshot(entry: SnapshotEntry, raw_root: Path) -> None:
    """Raise SnapshotMismatchError if the on-disk raw file drifted from the entry.

    Checks both SHA256 and byte size (size is a cheap first screen and catches a
    truncated re-fetch even before the hash).
    """
    raw_path = raw_root / entry.relpath
    if not raw_path.exists():
        raise SnapshotMismatchError(
            f"snapshot {entry.name!r}: raw file {raw_path} is missing; re-fetch per "
            f"docs/methodology before regenerating"
        )
    actual_size = raw_path.stat().st_size
    if actual_size != entry.size_bytes:
        raise SnapshotMismatchError(
            f"snapshot {entry.name!r}: size {actual_size} != manifest {entry.size_bytes}"
        )
    actual_sha = compute_sha256(raw_path)
    if actual_sha != entry.sha256:
        raise SnapshotMismatchError(
            f"snapshot {entry.name!r}: sha256 {actual_sha} != manifest {entry.sha256}"
        )


def _toml_escape(value: str) -> str:
    """Escape a string for a TOML basic string (backslash, quote, control)."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _emit_entry(entry: SnapshotEntry) -> str:
    """Render one SnapshotEntry as a `[[snapshot]]` TOML block. None fields omitted."""
    lines = ["[[snapshot]]"]
    lines.append(f'name = "{_toml_escape(entry.name)}"')
    lines.append(f'venue = "{_toml_escape(entry.venue)}"')
    lines.append(f'instrument = "{_toml_escape(entry.instrument)}"')
    lines.append(f'kind = "{_toml_escape(entry.kind)}"')
    lines.append(f'relpath = "{_toml_escape(entry.relpath)}"')
    lines.append(f'source_url = "{_toml_escape(entry.source_url)}"')
    lines.append(f"fetched_utc = {entry.fetched_utc.isoformat()}")
    lines.append(f'sha256 = "{entry.sha256}"')
    lines.append(f"size_bytes = {entry.size_bytes}")
    if entry.rows is not None:
        lines.append(f"rows = {entry.rows}")
    if entry.published_checksum is not None:
        lines.append(f'published_checksum = "{entry.published_checksum}"')
    return "\n".join(lines)


def upsert_entries(path: Path, new_entries: tuple[SnapshotEntry, ...]) -> None:
    """Merge `new_entries` into the manifest by name, preserving the preamble.

    The file's preamble (everything before the first `[[snapshot]]`, i.e. the
    documentation header) is kept verbatim; existing entries are loaded, the new
    ones override by `name`, and all blocks are re-emitted sorted by name. Writes
    LF line endings (`.gitattributes` pins the file to `eol=lf`).
    """
    existing = {e.name: e for e in load_manifest(path)} if path.exists() else {}
    for entry in new_entries:
        existing[entry.name] = entry
    merged = tuple(sorted(existing.values(), key=lambda e: e.name))

    raw_text = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = "[[snapshot]]"
    idx = raw_text.find(marker)
    preamble = raw_text[:idx] if idx != -1 else raw_text
    preamble = preamble.rstrip("\n")

    blocks = "\n\n".join(_emit_entry(e) for e in merged)
    if not blocks:
        out = preamble + "\n" if preamble else ""
    elif preamble:
        out = preamble + "\n\n" + blocks + "\n"
    else:
        out = blocks + "\n"
    path.write_text(out, encoding="utf-8", newline="\n")
