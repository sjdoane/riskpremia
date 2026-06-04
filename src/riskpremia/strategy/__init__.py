"""Signal + regime logic for the funding-carry study (built new, last).

Built AFTER the cost model and the random-entry null, per the inverted build
order (rule 6). The regime gate is a risk-OFF circuit breaker (stand aside when
funding is thin or tail risk is elevated), never a lean-in signal, mirroring the
Track-A stress-test discipline on the Bollerslev-Tauchen-Zhou gate. Every knob
(funding threshold, regime gate, venue, rebalance clock, sizing rule) is logged
to the trial registry so the Deflated-Sharpe trial count stays honest.
"""

from __future__ import annotations
