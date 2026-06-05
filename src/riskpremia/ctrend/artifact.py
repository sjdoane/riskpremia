"""The committed CTREND universe artifact (ADR 0005 PR1).

A regenerable JSON summary of the point-in-time, delisting-complete universe: the knobs,
the symbol counts, the full excluded-symbol list (so a missed stablecoin is visible to a
reviewer), a delisting proof (named dead coins ARE in the panel and stop trading), the
per-week eligible breadth, the dataset fingerprint, and the binding caveats. It carries no
raw vendor data; the daily closes live in the committed CSV fixture whose SHA256 the
`fingerprint` pins.

Panel-derived fields (the eligible-by-week series, the delisting proof, the ever-eligible
count, the panel row/week counts, the fingerprint) are pure functions of the committed
daily panel and are reproduced offline by a test. The build-time provenance fields (the
enumerated count, the excluded list) come from the live S3 enumeration and are recorded,
not re-derived offline (the analogue of the VRP artifact's alignment counts).

Determinism mirrors `vrp/artifact.py`: `json.dumps(sort_keys=True, indent=2,
allow_nan=False)`, LF newlines (`.gitattributes` pins `artifacts/**/*.json eol=lf`).
Stdlib + attrs + polars only; matplotlib is never imported here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import attrs
import polars as pl

from riskpremia.ctrend.errors import CtrendError
from riskpremia.ctrend.universe import (
    eligible_count_per_week,
    excluded_symbols,
)

SCHEMA_VERSION = 1
_STUDY = "crypto cross-sectional trend factor (CTREND, Study 3): the PIT universe data layer"

KNOWN_DELISTED: tuple[str, ...] = (
    "LUNAUSDT", "FTTUSDT", "BCCUSDT", "VENUSDT", "USTUSDT", "SRMUSDT",
)
"""Famously-delisted coins used as a live survivorship proof: each must be present in the
delisting-complete panel (if it ever made the committed liquid set) and stop trading at a
plausible date. The proof is emitted into the artifact and asserted by the reproduction
test (design review L6)."""

CAVEATS: tuple[str, ...] = (
    "The universe is screened by trailing USD DOLLAR VOLUME (top-N), a deliberate "
    "deviation from the paper's market-cap floor: Binance Vision has no market cap. The "
    "paper's closest analogue is its Table 8 'top-100 most liquid' subset (Amihud).",
    "Single-venue (Binance spot) vs the paper's CoinMarketCap cross-venue aggregate; a "
    "small price and liquidity-ranking basis.",
    "Stablecoin/fiat pairs and Binance leveraged tokens are excluded (a USD peg has no "
    "trend signal and would dominate a dollar-volume-ranked universe; the paper's 'coins' "
    "are not pegs or decaying derivatives). The full excluded list is in this artifact.",
    "Point-in-time: the liquidity rank at week t uses only data at or before t. "
    "Survivorship-safe: delisting is handled by absence (a dead coin's earlier weeks still "
    "rank); the panel includes dead coins enumerated from the S3 bucket.",
    "The committed daily panel is TRIMMED to the coins ever in the top-N_MAX; the build "
    "asserts this trim is lossless for any top-N (N <= N_MAX). A ticker rename (e.g. LUNA "
    "-> LUNC) appears as a delisting plus a fresh listing; the dead leg is retained.",
)


@attrs.frozen(slots=True)
class ExcludedSymbol:
    """One enumerated symbol excluded from the universe, with the reason."""

    symbol: str
    reason: str


@attrs.frozen(slots=True)
class DelistingProof:
    """A named delisted coin's presence + last trading week in the committed panel."""

    symbol: str
    present: bool
    last_week: str | None


@attrs.frozen(slots=True)
class EligibleByWeek:
    """The per-week eligible-symbol count (the universe breadth over time).

    Weeks with zero eligible coins are OMITTED (the early weeks before any coin has the
    minimum history), so this series can be shorter than `n_weeks` (the full grid).
    """

    week_end: tuple[str, ...]
    n_eligible: tuple[int, ...]


@attrs.frozen(slots=True)
class PanelFingerprint:
    """The content-addressed pin: the committed panel's decompressed-content SHA256 + shape.

    `panel_sha256` is the SHA256 of the DECOMPRESSED CSV content (cross-platform stable),
    not the `.gz` container bytes; the snapshot manifest separately stamps the committed
    `.gz` blob's file SHA256. `panel_relpath` points at the committed `.csv.gz`.
    """

    panel_sha256: str
    n_panel_rows: int
    panel_relpath: str


@attrs.frozen(slots=True)
class UniverseArtifact:
    """The committed PR1 deliverable: the reproducible universe summary."""

    schema_version: int
    study: str
    quote: str
    interval: str
    window_start: str
    window_end: str
    top_n: int
    lookback_weeks: int
    min_history_weeks: int
    n_max_committed: int
    n_symbols_enumerated: int
    n_symbols_excluded: int
    n_symbols_in_committed_panel: int
    n_ever_eligible: int
    n_weeks: int
    excluded: tuple[ExcludedSymbol, ...]
    delisting_proof: tuple[DelistingProof, ...]
    eligible_by_week: EligibleByWeek
    fingerprint: PanelFingerprint
    caveats: tuple[str, ...]


def _last_week_for(flagged: pl.DataFrame, symbol: str) -> str | None:
    sub = flagged.filter(pl.col("symbol") == symbol)
    if sub.height == 0:
        return None
    return str(sub["week_end"].max())


