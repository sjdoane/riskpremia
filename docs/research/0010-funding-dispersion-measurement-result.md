# Crypto Funding-Dispersion Measurement: the Measured Result

Date: 2026-06-07.
Related decision: [ADR 0009](../decisions/0009-pivot-to-funding-dispersion-measurement.md).
Pre-registration and method: [docs/research/0009](0009-funding-dispersion-measurement-design.md).

## What this is (and is not)

This is the measured result of Study 7, the pre-registered crypto funding-dispersion
measurement. It is a descriptive measurement of an object, like a volatility surface, NOT a
tradeable verdict and NOT a "positive result" in the make-money sense. The single sentence:

> Cross-sectional perpetual-funding dispersion is alive but decaying and non-deployable: the
> post-spot-ETF equal-weight IQR is 0.091 annualized versus 0.123 pre-ETF (difference -0.032,
> 95% CI [-0.058, -0.008]); the decay slope is -0.013/yr (95% CI [-0.022, -0.004]). The gross
> high-minus-low sort premium is +0.550 annualized, and it is not retail-capturable.

There is no tradeable Sharpe anywhere in this note, by design. Capturing the cross-sectional
funding spread requires shorting a wide altcoin-perp cross-section, which US retail cannot
access, on a venue (Binance) that is not US-tradeable. The gross premium is reported only as a
measured object so the dispersion can be expressed in carry units; it is the wall ADR 0006
flagged, not an edge.

## The measured object

The point-in-time top-15 most-liquid perpetuals (CTREND `pit_eligible`, USDT-quoted, 2022
onward; 116 ever-eligible symbols, 109 with a funding series), each event annualized by its own
funding interval (basis 365 times 24, single-sourced to `CRYPTO_ANNUALIZATION_DAYS`), carried
forward onto a fixed daily 00:00 UTC grid by a point-in-time backward as-of join (rejected
across a multi-day gap). The headline is the equal-weight cross-sectional interquartile range of
annualized funding, as a daily series; 1611 daily observations, 2022-01-02 to 2026-05-31. Full
method in ADR 0009.

## Result

| Quantity | Value |
| --- | --- |
| Headline: equal-weight cross-sectional IQR (full sample) | **0.106** annualized (95% CI [0.092, 0.122]) |
| Bootstrap effective T / raw T / block length | 28 / 1611 / 56.8 days |
| Regime: pre-ETF mean (739 days) / post-ETF mean (872 days) | **0.123 / 0.091** |
| Regime difference (post minus pre) | **-0.032** (95% CI [-0.058, -0.008]) |
| Decay slope | **-0.013/yr** (95% CI [-0.022, -0.004]) |
| Secondary: raw std / winsorized std (full-sample means) | 0.390 / 0.200 |
| Secondary: gross high-minus-low sort premium | **+0.550** annualized (95% CI [+0.354, +0.783]), non-capturable |
| Coverage: mean funded / eligible (worst day) | 13.6 / 15 = **91%** (worst 73%) |

Significance is the vendored stationary-block bootstrap on the FULL daily series (no VRP-style
striding; the dependence is funding-regime persistence, absorbed by the Politis-White block
length), with a percentile confidence interval and a block-deflated effective sample size. A
dispersion level is positive by construction, so the testable statements are the regime
DIFFERENCE and the decay SLOPE (both signed, both with CIs that exclude zero on the negative
side), never a vacuous clears-zero test on the level itself.

### Reading the result

- **Dispersion is real and large.** A 0.106 annualized interquartile range means that, on a
  typical day, the funding paid by the 75th-percentile coin exceeds the 25th-percentile coin by
  about ten annualized percentage points. The spread is not a units artifact (each event is
  interval-annualized before any comparison) and not an estimator artifact (the robust IQR is
  the headline; the tail-dominated raw std, 0.390, is reported only as a secondary diagnostic
  alongside its winsorized counterpart, 0.200).
