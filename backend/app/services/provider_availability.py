"""Bounded, persisted provider availability probes.

The scheduler calls this service only when explicitly enabled.  The probe
contract is deterministic and injectable in tests; live adapters are called
through one representative request per provider/capability and never in
parallel for the same provider.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.ohlcv import Timeframe
from app.models.provider_runtime import (
    ProviderAvailabilityObservation,
    ProviderAvailabilityRun,
    ProviderCapability,
    ProviderEntitlement,
    ProviderHealthState,
    ProviderPolicy,
)
from app.providers import get_provider
from app.services.onesignal import send_provider_availability_notification

CLASSIFICATIONS = {
    "success",
    "not_configured",
    "entitlement_exclusion",
    "authentication",
    "quota_rate_limit",
    "dns_transport",
    "timeout",
    "upstream_http",
    "schema_content_incompatibility",
    "empty_partial_response",
    "internal_parser_failure",
}
Probe = Callable[[str, ProviderCapability, dict[str, Any]], Any | Awaitable[Any]]


def representative_request(capability: ProviderCapability) -> dict[str, Any]:
    values: dict[ProviderCapability, dict[str, Any]] = {
        ProviderCapability.INSTRUMENT_SEARCH: {"query": "SPY", "limit": 1},
        ProviderCapability.INSTRUMENT_METADATA: {"symbol": "SPY"},
        ProviderCapability.PRICE_HISTORY: {"symbol": "SPY", "timeframe": "D1", "limit": 5},
        ProviderCapability.LATEST_PRICE: {"symbol": "SPY"},
        ProviderCapability.INSTRUMENT_EVENTS: {"symbol": "SPY"},
        ProviderCapability.INSTRUMENT_IDENTIFIERS: {"symbol": "SPY"},
        ProviderCapability.UNIVERSE_DISCOVERY: {"quote_type": "EQUITY", "offset": 0},
        ProviderCapability.OPTION_CHAIN: {"symbol": "SPY"},
        ProviderCapability.OPTION_QUOTE_HISTORY: {"symbol": "SPY", "days": 5},
        ProviderCapability.CORPORATE_ACTIONS: {"symbol": "SPY"},
        ProviderCapability.EARNINGS: {"symbol": "SPY"},
        ProviderCapability.FUNDAMENTALS: {"symbol": "SPY", "cik": "0000320193"},
        ProviderCapability.SHORT_INTEREST: {"symbol": "SPY"},
        ProviderCapability.MARKET_CALENDAR: {"symbol": "SPY"},
        ProviderCapability.FUTURES_HISTORY: {"symbol": "ES=F", "timeframe": "D1", "limit": 5},
        ProviderCapability.CRYPTO_HISTORY: {"symbol": "BTC-USD", "timeframe": "D1", "limit": 5},
        ProviderCapability.OPTIONS_CURRENT: {"symbol": "SPY"},
        ProviderCapability.MARKET_EVENTS: {"symbol": "SPY"},
    }
    return dict(values[capability])


def classify_exception(exc: BaseException) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None) or getattr(
        exc, "status_code", None
    )
    message = str(exc).lower()
    if isinstance(exc, TimeoutError | asyncio.TimeoutError) or "timeout" in message:
        return "timeout"
    if "dns" in message or "name or service" in message or "connection" in message:
        return "dns_transport"
    if status in {401, 403} or any(
        word in message for word in ("unauthorized", "forbidden", "api key")
    ):
        return "authentication"
    if status in {408, 429} or any(word in message for word in ("rate limit", "quota", "too many")):
        return "quota_rate_limit"
    if isinstance(status, int) and status >= 400:
        return "upstream_http"
    if isinstance(exc, KeyError) or any(
        token in message for token in ("schema", "field", "column", "payload")
    ):
        return "schema_content_incompatibility"
    if isinstance(exc, TypeError | ValueError | AttributeError):
        return "internal_parser_failure"
    return "internal_parser_failure"


def response_shape(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null", "items": 0}
    if isinstance(value, dict):
        return {"type": "object", "keys": sorted(str(key) for key in value.keys())[:32]}
    if isinstance(value, list | tuple | set):
        return {
            "type": "array",
            "items": len(value),
            "item_type": type(next(iter(value), None)).__name__,
        }
    return {"type": type(value).__name__}


def classify_response(value: Any) -> str:
    if value is None:
        return "empty_partial_response"
    if isinstance(value, list | tuple | set | dict) and not value:
        return "empty_partial_response"
    return "success"


async def default_probe(
    provider_name: str, capability: ProviderCapability, request: dict[str, Any]
) -> Any:
    provider = get_provider(provider_name)
    method_name = {
        ProviderCapability.INSTRUMENT_SEARCH: "search_instruments",
        ProviderCapability.INSTRUMENT_METADATA: "get_instrument_profile",
        ProviderCapability.LATEST_PRICE: "get_current_price",
        ProviderCapability.PRICE_HISTORY: "fetch_latest_ohlcv",
        ProviderCapability.INSTRUMENT_EVENTS: "fetch_instrument_events",
        ProviderCapability.INSTRUMENT_IDENTIFIERS: "fetch_stable_identifiers",
        ProviderCapability.UNIVERSE_DISCOVERY: "discover_universe_page",
        ProviderCapability.OPTION_CHAIN: "fetch_option_chain",
        ProviderCapability.OPTION_QUOTE_HISTORY: "fetch_option_quote_history",
        ProviderCapability.CORPORATE_ACTIONS: "fetch_instrument_events",
        ProviderCapability.EARNINGS: "fetch_instrument_events",
        ProviderCapability.FUNDAMENTALS: "fetch_fundamental_facts",
        ProviderCapability.SHORT_INTEREST: "fetch_short_interest",
        ProviderCapability.FUTURES_HISTORY: "fetch_latest_ohlcv",
        ProviderCapability.CRYPTO_HISTORY: "fetch_latest_ohlcv",
        ProviderCapability.OPTIONS_CURRENT: "fetch_option_chain",
        ProviderCapability.MARKET_EVENTS: "fetch_market_events",
    }.get(capability)
    if method_name is None:
        raise RuntimeError(f"no representative probe contract for {capability.value}")
    method = getattr(provider, method_name)
    args = (
        {"query": request["query"], "limit": request["limit"]}
        if capability == ProviderCapability.INSTRUMENT_SEARCH
        else {}
    )
    if capability in {
        ProviderCapability.INSTRUMENT_METADATA,
        ProviderCapability.LATEST_PRICE,
        ProviderCapability.INSTRUMENT_EVENTS,
        ProviderCapability.INSTRUMENT_IDENTIFIERS,
        ProviderCapability.OPTION_CHAIN,
        ProviderCapability.OPTION_QUOTE_HISTORY,
        ProviderCapability.CORPORATE_ACTIONS,
        ProviderCapability.EARNINGS,
        ProviderCapability.SHORT_INTEREST,
        ProviderCapability.OPTIONS_CURRENT,
        ProviderCapability.MARKET_EVENTS,
    }:
        args = {"symbol": request["symbol"]}
    if capability == ProviderCapability.PRICE_HISTORY:
        args = {"symbol": request["symbol"], "timeframe": Timeframe.D1, "limit": request["limit"]}
    if capability == ProviderCapability.UNIVERSE_DISCOVERY:
        args = {"quote_type": request["quote_type"], "offset": request["offset"]}
    if capability == ProviderCapability.FUNDAMENTALS:
        args = {"cik": request["cik"]}
    if capability in {ProviderCapability.FUTURES_HISTORY, ProviderCapability.CRYPTO_HISTORY}:
        args = {
            "symbol": request["symbol"],
            "timeframe": Timeframe.D1,
            "limit": request["limit"],
        }
    if capability == ProviderCapability.OPTION_QUOTE_HISTORY:
        now = datetime.now(UTC)
        args = {
            "symbol": request["symbol"],
            "start": now - timedelta(days=request["days"]),
            "end": now,
        }
    result = method(**args)
    return await result if inspect.isawaitable(result) else result


def provider_configured(source: DataSource, entitlement: ProviderEntitlement | None) -> bool:
    if entitlement and entitlement.authentication_required:
        config = source.config or {}
        if config.get("api_key") or config.get("credentials"):
            return True
        provider_key = f"{source.name.upper()}_API_KEY"
        return bool(getattr(settings, provider_key, ""))
    return True


def notification_due(
    *,
    mode: str,
    classification: str,
    success: bool,
    consecutive_failures: int,
    last_notification_kind: str | None,
    last_notification_at: datetime | None,
    now: datetime,
) -> str | None:
    """Return the OneSignal transition to emit, if any.

    A first failure is always durable in Settings but does not notify. Core
    failures notify on the second consecutive observation; weekly sweeps notify
    only on an explicit schema/content regression. Recovery is emitted only for
    a failure that previously generated a notification.
    """

    if success:
        return "recovery" if last_notification_kind == "failure" else None
    eligible = (mode == "daily_core" and consecutive_failures >= 2) or (
        mode == "weekly_supported_sweep" and classification == "schema_content_incompatibility"
    )
    if not eligible:
        return None
    if last_notification_kind != "failure" or last_notification_at is None:
        return "failure"
    cooldown = timedelta(
        seconds=max(0, settings.PROVIDER_AVAILABILITY_NOTIFICATION_COOLDOWN_SECONDS)
    )
    return "failure" if now - last_notification_at >= cooldown else None


async def run_availability_probes(
    db: AsyncSession,
    mode: str,
    *,
    probe: Probe | None = None,
    application_version: str = "unknown",
) -> dict[str, Any]:
    if mode not in {"daily_core", "weekly_supported_sweep"}:
        raise ValueError("mode must be daily_core or weekly_supported_sweep")
    started = datetime.now(UTC)
    run = ProviderAvailabilityRun(
        mode=mode,
        status="running",
        application_version=application_version,
        probe_contract_version="v1",
        started_at=started,
    )
    db.add(run)
    await db.flush()
    query = (
        select(ProviderPolicy, DataSource, ProviderEntitlement)
        .join(DataSource, DataSource.id == ProviderPolicy.data_source_id)
        .outerjoin(
            ProviderEntitlement,
            (ProviderEntitlement.data_source_id == ProviderPolicy.data_source_id)
            & (ProviderEntitlement.capability == ProviderPolicy.capability),
        )
        .where(ProviderPolicy.is_enabled.is_(True), DataSource.is_active.is_(True))
    )
    rows = (await db.execute(query)).all()
    if mode == "daily_core":
        rows = [row for row in rows if row[0].is_pinned or row[0].base_priority <= 20]
    observations: list[ProviderAvailabilityObservation] = []
    provider_locks: dict[str, asyncio.Lock] = {}
    for policy, source, entitlement in rows:
        request = representative_request(policy.capability)
        classification = "success"
        success = False
        error_message = None
        value: Any = None
        started_probe = time.perf_counter()
        if entitlement and (
            not entitlement.is_free or entitlement.configured_plan in {"excluded", "unreviewed"}
        ):
            classification = "entitlement_exclusion"
        elif not provider_configured(source, entitlement):
            classification = "not_configured"
        else:
            try:
                lock = provider_locks.setdefault(source.name, asyncio.Lock())
                async with lock:
                    value = await asyncio.wait_for(
                        (probe or default_probe)(source.name, policy.capability, request),
                        timeout=max(0.1, settings.PROVIDER_AVAILABILITY_PROBE_TIMEOUT_SECONDS),
                    )
                classification = classify_response(value)
                success = classification == "success"
            except Exception as exc:  # noqa: BLE001 - classification is the durable contract.
                classification = classify_exception(exc)
                error_message = str(exc)[:1000]
        previous = (
            await db.execute(
                select(ProviderAvailabilityObservation)
                .where(
                    ProviderAvailabilityObservation.data_source_id == source.id,
                    ProviderAvailabilityObservation.capability == policy.capability,
                )
                .order_by(desc(ProviderAvailabilityObservation.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        excluded = classification in {"not_configured", "entitlement_exclusion"}
        effective_failure = not success and not excluded
        streak = (
            0 if success or excluded else int(previous.consecutive_failures if previous else 0) + 1
        )
        recovered = bool(success and previous and previous.consecutive_failures > 0)
        health = (
            await db.execute(
                select(ProviderHealthState).where(
                    ProviderHealthState.data_source_id == source.id,
                    ProviderHealthState.capability == policy.capability,
                )
            )
        ).scalar_one_or_none()
        if health is None:
            health = ProviderHealthState(
                data_source_id=source.id,
                capability=policy.capability,
            )
            db.add(health)
            await db.flush()
        observed_at = datetime.now(UTC)
        notification_kind = notification_due(
            mode=mode,
            classification=classification,
            success=success,
            consecutive_failures=streak,
            last_notification_kind=health.last_notification_kind,
            last_notification_at=health.last_notification_at,
            now=observed_at,
        )
        if success:
            health.failure_streak = 0
            health.last_success_at = observed_at
            health.last_error_type = None
            health.last_error_message = None
        elif effective_failure:
            health.failure_streak = streak
            health.last_failure_at = observed_at
            health.last_error_type = classification
            health.last_error_message = error_message
        observation = ProviderAvailabilityObservation(
            run_id=run.id,
            data_source_id=source.id,
            capability=policy.capability,
            representative_request=request,
            latency_ms=round((time.perf_counter() - started_probe) * 1000),
            success=success,
            classification=classification,
            # Preserve shape evidence for empty/partial responses as well as
            # successes; exceptions still record an explicit null shape.
            response_shape=response_shape(value),
            consecutive_failures=streak,
            recovered=recovered,
            error_message=error_message,
        )
        db.add(observation)
        observations.append(observation)
        if notification_kind and settings.PROVIDER_AVAILABILITY_NOTIFICATIONS_ENABLED:
            notification_id = await send_provider_availability_notification(
                source.name,
                policy.capability.value,
                classification,
                recovered=notification_kind == "recovery",
            )
            if notification_id:
                health.last_notification_at = observed_at
                health.last_notification_kind = notification_kind
                health.notified_failure_streak = streak if notification_kind == "failure" else 0
    run.status = "completed"
    run.finished_at = datetime.now(UTC)
    await db.commit()
    return {
        "run_id": run.id,
        "mode": mode,
        "observations": len(observations),
        "failures": sum(not item.success for item in observations),
    }


async def latest_availability(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(ProviderAvailabilityObservation, DataSource, ProviderHealthState)
            .join(DataSource, DataSource.id == ProviderAvailabilityObservation.data_source_id)
            .outerjoin(
                ProviderHealthState,
                (
                    ProviderHealthState.data_source_id
                    == ProviderAvailabilityObservation.data_source_id
                )
                & (ProviderHealthState.capability == ProviderAvailabilityObservation.capability),
            )
            .order_by(desc(ProviderAvailabilityObservation.created_at))
        )
    ).all()
    seen: set[tuple[int, ProviderCapability]] = set()
    result = []
    for observation, source, health in rows:
        key = (source.id, observation.capability)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "provider": source.name,
                "capability": observation.capability.value,
                "classification": observation.classification,
                "success": observation.success,
                "latency_ms": observation.latency_ms,
                "consecutive_failures": observation.consecutive_failures,
                "recovered": observation.recovered,
                "error_message": observation.error_message,
                "observed_at": observation.created_at,
                "last_success_at": health.last_success_at if health else None,
                "last_failure_at": health.last_failure_at if health else None,
                "response_shape": observation.response_shape,
            }
        )
    return result


async def recent_availability_runs(db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    """Return bounded sweep history for operators without exposing probe payloads."""
    rows = (
        await db.execute(
            select(ProviderAvailabilityRun)
            .order_by(desc(ProviderAvailabilityRun.started_at))
            .limit(max(1, min(limit, 50)))
        )
    ).scalars()
    return [
        {
            "id": run.id,
            "mode": run.mode,
            "status": run.status,
            "application_version": run.application_version,
            "probe_contract_version": run.probe_contract_version,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "error": run.error,
        }
        for run in rows
    ]
