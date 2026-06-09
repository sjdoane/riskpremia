# Study 6 Live Deployment Runbook

Date: 2026-06-08. Status: DRAFT plan, not yet live. This is an operational runbook for deploying the
Study 6 cross-asset defensive trend rule with real money. It is paired with
[ADR 0008](../decisions/0008-pivot-to-cross-asset-defensive-trend.md) (the frozen rule) and
[docs/research/0017](../research/0017-portfolio-thesis.md) (where Study 6 sits in the portfolio).

> This is not financial advice. It is an engineering plan for executing a pre-registered, backtested
> rule. The decision, the capital, and the risk are the operator's. Read the honest caveats in
> section 9 before committing a dollar.

## 1. What you are deploying (the honest characterization)

Study 6 is the one candidate of ten that cleared the deflated, net-of-cost gate. It is a frozen,
no-fit, monthly long-or-cash trend rule, and it is the only deployable result in the project. The
honest description, carried straight from the research, governs every expectation:

- **It is risk management, not alpha.** Studies 8 and 9 establish on the same gate that defensive
  timing reduces risk and does not beat buy-and-hold the market. Study 6 clears the bar in excess of
  the bill: it is a crash-insured allocation that compounds at roughly 7.1% with an 11.2% maximum
  drawdown (about a third of a buy-and-hold equity drawdown). It is a classic rule (cross-asset
  trend, dual-momentum-like) validated with full rigor, not a novel edge.
- **It will lag buy-and-hold in bull markets, by design.** Trend rules give up return to cut risk.
  Underperforming the S&P in a rising market is the expected behavior, not a failure, and is not a
  reason to abandon the rule. The payoff is asymmetric: it sidesteps the deep, slow drawdowns
  (2000-2002, 2008).
- **It is regime-dependent, and the bond sleeve is the weak part.** The full-sample and monthly
  statistics pass and survive deflation, but the 2022-onward slice (PSR 0.40), the CPCV worst fold
  (0.72), and the long-Treasury sleeve standalone (0.85) are below the bar. The equity sleeve
  standalone (0.998) carries the result. The rate spike of 2022 is the visible stress.

## 2. The frozen rule (exact, from the repo)

These are the parameters in `src/riskpremia/xtrend/gate.py`, not a re-derivation. Deploy these or
re-run the gate; do not silently re-optimize.

| Parameter | Value |
| --- | --- |
| Sleeves | equity, bond (long-Treasury, the 10-year par-yield series) |
| Cash | 1-month Treasury bill |
| Weight per active sleeve | 1/N = 0.5 (two sleeves) |
| Signal | sleeve total-return level strictly above its 10-month moving average at the prior month-end |
| When a sleeve is below its average | that sleeve's half earns the bill |
| Rebalance | monthly, at the month-end close |
| Modeled costs | equity expense 0.10%/yr, bond expense 0.15%/yr, turnover 5 bps per side |

Read the rule out in words: at each month-end, for each of the two sleeves, compare its
total-return level to the average of its last ten month-end levels. If it is above, hold that sleeve
(half the book) for the coming month; if it is at or below, hold the bill for that half. Both above
is 50/50 equity and bond; both below is 100% bills.

## 3. Instrument map (backtest to live)

The backtest scores research indices; live execution needs liquid ETFs that track them faithfully.
The faithful single-fund matches, with the modeled expense the backtest already charged:

| Sleeve | Backtest series | Faithful live ETF | ETF expense | Note |
| --- | --- | --- | --- | --- |
| Equity | Kenneth French US market total return | VTI or ITOT (total US market) | ~0.03% | Cheaper than the modeled 0.10%, so conservative |
| Bond | US Treasury 10-year par-yield total return | IEF (7-10yr Treasury) | ~0.15% | The faithful duration match |
| Cash | 1-month Treasury bill | SGOV or BIL | ~0.09% | The out-of-sleeve parking place |

