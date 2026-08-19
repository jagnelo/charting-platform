"""Planning helpers for durable benchmark-family holdings refresh runs."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.services.benchmark_family_history import (
    normalize_family_keys,
    normalize_family_roles,
)

MAX_HOLDINGS_REFRESH_DATES = 64


def completed_month_end_dates(*, as_of: date | None = None, count: int = 1) -> list[date]:
    """Return bounded completed month-end candidates for maintenance refreshes.

    These are maintenance request dates, not a claim about any provider's official
    rebalance cadence. Each adapter may return the latest evidenced composition on
    or before the requested date; the requested date remains the point-in-time
    boundary for canonical persistence and later resolution.
    """

    if count < 1 or count > MAX_HOLDINGS_REFRESH_DATES:
        raise ValueError(
            f"At most {MAX_HOLDINGS_REFRESH_DATES} completed month-end dates are supported."
        )
    current = as_of or datetime.now(UTC).date()
    candidate = current.replace(day=1) - timedelta(days=1)
    dates: list[date] = []
    for _ in range(count):
        dates.append(candidate)
        candidate = candidate.replace(day=1) - timedelta(days=1)
    return dates


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
