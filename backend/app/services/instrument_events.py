from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any

import yfinance as yf
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.instrument_event import (
    EventTimeHint,
    InstrumentEvent,
    InstrumentEventFetchState,
    InstrumentEventType,
)
from app.providers import get_default_event_provider

logger = logging.getLogger(__name__)

EVENT_FETCH_VERSION = 2
_fetch_state_schema_checked = False


def _safe_decimal(val: Any) -> Decimal | None:
    try:
        f = float(val)
        if f != f:
            return None
        return Decimal(str(f))
    except (TypeError, ValueError):
        return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "to_dict"):
        try:
            return _jsonable(value.to_dict())
        except Exception:
            return str(value)
    try:
        if value != value:
            return None
    except Exception:
        pass
    if isinstance(value, Decimal):
        return float(value)
    return value


def _normalized_key(value: Any) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _find_by_key(value: Any, key: str, *, depth: int = 0) -> Any:
    if value is None or depth > 4:
        return None
    target = _normalized_key(key)

    if isinstance(value, dict):
        for k, v in value.items():
            if _normalized_key(k) == target:
                return v
        for v in value.values():
            found = _find_by_key(v, key, depth=depth + 1)
            if found is not None:
                return found
        return None

    if hasattr(value, "to_dict"):
        try:
            return _find_by_key(value.to_dict(), key, depth=depth + 1)
        except Exception:
            return None

    return None


def _calendar_value(calendar: Any, key: str) -> Any:
    return _find_by_key(calendar, key)


def _row_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        found = _find_by_key(row, key)
        if found is not None:
            return found
    return None


def _iter_dates(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str) or isinstance(value, datetime) or hasattr(value, "to_pydatetime"):
        return [value]
    if isinstance(value, dict):
        out: list[Any] = []
        for v in value.values():
            out.extend(_iter_dates(v))
        return out
    if hasattr(value, "dropna"):
        try:
            return _iter_dates(list(value.dropna()))
        except Exception:
            pass
    if isinstance(value, list | tuple | set):
        out = []
        for item in value:
            out.extend(_iter_dates(item))
        return out
    return [value]


def _event_time(value: Any) -> tuple[datetime, EventTimeHint] | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif hasattr(value, "to_pydatetime"):
        dt = value.to_pydatetime()
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)

    local_t = dt.time()
    if local_t == time(0, 0):
        hint = EventTimeHint.UNKNOWN
    elif local_t < time(14, 30):
        hint = EventTimeHint.PRE_MARKET
    elif local_t >= time(20, 0):
        hint = EventTimeHint.POST_MARKET
    else:
        hint = EventTimeHint.DURING_MARKET
    return dt, hint


def _payload(row: dict[str, Any]) -> str:
    return json.dumps({k: _jsonable(v) for k, v in row.items()}, sort_keys=True)


def _append_earnings_events(
    symbol: str,
    earnings: Any,
    fetched_at: datetime,
    events: list[dict[str, Any]],
) -> tuple[int, int]:
    if earnings is None:
        return 0, 0
    if hasattr(earnings, "empty") and earnings.empty:
        return 0, 0
    if not hasattr(earnings, "iterrows"):
        return 0, 0

    added = 0
    seen = 0
    for idx, row in earnings.iterrows():
        seen += 1
        parsed = _event_time(idx)
        if not parsed:
            parsed = _event_time(_row_value(row.to_dict(), "Earnings Date", "EarningsDate"))
        if not parsed:
            continue

        dt, hint = parsed
        row_dict = row.to_dict()
        eps_est = _safe_decimal(_row_value(row_dict, "EPS Estimate", "EPSEstimate", "Earnings Average"))
        eps_actual = _safe_decimal(_row_value(row_dict, "Reported EPS", "ReportedEPS", "EPS Actual"))
        surprise = _safe_decimal(_row_value(row_dict, "Surprise", "EPS Surprise"))
        surprise_pct = _safe_decimal(_row_value(row_dict, "Surprise(%)", "Surprise %", "EPSSurprisePct"))
        if surprise is None and eps_est is not None and eps_actual is not None:
            surprise = eps_actual - eps_est
        if surprise_pct is None and surprise is not None and eps_est not in (None, 0):
            surprise_pct = surprise / abs(eps_est)
        if surprise_pct is not None and abs(surprise_pct) > 2:
            surprise_pct = surprise_pct / Decimal("100")

        is_estimate = eps_actual is None
        source_event_key = f"earnings:{dt.isoformat()}"
        if any(event.get("source_event_key") == source_event_key for event in events):
            continue
        events.append({
            "event_type": InstrumentEventType.EARNINGS_ESTIMATE if is_estimate else InstrumentEventType.EARNINGS,
            "event_time": dt,
            "time_hint": hint,
            "title": f"{symbol} Earnings",
            "value": eps_est,
            "actual": eps_actual,
            "eps_estimate": eps_est,
            "eps_actual": eps_actual,
            "eps_surprise": surprise,
            "eps_surprise_pct": surprise_pct,
            "source_event_key": source_event_key,
            "raw_payload": _payload(row_dict),
            "fetched_at": fetched_at,
        })
        added += 1
    return added, seen


