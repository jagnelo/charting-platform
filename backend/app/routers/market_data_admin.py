"""Backend-only market-data governance and diagnostics endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.exchange import Exchange
from app.models.market_data_foundation import (
    ExchangeCalendarException,
    ExchangeSessionRule,
    FundamentalFact,
    InstrumentIdentityQuarantine,
    MarketCoverageSnapshot,
    MarketDataAnomaly,
    MarketEvent,
    MarketSeries,
    MarketUniverseLifecycleObservation,
    MarketUniverseReconciliationRun,
    ProviderQuotaWindow,
    ProviderRoutingDecision,
    ProviderShadowObservation,
    ShortInterestObservation,
)
from app.models.provider_runtime import ProviderCapability, ProviderCapacityEvent
from app.models.user import User
from app.services.market_data_monitoring import build_shadow_report

router = APIRouter(prefix="/market-data", tags=["market-data-admin"])


@router.get("/identity/quarantine")
async def list_identity_quarantine(
    status: str | None = Query(default="pending"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = (
        select(InstrumentIdentityQuarantine)
        .order_by(InstrumentIdentityQuarantine.created_at.desc())
        .limit(limit)
    )
    if status:
        query = query.where(InstrumentIdentityQuarantine.status == status)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "status": row.status,
            "provider": row.provider_name,
            "provider_symbol": row.provider_symbol,
            "exchange_mic": row.exchange_mic,
            "proposed_domain_key": row.proposed_domain_key,
            "reason": row.reason,
            "candidate_payload": row.candidate_payload,
            "instrument_id": row.instrument_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/series/{instrument_id}")
async def list_market_series(
    instrument_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    rows = (
        (
            await db.execute(
                select(MarketSeries)
                .where(MarketSeries.instrument_id == instrument_id)
                .order_by(MarketSeries.timeframe, MarketSeries.session_code, MarketSeries.id)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "instrument_id": row.instrument_id,
            "exchange_id": row.exchange_id,
            "data_source_id": row.data_source_id,
            "feed_scope": row.feed_scope,
            "session": row.session_code,
            "timeframe": row.timeframe,
            "adjustment_basis": row.adjustment_basis.value,
            "adjustment_version": row.adjustment_version,
            "is_canonical": row.is_canonical,
            "provenance": row.provenance,
        }
        for row in rows
    ]


@router.get("/sessions/{exchange_id}")
async def list_exchange_sessions(
    exchange_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    exchange = await db.get(Exchange, exchange_id)
    if exchange is None:
        return {"exchange_id": exchange_id, "rules": [], "exceptions": []}
    rules = (
        (
            await db.execute(
                select(ExchangeSessionRule)
                .where(ExchangeSessionRule.exchange_id == exchange_id)
                .order_by(ExchangeSessionRule.valid_from, ExchangeSessionRule.weekday)
            )
        )
        .scalars()
        .all()
    )
    exceptions = (
        (
            await db.execute(
                select(ExchangeCalendarException)
                .where(ExchangeCalendarException.exchange_id == exchange_id)
                .order_by(ExchangeCalendarException.session_date)
            )
        )
        .scalars()
        .all()
    )
    return {
        "exchange": {"id": exchange.id, "mic": exchange.mic, "timezone": exchange.timezone},
        "rules": [
            {
                "session": row.session_code,
                "weekday": row.weekday,
                "opens_at": row.opens_at,
                "closes_at": row.closes_at,
                "crosses_midnight": row.crosses_midnight,
                "trade_date_rule": row.trade_date_rule,
                "valid_from": row.valid_from,
                "valid_to": row.valid_to,
                "provenance": row.provenance,
            }
            for row in rules
        ],
        "exceptions": [
            {
                "date": row.session_date,
                "session": row.session_code,
                "kind": row.exception_kind.value,
                "opens_at": row.opens_at,
                "closes_at": row.closes_at,
                "reason": row.reason,
                "source": row.source,
                "provenance": row.provenance,
            }
            for row in exceptions
        ],
    }


@router.get("/quota")
async def list_provider_quota(
    provider_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = (
        select(ProviderQuotaWindow)
        .order_by(ProviderQuotaWindow.window_started_at.desc())
        .limit(limit)
    )
    if provider_id is not None:
        query = query.where(ProviderQuotaWindow.data_source_id == provider_id)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "data_source_id": row.data_source_id,
            "capability": row.capability,
            "dimension": row.dimension,
            "window_started_at": row.window_started_at,
            "window_seconds": row.window_seconds,
            "limit_units": row.limit_units,
            "reserved_units": row.reserved_units,
            "consumed_units": row.consumed_units,
            "cost_cents": row.cost_cents,
        }
        for row in rows
    ]


@router.get("/capacity-events")
async def list_provider_capacity_events(
    provider_id: int | None = None,
    capability: ProviderCapability | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List typed 429/418/quota rejections and their provider reset evidence."""

    query = (
        select(ProviderCapacityEvent)
        .order_by(ProviderCapacityEvent.observed_at.desc())
        .limit(limit)
    )
    if provider_id is not None:
        query = query.where(ProviderCapacityEvent.data_source_id == provider_id)
    if capability is not None:
        query = query.where(ProviderCapacityEvent.capability == capability)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "data_source_id": row.data_source_id,
            "capability": row.capability.value,
            "operation": row.operation,
            "scope": row.scope,
            "status_code": row.status_code,
            "error_type": row.error_type,
            "message": row.message,
            "retry_at": row.retry_at,
            "response_headers": row.response_headers,
            "observed_at": row.observed_at,
            "request_log_id": row.request_log_id,
        }
        for row in rows
    ]


