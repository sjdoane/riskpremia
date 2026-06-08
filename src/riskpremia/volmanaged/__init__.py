"""Study 8: a volatility-managed market portfolio adjudicating the Moreira-Muir claim (ADR 0010).

The headline kill is the managed-minus-unmanaged difference series (the standalone managed series
is a levered long-equity position whose Sharpe is the equity premium, not vol-timing skill). The
c-normalization is computed on the UNCAPPED weight with the cap as a separate friction, and an
expanding-window c is reported as the real-time sensitivity, per the design-review amendment.
"""