- **Dispersion is decaying.** Both regime evidence and the slope agree: the post-spot-ETF IQR is
  about a quarter below the pre-ETF level (difference -0.032, CI excludes zero), and the
  standalone decay slope is -0.013/yr (CI excludes zero). The spot-ETF date is the project's
  standard comparability split, not a claimed cause of an altcoin-funding regime change; the
  decay curve is the primary regime evidence and the slope is the summary.
- **The gross premium is the same object in carry units, and it is non-capturable.** The
  secondary quintile sort (top-minus-bottom, equal-weight, funding-only, next-period realized,
  point-in-time) is +0.550 annualized with a CI that excludes zero. It is funding-only and
  ignores the perp price PnL, which is exactly why it is not a tradeable edge: realizing it
  needs shorting a wide alt-perp cross-section on a non-US venue. No tradeable Sharpe is quoted
  for it.

## Implementation amendments (see ADR 0009 footer)

Two ways the build is narrower than the pre-registration, neither changing the verdict; both
were post-implementation-review findings:

1. **The spot-to-perp join is USDT-symbol-string identity, not a canonical asset key.** The
   eligible spot symbols are already USDT-quoted, and funding is fetched for those exact strings;
   the USD-margined perp shares the string. There is no canonical mapping and no USDC/BUSD
   fallback leg, so an asset whose only perp is non-USDT-quoted or prefix-renamed (the 1000x meme
   perps) is dropped rather than matched. This can only narrow the cross-section, never widen it,
   so it is a conservative understatement; the 91% coverage diagnostic (worst day 73%) makes the
   attrition visible and bounded. A canonical-key join with a quote fallback is a deployment-only
   backlog item.
2. **The universe is the fixed top-15 over 2022 onward,** chosen over the 402-coin top-50 union
   because the larger set is dominated by short-lived small caps whose churn adds estimator noise.
   The top-15 over the matured-perp window is a clean, bounded, documented liquid universe,
   recorded in the provenance and the manifest.

## Honesty guardrails (met)

- No tradeable-Sharpe headline and no long-short return as the headline, anywhere.
- An explicit non-deployability banner travels on the abstract, the artifact caveats, and both
  figures: US retail cannot short a wide altcoin-perp cross-section, and the venue with the data
  is not US-tradeable.
- The decay is in the headline sentence, not buried.
- The deliverable is a descriptive measurement, explicitly not a "positive result."
- The interval-normalization and the equal-weight, IQR-based estimator are shown so no reader
  mistakes a units or estimator artifact for dispersion.

## Figures

Rendered from the committed series and artifact (so a regenerated PNG cannot drift from the
audited measurement); the non-deployability caveat is printed on each.

- `docs/figures/funding_dispersion_iqr.png`: the daily equal-weight cross-sectional IQR, with
  the 90-day rolling median (a plot smoother only; the headline slope is OLS on the raw daily
  series), the spot-ETF boundary, and the two regime means.
- `docs/figures/funding_dispersion_sort_premium.png`: the secondary gross high-minus-low funding
  sort premium over time (non-capturable).

## Reproduce

```powershell
$env:PYTHONIOENCODING="utf-8"
$py = "C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe"
# One-time, network: fetch the funding archive across the PIT universe -> committed series + stamp
& $py -m scripts.build_dispersion_inputs
# No-network: committed series -> committed artifact (the measured numbers above)
& $py -m scripts.run_dispersion_measurement
# Render the figures from the committed series + artifact (the figures extra)
& $py -m scripts.regenerate_dispersion_figures
# The offline reproduction test asserts the committed fixture reproduces the artifact
& $py -m pytest -q tests/unit/test_dispersion_reproduces.py
```

## Post-implementation review

An adversarial post-implementation review returned a SHIP verdict with no Critical or High
findings. It reproduced every headline number from the committed fixture to the digit and
confirmed the bootstrap is run on the full (un-strided) series as pre-registered. The two Medium
findings (document the USDT-identity join and rename the decay knob to mark it a plot-only
smoother) are resolved here and in the code: the knob is `decay_plot_window_days`
(`DECAY_PLOT_WINDOW_DAYS`), read by the figures, and the join is documented in the ADR footer
and section above. The measurement ships as an honest, reproducible, non-deployable measured
object.
