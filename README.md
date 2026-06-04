# RiskPremia

A reproducible, intellectually-honest **measurement study** of the crypto
perpetual-futures **funding-carry** risk premium: does the carry survive realistic
exchange fees, the two-leg bid-ask spread, regime conditioning, and the
post-spot-ETF basis decay, measured on a venue a US retail trader can actually
trade? The honest contribution is the cost realism, the confound controls, the
capacity ceiling, and a pre-registered kill criterion, not a backtest number.

Sibling to [pit-backtest](https://github.com/sjdoane/pit-backtest), whose
recruiter-facing headline was a *reproducible honest momentum null* (vanilla
momentum does not beat passive after costs and deflation). This project extends
that discipline to a market with a defensible economic edge.

> **Status: early build (2026-06-03).** Scaffold + the week-1 data-access spike +
> the lead-track decision are done; the data layer is in progress. There is **no
> result yet**, by design: the cost model and a random-entry null come before any
> signal. This README describes the question and the apparatus; the numbers land
> when the build does. Live state is always in [STATUS.md](STATUS.md).

## Why this premium (the economic thesis, cited not claimed)

Leveraged-long crypto traders pay funding to hold perpetual futures; a
delta-neutral book (long spot, short perp) collects it. It is compensation for a
real, un-hedgeable risk: forced-liquidation and exchange-solvency exposure, with
arbitrage capital kept scarce because there is no spot/perp cross-margin on
regulated venues (you fund twice). This is a published result, not a discovery
(Schmeling, Schrimpf and Todorov, "Crypto carry," BIS Working Paper 1087). The
naive trade is content-farmed and reads as hype, so the contribution here is the
risk treatment and an honest quantification of the **post-spot-ETF decay** (the
basis fell from roughly 25% annualized in early 2024 to under about 5%).

## Pre-registered kill criterion (declared before any signal exists)

The study ships whatever the result is, an honest null included. The kill
criterion gates **real-money deployment**, not whether the write-up is worth
doing. Frozen up front in [ADR 0001](docs/decisions/0001-lead-track-selection.md):

- **Primary:** net-of-all-cost (US-tradeable-venue fees + both-leg spread +
  funding + short-term tax) **Deflated Sharpe below 0.95 out-of-sample**, under
  event-time-purged CPCV with embargo, on the frozen trial count, on the held-out
  post-spot-ETF period, means **declare non-viable and publish the honest null**.
- **Early economic gate:** if the median funding collected does not exceed the
  amortized round-trip cost for a passive always-on carry, the naive carry is
  dead after costs and any edge must come from selection or regime timing.

## Methodology

| Pillar | How |
| --- | --- |
| Cost model first | Build the per-leg modeled cost (taker/maker fees + half-to-full spread on entry and exit + funding) and run a random-entry NULL through it BEFORE any signal. If the signal is not clearly better than the null after costs, there is no edge. |
| Point-in-time discipline | The event clock is the funding settlement, not the calendar. Funding realized at T is known only at or after T; prices are taken from a backward as-of join, so no future leakage. |
| Event-time-purged CPCV | Combinatorial Purged Cross-Validation (Lopez de Prado 2018) split on funding events with embargo, reused from the sibling stack. |
| Deflated performance | PSR / Deflated Sharpe / MinTRL (Bailey and Lopez de Prado 2014) with an honest trial count; every configuration logged to a committed trial registry; Harvey-Liu BHY false-discovery control across the hypothesis set. |
| Capacity + break-even | Net edge vs position size with measured impact (the size where net edge crosses zero is the headline), plus the per-trade cost at which the edge dies. |
| Confound controls | Premium measured on long Binance history but the kill gate on US-realized funding, with the venue-basis delta reported as a measured number; funding reported as the clamped realized cash flow, not the pure premium; a pre-committed survivor universe to avoid survivorship-inflated cross-sections. |

## Reproducibility

Free, no API key, and verifiable from a clone. The long-history funding series
comes from Binance Vision S3 dumps (checksummed monthly files from 2020), the
live US-reachable tier is OKX (and Hyperliquid on-chain); raw bytes are
gitignored but SHA256-stamped into a committed manifest, and only derived
aggregate artifacts are tracked, so a reviewer re-fetches, verifies byte-identity,
and regenerates the headline. (Honest venue note: the live Binance and Bybit REST
APIs are geo-blocked from US IPs, which is itself a risk-register entry; the data
dumps and OKX are not.)

## Reading map

- [STATUS.md](STATUS.md) is the current state and what is deferred (read first).
- [docs/decisions/](docs/decisions/) is the ADR log; [0001](docs/decisions/0001-lead-track-selection.md)
  is the lead-track decision, the four-lens review and adversarial cross-check record, and the kill criterion.
- [docs/research/0001-data-layer-design.md](docs/research/0001-data-layer-design.md)
  is the reviewed data-layer design.
- [docs/STRATEGY-BRIEF.md](docs/STRATEGY-BRIEF.md) is the stress-tested context (the two
  candidate tracks and why Track B leads).
- [CHANGELOG.md](CHANGELOG.md) is the audit trail: every review finding and its resolution.

Track A (a single-name earnings variance-risk-premium study) was examined and
deprioritized; the friction-adjusted reasoning is in ADR 0001. Killing your own
weaker track on honest evidence is the point.

## How it is built (process)

Every meaningful component goes through a design plan, an independent senior-quant design review,
implementation, and a post-implementation review; every fork (the lead-track choice) goes
through a four-lens review plus an adversarial cross-check. Critical and High
findings are addressed before anything is marked done, and the finding plus its
resolution is recorded in the CHANGELOG. The analytics and validation stack
(PSR/DSR/MinTRL, purged CPCV, stationary block bootstrap, trial registry) is
vendored with attribution from the sibling project so the repo regenerates every
number on its own. Dependencies are pinned to exact patch; mypy runs strict.

## Setup

```powershell
# Dedicated venv (kept outside the synced tree)
uv venv --python 3.12 C:\Users\SamJD\.venvs\riskpremia
uv pip install --python C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe -e ".[dev]"
C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe -m pytest -q
```

## License

MIT (see [LICENSE](LICENSE)).
