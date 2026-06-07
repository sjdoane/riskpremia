# 0008: the cross-asset defensive trend gate (Study 6)

Study 6 tests the ADR 0008 cross-asset defensive trend rule on public-domain data. The goal
is not to optimize a trend model. It is to ask whether one frozen, retail-executable
long-or-cash rule across genuinely low-correlated asset classes survives the same
net-of-cost, deflated, reproducible kill discipline as the earlier studies, where two
correlated crypto assets did not (Study 4).

## Frozen rule

- Universe: US equity (Kenneth French daily market total return) and long-term US Treasury
  (ten-year total return reconstructed from the US Treasury par yield curve), with the
  one-month Treasury bill (Kenneth French risk-free rate) as cash.
- Window: the 1990-onward intersection of the two sources' trading days, through the frozen
  end-date 2026-03-31. Daily marks; monthly rebalance.
- Signal: at each month-end, a sleeve is active only when its total-return index is strictly
  above its ten-month simple moving average (the mean of the last ten monthly closes).
- Execution: the month-end signal governs only the next month; the position fills on the
  next month's first trading day and earns from there. No same-bar leak.
- Weighting: a fixed one-over-N-of-the-universe per active sleeve, with inactive capital in
  bills. Equal weight is frozen to remove the volatility-target degree of freedom.
- Costs: a fund expense ratio charged on held notional accrued daily (0.10 percent equity,
  0.15 percent long Treasury), plus a five-basis-point per-side turnover cost, rounded up.
- Scoring series: the daily net return in excess of the one-month bill. Cash earns the bill,
  so its excess is zero and a pass cannot rest on bill carry.

## Data path (built as designed, with two recorded substitutions)

ADR 0008 named FRED `DGS10` for the bond yield and allowed gold only if a clean public-domain
price series existed. During the build:

- Gold was dropped from the headline universe: the FRED London gold series returned HTTP 404
  (the licensed series is no longer served), and no other free, keyless, public-domain daily
  gold price path was found. This is the ADR 0008 pre-registered fallback (equity plus
  Treasury).
- The ten-year yield is sourced from the US Treasury daily par yield curve
  (home.treasury.gov), fetched per year, rather than FRED `DGS10`. FRED's bulk `DGS10` fetch
  was unreliable from the build machine (repeated connection failures on the large series),
  while the Treasury endpoint is the original source of the same ten-year par yield and is
  reachable per year. The data is identical in content; the par-yield history begins in 1990,
  which sets the common window.

Both substitutions are immaterial to the rule and the kill criterion; they are documented for
the audit trail and amended into ADR 0008.

## Scoring

Because the rule is frozen and no-fit, the statistic is conditional PSR(0), not Deflated
Sharpe. The pre-registered primary gate is the full-sample conditional PSR(0) on the daily
excess series. Reported alongside, never as the headline:

- The non-overlapping monthly conditional PSR(0). The honest independent unit is the month
  (the daily marks within a held month share one position), so the monthly figure is the
  conservative cross-check; it gives the same verdict.
- The purged-CPCV worst-fold conditional PSR(0) (the worst-regime stress). Path-stitching is
  not reported: for a no-fit rule the returns do not depend on a training set, so every
  stitched path equals the full sample and the path-stitched PSR degenerates to the
  full-sample PSR. The worst held-out fold is the meaningful CPCV stress.
- The 2008-onward and 2022-onward recency slices.
- A Deflated-Sharpe ladder at 8, 16, and 32 assumed inherited trials, with the cross-trial
  Sharpe variance estimated from the moving-average-length variant family.
- Per-sleeve attribution: each sleeve run alone (the equity-only and bond-only
  counterfactuals), to locate where the edge and the regime risk live.

Pre-registered kill checks: kill if the full-sample conditional PSR(0) is below 0.95, if the
maximum drawdown exceeds 35 percent, or if costs exceed 25 percent of the gross gain.

## Artifact

`scripts/run_xtrend_gate.py` rebuilds `artifacts/xtrend_gate.json` from
`tests/data/xtrend_panel.csv` and `tests/data/xtrend_panel_sources.json`, both SHA256-stamped
in `data/snapshots/manifest.toml`. The panel is an as-of snapshot of openly-redistributable
public-domain research data; the checksum attests tamper-evidence of the committed series,
not vendor byte-fidelity. `scripts/regenerate_xtrend_figures.py` renders
`docs/figures/xtrend_equity.png` (the net-wealth curve with the drawdown panel) and
`docs/figures/xtrend_gate_scorecard.png` (the conditional PSR(0) by window and sleeve against
the 0.95 bar) purely from the committed artifact (the `figures` extra, a skipif render test).

