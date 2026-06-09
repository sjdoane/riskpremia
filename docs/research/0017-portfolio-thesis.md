# The Portfolio Thesis: Ten Studies, One Apparatus, One Qualified Pass

Date: 2026-06-08.
This is the capstone synthesis of the RiskPremia project. It concludes the make-money search and
states what the apparatus found. Each study has its own pre-registration (an ADR) and its own result
note; this document is the cross-study reading.

## The thesis in one paragraph

One apparatus, built once and frozen, was pointed at ten candidate risk premia spanning every major
family a retail quant could reach: funding carry, the variance risk premium, cross-sectional and
time-series trend, FX carry, a cross-asset defensive rule, funding dispersion, volatility-managed
equity, industry trend, and a quality tilt. The apparatus is a free, US-reachable, checksum-pinned
data layer; a vendored deflated-Sharpe, purged-CPCV, and stationary-bootstrap statistics stack; and
a cost-model-first kill gate with a pre-registered criterion. **Across the ten studies, exactly one
candidate cleared the deflated, net-of-cost, retail-honest gate, and it is a classic cross-asset
defensive rule validated with full rigor, not a novel edge.** Five candidates were killed, three more
were honest nulls, one was a positive measurement with no tradeable edge, and one was a real but
too-thin premium that the gate caught as a near-miss before any capital was committed. The
contribution is not a backtest. It is a reproducible, intellectually-honest apparatus that rejects
nine candidates, accepts one on the merits, and catches its own near-miss, with every number
regenerable from committed data.

## The scoreboard

| # | Premium / strategy | Verdict | The kill number (vs the 0.95 bar) | Window | Trail |
| --- | --- | --- | --- | --- | --- |
| 1 | Perpetual funding carry | Killed | net-of-cost Deflated Sharpe approximately 0 | 2020-2024 | ADR 0003 |
| 2 | BTC variance risk premium | Measurement positive, tradeable non-viable | VRP +0.087/yr (real); short-straddle Deflated Sharpe 0.30 | 2022-2025 | ADR 0004 |
| 3 | CTREND crypto cross-sectional trend | Killed | retail top-quintile fails on cost; long-short CPCV-min DSR below bar | 2022-onward | ADR 0005 |
| 4 | BTC/ETH slow trend with vol cap | Killed | CPCV worst-fold conditional PSR(0) 0.144 | weekly | ADR 0006 |
| 5 | CME Micro G6 FX carry | Feasibility kill | integer-contract stress can fail account survival; no robust free settlement path | not run | ADR 0007 |
| 6 | **Cross-asset defensive trend** | **Qualified pass (the one deployable result)** | **full-sample PSR(0) 0.9996, monthly 0.9970, Deflated Sharpe 0.998 at 32 trials** | 1990-2026 | ADR 0008 |
| 7 | Crypto funding dispersion | Measured, non-deployable | cross-sectional IQR 0.106/yr (decaying -0.013/yr); gross sort +0.550/yr not capturable at retail | 2022-2026 | ADR 0009, research 0010 |
| 8 | Volatility-managed market | Non-viable (Cederburg replication) | difference PSR(0) 0.457; gross +1.78%/yr dies on the -2.14%/yr leverage cap | 1990-2026 | ADR 0010, research 0012 |
| 9 | Industry trend net-of-market | Non-viable (timing null) | pure-timing PSR(0) 0.229; timing -1.54%/yr | 1927-2026 | ADR 0011, research 0014 |
| 10 | Quality (profitability) tilt | Non-viable (real but too thin) | difference PSR(0) 0.932 net of cost (gross 0.951); FF5 alpha +0.65%/yr, t 2.76; DSR 0.35 at 16 trials | 1963-2026 | ADR 0012, research 0016 |

Secondaries: Study 2 has a positive measurement layer (implied variance exceeds realized in BTC, a
real risk premium) separate from the non-viable tradeable layer; Study 8 has a factor-asymmetry
secondary that is a uniform null across all five Fama-French factors, where the lone momentum
standout is an in-sample look-ahead that collapses on a real-time expanding-window normalization.

## The one deployable result, told honestly

Study 6, a cross-asset defensive trend, is the only candidate that cleared the gate, and the honest
description matters more than the headline. It is a frozen, no-fit, monthly long-or-cash trend rule
across the US equity market and long-term Treasuries, into Treasury bills, on openly-redistributable
public-domain data (Kenneth French factors and the US Treasury par yield curve), scored in excess of
the bill. Its full-sample conditional PSR(0) is 0.9996, its monthly non-overlapping PSR(0) is 0.9970,
its Deflated Sharpe is 0.998 even at 32 inherited trials, its maximum drawdown is 11.2%, its cost
share is 2.8%, and its CAGR is 7.1%.

The caveats are the point:

- **It is a classic rule, not a novel edge.** Cross-asset trend (dual-momentum-like) is a long-known
  defensive overlay. The achievement is validating it with full deflated, cost-realistic, purged
  rigor, not discovering it. No alpha is claimed that the literature did not already describe.
- **It is regime-dependent.** The CPCV worst fold is 0.72 and the 2022-onward recency slice is 0.40,
  both below the bar. The 2022 rate spike hurt the long-Treasury sleeve (standalone 0.846); the
  equity sleeve (standalone 0.998) carries the result and survives the recent regime.
