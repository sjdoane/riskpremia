# Project RiskPremia: strategy brief and stress-tested context

This is the stored context for a new rigorous quant project. It was produced by a
a structured multi-perspective direction review and adversarial stress-test, all run before any code. Read this first. The project's spiritual parent is `pit-backtest` (a
portfolio-grade event-driven equity backtester with PIT discipline, CPCV,
Deflated Sharpe, and Almgren cost realism) whose honest worked study showed
vanilla momentum does NOT beat passive after deflation and costs. That honesty is
the brand; this project extends it to a market with a defensible edge.

## The honest premise (do not relitigate)

A solo retail quant has exactly three structural advantages: tiny capacity (can
fish pools too small for a fund), no career/redemption risk (can hold lumpy
positions), and access to markets institutions avoid. Every viable edge must
monetize at least one. Solo EOD large-cap US-equity factor research has ~zero
expected edge after costs (maximally arbitraged); it is excluded. Recruiter-impressive
means rigor + intellectual honesty + a defensible economic edge thesis, NOT a big
backtest number. An honest negative or modest result, rigorously produced, is an
acceptable and impressive deliverable; a blown-up account is not.

## Constraint: the live Kalshi prediction-market bot is OFF-LIMITS

The research strongly favored prediction markets (Whelan et al.: Kalshi takers
lose ~32%, makers ~10%), but that is the domain of a separate, off-limits live
Kalshi system. This is a SEPARATE project in a different market, both to respect
that boundary and because a new market is a broader, more additive skill
demonstration. Prediction-market strategies are therefore out of scope here.

## The two theorized tracks (a week-1 data spike decides the lead)

Both are RISK PREMIA (compensation for bearing an un-hedgeable / crash-correlated
risk), both reuse the `pit-backtest` analytics + validation stack, both apply the
same rigor and rules. The first task is a data-access GO/NO-GO that picks the lead.

### Track A: Earnings Variance Risk Premium, framed as a MEASUREMENT STUDY

Lead this if a week-1 spike confirms USC WRDS / OptionMetrics access AND the
target is a pure options/vol desk (Jane Street, SIG, Optiver, Citadel Securities).

- **The question (not "harvest alpha"):** does the residual single-name
  earnings variance risk premium survive realistic options bid-ask, borrow, and
  honest multiple-testing deflation in 2024-2026? The honest-null is the expected
  and acceptable headline.
- **Economic frame:** the variance risk premium compensates for bearing the
  un-hedgeable earnings JUMP (Garleanu-Pedersen-Poteshman demand-based option
  pricing; Bollerslev-Tauchen-Zhou for the aggregate premium). You are paid the
  premium AND you own the left tail; the premium is the price of insurance on a
  discontinuous gap.
- **Novelty (execution/statistical, NOT economic):** the components are all
  published (the ~-8%/event straddle; the concave-IV-curve event-risk paper,
  Review of Finance 2025; Cao-Han cross-sectional RV-vs-IV / idiosyncratic-vol;
  BTZ regime; GPP demand pricing). The contribution is a correctly-deflated,
  cost-realistic, borrow-controlled JOINT test of whether conditioning the
  single-name event trade on the aggregate regime adds anything after the
  cross-sectional signal and after costs, plus the apparatus to answer it without
  self-deception.

### Track B: Crypto perpetual-futures funding carry (delta-neutral)

Lead this if WRDS access is NOT confirmed, OR the priority is reproducibility +
real money at solo scale + a faster first result, OR the target is a
systematic / relative-value / crypto / multi-strat seat.

- **The trade:** long spot, short the perpetual future (or the cross-exchange
  funding spread), delta-neutral, collecting the funding leveraged longs pay.
- **Economic frame (BIS Working Paper 1087, "Crypto carry"):** trend-chasing,
  limited-attention retail seek leveraged upside and pay positive funding; arbitrage
  capital is scarce because there is no cross-margin between spot and perp on
  regulated venues (you fund twice) and you bear forced-liquidation and exchange
  -solvency risk. It is a leverage-demand + crash-risk premium, not a free lunch.
