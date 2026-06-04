"""The null policies, the deflated-Sharpe scoring, and the reported exhibits
(ADR 0003 PR4b). Covers the entry-selection nulls, the PSR(0) kill number, the
lumpy/amortised diagnostic, the embargo>=H glue (incl. the float-rounding edge),
and the early-gate / sign-regime / after-tax artifacts."""

from __future__ import annotations

import math
import random

import polars as pl
import pytest

from riskpremia.analytics.sharpe import psr
from riskpremia.data.clock import DT_DTYPE, ms_to_utc
from riskpremia.execution.carry import (
    funding_window_indices,
    simulate_batch,
    simulate_trade,
    valid_entry_range,
)
from riskpremia.execution.cost import ALL_VENUES, KRAKEN, VenueCostModel
from riskpremia.execution.errors import CarryComputationError, ScoringError
from riskpremia.execution.exhibit import (
    after_tax_sidebar,
    early_gate,
    funding_sign_regime,
    gate_surface,
    headline_score,
    is_killed,
)
from riskpremia.execution.scoring import (
    effective_sample_size,
    make_purged_cpcv,
    per_interval_series,
    psr_zero,
    return_moments,
)
from riskpremia.strategy.null import (
    always_on_entries,
    non_overlapping_entries,
    random_subset_entries,
)

_START_MS = 1_577_836_800_000
_8H_MS = 8 * 3600 * 1000

_ZERO_COST = VenueCostModel(
    name="zero",
    tradeable=True,
    spot_taker_bps=0.0,
    spot_maker_bps=0.0,
    perp_taker_bps=0.0,
    perp_maker_bps=0.0,
    spot_half_spread_bps=0.0,
    perp_half_spread_bps=0.0,
    source="test",
    funding_capital_rate=0.0,
)


def _frame(rates: list[float], spot: list[float], perp: list[float]) -> pl.DataFrame:
    n = len(rates)
    return pl.DataFrame(
        {
            "dt": [ms_to_utc(_START_MS + i * _8H_MS) for i in range(n)],
            "funding_rate": rates,
            "spot_close": spot,
            "perp_close": perp,
            "funding_interval_hours": [8] * n,
        },
        schema={
            "dt": DT_DTYPE,
            "funding_rate": pl.Float64,
            "spot_close": pl.Float64,
            "perp_close": pl.Float64,
            "funding_interval_hours": pl.Int32,
        },
    )


# null entry-selection policies


def test_null_entry_policies_draw_from_valid_range() -> None:
    height, horizon = 100, 7
    valid = set(valid_entry_range(height, horizon))
    assert set(always_on_entries(height, horizon)) == valid
    # non-overlapping: strided by H, every entry valid, consecutive entries don't share intervals
    for phase in range(horizon):
        entries = list(non_overlapping_entries(height, horizon, phase=phase))
        assert all(e in valid for e in entries)
        windows = [set(funding_window_indices(e, horizon)) for e in entries]
        for a, b in zip(windows, windows[1:], strict=False):
            assert a.isdisjoint(b)  # genuinely independent trades
    # random subset: deterministic, sorted, all valid, no duplicates
    r1 = random_subset_entries(height, horizon, count=10, seed=7)
    r2 = random_subset_entries(height, horizon, count=10, seed=7)
    assert r1 == r2 == sorted(r1)
    assert len(set(r1)) == 10 and all(e in valid for e in r1)
    assert random_subset_entries(height, horizon, count=10, seed=8) != r1  # seed matters


def test_null_policy_guards() -> None:
    with pytest.raises(CarryComputationError):
        non_overlapping_entries(100, 7, phase=7)  # phase must be < H
    with pytest.raises(CarryComputationError):
        random_subset_entries(100, 7, count=1, seed=True)  # bool seed rejected
    with pytest.raises(CarryComputationError):
        random_subset_entries(20, 7, count=999, seed=1)  # over-draw


# deflated-Sharpe scoring


