"""Phase 0 live deployment of the Study 6 cross-asset defensive trend (see docs/deployment).

The monthly long-or-cash signal is computed by the FROZEN backtest rule (the shared
`riskpremia.xtrend.gate.signal_from_monthly_levels`), never a second implementation, so the
deployed decision cannot drift from the gated backtest. A self-contained paper-trading engine marks
a simulated account at month-end prices with the same cost mechanics as the backtest, so a live
track record can be accrued at zero capital before any real money or broker is involved.
"""
