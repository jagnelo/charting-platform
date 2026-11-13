"""
Background data tasks — bulk historical fetches.
"""

import hashlib
import json
import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import MarketRefreshJob
from app.models.ohlcv import TIMEFRAME_SECONDS, OHLCVBar, Timeframe
from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.models.watchlist import Watchlist, WatchlistItem
from app.models.workstation import (
    MarketGroup,
    MarketGroupMember,
    Workspace,
    WorkspaceTab,
    WorkspaceWindow,
)
from app.providers.errors import ProviderNotConfiguredError, bounded_redact_provider_message
from app.services.derived_timeframes import (
    materialize_derived_timeframes,
    refresh_derived_timeframe_if_needed,
)
from app.services.etf_consumer_types import is_placeholder_symbol
from app.services.market_data import fetch_ohlcv
from app.services.market_data_monitoring import build_shadow_report
from app.services.market_refresh_queue import (
    DEPENDENCY_PENDING_ERROR,
    RefreshLeaseLostError,
    _acquire_enqueue_lock,
    claim_refresh_jobs,
    complete_refresh_job,
    enqueue_refresh_job,
    retry_refresh_job,
)
from app.services.market_universe import reconcile_us_universe, record_core_daily_coverage
from app.services.provider_runtime import (
    ProviderNoDataError,
    ProviderQuotaUnknownError,
    bind_explicit_provider_acquisition,
)

logger = logging.getLogger(__name__)


def _configured_native_usage_providers() -> tuple[str, ...]:
    """Return only the explicit operator allowlist for native usage refresh."""

    configured = getattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", [])
    if not settings.PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED or not isinstance(configured, list):
        return ()
    return tuple(
        dict.fromkeys(
            str(provider).strip().lower() for provider in configured if str(provider).strip()
        )
    )


def _native_usage_refresh_succeeded_for_provider(result: dict, provider_name: str) -> bool:
    """Accept one provider's multiple named observations without accepting peers."""

    providers = {
        str(value or "").strip().lower()
        for value in (result.get("providers") or [])
        if str(value or "").strip()
    }
    return result.get("status") == "refreshed" and providers == {provider_name.strip().lower()}


async def _native_operation_baseline_states(
    db,
    provider_name: str,
    *,
    capability: ProviderCapability,
    operation: str,
    now: datetime,
):
    """Read exact operation quota baselines without changing coordinator state."""

    from app.services.provider_quota_coordinator import (
        ProviderQuotaCoordinatorError,
        provider_quota_baseline_status,
    )
    from app.services.provider_runtime import _dimension_applies_to_operation, quota_dimensions

    source = (
        await db.execute(select(DataSource).where(DataSource.name == provider_name))
    ).scalar_one_or_none()
    if source is None:
        return None, "provider_source_missing"
    policy = (
        await db.execute(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == source.id,
                ProviderPolicy.capability == capability,
            )
        )
    ).scalar_one_or_none()
    if policy is None or not policy.is_enabled:
        return None, "provider_operation_not_enabled"
    states = []
    for dimension in quota_dimensions(policy):
        if not _dimension_applies_to_operation(dimension, operation):
            continue
        if str(dimension.get("unit") or "").strip().lower() in {
            "concurrent_requests",
            "concurrency",
        }:
            continue
        try:
            state = provider_quota_baseline_status(
                provider_name=provider_name,
                capability=capability.value,
                policy=policy,
                dimension_name=str(dimension["name"]),
                now=now,
            )
        except ProviderQuotaCoordinatorError:
            return None, "native_quota_baseline_status_unavailable"
        states.append((dimension, state))
    if not states:
        return None, "operation_quota_dimensions_missing"
    return (policy, states), None


async def _native_usage_job_for_operation_baseline(
    db,
    *,
    provider_name: str,
    capability: ProviderCapability,
    operation: str,
    priority: int,
    now: datetime,
) -> tuple[MarketRefreshJob | None, str | None, bool]:
    """Queue one guarded native usage prerequisite for exact unknown pools.

    Returns (job, hold_reason, needed). Known capacity exhaustion and unknown
    or unsupported contracts never enter this path; only exact missing/stale
    baselines reported by the durable coordinator do.
    """

    plan, reason = await _native_operation_baseline_states(
        db,
        provider_name,
        capability=capability,
        operation=operation,
        now=now,
    )
    if plan is None:
        return None, reason, bool(reason)
    _operation_policy, states = plan
    unknown = [(dimension, state) for dimension, state in states if state["status"] == "unknown"]
    if not unknown:
        return None, None, False

    allowlist = _configured_native_usage_providers()
    normalized_provider = provider_name.strip().lower()
    if normalized_provider not in allowlist:
        return None, "native_usage_refresh_not_enabled_for_provider", True

    from app.services.provider_quota_coordinator import (
        ProviderQuotaCoordinatorError,
        provider_quota_baseline_status,
    )
    from app.services.provider_routing import quota_group_for_dimension
    from app.services.provider_runtime import (
        account_usage_reconciled_dimensions,
        policy_allows_account_usage_bootstrap,
        policy_has_known_quota,
        provider_contract_operation_cost_known,
        quota_dimensions,
        resolve_provider_chain,
    )

    with bind_explicit_provider_acquisition(
        request_id=f"native-usage-prerequisite:{normalized_provider}:{capability.value}:{operation}",
        operations=frozenset({(ProviderCapability.ACCOUNT_USAGE, "fetch_account_usage")}),
        provider_names=frozenset({normalized_provider}),
    ):
        usage_chain = await resolve_provider_chain(
            db,
            ProviderCapability.ACCOUNT_USAGE,
            operation="fetch_account_usage",
        )
    usage = next(
        (item for item in usage_chain if item.provider_name == normalized_provider),
        None,
    )
    if usage is None:
        return None, "native_usage_provider_not_resolved", True
    bootstrap_allowed = policy_allows_account_usage_bootstrap(usage.policy, "fetch_account_usage")
    normally_admitted = False
    if not bootstrap_allowed:
        normally_admitted = policy_has_known_quota(usage.policy) and (
            provider_contract_operation_cost_known(
                usage.policy,
                usage.data_source,
                "fetch_account_usage",
            )
        )
    if not bootstrap_allowed and not normally_admitted:
        return None, "native_usage_bootstrap_not_admitted", True

    usage_policy_dimensions = quota_dimensions(usage.policy)
    reconciled = account_usage_reconciled_dimensions(
        usage.policy,
        "fetch_account_usage",
        require_bootstrap=bootstrap_allowed,
    )
    compatible_dimensions: list[dict] = []
    for history_dimension, history_state in unknown:
        name = str(history_dimension["name"])
        if name not in reconciled:
            return None, "native_usage_dimension_not_reconciled", True
        usage_matches = [
            dimension
            for dimension in usage_policy_dimensions
            if str(dimension.get("name") or "") == name
            and str(dimension.get("unit") or "").strip().lower()
            not in {"concurrent_requests", "concurrency"}
        ]
        if len(usage_matches) != 1:
            return None, "native_usage_dimension_contract_mismatch", True
        usage_dimension = usage_matches[0]
        try:
            usage_state = provider_quota_baseline_status(
                provider_name=normalized_provider,
                capability=ProviderCapability.ACCOUNT_USAGE.value,
                policy=usage.policy,
                dimension_name=name,
                now=now,
            )
        except ProviderQuotaCoordinatorError:
            return None, "native_usage_quota_contract_unavailable", True
        # The usage observation is a prerequisite only when both contracts
        # address the very same account pool/window. A similarly named counter
        # with different scope, cap, or reset cannot authorize history.
        if any(
            history_state.get(key) != usage_state.get(key)
            for key in (
                "account_scope",
                "quota_group",
                "unit",
                "limit_units",
                "window_seconds",
                "rolling",
                "window_started_at",
            )
        ):
            return None, "native_usage_dimension_contract_mismatch", True
        if quota_group_for_dimension(
            capability.value, history_dimension
        ) != quota_group_for_dimension(ProviderCapability.ACCOUNT_USAGE.value, usage_dimension):
            return None, "native_usage_dimension_contract_mismatch", True
        compatible_dimensions.append(
            {
                "name": name,
                "window_started_at": history_state["window_started_at"],
                "window_seconds": history_state["window_seconds"],
                "rolling": history_state["rolling"],
            }
        )

    # Rolling windows use a stable duration bucket for deduplication; the
    # coordinator still validates the actual observation timestamp at reserve.
    key_parts = []
    for item in compatible_dimensions:
        if item["rolling"]:
            epoch = int(now.timestamp())
            window_key = epoch // max(1, int(item["window_seconds"]))
        else:
            window_key = item["window_started_at"]
        key_parts.append((item["name"], window_key))
    digest = hashlib.sha256(
        json.dumps([normalized_provider, sorted(key_parts)], separators=(",", ":")).encode()
    ).hexdigest()[:40]
    request_key = f"native-usage:{normalized_provider}:{digest}"
    job = await enqueue_refresh_job(
        db,
        request_key=request_key,
        capability=ProviderCapability.ACCOUNT_USAGE.value,
        priority=priority,
        metadata_payload={
            "provider_account_usage_refresh": {
                "provider_name": normalized_provider,
                "trigger_capability": capability.value,
                "trigger_operation": operation,
                "dimensions": compatible_dimensions,
            }
        },
        now=now,
        preserve_deferred_deadline=True,
    )
    if (
        job.status == "completed"
        and (job.result_summary or {}).get("preparation_status") != "ready"
    ):
        return job, "native_usage_refresh_not_qualified", True
    return job, None, True


async def _native_usage_prerequisite_for_operation(
    db,
    *,
    capability: ProviderCapability,
    operation: str,
    instrument_id: int | None,
    provider_symbol: str,
    priority: int,
    request_id: str,
    now: datetime,
) -> tuple[MarketRefreshJob | None, str | None, bool, dict | None]:
    """Find an admitted native refresh prerequisite without blocking fallbacks.

    An eligible resolver candidate may still be unusable because its native
    usage pool is unknown and account-usage refresh is not admitted. Keep that
    provider's hold, but inspect later exact-chain candidates before holding the
    whole operation. The ordinary executor remains responsible for reserving
    and selecting the provider that actually transports the operation.
    """

    from app.services.provider_runtime import resolve_provider_chain

    with bind_explicit_provider_acquisition(
        request_id=request_id,
        operations=frozenset({(capability, operation)}),
        instrument_id=instrument_id,
        symbol=provider_symbol,
    ):
        chain = await resolve_provider_chain(
            db,
            capability,
            operation=operation,
            instrument_id=instrument_id,
            provider_symbol=provider_symbol,
        )
    held_candidates: list[dict] = []
    for resolved in chain:
        job, reason, needed = await _native_usage_job_for_operation_baseline(
            db,
            provider_name=resolved.provider_name,
            capability=capability,
            operation=operation,
            priority=priority,
            now=now,
        )
        if not needed:
            # Let the existing executor attempt the chain. It has the final,
            # atomic admission decision and will continue after a candidate's
            # current capacity is exhausted without sending an unreserved call.
            return None, None, False, None

        baseline, _baseline_reason = await _native_operation_baseline_states(
            db,
            resolved.provider_name,
            capability=capability,
            operation=operation,
            now=now,
        )
        dimension_names = []
        if baseline is not None:
            _policy, states = baseline
            dimension_names = [
                str(dimension.get("name") or "")
                for dimension, state in states
                if state.get("status") == "unknown" and str(dimension.get("name") or "")
            ]
        context = {
            "provider_name": resolved.provider_name,
            "capability": capability.value,
            "operation": operation,
            "dimension_names": dimension_names,
        }
        if job is not None and not reason:
            # A durable admitted prerequisite is useful work; preserve the
            # normal wait/resume path instead of trying a later source before
            # its pool has been observed.
            return job, None, True, context
        if job is not None and job.status != "completed":
            return job, reason, True, context

        # No admitted refresh can repair this candidate (or its prerequisite
        # completed without qualification). Record it and continue the exact
        # resolver chain so a later verified provider can serve the request.
        held_candidates.append(
            {**context, "reason_code": reason or "native_usage_refresh_not_qualified"}
        )

    if held_candidates:
        first = held_candidates[0]
        return (
            None,
            first["reason_code"],
            True,
            {
                **{key: value for key, value in first.items() if key != "reason_code"},
                "provider_holds": held_candidates,
            },
        )
    return None, None, False, None