def build_artifact(
    flagged_weekly: pl.DataFrame,
    daily_committed: pl.DataFrame,
    enumerated_symbols: tuple[str, ...],
    *,
    quote: str,
    interval: str,
    top_n: int,
    lookback_weeks: int,
    min_history_weeks: int,
    n_max_committed: int,
    fingerprint: PanelFingerprint,
) -> UniverseArtifact:
    """Assemble the universe artifact from the eligibility-flagged weekly panel.

    `flagged_weekly` is the output of `pit_eligible` at `top_n`; `daily_committed` the
    committed daily panel; `enumerated_symbols` the full live S3 enumeration (for the
    excluded list and the enumerated count, build-time provenance).

    Raises:
      CtrendError: on an empty weekly panel.
    """
    if flagged_weekly.height == 0:
        raise CtrendError("build_artifact requires a non-empty weekly panel")
    excluded = excluded_symbols(enumerated_symbols, quote=quote)
    ever = flagged_weekly.filter(pl.col("eligible"))["symbol"].unique().to_list()
    by_week = eligible_count_per_week(flagged_weekly)
    weeks = [str(w) for w in flagged_weekly["week_end"].unique().sort().to_list()]
    proof = tuple(
        DelistingProof(
            symbol=s,
            present=flagged_weekly.filter(pl.col("symbol") == s).height > 0,
            last_week=_last_week_for(flagged_weekly, s),
        )
        for s in KNOWN_DELISTED
    )
    return UniverseArtifact(
        schema_version=SCHEMA_VERSION,
        study=_STUDY,
        quote=quote,
        interval=interval,
        window_start=weeks[0],
        window_end=weeks[-1],
        top_n=top_n,
        lookback_weeks=lookback_weeks,
        min_history_weeks=min_history_weeks,
        n_max_committed=n_max_committed,
        n_symbols_enumerated=len(enumerated_symbols),
        n_symbols_excluded=len(excluded),
        n_symbols_in_committed_panel=daily_committed["symbol"].n_unique(),
        n_ever_eligible=len(ever),
        n_weeks=len(weeks),
        excluded=tuple(ExcludedSymbol(symbol=s, reason=r) for s, r in excluded),
        delisting_proof=proof,
        eligible_by_week=EligibleByWeek(
            week_end=tuple(str(w) for w in by_week["week_end"].to_list()),
            n_eligible=tuple(int(n) for n in by_week["n_eligible"].to_list()),
        ),
        fingerprint=fingerprint,
        caveats=CAVEATS,
    )


def artifact_to_json(artifact: UniverseArtifact) -> str:
    """Deterministic JSON (sorted keys, exact ints, trailing newline)."""
    return json.dumps(attrs.asdict(artifact), indent=2, sort_keys=True, allow_nan=False) + "\n"


def dump_artifact(artifact: UniverseArtifact, path: Path) -> None:
    """Write the artifact JSON with LF newlines (the committed-byte contract)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact_to_json(artifact), encoding="utf-8", newline="\n")


def _req(d: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        raise CtrendError(f"universe artifact {ctx} missing required key {key!r}")
    return d[key]


def artifact_from_dict(data: dict[str, Any]) -> UniverseArtifact:
    """Reconstruct a UniverseArtifact from parsed JSON, raising loudly on a bad shape."""
    fp = _req(data, "fingerprint", "root")
    ebw = _req(data, "eligible_by_week", "root")
    return UniverseArtifact(
        schema_version=int(_req(data, "schema_version", "root")),
        study=str(_req(data, "study", "root")),
        quote=str(_req(data, "quote", "root")),
        interval=str(_req(data, "interval", "root")),
        window_start=str(_req(data, "window_start", "root")),
        window_end=str(_req(data, "window_end", "root")),
        top_n=int(_req(data, "top_n", "root")),
        lookback_weeks=int(_req(data, "lookback_weeks", "root")),
        min_history_weeks=int(_req(data, "min_history_weeks", "root")),
        n_max_committed=int(_req(data, "n_max_committed", "root")),
        n_symbols_enumerated=int(_req(data, "n_symbols_enumerated", "root")),
        n_symbols_excluded=int(_req(data, "n_symbols_excluded", "root")),
        n_symbols_in_committed_panel=int(_req(data, "n_symbols_in_committed_panel", "root")),
        n_ever_eligible=int(_req(data, "n_ever_eligible", "root")),
        n_weeks=int(_req(data, "n_weeks", "root")),
        excluded=tuple(
            ExcludedSymbol(
                symbol=str(_req(e, "symbol", "excluded")),
                reason=str(_req(e, "reason", "excluded")),
            )
            for e in _req(data, "excluded", "root")
        ),
        delisting_proof=tuple(
            DelistingProof(
                symbol=str(_req(p, "symbol", "delisting_proof")),
                present=bool(_req(p, "present", "delisting_proof")),
                last_week=None if p.get("last_week") is None else str(p["last_week"]),
            )
            for p in _req(data, "delisting_proof", "root")
        ),
        eligible_by_week=EligibleByWeek(
            week_end=tuple(str(w) for w in _req(ebw, "week_end", "eligible_by_week")),
            n_eligible=tuple(int(n) for n in _req(ebw, "n_eligible", "eligible_by_week")),
        ),
        fingerprint=PanelFingerprint(
            panel_sha256=str(_req(fp, "panel_sha256", "fingerprint")),
            n_panel_rows=int(_req(fp, "n_panel_rows", "fingerprint")),
            panel_relpath=str(_req(fp, "panel_relpath", "fingerprint")),
        ),
        caveats=tuple(str(c) for c in _req(data, "caveats", "root")),
    )


def load_artifact(path: Path) -> UniverseArtifact:
    """Load and validate a committed universe artifact JSON into a typed object."""
    with path.open("rb") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise CtrendError(f"universe artifact {path.name} is not a JSON object")
    return artifact_from_dict(data)
