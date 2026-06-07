from __future__ import annotations


class ETFHoldingsInternalProvider:
    """Internal provenance source for instruments materialized from ETF holdings."""

    name = "etf_holdings_internal"
    base_url = None
    description = (
        "Internal ETF holdings ingestion source used to materialize lightweight ETF "
        "and constituent instruments without fetching price history."
    )
