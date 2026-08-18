"""Planning helpers for durable benchmark-family holdings refresh runs."""

from __future__ import annotations

from datetime import date

from app.services.benchmark_family_history import (
    normalize_family_keys,
    normalize_family_roles,
)

MAX_HOLDINGS_REFRESH_DATES = 64


def plan_benchmark_family_holdings_refresh(
    *,
    requested_dates: list[date],
    family_keys: list[str] | None = None,
    roles: list[str] | None = None,
) -> dict:
    """Normalize a deterministic date × family unit plan without provider access."""

    normalized_dates = sorted(set(requested_dates))
    if not normalized_dates:
        raise ValueError("At least one requested benchmark family holdings date is required.")
    if len(normalized_dates) > MAX_HOLDINGS_REFRESH_DATES:
        raise ValueError(
            f"At most {MAX_HOLDINGS_REFRESH_DATES} requested holdings dates are supported."
        )
    normalized_families = normalize_family_keys(family_keys)
    normalized_roles = normalize_family_roles(roles)
    return {
        "requested_dates": normalized_dates,
        "family_keys": normalized_families,
        "roles": normalized_roles,
        "total_units": len(normalized_dates) * len(normalized_families),
    }
