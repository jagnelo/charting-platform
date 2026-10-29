"""One-shot, administrator-only VanEck OIH issuer qualification."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.data_source import DataSource
from app.models.etf_holdings import (
    ETFHoldingsBackfillFiling,
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
from app.services.etf_holdings import ETF_HOLDINGS_INTERNAL_PROVIDER, _hash_payload
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
from app.services.provider_runtime import (
    provider_entitlement_admission,
    record_entitlement_revision,
)

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
VANECK_PRETRANSPORT_FAILURE_REASON = (
    "No currently-supported providers available for " "etf_holdings/fetch_etf_holdings_latest"
)


async def _load_attempt_for_response(
    db: AsyncSession, attempt_id: int
) -> ETFHoldingsBackfillJob | None:
    """Reload the durable attempt with every response relationship loaded.

    The qualification runs in its own session so its job/log settlement can
    survive request rollback.  The route serializes the returned job only
    after this service closes that session; load ``filings`` here so response
    validation never tries lazy IO on a detached ORM instance.
    """

    result = await db.execute(
        select(ETFHoldingsBackfillJob)
        .options(selectinload(ETFHoldingsBackfillJob.filings))
        .where(ETFHoldingsBackfillJob.id == attempt_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


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


def _quota_activity_exists_since_attempt(
    *, account_scope: str, started_at: datetime, completed_at: datetime
) -> bool:
    """Read an existing quota ledger without creating or upgrading its schema."""

    from app.services import provider_quota_coordinator as quota  # noqa: PLC0415

    configured = make_url(quota._engine_url())
    engine = None
    try:
        if configured.get_backend_name() == "sqlite":
            database = configured.database or ""
            if (
                not database
                or database == ":memory:"
                or database.startswith("file:")
                or bool(configured.query)
            ):
                raise ETFHoldingsRouteHeldError(
                    "The shared quota ledger URI is unsupported for read-only recovery."
                )
            database_path = Path(database).expanduser().resolve()
            if not database_path.is_file():
                raise ETFHoldingsRouteHeldError(
                    "The existing persistent shared quota ledger is unavailable; recovery is denied."
                )
            readonly_url = URL.create(
                "sqlite+pysqlite",
                database=f"file:{quote(str(database_path), safe='/')}?mode=ro",
                query={"uri": "true"},
            )
            engine = create_engine(readonly_url, connect_args={"timeout": 5}, poolclass=NullPool)
            sqlite = True
        elif configured.get_backend_name() == "postgresql":
            engine = create_engine(configured, poolclass=NullPool, hide_parameters=True)
            sqlite = False
        else:
            raise ETFHoldingsRouteHeldError(
                "The shared quota ledger backend cannot be verified read-only."
            )
        with engine.connect() as connection:
            if sqlite:
                connection.exec_driver_sql("PRAGMA query_only = ON")
                if connection.exec_driver_sql("PRAGMA query_only").scalar_one() != 1:
                    raise ETFHoldingsRouteHeldError(
                        "The shared quota ledger did not enter read-only mode."
                    )
            else:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
                    raise ETFHoldingsRouteHeldError(
                        "The shared quota ledger did not enter read-only mode."
                    )
            tables = set(inspect(connection).get_table_names())
            required_tables = {
                quota._reservations.name,
                quota._live_receipts.name,
            }
            if not required_tables.issubset(tables):
                raise ETFHoldingsRouteHeldError(
                    "The shared quota ledger schema is incomplete; recovery is denied."
                )
            # A path that exists but contains a newly initialized empty schema
            # is not the persistent usage history that governed the failed
            # attempt. Require existing reservation history before interpreting
            # the absence of matching attempt rows as evidence.
            ledger_history = connection.execute(
                select(func.count()).select_from(quota._reservations)
            ).scalar_one()
            if int(ledger_history or 0) == 0:
                raise ETFHoldingsRouteHeldError(
                    "The shared quota ledger has no prior history to verify recovery."
                )
            reservation = connection.execute(
                select(quota._reservations.c.id)
                .where(
                    quota._reservations.c.provider_name == "vaneck",
                    quota._reservations.c.account_scope == account_scope,
                    quota._reservations.c.operation == VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
                    quota._reservations.c.created_at >= started_at,
                    quota._reservations.c.created_at <= completed_at,
                )
                .limit(1)
            ).first()
            receipts = connection.execute(
                select(
                    quota._live_receipts.c.reservation_id,
                    quota._live_receipts.c.provider_name,
                    quota._live_receipts.c.operation,
                    quota._live_receipts.c.created_at,
                ).where(
                    quota._live_receipts.c.created_at >= started_at,
                    quota._live_receipts.c.created_at <= completed_at,
                )
            ).all()
            if reservation is not None:
                return True
            for receipt in receipts:
                receipt_reservations = connection.execute(
                    select(
                        quota._reservations.c.provider_name,
                        quota._reservations.c.account_scope,
                        quota._reservations.c.operation,
                        quota._reservations.c.created_at,
                    ).where(quota._reservations.c.reservation_id == receipt.reservation_id)
                ).all()
                if not receipt_reservations:
                    return True
                providers = {row.provider_name for row in receipt_reservations}
                operations = {row.operation for row in receipt_reservations}
                scopes = {row.account_scope for row in receipt_reservations}
                if (
                    providers != {receipt.provider_name}
                    or operations != {receipt.operation}
                    or len(scopes) != 1
                    or any(row.created_at > receipt.created_at for row in receipt_reservations)
                ):
                    # Orphaned, cross-operation, cross-provider, or future-dated
                    # reservation linkage is ambiguous evidence.
                    return True
                if account_scope in scopes:
                    return True
                # Ignore a receipt only when its complete reservation lineage
                # proves that it belongs to another account scope. usage_scope
                # is a separate receipt field and is not an account identifier.
            return False
    except ETFHoldingsRouteHeldError:
        raise
    except Exception as exc:  # noqa: BLE001 - ledger read failures fail closed.
        raise ETFHoldingsRouteHeldError(
            "The existing shared quota ledger could not be verified read-only; recovery is denied."
        ) from exc
    finally:
        if engine is not None:
            engine.dispose()


async def _validate_pretransport_predecessor(
    db: AsyncSession,
    *,
    predecessor_job_id: int,
    profile: ETFProfile,
    source: DataSource,
    entitlement: ProviderEntitlement,
    account_scope: str,
    current_fingerprint: str,
) -> tuple[ETFHoldingsBackfillJob, list[dict[str, object]]]:
    predecessor = await db.scalar(
        select(ETFHoldingsBackfillJob)
        .where(ETFHoldingsBackfillJob.id == predecessor_job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        predecessor is None
        or predecessor.etf_profile_id != profile.id
        or predecessor.source_provider != "vaneck"
        or predecessor.job_type != VANECK_OIH_INITIAL_QUALIFICATION_JOB_TYPE
        or predecessor.status != "failed"
        or predecessor.completed_at is None
        or predecessor.failure_reason != VANECK_PRETRANSPORT_FAILURE_REASON
    ):
        raise ETFHoldingsRouteHeldError(
            "Only the exact failed pretransport OIH qualification can be recovered."
        )

    extra = predecessor.extra_data if isinstance(predecessor.extra_data, dict) else {}
    scope = extra.get("qualification_scope")
    outcome = extra.get("qualification_outcome")
    if (
        not isinstance(scope, dict)
        or scope.get("provider") != "vaneck"
        or scope.get("capability") != ProviderCapability.ETF_HOLDINGS.value
        or scope.get("operation") != VANECK_OIH_INITIAL_QUALIFICATION_OPERATION
        or scope.get("profile_id") != profile.id
        or scope.get("instrument_id") != profile.instrument_id
        or scope.get("provider_symbol") != "OIH"
        or scope.get("product_slug") != VANECK_OIH_PRODUCT_SLUG
        or scope.get("request_url") != VANECK_OIH_INITIAL_URL
        or scope.get("account_scope") != account_scope
        or scope.get("concurrency") != 1
        or scope.get("minimum_physical_interval_seconds") != VANECK_OIH_INITIAL_MIN_INTERVAL_SECONDS
        or scope.get("burst_capacity") != 1
        or scope.get("max_physical_requests") != VANECK_OIH_INITIAL_MAX_PHYSICAL_REQUESTS
        or scope.get("deadline_seconds") != VANECK_OIH_INITIAL_DEADLINE_SECONDS
        or scope.get("max_response_bytes") != VANECK_OIH_INITIAL_MAX_BODY_BYTES
        or scope.get("automatic_retries") != 0
        or scope.get("follow_redirects") is not False
        or isinstance(scope.get("review_revision"), bool)
        or not isinstance(scope.get("review_revision"), int)
        or scope["review_revision"] >= int(entitlement.revision or 1)
        or not isinstance(scope.get("provider_review_fingerprint"), str)
        or scope["provider_review_fingerprint"] == current_fingerprint
        or not isinstance(outcome, dict)
        or outcome.get("status") != "not_qualified"
        or outcome.get("reason") != VANECK_PRETRANSPORT_FAILURE_REASON
        or extra.get("provider_request_log_ids") != []
        or "pretransport_recovery" in extra
        or set(extra)
        != {
            "qualification_scope",
            "qualification_outcome",
            "provider_request_log_ids",
        }
        or set(outcome) != {"status", "reason"}
        or set(scope)
        != {
            "provider",
            "capability",
            "operation",
            "profile_id",
            "instrument_id",
            "provider_symbol",
            "product_slug",
            "request_url",
            "allowed_initial_host",
            "account_scope",
            "review_revision",
            "expires_at",
            "concurrency",
            "minimum_physical_interval_seconds",
            "burst_capacity",
            "max_physical_requests",
            "deadline_seconds",
            "max_response_bytes",
            "automatic_retries",
            "follow_redirects",
            "provider_review_fingerprint",
        }
        or any(
            key in outcome and outcome.get(key) is not None
            for key in ("request_log_ids", "snapshot_id", "raw_artifact_id")
        )
    ):
        raise ETFHoldingsRouteHeldError(
            "The prior qualification lacks exact changed-review pretransport evidence."
        )

    end = predecessor.completed_at
    if predecessor.started_at is None or end < predecessor.started_at or end > datetime.now(UTC):
        raise ETFHoldingsRouteHeldError("The predecessor attempt timing is invalid.")
    if await db.scalar(
        select(func.count(ETFHoldingsBackfillFiling.id)).where(
            ETFHoldingsBackfillFiling.last_job_id == predecessor.id
        )
    ):
        raise ETFHoldingsRouteHeldError(
            "The prior qualification has filing evidence and cannot be recovered."
        )
    if await db.scalar(
        select(func.count(ProviderRequestLog.id)).where(
            ProviderRequestLog.data_source_id == source.id,
            ProviderRequestLog.capability == ProviderCapability.ETF_HOLDINGS,
            ProviderRequestLog.operation == VANECK_OIH_INITIAL_QUALIFICATION_OPERATION,
            ProviderRequestLog.instrument_id == profile.instrument_id,
            ProviderRequestLog.requested_at >= predecessor.started_at,
            ProviderRequestLog.requested_at <= end,
        )
    ):
        raise ETFHoldingsRouteHeldError("Provider request evidence makes recovery ambiguous.")
    raw_artifacts = list(
        (
            await db.scalars(
                select(ETFHoldingsRawArtifact)
                .where(
                    ETFHoldingsRawArtifact.etf_profile_id == profile.id,
                    ETFHoldingsRawArtifact.fetched_at >= predecessor.started_at,
                    ETFHoldingsRawArtifact.fetched_at <= end,
                )
                .order_by(ETFHoldingsRawArtifact.id)
            )
        ).all()
    )
    diagnostic_artifacts: list[dict[str, object]] = []
    if raw_artifacts:
        if len(raw_artifacts) != 1:
            raise ETFHoldingsRouteHeldError("Raw body evidence makes recovery ambiguous.")
        artifact = raw_artifacts[0]
        no_body_payload = {
            "failure_type": "ProviderNoDataError",
            "failure_message": VANECK_PRETRANSPORT_FAILURE_REASON,
            "validation": None,
        }
        no_body_metadata = {
            "provider_request_log_ids": [],
            "request_urls": [],
            "request_attempts": [],
            "failure_type": "ProviderNoDataError",
            "failure_message": VANECK_PRETRANSPORT_FAILURE_REASON,
            "validation": None,
            "evidence_source": "shared_provider_request_log_and_refresh_rejection",
        }
        if (
            artifact.data_source_id != source.id
            or artifact.source_kind != "issuer_adapter_rejected_fetch"
            or artifact.source_url != ""
            or artifact.source_identifier is not None
            or artifact.content_type != "application/json"
            or artifact.content_hash != _hash_payload(no_body_payload)
            or artifact.composition_date is not None
            or artifact.as_of_date is not None
            or artifact.published_at is not None
            or artifact.parser_version != "vaneck"
            or artifact.payload_text is not None
            or artifact.payload_json != no_body_payload
            or artifact.legal_metadata != no_body_metadata
            or artifact.fetched_at < predecessor.started_at
            or artifact.fetched_at > end
        ):
            raise ETFHoldingsRouteHeldError("Raw body evidence makes recovery ambiguous.")
        diagnostic_artifacts.append(
            {"artifact_id": artifact.id, "content_hash": artifact.content_hash}
        )
    if await db.scalar(
        select(func.count(ETFHoldingsSnapshot.id)).where(
            ETFHoldingsSnapshot.etf_profile_id == profile.id,
            ETFHoldingsSnapshot.created_at >= predecessor.started_at,
            ETFHoldingsSnapshot.created_at <= end,
        )
    ):
        raise ETFHoldingsRouteHeldError("Snapshot evidence makes recovery ambiguous.")
    try:
        quota_activity = await asyncio.to_thread(
            _quota_activity_exists_since_attempt,
            account_scope=account_scope,
            started_at=predecessor.started_at,
            completed_at=end,
        )
    except Exception as exc:  # noqa: BLE001 - unverified ledger cannot authorize recovery.
        raise ETFHoldingsRouteHeldError(
            "The existing shared quota ledger could not be verified read-only; recovery is denied."
        ) from exc
    if quota_activity:
        raise ETFHoldingsRouteHeldError("Shared quota evidence makes recovery ambiguous.")
    return predecessor, diagnostic_artifacts


async def _qualify_vaneck_oih_fund(
    db: AsyncSession,
    *,
    requested_by_user_id: int,
    recovery_attestation: dict[str, object] | None = None,
) -> ETFHoldingsBackfillJob:
    """Latch and execute one exact OIH sample through Provider shared admission."""

    require_unbound_etf_holdings_context("VanEck initial qualification")
    binder = _provider_qualification_binder()
    operation_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    lock_db = AsyncSession(bind=db.bind, expire_on_commit=False)
    attempt: ETFHoldingsBackfillJob | None = None
    attempt_id: int | None = None
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
        if recovery_attestation is not None:
            # Refresh the committed review after serialization; the earlier
            # request-session identity map is not evidence of current review.
            source = await operation_db.scalar(
                select(DataSource)
                .where(DataSource.id == source.id, DataSource.name == "vaneck")
                .execution_options(populate_existing=True)
            )
            if source is None or not source.is_active:
                raise ETFHoldingsRouteHeldError("The reviewed VanEck source is no longer active.")
            policy = await operation_db.scalar(
                select(ProviderPolicy)
                .where(
                    ProviderPolicy.data_source_id == source.id,
                    ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
                )
                .execution_options(populate_existing=True)
            )
            entitlement = await operation_db.scalar(
                select(ProviderEntitlement)
                .where(
                    ProviderEntitlement.data_source_id == source.id,
                    ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
                )
                .execution_options(populate_existing=True)
            )
            if (
                policy is None
                or entitlement is None
                or policy.is_enabled
                or str(entitlement.live_probe_status or "not_run").strip().lower() != "not_run"
            ):
                raise ETFHoldingsRouteHeldError(
                    "Current disabled/not_run VanEck review is required for recovery."
                )
            admission = provider_entitlement_admission(
                entitlement,
                provider_name="vaneck",
                capability=ProviderCapability.ETF_HOLDINGS,
            )
            if not admission.get("allowed"):
                raise ETFHoldingsRouteHeldError(
                    "The current VanEck entitlement does not pass shared free-plan admission."
                )
            fresh_scope = account_scope_for_provider("vaneck", str(policy.quota_scope or ""))
            if fresh_scope != account_scope:
                raise ETFHoldingsRouteHeldError(
                    "VanEck account binding changed while recovery was being serialized."
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
        recovery_predecessor = None
        if recovery_attestation is not None:
            if len(existing_jobs) != 1 or existing_jobs[0].id != recovery_attestation.get(
                "predecessor_job_id"
            ):
                raise ETFHoldingsRouteHeldError(
                    "Recovery requires the sole original OIH attempt and permits one successor."
                )
            fingerprint = _provider_review_fingerprint(source, policy, entitlement)
            recovery_predecessor, diagnostic_artifacts = await _validate_pretransport_predecessor(
                operation_db,
                predecessor_job_id=int(recovery_attestation["predecessor_job_id"]),
                profile=profile,
                source=source,
                entitlement=entitlement,
                account_scope=account_scope,
                current_fingerprint=fingerprint,
            )
            recovery_attestation["predecessor_diagnostic_artifacts"] = diagnostic_artifacts
        elif existing_jobs:
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
                **(
                    {
                        "pretransport_recovery": {
                            **recovery_attestation,
                            "predecessor_job_id": recovery_predecessor.id,
                            "created_at": now.isoformat(),
                            "review_revision": int(entitlement.revision or 1),
                            "provider_review_fingerprint": scope["provider_review_fingerprint"],
                        }
                    }
                    if recovery_attestation is not None and recovery_predecessor is not None
                    else {}
                ),
            },
        )
        operation_db.add(attempt)
        await operation_db.flush()
        attempt_id = int(attempt.id)
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
        with binder_context as provider_authority:
            request_log_ids: list[int] = []
            snapshot = await _refresh_adapter_route(
                operation_db,
                profile,
                request_log_ids_out=request_log_ids,
                vaneck_initial_qualification_job_id=attempt.id,
                vaneck_initial_qualification_budget=budget,
                vaneck_initial_qualification_authority=provider_authority,
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
        response_attempt = await _load_attempt_for_response(operation_db, attempt_id)
        if response_attempt is None:
            raise ETFHoldingsRouteHeldError(
                "VanEck qualification completed but its response record could not be reloaded."
            )
        return response_attempt
    except asyncio.CancelledError:
        if attempt is not None and attempt_id is not None:
            await operation_db.rollback()
            await _await_shielded_finalizer(
                _finish_failed_qualification(
                    db.bind,
                    attempt_id=attempt_id,
                    status="interrupted",
                    reason="VanEck OIH qualification was cancelled; replay denied.",
                    redirect_location=None,
                )
            )
        raise
    except BaseException as exc:
        if attempt is not None and attempt_id is not None:
            await operation_db.rollback()
            location = getattr(exc, "location", None)
            await _await_shielded_finalizer(
                _finish_failed_qualification(
                    db.bind,
                    attempt_id=attempt_id,
                    status="failed",
                    reason=str(exc) or type(exc).__name__,
                    redirect_location=location,
                )
            )
            result = await _load_attempt_for_response(operation_db, attempt_id)
            if result is not None:
                return result
        if isinstance(exc, Exception):
            raise ETFHoldingsRouteHeldError(str(exc) or "VanEck qualification was held.") from exc
        raise
    finally:
        await lock_db.close()
        await operation_db.close()


async def qualify_vaneck_oih_fund(
    db: AsyncSession,
    *,
    requested_by_user_id: int,
) -> ETFHoldingsBackfillJob:
    """Run the original one-shot administrator-only qualification."""

    return await _qualify_vaneck_oih_fund(
        db,
        requested_by_user_id=requested_by_user_id,
    )


async def recover_vaneck_oih_fund(
    db: AsyncSession,
    *,
    requested_by_user_id: int,
    predecessor_job_id: int,
    review_evidence_reference: str,
    review_evidence_sha256: str,
    operator_reason: str,
) -> ETFHoldingsBackfillJob:
    """Create the sole audited successor to an exact failed pretransport attempt."""

    return await _qualify_vaneck_oih_fund(
        db,
        requested_by_user_id=requested_by_user_id,
        recovery_attestation={
            "predecessor_job_id": predecessor_job_id,
            "review_evidence_reference": review_evidence_reference,
            "review_evidence_sha256": review_evidence_sha256.lower(),
            "operator_reason": operator_reason,
        },
    )


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
    internal_source_id = await db.scalar(
        select(DataSource.id).where(DataSource.name == ETF_HOLDINGS_INTERNAL_PROVIDER)
    )
    if (
        artifact is None
        or artifact.etf_profile_id != profile.id
        or artifact.data_source_id != snapshot.data_source_id
        or snapshot.data_source_id is None
        or internal_source_id is None
        or artifact.data_source_id != internal_source_id
        or artifact.source_kind != snapshot.provenance
        or artifact.source_url != VANECK_OIH_INITIAL_URL
        or artifact.source_identifier != VANECK_OIH_PRODUCT_SLUG
        or artifact.fetched_at < attempt.started_at
        or not isinstance(artifact.payload_json, dict)
        or not isinstance(artifact.payload_json.get("raw_workbook_base64"), str)
        or artifact.content_hash != _hash_payload(artifact.payload_json)
        or (artifact.legal_metadata or {}).get("source_provider") != "vaneck"
        or (artifact.legal_metadata or {}).get("initial_qualification") is not True
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
