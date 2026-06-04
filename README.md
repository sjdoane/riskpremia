# Project RiskPremia

A rigorous, intellectually-honest quant research project on a risk premium with a
defensible economic edge, built to (a) plausibly make real money at solo/retail
scale and (b) be genuinely impressive to a quant recruiter via rigor and honesty,
not a hyped backtest. Sibling to `pit-backtest` (the equity backtester whose
honest momentum null is the brand); this extends that discipline to a market with
an edge.

Status: STARTED (2026-06-03). Scaffold up and the week-1 data-access spike is done.
**Lead track decided: Track B, crypto perpetual-futures funding carry (delta-neutral),
framed as a measurement study.** Track A (single-name earnings Variance Risk Premium) is
the demoted "I also examined this" contrast section. The decision, the unanimous council,
the verifier audit, and the pre-registered kill criterion are in
[`docs/decisions/0001-lead-track-selection.md`](docs/decisions/0001-lead-track-selection.md).
Current state and next steps live in [`STATUS.md`](STATUS.md).

## What to do first (returning session)

1. Read [`STATUS.md`](STATUS.md) (current state + what is deferred), then
   [`docs/decisions/0001-lead-track-selection.md`](docs/decisions/0001-lead-track-selection.md)
   (why Track B) and [`docs/STRATEGY-BRIEF.md`](docs/STRATEGY-BRIEF.md) (the stress-tested context).
2. Build order (rule 6): the data layer, then the cost model, then a random-entry NULL
   through that cost model, BEFORE any signal logic. The original full-authority brief is
   [`HANDOFF-PROMPT.md`](HANDOFF-PROMPT.md).
3. One question is open for Sam: the career target (it can promote Track A only if a pure
   vol-desk target AND a verified OptionMetrics entitlement are both confirmed).

## The most important rules (carried from the portfolio's operating rules; non-negotiable)

1. **Spawn review agents / a council for every meaningful chunk and every key
   decision** (Realist/Quant/Builder/Growth + a verifier for decisions; a post-impl
   reviewer for code). Address Critical + High findings before marking work done.
2. **Keep `STATUS.md`, `CHANGELOG.md`, and the project memory current** after every
   work block, and store all context so a fresh session can continue.
3. **No em-dashes anywhere** (code, docs, commits, chat). Hard ban. Use commas /
   colons / hyphens / restructure. Sweep with ripgrep before any PR.
4. **Kill-early.** Document the kill criterion UPFRONT (a net-of-cost Deflated
   Sharpe threshold out-of-sample). If it is hit, recommend killing plainly; an
   honest null is an acceptable, impressive deliverable.
5. **Windows-first.** PowerShell, absolute paths, no `&&` chaining, `$null` not
   `/dev/null`. A clean dedicated venv; never touch the off-limits live-bot venv.
6. **Verify against real data.** Tests on mocks/`:memory:`/fixtures are necessary
   but not sufficient. The backtest must be net of REALISTIC modeled costs; build
   the cost model FIRST and run a random-entry null through it before tuning.
7. **No secrets in chat.** API keys go in `.env` / env vars; if one is pasted,
   treat it as exposed and flag for rotation.
8. **Determinism + reproducibility:** pinned deps, point-in-time discipline,
   committed artifacts a reviewer can regenerate. Reuse the `pit-backtest`
   analytics/validation stack (PSR/DSR/CPCV/bootstrap/scorecard).

## Off-limits

The live Kalshi prediction-market bot is owned by a separate agent. Do NOT touch
it or build prediction-market strategies here; this is a separate market by design.
