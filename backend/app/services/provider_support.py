from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.instrument_identity import (
    InstrumentProviderCapabilityStatus,
    InstrumentProviderSymbol,
)
from app.models.provider_runtime import ProviderCapability

SUPPORT_STATUS_SUPPORTED = "supported"
SUPPORT_STATUS_UNSUPPORTED = "unsupported"
SUPPORT_STATUS_UNKNOWN = "unknown"


@dataclass(slots=True)
class ProviderSupportState:
    data_source_id: int
    capability: ProviderCapability
    status: str
    provider_symbol: str | None
    expires_at: datetime | None


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _ttl_for(status: str) -> timedelta:
    if status == SUPPORT_STATUS_SUPPORTED:
        return timedelta(seconds=settings.PROVIDER_SUPPORT_SUPPORTED_TTL_SECONDS)
    return timedelta(seconds=settings.PROVIDER_SUPPORT_UNSUPPORTED_TTL_SECONDS)


def _effective_status(
    row: InstrumentProviderCapabilityStatus | None,
    *,
    now: datetime | None = None,
) -> str:
    if row is None:
        return SUPPORT_STATUS_UNKNOWN
    now = now or _now_utc()
    expires_at = _ensure_aware(row.status_expires_at)
    if expires_at is not None and expires_at <= now:
        return SUPPORT_STATUS_UNKNOWN
    return row.support_status


async def get_provider_binding_ids(
    db: AsyncSession,
    instrument_id: int,
) -> set[int]:
    rows = (
        await db.execute(
            select(InstrumentProviderSymbol.data_source_id).where(
                InstrumentProviderSymbol.instrument_id == instrument_id,
                InstrumentProviderSymbol.is_active.is_(True),
            )
        )
    ).scalars().all()
    return set(rows)


async def get_provider_support_map(
    db: AsyncSession,
    instrument_id: int,
    capability: ProviderCapability,
) -> dict[int, ProviderSupportState]:
    now = _now_utc()
    rows = (
        await db.execute(
            select(InstrumentProviderCapabilityStatus).where(
                InstrumentProviderCapabilityStatus.instrument_id == instrument_id,
                InstrumentProviderCapabilityStatus.capability == capability,
            )
        )
    ).scalars().all()
    return {
        row.data_source_id: ProviderSupportState(
            data_source_id=row.data_source_id,
            capability=row.capability,
            status=_effective_status(row, now=now),
            provider_symbol=row.provider_symbol,
            expires_at=_ensure_aware(row.status_expires_at),
        )
        for row in rows
    }


async def record_provider_support(
    db: AsyncSession,
    *,
    instrument_id: int,
    data_source_id: int,
    capability: ProviderCapability,
    status: str,
    provider_symbol: str | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> InstrumentProviderCapabilityStatus:
    row = (
        await db.execute(
            select(InstrumentProviderCapabilityStatus).where(
                InstrumentProviderCapabilityStatus.instrument_id == instrument_id,
                InstrumentProviderCapabilityStatus.data_source_id == data_source_id,
                InstrumentProviderCapabilityStatus.capability == capability,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = InstrumentProviderCapabilityStatus(
            instrument_id=instrument_id,
            data_source_id=data_source_id,
            capability=capability,
            support_status=status,
        )
        db.add(row)

    now = _now_utc()
    row.support_status = status
    row.provider_symbol = provider_symbol or row.provider_symbol
    row.last_checked_at = now
    row.status_expires_at = now + _ttl_for(status)
    row.last_error_type = error_type
    row.last_error_message = error_message[:500] if error_message else None
    if status == SUPPORT_STATUS_SUPPORTED:
        row.last_success_at = now
        row.last_error_type = None
        row.last_error_message = None
    elif status == SUPPORT_STATUS_UNSUPPORTED:
        row.last_failure_at = now
    await db.flush()
    return row