Duration matters: the backtest bond sleeve is the 10-year constant maturity, so **IEF (7-10yr) is the
faithful proxy**. TLT (20+yr) is a materially longer-duration bet than what passed the gate and is a
deviation, not a substitute. If you prefer TLT, that is a different strategy that has not been
gated.

## 4. The monthly operating procedure

Once a month, at or just after the last trading day of the month. Total effort is a few minutes.

1. Pull the month-end total-return (dividend-adjusted) level of the equity proxy (VTI) and the bond
   proxy (IEF). Use the same adjusted-close series each month for consistency.
2. Run the live-signal script (section 10), which reuses the frozen `signal_from_monthly_levels` rule from the
   repo, to compute each sleeve's 10-month average and the target allocation. Never hand-eyeball the
   average; let the frozen code decide so live matches the backtest by construction.
3. Read the target: equity 50% if VTI is above its average else that 50% to SGOV; bond 50% if IEF is
   above its average else that 50% to SGOV.
4. Rebalance to the target by trading only the difference from the current holding. Avoid wash-sale
   complications by tracking lots if in a taxable account (prefer not to; see section 5).
5. Log the date, the two levels, the two averages, the target, and the actual fills to a running
   journal (CSV). This is the live audit trail and the input to the kill criterion.

Whipsaw note: a sleeve hovering near its average will flip in and out across months, paying turnover
each time. That cost is in the model (5 bps per side) and is expected; do not override the signal to
avoid a flip.

## 5. Account and sizing

- **Use a tax-advantaged account (a Roth IRA is ideal).** Monthly long-or-cash rebalancing realizes
  short-term gains in a taxable account, and that tax drag is not in the backtest. A Roth or
  traditional IRA removes the drag entirely and makes live match the modeled net return. This single
  choice is the largest controllable gap between the backtest and reality.
- **Start small and scale only on evidence.** This is a risk-managed sleeve, not a lottery ticket,
  but it is regime-dependent and unproven live. Size it as a deliberate fraction of investable
  capital, not the whole account, until it has tracked the backtest envelope for several months.
- **Decide the bond sleeve explicitly.** Two honest, already-measured choices:
  - **(A) The faithful frozen rule:** deploy both sleeves (50/50) exactly as gated. This is the
    result that passed.
  - **(B) Equity-sleeve-only:** the equity sleeve standalone has a PSR of 0.998 and sidesteps the
    weak, rate-sensitive bond sleeve. This is a simpler, recently-stronger variant, but it is a
    single-sleeve trend (less diversified) and is a deliberate deviation from the two-sleeve rule.
  Default to (A) for fidelity. Choose (B) only as an explicit, documented decision, not a silent
  drop of the inconvenient sleeve.

## 6. Phased rollout

- **Phase 0 (build and reconcile, about a week).** Implement the live-signal script (section 10).
  Run it over the full committed history and confirm its monthly positions match the committed
  backtest artifact (`artifacts/xtrend_gate.json`) to the position. This is the verify-against-real-
  data gate: if the live script does not reproduce the backtest's own signals, it is wrong.
- **Phase 1 (paper trade, 3 to 6 months).** Each month-end, generate the signal and record the
  paper fills and the ETF prices. Confirm the ETFs (VTI, IEF, SGOV) track the research series within
  a small tolerance and that real spreads and the round-trip cost stay inside the modeled budget.
- **Phase 2 (go live small, tax-advantaged).** Fund the chosen fraction in the IRA, set the initial
  allocation from the current signal, and run the monthly procedure for real.
- **Phase 3 (monitor and scale).** Track live results against the backtest envelope and the kill
  criterion (section 7). Scale the allocation only after it has behaved as designed across at least
  one stress (a market pullback where the rule de-risks on schedule).

## 7. The pre-registered LIVE kill criterion (the kill-early rule, applied to deployment)

Write the kill down before going live so the decision is not made emotionally in a drawdown. Stop and
reassess if any of these fire:

- **Structural drawdown breach:** the live peak-to-trough drawdown exceeds 18% (the backtest max is
  11.2%; 18% is a wide margin that signals the risk control is not working as modeled).
