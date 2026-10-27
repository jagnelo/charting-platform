"""One-shot, administrator-only VanEck OIH issuer qualification."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.data_source import DataSource
from app.models.etf_holdings import (
    ETFHoldingsBackfillJob,
    ETFHoldingsRawArtifact,
    ETFHoldingsSnapshot,
    ETFProfile,
)
from app.models.instrument import Instrument
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.services.etf_holdings import _hash_payload
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    ETFVaneckInitialQualificationBudget,
    _has_explicit_account_scope_mapping,
    require_unbound_etf_holdings_context,
)
from app.services.etf_holdings_refresh import (
    _record_success,
    _refresh_adapter_route,
    _resolve_canonical_fund_instrument,
)
from app.services.provider_quota_coordinator import account_scope_for_provider
from app.services.provider_runtime import record_entitlement_revision

VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE = "vaneck_oih_initial_qualification"
VANECK_OIH_INITIAL_QUALIFICATION_OPERATION = "fetch_etf_holdings_latest"
VANECK_OIH_PRODUCT_SLUG = "oil-services-etf-oih"
VANECK_OIH_INITIAL_URL = (
    "https://www.vaneck.com/us/en/investments/oil-services-etf-oih/" "downloads/holdings/?cken=true"
)
VANECK_OIH_INITIAL_DEADLINE_SECONDS = 120
VANECK_OIH_INITIAL_MAX_PHYSICAL_REQUESTS = 3
VANECK_OIH_INITIAL_MIN_INTERVAL_SECONDS = 30
VANECK_OIH_INITIAL_MAX_BODY_BYTES = 5 * 1024 * 1024


def _qualification_lock_key(account_scope: str) -> int:
    material = (
        f"provider:vaneck:ETF_HOLDINGS:initial:{account_scope.strip().lower()}:OIH"
    ).encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=True)


def _provider_review_fingerprint(
    source: DataSource,
    policy: ProviderPolicy,
    entitlement: ProviderEntitlement,
) -> str:
    config = source.config if isinstance(source.config, dict) else {}
    material = {
        "source": {
            "id": source.id,
            "name": source.name,
            "base_url": source.base_url,
            "supported_capabilities": source.supported_capabilities,
            "is_active": source.is_active,
            "review": config.get("etf_holdings_review"),
            "usage_tracking": config.get("usage_tracking"),
        },
        "policy": {
            "is_enabled": policy.is_enabled,
            "quota_scope": policy.quota_scope,
            "quota_source": policy.quota_source,
            "quota_verified_at": policy.quota_verified_at,
            "quota_contract": policy.quota_contract,
            "max_concurrency": policy.max_concurrency,
            "tokens_per_minute": policy.tokens_per_minute,
            "burst_capacity": policy.burst_capacity,
            "cooldown_seconds": policy.cooldown_seconds,
            "freshness_seconds": policy.freshness_seconds,
        },
        "entitlement": {
            "revision": entitlement.revision,
            "configured_plan": entitlement.configured_plan,
            "is_free": entitlement.is_free,
            "authentication_required": entitlement.authentication_required,
            "usage_terms": entitlement.usage_terms,
            "redistribution_allowed": entitlement.redistribution_allowed,
            "quota_policy": entitlement.quota_policy,
            "history_depth": entitlement.history_depth,
            "venue_coverage": entitlement.venue_coverage,
            "freshness_semantics": entitlement.freshness_semantics,
            "enabled_environments": entitlement.enabled_environments,
            "effective_at": entitlement.effective_at,
            "review_due_at": entitlement.review_due_at,
            "live_probe_status": entitlement.live_probe_status,
        },
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _assert_provider_review_unchanged(
    *,
    source: DataSource | None,
    policy: ProviderPolicy | None,
    entitlement: ProviderEntitlement | None,
    expected_fingerprint: str,
    expected_revision: int,
    expected_account_scope: str,
) -> None:
    if (
        source is None
        or policy is None
        or entitlement is None
        or not source.is_active
        or policy.is_enabled
        or int(entitlement.revision or 1) != expected_revision
        or str(entitlement.live_probe_status or "not_run").strip().lower() != "not_run"
        or _provider_review_fingerprint(source, policy, entitlement) != expected_fingerprint
    ):
        raise ETFHoldingsRouteHeldError(
            "VanEck Provider review changed during qualification; positive evidence was not recorded."
        )
    try:
        actual_scope = account_scope_for_provider("vaneck", str(policy.quota_scope or ""))
    except Exception as exc:  # noqa: BLE001 - changed or missing scope fails closed.
        raise ETFHoldingsRouteHeldError(
            "VanEck application-account binding changed during qualification."
        ) from exc
    if actual_scope != expected_account_scope:
        raise ETFHoldingsRouteHeldError(
            "VanEck application-account binding changed during qualification."
        )


async def _lock_and_validate_current_provider_review(
    db: AsyncSession,
    *,
    source_id: int,
    expected_fingerprint: str,
    expected_revision: int,
    expected_account_scope: str,
) -> tuple[DataSource | None, ProviderPolicy | None, ProviderEntitlement | None]:
    """Reload and lock the reviewed contract before writing positive evidence."""

    source = await db.scalar(
        select(DataSource)
        .where(DataSource.id == source_id, DataSource.name == "vaneck")
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    policy = await db.scalar(
        select(ProviderPolicy)
        .where(
            ProviderPolicy.data_source_id == source_id,
            ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    entitlement = await db.scalar(
        select(ProviderEntitlement)
        .where(
            ProviderEntitlement.data_source_id == source_id,
            ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    _assert_provider_review_unchanged(
        source=source,
        policy=policy,
        entitlement=entitlement,
        expected_fingerprint=expected_fingerprint,
        expected_revision=expected_revision,
        expected_account_scope=expected_account_scope,
    )
    return source, policy, entitlement


def _provider_qualification_binder():
    """Resolve only the Provider-owned binder; absent staged support fails closed."""

    from app.services import provider_runtime  # noqa: PLC0415

    binder = getattr(provider_runtime, "bind_vaneck_initial_etf_qualification", None)
    if not callable(binder):
        raise ETFHoldingsRouteHeldError(
            "VanEck first qualification is unavailable until its reviewed Provider scope is staged."
        )
    return binder


async def qualify_vaneck_oih_fund(
    db: AsyncSession,
    *,
    requested_by_user_id: int,
) -> ETFHoldingsBackfillJob:
    """Latch and execute one exact OIH sample through Provider shared admission."""

    require_unbound_etf_holdings_context("VanEck initial qualification")
    binder = _provider_qualification_binder()
    operation_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    lock_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    attempt: ETFHoldingsBackfillJob | None = None
    try:
        if lock_db.get_bind().dialect.name != "postgresql":
            raise ETFHoldingsRouteHeldError(
                "cross-process VanEck qualification serialization requires PostgreSQL"
            )
        profile = (
            await operation_db.execute(
                select(ETFProfile)
                .join(Instrument, Instrument.id == ETFProfile.instrument_id)
                .options(
                    selectinload(ETFProfile.instrument).selectinload(Instrument.instrument_type)
                )
                .where(Instrument.symbol == "OIH")
            )
        ).scalar_one_or_none()
        instrument = await _resolve_canonical_fund_instrument(operation_db, "OIH")
        profile_aliases = (
            profile.provider_aliases
            if profile and isinstance(profile.provider_aliases, dict)
            else {}
        )
        if (
            profile is None
            or instrument is None
            or profile.instrument_id != instrument.id
            or profile.instrument is None
            or profile.adapter_key != "vaneck"
            or str(profile_aliases.get("product_slug") or "") != VANECK_OIH_PRODUCT_SLUG
            or str(profile_aliases.get("holdings_adapter") or "").lower() != "vaneck"
        ):
            raise ETFHoldingsRouteHeldError(
                "VanEck initial qualification requires the existing canonical OIH profile and curated route."
            )

        source = await operation_db.scalar(select(DataSource).where(DataSource.name == "vaneck"))
        if source is None or not source.is_active:
            raise ETFHoldingsRouteHeldError(
                "VanEck source must be explicitly provisioned before qualification."
            )
        policy = await operation_db.scalar(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == source.id,
                ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        entitlement = await operation_db.scalar(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == source.id,
                ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
            )
        )
        if policy is None or entitlement is None:
            raise ETFHoldingsRouteHeldError(
                "Reviewed VanEck policy and entitlement rows are required."
            )
        if policy.is_enabled:
            raise ETFHoldingsRouteHeldError(
                "Initial qualification requires the ordinary VanEck policy to remain disabled."
            )
        if str(entitlement.live_probe_status or "not_run").strip().lower() != "not_run":
            raise ETFHoldingsRouteHeldError(
                "VanEck initial qualification is available only for an unprobed entitlement."
            )
        quota_scope = str(policy.quota_scope or "").strip().lower()
        scopes = settings.PROVIDER_QUOTA_ACCOUNT_SCOPES
        if not _has_explicit_account_scope_mapping("vaneck", quota_scope, scopes or {}):
            raise ETFHoldingsRouteHeldError(
                "VanEck requires an explicit shared application-account mapping."
            )
        try:
            account_scope = account_scope_for_provider("vaneck", quota_scope)
        except Exception as exc:  # noqa: BLE001 - unresolved account scope fails closed.
            raise ETFHoldingsRouteHeldError(
                "VanEck shared application-account scope is unavailable."
            ) from exc
        if not account_scope or account_scope.strip().upper() in {"*", "ALL", "ANY"}:
            raise ETFHoldingsRouteHeldError("VanEck qualification account scope is invalid.")

        await lock_db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _qualification_lock_key(account_scope)},
        )
        existing_jobs = list(
            (
                await operation_db.scalars(
                    select(ETFHoldingsBackfillJob).where(
                        ETFHoldingsBackfillJob.etf_profile_id == profile.id,
                        ETFHoldingsBackfillJob.job_type
                        == VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE,
                    )
                )
            ).all()
        )
        if existing_jobs:
            for existing_job in existing_jobs:
                if existing_job.status == "running":
                    existing_job.status = "interrupted"
                    existing_job.completed_at = datetime.now(UTC)
                    existing_job.failure_reason = (
                        "Prior VanEck OIH qualification was interrupted; replay denied."
                    )
                    extra = dict(existing_job.extra_data or {})
                    extra["qualification_outcome"] = {
                        "status": "not_qualified",
                        "reason": "interrupted_attempt_requires_operator_review",
                    }
                    existing_job.extra_data = extra
            await operation_db.commit()
            raise ETFHoldingsRouteHeldError(
                "OIH VanEck initial qualification is already latched; replay is denied."
            )

        now = datetime.now(UTC)
        deadline_monotonic = time.monotonic() + VANECK_OIH_INITIAL_DEADLINE_SECONDS
        scope = {
            "provider": "vaneck",
            "capability": ProviderCapability.ETF_HOLDINGS.value,
            "operation": VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
            "profile_id": profile.id,
            "instrument_id": instrument.id,
            "provider_symbol": "OIH",
            "product_slug": VANECK_OIH_PRODUCT_SLUG,
            "request_url": VANECK_OIH_INITIAL_URL,
            "allowed_initial_host": "www.vaneck.com",
            "account_scope": account_scope,
            "review_revision": int(entitlement.revision or 1),
            "expires_at": (
                now + timedelta(seconds=VANECK_OIH_INITIAL_DEADLINE_SECONDS)
            ).isoformat(),
            "concurrency": 1,
            "minimum_physical_interval_seconds": VANECK_OIH_INITIAL_MIN_INTERVAL_SECONDS,
            "burst_capacity": 1,
            "max_physical_requests": VANECK_OIH_INITIAL_MAX_PHYSICAL_REQUESTS,
            "deadline_seconds": VANECK_OIH_INITIAL_DEADLINE_SECONDS,
            "max_response_bytes": VANECK_OIH_INITIAL_MAX_BODY_BYTES,
            "automatic_retries": 0,
            "follow_redirects": False,
        }
        scope["provider_review_fingerprint"] = _provider_review_fingerprint(
            source, policy, entitlement
        )
        attempt = ETFHoldingsBackfillJob(
            etf_profile_id=profile.id,
            requested_by_user_id=requested_by_user_id,
            source_provider="vaneck",
            job_type=VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE,
            status="running",
            started_at=now,
            discovered_count=0,
            ingested_count=0,
            skipped_count=0,
            failed_count=0,
            extra_data={
                "qualification_scope": scope,
                "qualification_outcome": {"status": "in_progress"},
                "provider_request_log_ids": [],
            },
        )
        operation_db.add(attempt)
        await operation_db.commit()
        await operation_db.refresh(attempt)

        adapter = __import__(
            "app.services.etf_holdings_adapters", fromlist=["get_holdings_adapter"]
        ).get_holdings_adapter("vaneck")
        if adapter is None:
            raise ETFHoldingsRouteHeldError("VanEck holdings adapter is unavailable.")
        budget = ETFVaneckInitialQualificationBudget(
            expected_url=VANECK_OIH_INITIAL_URL,
            deadline_monotonic=deadline_monotonic,
            max_physical_requests=VANECK_OIH_INITIAL_MAX_PHYSICAL_REQUESTS,
            minimum_interval_seconds=VANECK_OIH_INITIAL_MIN_INTERVAL_SECONDS,
            max_response_bytes=VANECK_OIH_INITIAL_MAX_BODY_BYTES,
        )

        binder_context = binder(
            job_id=attempt.id,
            fund_profile_id=profile.id,
            instrument_id=instrument.id,
            provider_symbol="OIH",
            account_scope=account_scope,
            review_revision=int(entitlement.revision or 1),
            expires_at=datetime.fromisoformat(scope["expires_at"]),
        )
        with binder_context:
            request_log_ids: list[int] = []
            snapshot = await _refresh_adapter_route(
                operation_db,
                profile,
                request_log_ids_out=request_log_ids,
                vaneck_initial_qualification_job_id=attempt.id,
                vaneck_initial_qualification_budget=budget,
            )

        attempt = await operation_db.scalar(
            select(ETFHoldingsBackfillJob)
            .where(ETFHoldingsBackfillJob.id == attempt.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if attempt is None or attempt.status != "running":
            raise ETFHoldingsRouteHeldError(
                "VanEck qualification job changed before positive evidence was recorded."
            )
        persisted_scope = (attempt.extra_data or {}).get("qualification_scope")
        if persisted_scope != scope:
            raise ETFHoldingsRouteHeldError(
                "VanEck qualification scope changed before positive evidence was recorded."
            )
        linked_ids = list((attempt.extra_data or {}).get("provider_request_log_ids") or [])
        if not request_log_ids or linked_ids != request_log_ids:
            raise ETFHoldingsRouteHeldError(
                "VanEck qualification request logs are missing or ambiguously linked."
            )
        await _verify_success_evidence(
            operation_db,
            profile=profile,
            source=source,
            attempt=attempt,
            snapshot=snapshot,
            request_log_ids=request_log_ids,
        )

        # A fetch can outlive the review it began under. Lock the durable rows
        # after fresh reads so they cannot change between validation and commit.
        source, policy, entitlement = await _lock_and_validate_current_provider_review(
            operation_db,
            source_id=source.id,
            expected_fingerprint=scope["provider_review_fingerprint"],
            expected_revision=scope["review_revision"],
            expected_account_scope=account_scope,
        )
        budget.ensure_before_deadline()
        await _record_success(operation_db, profile, snapshot=snapshot)
        entitlement.live_probe_status = "passed"
        entitlement.revision = int(entitlement.revision or 1) + 1
        attempt.status = "completed"
        attempt.completed_at = datetime.now(UTC)
        attempt.discovered_count = 1
        attempt.ingested_count = 1
        extra = dict(attempt.extra_data or {})
        extra["qualification_outcome"] = {
            "status": "passed",
            "qualified_at": attempt.completed_at.isoformat(),
            "snapshot_id": snapshot.id,
            "raw_artifact_id": snapshot.source_artifact_id,
            "request_log_ids": request_log_ids,
        }
        attempt.extra_data = extra
        await operation_db.flush()
        await record_entitlement_revision(
            operation_db,
            entitlement,
            change_reason=f"vaneck_oih_initial_qualification:{attempt.id}",
        )
        await operation_db.commit()
        return attempt
    except asyncio.CancelledError:
        if attempt is not None:
            await operation_db.rollback()
            await _await_shielded_finalizer(
                _finish_failed_qualification(
                    db.bind,
                    attempt_id=attempt.id,
                    status="interrupted",
                    reason="VanEck OIH qualification was cancelled; replay denied.",
                    redirect_location=None,
                )
            )
        raise
    except BaseException as exc:
        if attempt is not None:
            await operation_db.rollback()
            location = getattr(exc, "location", None)
            await _await_shielded_finalizer(
                _finish_failed_qualification(
                    db.bind,
                    attempt_id=attempt.id,
                    status="failed",
                    reason=str(exc) or type(exc).__name__,
                    redirect_location=location,
                )
            )
            result = await operation_db.get(ETFHoldingsBackfillJob, attempt.id)
            if result is not None:
                return result
        if isinstance(exc, Exception):
            raise ETFHoldingsRouteHeldError(str(exc) or "VanEck qualification was held.") from exc
        raise
    finally:
        await lock_db.close()
        await operation_db.close()


async def _verify_success_evidence(
    db: AsyncSession,
    *,
    profile: ETFProfile,
    source: DataSource,
    attempt: ETFHoldingsBackfillJob,
    snapshot: ETFHoldingsSnapshot,
    request_log_ids: list[int],
) -> None:
    if (
        snapshot.etf_profile_id != profile.id
        or snapshot.source_provider != "vaneck"
        or snapshot.source_identifier != VANECK_OIH_PRODUCT_SLUG
        or snapshot.source_url != VANECK_OIH_INITIAL_URL
        or snapshot.source_artifact_id is None
        or snapshot.row_count <= 0
        or snapshot.composition_date is None
        or snapshot.known_at is None
        or snapshot.published_at is not None
        or snapshot.known_at < attempt.started_at
        or snapshot.completeness_status != "complete"
    ):
        raise ETFHoldingsRouteHeldError(
            "VanEck workbook did not produce dated OIH snapshot provenance."
        )
    artifact = await db.get(ETFHoldingsRawArtifact, snapshot.source_artifact_id)
    if (
        artifact is None
        or artifact.etf_profile_id != profile.id
        or artifact.data_source_id != source.id
        or artifact.source_kind != snapshot.provenance
        or artifact.source_url != VANECK_OIH_INITIAL_URL
        or artifact.source_identifier != VANECK_OIH_PRODUCT_SLUG
        or artifact.fetched_at < attempt.started_at
        or not isinstance(artifact.payload_json, dict)
        or not isinstance(artifact.payload_json.get("raw_workbook_base64"), str)
        or artifact.content_hash != _hash_payload(artifact.payload_json)
    ):
        raise ETFHoldingsRouteHeldError("VanEck raw workbook artifact is incomplete or mismatched.")
    raw = artifact.payload_json["raw_workbook_base64"]
    try:
        import base64  # noqa: PLC0415

        raw_bytes = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001 - invalid retained bytes cannot qualify.
        raise ETFHoldingsRouteHeldError("VanEck raw workbook bytes are invalid.") from exc
    raw_digest = hashlib.sha256(raw_bytes).hexdigest()
    if (
        len(raw_bytes) == 0
        or len(raw_bytes) > VANECK_OIH_INITIAL_MAX_BODY_BYTES
        or raw_digest != artifact.payload_json.get("raw_workbook_sha256")
        or raw_digest != (artifact.legal_metadata or {}).get("raw_workbook_sha256")
        or len(raw_bytes) != artifact.payload_json.get("raw_workbook_bytes")
        or artifact.legal_metadata is None
        or (artifact.legal_metadata or {}).get("initial_qualification") is not True
    ):
        raise ETFHoldingsRouteHeldError("VanEck raw workbook hash/size evidence does not match.")
    logs = list(
        (
            await db.scalars(
                select(ProviderRequestLog).where(ProviderRequestLog.id.in_(request_log_ids))
            )
        ).all()
    )
    if len(logs) != len(request_log_ids) or not 1 <= len(logs) <= 3:
        raise ETFHoldingsRouteHeldError("VanEck qualification request log count is invalid.")
    for log in logs:
        if (
            log.data_source_id != source.id
            or log.capability != ProviderCapability.ETF_HOLDINGS
            or log.operation != VANECK_OIH_INITIAL_QUALIFICATION_OPERATION
            or log.instrument_id != profile.instrument_id
            or (log.provider_symbol or "").strip().upper() != "OIH"
            or not log.success
            or log.completed_at is None
            or log.http_requests != 1
            or log.settled_usage_units is None
            or log.error_type is not None
        ):
            raise ETFHoldingsRouteHeldError(
                "VanEck Provider request evidence is not successfully settled."
            )


async def _finish_failed_qualification(
    bind,
    *,
    attempt_id: int,
    status: str,
    reason: str,
    redirect_location: str | None,
) -> None:
    from app.providers.errors import bounded_redact_provider_message  # noqa: PLC0415

    session = AsyncSession(bind=bind, expire_on_commit=False)
    try:
        job = await session.get(ETFHoldingsBackfillJob, attempt_id)
        if job is not None and job.status == "running":
            job.status = status
            job.failure_reason = bounded_redact_provider_message(reason, max_length=1000)
            job.completed_at = datetime.now(UTC)
            extra = dict(job.extra_data or {})
            extra["qualification_outcome"] = {
                "status": "not_qualified",
                "reason": bounded_redact_provider_message(reason, max_length=1000),
            }
            if redirect_location:
                extra["unreviewed_redirect_location"] = bounded_redact_provider_message(
                    redirect_location, max_length=2000
                )
            job.extra_data = extra
        await session.commit()
    finally:
        await session.close()


async def _await_shielded_finalizer(coro) -> None:
    task = asyncio.create_task(coro)
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    task.result()
