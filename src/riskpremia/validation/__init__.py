"""Asset-agnostic validation machinery, vendored from pit-backtest.

Event-time-purged cross-validation (`cv.py`: PurgedKFold / WalkForward / CPCV
with embargo) and the SQLite-backed trial registry (`trial_registry.py`, which
feeds the Deflated Sharpe trial count) are copied from the sibling pit-backtest
project. The CPCV purge predicate operates on a generic `dt` column plus
per-observation label horizons, so it applies to funding-clock observations
(8h marks) exactly as it applied to daily equity bars; the funding-carry study
purges on the FUNDING-EVENT clock, not the calendar index. See each module's
header for provenance.
"""

from __future__ import annotations