## Result

The rule clears the pre-registered primary gate but is regime-dependent. Headline values:

- Daily observations: 8843; months: 425; window 1990-11-01 to 2026-03-31; time in market 94.4%.
- Mean excess return: 0.0181 percent per day; annualized excess volatility 6.6 percent;
  annualized excess Sharpe about 0.69.
- Full-sample conditional PSR(0): 0.9996 (passes the 0.95 bar).
- Monthly non-overlapping conditional PSR(0): 0.9970 (425 months; same verdict).
- Deflated Sharpe at 8, 16, 32 trials: 0.999, 0.999, 0.998 (survives multiple-testing
  deflation; the variant Sharpes are close, so the cross-trial variance is small).
- CPCV worst-fold conditional PSR(0): 0.7216 (median 0.9400).
- Recency: 2008-onward 0.9730; 2022-onward 0.4016.
- Per-sleeve standalone conditional PSR(0): equity 0.9981, long Treasury 0.8456.
- Net excess gain 360.6 percent; net total gain 1032.7 percent; bill carry 145.9 percent.
- Maximum drawdown 11.2 percent; cost share 2.8 percent of gross; CAGR 7.1 percent.

The verdict is:

```text
NOT KILLED but regime-dependent. Full-sample and monthly conditional PSR(0) clear 0.95 and
survive deflation, with low drawdown and negligible costs, but the CPCV worst fold (0.72) and
the 2022-onward recency slice (0.40) are below the bar.
```

This is the project's first result to clear the deflated full-sample gate. It is an honest
qualified pass, not a clean unconditional one: the strategy is a classic cross-asset trend
rule, and the contribution is the reproducible, deflated, net-of-cost validation on clean
public-domain data, not a novel edge. The per-sleeve attribution locates the regime risk: the
equity trend sleeve carries the result (standalone PSR 0.998), while the long-Treasury sleeve
is weaker on its own (0.846) and is the source of the 2022-onward weakness (the rate-driven
bond drawdown). The full-sample pass does not rest on the long bond bull; the equity-only
counterfactual still clears the gate.

## Design review findings and resolutions

The pre-implementation senior-quant design review of the ADR pre-registration returned three
blocking findings, all resolved before the rule was frozen: a monthly worst-fold gate is
un-passable on power (resolved by scoring the daily mark-to-market series with the full-sample
conditional PSR(0) as the primary statistic and the CPCV worst fold as reported stress); the
bond reconstruction formula was unstated (resolved by writing the start-of-period-yield
constant-maturity formula into the ADR); and the public-domain sources are mutable (resolved
by as-of fixtures, a frozen data end-date, and a tamper-evidence framing).

## Post-implementation review

The post-implementation review reproduced the full daily excess series independently (maximum
absolute difference zero across 8843 days) and the headline statistics to the digit, and it
attacked the single most dangerous failure mode for a pass: that scoring daily marks of a
monthly rule inflates the effective sample and the PSR. That hypothesis was found false. The
daily excess series has negative net autocorrelation (the summed lag-one-to-forty-nine
autocorrelation is about -0.15), so the block deflation is conservative rather than
inflationary, and the non-overlapping monthly conditional PSR(0) (0.997, the honest
independent unit) gives the same verdict. The signal timing was re-derived with no look-ahead
(zero signal mismatches over 426 months), the bond reconstruction was confirmed point-in-time,
the costs were confirmed correct (expense on held notional, cost share on the gross
denominator), and the result was confirmed not driven by a few outlier years.

Two medium findings were addressed by adding diagnostics to the artifact, not by changing the
rule: the per-sleeve standalone conditional PSR(0) (so the regime risk is correctly located in
the long-Treasury sleeve, and the equity-only counterfactual is visible), and the
non-overlapping monthly conditional PSR(0) reported alongside the daily one (so the honest
monthly independent unit is explicit and the daily scoring is shown to be for resolution, not
to inflate the sample). The verdict, the recency weakness, and the per-sleeve attribution are
all surfaced in the artifact, not buried.

## Verification

The committed artifact reproduces offline from the committed panel, the panel is tamper-evident
against the manifest, and the live sources pass the network smoke tests. Full verification is
recorded in `CHANGELOG.md` for the PR that adds this design note, code, fixtures, and artifact.
