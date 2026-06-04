"""The contract test: the data layer's output feeds the vendored CPCV.

This is the single most load-bearing test in PR1. The whole point of the milestone
is that a funding-event observation frame plus its label horizons satisfy the
`CPCVSplitter.split` contract (sorted `dt` of `pl.Datetime("us","UTC")`, a
matching-dtype non-null `label_horizons` series of equal length), so the
event-time-purged cross-validation the kill gate runs under is fed correct data.
"""

from __future__ import annotations

from decimal import Decimal

from riskpremia.data.clock import (
    build_observation_frame,
    make_label_horizons,
    ms_to_utc,
    normalize_funding_frame,
)
from riskpremia.data.records import FundingRecord, InstrumentId
from riskpremia.validation.cv import CPCVSplitter, PurgedKFoldSplitter

_START_MS = 1_577_836_800_000
_8H_MS = 8 * 3600 * 1000


def _realistic_funding(n: int) -> list[FundingRecord]:
    """An 8h-grid funding series with mildly varying rates (in-band, not gross)."""
    inst = InstrumentId.of("binance_vision", "BTCUSDT")
    out: list[FundingRecord] = []
    for i in range(n):
        rate = -0.0001 + 0.00002 * ((i % 7) - 3)  # oscillates around zero
        out.append(
            FundingRecord(
                instrument=inst,
                funding_ts=ms_to_utc(_START_MS + i * _8H_MS),
                funding_rate=Decimal(str(round(rate, 8))),
                funding_interval_hours=8,
                realized=True,
            )
        )
    return out


def test_observation_frame_feeds_cpcv_split() -> None:
    obs_full = build_observation_frame(normalize_funding_frame(_realistic_funding(200)))
    observations, horizons = make_label_horizons(obs_full, horizon_events=3)

    splitter = CPCVSplitter(n_groups=6, k_test=2)
    assert splitter.expected_path_count() == 5

    splits = list(splitter.split(observations, horizons))
    assert len(splits) == 15  # C(6, 2)

    for split in splits:
        # cv.py guarantees disjointness; assert the contract here too.
        train = set(split.train_indices)
        test = set(split.test_indices)
        assert train.isdisjoint(test)
        assert len(test) > 0
        # purged + embargoed indices are removed from train, never in test.
        assert set(split.purged_indices).isdisjoint(test)


def test_observation_frame_feeds_purged_kfold() -> None:
    obs_full = build_observation_frame(normalize_funding_frame(_realistic_funding(120)))
    observations, horizons = make_label_horizons(obs_full, horizon_events=2)
    splits = list(PurgedKFoldSplitter(k=5, embargo_pct=0.01).split(observations, horizons))
    assert len(splits) == 5
    # every fold's test set is non-empty and the union covers all rows once.
    covered = sorted(idx for s in splits for idx in s.test_indices)
    assert covered == list(range(observations.height))
