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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.data_source import DataSource
from app.models.instrument import Instrument
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
from app.providers.errors import bounded_redact_provider_message
from app.services.derived_timeframes import materialize_derived_timeframes
from app.services.market_data import fetch_ohlcv
from app.services.market_data_monitoring import build_shadow_report
from app.services.market_refresh_queue import (
    RefreshLeaseLostError,
    _acquire_enqueue_lock,
    claim_refresh_jobs,
    complete_refresh_job,
    enqueue_refresh_job,
    retry_refresh_job,
)
from app.services.market_universe import reconcile_us_universe, record_core_daily_coverage
from app.services.provider_runtime import ProviderNoDataError, bind_explicit_provider_acquisition

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
    if usage is None or not policy_allows_account_usage_bootstrap(
        usage.policy, "fetch_account_usage"
    ):
        return None, "native_usage_bootstrap_not_admitted", True

    usage_policy_dimensions = quota_dimensions(usage.policy)
    reconciled = account_usage_reconciled_dimensions(usage.policy, "fetch_account_usage")
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
) -> tuple[MarketRefreshJob | None, str | None, bool]:
    """Find the first admitted provider operation needing native refresh."""

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
    for resolved in chain:
        job, reason, needed = await _native_usage_job_for_operation_baseline(
            db,
            provider_name=resolved.provider_name,
            capability=capability,
            operation=operation,
            priority=priority,
            now=now,
        )
        if needed:
            return job, reason, True
    return None, None, False


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
    provider_observed = usage_result.get("status") == "refreshed" and usage_result.get(
        "providers"
    ) == [provider_name]
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


async def _deepest_admitted_history_start(
    db: AsyncSession,
    instrument: Instrument,
    timeframe: Timeframe,
    *,
    adjusted: bool,
    end: datetime,
    request_id: str,
    excluded_provider_names: set[str] | frozenset[str] = frozenset(),
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
    bounds: list[tuple[datetime, str]] = []
    unknown_bound = False
    excluded = {str(name).strip().lower() for name in excluded_provider_names}
    for resolved in chain:
        if resolved.provider_name.strip().lower() in excluded:
            continue
        entitlement = resolved.entitlement
        quota_policy = entitlement.quota_policy if entitlement is not None else None
        constraints = (
            quota_policy.get("history_constraints") if isinstance(quota_policy, dict) else None
        )
        if not isinstance(constraints, dict):
            unknown_bound = True
            continue
        earliest, _reason = provider_history_bound_start(constraints, now=end)
        if earliest is not None:
            bounds.append((earliest, resolved.provider_name))
    if bounds:
        earliest, provider_name = min(bounds, key=lambda item: (item[0], item[1]))
        return earliest, provider_name, None
    reason = "history_depth_unknown" if unknown_bound else "no_eligible_history_provider"
    return None, None, reason


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
            excluded_provider_names=excluded_provider_names,
        )
        if admitted_start is None:
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
):
    """Prefer the deepest provider whose native quota can actually be admitted.

    The first unpinned chunk may fall back to another exact resolver candidate
    when the deepest candidate's baseline is unknown and its normal usage
    prerequisite is unavailable. Once a source is pinned (including a
    continuation chunk), hold on that source rather than mixing lineages.
    """

    pinned_source = bool(preparation.get("source_provider") or preparation.get("chunk"))
    excluded_provider_names: set[str] = set()
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
        existing_child = (existing.metadata_payload or {}).get("data_preparation_child") or {}
        for ref in existing_child.get("parent_refs") or []:
            if ref not in refs:
                refs.append(ref)
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