- **The honest novelty is the RISK treatment, not the trade** (vanilla carry is
  content-farmed and reads as hype): regime-condition the carry (stand aside when
  funding is thin or tail-elevated), engineer the counterparty/liquidation tail
  (FTX is the cautionary tale), and quantify the post-spot-ETF DECAY honestly
  (the basis fell from ~25% in early 2024 to under ~5%; show the decay curve and
  the negative-funding-regime drawdowns).

## The stress-test verdict (load-bearing; bake these in)

The adversarial pass returned KILL-the-naive-version and PROCEED-only-as-rigorous-study.
The non-negotiable modifications:

1. **Reframe as measurement, not harvest.** The headline question is "does it
   survive costs / borrow / deflation," and the honest-null is acceptable.
2. **Cost-model FIRST.** Build the per-instrument modeled bid-ask (half-to-full
   spread on entry AND exit, all legs) and run a NULL strategy (random entry, same
   structure) through it BEFORE building any selection logic. If the signal is not
   clearly better than the null after costs, there is no edge. This inverts the
   usual build order on purpose.
3. **The single most likely loss is the SPREAD, not the tail.** For options, the
   round-trip bid-ask on multiple single-name legs is close to the entire premium.
4. **Borrow / skew confound (Track A).** Single-name put-richness is contaminated
   by borrow fees; the "retail-demand / low-institutional-ownership" proxy
   correlates with hard-to-borrow, so the apparent premium may be a borrow /
   recall-risk trade in disguise. Control for it: screen borrow fee / utilization,
   measure richness from synthetic-forward financing (not raw mid), and report the
   edge conditional on borrow tercile. Orthogonalize the demand proxy against
   idiosyncratic vol and size (Cao-Han already published that effect).
5. **GPP single-stock rationale is wrong-signed.** GPP's net-long-end-user result
   is for INDEX options; single-name flow is mixed-to-opposite (covered-call
   writing). Drop the structural-demand story for single names or replace it with a
   signed, costed, out-of-sample demand-imbalance measure; do not ship the index
   result mislabeled onto single names.
6. **Demote the BTZ regime gate to a risk-OFF circuit breaker only.** It is a weak
   quarterly aggregate-return predictor (t ~2.3, R^2 ~4%); using it to LEAN IN on
   idiosyncratic single-name events is a category error and curve-fit risk. Use it
   only to STAND ASIDE when tail risk is elevated.
7. **Defined-risk wings are a survival/testability choice, not alpha.** They buy
   back the most overpriced OTM tail, reducing premium captured. Report BOTH the
   naked-equivalent EV and the defined-risk EV so the give-up is visible. Never
   trade naked single-name short vol; treat XIV/SVXY Feb-2018 as the worst case.
8. **Multiple testing is the killer.** Pre-register the full knob list (IV-richness
   threshold, demand proxy, regime gate, structure, wing width, entry timing, exit
   rule), freeze it, log every trial, apply Deflated Sharpe + Harvey-Liu BHY FDR.
   If DSR clears, suspect an undercounted trial ledger before believing the edge.
9. **Tax-honest P&L:** single-name equity options are short-term ordinary income
   (no 1256 60/40); model net-of-tax. Crypto likewise short-term.
10. **Counterparty/operational risk register (Track B):** venue solvency, withdrawal
    halts, liquidation buffers, depeg, funding sign-flip. Name them; do not ignore.

## Validation methodology (beyond PIT / CPCV / DSR, which you already have)

- **Trial ledger as a first-class committed artifact**: every configuration ever
  tested, so the DSR trial count is honest; BHY false-discovery-rate control across
  the hypothesis set.
- **Event-time-PURGED CPCV**: split folds on event/announcement dates (not calendar
  index) with embargo, because events cluster and leak across correlated names.
- **Capacity curve**: net edge vs position size including MEASURED impact (order-book
  walk for options; slippage + funding-move-on-entry for crypto). The size at which
  net edge crosses zero IS the honest headline number.
