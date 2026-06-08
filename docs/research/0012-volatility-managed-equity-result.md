# Volatility-Managed Market: the Measured Result

Date: 2026-06-07.
Related decision: [ADR 0010](../decisions/0010-pivot-to-volatility-managed-equity.md) (with its
design-review amendment).
Pre-registration and method: [docs/research/0011](0011-volatility-managed-equity-design.md).

## Verdict

**NON-VIABLE: a clean Cederburg replication (an honest null).** Volatility-managing the US equity
market does not beat buy-and-hold once the realistic retail leverage cap and net-of-cost frictions
are applied. The single sentence:

> The managed-minus-unmanaged difference (the kill statistic) has a full-sample conditional PSR(0)
> of 0.457, far below the 0.95 bar. A real gross volatility-timing alpha of +1.78%/yr at equal
> volatility (the Moreira-Muir effect is present in this data) does not survive: the 2.0x retail
> leverage cap removes -2.14%/yr (the dominant drag, 80%) and net-of-cost frictions remove a
> further -0.53%/yr (20%), leaving -0.88%/yr. The expanding-window real-time c agrees.

This was designed to be defensible regardless of sign: a pass would have been a second deployable
result distinct from Study 6, and a fail is a clean replication of the Cederburg, O'Doherty, Wang,
and Yan (2020) and Barroso and Detzel (2020) finding that the realistic implementation erases the
in-sample alpha. It is the sixth honest non-make-money result and an on-brand null.

## The measured object

The US equity market excess return (Kenneth French daily `Mkt-RF`, the committed Study 6 fixture,
so the primary needs no new data) scaled monthly by `w_m = c / RV_{m-1}`, where `RV_{m-1}` is the
previous calendar month's realized variance of the daily excess return and `c` is the Moreira-Muir
normalization computed on the UNCAPPED weight so the managed full-sample volatility equals the
unmanaged. The 2.0x cap is a separate retail friction; costs are one coherent model (10 bps expense
on the exposure, a 1.0%/yr financing spread on the levered portion over the bill, 5 bps per-side
turnover on the continuous monthly weight change). The benchmark is buy-and-hold the market at the
same expense. Window 1990-02 to 2026-03, 9032 daily observations (block-deflated effective T 609).

## Result

| Quantity | Value |
| --- | --- |
| PRIMARY: managed-minus-unmanaged difference PSR(0) | **0.457** (bar 0.95) |
| Difference annualized Sharpe | **-0.07** |
| Monthly non-overlapping difference PSR(0) | 0.370 (434 months) |
| Expanding-window (real-time) c difference PSR(0) | **0.429** (agrees) |
| Gross timing alpha (uncapped, costless, equal vol) | **+1.78%/yr** (Sharpe 0.11) |
| Leverage-cap drag / cost drag / net | **-2.14% / -0.53% / -0.88%** per year |
| CPCV worst fold / recency 2008 / recency 2022 | 0.127 / 0.436 / 0.471 |
| Deflated Sharpe at 8 / 32 / 128 trials | 0.385 / 0.354 / 0.331 |
| Cap sensitivity 1.0x / 1.5x / 2.0x | 0.336 / 0.413 / 0.457 |
| Financing 0.5% / 1.0% / 2.0% | 0.463 / 0.457 / 0.444 |
| Context: managed Sharpe / unmanaged Sharpe | 0.553 / 0.484 (the equity premium, not the kill) |

### Reading the result

- **The kill is the difference, not the level.** A c-normalized managed market is a levered
  long-equity position whose standalone Sharpe (0.553) is the equity premium; the unmanaged market
  Sharpe is 0.484. Both are "high," and using the standalone managed PSR would have falsely implied
  a result. The managed-minus-unmanaged difference is what isolates volatility-timing value, and it
  is null (PSR 0.457, annualized Sharpe -0.07). This is the single most important methodological
  point, caught by the design review before the build.
- **The cap, not cost, is the dominant killer, and the gross alpha is real.** The decomposition is
  explicit in the artifact: the uncapped, costless timing alpha is +1.78%/yr at equal volatility
  (the Moreira-Muir effect exists in this data), but the 2.0x retail leverage cap removes -2.14%/yr
  (the high-weight calm months that the strategy relies on are exactly the ones clipped), and costs
  remove a further -0.53%/yr. Disclosing this is the honest framing: the null is not a cost trick,
  it is the realistic-implementation mechanism Cederburg and Barroso-Detzel identified.
- **It is robust, not one unlucky slice.** Every reading of the kill is below the bar: the
  full-sample, the monthly, the real-time expanding-window c, the CPCV worst fold, both recency
  slices, the deflated Sharpe to 128 trials, and all three leverage caps (the de-risk-only 1.0x cap
  is the worst at 0.336, confirming that forfeiting the upside leg while keeping de-risking is the
  structurally hostile case).
- **Even the market sleeve is a null under this stack.** Barroso and Detzel reported the managed
  market as the lone cost-survivor among the factor zoo. Under this project's conservative
  cap-plus-cost stack over 1990 to 2026, even the market is a null. This is an honest, slightly
  stronger statement than the literature's, driven by the leverage cap, and it is reported as such,
  not oversold as a contradiction of Barroso-Detzel.