async def resume_native_usage_held_identity_jobs(
    db: AsyncSession,
    *,
    provider_name: str,
    now: datetime | None = None,
) -> int:
    """Requeue held identity/profile children after their exact native pool verifies.

    This only revisits durable children whose prior result was a native-usage
    admission hold. It re-resolves the exact logical operation and resumes only
    when the provider whose usage observation triggered this call is currently
    eligible and every one of its quota dimensions has a verified baseline.
    The original provider hold remains in child history for auditability.
    """

    normalized_provider = str(provider_name or "").strip().lower()
    if not normalized_provider:
        return 0
    current = now or datetime.now(UTC)
    reasons = {
        "native_usage_bootstrap_not_admitted",
        "native_usage_provider_not_resolved",
        "native_usage_refresh_not_enabled_for_provider",
    }
    rows = (
        (
            await db.execute(
                select(MarketRefreshJob)
                .where(
                    MarketRefreshJob.capability == ProviderCapability.INSTRUMENT_METADATA.value,
                    MarketRefreshJob.status == "completed",
                    MarketRefreshJob.result_summary["reason_code"].as_string().in_(reasons),
                )
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    resumed = 0
    for job in rows:
        child = deepcopy((job.metadata_payload or {}).get("data_preparation_child") or {})
        if child.get("kind") != "identity_profile":
            continue
        hold = child.get("native_usage_hold")
        if isinstance(hold, dict):
            try:
                capability = ProviderCapability(str(hold.get("capability") or ""))
            except ValueError:
                continue
            operation = str(hold.get("operation") or "")
            dimension_names = {
                str(value).strip()
                for value in (hold.get("dimension_names") or [])
                if str(value).strip()
            }
        else:
            # Recover children held by an older build, before the exact provider
            # and dimension were retained in the child metadata.
            refresh_profile = (
                bool(child.get("refresh_profile")) and child.get("instrument_id") is not None
            )
            capability = (
                ProviderCapability.INSTRUMENT_METADATA
                if refresh_profile
                else ProviderCapability.INSTRUMENT_SEARCH
            )
            operation = "get_instrument_profile" if refresh_profile else "search_instruments"
            dimension_names = set()
        instrument_id = (
            int(child["instrument_id"])
            if capability == ProviderCapability.INSTRUMENT_METADATA
            and child.get("instrument_id") is not None
            else None
        )
        symbol = str(child.get("symbol") or "").strip().upper()
        if not operation or not symbol:
            continue
        with bind_explicit_provider_acquisition(
            request_id=f"native-usage-resume:{job.id}:{normalized_provider}",
            operations=frozenset({(capability, operation)}),
            instrument_id=instrument_id,
            symbol=symbol,
        ):
            from app.services.provider_runtime import resolve_provider_chain

            chain = await resolve_provider_chain(
                db,
                capability,
                operation=operation,
                instrument_id=instrument_id,
                provider_symbol=symbol,
                read_only=True,
            )
        current_provider_verified = False
        for candidate in chain:
            baseline, baseline_reason = await _native_operation_baseline_states(
                db,
                candidate.provider_name,
                capability=capability,
                operation=operation,
                now=current,
            )
            if baseline is None or baseline_reason:
                continue
            _policy, states = baseline
            by_name = {
                str(dimension.get("name") or ""): state
                for dimension, state in states
                if str(dimension.get("name") or "")
            }
            required_dimensions = (
                (dimension_names or set(by_name))
                if candidate.provider_name == normalized_provider
                else set(by_name)
            )
            if not required_dimensions or any(
                by_name.get(name, {}).get("status") != "verified" for name in required_dimensions
            ):
                continue
            if any(state.get("status") != "verified" for state in by_name.values()):
                continue
            if candidate.provider_name == normalized_provider:
                current_provider_verified = True
        if not current_provider_verified:
            continue

        refs = list(child.get("parent_refs") or [])
        if not refs and child.get("parent_job_id") is not None:
            refs = [{"parent_job_id": child["parent_job_id"]}]
        from app.services.data_preparation import (
            _TRACKING_ROLES,
            _aggregate_status,
            _lock_parent_for_update,
        )

        parent_updated = False
        for parent_id in sorted(
            {int(ref.get("parent_job_id") or 0) for ref in refs if ref.get("parent_job_id")}
        ):
            parent = await _lock_parent_for_update(db, parent_id)
            if parent is None:
                continue
            data = deepcopy((parent.metadata_payload or {}).get("data_preparation") or {})
            if data.get("role") not in _TRACKING_ROLES:
                continue
            dependencies = list(data.get("dependencies") or [])
            changed = False
            identity_dependency_ids = {
                str(item.get("dependency_id"))
                for item in dependencies
                if item.get("dataset") == "identity"
                and job.id in [int(value) for value in item.get("job_ids", [])]
            }
            for dependency in dependencies:
                references_job = job.id in [int(value) for value in dependency.get("job_ids", [])]
                waiting_for_identity = (
                    dependency.get("dataset") == "history"
                    and bool(
                        identity_dependency_ids.intersection(
                            str(value) for value in (dependency.get("depends_on") or [])
                        )
                    )
                    and dependency.get("reason_code") in reasons
                )
                if references_job and dependency.get("dataset") in {"identity", "profile"}:
                    dependency.update(
                        {
                            "status": "queued",
                            "reason_code": None,
                            "retry_at": None,
                            "updated_at": current.isoformat(),
                        }
                    )
                    changed = True
                elif waiting_for_identity:
                    dependency.update(
                        {
                            "status": "waiting",
                            "reason_code": "identity_dependency_pending",
                            "retry_at": None,
                            "updated_at": current.isoformat(),
                        }
                    )
                    changed = True
            if changed:
                data["dependencies"] = dependencies
                data["status"] = _aggregate_status(dependencies)
                data["version"] = int(data.get("version") or 1) + 1
                data["last_progress_at"] = current.isoformat()
                parent.metadata_payload = {
                    **deepcopy(parent.metadata_payload or {}),
                    "data_preparation": data,
                }
                parent_updated = True
        if not parent_updated:
            continue
        previous_holds = list(child.get("native_usage_hold_history") or [])
        if isinstance(hold, dict):
            previous_holds.append(deepcopy(hold))
        if previous_holds:
            child["native_usage_hold_history"] = previous_holds
        child.pop("native_usage_hold", None)
        payload = deepcopy(job.metadata_payload or {})
        payload["data_preparation_child"] = child
        job.metadata_payload = payload
        job.status = "queued"
        job.next_attempt_at = current
        job.leased_until = None
        job.lease_token = None
        job.last_error = None
        job.finished_at = None
        job.result_summary = {
            "outcome": "queued",
            "preparation_status": "queued",
            "reason_code": "native_usage_baseline_verified",
            "resumed_at": current.isoformat(),
        }
        resumed += 1
    if resumed:
        await db.flush()
    return resumed


async def _defer_refresh_job_for_native_usage(
    db,
    *,
    job: MarketRefreshJob,
    usage_job: MarketRefreshJob,
    capability: ProviderCapability,
    operation: str,
    now: datetime,
) -> datetime:
    """Persist the exact native prerequisite and wait without fetching source data."""

    preparation = deepcopy((job.metadata_payload or {}).get("data_preparation_child") or {})
    wait_for_job_ids = list(
        dict.fromkeys(
            [
                *(int(value) for value in preparation.get("wait_for_job_ids", [])),
                int(usage_job.id),
            ]
        )
    )
    preparation["wait_for_job_ids"] = wait_for_job_ids
    payload = deepcopy(job.metadata_payload or {})
    payload["data_preparation_child"] = preparation
    job.metadata_payload = payload
    retry_at = now + timedelta(seconds=20)
    usage_retry_at = usage_job.next_attempt_at
    if usage_job.status == "deferred" and usage_retry_at is not None:
        usage_retry_at = (
            usage_retry_at.replace(tzinfo=UTC)
            if usage_retry_at.tzinfo is None
            else usage_retry_at.astimezone(UTC)
        )
        retry_at = max(retry_at, usage_retry_at)
    await retry_refresh_job(
        db,
        job,
        f"waiting for native usage prerequisite {usage_job.id}",
        retry_at=retry_at,
        result_summary={
            "preparation_status": "waiting",
            "reason_code": "native_usage_baseline_refresh_pending",
            "wait_for_job_id": usage_job.id,
            "capability": capability.value,
            "operation": operation,
        },
    )
    return retry_at


async def _run_native_usage_refresh_job(db, request: dict) -> dict:
    """Run the existing native usage service and require current baselines."""

    provider_name = str(request.get("provider_name") or "").strip().lower()
    if not provider_name or provider_name not in _configured_native_usage_providers():
        return {
            "preparation_status": "held",
            "reason_code": "native_usage_refresh_not_enabled_for_provider",
        }
    from app.services.provider_account_usage import refresh_provider_account_usage
    from app.services.provider_runtime import bind_explicit_provider_acquisition

    with bind_explicit_provider_acquisition(
        request_id=f"native-usage-refresh-job:{provider_name}",
        operations=frozenset({(ProviderCapability.ACCOUNT_USAGE, "fetch_account_usage")}),
        provider_names=frozenset({provider_name}),
    ):
        usage_result = await refresh_provider_account_usage(db, provider_name=provider_name)
    if _native_usage_refresh_succeeded_for_provider(usage_result, provider_name):
        await resume_native_usage_held_identity_jobs(db, provider_name=provider_name)
    target_dimensions = {
        str(item.get("name") or "")
        for item in (request.get("dimensions") or [])
        if isinstance(item, dict)
    }
    trigger_capability = ProviderCapability(
        str(request.get("trigger_capability") or ProviderCapability.PRICE_HISTORY.value)
    )
    trigger_operation = str(request.get("trigger_operation") or "fetch_ohlcv")
    states, state_reason = await _native_operation_baseline_states(
        db,
        provider_name,
        capability=trigger_capability,
        operation=trigger_operation,
        now=datetime.now(UTC),
    )
    verified_dimensions: set[str] = set()
    if states is not None:
        _policy, dimension_states = states
        verified_dimensions = {
            str(dimension.get("name") or "")
            for dimension, state in dimension_states
            if str(dimension.get("name") or "") in target_dimensions
            and state.get("status") == "verified"
        }
    baseline_verified = bool(target_dimensions) and verified_dimensions == target_dimensions
    provider_observed = _native_usage_refresh_succeeded_for_provider(usage_result, provider_name)
    return {
        "preparation_status": "ready" if provider_observed and baseline_verified else "held",
        "reason_code": (
            None
            if provider_observed and baseline_verified
            else state_reason or "native_usage_refresh_not_qualified"
        ),
        "dimensions_verified": sorted(verified_dimensions),
    }


def _maintenance_observation_bucket(observed_at: datetime) -> str:
    """Use the same hourly freshness bucket as shared latest-history jobs."""

    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    return observed_at.astimezone(UTC).strftime("%Y-%m-%dT%H")


async def _latest_completed_session_end(db, exchange_id: int, observed_at: datetime):
    """Resolve the latest actually closed regular session from stored calendars."""

    from app.models.exchange import Exchange
    from app.services.exchange_sessions import is_session_complete, resolve_session_window

    exchange = await db.get(Exchange, exchange_id)
    if exchange is None or not exchange.timezone:
        return None
    try:
        local_today = observed_at.astimezone(ZoneInfo(exchange.timezone)).date()
    except ZoneInfoNotFoundError:
        return None
    for days_back in range(15):
        window = await resolve_session_window(
            db, exchange_id, local_today - timedelta(days=days_back)
        )
        if window is not None and is_session_complete(window, now=observed_at):
            return window
    return None


async def _maintenance_history_end_at(
    db,
    *,
    instrument_ids: set[int],
    timeframe: Timeframe,
    observed_at: datetime,
    primary_exchange_ids: dict[int, set[int]],
    publication_end_cache: dict[tuple[int, Timeframe], datetime | None] | None = None,
):
    """Bound maintenance to published session/bar time, not a live wall clock.

    Daily and derived weekly/monthly work advances only after a regular session
    closes. Intraday work advances to its latest completed interval while the
    venue is open. Closed sessions therefore share the previous observation
    and do not create repeated source requests.
    """

    if not instrument_ids or any(not primary_exchange_ids.get(value) for value in instrument_ids):
        return None
    exchange_ids = set().union(*(primary_exchange_ids[value] for value in instrument_ids))
    if not exchange_ids:
        return None
    from app.models.exchange import Exchange
    from app.services.exchange_sessions import resolve_session_window

    cutoffs: list[datetime] = []
    for exchange_id in sorted(exchange_ids):
        cache_key = (exchange_id, timeframe)
        if publication_end_cache is not None and cache_key in publication_end_cache:
            cached_cutoff = publication_end_cache[cache_key]
            if cached_cutoff is None:
                return None
            cutoffs.append(cached_cutoff)
            continue
        exchange = await db.get(Exchange, exchange_id)
        if exchange is None or not exchange.timezone:
            if publication_end_cache is not None:
                publication_end_cache[cache_key] = None
            return None
        try:
            local_today = observed_at.astimezone(ZoneInfo(exchange.timezone)).date()
        except ZoneInfoNotFoundError:
            if publication_end_cache is not None:
                publication_end_cache[cache_key] = None
            return None
        session_today = await resolve_session_window(db, exchange_id, local_today)
        cutoff = None
        interval_seconds = TIMEFRAME_SECONDS.get(timeframe)
        if (
            interval_seconds is not None
            and timeframe not in {Timeframe.D1, Timeframe.W1, Timeframe.MN}
            and session_today is not None
            and session_today.opens_at <= observed_at < session_today.closes_at
        ):
            elapsed = (observed_at - session_today.opens_at).total_seconds()
            completed_intervals = int(elapsed // interval_seconds)
            if completed_intervals > 0:
                cutoff = session_today.opens_at + timedelta(
                    seconds=interval_seconds * (completed_intervals - 1)
                )
        if cutoff is None:
            latest = await _latest_completed_session_end(db, exchange_id, observed_at)
            if latest is None:
                if publication_end_cache is not None:
                    publication_end_cache[cache_key] = None
                return None
            cutoff = latest.closes_at
        cutoff = cutoff.astimezone(UTC)
        if publication_end_cache is not None:
            publication_end_cache[cache_key] = cutoff
        cutoffs.append(cutoff)
    return min(cutoffs)


# Timeframes to refresh nightly (recent bars only, not full re-fetch)
NIGHTLY_REFRESH_TIMEFRAMES: list[Timeframe] = [
    Timeframe.MN,
    Timeframe.W1,
    Timeframe.D1,
    Timeframe.H4,
    Timeframe.H1,
]


async def _get_newest_bar_ts(db, instrument_id: int, tf: Timeframe) -> datetime | None:
    from sqlalchemy import func

    result = await db.execute(
        select(func.max(OHLCVBar.ts)).where(
            OHLCVBar.instrument_id == instrument_id,
            OHLCVBar.timeframe == tf,
            OHLCVBar.is_adjusted.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def fetch_instrument_history(ctx: dict, instrument_id: int) -> dict:
    """Legacy entry-point — delegates to bulk_fetch_instrument."""
    async with AsyncSessionLocal() as db:
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            return {"error": f"Instrument {instrument_id} not found"}

        from app.services.bulk_fetch import bulk_fetch_instrument

        results = await bulk_fetch_instrument(db, instrument, redis=ctx.get("redis"))
        return {"instrument_id": instrument_id, "symbol": instrument.symbol, "results": results}


async def fetch_all_instruments_history(ctx: dict) -> dict:
    """
    Refresh OHLCV data for all active instruments in the DB.
    Intended to be run as a nightly scheduled task.
    Only fetches recent data (not full history) for efficiency.
    """
    async with AsyncSessionLocal() as db:
        instruments = (
            (
                await db.execute(
                    __import__("sqlalchemy", fromlist=["select"])
                    .select(Instrument)
                    .where(Instrument.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )

        logger.info(f"Refreshing data for {len(instruments)} instruments")
        total_bars = 0
        derived_bars = {Timeframe.W1.value: 0, Timeframe.MN.value: 0}

        for instrument in instruments:
            has_daily_history = False
            for tf in NIGHTLY_REFRESH_TIMEFRAMES:
                try:
                    newest = await _get_newest_bar_ts(db, instrument.id, tf)
                    if newest is None:
                        # No data for this TF yet — bulk fetch handles this, skip
                        continue
                    if tf == Timeframe.D1:
                        has_daily_history = True
                    # Small overlap buffer to catch any late-arriving bars
                    start = newest - timedelta(hours=1)
                    bars = await fetch_ohlcv(db, instrument, tf, start, redis=ctx.get("redis"))
                    total_bars += len(bars)
                except Exception as e:
                    logger.error(
                        "Refresh failed %s %s: %s",
                        instrument.symbol,
                        tf.value,
                        bounded_redact_provider_message(e),
                    )

            # Coarse views are derived only from persisted canonical D1 bars;
            # this adds no provider request and cannot fabricate observations.
            if has_daily_history:
                try:
                    derived = await materialize_derived_timeframes(db, instrument.id)
                    for timeframe in (Timeframe.W1.value, Timeframe.MN.value):
                        derived_bars[timeframe] += int(derived.get(timeframe, 0))
                    await db.commit()
                except Exception as exc:  # noqa: BLE001 - continue the nightly refresh safely
                    await db.rollback()
                    logger.error(
                        "Coarse history materialization failed %s: %s",
                        instrument.symbol,
                        bounded_redact_provider_message(exc),
                    )

        return {
            "instruments_refreshed": len(instruments),
            "total_bars": total_bars,
            "derived_bars": derived_bars,
        }


async def enqueue_core_refresh_jobs(ctx: dict) -> dict:
    """Queue catalogue, saved-input and discovered-universe work on the shared planner."""

    return await enqueue_workstation_maintenance(ctx, include_discovered=True)


async def enqueue_workstation_maintenance(ctx: dict, *, include_discovered: bool = False) -> dict:
    """Persist default and user workstation preparation without source I/O.

    Visible API requests retain priority 10, default/core and saved-list work
    uses 50, and the remaining active universe uses 100. All datasets go
    through the shared request planner and existing refresh queue.
    """

    del ctx  # Queue construction is database-only; workers perform provider I/O.
    from pydantic import ValidationError

    from app.schemas.data_preparation import DataEnsureRequest
    from app.services.data_preparation import create_maintenance_data_preparation_request
    from app.services.top_down_taxonomy import seed_top_down_taxonomy
    from app.services.workstation_bootstrap import (
        CORE_WORKSTATION_INSTRUMENTS,
        ensure_core_workstation_identities,
    )
    from app.services.workstation_tool_catalogue import (
        default_maintenance_request_specs,
        maintenance_request_specs,
    )

    scheduled_at = datetime.now(UTC)
    run_date = scheduled_at.date().isoformat()
    observation_bucket = _maintenance_observation_bucket(scheduled_at)
    if settings.E2E_SEED_MARKET_DATA:
        return {"skipped": True, "reason": "controlled fixture mode owns workstation data"}
    async with AsyncSessionLocal() as db:
        # These routines only establish local canonical identities and group
        # membership; they do not query any provider.
        await ensure_core_workstation_identities(db)
        await seed_top_down_taxonomy(db)
        await db.flush()

        default_specs = default_maintenance_request_specs()
        workspace_rows = (
            await db.execute(
                select(
                    Workspace.id,
                    WorkspaceWindow.tool_type,
                    WorkspaceWindow.configuration,
                )
                .join(WorkspaceTab, WorkspaceTab.workspace_id == Workspace.id)
                .join(WorkspaceWindow, WorkspaceWindow.tab_id == WorkspaceTab.id)
            )
        ).all()
        for _workspace_id, tool_type, configuration in workspace_rows:
            default_specs.extend(maintenance_request_specs(tool_type, configuration))

        existing_group_keys = set((await db.execute(select(MarketGroup.stable_key))).scalars())
        default_specs = [
            spec
            for spec in default_specs
            if spec.get("target", {}).get("kind") not in {"market_group", "family"}
            or str(spec["target"].get("group_key") or spec["target"].get("family_key") or "")
            in existing_group_keys
        ]

        referenced_symbols: set[str] = set()
        referenced_group_keys: set[str] = set()
        for spec in default_specs:
            target = spec.get("target") or {}
            if target.get("kind") == "instrument" and target.get("symbol"):
                referenced_symbols.add(str(target["symbol"]).upper())
            if target.get("kind") in {"market_group", "family"}:
                group_key = target.get("group_key") or target.get("family_key")
                if group_key:
                    referenced_group_keys.add(str(group_key))
            analysis = spec.get("analysis") or {}
            if analysis.get("benchmark_symbol"):
                referenced_symbols.add(str(analysis["benchmark_symbol"]).upper())
            for leg in analysis.get("legs") or []:
                if leg.get("symbol"):
                    referenced_symbols.add(str(leg["symbol"]).upper())
        referenced_ids = (
            set(
                (
                    await db.execute(
                        select(Instrument.id).where(
                            Instrument.is_active.is_(True),
                            Instrument.is_synthetic.is_(False),
                            Instrument.symbol.in_(referenced_symbols),
                        )
                    )
                ).scalars()
            )
            if referenced_symbols
            else set()
        )
        symbol_to_id = (
            {
                str(symbol).upper(): int(instrument_id)
                for instrument_id, symbol in (
                    await db.execute(
                        select(Instrument.id, Instrument.symbol).where(
                            Instrument.is_active.is_(True),
                            Instrument.is_synthetic.is_(False),
                            Instrument.symbol.in_(referenced_symbols),
                        )
                    )
                ).all()
            }
            if referenced_symbols
            else {}
        )
        group_to_ids: dict[str, set[int]] = {}
        if referenced_group_keys:
            for group_key, instrument_id in (
                await db.execute(
                    select(MarketGroup.stable_key, MarketGroupMember.instrument_id)
                    .join(MarketGroup, MarketGroup.id == MarketGroupMember.market_group_id)
                    .join(Instrument, Instrument.id == MarketGroupMember.instrument_id)
                    .where(
                        MarketGroup.stable_key.in_(referenced_group_keys),
                        Instrument.is_active.is_(True),
                        Instrument.is_synthetic.is_(False),
                    )
                )
            ).all():
                group_to_ids.setdefault(str(group_key), set()).add(int(instrument_id))
            referenced_ids.update(
                instrument_id for ids in group_to_ids.values() for instrument_id in ids
            )

        # Any symbol retained in a user's saved list is a default-readiness
        # dependency, independent of whether that user currently has a browser.
        saved_instrument_ids = set(
            (
                await db.execute(
                    select(WatchlistItem.instrument_id)
                    .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
                    .join(Instrument, Instrument.id == WatchlistItem.instrument_id)
                    .where(Instrument.is_active.is_(True))
                    .where(Instrument.is_synthetic.is_(False))
                    .distinct()
                )
            ).scalars()
        )
        core_symbols = {symbol.upper() for symbol, _name, _kind in CORE_WORKSTATION_INSTRUMENTS}
        core_instrument_ids = set(
            (
                await db.execute(
                    select(Instrument.id).where(
                        Instrument.is_active.is_(True),
                        Instrument.is_synthetic.is_(False),
                        Instrument.symbol.in_(core_symbols),
                    )
                )
            ).scalars()
        )
        prioritized_ids = saved_instrument_ids | core_instrument_ids | referenced_ids
        for instrument_id in sorted(prioritized_ids):
            default_specs.append(
                {
                    "target": {"kind": "instrument", "instrument_id": instrument_id},
                    "timeframe": "D1",
                    "adjusted": True,
                }
            )

        active_ids = set(
            (
                await db.execute(
                    select(Instrument.id).where(
                        Instrument.is_active.is_(True), Instrument.is_synthetic.is_(False)
                    )
                )
            ).scalars()
        )
        from app.models.listing import InstrumentListing

        primary_exchange_ids: dict[int, set[int]] = {}
        if active_ids:
            for instrument_id, exchange_id in (
                await db.execute(
                    select(InstrumentListing.instrument_id, InstrumentListing.exchange_id).where(
                        InstrumentListing.instrument_id.in_(active_ids),
                        InstrumentListing.is_active.is_(True),
                        InstrumentListing.is_primary.is_(True),
                        InstrumentListing.exchange_id.is_not(None),
                    )
                )
            ).all():
                primary_exchange_ids.setdefault(int(instrument_id), set()).add(int(exchange_id))
        background_ids = active_ids - prioritized_ids
        if include_discovered:
            for instrument_id in sorted(background_ids):
                default_specs.append(
                    {
                        "target": {"kind": "instrument", "instrument_id": instrument_id},
                        "timeframe": "D1",
                        "adjusted": True,
                        "datasets": ["history"],
                        "_priority": "background",
                    }
                )

        queued = {"default": 0, "background": 0}
        seen: set[str] = set()
        publication_end_cache: dict[tuple[int, Timeframe], datetime | None] = {}
        for spec in default_specs:
            priority = str(spec.pop("_priority", "default"))
            target = spec.get("target") or {}
            if (
                target.get("kind") == "market_group"
                and target.get("group_key") not in existing_group_keys
            ):
                continue
            try:
                request = DataEnsureRequest(**spec)
            except (ValidationError, TypeError, ValueError):
                continue
            if request.end_at is None:
                request_instrument_ids: set[int] = set()
                target = spec.get("target") or {}
                if target.get("kind") == "instrument":
                    if target.get("instrument_id"):
                        request_instrument_ids.add(int(target["instrument_id"]))
                    elif target.get("symbol"):
                        symbol_id = symbol_to_id.get(str(target["symbol"]).upper())
                        if symbol_id is not None:
                            request_instrument_ids.add(symbol_id)
                elif target.get("kind") in {"market_group", "family"}:
                    group_key = str(target.get("group_key") or target.get("family_key") or "")
                    request_instrument_ids.update(group_to_ids.get(group_key, set()))
                analysis = spec.get("analysis") or {}
                if analysis.get("benchmark_symbol"):
                    benchmark_id = symbol_to_id.get(str(analysis["benchmark_symbol"]).upper())
                    if benchmark_id is not None:
                        request_instrument_ids.add(benchmark_id)
                for leg in analysis.get("legs") or []:
                    if leg.get("instrument_id"):
                        request_instrument_ids.add(int(leg["instrument_id"]))
                    elif leg.get("symbol"):
                        leg_id = symbol_to_id.get(str(leg["symbol"]).upper())
                        if leg_id is not None:
                            request_instrument_ids.add(leg_id)
                published_end = await _maintenance_history_end_at(
                    db,
                    instrument_ids=request_instrument_ids,
                    timeframe=request.timeframe,
                    observed_at=scheduled_at,
                    primary_exchange_ids=primary_exchange_ids,
                    publication_end_cache=publication_end_cache,
                )
                if published_end is not None:
                    request = request.model_copy(update={"end_at": published_end})
            normalized = request.model_dump(mode="json")
            marker = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
            if marker in seen:
                continue
            seen.add(marker)
            digest = hashlib.sha256(marker.encode("utf-8")).hexdigest()[:24]
            await create_maintenance_data_preparation_request(
                db,
                request=request,
                # Keep parent dedupe aligned with the shared history child's
                # established publication/freshness bucket. A repeated pass
                # in this bucket reuses the parent; a later due observation
                # on the same date can bind fresh child work.
                idempotency_key=(
                    f"workstation:{request.end_at.isoformat()}:{digest}"
                    if request.end_at is not None
                    else f"workstation:{observation_bucket}:{digest}"
                ),
                priority=priority,
                now=scheduled_at,
            )
            queued[priority] += 1
            if len(seen) % 100 == 0:
                await db.commit()
        await db.commit()
        return {
            "queued": sum(queued.values()),
            "default": queued["default"],
            "background": queued["background"],
            "mode": "shared_preparation_queue",
            "run_date": run_date,
        }


def _refresh_queue_batch_limit(limit: int | None = None) -> int:
    """Return a bounded queue batch size for one worker tick."""

    configured = (
        limit
        if limit is not None
        else getattr(settings, "MARKET_DATA_REFRESH_QUEUE_BATCH_SIZE", 100)
    )
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = 100
    return max(1, min(parsed, 500))


def _history_chunk_start(end: datetime, timeframe: Timeframe, bars: int) -> datetime:
    """Choose an inclusive, calendar-aligned request with at most ``bars`` slots."""
    current = end.astimezone(UTC) if end.tzinfo else end.replace(tzinfo=UTC)
    slots = max(1, int(bars))
    if timeframe is Timeframe.MN:
        month_index = current.year * 12 + current.month - 1 - (slots - 1)
        year, month_zero = divmod(month_index, 12)
        return current.replace(
            year=year, month=month_zero + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    if timeframe is Timeframe.Y1:
        return current.replace(
            year=current.year - (slots - 1),
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    if timeframe is Timeframe.W1:
        monday = current.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=current.weekday()
        )
        return monday - timedelta(weeks=slots - 1)
    if timeframe is Timeframe.D1:
        midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight - timedelta(days=slots - 1)
    seconds = TIMEFRAME_SECONDS[timeframe]
    return current - timedelta(seconds=seconds * (slots - 1))


def _older_chunk_priority(
    *,
    current_priority: int,
    range_mode: str,
    useful_start: datetime | None,
    older_chunk_end: datetime,
) -> int:
    """Keep explicit/useful analysis work urgent; schedule excess backfill last."""
    if range_mode == "bounded":
        return current_priority
    if useful_start is not None and older_chunk_end >= useful_start:
        return current_priority
    return 100


async def _local_history_completion(
    db,
    *,
    job,
    instrument,
    timeframe: Timeframe,
    preparation: dict,
) -> dict | None:
    """Complete a no-eligible-provider history plan from canonical local bars.

    No provider is called here. The window is the explicit range, or the same
    default chunk the provider path would have requested. ``ready`` requires
    complete local coverage; ``partial`` reports the covered span and the gaps.
    Only a window with no local bars at all returns None, which keeps the
    original provider-eligibility reason.
    """

    from sqlalchemy import select as _select

    from app.services.market_data import _coverage_calendar
    from app.services.ohlcv_coverage import assess_ohlcv_coverage

    now = datetime.now(UTC)
    # Default end is the latest completed bucket, matching the availability
    # check, so a daily bar stamped at midnight is not reported as a gap.
    end = (
        _optional_datetime(preparation.get("range_end"))
        or _optional_datetime(job.end_at)
        or _history_chunk_start(now, timeframe, 1)
    )
    max_bars = max(1, int(settings.PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS))
    start = _optional_datetime(preparation.get("range_start")) or _history_chunk_start(
        end, timeframe, max_bars
    )
    adjusted = bool(preparation.get("adjusted", True))
    bars = await fetch_ohlcv(
        db,
        instrument,
        timeframe,
        start,
        end=end,
        adjusted=adjusted,
        allow_provider_fetch=False,
    )
    if bars:
        coverage = assess_ohlcv_coverage(
            bars,
            timeframe,
            start,
            end,
            calendar=_coverage_calendar(instrument),
        )
        covered_start = coverage.covered_start
        covered_end = coverage.covered_end
        missing = list(coverage.missing_slices)
        ready = coverage.status.value == "ready"
        bar_count = len(bars)
    else:
        any_local = (
            await db.execute(
                _select(OHLCVBar.id)
                .where(
                    OHLCVBar.instrument_id == instrument.id,
                    OHLCVBar.timeframe == timeframe,
                    OHLCVBar.is_adjusted.is_(adjusted),
                )
                .limit(1)
            )
        ).first()
        if any_local is None:
            return None
        covered_start = covered_end = None
        missing = [(start, end)]
        ready = False
        bar_count = 0
    return {
        "preparation_status": "ready" if ready else "partial",
        "reason_code": None if ready else "history_coverage_partial",
        "instrument_id": instrument.id,
        "timeframe": timeframe.value,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "bars_observed": bar_count,
        "covered_start": covered_start.isoformat() if covered_start else None,
        "covered_end": covered_end.isoformat() if covered_end else None,
        "missing_slices": [
            {"start": gap_start.isoformat(), "end": gap_end.isoformat()}
            for gap_start, gap_end in missing
        ],
        "local_only": True,
        "provider_plan_reason": "no_eligible_history_provider",
        "retry_at": None,
    }


def _history_chunk_data_status(*, bars: list, range_coverage_status: str | None) -> str:
    """Do not turn a zero-output range into useful partial coverage."""
    if not bars:
        return "empty"
    if range_coverage_status is not None and range_coverage_status != "ready":
        return "partial"
    return "ready"


def _provider_no_data_reason(exc: ProviderNoDataError) -> str:
    """Map typed provider exhaustion to a stable, truthful preparation reason."""
    if str(exc).startswith(
        "No currently-supported providers available for price_history/fetch_ohlcv"
    ):
        return "no_eligible_history_provider"
    return "source_returned_no_data"


async def _deepest_admitted_history_start(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    *,
    adjusted: bool,
    end: datetime,
    request_id: str,
    priority: int = 100,
    requested_start: datetime | None = None,
    preparation: dict | None = None,
    excluded_provider_names: set[str] | frozenset[str] = frozenset(),
    required_provider_name: str | None = None,
) -> tuple[datetime | None, str | None, str | None]:
    """Inspect reviewed, currently admitted provider bounds without transport."""
    from app.services.market_data import ohlcv_operation_cost_overrides
    from app.services.provider_runtime import provider_history_bound_start, resolve_provider_chain

    chunk_start = _history_chunk_start(
        end,
        timeframe,
        max(1, int(settings.PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS)),
    )
    with bind_explicit_provider_acquisition(
        request_id=request_id,
        operations=frozenset({(ProviderCapability.PRICE_HISTORY, "fetch_ohlcv")}),
        instrument_id=instrument.id,
        symbol=instrument.symbol,
    ):
        chain = await resolve_provider_chain(
            db,
            ProviderCapability.PRICE_HISTORY,
            instrument_id=instrument.id,
            provider_symbol=instrument.symbol,
            operation=f"fetch_ohlcv:{timeframe.value}",
            operation_cost_overrides=ohlcv_operation_cost_overrides(timeframe, chunk_start, end),
            adjusted=adjusted,
            read_only=True,
        )
    bounds: list[tuple[datetime, str, bool]] = []
    unknown_bound = False
    invalid_bound = False
    excluded = {str(name).strip().lower() for name in excluded_provider_names}
    for resolved in chain:
        if (
            required_provider_name is not None
            and resolved.provider_name.strip().lower() != required_provider_name.strip().lower()
        ):
            continue
        if resolved.provider_name.strip().lower() in excluded:
            continue
        entitlement = resolved.entitlement
        quota_policy = entitlement.quota_policy if entitlement is not None else None
        constraints = (
            quota_policy.get("history_constraints") if isinstance(quota_policy, dict) else None
        )
        declared_constraints = isinstance(constraints, dict)
        earliest = None
        if declared_constraints:
            # Relative provider limits move with wall time. Anchor them when
            # this worker plans the operation, not to the request's captured
            # end timestamp, which may already be stale by the time transport
            # admission rechecks the same limit.
            earliest, _reason = provider_history_bound_start(constraints, now=datetime.now(UTC))
            if (
                earliest is not None
                and requested_start is None
                and (
                    constraints.get("max_lookback_years") is not None
                    or constraints.get("max_lookback_days") is not None
                )
            ):
                # Leave a small in-window margin for the resolver's later
                # admission check and bar-boundary rounding. Fixed vendor
                # earliest dates and explicit caller ranges are unchanged.
                earliest += timedelta(days=1)
            invalid_bound = invalid_bound or earliest is None
        elif (
            requested_start is None
            and resolved.provider_name == "twelve_data"
            and not adjusted
            and timeframe in {Timeframe.D1, Timeframe.W1, Timeframe.MN}
        ):
            witness = await _twelve_data_history_bound_witness(
                db,
                instrument,
                timeframe,
                resolved,
                end=end,
                request_id=request_id,
                priority=priority,
                preparation=preparation if preparation is not None else {},
            )
            if witness is not None:
                earliest = _optional_datetime(witness.get("earliest_start"))
                if earliest is not None and preparation is not None:
                    preparation["history_bound_witness"] = witness
        if earliest is None:
            unknown_bound = True
            if requested_start is None and preparation is not None:
                pending = set(preparation.get("history_depth_unknown_candidates") or [])
                pending.add(resolved.provider_name)
                preparation["history_depth_unknown_candidates"] = sorted(pending)
            if requested_start is not None and not declared_constraints:
                # A concrete caller range is not rejected by another source's
                # shallower floor. This source is tried under a one-request
                # bounded scope; an empty/unsupported response is not a global
                # history boundary.
                bounds.append((requested_start, resolved.provider_name, True))
            continue
        if requested_start is not None and requested_start < earliest:
            continue
        bounds.append((earliest, resolved.provider_name, False))
    if bounds:
        if requested_start is not None:
            earliest, provider_name, unknown_source_floor = bounds[0]
            if unknown_source_floor and preparation is not None:
                preparation["bounded_unknown_depth_provider"] = provider_name
        else:
            earliest, provider_name, _unknown_source_floor = min(
                bounds, key=lambda item: (item[0], item[1])
            )
        return earliest, provider_name, None
    reason = (
        "history_depth_invalid"
        if invalid_bound and not bounds
        else "history_depth_unknown"
        if unknown_bound
        else "no_eligible_history_provider"
    )
    return None, None, reason


async def _twelve_data_history_bound_witness(
    db,
    instrument: Instrument,
    timeframe: Timeframe,
    resolved,
    *,
    end: datetime,
    request_id: str,
    priority: int,
    preparation: dict,
) -> dict | None:
    """Read or acquire one exact Twelve Data symbol/listing history witness."""

    from hashlib import sha256

    from app.services.provider_runtime import (
        bind_explicit_provider_acquisition,
        execute_provider_call,
    )

    usage_job, usage_hold, usage_needed = await _native_usage_job_for_operation_baseline(
        db,
        provider_name="twelve_data",
        capability=ProviderCapability.PRICE_HISTORY,
        operation="get_earliest_timestamp",
        priority=priority,
        now=datetime.now(UTC),
    )
    if usage_needed:
        if usage_job is not None:
            preparation["history_bound_usage_job_id"] = int(usage_job.id)
        if usage_hold:
            preparation["history_bound_usage_hold"] = usage_hold
        return None

    binding_rows = (
        await db.execute(
            select(
                InstrumentProviderSymbol.provider_symbol,
                InstrumentProviderSymbol.provider_exchange_code,
                InstrumentProviderSymbol.effective_at,
                InstrumentListing.id,
                InstrumentListing.currency,
                InstrumentListing.effective_at,
                Exchange.mic,
                Exchange.timezone,
                Instrument.domain_key,
                Instrument.currency,
            )
            .join(DataSource, DataSource.id == InstrumentProviderSymbol.data_source_id)
            .join(
                InstrumentListing,
                (InstrumentListing.instrument_id == InstrumentProviderSymbol.instrument_id)
                & InstrumentListing.is_active.is_(True)
                & InstrumentListing.is_primary.is_(True),
            )
            .join(Exchange, Exchange.id == InstrumentListing.exchange_id)
            .join(Instrument, Instrument.id == InstrumentProviderSymbol.instrument_id)
            .where(
                InstrumentProviderSymbol.instrument_id == instrument.id,
                InstrumentProviderSymbol.data_source_id == resolved.data_source.id,
                InstrumentProviderSymbol.is_active.is_(True),
                InstrumentProviderSymbol.is_primary.is_(True),
                DataSource.name == "twelve_data",
            )
        )
    ).all()
    if len(binding_rows) != 1:
        return None
    (
        source_symbol,
        source_mic,
        binding_effective_at,
        listing_id,
        listing_currency,
        listing_effective_at,
        listing_mic,
        exchange_timezone,
        domain_key,
        instrument_currency,
    ) = binding_rows[0]
    mic = str(listing_mic or "").strip().upper()
    currency = str(instrument_currency or "").strip().upper()
    if (
        not source_symbol
        or not mic
        or str(source_mic or "").strip().upper() != mic
        or not currency
        or str(listing_currency or "").strip().upper() != currency
        or not exchange_timezone
        or not domain_key
    ):
        holds = dict(preparation.get("history_depth_unknown_holds") or {})
        holds["twelve_data"] = "verified_symbol_listing_scope_unavailable"
        preparation["history_depth_unknown_holds"] = holds
        return None
    scope = {
        "version": 1,
        "provider_name": "twelve_data",
        "data_source_id": resolved.data_source.id,
        "instrument_id": instrument.id,
        "domain_key": domain_key,
        "canonical_symbol": instrument.symbol.strip().upper(),
        "provider_symbol": str(source_symbol).strip().upper(),
        "listing_id": listing_id,
        "mic": mic,
        "currency": currency,
        "timeframe": timeframe.value,
        "adjusted": False,
        "adjustment_basis": "raw",
        "feed_scope": "twelve_data:time_series",
        "session": "regular",
        "entitlement_revision": resolved.entitlement.revision,
    }
    scope_key = sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    witnesses = preparation.get("history_bound_witnesses")
    if isinstance(witnesses, dict):
        cached = witnesses.get(scope_key)
        if isinstance(cached, dict):
            try:
                stale_after = _optional_datetime(cached.get("stale_after"))
                if (
                    all(cached.get(key) == value for key, value in scope.items())
                    and _optional_datetime(cached.get("observed_at")) is not None
                    and stale_after is not None
                    and stale_after > datetime.now(UTC)
                    and _optional_datetime(cached.get("earliest_start")) is not None
                ):
                    return cached
            except (TypeError, ValueError):
                pass

    with bind_explicit_provider_acquisition(
        request_id=request_id,
        operations=frozenset({(ProviderCapability.PRICE_HISTORY, "get_earliest_timestamp")}),
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        provider_names=frozenset({"twelve_data"}),
    ):
        execution = await execute_provider_call(
            db,
            ProviderCapability.PRICE_HISTORY,
            "get_earliest_timestamp",
            instrument_id=instrument.id,
            provider_symbol=instrument.symbol,
            usage_identity=str(source_symbol).strip().upper(),
            provider_name="twelve_data",
            operation_cost_overrides={"twelve_data": 1},
            adjusted=False,
            invoke=lambda provider, _symbol: provider.get_earliest_timestamp(
                str(source_symbol).strip().upper(),
                timeframe,
                mic_code=mic,
                exchange_timezone=str(exchange_timezone),
            ),
        )
    earliest = execution.result
    if not isinstance(earliest, datetime):
        return None
    earliest = _optional_datetime(earliest)
    if earliest is None or earliest > _optional_datetime(end):
        return None
    # These columns carry lifecycle start evidence (for example the listing
    # IPO date), whereas ``known_at`` is only when we learned about the row.
    # Never use first-observed timestamps to invent an instrument history floor.
    effective_dates = [
        _optional_datetime(value)
        for value in (binding_effective_at, listing_effective_at)
        if isinstance(value, datetime)
    ]
    effective_dates = [value for value in effective_dates if value is not None]
    if effective_dates:
        earliest = max(earliest, *effective_dates)
    if earliest > _optional_datetime(end):
        return None
    observed_at = datetime.now(UTC)
    witness = {
        **scope,
        "earliest_start": earliest.isoformat(),
        "observed_at": observed_at.isoformat(),
        "stale_after": (observed_at + timedelta(days=30)).isoformat(),
        "source_operation": "get_earliest_timestamp",
        "source_entitlement_revision": resolved.entitlement.revision,
        "source_response_field": "unix_time",
    }
    witnesses = dict(witnesses) if isinstance(witnesses, dict) else {}
    witnesses[scope_key] = witness
    preparation["history_bound_witnesses"] = witnesses
    return witness


def _optional_datetime(value) -> datetime | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


async def _history_chunk_plan(
    db,
    job,
    instrument,
    timeframe,
    preparation,
    *,
    excluded_provider_names: set[str] | frozenset[str] = frozenset(),
):
    now = datetime.now(UTC)
    requested_end = _optional_datetime(preparation.get("range_end")) or job.end_at or now
    max_bars = max(1, int(settings.PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS))
    requested_start = _optional_datetime(preparation.get("range_start"))
    deepest_start = requested_start
    source_provider = preparation.get("source_provider")
    if deepest_start is None or source_provider is None:
        admitted_start, source_provider, reason = await _deepest_admitted_history_start(
            db,
            instrument,
            timeframe,
            adjusted=bool(preparation.get("adjusted", True)),
            end=requested_end,
            request_id=f"data-preparation-plan:{job.id}",
            priority=int(getattr(job, "priority", 100)),
            requested_start=requested_start,
            preparation=preparation,
            excluded_provider_names=excluded_provider_names,
            required_provider_name=source_provider,
        )
        if admitted_start is None:
            if preparation.get("history_bound_usage_job_id"):
                return None, None, None, None, None, None
            return None, None, None, None, None, reason
        if requested_start is not None and requested_start < admitted_start:
            return (
                None,
                None,
                requested_start,
                requested_end,
                source_provider,
                "requested_history_outside_admitted_depth",
            )
        analysis_required_start = _optional_datetime(preparation.get("analysis_required_start"))
        preparation["analysis_requirement_unmet"] = (
            requested_start is None
            and analysis_required_start is not None
            and analysis_required_start < admitted_start
        )
        deepest_start = requested_start or admitted_start
        preparation["source_provider"] = source_provider
    if preparation.get("chunk"):
        chunk_start = _optional_datetime(job.start_at)
        chunk_end = _optional_datetime(job.end_at)
    else:
        chunk_start = max(deepest_start, _history_chunk_start(requested_end, timeframe, max_bars))
        chunk_end = requested_end
        preparation["selection_start"] = chunk_start.isoformat()
    if chunk_start is None or chunk_end is None or chunk_end < chunk_start:
        return None, None, deepest_start, requested_end, source_provider, "invalid_history_range"
    return chunk_start, chunk_end, deepest_start, requested_end, source_provider, None


async def _history_chunk_plan_with_native_admission(
    db,
    job,
    instrument,
    timeframe,
    preparation,
    *,
    priority: int,
    excluded_provider_names: set[str] | frozenset[str] = frozenset(),
):
    """Prefer the deepest provider whose native quota can actually be admitted.

    The first unpinned chunk may fall back to another exact resolver candidate
    when the deepest candidate's baseline is unknown and its normal usage
    prerequisite is unavailable. Once a source is pinned (including a
    continuation chunk), hold on that source rather than mixing lineages.
    """

    pinned_source = bool(preparation.get("source_provider") or preparation.get("chunk"))
    excluded_provider_names = set(excluded_provider_names)
    last_native_hold: str | None = None
    while True:
        candidate_preparation = deepcopy(preparation)
        if not pinned_source:
            candidate_preparation.pop("source_provider", None)
        plan = await _history_chunk_plan(
            db,
            job,
            instrument,
            timeframe,
            candidate_preparation,
            excluded_provider_names=excluded_provider_names,
        )
        plan_reason = plan[5]
        if plan_reason:
            return plan, candidate_preparation, None, None, last_native_hold

        history_usage_job_id = candidate_preparation.get("history_bound_usage_job_id")
        if history_usage_job_id:
            history_usage_job = await db.get(MarketRefreshJob, int(history_usage_job_id))
            if history_usage_job is None:
                return plan, candidate_preparation, None, "history_bound_usage_job_missing", None
            if history_usage_job.status != "completed":
                candidate_preparation.pop("source_provider", None)
                return plan, candidate_preparation, history_usage_job, None, None
            candidate_preparation.pop("history_bound_usage_job_id", None)
            if (history_usage_job.result_summary or {}).get("preparation_status") != "ready":
                return (
                    plan,
                    candidate_preparation,
                    None,
                    None,
                    "history_bound_usage_refresh_not_qualified",
                )

        source_provider = plan[4]
        if not source_provider:
            return plan, candidate_preparation, None, None, last_native_hold

        usage_job, usage_hold, usage_needed = await _native_usage_job_for_operation_baseline(
            db,
            provider_name=source_provider,
            capability=ProviderCapability.PRICE_HISTORY,
            operation="fetch_ohlcv",
            priority=priority,
            now=datetime.now(UTC),
        )
        if usage_needed and usage_hold and not pinned_source:
            excluded_provider_names.add(source_provider)
            last_native_hold = usage_hold
            continue
        return plan, candidate_preparation, usage_job, usage_hold, None


def _is_pretransport_history_quota_denial(exc: Exception, timeframe: Timeframe) -> bool:
    """Recognize only the runtime's typed no-reservation/no-transport outcome."""

    from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError

    prefix = (
        "durable provider quota admission denied for "
        f"price_history/fetch_ohlcv:{timeframe.value}:"
    )
    return isinstance(exc, ProviderQuotaAdmissionError) and str(exc).startswith(prefix)


async def _plan_and_fetch_history_chunk(
    db,
    *,
    job,
    instrument,
    timeframe: Timeframe,
    preparation: dict,
    priority: int,
    redis,
):
    """Plan and fetch one chunk, skipping candidates only on proven pre-send denial.

    Only an unpinned deepest-history request may try another candidate. Bounded
    requests and continuations stay on their chosen source. ProviderRateLimitError,
    arbitrary errors, and quota errors without the runtime's reservation-denied
    signature are propagated because transport may have started.
    """

    from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError

    may_select_alternative = (
        preparation.get("range_mode") == "deepest_admitted"
        and not preparation.get("source_provider")
        and not preparation.get("chunk")
    )
    excluded_provider_names: set[str] = set()
    last_denial: ProviderQuotaAdmissionError | None = None
    while True:
        (
            chunk_plan,
            candidate_preparation,
            usage_job,
            usage_hold,
            native_hold,
        ) = await _history_chunk_plan_with_native_admission(
            db,
            job,
            instrument,
            timeframe,
            preparation,
            priority=priority,
            excluded_provider_names=excluded_provider_names,
        )
        source_provider = chunk_plan[4]
        if chunk_plan[5] or usage_job is not None or usage_hold or native_hold:
            if last_denial is not None:
                # Keep the exact known quota reset from the candidate that was
                # denied. A different candidate's unresolved baseline does not
                # authorize an unsafe switch or erase that temporary retry.
                raise last_denial
            return (
                chunk_plan,
                candidate_preparation,
                usage_job,
                usage_hold,
                native_hold,
                None,
            )
        if not source_provider or source_provider in excluded_provider_names:
            if last_denial is not None:
                raise last_denial
            return (
                chunk_plan,
                candidate_preparation,
                usage_job,
                usage_hold,
                native_hold,
                None,
            )
        if last_denial is not None and candidate_preparation.get("analysis_requirement_unmet"):
            # Do not pin a shallower fallback that cannot satisfy the request's
            # explicit analysis floor; wait for the deeper candidate's exact
            # quota retry instead.
            raise last_denial

        planned_start, planned_end = chunk_plan[0], chunk_plan[1]
        try:
            from app.services.provider_runtime import (
                bind_bounded_unknown_history,
                bind_history_bound_witness,
            )

            with bind_explicit_provider_acquisition(
                request_id=f"data-preparation:{job.id}",
                operations=frozenset({(ProviderCapability.PRICE_HISTORY, "fetch_ohlcv")}),
                instrument_id=instrument.id,
                symbol=instrument.symbol,
                provider_names=frozenset({source_provider}),
            ):
                with bind_history_bound_witness(candidate_preparation.get("history_bound_witness")):
                    if (
                        candidate_preparation.get("bounded_unknown_depth_provider")
                        == source_provider
                    ):
                        with bind_bounded_unknown_history(
                            provider_name=source_provider,
                            instrument_id=instrument.id,
                            canonical_symbol=instrument.symbol,
                            timeframe=timeframe.value,
                            adjusted=bool(candidate_preparation.get("adjusted", True)),
                            start_at=planned_start,
                            end_at=planned_end,
                        ):
                            bars = await fetch_ohlcv(
                                db,
                                instrument,
                                timeframe,
                                planned_start,
                                end=planned_end,
                                adjusted=bool(candidate_preparation.get("adjusted", True)),
                                redis=redis,
                                source_provider=source_provider,
                            )
                    else:
                        bars = await fetch_ohlcv(
                            db,
                            instrument,
                            timeframe,
                            planned_start,
                            end=planned_end,
                            adjusted=bool(candidate_preparation.get("adjusted", True)),
                            redis=redis,
                            source_provider=source_provider,
                        )
        except ProviderNoDataError as exc:
            candidate_preparation["provider_no_data_reason"] = _provider_no_data_reason(exc)
            bars = []
        except ProviderQuotaAdmissionError as exc:
            if not may_select_alternative or not _is_pretransport_history_quota_denial(
                exc, timeframe
            ):
                raise
            if source_provider in excluded_provider_names:
                raise
            excluded_provider_names.add(source_provider)
            last_denial = exc
            continue
        return (
            chunk_plan,
            candidate_preparation,
            usage_job,
            usage_hold,
            native_hold,
            bars,
        )


async def _enqueue_older_history_chunk(
    db: AsyncSession,
    *,
    job: MarketRefreshJob,
    instrument: Instrument,
    timeframe: Timeframe,
    preparation: dict,
    chunk_start: datetime,
    full_start: datetime,
    full_end: datetime,
) -> int | None:
    previous_end = chunk_start - timedelta(microseconds=1)
    if previous_end <= full_start:
        return None
    previous_start = max(
        full_start,
        _history_chunk_start(
            previous_end,
            timeframe,
            max(1, int(settings.PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS)),
        ),
    )
    # Serialize continuation creation with late coalescing requests. The
    # worker released its claim transaction before transport, so another
    # owner may have appended a parent while the provider call was in flight.
    # Refresh under the same child enqueue lock before copying those refs.
    from app.services.data_preparation import _history_request_key, _lock_parent_for_update

    await _acquire_enqueue_lock(db, job.request_key)
    await db.refresh(job, attribute_names=["metadata_payload"])
    current_payload = deepcopy(job.metadata_payload or {})
    current_child = deepcopy(current_payload.get("data_preparation_child") or {})
    continuation = dict(preparation)
    continuation.update(
        {
            "chunk": True,
            "range_start": full_start.isoformat(),
            "range_end": full_end.isoformat(),
            "selection_start": previous_start.isoformat(),
            "wait_for_job_ids": [],
            "derived_only": False,
        }
    )
    refs = list(current_child.get("parent_refs") or [])
    continuation["parent_refs"] = refs

    request_key = _history_request_key(
        instrument.id,
        timeframe,
        bool(preparation.get("adjusted", True)),
        previous_start,
        previous_end,
        refresh_bucket="fixed",
    )
    await _acquire_enqueue_lock(db, request_key)
    existing = (
        await db.execute(
            select(MarketRefreshJob).where(MarketRefreshJob.request_key == request_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        from app.services.data_preparation import _MAX_PARENT_REFS, _dedupe_parent_refs

        existing_child = (existing.metadata_payload or {}).get("data_preparation_child") or {}
        refs = _dedupe_parent_refs([*refs, *(existing_child.get("parent_refs") or [])])[
            -_MAX_PARENT_REFS:
        ]
    useful_start = _optional_datetime(preparation.get("analysis_required_start"))
    next_priority = _older_chunk_priority(
        current_priority=job.priority,
        range_mode=str(preparation.get("range_mode") or "deepest_admitted"),
        useful_start=useful_start,
        older_chunk_end=previous_end,
    )
    next_job = await enqueue_refresh_job(
        db,
        request_key=request_key,
        capability="price_history",
        instrument_id=instrument.id,
        timeframe=timeframe.value,
        start_at=previous_start,
        end_at=previous_end,
        priority=next_priority,
        metadata_payload={"data_preparation_child": {**continuation, "parent_refs": refs}},
    )
    for ref in refs:
        parent = await _lock_parent_for_update(db, int(ref.get("parent_job_id") or 0))
        if parent is None:
            continue
        parent_data = (parent.metadata_payload or {}).get("data_preparation")
        if not isinstance(parent_data, dict):
            continue
        updated_parent = deepcopy(parent_data)
        dependencies = list(updated_parent.get("dependencies") or [])
        attached = False
        for dependency in dependencies:
            if dependency.get("dependency_id") != ref.get("dependency_id"):
                continue
            background_ids = list(dependency.get("background_job_ids") or [])
            if next_job.id not in background_ids:
                background_ids.append(next_job.id)
            dependency["background_job_ids"] = background_ids
            dependency["updated_at"] = datetime.now(UTC).isoformat()
            attached = True
            break
        if not attached:
            continue
        updated_parent["dependencies"] = dependencies
        from app.services.data_preparation import _aggregate_status

        updated_parent["status"] = _aggregate_status(dependencies)
        updated_parent["version"] = int(updated_parent.get("version") or 1) + 1
        updated_parent["last_progress_at"] = datetime.now(UTC).isoformat()
        parent.metadata_payload = {
            **deepcopy(parent.metadata_payload or {}),
            "data_preparation": updated_parent,
        }
    await db.flush()
    return next_job.id


async def _process_instrument_events_refresh_job(
    db: AsyncSession,
    job: MarketRefreshJob,
) -> dict:
    """Run one durable instrument-event page without coupling it to a GET."""

    from app.models.instrument_event import InstrumentEventFetchState
    from app.services.instrument_events import (
        EVENT_FETCH_VERSION,
        fetch_and_store_instrument_events,
        instrument_events_refresh_request_key,
    )

    instrument = await db.get(Instrument, job.instrument_id) if job.instrument_id else None
    if instrument is None:
        return {"preparation_status": "unavailable", "reason_code": "instrument_not_found"}

    try:
        with bind_explicit_provider_acquisition(
            request_id=f"calendar-refresh:{job.id}",
            operations=frozenset(
                {
                    (
                        ProviderCapability.INSTRUMENT_EVENTS,
                        "fetch_instrument_events",
                    )
                }
            ),
            instrument_id=instrument.id,
        ):
            inserted = await fetch_and_store_instrument_events(
                db,
                instrument,
                # Runtime policies are seeded at application startup. A cache
                # refresh must not repeat the full registry seed while holding
                # the worker transaction.
                seed_runtime=False,
            )
    except ProviderNoDataError:
        return {
            "preparation_status": "unavailable",
            "reason_code": "event_source_unavailable",
            "instrument_id": instrument.id,
        }
    except ProviderNotConfiguredError:
        return {
            "preparation_status": "unavailable",
            "reason_code": "event_provider_not_configured",
            "instrument_id": instrument.id,
        }
    except ProviderQuotaUnknownError:
        return {
            "preparation_status": "held",
            "reason_code": "provider_quota_state_unknown",
            "instrument_id": instrument.id,
        }

    state = (
        await db.execute(
            select(InstrumentEventFetchState)
            .where(InstrumentEventFetchState.instrument_id == instrument.id)
            .order_by(InstrumentEventFetchState.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    page_incomplete = bool(
        state is not None and state.fetch_version >= EVENT_FETCH_VERSION and not state.complete
    )
    has_continuation = page_incomplete and bool(state.continuation_token)
    if has_continuation:
        next_request_key = instrument_events_refresh_request_key(instrument.id, state)
        if next_request_key != job.request_key:
            await enqueue_refresh_job(
                db,
                request_key=next_request_key,
                capability=ProviderCapability.INSTRUMENT_EVENTS.value,
                instrument_id=instrument.id,
                priority=100,
                metadata_payload={
                    "instrument_event_refresh": {
                        "instrument_id": int(instrument.id),
                        "requested_at": datetime.now(UTC).isoformat(),
                    }
                },
                preserve_deferred_deadline=True,
                requeue_completed=True,
            )

    return {
        "preparation_status": "partial" if page_incomplete else "ready",
        "reason_code": "event_page_continuation_pending"
        if has_continuation
        else "event_page_incomplete"
        if page_incomplete
        else None,
        "instrument_id": instrument.id,
        "events_observed": int(state.event_count or 0) if state is not None else inserted,
        "page_count": int(state.page_count or 0) if state is not None else 0,
        "source": state.source if state is not None else None,
    }


async def process_refresh_jobs(ctx: dict, limit: int | None = None) -> dict:
    """Process queued requests with lease/retry telemetry and bounded fan-out."""

    async def reload_claimed_job_for_retry(
        db: AsyncSession,
        *,
        job_id: int,
        lease_token: str | None,
        now: datetime,
    ) -> MarketRefreshJob | None:
        """Reload a still-owned lease after rollback without touching expired ORM fields."""

        if not lease_token:
            return None
        with db.no_autoflush:
            result = await db.execute(
                select(MarketRefreshJob)
                .where(
                    MarketRefreshJob.id == job_id,
                    MarketRefreshJob.status == "leased",
                    MarketRefreshJob.lease_token == lease_token,
                    or_(
                        MarketRefreshJob.leased_until.is_(None),
                        MarketRefreshJob.leased_until >= now,
                    ),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        return result.scalar_one_or_none()

    async with AsyncSessionLocal() as db:
        batch_limit = _refresh_queue_batch_limit(limit)
        claimed_jobs = 0
        completed = 0
        retried = 0
        lease_lost = 0
        more_jobs = False
        next_wakeup_at: datetime | None = None
        previous_job_rollback = False
        while claimed_jobs < batch_limit:
            jobs = await claim_refresh_jobs(db, limit=1)
            if not jobs:
                break
            job = jobs[0]
            claimed_jobs += 1
            claimed_job_id = job.id
            claimed_lease_token = getattr(job, "lease_token", None)
            # Claim only the next job, persist the lease, then release its row
            # locks before provider work. Re-selecting after each bounded job
            # lets newly arrived visible requests outrank queued background
            # work instead of sitting behind a pre-leased batch.
            await db.commit()
            try:
                if previous_job_rollback:
                    # A rollback expires every ORM object in this session, not
                    # only the job whose work failed. Re-read by the immutable
                    # claim key and lease token rather than reading expired ORM
                    # columns before the async refresh has run.
                    recovered_job = await reload_claimed_job_for_retry(
                        db,
                        job_id=claimed_job_id,
                        lease_token=claimed_lease_token,
                        now=datetime.now(UTC),
                    )
                    if recovered_job is None:
                        logger.info(
                            "Refresh job %s lease expired or changed after rollback",
                            claimed_job_id,
                        )
                        lease_lost += 1
                        continue
                    job = recovered_job
                    previous_job_rollback = False
                if job.capability == ProviderCapability.ACCOUNT_USAGE.value:
                    request = (job.metadata_payload or {}).get(
                        "provider_account_usage_refresh"
                    ) or {}
                    result_summary = await _run_native_usage_refresh_job(db, request)
                    await db.refresh(job)
                    await complete_refresh_job(db, job, result_summary=result_summary)
                    completed += 1
                    await db.commit()
                    continue
                if job.capability == ProviderCapability.INSTRUMENT_EVENTS.value:
                    result_summary = await _process_instrument_events_refresh_job(db, job)
                    await db.refresh(job)
                    await complete_refresh_job(db, job, result_summary=result_summary)
                    completed += 1
                    await db.commit()
                    continue
                if job.capability == "data_preparation_screener_expansion":
                    from app.services.data_preparation import process_screener_expansion_batch

                    result_summary = await process_screener_expansion_batch(db, job=job)
                    await db.refresh(job)
                    await complete_refresh_job(db, job, result_summary=result_summary)
                    completed += 1
                    await db.commit()
                    continue
                if job.capability == "etf_holdings_preparation":
                    from app.services.data_preparation import _etf_holdings_preparer

                    preparation = (job.metadata_payload or {}).get("data_preparation_child") or {}
                    preparer = _etf_holdings_preparer()
                    instrument = (
                        await db.get(Instrument, job.instrument_id) if job.instrument_id else None
                    )
                    if instrument is None or preparer is None:
                        result_summary = {
                            "preparation_status": "unavailable",
                            "reason_code": "instrument_not_found"
                            if instrument is None
                            else "etf_handler_unavailable",
                        }
                    else:
                        from app.schemas.data_preparation import PreparationDataset
                        from app.services.data_preparation_contracts import (
                            DatasetPreparationContext,
                        )

                        context = DatasetPreparationContext(
                            request_id=str(preparation["request_id"]),
                            dependency_id=str(preparation.get("dependency_id") or ""),
                            dataset=PreparationDataset.HOLDINGS,
                            timeframe=Timeframe.D1,
                            adjusted=True,
                            requested_start=None,
                            requested_end=None,
                            priority=(
                                "visible"
                                if job.priority <= 10
                                else "background"
                                if job.priority >= 100
                                else "default"
                            ),
                            deadline=datetime.now(UTC) + timedelta(minutes=30),
                        )
                        result = await preparer(db, instrument, context=context)
                        if result.status == "waiting" and result.retry_at is not None:
                            await retry_refresh_job(
                                db,
                                job,
                                result.reason_code or "ETF preparation is waiting",
                                retry_at=result.retry_at,
                                result_summary={
                                    "preparation_status": "waiting",
                                    "reason_code": result.reason_code,
                                },
                            )
                            retried += 1
                            next_wakeup_at = min(next_wakeup_at or result.retry_at, result.retry_at)
                            await db.commit()
                            continue
                        result_summary = {
                            "preparation_status": result.status,
                            "reason_code": result.reason_code,
                            "covered_start": result.covered_start.isoformat()
                            if result.covered_start
                            else None,
                            "covered_end": result.covered_end.isoformat()
                            if result.covered_end
                            else None,
                            "retry_at": result.retry_at.isoformat() if result.retry_at else None,
                            "acquired_version": result.acquired_version,
                        }
                    await db.refresh(job)
                    await complete_refresh_job(db, job, result_summary=result_summary)
                    completed += 1
                    await db.commit()
                    continue
                if job.capability == "instrument_metadata":
                    preparation = (job.metadata_payload or {}).get("data_preparation_child") or {}
                    from app.schemas.data_preparation import PreparationDataset

                    if preparation.get("kind") != "identity_profile":
                        raise ValueError("unsupported metadata preparation job")
                    from app.models.user import User
                    from app.routers.instruments import acquire_instrument
                    from app.schemas.instrument_acquisition import InstrumentAcquireRequest
                    from app.services.data_preparation import (
                        _profile_payload_has_field,
                        expand_resolved_identity_dependency,
                        record_identity_preparation_outcome,
                    )
                    from app.services.market_data import get_provider_profile_async

                    parent_refs = list(preparation.get("parent_refs") or [])
                    selected_parent = None
                    owner = None
                    selected_parent_is_system = False
                    for parent_ref in parent_refs:
                        candidate_parent = await db.get(
                            MarketRefreshJob, int(parent_ref.get("parent_job_id") or 0)
                        )
                        candidate_data = (
                            (candidate_parent.metadata_payload or {}).get("data_preparation")
                            if candidate_parent is not None
                            else None
                        )
                        candidate_role = (
                            candidate_data.get("role") if isinstance(candidate_data, dict) else None
                        )
                        candidate_owner_id = parent_ref.get("owner_user_id")
                        candidate_owner = (
                            await db.get(User, int(candidate_owner_id))
                            if candidate_owner_id
                            else None
                        )
                        owner_request_is_active = bool(
                            candidate_role == "owner_request_tracking"
                            and candidate_owner is not None
                            and candidate_owner.is_active
                            and candidate_data.get("owner_user_id") == candidate_owner.id
                        )
                        system_request_is_valid = bool(
                            candidate_role == "system_maintenance_tracking"
                            and candidate_owner_id is None
                            and candidate_data.get("owner_user_id") is None
                        )
                        if candidate_parent is not None and (
                            owner_request_is_active or system_request_is_valid
                        ):
                            selected_parent, owner = candidate_parent, candidate_owner
                            selected_parent_is_system = system_request_is_valid
                            break
                    if selected_parent is None or (owner is None and not selected_parent_is_system):
                        await record_identity_preparation_outcome(
                            db,
                            identity_job=job,
                            status="unavailable",
                            reason_code="preparation_owner_unavailable",
                        )
                        result_summary = {
                            "preparation_status": "unavailable",
                            "reason_code": "preparation_owner_unavailable",
                        }
                    else:
                        request_id = f"data-preparation-job:{job.id}"
                        instrument_id = preparation.get("instrument_id")
                        selected = (
                            await db.get(Instrument, int(instrument_id)) if instrument_id else None
                        )
                        can_refresh_profile = bool(
                            preparation.get("refresh_profile")
                            and selected is not None
                            and selected.identity_status == "resolved"
                            and selected.domain_key
                            and selected.primary_identifier_type not in {None, "internal", "cik"}
                            and selected.primary_identifier_value
                        )
                        profile_preflight_held = False
                        if can_refresh_profile:
                            (
                                usage_job,
                                usage_hold,
                                usage_needed,
                                usage_context,
                            ) = await _native_usage_prerequisite_for_operation(
                                db,
                                capability=ProviderCapability.INSTRUMENT_METADATA,
                                operation="get_instrument_profile",
                                instrument_id=selected.id,
                                provider_symbol=selected.symbol,
                                priority=job.priority,
                                request_id=request_id,
                                now=datetime.now(UTC),
                            )
                            if usage_needed and usage_hold is not None:
                                profile_preflight_held = True
                                child_payload = deepcopy(job.metadata_payload or {})
                                child_metadata = deepcopy(
                                    child_payload.get("data_preparation_child") or {}
                                )
                                if usage_context is not None:
                                    child_metadata["native_usage_hold"] = {
                                        **usage_context,
                                        "reason_code": usage_hold,
                                    }
                                    child_payload["data_preparation_child"] = child_metadata
                                    job.metadata_payload = child_payload
                                result_summary = {
                                    "preparation_status": "held",
                                    "reason_code": usage_hold,
                                    "instrument_id": selected.id,
                                    "native_usage_prerequisite": {
                                        **(usage_context or {}),
                                        "reason_code": usage_hold,
                                    },
                                }
                                await record_identity_preparation_outcome(
                                    db,
                                    identity_job=job,
                                    status="held",
                                    reason_code=usage_hold,
                                    dataset_filter=PreparationDataset.PROFILE,
                                )
                            elif usage_needed and usage_job is not None:
                                retry_at = await _defer_refresh_job_for_native_usage(
                                    db,
                                    job=job,
                                    usage_job=usage_job,
                                    capability=ProviderCapability.INSTRUMENT_METADATA,
                                    operation="get_instrument_profile",
                                    now=datetime.now(UTC),
                                )
                                retried += 1
                                next_wakeup_at = min(next_wakeup_at or retry_at, retry_at)
                                await db.commit()
                                continue
                        if profile_preflight_held:
                            pass
                        elif can_refresh_profile:
                            required_profile_fields = tuple(
                                str(value)
                                for value in (preparation.get("required_profile_fields") or [])
                            )
                            with bind_explicit_provider_acquisition(
                                request_id=request_id,
                                operations=frozenset(
                                    {
                                        (
                                            ProviderCapability.INSTRUMENT_METADATA,
                                            "get_instrument_profile",
                                        )
                                    }
                                ),
                                instrument_id=selected.id,
                                symbol=selected.symbol,
                            ):
                                profile = await get_provider_profile_async(
                                    db,
                                    selected.symbol,
                                    instrument_id=selected.id,
                                    persist=True,
                                    raise_provider_errors=True,
                                    required_profile_fields=required_profile_fields,
                                )
                            if (
                                profile is None
                                or profile.canonical_symbol.strip().upper()
                                != selected.symbol.upper()
                            ):
                                result_summary = {
                                    "preparation_status": "unavailable",
                                    "reason_code": "provider_profile_not_available",
                                    "instrument_id": selected.id,
                                }
                                await record_identity_preparation_outcome(
                                    db,
                                    identity_job=job,
                                    status="unavailable",
                                    reason_code="provider_profile_not_available",
                                    dataset_filter=PreparationDataset.PROFILE,
                                )
                            elif any(
                                not _profile_payload_has_field(
                                    profile.provider,
                                    {"extra": profile.extra or {}},
                                    field,
                                )
                                for field in required_profile_fields
                            ):
                                result_summary = {
                                    "preparation_status": "unavailable",
                                    "reason_code": "required_profile_field_unavailable",
                                    "missing_profile_fields": [
                                        field
                                        for field in required_profile_fields
                                        if not _profile_payload_has_field(
                                            profile.provider,
                                            {"extra": profile.extra or {}},
                                            field,
                                        )
                                    ],
                                    "instrument_id": selected.id,
                                }
                                await record_identity_preparation_outcome(
                                    db,
                                    identity_job=job,
                                    status="unavailable",
                                    reason_code="required_profile_field_unavailable",
                                    dataset_filter=PreparationDataset.PROFILE,
                                )
                            else:
                                result_summary = {
                                    "preparation_status": "ready",
                                    "instrument_id": selected.id,
                                }
                        else:
                            symbol = str(preparation["symbol"])
                            (
                                usage_job,
                                usage_hold,
                                usage_needed,
                                usage_context,
                            ) = await _native_usage_prerequisite_for_operation(
                                db,
                                capability=ProviderCapability.INSTRUMENT_SEARCH,
                                operation="search_instruments",
                                instrument_id=None,
                                provider_symbol=symbol,
                                priority=job.priority,
                                request_id=request_id,
                                now=datetime.now(UTC),
                            )
                            if usage_needed and usage_hold is not None:
                                child_payload = deepcopy(job.metadata_payload or {})
                                child_metadata = deepcopy(
                                    child_payload.get("data_preparation_child") or {}
                                )
                                if usage_context is not None:
                                    child_metadata["native_usage_hold"] = {
                                        **usage_context,
                                        "reason_code": usage_hold,
                                    }
                                    child_payload["data_preparation_child"] = child_metadata
                                    job.metadata_payload = child_payload
                                await record_identity_preparation_outcome(
                                    db,
                                    identity_job=job,
                                    status="held",
                                    reason_code=usage_hold,
                                )
                                result_summary = {
                                    "preparation_status": "held",
                                    "reason_code": usage_hold,
                                    "symbol": symbol,
                                    "native_usage_prerequisite": {
                                        **(usage_context or {}),
                                        "reason_code": usage_hold,
                                    },
                                }
                            elif usage_needed and usage_job is not None:
                                retry_at = await _defer_refresh_job_for_native_usage(
                                    db,
                                    job=job,
                                    usage_job=usage_job,
                                    capability=ProviderCapability.INSTRUMENT_SEARCH,
                                    operation="search_instruments",
                                    now=datetime.now(UTC),
                                )
                                retried += 1
                                next_wakeup_at = min(next_wakeup_at or retry_at, retry_at)
                                await db.commit()
                                continue
                            else:
                                response = await acquire_instrument(
                                    InstrumentAcquireRequest(symbol=symbol, request_id=request_id),
                                    db=db,
                                    current_user=owner,
                                )
                                if (
                                    response.status == "resolved"
                                    and response.instrument is not None
                                ):
                                    await db.refresh(job)
                                    await expand_resolved_identity_dependency(
                                        db,
                                        identity_job=job,
                                        instrument_id=response.instrument.instrument_id,
                                    )
                                retry_at = next(
                                    (
                                        item.retry_at
                                        for item in response.source_outcomes
                                        if item.retry_at
                                    ),
                                    None,
                                )
                                more_jobs = True
                                if response.status != "resolved":
                                    await record_identity_preparation_outcome(
                                        db,
                                        identity_job=job,
                                        status=response.status,
                                        reason_code=response.reason_code,
                                        retry_at=retry_at,
                                    )
                                if response.status == "held" and retry_at is not None:
                                    await db.refresh(job)
                                    await retry_refresh_job(
                                        db,
                                        job,
                                        response.reason_code or "provider admission held",
                                        retry_at=retry_at,
                                        result_summary={
                                            "preparation_status": "held",
                                            "reason_code": response.reason_code,
                                        },
                                    )
                                    retried += 1
                                    next_wakeup_at = min(next_wakeup_at or retry_at, retry_at)
                                    await db.commit()
                                    continue
                                result_summary = {
                                    "preparation_status": (
                                        "ready"
                                        if response.status == "resolved"
                                        else response.status
                                    ),
                                    "reason_code": response.reason_code,
                                    "retry_at": retry_at.isoformat() if retry_at else None,
                                    "instrument_id": (
                                        response.instrument.instrument_id
                                        if response.instrument is not None
                                        else None
                                    ),
                                }
                    await db.refresh(job)
                    await complete_refresh_job(db, job, result_summary=result_summary)
                    completed += 1
                    await db.commit()
                    continue
                if job.capability != "price_history":
                    raise ValueError("unsupported refresh queue capability")
                if job.instrument_id is None or not job.timeframe:
                    raise ValueError("refresh job has no instrument/timeframe")
                instrument = await db.get(Instrument, job.instrument_id)
                if instrument is None:
                    raise ValueError(f"instrument {job.instrument_id} no longer exists")
                timeframe = Timeframe(job.timeframe)
                preparation = (job.metadata_payload or {}).get("data_preparation_child") or {}

                async def refresh_cached_coarse_from_daily() -> None:
                    """Reconcile W1/MN from the current D1 cache without transport."""

                    if timeframe is not Timeframe.D1 or preparation.get("derived_only"):
                        return
                    adjusted = bool(preparation.get("adjusted", True))
                    for coarse_timeframe in (Timeframe.W1, Timeframe.MN):
                        await refresh_derived_timeframe_if_needed(
                            db,
                            instrument.id,
                            coarse_timeframe,
                            adjusted=adjusted,
                        )

                wait_for_ids = [int(value) for value in preparation.get("wait_for_job_ids", [])]
                if wait_for_ids:
                    prerequisites = list(
                        (
                            await db.execute(
                                select(MarketRefreshJob).where(
                                    MarketRefreshJob.id.in_(wait_for_ids)
                                )
                            )
                        ).scalars()
                    )
                    if len(prerequisites) != len(set(wait_for_ids)) or any(
                        prerequisite.status != "completed" for prerequisite in prerequisites
                    ):
                        await refresh_cached_coarse_from_daily()
                        raise RefreshDependencyPending(
                            retry_at=datetime.now(UTC) + timedelta(seconds=20)
                        )

                if not preparation.get("derived_only") and is_placeholder_symbol(instrument.symbol):
                    # Identity resolution (a prerequisite above) did not turn
                    # this ETF-holding placeholder into a real ticker. No
                    # provider can serve an invented symbol; asking burns quota
                    # on a 400 and retries forever. End the child truthfully.
                    await complete_refresh_job(
                        db,
                        job,
                        result_summary={
                            "preparation_status": "unavailable",
                            "reason_code": "provider_symbol_unresolved",
                            "instrument_id": instrument.id,
                            "timeframe": timeframe.value,
                        },
                    )
                    completed += 1
                    await db.commit()
                    continue

                planned_start = job.start_at
                planned_end = job.end_at
                full_range_start = None
                full_range_end = None
                range_coverage_status = None
                default_series_selected = False
                chunk_coverage_status = None
                if preparation.get("derived_only"):
                    await materialize_derived_timeframes(
                        db,
                        instrument.id,
                        adjusted=bool(preparation.get("adjusted", True)),
                        end=job.end_at,
                    )
                    start = job.start_at or datetime(1970, 1, 1, tzinfo=UTC)
                    bars = await fetch_ohlcv(
                        db,
                        instrument,
                        timeframe,
                        start,
                        end=job.end_at,
                        adjusted=bool(preparation.get("adjusted", True)),
                        allow_provider_fetch=False,
                    )
                elif preparation.get("range_mode") in {"deepest_admitted", "bounded"}:
                    (
                        chunk_plan,
                        preparation,
                        usage_job,
                        usage_hold,
                        native_hold_after_fallbacks,
                        bars,
                    ) = await _plan_and_fetch_history_chunk(
                        db,
                        job=job,
                        instrument=instrument,
                        timeframe=timeframe,
                        preparation=preparation,
                        priority=job.priority,
                        redis=ctx.get("redis"),
                    )
                    (
                        planned_start,
                        planned_end,
                        full_range_start,
                        full_range_end,
                        source_provider,
                        plan_reason,
                    ) = chunk_plan
                    if native_hold_after_fallbacks:
                        await refresh_cached_coarse_from_daily()
                        await complete_refresh_job(
                            db,
                            job,
                            result_summary={
                                "preparation_status": "held",
                                "reason_code": native_hold_after_fallbacks,
                                "retry_at": None,
                                "instrument_id": instrument.id,
                                "timeframe": timeframe.value,
                            },
                        )
                        completed += 1
                        await db.commit()
                        continue
                    if plan_reason:
                        await refresh_cached_coarse_from_daily()
                        local_outcome = None
                        if plan_reason == "no_eligible_history_provider":
                            local_outcome = await _local_history_completion(
                                db,
                                job=job,
                                instrument=instrument,
                                timeframe=timeframe,
                                preparation=preparation,
                            )
                        if local_outcome is not None:
                            await complete_refresh_job(
                                db,
                                job,
                                result_summary=local_outcome,
                            )
                            completed += 1
                            await db.commit()
                            continue
                        await complete_refresh_job(
                            db,
                            job,
                            result_summary={
                                "preparation_status": "waiting",
                                "reason_code": plan_reason,
                                "instrument_id": instrument.id,
                                "timeframe": timeframe.value,
                            },
                        )
                        completed += 1
                        await db.commit()
                        continue
                    if usage_hold is not None:
                        await refresh_cached_coarse_from_daily()
                        await complete_refresh_job(
                            db,
                            job,
                            result_summary={
                                "preparation_status": "held",
                                "reason_code": usage_hold,
                                "retry_at": None,
                                "instrument_id": instrument.id,
                                "timeframe": timeframe.value,
                            },
                        )
                        completed += 1
                        await db.commit()
                        continue
                    if usage_job is not None:
                        preparation = deepcopy(preparation)
                        wait_ids = list(
                            dict.fromkeys(
                                [
                                    *(
                                        int(value)
                                        for value in preparation.get("wait_for_job_ids", [])
                                    ),
                                    int(usage_job.id),
                                ]
                            )
                        )
                        preparation["wait_for_job_ids"] = wait_ids
                        payload = deepcopy(job.metadata_payload or {})
                        payload["data_preparation_child"] = preparation
                        job.metadata_payload = payload
                        if usage_job.status == "completed":
                            await refresh_cached_coarse_from_daily()
                            await complete_refresh_job(
                                db,
                                job,
                                result_summary={
                                    "preparation_status": "held",
                                    "reason_code": "native_usage_refresh_not_qualified",
                                    "retry_at": None,
                                    "instrument_id": instrument.id,
                                    "timeframe": timeframe.value,
                                },
                            )
                            completed += 1
                            await db.commit()
                            continue
                        await refresh_cached_coarse_from_daily()
                        raise RefreshDependencyPending(
                            retry_at=datetime.now(UTC) + timedelta(seconds=20)
                        )
                    if bars is not None:
                        next_job_id = None
                        if (
                            bars
                            and full_range_start is not None
                            and planned_start > full_range_start
                        ):
                            next_job_id = await _enqueue_older_history_chunk(
                                db,
                                job=job,
                                instrument=instrument,
                                timeframe=timeframe,
                                preparation=preparation,
                                chunk_start=planned_start,
                                full_start=full_range_start,
                                full_end=full_range_end or planned_end,
                            )
                            more_jobs = more_jobs or next_job_id is not None
                        if next_job_id is not None:
                            # The visible chunk is useful, but automatic depth
                            # remains outstanding and is reported as partial.
                            range_coverage_status = "partial"
                        if source_provider and full_range_start and full_range_end:
                            from app.services.market_data import _coverage_calendar
                            from app.services.market_series import (
                                select_default_series_for_complete_range,
                                select_default_series_for_latest_contiguous_suffix,
                            )
                            from app.services.ohlcv_coverage import assess_ohlcv_coverage

                            selected_range_start = (
                                _optional_datetime(preparation.get("selection_start"))
                                or planned_start
                                or full_range_start
                            )
                            selected_range_bars = await fetch_ohlcv(
                                db,
                                instrument,
                                timeframe,
                                selected_range_start,
                                end=full_range_end,
                                adjusted=bool(preparation.get("adjusted", True)),
                                allow_provider_fetch=False,
                                source_provider=source_provider,
                            )
                            selected_coverage = assess_ohlcv_coverage(
                                selected_range_bars,
                                timeframe,
                                selected_range_start,
                                full_range_end,
                                calendar=_coverage_calendar(instrument),
                            )
                            series_ids = {
                                int(bar.market_series_id)
                                for bar in selected_range_bars
                                if bar.market_series_id is not None
                            }
                            if len(series_ids) == 1:
                                selected_series_id = next(iter(series_ids))
                                if selected_coverage.status.value == "ready":
                                    default_series_selected = (
                                        await select_default_series_for_complete_range(
                                            db,
                                            instrument_id=instrument.id,
                                            timeframe=timeframe.value,
                                            adjusted=bool(preparation.get("adjusted", True)),
                                            market_series_id=selected_series_id,
                                            start=selected_range_start,
                                            end=full_range_end,
                                        )
                                    )
                                if not default_series_selected:
                                    default_series_selected = (
                                        await select_default_series_for_latest_contiguous_suffix(
                                            db,
                                            instrument_id=instrument.id,
                                            timeframe=timeframe.value,
                                            adjusted=bool(preparation.get("adjusted", True)),
                                            market_series_id=selected_series_id,
                                            requested_start=selected_range_start,
                                            end=full_range_end,
                                        )
                                    )
                            if next_job_id is None:
                                complete_range_bars = (
                                    selected_range_bars
                                    if selected_range_start == full_range_start
                                    else await fetch_ohlcv(
                                        db,
                                        instrument,
                                        timeframe,
                                        full_range_start,
                                        end=full_range_end,
                                        adjusted=bool(preparation.get("adjusted", True)),
                                        allow_provider_fetch=False,
                                        source_provider=source_provider,
                                    )
                                )
                                full_coverage = assess_ohlcv_coverage(
                                    complete_range_bars,
                                    timeframe,
                                    full_range_start,
                                    full_range_end,
                                    calendar=_coverage_calendar(instrument),
                                )
                                range_coverage_status = full_coverage.status.value
                                if range_coverage_status == "ready" and preparation.get(
                                    "analysis_requirement_unmet"
                                ):
                                    range_coverage_status = "partial"
                                if range_coverage_status == "ready" and preparation.get(
                                    "history_depth_unknown_candidates"
                                ):
                                    range_coverage_status = "partial"
                else:
                    start = job.start_at or (datetime.now(UTC) - timedelta(days=7))
                    with bind_explicit_provider_acquisition(
                        request_id=f"data-preparation:{job.id}",
                        operations=frozenset({(ProviderCapability.PRICE_HISTORY, "fetch_ohlcv")}),
                        instrument_id=instrument.id,
                    ):
                        bars = await fetch_ohlcv(
                            db,
                            instrument,
                            timeframe,
                            start,
                            end=job.end_at,
                            adjusted=bool(preparation.get("adjusted", True)),
                            redis=ctx.get("redis"),
                        )
                await refresh_cached_coarse_from_daily()

                result_start = min((bar.ts for bar in bars), default=None)
                result_end = max((bar.ts for bar in bars), default=None)
                coverage_scopes = sorted(
                    {
                        (
                            int(bar.data_source_id) if bar.data_source_id is not None else None,
                            int(bar.market_series_id) if bar.market_series_id is not None else None,
                            str(getattr(bar.adjustment_basis, "value", bar.adjustment_basis)),
                            str(bar.adjustment_version or ""),
                            bool(bar.is_adjusted),
                        )
                        for bar in bars
                    },
                    key=lambda item: tuple(-1 if value is None else value for value in item),
                )
                data_status = _history_chunk_data_status(
                    bars=bars,
                    range_coverage_status=range_coverage_status,
                )
                if bars and planned_start is not None and planned_end is not None:
                    from app.services.market_data import _coverage_calendar
                    from app.services.ohlcv_coverage import assess_ohlcv_coverage

                    coverage = assess_ohlcv_coverage(
                        bars,
                        timeframe,
                        planned_start,
                        planned_end,
                        calendar=_coverage_calendar(instrument),
                    )
                    chunk_coverage_status = coverage.status.value
                    if coverage.status.value != "ready":
                        data_status = "partial"
                reason_code = (
                    preparation.get("provider_no_data_reason") if data_status == "empty" else None
                )
                if reason_code is None:
                    reason_code = (
                        "analysis_history_depth_not_admitted"
                        if preparation.get("analysis_requirement_unmet")
                        else "history_depth_unknown"
                        if preparation.get("history_depth_unknown_candidates")
                        and range_coverage_status == "partial"
                        else "history_coverage_partial"
                        if range_coverage_status == "partial"
                        else None
                    )
                await complete_refresh_job(
                    db,
                    job,
                    result_summary={
                        "instrument_id": instrument.id,
                        "timeframe": timeframe.value,
                        "requested_start": planned_start.isoformat() if planned_start else None,
                        "requested_end": planned_end.isoformat() if planned_end else None,
                        "bars_observed": len(bars),
                        "covered_start": result_start.isoformat() if result_start else None,
                        "covered_end": result_end.isoformat() if result_end else None,
                        "coverage_scopes": [
                            {
                                "data_source_id": data_source_id,
                                "market_series_id": market_series_id,
                                "adjustment_basis": adjustment_basis,
                                "adjustment_version": adjustment_version,
                                "is_adjusted": is_adjusted,
                            }
                            for (
                                data_source_id,
                                market_series_id,
                                adjustment_basis,
                                adjustment_version,
                                is_adjusted,
                            ) in coverage_scopes
                        ],
                        "data_status": data_status,
                        "chunk_coverage_status": chunk_coverage_status,
                        "coverage_window_start": (
                            full_range_start.isoformat()
                            if full_range_start
                            else planned_start.isoformat()
                            if planned_start
                            else None
                        ),
                        "coverage_window_end": (
                            full_range_end.isoformat()
                            if full_range_end
                            else planned_end.isoformat()
                            if planned_end
                            else None
                        ),
                        "history_source_provider": preparation.get("source_provider"),
                        "range_coverage_status": range_coverage_status,
                        "reason_code": reason_code,
                        "history_depth_unknown_candidates": preparation.get(
                            "history_depth_unknown_candidates", []
                        ),
                        "history_depth_unknown_holds": preparation.get(
                            "history_depth_unknown_holds", {}
                        ),
                        "history_bound_witnesses": preparation.get("history_bound_witnesses", {}),
                        "default_series_selected": default_series_selected,
                    },
                )
                completed += 1
            except RefreshLeaseLostError as exc:
                # Another worker owns this job now (or its lease expired).
                # Never retry or overwrite that worker's state from this
                # stale execution; the durable queue will expose/reclaim it.
                logger.info(
                    "Refresh job %s lease no longer owned: %s",
                    claimed_job_id,
                    bounded_redact_provider_message(exc),
                )
                lease_lost += 1
            except RefreshDependencyPending as exc:
                # This is an expected wait, not a failed transaction. In
                # particular, history planning may have just queued a native
                # usage prerequisite and attached it to this job. Commit that
                # graph before deferring the leased history child.
                pending_payload = deepcopy(job.metadata_payload or {})
                now = datetime.now(UTC)
                with db.no_autoflush:
                    lease_row = (
                        await db.execute(
                            select(MarketRefreshJob)
                            .where(
                                MarketRefreshJob.id == claimed_job_id,
                                MarketRefreshJob.status == "leased",
                                MarketRefreshJob.lease_token == claimed_lease_token,
                                or_(
                                    MarketRefreshJob.leased_until.is_(None),
                                    MarketRefreshJob.leased_until >= now,
                                ),
                            )
                            .with_for_update()
                            .execution_options(populate_existing=True)
                        )
                    ).scalar_one_or_none()
                if lease_row is None:
                    await db.rollback()
                    previous_job_rollback = True
                    logger.info(
                        "Refresh job %s lease lost before prerequisite defer",
                        claimed_job_id,
                    )
                    lease_lost += 1
                    continue
                # Restore the in-memory dependency graph after the locked read,
                # then flush it and the prerequisite insert under the validated
                # lease row lock.
                lease_row.metadata_payload = pending_payload
                await db.flush()
                await db.commit()
                await db.refresh(lease_row)
                job = lease_row
                try:
                    await retry_refresh_job(
                        db,
                        job,
                        str(exc),
                        retry_at=exc.retry_at,
                        lease_token=claimed_lease_token,
                    )
                except RefreshLeaseLostError as lease_exc:
                    logger.info(
                        "Refresh job %s lease lost while deferring prerequisite: %s",
                        claimed_job_id,
                        bounded_redact_provider_message(lease_exc),
                    )
                    lease_lost += 1
                else:
                    retried += 1
                    next_wakeup_at = min(
                        next_wakeup_at or exc.retry_at,
                        exc.retry_at,
                    )
            except Exception as exc:
                original_error = exc
                original_error_message = str(exc)
                try:
                    await db.rollback()
                    previous_job_rollback = True
                    job = await reload_claimed_job_for_retry(
                        db,
                        job_id=claimed_job_id,
                        lease_token=claimed_lease_token,
                        now=datetime.now(UTC),
                    )
                    if job is None:
                        raise RefreshLeaseLostError(
                            f"refresh job {claimed_job_id} lease is no longer valid"
                        )
                    await retry_refresh_job(
                        db,
                        job,
                        original_error_message,
                        retry_at=getattr(original_error, "retry_at", None),
                        lease_token=claimed_lease_token,
                    )
                except RefreshLeaseLostError as lease_exc:
                    logger.info(
                        "Refresh job %s lease lost during retry: %s",
                        claimed_job_id,
                        bounded_redact_provider_message(lease_exc),
                    )
                    lease_lost += 1
                except Exception as retry_exc:
                    logger.error(
                        "Could not persist retry for refresh job %s after %s: %s",
                        claimed_job_id,
                        type(original_error).__name__,
                        type(retry_exc).__name__,
                    )
                    raise retry_exc from original_error
                else:
                    retried += 1
                    if job.next_attempt_at is not None:
                        next_wakeup_at = min(
                            next_wakeup_at or job.next_attempt_at,
                            job.next_attempt_at,
                        )
            await db.commit()
        more_jobs = more_jobs or claimed_jobs >= batch_limit
        wakeup_scheduled = False
        redis = ctx.get("redis")
        if redis is not None and (more_jobs or next_wakeup_at is not None):
            try:
                wake_kwargs = {"_defer_by": 1} if more_jobs else {"_defer_until": next_wakeup_at}
                await redis.enqueue_job(
                    "task_process_refresh_jobs",
                    _job_id=f"data-preparation-followup:{uuid4().hex}",
                    _expires=3600,
                    **wake_kwargs,
                )
                wakeup_scheduled = True
            except Exception as exc:
                logger.warning(
                    "Could not schedule data-preparation continuation: %s", type(exc).__name__
                )
        return {
            "claimed": claimed_jobs,
            "completed": completed,
            "retried": retried,
            "lease_lost": lease_lost,
            "wakeup_scheduled": wakeup_scheduled,
        }


class RefreshDependencyPending(RuntimeError):
    def __init__(self, *, retry_at: datetime) -> None:
        super().__init__(DEPENDENCY_PENDING_ERROR)
        self.retry_at = retry_at


async def _read_prepared_history(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    *,
    adjusted: bool,
    start: datetime | None,
    end: datetime | None,
) -> list[OHLCVBar]:
    """Read only the canonical default series after a queue fetch/materialization."""

    from app.services.market_data import _default_series_bar_condition

    predicates = [
        OHLCVBar.instrument_id == instrument.id,
        OHLCVBar.timeframe == timeframe,
        OHLCVBar.is_adjusted.is_(adjusted),
        _default_series_bar_condition(instrument.id, timeframe, adjusted),
    ]
    if start is not None:
        predicates.append(OHLCVBar.ts >= start)
    if end is not None:
        predicates.append(OHLCVBar.ts <= end)
    return list(
        (await db.execute(select(OHLCVBar).where(*predicates).order_by(OHLCVBar.ts))).scalars()
    )


async def run_market_data_shadow_report(ctx: dict) -> dict:
    """Produce the daily operator report without changing routing behavior."""

    async with AsyncSessionLocal() as db:
        report = await build_shadow_report(db)
        logger.info(
            "market-data shadow report: observations=%s discrepancies=%s rate=%.4f",
            report["observations"],
            report["discrepancies"],
            report["discrepancy_rate"],
        )
        return report


async def reconcile_market_universe(ctx: dict) -> dict:
    """Reconcile complete US discovery feeds, then record core D1 coverage."""

    async with AsyncSessionLocal() as db:
        reconciliation = await reconcile_us_universe(db)
        coverage = await record_core_daily_coverage(db)
        await db.commit()
        return {"reconciliation": reconciliation, "coverage": coverage}


async def refresh_provider_account_usage_snapshots(ctx: dict) -> dict:
    """Refresh explicitly configured provider-native account counters.

    Account introspection is provider traffic and is therefore never inferred
    from a generic schedule. Deployments must enable this task and name each
    provider explicitly; the service still applies that provider's credential,
    quota, entitlement, and circuit-breaker gates before making a request.
    """

    from app.config import settings
    from app.services.provider_account_usage import (
        refresh_provider_account_usage,
    )

    if not settings.PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED:
        return {"skipped": True, "reason": "provider account-usage refresh disabled"}
    configured = getattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", [])
    providers = tuple(
        dict.fromkeys(
            str(provider).strip()
            for provider in (configured if isinstance(configured, list) else [])
            if str(provider).strip()
        )
    )
    if not providers:
        return {"skipped": True, "reason": "no provider account-usage refresh providers configured"}

    async with AsyncSessionLocal() as db:
        results = []
        for provider in providers:
            try:
                with bind_explicit_provider_acquisition(
                    request_id=f"scheduled-native-usage-refresh:{provider}",
                    operations=frozenset(
                        {(ProviderCapability.ACCOUNT_USAGE, "fetch_account_usage")}
                    ),
                    provider_names=frozenset({provider.strip().lower()}),
                ):
                    provider_name = provider.strip().lower()
                    result = await refresh_provider_account_usage(db, provider_name=provider_name)
                    if _native_usage_refresh_succeeded_for_provider(result, provider_name):
                        resumed = await resume_native_usage_held_identity_jobs(
                            db, provider_name=provider_name
                        )
                        if resumed:
                            await db.commit()
                            result["resumed_preparation_jobs"] = resumed
                    results.append(result)
            except Exception as exc:  # noqa: BLE001 - keep one provider failure from suppressing others.
                results.append(
                    {
                        "status": "failed",
                        "providers": [],
                        "observations": [],
                        "failures": [
                            {
                                "provider": provider,
                                "error": bounded_redact_provider_message(exc, max_length=500),
                            }
                        ],
                    }
                )
    return {"providers": list(providers), "results": results}


async def refresh_market_events(ctx: dict) -> dict:
    """Persist one bounded forward market-event window when enabled."""

    from app.config import settings
    from app.services.market_events import refresh_market_events as _refresh_market_events

    if not settings.MARKET_EVENTS_REFRESH_ENABLED:
        return {"skipped": True, "reason": "market-events refresh disabled"}

    today = datetime.now(UTC).date()
    lookahead_days = max(1, int(settings.MARKET_EVENTS_REFRESH_LOOKAHEAD_DAYS))
    max_providers = max(1, int(settings.MARKET_EVENTS_REFRESH_MAX_PROVIDERS))
    async with AsyncSessionLocal() as db:
        return await _refresh_market_events(
            db,
            start=today,
            end=today + timedelta(days=lookahead_days),
            max_providers=max_providers,
        )


async def materialize_market_event_prelisting(ctx: dict) -> dict:
    """Materialize a bounded future-listing candidate set when enabled."""

    from app.config import settings
    from app.services.market_event_prelisting import (
        materialize_prelisting_candidates,
        promote_prelisting_candidates,
    )

    if not settings.MARKET_EVENTS_PRELISTING_ENABLED:
        return {"skipped": True, "reason": "pre-listing materialization disabled"}
    today = datetime.now(UTC).date()
    lookahead_days = max(1, int(settings.MARKET_EVENTS_PRELISTING_LOOKAHEAD_DAYS))
    max_events = max(1, int(settings.MARKET_EVENTS_PRELISTING_MAX_EVENTS))
    async with AsyncSessionLocal() as db:
        materialized = await materialize_prelisting_candidates(
            db,
            start=today,
            end=today + timedelta(days=lookahead_days),
            max_events=max_events,
        )
        promoted = await promote_prelisting_candidates(db, max_candidates=max_events)
        await db.commit()
        return {"materialized": materialized, "promoted": promoted}


async def refresh_edgar_ipo_pipeline_for_issuer_universe(ctx: dict) -> dict:
    """Scan a durable bounded batch of known SEC issuers for filing candidates."""

    from app.config import settings
    from app.services.market_event_edgar_scan import (
        refresh_edgar_ipo_pipeline_for_issuer_universe as _refresh_edgar_ipo_pipeline_for_issuer_universe,
    )

    if not settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED:
        return {"skipped": True, "reason": "EDGAR issuer-universe scan disabled"}
    if settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED:
        return {
            "skipped": True,
            "reason": "EDGAR issuer and SEC directory scans are mutually exclusive",
        }
    today = datetime.now(UTC).date()
    lookback_days = max(1, int(settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_LOOKBACK_DAYS))
    max_issuers = max(1, int(settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_MAX_ISSUERS))
    max_events = max(
        1,
        int(settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_MAX_EVENTS_PER_ISSUER),
    )
    async with AsyncSessionLocal() as db:
        return await _refresh_edgar_ipo_pipeline_for_issuer_universe(
            db,
            start=today - timedelta(days=lookback_days),
            end=today,
            max_issuers=max_issuers,
            max_events_per_issuer=max_events,
        )


async def refresh_edgar_ipo_pipeline_for_sec_directory(ctx: dict) -> dict:
    """Scan one durable page of SEC ticker associations after policy gates."""

    from app.config import settings
    from app.services.market_event_edgar_scan import (
        refresh_edgar_ipo_pipeline_for_sec_directory as _refresh_edgar_ipo_pipeline_for_sec_directory,
    )

    if not settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED:
        return {"skipped": True, "reason": "EDGAR SEC directory scan disabled"}
    if settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED:
        return {
            "skipped": True,
            "reason": "EDGAR issuer and SEC directory scans are mutually exclusive",
        }
    max_submissions_requests = int(
        settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS
    )
    if max_submissions_requests <= 0:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory submissions request budget not reviewed",
        }
    if max_submissions_requests > 500:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory submissions request budget must be at most 500",
        }
    configured_max_issuers = int(settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS)
    if not 1 <= configured_max_issuers <= 500:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory max issuers must be between 1 and 500",
        }
    if configured_max_issuers > max_submissions_requests:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory submissions request budget is below max issuers",
        }
    today = datetime.now(UTC).date()
    lookback_days = max(1, int(settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_LOOKBACK_DAYS))
    max_issuers = configured_max_issuers
    max_events = max(
        1,
        int(settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_EVENTS_PER_ISSUER),
    )
    materialization_mode = (
        str(settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE).strip().lower()
    )
    if materialization_mode not in {"disabled", "create_missing"}:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory issuer materialization mode is invalid",
        }
    reviewed_cycle_count = int(settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_REVIEWED_CYCLE_COUNT)
    if reviewed_cycle_count < 0:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory reviewed cycle count must be non-negative",
        }
    async with AsyncSessionLocal() as db:
        return await _refresh_edgar_ipo_pipeline_for_sec_directory(
            db,
            start=today - timedelta(days=lookback_days),
            end=today,
            max_issuers=max_issuers,
            max_events_per_issuer=max_events,
            max_submissions_requests=max_submissions_requests,
            issuer_materialization_mode=materialization_mode,
            issuer_materialization_reviewed_cycle_count=reviewed_cycle_count,
        )


async def refresh_tokenized_asset_prices(ctx: dict) -> dict:
    """Refresh a bounded tokenized quote batch through durable provider routing."""

    from app.config import settings
    from app.services.tokenized_assets import refresh_tokenized_prices

    async with AsyncSessionLocal() as db:
        return await refresh_tokenized_prices(
            db,
            max_assets=settings.TOKENIZED_ASSET_REFRESH_MAX_ASSETS,
        )


async def refresh_tokenized_asset_catalog(ctx: dict) -> dict:
    """Discover a bounded tokenized catalogue through durable provider routing."""

    from app.config import settings
    from app.services.tokenized_assets import refresh_tokenized_assets

    async with AsyncSessionLocal() as db:
        return await refresh_tokenized_assets(
            db,
            max_pages=settings.TOKENIZED_CATALOG_REFRESH_MAX_PAGES,
            page_size=settings.TOKENIZED_CATALOG_REFRESH_PAGE_SIZE,
        )


async def refresh_tokenized_historical_asset_prices(ctx: dict) -> dict:
    """Persist a bounded tokenized aggregate-history batch."""

    from app.config import settings
    from app.services.tokenized_assets import refresh_tokenized_historical_prices

    async with AsyncSessionLocal() as db:
        return await refresh_tokenized_historical_prices(
            db,
            max_assets=settings.TOKENIZED_HISTORICAL_REFRESH_MAX_ASSETS,
            timespan=settings.TOKENIZED_HISTORICAL_REFRESH_TIMESPAN,
        )


async def refresh_tokenized_corporate_actions(ctx: dict) -> dict:
    """Persist bounded tokenized corporate-action feeds as market events."""

    from app.config import settings
    from app.services.tokenized_assets import refresh_tokenized_events

    async with AsyncSessionLocal() as db:
        return await refresh_tokenized_events(
            db,
            max_providers=settings.TOKENIZED_EVENT_REFRESH_MAX_PROVIDERS,
            max_pages=settings.TOKENIZED_EVENT_REFRESH_MAX_PAGES,
            page_size=settings.TOKENIZED_EVENT_REFRESH_PAGE_SIZE,
        )
