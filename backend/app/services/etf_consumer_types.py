"""TC read-side classification for persisted ETF holding evidence.

The released ETF service no longer exports these historical consumer helpers.
Keep TC's narrow eligibility rules local to its consumers; raw producer labels
remain untouched for audit and source lineage.
"""

from __future__ import annotations

import re

EQUITY_HOLDING_TYPES = frozenset(
    {
        "equity",
        "stock",
        "common_stock",
        "real_estate_investment_trust",
    }
)


def normalize_holding_type(value: str | None) -> str:
    """Normalize a label for TC eligibility checks without mutating stored data."""

    text = str(value or "").strip().casefold()
    return "_".join(part for part in re.split(r"[^a-z0-9]+", text) if part)


def is_equity_holding_type(value: str | None) -> bool:
    return normalize_holding_type(value) in EQUITY_HOLDING_TYPES


def is_placeholder_symbol(symbol: str | None) -> bool:
    """Recognize TC's unresolved-holding marker without a producer API shim."""

    normalized = str(symbol or "").strip().upper()
    return bool(normalized and normalized.startswith("HOLDING-"))