### Distinct from Study 6 (the redundancy objection, answered)

The adversarial cross-check warned the managed market might be redundant with Study 6 (both long
equity, de-risked on a signal, into bills). The numbers answer it: the daily level correlation is
0.713 (high by construction, as both are long equity much of the time), but the managed-minus-
unmanaged difference correlates only 0.042 with the Study 6 excess (the volatility-timing signal is
near-orthogonal to the price trend), and a 50/50 combination Sharpe (0.660) is below Study 6 alone
(0.692), so the managed market adds nothing to the existing deployable result either. The signals
are genuinely distinct; the managed market is simply not additive value.

## Honesty guardrails (met)

- The kill is the difference over buy-and-hold, never the standalone levered-equity Sharpe.
- The full-sample c is labeled an in-sample normalization; the expanding-window real-time c is
  reported as the out-of-sample check and agrees.
- The cost model is one coherent implementation, and the gross decomposition shows the cost was not
  tuned to force the null (the dominant drag is the ADR-frozen leverage cap, not cost).
- The deployment claim is a clean null; no tradeable edge is asserted.

## Reproduce

```powershell
$env:PYTHONIOENCODING="utf-8"
$py = "C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe"
# No-network: the committed Study 6 panel rebuilds the committed gate artifact (the numbers above)
& $py -m scripts.run_volmanaged_gate
# Render the figures from the committed panel + artifact (the figures extra)
& $py -m scripts.regenerate_volmanaged_figures
# The offline reproduction test rebuilds the artifact from the committed fixture to the digit
& $py -m pytest -q tests/unit/test_volmanaged_reproduces.py
```

## Figures

- `docs/figures/volmanaged_wealth.png`: the managed and unmanaged net wealth (overlapping) and
  their ratio over time, with the gross-alpha-dies-on-the-cap caption.
- `docs/figures/volmanaged_scorecard.png`: the difference PSR(0) across every stress dimension, all
  below the 0.95 bar.

## Post-implementation review

An adversarial post-implementation review returned a SHIP verdict with no Critical or High
findings. It reproduced the headline from scratch, verified the c-identity to 1e-8, reconstructed
the cost series to exactly 0.0, confirmed the artifact reproduces byte-for-byte, and independently
derived the +1.78% / -2.14% / -0.53% attribution. Its one Medium finding (surface the positive
gross alpha and name the leverage cap, not cost, as the dominant killer) is resolved here and in
the artifact's gross-decomposition fields and the reworded verdict.

## The factor-asymmetry secondary (built): a uniform null

The pre-registered secondary applies the identical scaler to the long-short Kenneth French factors
(SMB, HML, RMW, CMA, and the momentum factor WML), each scored as a managed-minus-unmanaged
difference with a turnover-only cost (a long-short factor cannot be levered through a market ETF, so
there is no financing leg and no exposure expense; the c-normalization and 2.0x scaling cap match
the market). 1990-01 to 2026-04, 9149 daily observations.

| Factor | Difference PSR(0), full-sample c | Difference PSR(0), real-time c | Gross alpha | Net |
| --- | --- | --- | --- | --- |
| Market (the primary) | 0.457 | 0.429 | +1.78%/yr | -0.88%/yr |
| SMB | 0.197 | 0.273 | -0.94%/yr | -1.43%/yr |
| HML | 0.430 | 0.442 | -0.80%/yr | -0.71%/yr |
| RMW | 0.435 | 0.271 | +1.02%/yr | -0.46%/yr |
| CMA | 0.052 | 0.120 | -1.04%/yr | -1.39%/yr |
| WML (momentum) | 0.826 | **0.489** | +11.57%/yr | +4.28%/yr |

**A uniform null.** The managed market and all five managed factors fail the (undeflated)
net-of-cost PSR(0) gate, so the literature's predicted market-survives, factors-die asymmetry does
not hold under this conservative retail stack. The pre-registered asymmetry (confirmed only if the
managed market clears the bar and at least four of five factors do not) is not confirmed, because
the market is itself a null.

**Momentum is the apparent standout, but it is a look-ahead artifact.** Under the full-sample c,
WML has a large +11.57%/yr gross volatility-timing alpha (the Barroso-Santa-Clara managed-momentum
effect, where momentum crashes cluster in high-volatility states) and the highest full-sample
difference PSR (0.826), the closest to surviving. But this does not survive the project's own
pre-registered expanding-window real-time c: WML's out-of-sample PSR collapses to 0.489 and its net
alpha to about zero, because the full-sample c is set knowing WML's ex-post volatility and a large
share of the apparent edge lives in the 1994-95 expanding-window burn-in that a real-time strategy
could not yet trade. So even the managed-momentum near-miss is an in-sample artifact, and the
uniform null is robust out-of-sample. This was caught by the secondary's adversarial
post-implementation review and resolved by adding the expanding-window c row for every factor.

The committed artifact is `artifacts/volmanaged_factor_asymmetry.json` (rebuilt offline from the
committed factor panel `tests/data/volmanaged_factor_panel.csv`); the figure is
`docs/figures/volmanaged_factor_asymmetry.png`.

## Registered next step

Industry/sector momentum is the registered backup (a long-only, retail-executable, distinct premium
on the same Kenneth French library), the natural next deployable swing.