- **Signal divergence:** the live-signal script and the executed positions disagree in any month
  (an execution or data-plumbing bug), or the live script stops reproducing the backtest on history
  after a data update.
- **Cost blowout:** the realized round-trip cost in any rebalance exceeds roughly double the modeled
  5 bps per side, repeatedly (a liquidity or spread problem in the chosen funds).
- **Thesis break, not bull-market lag:** the rule fails to de-risk during a sustained equity
  downtrend (the one thing it exists to do). Note clearly what is NOT a kill: underperforming
  buy-and-hold in a bull market is the design, and whipsaw turnover in a choppy market is expected.

A kill means halt new rebalances, move to bills, and re-open the research, not panic-sell at a low.

## 8. Monitoring and logging

- Keep a monthly journal CSV: date, VTI level, VTI 10-month average, IEF level, IEF 10-month average,
  target weights, executed weights, fills, fees paid.
- Once a quarter, compute the live realized return, volatility, and drawdown and compare to the
  backtest envelope and to a 60/40 benchmark, for context only (beating or lagging 60/40 in a given
  quarter is not a signal; the multi-year drawdown behavior is).
- Keep the repo as the source of truth for the rule. Any change to the rule is a new ADR and a
  re-run of the gate, never an ad-hoc tweak in the live script.

## 9. Risks and honest caveats

- **Not advice; unproven live.** A passing backtest is necessary, not sufficient. Live carries
  execution, data, tax, and behavioral risks the backtest cannot see.
- **Regime dependence is real and current.** The 2022-onward slice is below the bar and the bond
  sleeve is the weak part. The strategy may be entering live in one of its harder regimes.
- **Tracking gap.** ETFs are not the research indices; small, persistent tracking differences exist
  and are validated, not assumed away, in Phase 1.
- **Behavioral risk is the dominant failure mode.** The hardest part of trend-following is holding
  the rule through whipsaws and bull-market lag. Most retail trend-followers quit at the worst time.
  The pre-committed rule and the written kill criterion exist to remove discretion.
- **Capacity is not a concern at retail size; behavior and taxes are.** Focus the energy there.

## 10. The Phase 0 paper-trading system (BUILT)

This is implemented in `src/riskpremia/live/` and the `scripts/` entry points. It reuses the frozen
rule so live cannot drift from the backtest, and it runs entirely offline with no broker and no
money.

- `signal.py`: `target_from_levels` takes each sleeve's month-end levels and returns the target
  weights. The active/inactive decision comes straight from `signal_from_monthly_levels`, the exact
  function the gated backtest uses (extracted as the single source of truth), so the live decision is
  the backtest decision.
- `paper.py`: a self-contained paper account that marks at month-end prices and rebalances with the
  backtest's cost mechanics (turnover charged per side on the risk-sleeve weight change, the cash leg
  the residual). The cash sleeve is held as the bill ETF, so idle capital earns the bill as the
  backtest assumes.
- `levels.py`, `journal.py`: the month-end levels file and the appended monthly journal (the
  out-of-sample track record).
- The reconciliation test (`tests/unit/test_live_signal.py`) feeds the backtest's own month-end
  levels into the live path and asserts the active flag matches the backtest at every month, and that
  the match is non-vacuous (both states occur). A regression in the live path fails CI.

### Running it (Windows, the project venv)

```powershell
$env:PYTHONIOENCODING="utf-8"
$py = "C:\Users\SamJD\.venvs\riskpremia\Scripts\python.exe"
# One-time: build the committed seed of VTI/IEF/SGOV month-end adjusted closes (network)
& $py -m scripts.build_live_levels
# See this month's signal (read-only, no state)
& $py -m scripts.live_signal
# Each month: append the newest completed month, then paper-rebalance
& $py -m scripts.build_live_levels append
& $py -m scripts.paper_rebalance
```

The runtime files (`live_state/levels.csv`, `account.json`, `journal.csv`) are gitignored; the
committed seed under `tests/data/` is the reproducible starting point. The account starts fresh now,
so the seed history only feeds the ten-month signal window. This is forward paper trading, not a
replay of the backtest.

