# Quality (Profitability) Tilt: the Measured Result

Date: 2026-06-07.
Related decision: [ADR 0012](../decisions/0012-pivot-to-quality-tilt.md) (with its design-review
amendment).
Pre-registration and method: [docs/research/0015](0015-quality-tilt-design.md).

## Verdict

**NON-VIABLE: a real premium that is too thin to deploy.** The operating-profitability premium is
genuine and statistically significant, but it does not survive the deployable differential cost and
the multiple-testing deflation for such a mined factor. The single sentence:

> The high-profitability portfolio carries a real, significant quality premium: its Fama-French
> five-factor alpha is +0.65%/yr with a Newey-West t of 2.76 and robust-minus-weak the dominant
> loading (so it is genuinely profitability, not a beta or size artifact; the market beta is 0.99).
> But net of the deployable differential expense (a quality ETF costs more to hold than a market
> ETF) the high-profitability-minus-market difference PSR(0) is 0.932, below the 0.95 bar; the gross
> (no-cost) PSR is 0.951; and the Deflated Sharpe for the quality factor's search collapses to 0.35
> at 16 trials. It is a real but non-deployable tilt, the eighth honest result.

This is the most important kind of result for a project whose operator intends to deploy live: the
gross number (0.9505) looks like a pass, and a sloppy gate would have shipped it. The honest gate,
with the deployable differential cost and the deflation as hard conditions, shows it is not a
make-money edge, before any money is at risk.

## The measured object

Hold the Kenneth French high-operating-profitability value-weighted tercile (`Hi 30`,
`Portfolios_Formed_on_OP_Daily`, 1963 to 2026, 15813 daily observations), a static no-fit tilt (the
portfolio reconstitutes annually at end-June; the build never rebalances). The kill is the difference
over buy-and-hold the value-weight market, both deployed as ETFs, so the honest cost is the
differential expense (a 0.15% quality-ETF expense minus a 0.04% market-ETF expense, a net of about
0.11%/yr); there is no separate reconstitution turnover (the French series embeds it). A Fama-French
five-factor regression attributes the difference; block-deflated effective T is 4610.

## Result

| Quantity | Value |
| --- | --- |
| PRIMARY: high-profitability-minus-market difference PSR(0), net of differential cost | **0.932** (bar 0.95) |
| Gross (no-cost) difference PSR(0) | **0.951** (context, before the deployable expense) |
| Fama-French five-factor alpha (Newey-West t) | **+0.65%/yr (t 2.76)** |
| Decomposition: raw difference / FF5 alpha / RMW component | **+1.13% / +0.65% / +0.98%** per year |
| FF5 loadings: market / SMB / HML / RMW / CMA | 0.99 / -0.03 / -0.10 / **0.31** / -0.01 |
| Context: high net-of-bill PSR(0) | **0.9953** (the equity premium, not the kill) |
| CPCV worst fold | 0.614 |
| Recency 2000 / 2008 / 2010 / 2022 | 0.815 / 0.949 / 0.814 / 0.618 |
| Deflated Sharpe at 8 / 16 / 32 / 128 trials | 0.489 / **0.35** / 0.243 / 0.109 |
| Cost sensitivity 0.05% / 0.10% / 0.20% differential | 0.943 / 0.934 / 0.913 |
| Make-money pass | **False** |

### Reading the result

- **The premium is real, and the build proves it is genuinely quality.** The raw
  high-profitability-minus-market difference is +1.13%/yr, and the Fama-French five-factor alpha is
  +0.65%/yr with a Newey-West t of 2.76: a positive, autocorrelation-robust, statistically
  significant alpha, with robust-minus-weak (0.31) the dominant factor loading and a market beta of
  0.99. So it is not a disguised beta, size, or value tilt; it is the profitability premium.
- **But it is too thin to deploy.** The gross-of-cost difference PSR clears the bar (0.951), but the
  honest deployable cost is the differential expense between a quality ETF and a market ETF; net of
  that, the difference PSR is 0.932, below the bar. The cost sensitivity confirms it fails at every
  differential level (0.943 to 0.913 over 0.05% to 0.20%). This is the make-or-break for a marginal
  factor, and it breaks.
