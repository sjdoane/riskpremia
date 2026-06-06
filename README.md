# RiskPremia

A reproducible, intellectually-honest **measurement study** of crypto risk premia.
One apparatus (free, US-reachable, checksum-pinned data; a vendored deflated-Sharpe /
purged-CPCV / bootstrap stack; a cost-model-first kill gate) is pointed at a sequence
of candidate premia:

1. **The perpetual funding carry** (Study 1): does a delta-neutral long-spot /
   short-perp book that collects funding survive realistic retail costs? **Result: an
   honest null.** Net-of-cost Deflated Sharpe is ~0 on every US-tradeable venue and
   horizon; the round-trip cost dwarfs the funding and the post-spot-ETF basis decayed.
   Killed cleanly per the pre-registered criterion ([ADR 0003](docs/decisions/0003-cost-model-and-null.md)).
2. **The variance risk premium** (Study 2): implied variance (Deribit DVOL)
   persistently exceeds subsequently-realized variance in BTC. **Result: a real,
   positive, statistically-significant measurement premium, but the tradeable monthly
   short-straddle gate is non-viable** after costs and crash-tail accounting
   ([ADR 0004](docs/decisions/0004-pivot-to-variance-risk-premium.md)).
3. **The CTREND crypto cross-sectional trend factor** (Study 3): the gross signal has
   real rank-IC quality, but the retail long-only top quintile is non-viable after
   realistic costs, and the academic long-short comparison also fails the conservative
   CPCV-min DSR gate ([ADR 0005](docs/decisions/0005-pivot-to-ctrend-trend-factor.md)).
4. **BTC/ETH slow trend with cash and a volatility cap** (Study 4): the frozen weekly
   spot-only rule is positive and drawdown-reducing, but non-viable because the CPCV
   stress minimum conditional PSR(0) is 0.1439, below the 0.95 gate
   ([ADR 0006](docs/decisions/0006-pivot-to-btc-eth-slow-trend.md)).
5. **CME Micro G6 FX carry** (Study 5 feasibility): killed before implementation because
   the exact free historical CME settlement path is not robust enough for a deployable
   futures backtest and USD 10,000 integer-contract stress can fail account survival
   ([ADR 0007](docs/decisions/0007-kill-cme-micro-g6-fx-carry.md)).
6. **Cross-asset defensive trend** (Study 6): a frozen, no-fit, long-only trend rule across
   genuinely low-correlated asset classes (US equity, long-term US Treasury, gold) on
   openly-redistributable public-domain data, scored in excess of the Treasury bill. Selected
   and pre-registered after a four-lens fork as the deployable swing that repairs Study 4's
   weakness with integrity; build and verdict pending
   ([ADR 0008](docs/decisions/0008-pivot-to-cross-asset-defensive-trend.md)).