@router.get("/routing/decisions")
async def list_routing_decisions(
    request_key: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = (
        select(ProviderRoutingDecision)
        .order_by(ProviderRoutingDecision.created_at.desc())
        .limit(limit)
    )
    if request_key:
        query = query.where(ProviderRoutingDecision.request_key == request_key)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "request_key": row.request_key,
            "capability": row.capability,
            "instrument_id": row.instrument_id,
            "selected_data_source_id": row.selected_data_source_id,
            "candidates": row.candidates,
            "rejected": row.rejected,
            "workload_key": row.workload_key,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/events")
async def list_market_events(
    instrument_id: int | None = None,
    event_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = select(MarketEvent).order_by(MarketEvent.event_time.desc().nullslast()).limit(limit)
    if instrument_id is not None:
        query = query.where(MarketEvent.instrument_id == instrument_id)
    if event_type:
        query = query.where(MarketEvent.event_type == event_type)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "event_key": row.event_key,
            "instrument_id": row.instrument_id,
            "issuer_id": row.issuer_id,
            "event_time": row.event_time,
            "effective_date": row.effective_date,
            "source": row.source,
            "is_provisional": row.is_provisional,
            "payload": row.payload,
        }
        for row in rows
    ]


@router.get("/fundamentals")
async def list_fundamental_facts(
    issuer_id: int | None = None,
    instrument_id: int | None = None,
    fact_key: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = (
        select(FundamentalFact).order_by(FundamentalFact.filed_at.desc().nullslast()).limit(limit)
    )
    if issuer_id is not None:
        query = query.where(FundamentalFact.issuer_id == issuer_id)
    if instrument_id is not None:
        query = query.where(FundamentalFact.instrument_id == instrument_id)
    if fact_key:
        query = query.where(FundamentalFact.fact_key == fact_key)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "issuer_id": row.issuer_id,
            "instrument_id": row.instrument_id,
            "namespace": row.fact_namespace,
            "key": row.fact_key,
            "unit": row.unit,
            "value_numeric": row.value_numeric,
            "value_text": row.value_text,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "filed_at": row.filed_at,
            "accepted_at": row.accepted_at,
            "source": row.source,
            "source_identifier": row.source_identifier,
        }
        for row in rows
    ]


