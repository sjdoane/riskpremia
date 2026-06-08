# Quality (Profitability) Tilt: Fork, Literature Check, and Method

Date: 2026-06-07.
Related decision: [ADR 0012](../decisions/0012-pivot-to-quality-tilt.md).

## The fork

After the Study 9 industry-trend timing null, the registered backup was a long-only low-volatility
(low-beta) tilt, the one genuinely orthogonal, non-trend, non-timing premium left. An adversarial
cross-check (web-searching the literature) plus two live data probes redirected it to a long-only
profitability (quality) tilt.

## The adversarial redirect

The cross-check argued the low-volatility tilt is the wrong Study 10 on three points:

- **The unlevered retail form is a likely eighth null.** The genuine betting-against-beta anomaly
  lives in a leveraged long-short portfolio; an unlevered retail investor holding the low-beta
  quintile only harvests lower volatility for lower absolute return, a risk-adjusted result that
  re-proves the existing thesis (Studies 6, 8, 9: less risk, no excess return over buy-and-hold) in
  a new costume rather than advancing the make-money goal.
- **It is the most crowded and decayed major factor.** The documented low-volatility-ETF inflows
  after 2011, the 2016 low-volatility crash when the trade got rich, and post-publication decay make
  even the risk-adjusted edge fragile on a full-sample-through-2026 deflated gate.
- **The data is monthly only.** The clean Kenneth French beta-sorted series is monthly, the
  project's weakest-powered test for its most contested candidate, breaking the daily-data discipline
  of Studies 6 to 9.

The cross-check's alternative, a long-only profitability (quality) tilt, is stronger on every
dimension: it is the one major factor whose long leg carries a positive absolute return tilt (so a
net-of-market pass, a genuine make-money result, is possible rather than a foregone risk-reduction
null); it is the least crowded and most out-of-sample-robust major factor (robust across 23 countries
1987 to 2019); it is low-turnover by construction, so the deflated net-of-cost gate that kills
crowded high-turnover factors is where quality is strongest; and the Kenneth French operating-
profitability portfolios are available daily.

## The data probes (the feasibility check)

- `Portfolios_Formed_on_OP_Daily` (operating profitability) is clean: value-weighted daily, 1963-07
  to 2026-04, 15813 rows, zero missing markers, with `Hi 30` and `Hi 20` (the high-profitability
  tercile and quintile) as deployable long legs. The market and the one-month bill come from the same
  Kenneth French factor library already in the loader.
- `Portfolios_Formed_on_BETA` (the low-volatility candidate) is monthly only (1963 onward); the daily
  variance and residual-variance files return HTTP 404. This confirmed the data divergence that
  weighed against low-volatility.

## Decision

Build a long-only quality (profitability) tilt: hold the high-operating-profitability value-weighted
portfolio (the `Hi 30` tercile headline), scored as the net-of-market difference over buy-and-hold
the value-weight market. Both legs are value-weighted, so the difference is a clean net-of-market
comparison with no equal-weight-versus-value-weight confound (the seam the Study 9 design review
caught), and it reuses the Study 8 and Study 9 difference-kill machinery. A Fama-French regression
attributes the net-of-market difference to pure profitability versus bundled size, value, and beta
tilts. The low-volatility tilt is the deferred candidate; a value (HML) tilt was weighed and deferred
as more cyclical and weaker post-2008.

The make-money shot is genuine: profitability is the orthogonal factor most likely to clear a
deflated net-of-cost gate as a real result rather than a risk-reduction null, and a null is still an
honest, valuable outcome. The frozen method is in ADR 0012; the build and the measured result follow.

## References

- Novy-Marx (2013), The Other Side of Value: The Gross Profitability Premium, Journal of Financial
  Economics. https://www.sciencedirect.com/science/article/abs/pii/S0304405X13000044
- Fama and French (2015), A Five-Factor Asset Pricing Model, Journal of Financial Economics.
  https://www.sciencedirect.com/science/article/abs/pii/S0304405X14002323
- Frazzini and Pedersen (2014), Betting Against Beta, Journal of Financial Economics.
  https://www.nber.org/system/files/working_papers/w16601/w16601.pdf
- Asness, Frazzini, Pedersen (2019), Quality Minus Junk, Review of Accounting Studies.
  https://link.springer.com/article/10.1007/s11142-018-9470-2
