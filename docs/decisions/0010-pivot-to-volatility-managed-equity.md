# ADR 0010: a volatility-managed market-portfolio study

Status: Accepted. Pre-registration before implementation.
Date: 2026-06-07.
Authors: Sam Doane (strategy fork after the Study 7 measurement, with a four-lens decision
review, an adversarial cross-check, a literature check on the contested claim, and a data-path
verification against the already-committed Study 6 fixtures).

## Context

The project has run seven studies: four honest nulls (funding carry, CTREND, BTC/ETH trend, and
the VRP tradeable layer), two measurements (the VRP measurement layer and the Study 7 funding
dispersion), and one qualified, regime-dependent deployable pass (Study 6, a cross-asset
defensive trend). The standing goal is a portfolio of kill-gate-tested strategies that plausibly
make money at retail and are recruiter-impressive through rigor. After a qualified pass and two
measurements, the marginal value is highest from a second, distinct deployable result, so Study
8 is a deployable swing, not a third measurement.

A fresh fork weighed the candidates: a volatility-managed equity strategy (the ADR 0008
registered backup), industry/sector momentum on the Kenneth French industry portfolios, and open
alternatives. A four-lens decision review (realist, quant, builder, growth) and an adversarial
cross-check were run as independent reviews; all five agreed Study 8 should be a deployable
swing.

The decisive facts, with the contested literature:

- **Volatility management is a documented out-of-sample, net-of-cost failure for the factor zoo,
  with one survivor: the market.** Moreira and Muir (2017, JF) reported large in-sample alphas
  from scaling factor exposure inversely to recent realized variance. The replication record
  overturned this for factors: Cederburg, O'Doherty, Wang, and Yan (2020, JFE) found
  out-of-sample versions generally underperform the unmanaged portfolios because the underlying
  spanning regressions are structurally unstable; Barroso and Detzel (2020, JFE) found that after
  transaction costs the managed versions of every factor except the market produce roughly zero
  alpha; "The disappearing profitability of volatility-managed equity factors" (2023) and
  DeMiguel, Martin-Utrera, and Uppal (2024, JF) reinforce this. The single robust corner is the
  volatility-managed market portfolio.
- **That asymmetry is a pre-committable, falsifiable prediction**, which makes the result
  defensible regardless of sign: the literature predicts the managed market survives a
  deflated, net-of-cost gate while the managed factors do not. A pass corroborates the one robust
  corner; a fail under this project's conservative cost-and-deflation stack is a clean
  replication of Cederburg. There is no embarrassing middle.
- **The build is near-zero-feasibility-risk.** The exact data object (the Kenneth French daily
  `Mkt-RF` and `RF`) is already committed and SHA256-stamped for Study 6, and the deflated-Sharpe
  and purged-CPCV gate, the cost model, and the committed-fixture and offline-reproduction
  pattern all reuse from Study 6.

The adversarial cross-check argued for industry momentum instead and raised two real objections
to the volatility-managed pick: that it is mechanically redundant with Study 6 (both are long
equity, de-risked on a signal, into bills), and that the researcher degrees of freedom (the
variance-estimator window, the leverage cap, the rebalance frequency) make any verdict weak.
Both are answered by the scope and the pre-registration below: the signal is volatility timing,
not the price trend of Study 6 (the two frequently disagree and are near-orthogonal); the
comparison is a direct managed-versus-unmanaged test rather than a spanning regression (the
lowest-degrees-of-freedom framing); and every free parameter is frozen here before any code.
Industry momentum is recorded as the registered backup.

## Decision

**Build a volatility-managed market-portfolio study (Study 8), retail-deployable, that
adjudicates the contested volatility-managed claim on the project's deflated, net-of-cost gate.**
The headline is the volatility-managed US equity market portfolio scored against the unmanaged
buy-and-hold market; the literature's predicted market-survives, factors-die asymmetry is
pre-registered as a secondary test so the result is informative either way.

## The measured object and method (frozen)

### The signal (frozen, no grid)

Let `r_t` be the daily US equity market excess return (`Mkt-RF` from the Kenneth French daily
factors). The volatility-managed weight for month `m` is the Moreira-Muir inverse-variance scale

