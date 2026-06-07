# Volatility-Managed Equity: Fork, Literature Check, and Method

Date: 2026-06-07.
Related decision: [ADR 0010](../decisions/0010-pivot-to-volatility-managed-equity.md).

## The fork

After the Study 7 funding-dispersion measurement, the project stood at four honest nulls, two
measurements, and one qualified, regime-dependent deployable pass (Study 6). The standing goal is
a portfolio of strategies that plausibly make money at retail and are recruiter-impressive
through rigor. The fork question for Study 8: take a deployable swing, and if so, which one.

A four-lens decision review (realist, quant, builder, growth) and an adversarial cross-check were
run as five independent reviews over a candidate shortlist: a volatility-managed equity strategy
(the ADR 0008 registered backup), industry/sector momentum on the Kenneth French industry
portfolios, and open alternatives. All five agreed on one point without dissent: Study 8 should
be a deployable swing, not a third measurement, because after a qualified pass and two
measurements a third measurement adds little to the make-money goal.

## The four lenses

- **Realist.** Hard-nosed on what a retail account can actually earn. Found that the published
  record is decisive that volatility-managed equity fails out-of-sample net of cost, and that
  industry momentum is the more economically durable survivor; leaned toward a momentum rule with
  a trend overlay to cut turnover and crash beta. Go on a deployable swing.
- **Quant.** Statistical defensibility. Surfaced the key insight that reshaped the decision: the
  literature predicts a clean, single-bit, pre-committable outcome, the managed market survives a
  deflated net-of-cost gate while the managed factors do not, so a volatility-managed study is
  defensible regardless of sign if it is scoped to the managed market and scored as a direct
  managed-versus-unmanaged test (the lowest degrees-of-freedom framing) rather than a spanning
  regression (the Cederburg-unstable, p-hackable object). Ranked industry momentum last for
  defensibility because its design space is a large forking-path surface. Go on a deployable
  swing.
- **Builder.** Build cost and reuse. Found the volatility-managed market the smallest honest
  build by a wide margin: the exact data (Kenneth French daily `Mkt-RF` and `RF`) is already
  committed and stamped for Study 6, and roughly ninety percent of the Study 6 gate (the
  monthly-signal-from-daily machinery, the daily mark-to-market simulator with held-notional
  expense and per-side turnover, the full scoring and CPCV and deflation and artifact stack)
  reuses verbatim; the only new load-bearing code is the variance estimator and the leverage cap.
  Industry momentum is materially larger (a new industry-portfolio file format and a
  cross-sectional portfolio engine). Go on a deployable swing.
- **Growth.** Recruiter and portfolio value. Found that adjudicating a famous, still-open
  published debate on the project's own deflated net-of-cost gate is high signal regardless of
  sign and on-brand ("honest nulls plus rigorous gates"), and that the Moreira-Muir versus
  Cederburg versus Barroso-Detzel versus DeMiguel thread is actively contested in top journals
  through 2024, whereas industry momentum reads as a settled classic. Go on a deployable swing.

## The adversarial cross-check

The adversarial review argued to switch to industry momentum and raised the two strongest
objections to the volatility-managed pick:

1. It is a pre-flagged likely null, so it risks adding a fifth null after a qualified pass.
2. It is mechanically redundant with Study 6 (both are long equity, de-risked on a signal, into
   bills), and the researcher degrees of freedom (the variance window, the leverage cap, the
   rebalance) make any verdict weak.

It also conceded the one fact that cuts the other way: Barroso and Detzel's sole survivor after
costs is the volatility-managed market, which is exactly the sleeve the study scales.

Both objections are answered by the scope and the pre-registration in ADR 0010, not waved away:

- The signal is volatility timing (scale by realized variance), not the price trend of Study 6
  (above or below a ten-month average). The two are near-orthogonal and frequently disagree (a
  calm market below its trend; a turbulent market above it), so the study is not a re-run of
  Study 6. The managed-versus-Study-6 return correlation is reported so the reader can see the
  distinctness rather than take it on faith.
