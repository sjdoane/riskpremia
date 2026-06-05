# 0002: the CTREND universe data layer (Study 3, PR1)

The reviewed design of the point-in-time, delisting-complete multi-coin universe data
layer that the CTREND signal (PR2) and the backtest + kill gate (PR3) consume. Written
after a design plan, an independent senior-quant design review, and a verification of the
source paper's exact methodology (the review correctly insisted the data granularity be
settled before any panel is committed, because it is expensive to redo).

## The paper's method (verified against the published text)

Fieberg, Liedtke, Poddig, Walker, Zaremba, "A Trend Factor for the Cross-Section of
Cryptocurrency Returns" (JFQA 2025; SSRN 4601972). The load-bearing facts for the data
layer, read from the paper:

- Data: daily open/high/low/close, volume, and MARKET CAP from CoinMarketCap, 2015-2022,
  3,244 unique coins. A valid observation requires non-missing close, volume, and market
  cap. The universe filter is a MARKET-CAP floor (>= USD 1 million), with the main
  portfolios VALUE-WEIGHTED by market cap. Returns truncated at the 0.5/99.5 percentiles.
- Signal: 28 technical signals computed on DAILY data across four families: momentum
  oscillators (14-day RSI, stochastic K/D over 14 days, stochRSI, CCI), price simple
  moving averages (7 SMAs at 3, 5, 10, 20, 50, 100, 200 days, scaled by the current
  price), volume indicators, and volatility indicators. The 28 daily signals are
  aggregated cross-sectionally by the CS-C-ENet of Han, He, Rapach, Zhou (2024): a
  per-signal cross-sectional univariate (Fama-MacBeth, smoothed over the window) forecast,
  then a pooled elastic-net (L1/L2 mix 0.5, lambda by corrected AIC) that selects and
  averages the positive-weight univariate forecasts. Signals are cross-sectionally ranked
  into [-0.5, 0.5] before regression; regressions are value-weighted least squares.
- Fit + rebalance: a fixed ROLLING 52-week window estimates the model, predicting the
  NEXT week; at the start of each week coins are ranked on the aggregate CTREND signal
  into five VALUE-WEIGHTED quintile portfolios, rebalanced WEEKLY. The long-short factor
  buys the top quintile and sells the bottom.
- The cost-survival claim PR3 tests lives in the paper's LIQUID-subset robustness (its
  Table 8): the factor is re-run within the 100 largest and the 100 most-liquid coins
  (liquidity = the Amihud (2002) illiquidity ratio), and the transaction-cost section
  reports the break-even cost band that motivates this study.

The decisive consequence for PR1: the signal is computed on DAILY bars even though the
rebalance is WEEKLY. A weekly-only panel cannot reconstruct a 14-day RSI or a 50/100/200-
day SMA. So the universe data layer stores DAILY price + volume and derives the weekly
rebalance grid (eligibility + returns) from it. This refines ADR 0005's v1 "weekly
resampling" assumption (recorded as an amendment to ADR 0005).

## What this layer must NOT pretend to be (the data-driven deviations from the paper)

Binance Vision publishes price + volume but NO market capitalization or circulating
supply. Therefore this replication CANNOT use the paper's market-cap universe filter or
its market-cap value-weighting. ADR 0005 anticipated this and deliberately substitutes a
LIQUIDITY universe (top-N by trailing USD dollar volume), point-in-time, and a retail-
realistic LONG-ONLY top-quintile headline (the academic long-short is the comparison).
These are documented deviations, carried as caveats with the numbers, not silent choices:

1. Universe screen: top-N by trailing weekly dollar volume (a liquidity proxy), NOT the
   paper's market-cap floor. Closest paper analogue: the Table 8 "100 most liquid" subset
   (Amihud). Dollar volume and Amihud liquidity are highly correlated; dollar volume is
   the ADR-0005-specified, reproducible-from-Binance choice. (Amihud is a tracked
   alternative knob.)
2. Weighting: equal-weight within the quintile (PR3), NOT market-cap value-weighting
   (no market cap available). A documented deviation; the long leg carries much of the
   paper's alpha, and equal-weight is the honest retail proxy.
3. Source basis: Binance-only spot vs the paper's CoinMarketCap cross-venue aggregate; a
   small price/liquidity basis, caveated.