```text
w_m = c * sigma_target^2 / RV_{m-1}
```

where `RV_{m-1}` is the realized variance over the **previous** calendar month (the sum of
squared daily excess returns, a single pre-committed estimator, no alternative windows), and `c`
is a single full-sample normalization constant chosen so that the managed series has the **same
full-sample realized volatility as the unmanaged market**. This c-normalization is the
Moreira-Muir identifying convention and it removes the free-leverage confound: the managed and
unmanaged series are compared at equal volatility, so a higher Sharpe is timing skill, not extra
leverage. `sigma_target` is absorbed into `c` and is not a separate knob. The weight is applied
for the whole of month `m` (the signal uses only month `m-1` data, so it is point-in-time) and is
floored at 0.

### The leverage cap and the retail implementation

The weight is capped at **2.0** (the primary), the retail-realistic ceiling. The deployable
implementation is a position split between a broad US equity ETF (or a 2x leveraged equity ETF
such as SSO for the levered leg) and the one-month bill, not a margin account, so the leverage is
internal to the ETF, daily-reset, cannot trigger a margin call, and the position value cannot go
below zero. The 1.0x (de-risk-only, no leverage) and 1.5x caps are reported as registered
sensitivities, not as separate trials. A financing cost is charged on the levered portion (the
weight above 1.0) at the one-month bill plus a retail spread.

### Costs (the load-bearing honesty seam)

Barroso and Detzel locate the death of the factor versions in the cost of the scaling turnover.
The cost model is therefore charged on the **continuous monthly change in the weight**, not only
on entries: each rebalance pays the Study 6 per-side turnover cost on the absolute weight change
plus the held-notional expense ratio (a leveraged-ETF expense ratio on the levered leg), plus the
financing cost above. A managed series that clears the gate only because the scaling trades were
free is a false pass, so the scaling turnover and the financing are modeled before the rule is
frozen.

### The gate (mirroring Study 6, the no-fit primary)

The c-normalization is a mechanical full-sample constant with no estimated coefficients to hold
out, so the rule is effectively no-fit and the gate mirrors Study 6:

- **Primary (deployability):** the full-sample conditional PSR(0) of the managed market
  portfolio's net-of-cost excess-over-bills return, against the project's 0.95 bar, deflated by
  the frozen trial count. Purged-CPCV worst fold and the 2022-onward recency slice are reported
  as stress, not as the headline kill (path-stitching is degenerate for a no-fit rule, so the
  worst fold is reported, as in Study 6).
- **Adjudication statistic:** the full-sample conditional PSR(0) of the managed-minus-unmanaged
  return series (does volatility timing add risk-adjusted value over buy-and-hold at equal
  volatility?), with its bootstrap confidence interval. This is the direct Cederburg framing and
  is reported alongside the deployability verdict.
- The unmanaged buy-and-hold market is the benchmark throughout; the monthly non-overlapping
  conditional PSR(0) is reported as the honest independent-unit cross-check, as in Study 6.

### The secondary asymmetry test (the predicted market-survives, factors-die result)

The identical frozen scaler is applied to the standard Kenneth French factors (SMB and HML are in
the already-fetched daily file; RMW, CMA, and the momentum factor WML are fetched from the same
Kenneth French library, the same accepted source and loader family). Each managed factor is
scored on the same net-of-cost deflated gate. The headline of this secondary is the **asymmetry**:
whether the managed market clears the bar while the managed factors do not, the literature's
prediction. The trial count for the deflation is the full set of managed series tested (the
market plus the factors), so the market clearing a multi-trial deflation is a strong statement
and a factor null is the expected, on-brand outcome.

### Significance and reproducibility

The vendored deflated-Sharpe, purged-CPCV, and stationary-block-bootstrap stack is reused
unchanged. The trial count is frozen in the registry before the run. The signal, the leverage
cap, the cost model, the rebalance, the primary statistic, and the out-of-sample split are all
frozen in this ADR. The committed series is the daily managed and unmanaged return series with
the manifest stamp; an offline reproduction test rebuilds the artifact from the committed
fixture, as in every prior study.

