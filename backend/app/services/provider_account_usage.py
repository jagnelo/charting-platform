"""Provider-native account usage observations.

The request ledger remains the authoritative local accounting source.  This
module stores provider-reported counters as separate observations so operators
can compare the external account window with local usage across sessions.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderAccountUsageObservation, ProviderCapability
from app.providers.base import ProviderAccountUsage
from app.providers.errors import bounded_redact_provider_message
from app.services.provider_runtime import execute_provider_call, resolve_provider_chain


def _usage_payload(observation: ProviderAccountUsageObservation, provider: str) -> dict[str, Any]:
    return {
        "id": observation.id,
        "provider": provider,
        "observed_at": observation.observed_at,
        "unit": observation.unit,
        "limit": observation.limit,
        "remaining": observation.remaining,
        "consumed": observation.consumed,
        "reset_at": observation.reset_at,
        "options_data_permissions": observation.options_data_permissions,
    }


def _validate_usage(usage: ProviderAccountUsage) -> None:
    if not str(usage.unit or "").strip():
        raise ValueError("provider returned an empty account-usage unit")
    for field in ("limit", "remaining", "consumed"):
        value = getattr(usage, field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError(f"provider returned an invalid account-usage {field}")
    if usage.limit is not None and usage.remaining is not None and usage.remaining > usage.limit:
        raise ValueError("provider returned account-usage remaining above limit")
    if usage.reset_at is not None and usage.reset_at.tzinfo is None:
        raise ValueError("provider returned a timezone-naive account-usage reset")


async def refresh_provider_account_usage(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
) -> dict[str, Any]:
    """Fetch and persist one provider-native usage observation.

    Admission still goes through the normal provider runtime, including
    credentials, reviewed quota contracts, live-probe status, and the explicit
    operation cost for ``fetch_account_usage``.  A provider that does not
    expose this surface is not guessed or synthesized.
    """

    chain = await resolve_provider_chain(
        db,
        ProviderCapability.ACCOUNT_USAGE,
        operation="fetch_account_usage",
    )
    if provider_name:
        chain = [item for item in chain if item.provider_name == provider_name]
    if not chain:
        return {"status": "no_qualified_provider", "providers": [], "observations": []}

    observations: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for resolved in chain:
        try:
            execution = await execute_provider_call(
                db,
                ProviderCapability.ACCOUNT_USAGE,
                "fetch_account_usage",
                provider_name=resolved.provider_name,
                invoke=lambda provider, _symbol: provider.fetch_account_usage(),
                response_items=lambda value: 1 if value is not None else 0,
                treat_empty_as_failure=True,
            )
            usage = execution.result
            if not isinstance(usage, ProviderAccountUsage):
                raise TypeError("provider returned an invalid account-usage observation")
            _validate_usage(usage)
            observed_at = usage.observed_at
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=UTC)
            row = ProviderAccountUsageObservation(
                data_source_id=execution.data_source.id,
                observed_at=observed_at,
                unit=usage.unit,
                limit=usage.limit,
                remaining=usage.remaining,
                consumed=usage.consumed,
                reset_at=usage.reset_at,
                options_data_permissions=usage.options_data_permissions,
            )
            db.add(row)
            await db.flush()
            observations.append(_usage_payload(row, execution.provider_name))
            # One provider is selected by the runtime for this account-scoped
            # observation. Do not call lower-priority providers in the same
            # request and spend another account quota window.
            break
        except Exception as exc:  # noqa: BLE001 - retain redacted admin evidence upstream.
            failures.append(
                {
                    "provider": resolved.provider_name,
                    "error": bounded_redact_provider_message(exc, max_length=500),
                }
            )

    await db.commit()
    return {
        "status": "refreshed" if observations else ("failed" if failures else "no_observation"),
        "providers": [item["provider"] for item in observations],
        "observations": observations,
        "failures": failures,
    }


async def list_provider_account_usage(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the most recent durable native-usage observations."""

    bounded_limit = max(1, min(int(limit), 500))
    query = (
        select(ProviderAccountUsageObservation, DataSource.name)
        .join(DataSource, DataSource.id == ProviderAccountUsageObservation.data_source_id)
        .order_by(ProviderAccountUsageObservation.observed_at.desc())
        .limit(bounded_limit)
    )
    if provider_name:
        query = query.where(DataSource.name == provider_name)
    rows = (await db.execute(query)).all()
    return [_usage_payload(observation, provider) for observation, provider in rows]