Two honest scope notes so the paper record is not oversold as bar-identical to the backtest. First,
the backtest forms the signal at month-end and rebalances on the first trading day of the next month,
while the paper engine marks and trades at the month-end close itself: the same signal with no
look-ahead (it trades at a close it has already seen), but a roughly one-day execution offset, so the
paper path is the more realistic of the two rather than identical to it. Second, the reconciliation
proves the live RULE reproduces the gated rule exactly; it does not prove the Yahoo adjusted closes
reproduce the research index, which is the tracking gap Phase 1 validates. The "live cannot drift"
guarantee is scoped to the rule, not the data source.

## 11. Automating the loop

The whole monthly loop can run unattended, but the honest default for a once-a-month rebalance is
confirm-gated automation, not fully hands-off. The script does all the work and proposes the exact
orders; a human approves with one tap. The cadence is monthly and the action takes two minutes by
hand, so the asymmetric downside of an unsupervised bad trade (a stale or unsplit price feeding a
wrong order, an API outage, a code fat-finger) is not worth trading away for convenience. This is the
opposite of the Kalshi bot, which is high-frequency and must be automated; here automation is a
convenience, not a requirement.

### The architecture

A scheduled job runs the rebalance script on the last trading day of the month:

1. Windows Task Scheduler fires `scripts.live_rebalance` near the month-end close (the same
   Task Scheduler pattern the Kalshi bot already uses).
2. Fetch the month-end adjusted closes of the equity and bond proxies, ideally from the broker's own
   API so the signal prices and the execution prices are the same source. Append to the levels CSV.
3. Compute the signal with the frozen `riskpremia.xtrend.gate.signal_from_monthly_levels`. No new
   logic.
4. Pull current positions and cash from the broker API; compute target weights, target shares, and
   the order difference.
5. Guardrails before any order: price-freshness check, a signal-only-changed-if-the-level-crossed
   sanity check, an order-size cap, and an automatic kill-criterion check (a drawdown breach halts
   and alerts instead of trading).
6. Confirm gate: email or text the proposed orders and wait for a one-tap approval, OR, in full-auto
   mode, place the orders directly (marketable limit or market-on-close).
7. Place orders via the broker API, log the fills to the journal CSV, and send a run summary.

### Broker choice (the tax-advantaged-account constraint drives it)

To keep both the IRA tax advantage (section 5) and automation, the broker must support an IRA and a
trading API:

- **Interactive Brokers**: the most robust API, full IRA support, fractional shares, low cost. The
  default choice for this. Heavier API surface.
- **Charles Schwab**: an official trader API (from the TD Ameritrade acquisition) with IRA support.
- **Tradier**: a simple REST API, IRA support, commission-free.
- **Alpaca**: the cleanest API and the best paper-trading sandbox, so it is ideal for Phase 1, but
  its IRA support is limited; using it live would mean a taxable account, which reintroduces the tax
  drag section 5 warns about. Use it for paper, not for the live IRA.

### How automation maps to the rollout

- Phase 1 (paper): full-auto on Alpaca paper. Zero real-money risk, and it proves the entire loop
  end to end (schedule, data, signal, order computation, fills, logging, alerts).
- Phase 2 (live small): confirm-gated. The script computes and proposes; you approve each month.
- Phase 3 (optional): graduate to full-auto only after the guardrails, the auto-kill-switch, and the
  alerting have been exercised for several months and a real rebalance has fired correctly.

The reproducibility rule still holds: the automated executor reuses the frozen repo signal and is
gated by the same reconciliation test, so automation never becomes a second, drifting implementation
of the rule.

## 12. Next: a broker paper account, then live

When ready, the same `target_from_levels` output drives a broker adapter. Start with an Alpaca paper
account (free, no money) for broker-side fills, then graduate to a confirm-gated live executor in a
tax-advantaged account, as section 11 describes. The paper engine here is the zero-dependency first
step that needs none of that.
