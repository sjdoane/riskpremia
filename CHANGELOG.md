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

### Career-target fork resolved

- Asked the user (career target is the only input that could promote Track A).
  The user deferred to the agent's judgment ("make the decision"). Track B is
  LOCKED; framing default is broad / systematic / reproducibility-first; no
  WRDS/OptionMetrics chase. STATUS + memory updated.

### Data-layer milestone: planned + Plan-reviewed (rule 1)

- **Plan agent (senior quant-infra architect)** produced a file-by-file data-layer
  plan grounded in the live-verified vendor facts. Empirical groundwork confirmed:
  Binance Vision funding zips download + checksum-verify (schema
  `[calc_time, funding_interval_hours, last_funding_rate]`, 94 rows for 2020-01);
  OKX funding history does NOT page back past ~2021 (so it is live/recent only,
  not the long-history backbone); Hyperliquid funds HOURLY (not 8h) with a thin
  spot leg. Design captured in `docs/research/0001-data-layer-design.md`.
- **Plan-reviewer (senior quant/data-infra)** returned APPROVE-WITH-CHANGES after
  probing the live endpoints itself. Findings and resolutions (all accepted):
  - **C1 [Critical]:** the plan's OKX realized-gate premise was FACTUALLY WRONG
    (the `/funding-rate-history` head row is already settled, not future; the
    predicted rate is in the separate `/funding-rate` endpoint). Resolution: gate
    on `realizedRate is not None AND method == "current_period" AND window_end <
    now` (strict `<`); never read `/funding-rate`; exclude the predicted field
    from the record path.
  - **C2 [Critical]:** Binance funding is a clamped interest + premium composite;
    reporting it as "the premium" is a category error. Resolution: document it as
    the realized clamped cash flow, keep the `premium` component, add a
    clamp-incidence diagnostic.
  - **C3 [Critical]:** the basis must use the perp MARK price vs a matched,
    snapshotted, same-quote spot product; Hyperliquid basis set null (off-venue
    spot not yet reproducible).
  - **C4 [Critical]:** Binance Vision survivorship biases the premium up; v1
    headline universe is a pre-committed survivor set (BTCUSDT then ETHUSDT), NOT
    a multi-coin median; caveated in ADR 0002 + methodology.
  - **H5 [High]:** quantify the venue-basis confound (emit a Binance-vs-OKX
    funding delta on the matched grid; kill gate on OKX-realized, decay headline
    on Binance), plus determinism/test items (tz-aware dtype parity assertion,
    horizon gap-guard + length-parity assert, Decimal-vs-Float64 basis test,
    `extra="forbid"` only on the immutable CSV, committed regeneration script +
    byte-equality test, pinned spot-ETF regime constant, tolerance-banded
    modal-gap warning, realized-aware dedup).
  - **Scope [accepted]:** the reviewer's CUT TO SHIP FASTER (BTCUSDT Binance
    backbone + OKX-realized delta; defer Hyperliquid, retention probes,
    multi-coin, full pagination) roughly halves pre-cost-model LOC, honoring
    rule 6. PR split locked in the design doc (PR1 heart, PR2 Binance, PR3 OKX).

### Verification (against real behaviour, not just mocks)

- Crypto endpoints hit live from the machine (real OKX JSON + real geo-block
  responses confirm the network path and the findings). The Plan-reviewer
  independently re-probed OKX/Binance live and corrected the OKX gate premise.
- Vendored stack imported and executed in the venv: DSR canonical pin reproduced
  to 1e-3; CPCV path count + bootstrap determinism confirmed.
- Em-dash sweep clean on all new files (verified before commit).

### Deferred

- Career-target confirmation (user); US-tradeable venue choice (cost-model ADR);
  Binance Vision history depth + instrument survivorship (data-layer milestone);
  CI workflow (after the first real milestone).
