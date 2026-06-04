"""Acceptance check that the vendored analytics/validation stack is faithful.

The pit-backtest project holds the authoritative, exhaustive unit tests for
these modules (they are copied verbatim from it, see each module header). This
file is the RiskPremia-side fidelity check: it pins the same canonical numerical
results the source project pins, so a reviewer of THIS repo can confirm the copy
behaves identically without cloning the sibling project, and a botched future
re-vendor surfaces immediately.
"""

from __future__ import annotations

import math

from riskpremia.analytics.bootstrap import (
    politis_white_block_length,
    stationary_block_bootstrap,
)
from riskpremia.analytics.sharpe import dsr, min_trl, psr
from riskpremia.validation.cv import CPCVSplitter, PurgedKFoldSplitter


def test_dsr_canonical_bailey_lopez_de_prado_2014() -> None:
    """The Bailey-Lopez de Prado 2014 worked example resolves to DSR ~= 0.766.

    SR_hat=1.5, T=60, gamma_3=-0.5, gamma_4=5, N=30, V[{SR_n}]=0.4. This is the
    pin pit-backtest's ADR 0013 corrected the methodology note's 0.971 against;
    reproducing it here proves the vendored Acklam inverse-CDF + Wald variance
    path is intact.
    """
    value = dsr(sr_hat=1.5, T=60, gamma_3=-0.5, gamma_4=5.0, v_sr=0.4, n_effective=30)
    assert abs(value - 0.766) < 1e-3


def test_psr_degenerate_and_min_trl_finite() -> None:
    """PSR is a probability in [0, 1]; MinTRL is finite when sr_hat > sr_star."""
    p = psr(sr_hat=1.5, sr_star=0.0, T=60, gamma_3=-0.5, gamma_4=5.0)
    assert 0.0 <= p <= 1.0
    trl = min_trl(sr_hat=1.0, sr_star=0.0, alpha=0.05, gamma_3=0.0, gamma_4=3.0)
    assert math.isfinite(trl) and trl > 1.0


def test_dsr_single_trial_degenerates_to_psr() -> None:
    """n_effective=1 degenerates to PSR against a zero benchmark (no deflation)."""
    d = dsr(sr_hat=1.0, T=120, gamma_3=0.0, gamma_4=3.0, v_sr=0.0, n_effective=1)
    p = psr(sr_hat=1.0, sr_star=0.0, T=120, gamma_3=0.0, gamma_4=3.0)
    assert d == p


def test_cpcv_path_count_6_2_is_5() -> None:
    """CPCV(N=6, k=2) yields phi(6,2) = (2/6) * C(6,2) = 5 paths."""
    assert CPCVSplitter(n_groups=6, k_test=2).expected_path_count() == 5


def test_cpcv_path_assignments_invariants() -> None:
    """Each combination index appears exactly k_test times across the path map."""
    splitter = CPCVSplitter(n_groups=6, k_test=2)
    paths = splitter.path_assignments()
    assert len(paths) == splitter.expected_path_count()
    counts: dict[int, int] = {}
    for path in paths:
        assert len(path) == 6
        for combo_idx in path:
            counts[combo_idx] = counts.get(combo_idx, 0) + 1
    assert set(counts.values()) == {2}


def test_purged_kfold_constructs() -> None:
    """The purged k-fold splitter constructs with a valid k and embargo."""
    splitter = PurgedKFoldSplitter(k=5, embargo_pct=0.01)
    assert splitter is not None


def test_bootstrap_is_seed_deterministic() -> None:
    """Same seed + same call sequence -> byte-identical resampled paths."""
    series = [0.01, -0.02, 0.03, 0.0, 0.015, -0.005, 0.02]
    a = stationary_block_bootstrap(series, 4, expected_block_length=2.5, seed=7)
    b = stationary_block_bootstrap(series, 4, expected_block_length=2.5, seed=7)
    assert a == b
    assert len(a) == 4 and all(len(p) == len(series) for p in a)


def test_politis_white_short_series_returns_one() -> None:
    """A series too short to estimate the spectrum (n < 11) returns 1.0."""
    assert politis_white_block_length([0.01, -0.01, 0.02]) == 1.0
