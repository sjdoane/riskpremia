"""Fetch month-end total-return levels for the Study 6 proxies (VTI, IEF, SGOV).

Network entry point. Pulls monthly dividend-adjusted closes for the three proxies, aligns them on
the common completed months, and writes the committed seed (default) or appends the newest completed
month to the runtime levels file. Adjusted close is the total-return level, so dividends are
reinvested implicitly, matching the backtest's total-return basis.

Usage (from the repo root, with the project venv):
  python -m scripts.build_live_levels            # (re)build the committed seed from ~8y of history
  python -m scripts.build_live_levels append     # append the newest completed month to live_state
"""

from __future__ import annotations

import calendar
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

from riskpremia.live.errors import LiveError
from riskpremia.live.levels import LevelRow, append_level, read_levels, write_levels_csv
from riskpremia.live.signal import CASH_SYMBOL, SLEEVE_SYMBOLS

_REPO = Path(__file__).resolve().parents[1]
_SEED = _REPO / "tests" / "data" / "live_levels_seed.csv"
_LIVE = _REPO / "live_state" / "levels.csv"
_EQUITY = SLEEVE_SYMBOLS["equity"]
_BOND = SLEEVE_SYMBOLS["bond"]
_UA = "riskpremia live deployment (https://github.com/sjdoane/riskpremia)"
_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1mo&range={rng}"


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _fetch_monthly_adjclose(
    symbol: str, *, rng: str, attempts: int = 4
) -> dict[tuple[int, int], float]:
    """Return a map from (year, month) to the monthly adjusted close, completed months only."""
    url = _CHART.format(sym=symbol, rng=rng)
    last: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read())
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(2.0 * (i + 1))
    else:
        raise LiveError(f"fetch failed for {symbol}: {last}")
    result = payload.get("chart", {}).get("result")
    if not result:
        raise LiveError(f"no chart result for {symbol}: {payload.get('chart', {}).get('error')}")
    block = result[0]
    stamps = block["timestamp"]
    adj = block["indicators"]["adjclose"][0]["adjclose"]
    now = datetime.now(UTC)
    current = (now.year, now.month)
    out: dict[tuple[int, int], float] = {}
    for ts, value in zip(stamps, adj, strict=True):
        if value is None:
            continue
        d = datetime.fromtimestamp(int(ts), tz=UTC)
        key = (d.year, d.month)
        if key >= current:  # drop the current, incomplete month
            continue
        out[key] = float(value)
    return out


def _aligned_rows(rng: str) -> list[LevelRow]:
    eq = _fetch_monthly_adjclose(_EQUITY, rng=rng)
    bd = _fetch_monthly_adjclose(_BOND, rng=rng)
    cs = _fetch_monthly_adjclose(CASH_SYMBOL, rng=rng)
    common = sorted(set(eq) & set(bd) & set(cs))
    if not common:
        raise LiveError("no common completed months across the three proxies")
    return [LevelRow(_month_end(y, m), eq[(y, m)], bd[(y, m)], cs[(y, m)]) for (y, m) in common]


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if mode == "append":
        if not _LIVE.exists():
            raise LiveError(f"{_LIVE} does not exist; run paper_rebalance once to initialize it")
        rows = _aligned_rows("2y")
        last = read_levels(_LIVE)[-1].date
        pending = [r for r in rows if (r.date.year, r.date.month) > (last.year, last.month)]
        if not pending:
            print(f"No new completed month after {last}; nothing to append.")
            return
        for r in pending:  # backfill every missing completed month, in order, gap-checked
            append_level(_LIVE, r)
        names = ", ".join(r.date.isoformat() for r in pending)
        print(f"Appended {len(pending)} month(s) to {_LIVE.relative_to(_REPO).as_posix()}: {names}")
        return
    rows = _aligned_rows("8y")
    write_levels_csv(_SEED, rows)
    print(f"Wrote {_SEED.relative_to(_REPO).as_posix()} with {len(rows)} months "
          f"({rows[0].date.isoformat()}..{rows[-1].date.isoformat()})")


if __name__ == "__main__":
    main()