## Honesty guardrails (pre-registered)

- The literature predicts a likely null for the managed factors and a marginal-at-best result
  for the managed market net of cost. The study ships either way, framed as an **adjudication**
  of a contested published claim, never as a search for an edge.
- The cost must hit the continuous scaling turnover and the financing on the levered leg; a pass
  that survives only by underpricing the scaling trades is reported as a false pass and corrected.
- No degrees-of-freedom grid: a single variance window, a single leverage cap as primary, a
  single rebalance frequency, all frozen here. The leverage-cap sensitivities are reported as
  stress, not searched for a winner.
- The redundancy with Study 6 is addressed head-on: the contribution is volatility timing (a
  distinct, near-orthogonal signal to the price trend) and the adjudication of a specific
  contested claim, not a re-run of the Study 6 rule. If the managed market passes, it is a second
  deployable result distinct from Study 6; the correlation between the two strategies' returns is
  reported.
- No tradeable result is overstated: a qualified or regime-dependent pass is labeled as such, as
  Study 6 was.

## The two pre-code feasibility gates

- **Data gate: PASS (pre-cleared).** The primary needs zero new data: the Kenneth French daily
  `Mkt-RF` and `RF` are already committed and SHA256-stamped in the Study 6 fixture, and the
  loader, the cost model, and the gate exist. The secondary factors come from the same Kenneth
  French library (SMB and HML are already in the fetched file; RMW, CMA, and WML are standard
  daily zips from the same openly-redistributable source), a small one-time extension of the
  existing loader. The data is free, keyless, reproducible, and redistribution-permitted, the
  Study 6 standard.
- **Stress gate: PASS.** The deployable implementation is a position split between a broad equity
  ETF (or a 2x leveraged equity ETF for the levered leg) and the one-month bill. There is no
  short leg, no margin account, and no inaccessible financing; the leveraged ETF's value cannot
  go below zero and cannot trigger a margin call, so a minimum practical position cannot destroy a
  small account. The strategy de-risks as volatility rises, so the realized leverage in a crash
  is low by construction.

## Considered and deferred

- **Industry/sector momentum** on the Kenneth French industry portfolios (the adversarial's
  pick): a genuine, long-only, retail-executable, distinct premium with cost-survival support in
  the literature. Recorded as the **registered backup** if Study 8 lands as a null. Not chosen
  now because its design space (lookback, holding period, number of industries, skip-month,
  volatility scaling) is a large forking-path surface that a strict deflated gate can only
  partially discipline (the quant lens), its honest build is materially larger (a new
  industry-portfolio file format and a cross-sectional portfolio engine, the builder lens), and
  it reads as a settled classic rather than a live debate (the growth lens).
- **A momentum-plus-trend overlay** (the realist's fusion): higher degrees of freedom and it
  rhymes with the project's three existing trend studies; deferred.
- **A managed-factor-only study** (no market sleeve): rejected as a guaranteed null per the
  literature; the market sleeve is included precisely because it is the documented survivor and
  makes the asymmetry test informative.

## First milestone

**The volatility-managed market-portfolio gate, built from the already-committed Kenneth French
daily fixture.** A no-network builder computes the previous-month realized variance, forms the
c-normalized capped managed weight, charges the continuous scaling turnover and the financing,
marks the managed and unmanaged series daily, and writes a committed, SHA256-stamped series plus
the gate artifact (the deployability PSR, the managed-minus-unmanaged adjudication statistic, the
CPCV worst fold and recency stress, the leverage-cap sensitivities, and the
managed-versus-Study-6 correlation). The secondary applies the same scaler to the factor set and
writes the asymmetry table. An offline reproduction test rebuilds the artifact from the committed
fixture. Recruiter-facing figures follow.

## Status

Accepted. The measured object, the frozen method, the gate design, the significance design, and
the honesty guardrails above are pre-registered. The candidate survey, the four-lens and
adversarial findings, the literature check, and the data-path verification are in
`docs/research/0011-volatility-managed-equity-design.md`. The build and the measured result
follow.