- **Break-even cost**: the per-trade cost at which the edge dies; show realized cost
  is comfortably below it.
- **Regime decomposition + forward out-of-sample**: decompose PnL by regime; where
  possible, forward paper-trade with logged realized-vs-predicted (the strongest
  credibility signal, and the candidate already does CLV-style forward gates on
  Kalshi).
- **Kill criterion, declared UPFRONT** (kill-early rule): e.g. "kill if the
  net-of-modeled-cost Deflated Sharpe < [threshold] out-of-sample under event-time
  CPCV on a held-out period, on a frozen trial count." Recommend killing if hit; do
  not soft-pedal.

## Data + feasibility (the week-1 spike)

- **Track A options data:** free deep-history with clean earnings alignment does
  NOT exist. Best: OptionMetrics IvyDB via USC WRDS (~$0 if entitled; CONFIRM in
  week 1, including summer-access + redistribution limits, which mean raw data
  cannot be reshipped to a public repo, so publish only derived/aggregated
  artifacts). Commercial fallback: ORATS one-time full history (~low-4-figures;
  ships earnings moves natively; $100 trial to validate coverage first). Polygon /
  DoltHub are prototype-only (~3-5yr, too shallow for a quarterly event study).
  NOTE: the `Massive Market Data` MCP on this machine is NOT entitled to options
  (403); do not rely on it for option chains.
- **Track B crypto data:** free + unconditional + fully reviewer-reproducible.
  Binance `GET /fapi/v1/fundingRate` + spot/perp klines (perps from ~2019-09),
  Bybit / OKX / Hyperliquid funding-history endpoints. No key needed for market data.
- **Engine reuse:** the `pit-backtest` analytics/validation stack
  (`analytics/sharpe.py` PSR/DSR/MinTRL, `validation/cv.py` CPCV, `analytics/bootstrap.py`,
  `analytics/scorecard.py`, the trial registry, the determinism invariant) is
  asset-agnostic and REUSABLE for either track. The `BarLoop` / Almgren cost model
  are equity-daily-bar-specific and must be REBUILT (a small two-leg 8h-clock
  harness for Track B; an options pricer + multi-leg payoff + per-name option-spread
  model + event-time CV glue for Track A). Effort: Track B ~600-1,000 LOC / ~2-3
  weeks; Track A ~2,000-3,000 LOC / ~6-8 weeks.

## Decision rule for the lead track (run the week-1 spike, then choose)

- Confirm USC WRDS / OptionMetrics in week 1 (pull one name's surface + earnings
  history end-to-end). If it works AND a vol-desk signal is the goal -> Track A.
- If WRDS is unavailable, OR reproducibility + real-money + speed is the priority,
  OR the target is systematic/RV/crypto -> Track B. Do NOT buy ORATS speculatively.
- Whichever is the lead, the other becomes a one-section "I also examined this;
  here is the friction-adjusted result and why I deprioritized it," which itself
  demonstrates kill-early judgment.

## Selected sources (for the new window to follow up)

- Dew-Becker & Giglio (2025), "The Decline of the Variance Risk Premium," Chicago Fed WP 2025-17.
- Garleanu, Pedersen, Poteshman (2009), "Demand-Based Option Pricing," RFS (NBER w11843).
- Bollerslev, Tauchen, Zhou (2009), "Expected Stock Returns and Variance Risk Premia," RFS.
- "Pricing event risk: evidence from concave implied volatility curves," Review of Finance (2025).
- Cao & Han, "Cross section of option returns and idiosyncratic stock volatility," JFE.
- Schmeling, Schrimpf, Todorov, "Crypto carry," BIS Working Paper 1087.
- Harvey & Liu, "Backtesting"; Bailey & Lopez de Prado, "The Deflated Sharpe Ratio."
- Whelan et al. (2025), "Makers and Takers: The Economics of the Kalshi Prediction Market," UCD WP2025_19 (context only; prediction markets are out of scope).