def test_return_moments_conventions() -> None:
    # A symmetric series: skewness ~ 0; sample-std Sharpe = mean/std.
    series = [-2.0, -1.0, 0.0, 1.0, 2.0, -2.0, -1.0, 0.0, 1.0, 2.0]
    m = return_moments(series)
    assert abs(m.gamma_3) < 1e-9
    assert m.t_obs == len(series)
    assert math.isclose(m.sr_hat, m.mean / m.std, rel_tol=1e-12)
    with pytest.raises(ScoringError):
        return_moments([1.0])  # n < 2
    with pytest.raises(ScoringError):
        return_moments([3.0, 3.0, 3.0])  # zero variance


def test_psr_zero_orders_with_the_mean() -> None:
    rng_pos = [0.01 + 0.001 * ((i % 5) - 2) for i in range(60)]  # strongly positive mean
    rng_neg = [-x for x in rng_pos]
    rng_mid = [0.001 * ((i % 5) - 2) for i in range(60)]  # ~zero mean
    assert psr_zero(rng_pos) > 0.99
    assert psr_zero(rng_neg) < 0.01
    assert 0.3 < psr_zero(rng_mid) < 0.7


def test_psr_zero_deflates_t_for_an_autocorrelated_series() -> None:
    # A smooth, strongly positively-autocorrelated positive-mean series: the strided
    # trades are NOT iid, so the honest T is the block-deflated effective sample size,
    # and the deflation cannot inflate significance vs the raw observation count.
    series = [0.001 + 0.0005 * math.sin(i / 15.0) for i in range(200)]
    eff_t, pw = effective_sample_size(series)
    assert pw > 1.0  # residual serial dependence detected
    assert 2 <= eff_t < len(series)
    m = return_moments(series)
    full_t_psr = psr(m.sr_hat, 0.0, len(series), m.gamma_3, m.gamma_4)
    assert psr_zero(series) <= full_t_psr
    # A seeded iid series carries a far larger honest sample than the autocorrelated one.
    rng = random.Random(20260603)
    iid_like = [rng.gauss(0.002, 0.001) for _ in range(200)]
    eff_iid, _ = effective_sample_size(iid_like)
    assert eff_iid > eff_t


def test_per_interval_lumpy_and_amortised_both_conserve() -> None:
    rates = [0.0002 * (1 + (i % 4)) for i in range(20)]
    obs = _frame(rates, [100.0 + 0.3 * i for i in range(20)], [100.2 + 0.25 * i for i in range(20)])
    entry, horizon = 4, 5
    trade = simulate_trade(obs, entry, horizon_events=horizon, cost_model=KRAKEN)
    lumpy = per_interval_series(
        obs, [entry], horizon_events=horizon, cost_model=KRAKEN, amortise=False
    )
    amort = per_interval_series(
        obs, [entry], horizon_events=horizon, cost_model=KRAKEN, amortise=True
    )
    assert len(lumpy) == len(amort) == horizon
    assert math.isclose(sum(lumpy), trade.net_pretax, abs_tol=1e-12)
    assert math.isclose(sum(amort), trade.net_pretax, abs_tol=1e-12)
    # The placement differs: lumpy concentrates the round-trip cost on entry/exit.
    assert lumpy != amort


def test_make_purged_cpcv_embargo_covers_horizon_incl_float_edge() -> None:
    from riskpremia.validation.cv import _embargo_count

    # The float-rounding edge floor(n*(H/n)) can give H-1; the glue must not abort.
    for n_obs, horizon in [(79, 21), (55, 7), (240, 21), (2630, 21), (100, 1)]:
        splitter = make_purged_cpcv(n_obs, horizon)
        embargo_pct = max(0.05, (horizon + 0.5) / n_obs)
        assert _embargo_count(n_obs, embargo_pct) >= horizon
        assert splitter.expected_path_count() == 5  # N=6, k=2 default
    with pytest.raises(ScoringError):
        make_purged_cpcv(10, 10)  # (H+0.5)/n >= 1 -> no usable train set


# reported exhibits


def test_early_gate_headroom_and_annualization() -> None:
    # Tiny positive funding, real Kraken cost -> the round trip dwarfs the funding.
    obs = _frame([0.00008] * 40, [100.0] * 40, [100.0] * 40)
    batch = simulate_batch(obs, horizon_events=3, cost_model=KRAKEN)
    gate = early_gate(batch, KRAKEN, 3)
    assert gate.tradeable is True
    assert math.isclose(gate.median_funding, 3 * 0.00008, rel_tol=1e-6)
    assert math.isclose(gate.round_trip_cost, KRAKEN.round_trip_cost_fraction(), abs_tol=1e-15)
    assert gate.headroom < 0  # the carry does not clear cost (the early kill)
    assert gate.funding_annualized > 0


