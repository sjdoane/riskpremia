# Industry-Trend Net-of-Market: the Measured Result

Date: 2026-06-07.
Related decision: [ADR 0011](../decisions/0011-pivot-to-industry-trend-net-of-market.md) (with its
design-review amendment).
Pre-registration and method: [docs/research/0013](0013-industry-trend-net-of-market-design.md).

## Verdict

**NON-VIABLE: an honest timing null.** Holding the 12 Kenneth French industries long-or-cash on a
ten-month trend does not beat simply holding them always-invested, once the comparison isolates the
timing (the strategy minus its own always-invested equal-weight self). The single sentence:

> The pure-timing kill (strategy minus always-invested equal-weight) has a full-sample conditional
> PSR(0) of 0.229, far below the 0.95 bar; the annualized timing return is -1.54%/yr. The trend rule
> reduces volatility (its standalone Sharpe 0.62 beats the always-invested 0.49) but gives up
> return, so it does not add value over always-invested net of cost. It is crash insurance, not a
> market-beater, exactly as the fork expected.

This was designed to be defensible regardless of sign, and the null is the informative outcome: with
Study 8 (volatility-managed timing), it establishes that **defensive equity timing does not beat
buy-and-hold at retail**, whether the timer is realized volatility (Study 8) or the price trend
(Study 9).

## The measured object

