# 0005: the BTC/ETH slow trend gate (Study 4, PR6a)

Study 4 tests the ADR 0006 BTC/ETH slow trend allocation after the CTREND null. The
goal is not to optimize a crypto trend model. The goal is to ask whether one frozen,
retail-executable defensive beta rule survives the same net-of-cost, reproducible
kill discipline as the earlier studies.

## Frozen rule

- Universe: BTCUSDT and ETHUSDT spot daily bars from Binance Vision.
- Data window: 2019-01-01 through 2026-05-31, with 2022-01-01 as the out-of-sample
  scoring start.
- Signal: at the Sunday UTC daily close, an asset is active only when close is strictly
  greater than its 200-day simple moving average.
- Execution: the signal is known only after Sunday close, fills at Monday open, and exits
  at the next Monday open.
- Sizing: inverse-volatility weights across active assets, using a 60-day daily log-return
  volatility estimate and the BTC/ETH covariance when both are active.
- Risk cap: 25 percent annualized volatility target, 100 percent gross notional cap, no
  leverage, shorts, perps, option legs, or parameter search.
- Cash: zero-yield cash for inactive capital. Nonzero cash yield is rejected in PR6a so it
  cannot become a hidden source of edge.
- Costs: the Kraken spot cost model, applied to weekly turnover before the holding return.

The net return is self-financing:

```text
net = (1 - rebalance_cost_fraction) * (1 + holding_return) - 1
```

Daily max drawdown is measured from a daily mark-to-market equity path, not from weekly
endpoints only.

## Scoring

Because PR6a has one frozen no-fit rule, the statistic is labelled conditional PSR(0), not
Deflated Sharpe. The effective sample size still uses the project block-length correction.
Purged CPCV is retained as a worst-regime stress over the weekly return series, not as
fitted-model validation.

The pre-registered kill checks are:

- CPCV stress minimum conditional PSR(0) must be at least 0.95.
- Daily max drawdown must be no more than 35 percent.
- Total costs paid must be no more than 25 percent of compounded gross gain.
- Target gross must respect the 100 percent notional cap, with a 105 percent drift guard
  before the next rebalance.

A pass would still be provisional until a US spot USD venue rebuild confirmed the signal
near the 200-day threshold. A fail under Binance Vision can ship as an honest null.

## Artifact

`scripts/run_btc_eth_trend_gate.py` rebuilds `artifacts/btc_eth_trend_gate.json` from:

- `tests/data/btc_eth_daily_ohlc.csv`
- `tests/data/btc_eth_daily_ohlc_sources.json`

Both fixtures are SHA256-stamped in `data/snapshots/manifest.toml`. The source provenance
file records each Binance Vision monthly spot-kline zip and published checksum used to
construct the committed fixture.

The artifact separates `first_signal_date`, `first_fill_date`, `last_signal_date`,
`last_fill_date`, and `last_exit_date` so the execution clock is auditable.

## Result

The gate is non-viable. Headline values:

- Weekly observations: 229.
- First fill to last exit: 2022-01-03 to 2026-05-25.
- Mean net return: +0.1975 percent per week.
- Full-window conditional PSR(0): 0.6970.
- CPCV stress minimum conditional PSR(0): 0.1439.
- Daily max drawdown: 26.65 percent.
- Total cost share of gross edge: 11.47 percent.
- Compounded net gain: 43.91 percent.
- CAGR: 8.64 percent.
- Buy-and-hold BTC/ETH diagnostic total return: 8.91 percent.
- Buy-and-hold diagnostic max drawdown: 68.85 percent.

The rule improves drawdown versus buy-and-hold and has a positive net compounded result,
but it fails the statistical kill gate. The verdict is:

```text
NON-VIABLE BTC/ETH slow-trend honest null. CPCV stress PSR 0.144 below 0.95.
```

## Design review findings and resolutions

The senior-quant design review returned three Critical and four High findings. All were
fixed before implementation:

- Critical 1, look-ahead execution: fixed by using Sunday close only for the signal,
  Monday open for the fill, and the next Monday open for exit.
- Critical 2, statistic label: fixed by labelling the no-fit rule as conditional PSR(0)
  and treating CPCV as a worst-regime stress, not fitted validation.
- Critical 3, drawdown endpoint risk: fixed by using a daily mark-to-market equity path.
- High 1, cost timing: fixed with the self-financing return formula above.
- High 2, cost-share denominator: fixed by dividing total costs paid by compounded gross
  gain and automatically failing when gross gain is not positive.
- High 3, venue caveat: accepted as a pass blocker; a pass would need a US spot USD
  rebuild.
- High 4, audit dates: fixed by separating signal, fill, and exit dates in the artifact.

Medium items were also incorporated: strict `close > SMA`, zero-yield cash, Kraken venue
disclosure, source checksum provenance, and volatility guards.

## Post-implementation review

The post-implementation review found no Critical or High issues and independently rebuilt
the weekly logic from the committed CSV without calling `trend.gate`. It matched the
artifact exactly on the number of weeks, first and last dates, net gain, gross gain, total
cost paid, and daily max drawdown.

Resolved follow-up items:

- Added surgical tests for Sunday-close signal, Monday-open fill, and Monday-open exit.
- Added a test that a midweek crash with endpoint recovery is captured by daily drawdown.
- Added a direct test that nonpositive compounded gross edge makes cost share infinite and
  fails the cost-share gate.
- Added full artifact JSON structure comparison in the reproduction test, with exact
  non-floats and tolerant floats.
- Made duplicate `(symbol, date)` bars a loud error in fixture write and read paths.
- Pinned the source provenance JSON to LF bytes so manifest hashes match on Windows and
  Linux.
- Added a guard and test that PR6a cash return is fixed at zero-yield cash.
- Aligned the buy-and-hold diagnostic to the same exit-open convention as the strategy.
- Added a source-layer passthrough test that Binance Vision spot klines carry the open.

## Verification

The committed artifact reproduces offline from the committed fixtures. Full verification
is recorded in `CHANGELOG.md` for the PR that adds this design note, code, fixtures, and
artifact.