def _fetch_yfinance_events_sync(symbol: str) -> list[dict[str, Any]]:
    ticker = yf.Ticker(symbol)
    fetched_at = datetime.now(UTC)
    events: list[dict[str, Any]] = []

    try:
        cal = ticker.calendar
        earnings_date = _calendar_value(cal, "Earnings Date")
        for d in _iter_dates(earnings_date):
            parsed = _event_time(d)
            if not parsed:
                continue
            dt, hint = parsed
            eps_est = _safe_decimal(_calendar_value(cal, "Earnings Average"))
            events.append({
                "event_type": InstrumentEventType.EARNINGS_ESTIMATE,
                "event_time": dt,
                "time_hint": hint,
                "title": f"{symbol} Earnings (estimated)",
                "value": eps_est,
                "eps_estimate": eps_est,
                "source_event_key": f"earnings:{dt.isoformat()}",
                "raw_payload": _payload(cal if isinstance(cal, dict) else {"calendar": cal}),
                "fetched_at": fetched_at,
            })

        ex_div = _calendar_value(cal, "Ex-Dividend Date")
        for d in _iter_dates(ex_div):
            parsed = _event_time(d)
            if parsed:
                dt, hint = parsed
                amount = _safe_decimal(_calendar_value(cal, "Dividend Amount"))
                events.append({
                    "event_type": InstrumentEventType.EX_DIVIDEND,
                    "event_time": dt,
                    "time_hint": hint,
                    "title": f"{symbol} Ex-Dividend",
                    "value": amount,
                    "dividend_amount": amount,
                    "source_event_key": f"ex_dividend:{dt.date().isoformat()}",
                    "raw_payload": _payload(cal if isinstance(cal, dict) else {"calendar": cal}),
                    "fetched_at": fetched_at,
                })

        div_date = _calendar_value(cal, "Dividend Date")
        for d in _iter_dates(div_date):
            parsed = _event_time(d)
            if parsed:
                dt, hint = parsed
                amount = _safe_decimal(_calendar_value(cal, "Dividend Amount"))
                events.append({
                    "event_type": InstrumentEventType.DIVIDEND,
                    "event_time": dt,
                    "time_hint": hint,
                    "title": f"{symbol} Dividend",
                    "value": amount,
                    "actual": amount,
                    "dividend_amount": amount,
                    "source_event_key": f"dividend:{dt.date().isoformat()}",
                    "raw_payload": _payload(cal if isinstance(cal, dict) else {"calendar": cal}),
                    "fetched_at": fetched_at,
                })
    except Exception as exc:
        logger.debug("yfinance calendar fetch failed for %s: %s", symbol, exc)

    try:
        get_earnings_dates = getattr(ticker, "get_earnings_dates", None)
        if callable(get_earnings_dates):
            limit = 100
            for offset in range(0, 400, limit):
                try:
                    earnings_page = get_earnings_dates(limit=limit, offset=offset)
                except TypeError:
                    earnings_page = get_earnings_dates()
                added, seen = _append_earnings_events(symbol, earnings_page, fetched_at, events)
                if seen < limit or added == 0:
                    break
    except Exception as exc:
        logger.debug("yfinance get_earnings_dates fetch failed for %s: %s", symbol, exc)

    try:
        earnings = ticker.earnings_dates
        _append_earnings_events(symbol, earnings, fetched_at, events)
    except Exception as exc:
        logger.debug("yfinance earnings_dates fetch failed for %s: %s", symbol, exc)

    try:
        divs = ticker.dividends
        if divs is not None and not divs.empty:
            for idx, amount_raw in divs.items():
                parsed = _event_time(idx)
                if parsed:
                    dt, hint = parsed
                    amount = _safe_decimal(amount_raw)
                    events.append({
                        "event_type": InstrumentEventType.DIVIDEND,
                        "event_time": dt,
                        "time_hint": hint,
                        "title": f"{symbol} Dividend",
                        "value": amount,
                        "actual": amount,
                        "dividend_amount": amount,
                        "source_event_key": f"dividend:{dt.date().isoformat()}",
                        "raw_payload": _payload({"amount": amount}),
                        "fetched_at": fetched_at,
                    })
    except Exception as exc:
        logger.debug("yfinance dividends fetch failed for %s: %s", symbol, exc)

    try:
        splits = ticker.splits
        if splits is not None and not splits.empty:
            for idx, ratio_raw in splits.items():
                parsed = _event_time(idx)
                if not parsed:
                    continue
                dt, hint = parsed
                ratio = _safe_decimal(ratio_raw)
                events.append({
                    "event_type": InstrumentEventType.SPLIT,
                    "event_time": dt,
                    "time_hint": hint,
                    "title": f"{symbol} Stock Split",
                    "value": ratio,
                    "actual": ratio,
                    "split_ratio": ratio,
                    "source_event_key": f"split:{dt.date().isoformat()}",
                    "raw_payload": _payload({"ratio": ratio}),
                    "fetched_at": fetched_at,
                })
    except Exception as exc:
        logger.debug("yfinance splits fetch failed for %s: %s", symbol, exc)

    deduped: dict[str, dict[str, Any]] = {}
    for event in events:
        deduped[event["source_event_key"]] = event
    return list(deduped.values())


