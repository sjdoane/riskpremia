# Crypto Funding-Dispersion Measurement: Fork, Data Probe, and Method

Date: 2026-06-07.
Related decision: [ADR 0009](../decisions/0009-pivot-to-funding-dispersion-measurement.md).

## The fork

After the Study 6 qualified pass, a four-lens decision review and an adversarial cross-check
selected Study 7. The four lenses agreed on a crypto funding-dispersion measurement note: it is
a fast, low-risk, crypto-native measured positive that re-anchors the project after Study 6
moved into cross-asset macro, it reuses machinery the project already has, and it cannot fail a
deploy gate because it makes no deployment claim. The adversarial cross-check pushed for a
second deployable swing instead, on the argument that after a only-qualified pass the project
most needs a second clean deployable result. That push was weighed and not taken, because the
clean-data deployable candidates are empirically weak:

- A volatility-managed portfolio is contested out-of-sample by name (Cederburg, O'Doherty,
  Wang, and Yan 2020; Barroso and Detzel 2020 on costs), so it is a likely null on this
  project's deflated, net-of-cost gate.
- A cross-asset trend variant rhymes with Study 6 and inherits the same recent-regime weakness.
- A long-only defensive equity tilt rhymes with the failed CTREND; crypto cash-and-carry needs
  shorting.

Forcing a likely-null swing on the same asset pair would not advance the make-money goal more
than a clean, distinct measurement advances the portfolio. The dispersion is also a distinct
premium from the killed Study 1, which measured the funding LEVEL carry; this measures the
cross-sectional DISPERSION across coins. The deployable swing is recorded as the registered
next option.

## Lane 1: data probe (Gate 1, PASS)

The Binance Vision funding archive was probed directly via the keyless S3 path the loader uses.
Real results:

| Probe | Result |
| --- | --- |
| Universe | 816 perpetual funding series (733 USDT, 39 USDC, 41 BUSD), single S3 page |
| BTC history | 2020-01 to 2026-05 (77 monthly files); ETH the same span |
| Schema | `calc_time, funding_interval_hours, last_funding_rate` |
| Checksum | computed SHA256 equals the published per-file checksum byte-for-byte |
| Survivorship | delisted contracts persist with a frozen end-date (for example a BUSD leg stops exactly at the BUSD delisting), so the archive is survivorship-complete |

The measured object (per-coin perpetual funding across a wide universe, with depth) is free,
keyless, reproducible, checksummed, and survivorship-complete. The existing stdlib Binance
Vision funding loader, the funding-event clock, and the CTREND point-in-time universe spine are
directly reusable.

Three real holes, each with a data-driven fix that must be in the method, not discovered later:

1. **Funding-interval heterogeneity is live.** Some coins settle every 4 hours and others every
   8, and the raw per-event rate is therefore not comparable across coins. Each coin's rate is
   annualized via its `funding_interval_hours` before any cross-sectional comparison. Skipping
   this would manufacture spurious dispersion; it is the single biggest trap and it is fully
   solvable from the data.
2. **Survivorship and the universe definition.** A coin leaving the panel is a real delisting,
   not a gap. The universe is defined point-in-time (the CTREND top-N-by-dollar-volume screen)
   so the dispersion series is not an artifact of the coin count changing over time.
3. **Quote duplication.** The archive carries the same underlying under USDT, USDC, and BUSD
   quotes; these are de-duplicated to one perpetual per underlying (prefer USDT) before the
   cross-sectional spread is computed.

## Lane 2: method (refined by the design review)

- Universe and join: the point-in-time eligible SPOT set (CTREND `pit_eligible`) is mapped to
  the canonical asset key and joined to one perp funding series per coin (prefer the USDT-perp
  leg), with a per-week eligible-versus-funded coverage diagnostic. The spine ranks spot and the
  funding archive is perp, so the canonical join is the load-bearing seam.
- Per-event annualization via each event's own `funding_interval_hours`, single-sourced to the
  project's `CRYPTO_ANNUALIZATION_DAYS` (basis 365 times 24 equals 8760).
- A fixed common daily grid (00:00 UTC) built by a point-in-time backward carry-forward, so
  4-hour and 8-hour settlements do not manufacture a composition swing.
- Headline statistic: the equal-weight cross-sectional interquartile range (robust to small-cap
  tails), reported as a post-ETF level with a bootstrap confidence interval, the pre-versus-post
  difference, and a rolling-window decay slope. The raw and winsorized standard deviations are
  secondary diagnostics.
- The gross sort premium (quintile top-minus-bottom, equal-weight, funding-only, next-period
  realized, point-in-time) is a secondary, banner-attached, non-capturable measured object.
- Significance: the stationary-block bootstrap on the FULL daily dispersion series (no VRP-style
  striding; the dependence is funding-regime persistence, absorbed by the Politis-White block
  length) for the level, the regime difference, and the decay slope; and on the formed
  top-minus-bottom return series for the secondary sort premium. The seed and resample count are
  pinned.

## Design review findings and resolutions

An independent senior-quant design review of this pre-registration returned three Critical, four
High, and five Medium findings, all resolved in ADR 0009 before merge (the risk for a
measurement note is mis-measurement or oversell, not a false pass):

- Critical: the universe spine is spot-keyed while funding is perp-keyed (resolved with the
  explicit canonical join plus the coverage diagnostic); the headline was undefined (resolved by
  naming the equal-weight interquartile-range level plus the regime split and decay as the
  single headline and demoting the sort premium); the bootstrap was copied from the VRP without
  noting that the VRP strides out a window-overlap a dispersion series does not have (resolved by
  bootstrapping the full series, with the block length absorbing the persistence, and reporting a
  level and a signed difference rather than a vacuous clears-zero test).
- High: the 4-hour-versus-8-hour settlement grid manufactures spurious dispersion (resolved by
  the common-grid carry-forward); the standard deviation is tail-dominated (resolved by the
  equal-weight interquartile-range headline); the annualization constant must be single-sourced
  and applied per event, not per coin (resolved).
- Medium: the spot-ETF boundary is a comparability convention, not a cause; the decay estimator,
  the sort construction, and the perp-survivorship diagnostic are frozen; the framing is a
  descriptive measurement with the decay stated in the headline, not a "positive result."

## Lane 3: honesty guardrails

The dispersion looks like free money (the related literature reports a gross cross-sectional
crypto carry Sharpe above six over 2020 to 2025, entirely non-retail-capturable and already
decaying to negative by 2025). The note must therefore carry no tradeable-Sharpe headline and
no long-short return as the headline; an explicit non-deployability banner up front (US retail
cannot short a wide altcoin-perp cross-section, and the data venue is not US-tradeable); the
decay stated as part of the finding; and the interval-normalization shown so no reader mistakes
a units artifact for dispersion.

## Final review

The conclusion of the fork is build-as-a-measurement, with the deployable swing registered as
the next option:

- Build the funding-dispersion measurement, reusing the Binance Vision loader, the funding
  clock, and the point-in-time universe spine.
- Apply the three normalizations (interval-annualize, point-in-time universe, quote de-dup)
  before measuring the cross-sectional spread.
- Report significance with the block-deflated bootstrap, like Study 2.
- Keep the non-deployability banner prominent and quote no tradeable Sharpe; the deliverable is
  the measured object, not an edge.