@router.get("/short-interest/{instrument_id}")
async def list_short_interest(
    instrument_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    rows = (
        (
            await db.execute(
                select(ShortInterestObservation)
                .where(ShortInterestObservation.instrument_id == instrument_id)
                .order_by(ShortInterestObservation.settlement_date.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "settlement_date": row.settlement_date,
            "publication_date": row.publication_date,
            "short_position": row.short_position,
            "short_percent_float": row.short_percent_float,
            "days_to_cover": row.days_to_cover,
            "source": row.source,
            "source_identifier": row.source_identifier,
            "payload": row.payload,
        }
        for row in rows
    ]


@router.get("/coverage")
async def list_market_coverage(
    instrument_id: int | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = (
        select(MarketCoverageSnapshot)
        .order_by(MarketCoverageSnapshot.evaluated_at.desc())
        .limit(limit)
    )
    if instrument_id is not None:
        query = query.where(MarketCoverageSnapshot.instrument_id == instrument_id)
    if status:
        query = query.where(MarketCoverageSnapshot.status == status)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "instrument_id": row.instrument_id,
            "market_series_id": row.market_series_id,
            "timeframe": row.timeframe,
            "expected_start": row.expected_start,
            "expected_end": row.expected_end,
            "expected_bars": row.expected_bars,
            "observed_bars": row.observed_bars,
            "coverage_ratio": row.coverage_ratio,
            "status": row.status,
            "missing_slices": row.missing_slices,
            "evaluated_at": row.evaluated_at,
            "provenance": row.provenance,
        }
        for row in rows
    ]


@router.get("/universe/runs")
async def list_universe_reconciliation_runs(
    provider_id: int | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = (
        select(MarketUniverseReconciliationRun)
        .order_by(MarketUniverseReconciliationRun.observed_at.desc())
        .limit(limit)
    )
    if provider_id is not None:
        query = query.where(MarketUniverseReconciliationRun.data_source_id == provider_id)
    if status:
        query = query.where(MarketUniverseReconciliationRun.status == status)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "data_source_id": row.data_source_id,
            "quote_type": row.quote_type,
            "observed_at": row.observed_at,
            "finished_at": row.finished_at,
            "status": row.status,
            "expected_count": row.expected_count,
            "observed_count": row.observed_count,
            "new_count": row.new_count,
            "updated_count": row.updated_count,
            "missing_count": row.missing_count,
            "deactivated_count": row.deactivated_count,
            "quarantined_count": row.quarantined_count,
            "error": row.error,
            "provenance": row.provenance,
        }
        for row in rows
    ]


@router.get("/universe/lifecycle")
async def list_universe_lifecycle(
    provider_id: int | None = None,
    lifecycle_status: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = (
        select(MarketUniverseLifecycleObservation)
        .order_by(MarketUniverseLifecycleObservation.observed_at.desc())
        .limit(limit)
    )
    if provider_id is not None:
        query = query.where(MarketUniverseLifecycleObservation.data_source_id == provider_id)
    if lifecycle_status:
        query = query.where(MarketUniverseLifecycleObservation.lifecycle_status == lifecycle_status)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "data_source_id": row.data_source_id,
            "run_id": row.run_id,
            "instrument_id": row.instrument_id,
            "listing_id": row.listing_id,
            "provider_symbol": row.provider_symbol,
            "exchange_mic": row.exchange_mic,
            "quote_type": row.quote_type,
            "observed_at": row.observed_at,
            "present": row.present,
            "lifecycle_status": row.lifecycle_status,
            "first_seen_at": row.first_seen_at,
            "last_seen_at": row.last_seen_at,
            "last_missing_at": row.last_missing_at,
            "consecutive_seen": row.consecutive_seen,
            "consecutive_missing": row.consecutive_missing,
            "payload": row.payload,
        }
        for row in rows
    ]


@router.get("/shadow")
async def get_market_data_shadow_report(
    since: datetime | None = None,
    capability: str | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return await build_shadow_report(db, since=since, capability=capability)


@router.get("/shadow/observations")
async def list_shadow_observations(
    capability: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = (
        select(ProviderShadowObservation)
        .order_by(ProviderShadowObservation.observed_at.desc())
        .limit(limit)
    )
    if capability:
        query = query.where(ProviderShadowObservation.capability == capability)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "request_key": row.request_key,
            "capability": row.capability,
            "instrument_id": row.instrument_id,
            "primary_data_source_id": row.primary_data_source_id,
            "alternate_data_source_id": row.alternate_data_source_id,
            "comparison_status": row.comparison_status,
            "discrepancy_metrics": row.discrepancy_metrics,
            "routing_enabled": row.routing_enabled,
            "observed_at": row.observed_at,
            "provenance": row.provenance,
        }
        for row in rows
    ]


@router.get("/anomalies")
async def list_market_data_anomalies(
    status: str | None = Query(default="open"),
    severity: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = select(MarketDataAnomaly).order_by(MarketDataAnomaly.detected_at.desc()).limit(limit)
    if status:
        query = query.where(MarketDataAnomaly.status == status)
    if severity:
        query = query.where(MarketDataAnomaly.severity == severity)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "instrument_id": row.instrument_id,
            "market_series_id": row.market_series_id,
            "anomaly_type": row.anomaly_type,
            "severity": row.severity,
            "status": row.status,
            "detected_at": row.detected_at,
            "details": row.details,
            "source": row.source,
        }
        for row in rows
    ]