Each of the 12 value-weighted Kenneth French industries is held long when its total-return index is
above its ten-month moving average at the prior month-end, else its one-twelfth of capital earns the
one-month bill (Study 6's frozen no-fit rule, verbatim, on 12 sleeves). Fixed 1/12 weight, monthly
rebalance, 5 bps per-side turnover and a 0.10 percent annual expense on held notional. The kill is
the strategy minus its own always-invested equal-weight buy-and-hold; the strategy minus the
value-weight market is the deployable context and the equal-weight-minus-value-weight tilt is the
bridge. Window 1927-05 to 2026-04, 25984 daily observations (block-deflated effective T 7312).

## Result

| Quantity | Value |
| --- | --- |
| PRIMARY: strategy-minus-always-invested (pure timing) PSR(0) | **0.229** (bar 0.95) |
| Timing annualized Sharpe / annualized return | **-0.14 / -1.54%/yr** |
| Decomposition: timing + tilt = deploy (per year) | **-1.54% + 0.49% = -1.05%** |
| Monthly non-overlapping timing PSR(0) | 0.320 |
| Context: strategy net-of-BILL PSR(0) | **0.9998** (the equity premium, not the kill) |
| Context: standalone Sharpe strategy / EW / market | 0.623 / 0.487 / 0.446 |
| Strategy: time in market / max drawdown / CAGR | 91.7% / 52.3% / 9.9% |
| CPCV worst fold / recency 2000 / 2008 / 2022 | 0.066 / 0.378 / 0.347 / 0.143 |
| Deflated Sharpe at 16 / 64 / 128 trials | 0.066 / 0.041 / 0.032 |
| Cost sensitivity 5 / 10 / 20 bps per side | 0.229 / 0.220 / 0.202 |
| Redundancy vs Study 6: timing-diff corr / active-bet corr | -0.043 / **0.821** |

### Reading the result

- **The benchmark choice is the whole game, and the decomposition proves it.** The
  strategy-minus-bill PSR is 0.9998 (it crushes the bill), but that is the equity premium harvested
  by a book that is 92 percent in the market, not timing skill (the Study 8 trap). The
  strategy-minus-value-weight-market difference is -1.05%/yr, but that conflates the timing with a
  static equal-weight tilt. Only the strategy-minus-its-own-always-invested-self isolates the
  timing, and it is -1.54%/yr (PSR 0.229). The decomposition is exposed and exact: timing (-1.54)
  plus tilt (+0.49) equals deploy (-1.05). The static equal-weight-over-value-weight tilt is a small
  positive (+0.49%/yr) that would have masked part of the negative timing had the kill been
  net-of-market; the design review caught this before the build.
- **The strategy has a higher standalone Sharpe yet a negative timing difference, and that is
  coherent.** Trend-timing lowers volatility (standalone Sharpe 0.62 versus 0.49 for
  always-invested), but it does so by giving up return: it sits out early rebounds and pays
  whipsaw turnover, so its mean return is 1.54%/yr below always-invested. For a retail investor who
  cannot lever, the choice is the higher-return-higher-volatility always-invested book or the
  lower-return-lower-volatility timed book; the timing does not make money over always-invested. It
  is risk reduction, not return addition. This is precisely the Study 8 pattern (volatility timing
  also raised the standalone Sharpe while the difference over always-invested was null).
- **It is robust, not one unlucky slice.** Every reading of the timing kill is below the bar: the
  full-sample, the monthly, the CPCV worst fold, the 2000-, 2008-, and 2022-onward recency slices,
  the deflated Sharpe to 128 trials, and the cost sensitivity to 20 bps per side.
- **Study 9 is timing-redundant with Study 6, and the data says so honestly.** The
  timing-difference series correlates only -0.043 with the Study 6 excess, but the active-bet
  correlation is 0.821: the two trend strategies make nearly the same on/off bets (they de-risk in
  the same broad-market drawdowns), so Study 9 is largely re-expressing Study 6's equity timing
  across 12 sectors rather than a distinct signal. The equal-weight combination Sharpe (0.18 on the
  difference series) adds nothing. This confirms, with data, the adversarial cross-check's
  one-note-trend concern.

## Honesty guardrails (met)

- The kill is the pure-timing difference over always-invested, never the net-of-bill return (the
  equity premium) or the net-of-market difference (which carries the equal-weight tilt).
- The decomposition makes the timing-versus-tilt attribution auditable and exact.
- The trend rule is frozen verbatim from Study 6 with no re-optimization; the moving-average length
  and breadth variants are a deflation family.
- The deployment claim is a clean null; no tradeable edge is asserted, and the redundancy with
  Study 6 is reported, not hidden.

## Reproduce

```powershell
$env:PYTHONIOENCODING="utf-8"
$py = "C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe"
# No-network: the committed panel rebuilds the committed gate artifact (the numbers above)
& $py -m scripts.run_indtrend_gate
# Render the figures (the figures extra)
& $py -m scripts.regenerate_indtrend_figures
# The offline reproduction test rebuilds the artifact from the committed fixture to the digit
& $py -m pytest -q tests/unit/test_indtrend_reproduces.py
```

## Figures

- `docs/figures/indtrend_wealth.png`: the strategy, the always-invested equal-weight benchmark, and
  the value-weight market net wealth (log), with the timing-difference caption.
- `docs/figures/indtrend_scorecard.png`: the net-of-bill context bar (clears the bar on the equity
  premium) next to the timing kill and its stress slices (all below the bar).

## Post-implementation review

An adversarial post-implementation review returned a SHIP verdict with no Critical or High findings.
It reproduced the artifact to 1e-9, re-derived the decomposition identity by hand (gap 1.7e-18),
confirmed no leverage (max gross exactly 1.0) and no look-ahead, and ran the decisive adversarial
test: the timing null persists **gross of all costs** (the cost-free timing difference is -1.50%/yr,
PSR 0.326), so it is a genuine "trend-timing forfeits equity-premium return" result, not a cost or
benchmark artifact (costs add only -0.04%/yr). It confirmed the strategy mean (9.6%/yr) is below the
always-invested mean (11.2%/yr) while its volatility is six points lower, which is why the standalone
Sharpe rises yet the timing difference is negative, the coherent Study 8 pattern. The two Medium
findings were cosmetic and reported-context only: the build's ten-month burn-in is correct (it
matches Study 6 and a ten-month moving average), and a local cost-share denominator was mislabeled
"gross" when it divides by the net-compounded terminal; the latter was renamed (the value is
unchanged, so the artifact is byte-identical).

## The thesis (Studies 6, 8, 9)

Study 6 showed a stock-and-bond trend rule beats the bill (an equity-premium-aided, regime-dependent
pass). Study 8 showed volatility-managed timing does not beat buy-and-hold the market net of cost.
Study 9 shows price-trend timing does not beat always-invested net of cost either. Together they
establish that defensive equity timing, however the timer is built, reduces risk but does not make
money over buy-and-hold at retail; beating the market in money terms needs leverage or shorting that
retail cannot access.