4. Stablecoins / leveraged tokens excluded (see below): the paper's mcap universe rarely
   ranks stables; a dollar-volume-ranked universe would be dominated by them, so excluding
   them is both faithful (the paper's "coins" are not pegs/derivatives) and necessary.

## Granularity, source, and the canonical instrument

- Source: Binance Vision spot monthly-partitioned klines (free, immutable, checksummed,
  US-reachable, and delisting-complete: the S3 bucket retains dead symbols, enumerable
  directly). Probed live 2026-06: 664 USDT-quoted spot symbols (3,615 total), with the
  famously-delisted LUNA / FTT / BCC / VEN / UST / SRM all present, confirming the bucket
  is survivorship-safe at the source.
- Granularity: DAILY (`1d`) klines (close = column 4, close_time = column 6 normalized by
  the existing ms/us normalizer, quote-asset-volume = column 7 = the USD(T) dollar volume
  directly, no price * base-volume reconstruction).
- Universe: USDT-quoted spot pairs (the dominant liquid quote), minus a deterministic,
  documented exclusion of stablecoin/fiat pairs and Binance leveraged tokens.
- The panel is keyed on (date, symbol); `symbol` is unique. `canonical` (the venue-
  independent asset key) is carried as INFORMATIONAL only and is NOT a dedup/join key, so
  the `1000SHIB` vs `SHIB` repricing convention and a ticker rename (LUNA -> LUNC) are
  treated as the distinct tradeable instruments they are (a rename appears as a delisting
  plus a fresh listing; the dead leg is retained, so survivorship is preserved; continuity
  is intentionally not stitched). This decision is documented, not silent.

## The exclusion filter (deterministic, documented, artifact-surfaced)

`classify_exclusion(symbol, listed_bases)` excludes, from the USDT universe:
- Non-standard tickers: a base that is not ASCII uppercase-alphanumeric (the Binance Vision
  bucket carries a few non-ASCII novelty symbols, e.g. a CJK-named promo token, that are not
  coins and cannot even be ASCII-encoded into an S3 URL). Checked first.
- Stablecoin / fiat bases (a committed `STABLE_OR_FIAT` set: USDC, BUSD, TUSD, FDUSD,
  USDP, DAI, PAX, UST, USTC, GUSD, USD1, PYUSD, USDE, EUR, GBP, AUD, TRY, BRL, RUB, JPY,
  AEUR, ...): a USD-pegged instrument has no trend/momentum signal and is not what the
  paper's "coin" universe means; it would also dominate a dollar-volume-ranked top-N.
- Binance leveraged tokens: bases ending in BULL / BEAR / 3L / 3S / 4L / 4S / 5L / 5S
  unconditionally (no real coin ends in these), and UP / DOWN only when the base minus the
  suffix is itself a listed base (so BTCUP -> BTC is listed -> excluded, while JUP -> "J"
  not a base -> kept). Leveraged tokens are decaying derivatives, not spot coins.

The full list of EXCLUDED symbols (and the reason) is emitted into the universe artifact
so a reviewer can eyeball the drops and catch a missed stable; the build also reconciles
`n_enumerated == n_excluded + n_in_universe` so nothing is dropped silently.

## The weekly grid + the point-in-time eligibility (the load-bearing PIT spine)

From the daily panel:
- Weekly bars: resample daily -> weekly (week ending Sunday UTC, the Binance native week),
  weekly close = the last daily close in the week, weekly dollar volume = the sum of daily
  dollar volume. A week with no daily data (a halt) has no weekly bar.
- Returns: `weekly_return(t) = close(t)/close(t-1) - 1` within symbol, NULL across a
  non-consecutive-week gap (so a halt is never mislabeled as a one-week return). PR1 also
  exposes `forward_return(t)` = `weekly_return` shifted -1 within symbol (the return over
  (t, t+1]), the holding return PR3 must use, named so the same-bar look-ahead (decide and
  realize on the same close) is structurally hard to hit.
- Eligibility (`pit_eligible`): at each week t, among symbols with a bar at t and at least
  `MIN_HISTORY_WEEKS` weekly bars up to t, rank by `trailing_dollar_volume` (the backward
  rolling mean of weekly dollar volume over `LOOKBACK_WEEKS`, ending AT week t, strictly
  point-in-time), tie-broken by symbol ascending, and mark the top `TOP_N` eligible. The
  rank at week t reads ONLY data at or before t. Delisting is handled by absence: after a
  coin's last bar it is not eligible (it stopped trading), but its earlier weeks DO count
  in earlier rankings (no survivorship).

v1 knobs (each a PR2/PR3 trial-registry entry): `TOP_N = 100` (the paper's liquid-subset
size; 20 per quintile), `LOOKBACK_WEEKS = 4` (a trailing ~1-month ADV), `MIN_HISTORY_WEEKS
= 8`, `N_MAX_COMMITTED = 120` (the trim ceiling). Window pinned in the build script.

## Reproducibility model (consistent with the VRP PR5b precedent)

- Raw daily zips: gitignored `data/raw/`, each checksum-verified at fetch (immutable +
  published `.CHECKSUM`).
- The committed anchor: ONE daily panel under `tests/data/`, the daily panel TRIMMED to the
  union of symbols ever in the top-`N_MAX_COMMITTED` (the losslessness argument below). A
  daily panel of ~560 liquid coins over seven years is ~35 MB plain, so it is committed
  GZIPPED (`ctrend_daily_panel_usdt.csv.gz`, ~10 MB). Two cross-platform-stable hashes pin
  it: the universe artifact stores the SHA256 of the DECOMPRESSED CSV CONTENT (the
  meaningful integrity check, platform-independent because a re-gzip on a different zlib
  yields different container bytes for identical content), and the snapshot manifest stamps
  the committed `.gz` blob's FILE SHA256 (git preserves the blob byte-for-byte and
  `.gitattributes` marks `*.gz binary`, so CI reads the identical bytes a build wrote). The
  underlying CSV is deterministic: sorted by `(symbol, date)`, LF, each value its EXACT
  `Decimal` with trailing zeros stripped (lossless: `4.83900000` is written `4.839` and
  reads back to the identical float). The weekly grid, eligibility, and returns are PURE
  FUNCTIONS of this committed panel (computed in code, never separately committed, so they
  cannot drift). The build re-fetches the checksummed raw and proves it reproduces the
  committed eligibility.