- **Deflation demolishes it.** A trial-count-one PSR is not a pass for a factor as mined as quality
  (the profitability-definition, breadth, and weighting forks are a large search). The Deflated
  Sharpe collapses to 0.35 at 16 trials and 0.11 at 128. Tellingly, the widest cut (the `Hi 30`
  tercile) is the strongest member of the breadth family, the signature of a broad large-cap-quality
  exposure rather than a monotone profitability premium that should strengthen as you concentrate.
- **It decays post-2010.** The recency slices fall from the full-sample to 0.815 (2000), 0.814
  (2010, the quality-ETF era), and 0.618 (2022). None clears the bar; the premium is weaker in the
  era after the quality factor was widely published and traded.
- **The net-of-bill number is the equity-premium trap, reported as context.** The high-profitability
  portfolio's net-of-bill PSR is 0.9953 (it crushes the bill), but that is the equity premium of a
  long-equity portfolio, not the quality edge; only the net-of-market difference tests quality.
- **Distinct from Study 6.** The difference correlates -0.059 with the Study 6 cross-asset trend; a
  fundamental cross-sectional tilt is genuinely orthogonal to the trend family.

## Honesty guardrails (met)

- The kill is the difference net of the deployable differential expense, never the gross or the
  net-of-bill (the equity premium).
- The Fama-French attribution is a gate guardrail (a make-money pass requires a positive alpha with
  robust-minus-weak dominant), so a beta or size tilt cannot be deployed mislabeled as quality.
- The deflation is a hard gate condition, not a footnote; the make-money pass requires it.
- The deployable-versus-proxy gap is stated: the academic value-weighted tercile is not a real
  quality ETF (which uses a sector-neutral composite over fewer large caps), so a tercile pass would
  not have been a QUAL guarantee.

## Reproduce

```powershell
$env:PYTHONIOENCODING="utf-8"
$py = "C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe"
# No-network: the committed panel rebuilds the committed gate artifact (the numbers above)
& $py -m scripts.run_quality_gate
# Render the figures (the figures extra)
& $py -m scripts.regenerate_quality_figures
# The offline reproduction test rebuilds the artifact from the committed fixture to the digit
& $py -m pytest -q tests/unit/test_quality_reproduces.py
```

## Figures

- `docs/figures/quality_wealth.png`: the high-profitability and market net wealth (log) and their
  ratio, with the real-but-thin-premium caption.
- `docs/figures/quality_scorecard.png`: the difference PSR across stress, the gross bar clearing the
  bar while the deployable cost, the deflation, and the post-2010 decay push it under.

## Post-implementation review

An adversarial post-implementation review returned a SHIP verdict with no Critical or High findings.
It independently re-derived every load-bearing number through a different numerical path (a numpy
least-squares solve versus the gate's matrix inverse, and a hand-rolled Newey-West) and matched the
committed artifact to six digits (alpha +0.006457, market beta 0.995, robust-minus-weak loading
0.312, Newey-West t 2.760), confirmed the build is byte-for-byte deterministic, and proved the
make-money boolean has no false-pass path (the stress slices are monotone tighteners that cannot
fabricate a pass, and a synthetic genuine alpha does fire the pass, so the gate is not dead code).
Its sharpest observation: the result is over-determined, not marginal, because the headline already
fails at the easiest threshold (a single-trial PSR of 0.9318 net of the differential cost, before
the deflation even binds). Two Low and one Medium finding, all cosmetic and non-blocking: the
from_2008 recency slice receives the most-generous (zero block-deflation) treatment, since its
Politis-White block length is below one, and still misses the bar; and the fetch timestamp and the
upstream-file-hash indirection in the provenance are harmless. The reviewer's one emphasis is the
deployable-versus-QUAL gap (already in the caveats): no live deployment should be inferred from a
gross PSR that the deployable differential cost alone already takes under.

## The live-deployment angle

The operator intended to deploy this live if it passed all gates. It does not: the gross number is a
near-miss that the deployable differential cost and the multiple-testing deflation turn into a clear
fail. The genuine, significant quality premium (+0.65%/yr Fama-French alpha) is real, but it is too
thin to overcome the honest cost of holding a quality ETF over a market ETF, and it has decayed in
the post-publication era. The honest finding, surfaced before any capital was committed, is that the
operating-profitability tilt is a real academic premium and not a retail make-money edge.