- **It clears the bar in excess of the bill, which is what it is: risk management.** Studies 8 and 9
  establish, on the same gate, that defensive timing reduces risk but does not beat buy-and-hold the
  market at retail. Study 6 is consistent with that: it is a crash-insured long-equity-and-bond book
  that clears the deflated gate over the bill and is regime-dependent, not a free lunch over the
  market. Deployed, it is a risk-managed allocation, sized accordingly.

## What the apparatus learned (the cross-study lessons)

The value of running ten studies through one frozen gate is the methodology that compounds across
them. Five lessons recur:

1. **The kill is the difference over the right benchmark, never net of the bill.** A long-equity book
   crushes the bill, so its net-of-bill PSR is spectacular by construction: 0.9953 (Study 10), 0.9998
   (Study 9), and the standalone managed-market Sharpe in Study 8. That number is the equity premium,
   not the claimed skill. The honest kill is always the difference over the benchmark that isolates
   the claim, the managed-minus-unmanaged difference (Study 8), the strategy minus its own
   always-invested self (Study 9), the high-profitability-minus-market difference (Study 10). A design
   review caught this same equity-premium trap in three separate studies before any code was written.

2. **Deployable cost realism is where most edges die, and the gross alpha is often real.** Study 8 has
   a genuine +1.78%/yr gross volatility-timing alpha that the 2.0x retail leverage cap turns into a
   loss (the cap removes -2.14%/yr, the dominant drag). Study 10 has a genuine +0.65%/yr Fama-French
   alpha that the differential expense of a quality ETF over a market ETF takes under the bar.
   Studies 1 and 3 die on round-trip retail cost. The honest finding is rarely "there was nothing
   there"; it is "the real thing did not survive the realistic implementation."

3. **Multiple-testing deflation is decisive for mined factors.** A single-trial PSR is not a pass.
   Study 10's gross PSR is 0.951, a near-miss; deflating for the heavily-searched quality factor
   collapses the Deflated Sharpe to 0.35 at 16 trials. The deflation is precisely what separates a
   marketable near-miss from a deployable result, and it is a hard gate condition, not a footnote.

4. **Defensive timing is risk management, not a market-beater.** Three studies triangulate it on the
   same gate: volatility-managed timing (Study 8), price-trend industry timing (Study 9), and even the
   qualified Study 6 is crash insurance that clears the bar over the bill while remaining
   regime-dependent. The trend rule in Study 9 gives up -1.54%/yr of return to reduce volatility. The
   consistent verdict across the defensive family is that timing reduces risk and does not beat
   buy-and-hold the market at retail net of cost.

5. **The apparatus catches its own near-misses before real money.** Study 10 is the proof. Its gross
   PSR (0.951) looked like a pass, the operator intended to deploy live on a pass, and a sloppy gate
   would have shipped it. The pre-registered honest gate, with the differential cost and the deflation
   as hard conditions and a Fama-French alpha guardrail against deploying a mislabeled beta tilt,
   produced the correct non-viable verdict before any capital was at risk. A gate that only ever says
   "no" is not credible; a gate that rejects nine, accepts one on the merits, and catches a tenth
   near-miss is.

## The apparatus

Every study shares the same machinery, which is the actual deliverable:

- **A free, US-reachable, checksum-pinned data layer.** Public-domain Kenneth French factors and US
  Treasury curves, and clean exchange archives, each committed as a SHA256-stamped fixture so every
  result regenerates offline from the exact bytes that produced it.
- **A vendored statistics stack.** The deflated Sharpe ratio, purged and combinatorial cross-validation,
  the Politis-White automatic block length, and a stationary bootstrap, copied and attributed from the
  sibling pit-backtest and pinned so the numbers are bit-reproducible.
- **A cost-model-first kill gate.** The cost model is built before the verdict, the kill statistic is
  the difference over the honest benchmark, the criterion (a deflated conditional PSR clearing 0.95) is
  pre-registered in an ADR, and the kill-early rule ends a study at its design phase when the
  feasibility fails (Study 5).
- **A two-stage adversarial review on every build.** A senior-quant design review before code (which
  in Studies 8, 9, and 10 computed the result on live data and amended the gate before implementation)
  and an adversarial post-implementation review that independently re-derives the numbers. The reviews
  are recorded in the CHANGELOG with their findings and resolutions.
- **Pre-registration and reproducibility throughout.** Each pivot is an ADR written before the build;
  each result is a research note; each artifact is committed and reproduced to the digit by an offline
  test.

## Conclusion: the search is concluded, and an honest null is the success

The make-money search is concluded. Ten candidate premia across every major retail-reachable family
were tested on one frozen, honest gate, and exactly one cleared it, a classic cross-asset defensive
rule validated with full rigor and deployed as the risk-managed allocation it is, not as a novel
edge. The other nine produced five kills, three nulls, and a positive-but-non-tradeable measurement,
and the apparatus caught its single near-miss before real money.

This is the same headline as the sibling pit-backtest, whose contribution was a reproducible honest
momentum null: the value is cost realism, confound controls, a pre-registered kill criterion, and
reproducibility, never a hyped backtest. An honest null is a success. A blown-up account or an
oversold backtest is the failure this project was built to avoid, and it avoided it ten times.
