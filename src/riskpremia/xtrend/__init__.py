"""Study 6: a cross-asset defensive trend rule on public-domain data (ADR 0008).

A frozen, no-fit, monthly, long-or-cash time-series trend rule across genuinely
low-correlated asset classes (US equity, long-term US Treasury, gold), each held only
when its total-return index is above its ten-month moving average, otherwise in the
one-month Treasury bill. The net series is marked to market daily and scored in excess
of the bill. See ADR 0008 for the frozen rule and the pre-registered kill criterion.
"""