Sibling to [pit-backtest](https://github.com/sjdoane/pit-backtest), whose headline was a
*reproducible honest momentum null*. The contribution here is the same: cost realism,
confound controls, a pre-registered kill criterion, and reproducibility, never a hyped
backtest. An honest null is a success; a blown-up account or an oversold backtest is a
failure.

> **Status (2026-06-06):** Studies 1, 2 tradeable layer, 3, and 4 are honest nulls.
> Study 2's measurement layer remains a positive finding. Study 5, the CME Micro G6 FX
> carry feasibility pass, was killed before implementation. Study 6, a cross-asset
> defensive trend on public-domain data, is selected and pre-registered ([ADR 0008](docs/decisions/0008-pivot-to-cross-asset-defensive-trend.md));
> the build and verdict follow. Live state is always in [STATUS.md](STATUS.md).

## Study 2 result: the BTC variance risk premium

Layer ii is complete and non-viable: the systematic monthly short straddle netted a
Deflated Sharpe of 0.30, below the 0.95 bar, with a slightly negative mean and crash
shocks a retail account could not survive. The measurement layer below remains the
positive result.

Implied variance (the Deribit DVOL index, squared) minus the matched-horizon realized
variance (the variance-swap convention, on the Binance Vision spot closes), BTC,
2022-01 to 2025-05, 30-day horizon:

| Quantity | Value |
| --- | --- |
| Mean VRP (median across non-overlapping phases) | **0.087** annualized variance points |
| 95% CI (phase-0 strided block-bootstrap, overlap-honest) | **[0.033, 0.119]**, clears zero |
| Days with implied > realized | **70%** |
| Pre-spot-ETF mean to post-spot-ETF mean | **0.101 to 0.059** (a decay paralleling the carry) |

The premium is real and positive: implied variance is, on average, dearer than what is
subsequently realized, which is what an option seller is paid for bearing variance and
jump risk. The CI clearing zero is reported on the **non-overlapping** strided series
with a Politis-White block-deflated effective sample size, not a dishonest t-stat on the
29/30-overlapping daily series. This is a **measurement**, not a tradeable result (see
the caveats below and Layer ii).

![BTC implied vs realized volatility](docs/figures/dvol_vs_realized.png)

![BTC variance risk premium with the spot-ETF regime means](docs/figures/vrp_decay.png)

The numbers and figures regenerate from a committed JSON artifact
([artifacts/vrp_measurement.json](artifacts/vrp_measurement.json)) with no data bundle:

```powershell
# render the figures from the committed artifact (needs the figures extra)
python -m scripts.regenerate_figures
# rebuild the artifact + fixtures + manifest stamp from the live data (one-time)
python -m scripts.build_vrp_artifact
```

**Binding caveats (carried in the artifact and on the figures):** the headline is the
measurement plus the regime decomposition, **never a short-volatility Sharpe** (the
Deflated Sharpe cannot price an out-of-sample crash); the point estimate is the
median-phase mean while the CI is the phase-0 strided interval; the implied leg is the
Deribit BTC index and the realized leg the Binance spot, so the premium is a
cross-underlying proxy; and the vol-point spread (figure 1) is a distinct object from the
variance premium (figure 2). The decision to harvest it rests on the in-sample crash
losses plus a peso-adjustment (Layer ii), not on a Sharpe.

## Pre-registered kill criteria (declared before any signal exists)

Each study ships whatever the result is, an honest null included. The criterion gates
**real-money deployment**, not whether the write-up is worth doing.

- **Study 1 (carry,** [ADR 0001](docs/decisions/0001-lead-track-selection.md)**):**
  net-of-all-cost Deflated Sharpe below 0.95 out-of-sample on the held-out post-spot-ETF
  period means declare non-viable. **Triggered: killed.**
- **Study 2 (VRP,** [ADR 0004](docs/decisions/0004-pivot-to-variance-risk-premium.md)**):**
  net-of-all-modeled-cost Deflated Sharpe below 0.95 out-of-sample, **or** an in-sample
  crash loss plus peso-adjustment a retail account could not survive, means declare
  non-viable. The measurement floor (Layer i, above) is the primary deliverable either
  way.
- **Study 3 (CTREND,** [ADR 0005](docs/decisions/0005-pivot-to-ctrend-trend-factor.md)**):**
  net-of-cost CPCV-min DSR below 0.95 on the 2022+ liquid-universe window means the
  published cost-survival claim does not hold under the project's realistic retail-cost
  stress. **Triggered: killed.**
- **Study 4 (BTC/ETH slow trend,** [ADR 0006](docs/decisions/0006-pivot-to-btc-eth-slow-trend.md)**):**
  kill if 2022+ net-of-cost CPCV stress minimum conditional PSR(0) is below 0.95,
  max drawdown exceeds 35%, turnover costs consume more than 25% of gross edge, or the
  result only passes by relaxing the 100% notional cap. **Triggered: killed.**
- **Study 5 (CME Micro G6 FX carry feasibility,** [ADR 0007](docs/decisions/0007-kill-cme-micro-g6-fx-carry.md)**):**
  kill before implementation if the exact free futures-settlement data path fails or
  minimum practical micro sizing can plausibly lose more than 50% of a USD 10,000 account.
  **Triggered: killed.**

## Methodology (the shared discipline)

| Pillar | How |
| --- | --- |
| Cost model first | Build the per-leg modeled cost (fees + spread on entry and exit + funding or option premium) and run a random-entry NULL through it BEFORE any signal. If the signal is not clearly better than the null after costs, there is no edge. |
| Point-in-time discipline | The clock is the market event (the funding settlement; the daily DVOL/realized window), not the calendar. Forward windows use only future data by construction and are never used as a tradeable signal. |
| Honest overlap inference | Overlapping windows are autocorrelated, so the headline is the NON-overlapping strided series with a stationary block bootstrap and a Politis-White block-deflated effective sample size, never a naive t-stat. |
| Deflated performance | PSR / Deflated Sharpe / MinTRL (Bailey and Lopez de Prado 2014) with an honest trial count, reported necessary-not-sufficient for a premium (it cannot price the out-of-sample crash, the peso problem). |
| Confound controls | Premia measured on long Binance history but the US-realized confounds (the venue-basis funding delta; the Deribit-vs-Binance underlying basis) reported as caveats at the point of computation; a pre-committed survivor universe. |
| Reproducibility | Free, keyless, US-reachable, stdlib-only fetch; raw bytes SHA256-stamped into a committed manifest; live/as-of inputs (DVOL) committed as tamper-evident CSV fixtures; only derived aggregate artifacts tracked, so a reviewer regenerates every number from a clone. |

## Reproducibility

Free, no API key, verifiable from a clone. Funding + spot history come from Binance
Vision S3 dumps (checksummed monthly files from 2020); the implied-vol index is the
Deribit DVOL endpoint (keyless, US-reachable). Immutable dumps are gitignored and
re-fetched against a committed SHA256 manifest; the **live/as-of DVOL series** (no
published checksum) is pinned differently: the exact daily closes used are committed as
small CSV fixtures whose SHA256 makes them tamper-evident, so the headline reproduces
**offline** in CI (see `tests/unit/test_vrp_artifact_reproduces_headline.py`). The whole
data layer fetches with the standard library only (zero third-party fetch surface).
(Honest venue note: the live Binance and Bybit REST APIs are geo-blocked from US IPs, a
risk-register entry; the data dumps, OKX, and Deribit DVOL are not.)

## How it is built (process)

Every meaningful component goes through a design plan, an independent senior-quant design
review, implementation, and a post-implementation review; every fork (a track choice, a
go-live decision) goes through a four-lens review plus an adversarial cross-check.
Critical and High findings are addressed before anything is marked done, and the finding
plus its resolution is recorded in the [CHANGELOG](CHANGELOG.md). The analytics and
validation stack (PSR/DSR/MinTRL, purged CPCV, stationary block bootstrap, trial
registry) is vendored with attribution from the sibling project so the repo regenerates
every number on its own. Dependencies are pinned to exact patch; mypy runs strict.

## Reading map

- [STATUS.md](STATUS.md) is the current state and what is deferred (read first).
- [docs/decisions/](docs/decisions/) is the ADR log: [0001](docs/decisions/0001-lead-track-selection.md)
  (lead-track choice + kill criterion), [0002](docs/decisions/0002-data-layer-funding-clock.md)
  (data layer), [0003](docs/decisions/0003-cost-model-and-null.md) (cost model + the carry
  kill), [0004](docs/decisions/0004-pivot-to-variance-risk-premium.md) (the VRP pivot),
  [0005](docs/decisions/0005-pivot-to-ctrend-trend-factor.md) (CTREND), and
  [0006](docs/decisions/0006-pivot-to-btc-eth-slow-trend.md) (BTC/ETH slow trend),
  [0007](docs/decisions/0007-kill-cme-micro-g6-fx-carry.md) (CME Micro G6 FX feasibility), and
  [0008](docs/decisions/0008-pivot-to-cross-asset-defensive-trend.md) (cross-asset defensive trend).
- [CHANGELOG.md](CHANGELOG.md) is the audit trail: every review finding and its resolution.

## Setup

```powershell
# Dedicated venv (kept outside the synced tree)
uv venv --python 3.12 C:\Users\SamJD\.venvs\riskpremia
uv pip install --python C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe -e ".[dev,figures]"
C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe -m pytest -q -m "not network"
```

## License

MIT (see [LICENSE](LICENSE)).