- The universe artifact (`artifacts/ctrend_universe.json`) regenerates from the committed
  panel offline and carries the summary, the delisting proof, the excluded-symbol list,
  and the fingerprint.
- An offline test rebuilds the artifact's eligibility counts + delisting proof from the
  committed panel (mirrors `tests/unit/test_vrp_gate_reproduces.py`); a live network test
  is the real-data proof (enumeration returns the delisted coins; a real fetch shows a
  delisted coin's data stopping).

## The losslessness of the committed-panel trim

To select the top-N (N <= N_MAX) at week t, the top-N are the N largest trailing-weekly-
dollar-volume symbols meeting min-history with a bar at t. Any symbol in week t's
top-N_MAX is by definition in the union "ever top-N_MAX" = the committed set; a symbol NOT
in the committed set is never in any week's top-N_MAX, so it cannot be in week t's top-N
(N <= N_MAX). A committed symbol's trailing volume and history depend only on its OWN
(daily -> weekly) bars, all committed. Therefore top-N over the trimmed panel equals top-N
over the full universe for every week and every N <= N_MAX. The build asserts this
directly at N_MAX (a safety net against a min-history / tie-break interaction), and treats
a per-symbol fetch FAILURE as fatal (a silent drop would reintroduce survivorship through
the build harness, the exact failure mode the enumeration design prevents).

## PIT / honesty invariants (the audit list)

1. The liquidity rank at week t uses only data at or before t (backward rolling ending at
   t). No future.
2. Delisting is handled by absence (no survivorship; dead coins' earlier weeks still rank).
3. `weekly_return` is null across a calendar-week gap; `forward_return` is the explicit
   holding return so PR3 cannot use the same-bar return it decided on.
4. The committed-panel trim is lossless for N <= N_MAX (argued + build-asserted).
5. Determinism: sorted polars, deterministic symbol-ascending tie-break, no RNG, LF
   committed bytes, exact-Decimal CSV, the single documented Decimal -> Float64 cast at the
   frame build.
6. A fetch failure is fatal and the enumerated == excluded + in-universe reconciliation is
   asserted, so no coin is silently dropped.

## How the design review shaped this

The independent senior-quant review returned approve-with-changes. Its two most
consequential findings drove the design before any data was committed: that the panel must
be DAILY (the paper's features are daily), which sent me to verify the paper's exact
construction; and that the holding-return alignment must be foreclosed at the data layer
(the `forward_return` column). The other findings hardened the build against silent
survivorship drops, fixed a cross-sectional tie-break that the obvious one-liner inverts,
corrected the bar-vs-calendar-week labeling, and aligned the error class, the
`min_samples` deprecation, and the sorted-input guards with the existing codebase. The
per-finding resolutions are recorded in CHANGELOG.md.