async def _ensure_fetch_state_schema(db: AsyncSession) -> None:
    global _fetch_state_schema_checked
    if _fetch_state_schema_checked:
        return

    conn = await db.connection()

    def _needs_fetch_version(sync_conn) -> bool:
        inspector = inspect(sync_conn)
        if "instrument_event_fetch_state" not in inspector.get_table_names():
            return False
        columns = {column["name"] for column in inspector.get_columns("instrument_event_fetch_state")}
        return "fetch_version" not in columns

    if await conn.run_sync(_needs_fetch_version):
        await db.execute(
            text(
                "ALTER TABLE instrument_event_fetch_state "
                "ADD COLUMN IF NOT EXISTS fetch_version INTEGER NOT NULL DEFAULT 1"
            )
        )
        await db.flush()

    _fetch_state_schema_checked = True


async def fetch_and_store_instrument_events(db: AsyncSession, instrument: Instrument) -> int:
    if instrument.is_synthetic:
        return 0
    await _ensure_fetch_state_schema(db)
    provider = get_default_event_provider()

    events = await asyncio.get_event_loop().run_in_executor(
        None,
        provider.fetch_instrument_events,
        instrument.symbol,
    )
    fetched_at = max((event.fetched_at for event in events), default=datetime.now(UTC))
    earnings_count = sum(1 for event in events if event.event_type in {
        InstrumentEventType.EARNINGS,
        InstrumentEventType.EARNINGS_ESTIMATE,
    })

    inserted = 0
    for event in events:
        values = {
            "event_type": event.event_type,
            "event_time": event.event_time,
            "time_hint": event.time_hint,
            "title": event.title,
            "value": event.value,
            "actual": event.actual,
            "eps_estimate": event.eps_estimate,
            "eps_actual": event.eps_actual,
            "eps_surprise": event.eps_surprise,
            "eps_surprise_pct": event.eps_surprise_pct,
            "dividend_amount": event.dividend_amount,
            "split_ratio": event.split_ratio,
            "source_event_key": event.source_event_key,
            "raw_payload": event.raw_payload,
            "fetched_at": event.fetched_at,
            "instrument_id": instrument.id,
            "source": provider.name,
            "currency": instrument.currency,
        }
        stmt = (
            pg_insert(InstrumentEvent)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_instrument_event_source_key",
                set_={
                    "event_type": values["event_type"],
                    "event_time": values["event_time"],
                    "time_hint": values["time_hint"],
                    "title": values["title"],
                    "value": values.get("value"),
                    "actual": values.get("actual"),
                    "eps_estimate": values.get("eps_estimate"),
                    "eps_actual": values.get("eps_actual"),
                    "eps_surprise": values.get("eps_surprise"),
                    "eps_surprise_pct": values.get("eps_surprise_pct"),
                    "dividend_amount": values.get("dividend_amount"),
                    "split_ratio": values.get("split_ratio"),
                    "currency": values.get("currency"),
                    "raw_payload": values.get("raw_payload"),
                    "fetched_at": values["fetched_at"],
                },
            )
        )
        await db.execute(stmt)
        inserted += 1

    state_stmt = (
        pg_insert(InstrumentEventFetchState)
        .values(
            instrument_id=instrument.id,
            source=provider.name,
            fetched_at=fetched_at,
            event_count=len(events),
            earnings_count=earnings_count,
            fetch_version=EVENT_FETCH_VERSION,
        )
        .on_conflict_do_update(
            constraint="uq_instrument_event_fetch_state_source",
            set_={
                "fetched_at": fetched_at,
                "event_count": len(events),
                "earnings_count": earnings_count,
                "fetch_version": EVENT_FETCH_VERSION,
            },
        )
    )
    await db.execute(state_stmt)
    await db.flush()
    return inserted


async def ensure_instrument_events_loaded(
    db: AsyncSession,
    instrument: Instrument,
    *,
    refresh: bool = False,
) -> None:
    if instrument.is_synthetic:
        return
    await _ensure_fetch_state_schema(db)
    provider = get_default_event_provider()
    state = (
        await db.execute(
            select(InstrumentEventFetchState).where(
                InstrumentEventFetchState.instrument_id == instrument.id,
                InstrumentEventFetchState.source == provider.name,
            )
        )
    ).scalar_one_or_none()
    if refresh or state is None or state.fetch_version < EVENT_FETCH_VERSION:
        await fetch_and_store_instrument_events(db, instrument)


async def query_instrument_events(
    db: AsyncSession,
    instrument: Instrument,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[InstrumentEvent]:
    stmt = select(InstrumentEvent).where(InstrumentEvent.instrument_id == instrument.id)
    if start is not None:
        stmt = stmt.where(InstrumentEvent.event_time >= start)
    if end is not None:
        stmt = stmt.where(InstrumentEvent.event_time <= end)
    stmt = stmt.order_by(InstrumentEvent.event_time.desc(), InstrumentEvent.event_type)
    return (await db.execute(stmt)).scalars().all()
