# Industry-Trend Net-of-Market: Fork, Literature Check, and Method

Date: 2026-06-07.
Related decision: [ADR 0011](../decisions/0011-pivot-to-industry-trend-net-of-market.md).

## The fork

After the Study 8 volatility-managed null, the registered backup was cross-sectional
industry/sector momentum. A focused fork ran three independent reviews (an adversarial direction
review, a deployability realist, and a senior-quant design review), each web-searching the
literature, plus two live data probes. The fork redirected the study.

## The three reviews

- **Adversarial (direction).** Argued that cross-sectional industry momentum is the wrong pick and
  the likely seventh null: its cross-sectional premium is roughly flat from 2000 onward (the regime
  the deflated gate stresses), it is largely subsumed by the broad momentum factor (a dominated
  signal), the long-only retail version forfeits about half the academic long-short alpha while
  carrying full market beta, and it rhymes with the project's existing trend studies. Its key
  insight: the impressive long-history industry result in the recent literature (Zarattini and
  Antonacci, a reported Sharpe near 1.4) is a time-series (absolute) trend, not the cross-section, so
  picking the cross-section buys the weak cousin. Verdict: switch the signal to absolute industry
  trend, reusing Study 6's frozen rule; a long-only low-volatility tilt is the orthogonality
  runner-up.
- **Deployability realist.** Found the long-only sector-momentum edge is overwhelmingly a pre-2000
  artifact (Faber relative-strength top-2 roughly matched the market over the recent years before
  costs; business-cycle sector rotation's edge largely disappears after costs). Its decisive point:
  the benchmark choice is everything. Beating the bill is just harvesting equity beta (the Study 8
  trap); the honest deployable bar is beating buy-and-hold the market, net of cost, and against that
  bar the strategy plausibly does not clear. Expected outcome: a likely null, or at best a
  Study-6-style regime-dependent pass that the recency stress should reject.
- **Senior quant (design).** Specified the frozen rule and, most importantly, recommended the kill
  statistic be the net-of-market difference (the held portfolio minus the market), not the
  net-of-bill return, because a long-only equity book passes a bill-excess test on the equity
  premium. It anchored every parameter to the canonical convention (Moskowitz and Grinblatt 1999;
  Jegadeesh and Titman 1993) rather than to what lifts the backtest, and named the single safeguard:
  freeze one headline cell with every other knob declared a deflation variant in advance.

## The data probes (the feasibility tiebreaker)

- The Kenneth French **12-industry daily value-weighted** portfolios are clean and complete (no
  missing markers), 1926 onward, and map closely to the deployable SPDR sector funds. The
  **49-industry** daily set is finer but carries `-99.99` missing markers in early decades (a
  data-cleaning forking-path hazard).
- The Kenneth French **beta-sorted** portfolios (the low-volatility / defensive candidate) are
  **monthly only** (1963 onward); the daily variance and beta files return HTTP 404. So the
  orthogonal low-beta alternative carries a data and apparatus divergence from the project's daily
  pattern, plus an unresolved kill statistic for an unlevered defensive tilt (a Sharpe or
  information-ratio comparison, not a mean difference).

## Decision

Build **absolute (time-series) industry trend on the 12-industry daily portfolios, scored
net-of-market**, reusing Study 6's frozen no-fit ten-month rule. The reasoning:

- It acts on the fork: it pivots off the dominated cross-sectional momentum to the panel's plurality
  signal (the stronger, documented absolute trend) and carries the unanimous net-of-market lesson.
- It has the cleanest combination of a well-defined kill statistic (the managed-minus-market
  difference PSR, the Study 8 machinery), confirmed clean daily data, and maximal apparatus reuse
  (about ninety-five percent of Study 6's gate).
- It is no-fit: the ten-month rule is frozen from Study 6 verbatim, collapsing the
  degrees-of-freedom that damn cross-sectional momentum on a deflated gate.
- It fills a distinct cell: Study 6 only beat the bill (an equity-premium-aided pass); this asks
  whether price-trend timing beats the market. A pass is a strong deployable result; a likely null
  would, with Study 8 (vol-timing) and the net-of-market re-framing, establish that defensive equity
  timing does not beat buy-and-hold at retail.

The genuinely orthogonal low-volatility tilt is recorded as the registered next candidate (a
non-trend premium) once its monthly-data and kill-statistic design is worked out. The frozen method
is in ADR 0011; the build and the measured result follow.

## References

- Moskowitz and Grinblatt (1999), Do Industries Explain Momentum?, Journal of Finance.
  https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00146
- Jegadeesh and Titman (1993), Returns to Buying Winners and Selling Losers, Journal of Finance.
- Daniel and Moskowitz (2016), Momentum Crashes, Journal of Financial Economics.
  https://www.sciencedirect.com/science/article/pii/S0304405X16301490
- Zarattini and Antonacci (2024), A Century of Profitable Industry Trends.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4857230
