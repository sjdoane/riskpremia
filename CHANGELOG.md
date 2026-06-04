# CHANGELOG

What shipped, plus every review finding and its resolution (rule 2). Newest
first. This is the audit trail; STATUS.md is the current-state snapshot.

## 2026-06-03, session 1: scaffold + week-1 data-access spike

### Shipped

- **Project scaffold.** Clean dedicated venv `C:\Users\SamJD\.venvs\riskpremia`
  (Python 3.12.13). Pinned `pyproject.toml` (polars 1.41.1, numpy 1.26.4,
  pydantic 2.9.2, attrs 24.2.0; dataops extra httpx 0.27.2; dev pytest 8.3.3 /
  mypy 1.13.0 / ruff 0.7.4 / pytest-cov 5.0.0 / pytest-env 1.1.5), mypy --strict
  config, ruff config, pytest config (PYTHONHASHSEED=0, warnings-as-errors).
  `.gitignore`, MIT `LICENSE`, `data/snapshots/manifest.toml` stub. Installed
  versions verified to match the pins exactly.
- **Vendored analytics/validation stack** from pit-backtest (commit `edad904`),
  each file carrying a provenance header: `analytics/sharpe.py`,
  `analytics/bootstrap.py`, `validation/cv.py`, `validation/trial_registry.py`.
  Vendored (not a path dependency) so a reviewer regenerates every number from
  THIS repo alone. `tests/unit/test_vendored_stack.py` pins the canonical
  numerical results (8 tests, all green; Bailey-LdP 2014 DSR = 0.7657 vs the
  0.766 pin; CPCV(6,2) = 5 paths; bootstrap seed-determinism).
- **Week-1 data-access spike** run end-to-end. WRDS: zero setup on the machine,
  entitlement not autonomously confirmable, non-redistributable even if entitled.
  Crypto: OKX + Hyperliquid live and US-reachable; Binance Vision S3 dumps
  (checksummed, from 2020-01) reproducible and US-reachable; live Binance/Bybit
  APIs geo-blocked from the US IP.
- **ADR 0001 (lead-track selection):** Track B (crypto funding carry) chosen as
  lead, with the pre-registered kill criterion declared upfront.

### Review findings and resolutions

The lead-track fork ran the rule-1 process: a 4-member council + adversarial
verifier.

- **Council (Realist / Quant / Builder / Growth): unanimous Track B, HIGH
  confidence, identical flip condition** (confirm BOTH WRDS entitlement AND a
  pure vol-desk target). Recorded in ADR 0001. No dissent to resolve.
- **Verifier C1 [Critical, accepted]:** the cost model, capacity curve, and kill
  gate must be parameterised to a genuinely US-TRADEABLE venue, not the Binance
  data venue, or the kill gate runs against costs that cannot be incurred.
  Resolution: locked decision 3 in ADR 0001; the cost-model milestone picks a
  US-tradeable venue with a real fee schedule.
- **Verifier H1 [High, accepted]:** restructure the user escalation so career
  target is the PRIMARY question, WRDS conditional. Resolution: the user-facing
  question leads with career target; WRDS is the conditional follow-up.
- **Verifier H2 [High, accepted]:** portfolio-redundancy risk (a second
  reproducible null must show range, not repeat the momentum null). Resolution:
  positioning in ADR 0001 decision 8 + the additivity argument (different market,
  different premium, retail-tradeable, risk-engineering contribution).
- **Verifier M1 [Medium, accepted]:** add crypto landmines to the risk register
  (US venue access, both-legs financing + capital tie-up, exchange-solvency fat
  tail, coin/venue survivorship). Resolution: ADR 0001 locked decision 6.
- **Verifier note [accepted]:** the 4-0 unanimity is partly over-determined (all
  lenses key off the non-redistributable-data fact), so confidence is discounted
  from "4-0" to "strong but single-fact-dominated." The career-target escalation
  is the honest hedge.

### Verification (against real behaviour, not just mocks)

- Crypto endpoints hit live from the machine (real OKX JSON + real geo-block
  responses confirm the network path and the findings).
- Vendored stack imported and executed in the venv: DSR canonical pin reproduced
  to 1e-3; CPCV path count + bootstrap determinism confirmed.
- Em-dash sweep clean on all new files (verified before commit).

### Deferred

- Career-target confirmation (user); US-tradeable venue choice (cost-model ADR);
  Binance Vision history depth + instrument survivorship (data-layer milestone);
  CI workflow (after the first real milestone).
