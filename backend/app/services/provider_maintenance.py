from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.provider_observation import (
    InstrumentDatasetState,
    InstrumentIdentifierSnapshot,
    InstrumentProfileSnapshot,
    InstrumentSearchSnapshot,
    LatestPriceSnapshot,
    UniverseDiscoverySnapshot,
)
from app.models.provider_runtime import ProviderCapability, ProviderHealthState, ProviderRequestLog


def _now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _RetentionTarget:
    name: str
    model: Any
    ts_attr: str
    retention_days: int


def _targets() -> list[_RetentionTarget]:
    return [
        _RetentionTarget(
            "provider_request_log",
            ProviderRequestLog,
            "requested_at",
            settings.PROVIDER_REQUEST_LOG_RETENTION_DAYS,
        ),
        _RetentionTarget(
            "latest_price_snapshot",
            LatestPriceSnapshot,
            "observed_at",
            settings.LATEST_PRICE_SNAPSHOT_RETENTION_DAYS,
        ),
        _RetentionTarget(
            "instrument_search_snapshot",
            InstrumentSearchSnapshot,
            "observed_at",
            settings.INSTRUMENT_SEARCH_SNAPSHOT_RETENTION_DAYS,
        ),
        _RetentionTarget(
            "universe_discovery_snapshot",
            UniverseDiscoverySnapshot,
            "observed_at",
            settings.UNIVERSE_DISCOVERY_SNAPSHOT_RETENTION_DAYS,
        ),
        _RetentionTarget(
            "instrument_profile_snapshot",
            InstrumentProfileSnapshot,
            "observed_at",
            settings.INSTRUMENT_PROFILE_SNAPSHOT_RETENTION_DAYS,
        ),
        _RetentionTarget(
            "instrument_identifier_snapshot",
            InstrumentIdentifierSnapshot,
            "observed_at",
            settings.INSTRUMENT_IDENTIFIER_SNAPSHOT_RETENTION_DAYS,
        ),
    ]


async def summarize_provider_observations(db: AsyncSession) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for target in _targets():
        ts_column = getattr(target.model, target.ts_attr)
        row = (
            await db.execute(
                select(
                    func.count(target.model.id),
                    func.min(ts_column),
                    func.max(ts_column),
                )
            )
        ).one()
        summaries.append(
            {
                "dataset": target.name,
                "rows": int(row[0] or 0),
                "oldest_at": row[1],
                "newest_at": row[2],
                "retention_days": target.retention_days,
            }
        )
    return summaries


async def list_stale_dataset_states(
    db: AsyncSession,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    now = _now_utc()
    rows = (
        await db.execute(
            select(InstrumentDatasetState, Instrument, DataSource)
            .join(Instrument, Instrument.id == InstrumentDatasetState.instrument_id)
            .outerjoin(DataSource, DataSource.id == InstrumentDatasetState.data_source_id)
            .where(
                InstrumentDatasetState.stale_after.is_not(None),
                InstrumentDatasetState.stale_after < now,
            )
            .order_by(InstrumentDatasetState.stale_after.asc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "provider": data_source.name if data_source is not None else None,
            "dataset_type": state.dataset_type,
            "dataset_key": state.dataset_key,
            "status": state.status.value,
            "stale_after": state.stale_after,
            "observed_at": state.observed_at,
            "fetched_at": state.fetched_at,
            "extra_data": state.extra_data,
        }
        for state, instrument, data_source in rows
    ]


async def prune_provider_observations(db: AsyncSession) -> dict[str, int]:
    deleted: dict[str, int] = {}
    now = _now_utc()
    for target in _targets():
        if target.retention_days <= 0:
            deleted[target.name] = 0
            continue
        cutoff = now - timedelta(days=target.retention_days)
        result = await db.execute(
            delete(target.model).where(getattr(target.model, target.ts_attr) < cutoff)
        )
        deleted[target.name] = int(result.rowcount or 0)
    await db.flush()
    return deleted


async def reset_provider_health_state(
    db: AsyncSession,
    *,
    provider_name: str,
    capability: ProviderCapability,
) -> bool:
    row = (
        await db.execute(
            select(ProviderHealthState)
            .join(DataSource, DataSource.id == ProviderHealthState.data_source_id)
            .where(
                DataSource.name == provider_name,
                ProviderHealthState.capability == capability,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.failure_streak = 0
    row.circuit_open_until = None
    row.last_error_type = None
    row.last_error_message = None
    await db.flush()
    return True
