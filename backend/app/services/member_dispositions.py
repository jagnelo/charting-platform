"""Provider-neutral member disposition accounting for canonical source plans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MEMBER_DISPOSITION_KEYS = ("canonical", "placeholder", "unresolved", "excluded")


def member_disposition_counts(
    members: list[Any], descriptor: Any, exclusions: tuple[dict, ...] | list[dict]
) -> dict[str, int]:
    """Return stable canonical/placeholder/unresolved/excluded counts.

    Source resolvers publish resolved canonical members, retain placeholder
    provenance on the descriptor, and represent unresolved or non-member rows
    as exclusion reasons. Keep aggregate exclusion fields compatible while
    making each disposition explicit to maintenance and workstation clients.
    """

    provenance = getattr(descriptor, "provenance", {}) or {}
    placeholder_count = 0
    if isinstance(provenance, Mapping):
        try:
            placeholder_count = max(0, int(provenance.get("placeholder_member_count", 0) or 0))
        except (TypeError, ValueError):
            placeholder_count = 0
    unresolved_rows = sum(
        1 for exclusion in exclusions if exclusion.get("reason") == "unresolved_holding"
    )
    excluded_rows = sum(
        1
        for exclusion in exclusions
        if exclusion.get("reason") in {"cash_holding", "derivative_holding", "non_equity_holding"}
    )
    return {
        "canonical": len({int(member.instrument_id) for member in members}),
        "placeholder": placeholder_count,
        "unresolved": max(0, unresolved_rows - placeholder_count),
        "excluded": excluded_rows,
    }
