# ADR 0007: kill CME Micro G6 FX carry as a deployable strategy

Status: Accepted. Feasibility killed before implementation.
Date: 2026-06-06.
Authors: Sam Doane (strategy feasibility fork after the BTC/ETH slow-trend null, with
separate data, methodology, execution, and stress reviews).

## Context

Study 4, the BTC/ETH slow-trend rule, returned another honest null. ADR 0006 named
G10 Micro FX carry with a hard risk-off switch as the registered backup, but only if two
gates passed before any backtest code was written:

- A free, keyless, reproducible data path for spot FX, rates, futures settlements, and
  CFTC positioning.
- A stress-loss gate showing that the minimum practical CME Micro FX deployment could
  survive a USD 10,000 account.

Those were intentionally feasibility gates, not after-the-fact diagnostics. The whole
point was to avoid spending another build cycle on a strategy whose failure mode is already
visible from data access or integer contract sizing.

## Research Findings

### The tradeable universe is not G10

CME Micro FX does not cover the full G10 currency set at micro size. Current CME product
materials support a partial micro universe:

| Currency future | Code | Contract size | Tick | Tick value |
| --- | --- | ---: | ---: | ---: |
| Micro EUR/USD | `M6E` | 12,500 EUR | 0.0001 USD/EUR | USD 1.25 |
| Micro AUD/USD | `M6A` | 10,000 AUD | 0.0001 USD/AUD | USD 1.00 |
| Micro GBP/USD | `M6B` | 6,250 GBP | 0.0001 USD/GBP | USD 0.625 |
| Micro JPY/USD | `MJY` | 1,250,000 JPY | 0.000001 USD/JPY | USD 1.25 |
| Micro CAD/USD | `MCD` | 10,000 CAD | 0.0001 USD/CAD | USD 1.00 |
| Micro CHF/USD | `MSF` | 12,500 CHF | 0.0001 USD/CHF | USD 1.25 |

NZD, NOK, and SEK are available in broader CME FX products, but not in the current micro
set. The honest label is therefore **CME Micro G6 FX carry**, not G10 carry. Sources:
[CME Micro FX](https://www.cmegroup.com/markets/microsuite/fx.html) and
[CME FX Product Guide](https://www.cmegroup.com/markets/fx/fx-product-guide.html).

### The exact free settlement-history path fails

The data review found viable free sources for a measurement-only macro study:

- BIS bilateral exchange rates and Federal Reserve H.10/FRED as spot FX sources.
- BIS central bank policy rates as a policy-rate carry signal.
- Cboe VIX or FRED VIXCLS for the hard risk-off filter.
- CFTC historical compressed COT files for weekly positioning diagnostics.

That is not enough for the deployable CME Micro FX strategy. The registered backup required
free historical futures settlements or a robust exact proxy for the traded contracts, because
the backtest must model futures returns, roll, bid-ask, execution, and daily variation-margin
liquidity.

The current CME settlement path is not robust enough to be load-bearing. CME describes delayed
settlement viewing as free, while bulk historical settlement access is handled through paid
DataMine products. A browser-visible TCF directory is not the same as a stable, keyless,
scriptable history. Local direct fetch attempts for current TCF CSV files returned HTTP 403,
and the visible public directory does not provide a long 2010-plus historical archive. Source:
[CME settlement data FAQ](https://www.cmegroup.com/articles/faqs/access-to-cme-group-settlement-data-faq.html).

CFTC positioning did pass a free-source check: the 2025 and 2026 financial futures COT
historical ZIP files were reachable with HTTP 200 from the official CFTC site. That is useful,
but it is auxiliary weekly data, not the futures return series.

### The USD 10,000 stress-loss gate fails

Even if the settlement data were available, the exchange-traded micro deployment is too lumpy
for a USD 10,000 account.

The yen carry unwind is the live recent failure mode. BIS Bulletin 90 describes the August
2024 event as a carry-unwind shock with a large estimated yen carry footprint. Using Fed H.10
USD/JPY closes, USD/JPY moved from 161.73 on July 10, 2024 to 143.95 on August 5, 2024. A
short `MJY` position loses roughly:

```text
1,250,000 * (1 / 143.95 - 1 / 161.73) = USD 955
```

An AUD/JPY-style micro cross built from a long AUD/USD leg and a short JPY/USD leg loses
roughly USD 1,214 over the same move before slippage and margin frictions. Sources:
[BIS Bulletin 90](https://www.bis.org/publ/bisbull90.htm),
[Fed H.10 July 15, 2024](https://www.federalreserve.gov/releases/h10/20240715/), and
[Fed H.10 August 12, 2024](https://www.federalreserve.gov/releases/h10/20240812/).

The CHF event is worse. The SNB discontinued the EUR/CHF minimum exchange-rate policy on
January 15, 2015. Fed H.10 USD/CHF moved from 1.0172 on January 14, 2015 to 0.8488 on
January 16, 2015. A short `MSF` position loses roughly:

```text
12,500 * (1 / 0.8488 - 1 / 1.0172) = USD 2,438
```

Two short CHF funding legs are about USD 4,876 before slippage. Three are about USD 7,314,
already a 73 percent hit to a USD 10,000 account. Sources:
[SNB 2015 announcement context](https://www.snb.ch/en/publications/communication/speeches/2015/ref_20150424_tjn)
and [Fed H.10 January 20, 2015](https://www.federalreserve.gov/releases/h10/20150120/).

The practical problem is not just margin. Margin is a performance bond, not risk capital.
Diversified carry baskets require multiple integer contracts, two-leg crosses introduce
ratio rounding, and a VIX risk-off switch cannot reliably exit a surprise currency-specific
event before the loss is realized.

## Decision

**Do not implement the CME Micro FX carry gate. Kill this backup at feasibility.**

The strategy fails both pre-implementation bars:

- **Data gate:** the exact free, keyless, reproducible futures-settlement history path is
  not reliable enough to support a CME Micro FX backtest. Spot FX plus policy rates can
  support a measurement study, but not a deployable futures strategy verdict.
- **Stress gate:** integer micro contracts can plausibly lose more than 50 percent of a
  USD 10,000 account in CHF-style funding shocks when a diversified carry basket holds
  multiple short funding legs.

The result is not "carry does not exist." The result is narrower and more useful:
CME Micro G6 FX carry is not a good next deployable RiskPremia build under the project's
free-data, small-account, cost-realistic constraints.

## What Remains Allowed

A future **measurement-only** macro note could still use BIS/Fed spot FX, BIS policy rates,
Cboe/FRED VIX, and CFTC positioning to study whether simple spot-plus-rate carry regimes
look economically alive. That would need a new ADR and a clearly different headline:
measurement, not a tradeable CME Micro strategy.

Do not revive the deployable version unless at least one of these changes:

- Paid or licensed CME settlement history is accepted and documented.
- A free, stable, source-approved settlement archive appears.
- The deployment account size is large enough that one to three micro contracts cannot
  dominate account survival.
- The strategy is scoped to one or two predefined pairs and is no longer described as a
  diversified carry basket.

Any such revival counts as a new trial family and must be deflated accordingly.

## Next Step

Start a fresh strategy fork rather than continuing down the Micro FX path. The next
candidate must pass the same two pre-code feasibility gates:

- Free, reproducible, source-approved data for the exact traded or measured object.
- A minimum-size stress test that cannot plausibly destroy the target account before the
  model has a chance to be right.

## Status

Accepted. CME Micro G6 FX carry is killed as a deployable strategy before implementation.
The decision artifact is this ADR; the supporting research note is
`docs/research/0006-g10-micro-fx-feasibility.md`.