- The degrees of freedom are frozen in the ADR before any code: a single previous-month realized
  variance estimator, the Moreira-Muir c-normalization (managed volatility equal to unmanaged
  volatility full-sample, which removes the free-leverage confound), a single primary leverage
  cap, a single rebalance frequency, and a single primary statistic. The leverage-cap
  sensitivities are reported as stress, not searched for a winner.
- The likely-null risk is converted into a feature: the headline is the literature's predicted
  market-survives, factors-die asymmetry, a falsifiable prediction. A managed-market pass is a
  second deployable result distinct from Study 6; a managed-market fail under this project's
  conservative cost-and-deflation stack is a clean replication of Cederburg. Either outcome ships
  as a defensible, on-brand deliverable.

Industry/sector momentum is recorded as the registered backup if Study 8 lands as a null.

## Literature check (the contested claim)

- Moreira and Muir (2017, JF), "Volatility-Managed Portfolios": scaling factor exposure
  inversely to recent realized variance produced large in-sample alphas and Sharpe-ratio gains.
- Cederburg, O'Doherty, Wang, and Yan (2020, JFE), "On the performance of volatility-managed
  portfolios": reasonable out-of-sample, real-time versions generally earn lower
  certainty-equivalent returns and Sharpe ratios than the unmanaged portfolios, primarily because
  the underlying spanning regressions are structurally unstable.
- Barroso and Detzel (2020, JFE), "Do limits to arbitrage explain the benefits of
  volatility-managed portfolios?": after transaction costs the managed versions of every factor
  except the market produce roughly zero abnormal return and lower Sharpe ratios; the cost of the
  scaling turnover is the mechanism.
- "The disappearing profitability of volatility-managed equity factors" (2023) and DeMiguel,
  Martin-Utrera, and Uppal (2024, JF), "A Multifactor Perspective on Volatility-Managed
  Portfolios": reinforce that the factor-level benefits are fragile and largely vanish in a
  multifactor, net-of-cost, out-of-sample setting.

The consensus the project can pre-register: the managed market is the lone robust corner; the
managed factors are not. This is the asymmetry Study 8 tests.

## Data-path verification (Gate 1, PASS, pre-cleared)

The existing `src/riskpremia/data/sources/ken_french.py` already fetches the daily research
factors zip and the committed Study 6 panel already carries the daily `Mkt-RF` and `RF`, so the
primary (the managed market) needs no new data. The realized-variance signal is computable from
the committed daily market excess returns with zero new plumbing. The secondary factor set comes
from the same Kenneth French library and loader family (SMB and HML are already in the fetched
file; RMW, CMA, and the momentum factor are standard daily zips from the same openly-redistributed
source), a small one-time extension. The stress gate passes by construction: the deployable
implementation is a leveraged-ETF-or-cash split with no short leg, no margin account, and no
inaccessible financing.

## Decision

Build a volatility-managed market-portfolio study (Study 8), scoped to the managed market, scored
as a direct managed-versus-unmanaged test net of the scaling-turnover and financing costs and
deflated, with the predicted market-survives, factors-die asymmetry pre-registered as a secondary.
Industry/sector momentum is the registered backup. The frozen method is in ADR 0010; the build
and the measured result follow.

## References

- Moreira and Muir (2017), Volatility-Managed Portfolios, Journal of Finance.
  https://www.nber.org/system/files/working_papers/w22208/w22208.pdf
- Cederburg, O'Doherty, Wang, and Yan (2020), On the performance of volatility-managed
  portfolios, Journal of Financial Economics.
  https://www.sciencedirect.com/science/article/abs/pii/S0304405X2030132X
- Barroso and Detzel (2020), Do limits to arbitrage explain the benefits of volatility-managed
  portfolios?, Journal of Financial Economics.
  https://www.sciencedirect.com/science/article/abs/pii/S0304405X21000775
- DeMiguel, Martin-Utrera, and Uppal (2024), A Multifactor Perspective on Volatility-Managed
  Portfolios, Journal of Finance.
  https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13395
- The disappearing profitability of volatility-managed equity factors (2023).
  https://www.sciencedirect.com/science/article/abs/pii/S1386418123000551