async def process_refresh_jobs(ctx: dict, limit: int | None = None) -> dict:
    """Process queued requests with lease/retry telemetry and bounded fan-out."""

    async with AsyncSessionLocal() as db:
        jobs = await claim_refresh_jobs(db, limit=_refresh_queue_batch_limit(limit))
        # Persist the lease and release its row locks before doing any
        # provider work. Request handlers may coalesce another owner onto a
        # leased child while the worker is waiting on a slow transport.
        await db.commit()
        completed = 0
        retried = 0
        lease_lost = 0
        more_jobs = len(jobs) >= _refresh_queue_batch_limit(limit)
        next_wakeup_at: datetime | None = None
        for job in jobs:
            try:
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
                                result_summary = {
                                    "preparation_status": "unavailable",
                                    "reason_code": usage_hold,
                                    "instrument_id": selected.id,
                                }
                                await record_identity_preparation_outcome(
                                    db,
                                    identity_job=job,
                                    status="unavailable",
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
                                await record_identity_preparation_outcome(
                                    db,
                                    identity_job=job,
                                    status="unavailable",
                                    reason_code=usage_hold,
                                )
                                result_summary = {
                                    "preparation_status": "unavailable",
                                    "reason_code": usage_hold,
                                    "symbol": symbol,
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
                        raise RefreshDependencyPending(
                            retry_at=datetime.now(UTC) + timedelta(seconds=20)
                        )

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
                    ) = await _history_chunk_plan_with_native_admission(
                        db,
                        job,
                        instrument,
                        timeframe,
                        preparation,
                        priority=job.priority,
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
                        raise RefreshDependencyPending(
                            retry_at=datetime.now(UTC) + timedelta(seconds=20)
                        )
                    try:
                        with bind_explicit_provider_acquisition(
                            request_id=f"data-preparation:{job.id}",
                            operations=frozenset(
                                {(ProviderCapability.PRICE_HISTORY, "fetch_ohlcv")}
                            ),
                            instrument_id=instrument.id,
                            symbol=instrument.symbol,
                            provider_names=(
                                frozenset({source_provider}) if source_provider else None
                            ),
                        ):
                            bars = await fetch_ohlcv(
                                db,
                                instrument,
                                timeframe,
                                planned_start,
                                end=planned_end,
                                adjusted=bool(preparation.get("adjusted", True)),
                                redis=ctx.get("redis"),
                                source_provider=source_provider,
                            )
                    except ProviderNoDataError:
                        bars = []
                    else:
                        if timeframe is Timeframe.D1 and preparation.get(
                            "derive_coarse_timeframes"
                        ):
                            await materialize_derived_timeframes(
                                db,
                                instrument.id,
                                adjusted=bool(preparation.get("adjusted", True)),
                            )
                        next_job_id = None
                        if full_range_start is not None and planned_start > full_range_start:
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
                            if selected_coverage.status.value == "ready" and len(series_ids) == 1:
                                default_series_selected = (
                                    await select_default_series_for_complete_range(
                                        db,
                                        instrument_id=instrument.id,
                                        timeframe=timeframe.value,
                                        adjusted=bool(preparation.get("adjusted", True)),
                                        market_series_id=next(iter(series_ids)),
                                        start=selected_range_start,
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
                data_status = "ready" if bars else "empty"
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
                if range_coverage_status is not None and range_coverage_status != "ready":
                    data_status = "partial"
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
                        "reason_code": (
                            "analysis_history_depth_not_admitted"
                            if preparation.get("analysis_requirement_unmet")
                            else "history_coverage_partial"
                            if range_coverage_status == "partial"
                            else None
                        ),
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
                    job.id,
                    bounded_redact_provider_message(exc),
                )
                lease_lost += 1
            except Exception as exc:
                try:
                    await retry_refresh_job(
                        db,
                        job,
                        str(exc),
                        retry_at=getattr(exc, "retry_at", None),
                    )
                except RefreshLeaseLostError as lease_exc:
                    logger.info(
                        "Refresh job %s lease lost during retry: %s",
                        job.id,
                        bounded_redact_provider_message(lease_exc),
                    )
                    lease_lost += 1
                else:
                    retried += 1
                    if job.next_attempt_at is not None:
                        next_wakeup_at = min(
                            next_wakeup_at or job.next_attempt_at,
                            job.next_attempt_at,
                        )
            await db.commit()
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
            "claimed": len(jobs),
            "completed": completed,
            "retried": retried,
            "lease_lost": lease_lost,
            "wakeup_scheduled": wakeup_scheduled,
        }


class RefreshDependencyPending(RuntimeError):
    def __init__(self, *, retry_at: datetime) -> None:
        super().__init__("data preparation dependency is not complete")
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
                    results.append(
                        await refresh_provider_account_usage(
                            db, provider_name=provider.strip().lower()
                        )
                    )
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
