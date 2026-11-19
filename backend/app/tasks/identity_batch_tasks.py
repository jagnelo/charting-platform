"""Scheduled batched identity resolution for discovered US equity listings."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.provider_runtime import ProviderCapability
from app.services.identity_batch import (
    OPENFIGI_OPERATION,
    OPENFIGI_PROVIDER,
    release_long_held_identity_jobs,
    resolve_us_listed_equity_identities,
)

logger = logging.getLogger(__name__)

# Bounded so a backlog of long-held children re-enters the queue gradually.
_RELEASE_LONG_HELD_PER_PASS = 500


async def ensure_openfigi_native_baseline(db: AsyncSession) -> str | None:
    """Return ``None`` when the OpenFIGI mapping pool can be reserved now.

    OpenFIGI's reviewed contract reconciles its per-minute mapping pool from
    native rate-limit headers. When that rolling baseline is unknown, refresh
    it through the same guarded native-usage path the durable queue uses,
    which itself requires the operator allowlist
    (``PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS``). Never bypass it.
    """

    from app.tasks.data_tasks import (
        _configured_native_usage_providers,
        _native_operation_baseline_states,
        _run_native_usage_refresh_job,
    )

    plan, reason = await _native_operation_baseline_states(
        db,
        OPENFIGI_PROVIDER,
        capability=ProviderCapability.INSTRUMENT_IDENTIFIERS,
        operation=OPENFIGI_OPERATION,
        now=datetime.now(UTC),
    )
    if plan is None:
        return reason or "native_quota_baseline_status_unavailable"
    _policy, states = plan
    unknown = [
        str(dimension.get("name") or "")
        for dimension, state in states
        if state.get("status") == "unknown"
    ]
    if not unknown:
        return None
    if OPENFIGI_PROVIDER not in _configured_native_usage_providers():
        return "native_usage_refresh_not_enabled_for_provider"
    result = await _run_native_usage_refresh_job(
        db,
        {
            "provider_name": OPENFIGI_PROVIDER,
            "trigger_capability": ProviderCapability.INSTRUMENT_IDENTIFIERS.value,
            "trigger_operation": OPENFIGI_OPERATION,
            "dimensions": [{"name": name} for name in unknown],
        },
    )
    await db.commit()
    if result.get("preparation_status") == "ready":
        return None
    return str(result.get("reason_code") or "native_usage_refresh_not_qualified")


async def resolve_identity_batch_task(ctx: dict) -> dict:
    """One bounded pass of batched US-listing identity resolution."""

    del ctx
    if not settings.INSTRUMENT_IDENTITY_BATCH_ENABLED:
        return {"skipped": True, "reason": "identity batch disabled"}
    if settings.E2E_SEED_MARKET_DATA:
        return {"skipped": True, "reason": "controlled fixture mode owns identities"}
    async with AsyncSessionLocal() as db:
        released = await release_long_held_identity_jobs(
            db,
            now=datetime.now(UTC),
            defer_limit=timedelta(
                seconds=max(0, int(settings.INSTRUMENT_IDENTITY_HELD_DEFER_MAX_SECONDS))
            ),
            max_jobs=_RELEASE_LONG_HELD_PER_PASS,
        )
        await db.commit()
        result = await resolve_us_listed_equity_identities(
            db,
            ensure_native_baseline=ensure_openfigi_native_baseline,
            max_requests=max(1, int(settings.INSTRUMENT_IDENTITY_BATCH_MAX_REQUESTS)),
            max_seconds=max(1.0, float(settings.INSTRUMENT_IDENTITY_BATCH_MAX_SECONDS)),
            retry_after=timedelta(days=max(1, int(settings.INSTRUMENT_IDENTITY_BATCH_RETRY_DAYS))),
        )
    result["long_held_identity_jobs_released"] = released
    log = logger.warning if result.get("status") in {"held", "failed"} else logger.info
    log("identity batch: %s", result)
    return result