def test_headline_score_kills_a_negative_carry_and_can_pass_a_clean_one() -> None:
    # Negative net (Kraken cost, tiny varying funding) -> PSR(0) ~ 0, fails.
    rates_neg = [0.00008 + 0.00004 * ((i % 5) - 2) for i in range(60)]
    obs = _frame(rates_neg, [100.0] * 60, [100.0] * 60)
    batch = simulate_batch(obs, horizon_events=3, cost_model=KRAKEN)
    score = headline_score(obs, batch, horizon_events=3, cost_model=KRAKEN)
    assert score.dsr_kill < 0.05 and score.passes is False
    # The kill reads the LESS favourable of the per-trade and the lumpy DSR.
    assert score.dsr_kill == min(score.dsr_per_trade_median, score.dsr_lumpy)
    assert score.dsr_per_trade_min <= score.dsr_per_trade_median <= score.dsr_per_trade_max

    # A clean positive carry (zero cost, steady positive funding) CAN pass.
    rates = [0.001 + 0.0001 * ((i % 5) - 2) for i in range(90)]
    obs_pos = _frame(rates, [100.0] * 90, [100.0] * 90)
    batch_pos = simulate_batch(obs_pos, horizon_events=3, cost_model=_ZERO_COST)
    good = headline_score(obs_pos, batch_pos, horizon_events=3, cost_model=_ZERO_COST)
    assert good.dsr_per_trade_median > 0.95


def test_funding_sign_regime_decomposition() -> None:
    rates = [0.001, -0.002, 0.001, 0.001, -0.003, 0.0, 0.002]
    obs = _frame(rates, [100.0] * 7, [100.0] * 7)
    regime = funding_sign_regime(obs)
    assert regime.n_positive == 4 and regime.n_negative == 2 and regime.n_zero == 1
    assert regime.mean_collected_negative < 0 < regime.mean_collected_positive
    # the collecting equity falls when funding goes negative
    assert regime.negative_regime_drawdown > 0


def test_after_tax_sidebar_offsets_within_year() -> None:
    obs = _frame([0.0002] * 40, [100.0] * 40, [100.0] * 40)
    batch = simulate_batch(obs, horizon_events=2, cost_model=_ZERO_COST)
    sidebar = after_tax_sidebar(batch, ordinary_rate=0.35)
    assert sidebar.pre_tax_total > 0
    assert math.isclose(sidebar.after_tax_total, sidebar.pre_tax_total * 0.65, rel_tol=1e-9)
    assert math.isclose(sidebar.tax_drag, sidebar.pre_tax_total * 0.35, rel_tol=1e-9)
    with pytest.raises(ScoringError):
        after_tax_sidebar(batch, ordinary_rate=1.0)


def test_gate_surface_kills_a_negative_grid_and_passes_a_clean_cell() -> None:
    # The full venue x H x capital-multiple grid on a deeply negative carry -> KILL.
    rates = [0.00008 + 0.00004 * ((i % 5) - 2) for i in range(260)]
    obs = _frame(rates, [100.0] * 260, [100.0] * 260)
    cells = gate_surface(obs, venues=ALL_VENUES, horizons=(3, 21), capital_multiples=(2.0, 1.0))
    assert len(cells) == len(ALL_VENUES) * 2 * 2
    assert all(not c.score.passes for c in cells)
    assert {c.score.capital_multiple for c in cells} == {2.0, 1.0}
    assert is_killed(cells) is True
    # A zero-cost tradeable cell with a clean positive carry is NOT killed.
    rates_pos = [0.001 + 0.0001 * ((i % 5) - 2) for i in range(120)]
    obs_pos = _frame(rates_pos, [100.0] * 120, [100.0] * 120)
    clean = gate_surface(obs_pos, venues=(_ZERO_COST,), horizons=(3,), capital_multiples=(2.0,))
    assert is_killed(clean) is False
