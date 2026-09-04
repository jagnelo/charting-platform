"""Versioned exchange-session lookup used by refresh/freshness services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange import Exchange
from app.models.market_data_foundation import (
    CalendarExceptionKind,
    ExchangeCalendarException,
    ExchangeSessionRule,
)


@dataclass(frozen=True, slots=True)
class SessionWindow:
    exchange_id: int
    session_code: str
    trade_date: date
    opens_at: datetime
    closes_at: datetime
    source: str


async def resolve_session_window(
    db: AsyncSession,
    exchange_id: int,
    trade_date: date,
    *,
    session_code: str = "regular",
) -> SessionWindow | None:
    exchange = await db.get(Exchange, exchange_id)
    if exchange is None or not exchange.timezone:
        return None
    exception = (
        await db.execute(
            select(ExchangeCalendarException).where(
                ExchangeCalendarException.exchange_id == exchange_id,
                ExchangeCalendarException.session_date == trade_date,
                ExchangeCalendarException.session_code == session_code,
            )
        )
    ).scalar_one_or_none()
    if exception and exception.exception_kind in {
        CalendarExceptionKind.HOLIDAY,
        CalendarExceptionKind.CLOSED,
    }:
        return None
    rule = (
        await db.execute(
            select(ExchangeSessionRule)
            .where(
                ExchangeSessionRule.exchange_id == exchange_id,
                ExchangeSessionRule.session_code == session_code,
                ExchangeSessionRule.weekday == trade_date.weekday(),
                ExchangeSessionRule.valid_from <= trade_date,
                (ExchangeSessionRule.valid_to.is_(None) | (ExchangeSessionRule.valid_to >= trade_date)),
            )
            .order_by(ExchangeSessionRule.valid_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if rule is None:
        return None
    open_time = exception.opens_at if exception and exception.opens_at else rule.opens_at
    close_time = exception.closes_at if exception and exception.closes_at else rule.closes_at
    if open_time is None or close_time is None:
        return None
    zone = ZoneInfo(exchange.timezone)
    opens = datetime.combine(trade_date, open_time, tzinfo=zone)
    close_date = trade_date + timedelta(days=1) if rule.crosses_midnight else trade_date
    closes = datetime.combine(close_date, close_time, tzinfo=zone)
    return SessionWindow(
        exchange_id=exchange_id,
        session_code=session_code,
        trade_date=trade_date,
        opens_at=opens.astimezone(UTC),
        closes_at=closes.astimezone(UTC),
        source="calendar_exception" if exception else "session_rule",
    )


def project_to_user_timezone(timestamp: datetime, user_timezone: str) -> datetime:
    """Project an aware UTC timestamp to a validated IANA user timezone."""

    value = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=UTC)
    return value.astimezone(ZoneInfo(user_timezone))


def is_session_complete(window: SessionWindow, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current >= window.closes_at
