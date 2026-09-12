"""Durable, bounded SEC EDGAR issuer-universe pipeline scanning."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import Issuer, MarketEventScanState
from app.services.market_events import refresh_edgar_ipo_pipeline

_SCAN_KEY = "edgar:ipo_pipeline:issuer_universe"
_PROVIDER = "edgar"
_OPERATION = "fetch_ipo_pipeline_events"


def _validate_limit(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 500:
        raise ValueError(f"{name} must be between 1 and 500")


async def refresh_edgar_ipo_pipeline_for_issuer_universe(
    db: AsyncSession,
    *,
    start: date | None = None,
    end: date | None = None,
    max_issuers: int = 50,
    max_events_per_issuer: int = 100,
) -> dict[str, Any]:
    """Scan persisted SEC issuers in durable batches without hidden fan-out.

    EDGAR has no global IPO-calendar endpoint. This workflow therefore walks
    only issuers already present in the canonical ``issuer`` table, persists a
    cursor across worker/session restarts, and reports partial cycles instead
    of claiming global completeness when the bounded batch has not wrapped.
    """

    _validate_limit(max_issuers, "max_issuers")
    _validate_limit(max_events_per_issuer, "max_events_per_issuer")
    if start is not None and end is not None and end < start:
        raise ValueError("end must be on or after start")

    state = (
        await db.execute(
            select(MarketEventScanState)
            .where(MarketEventScanState.scan_key == _SCAN_KEY)
            .with_for_update()
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if state is None:
        state = MarketEventScanState(
            scan_key=_SCAN_KEY,
            provider=_PROVIDER,
            operation=_OPERATION,
            cycle_started_at=now,
            status="running",
            provenance={"algorithm": "edgar_ipo_pipeline_issuer_scan_v1"},
        )
        db.add(state)
        await db.flush()

    # A completed cycle starts the next invocation from the beginning.  Keep
    # this explicit in the response so operators can distinguish a fresh
    # cycle from the first ever scan, even though both use a NULL cursor.
    wrapped = state.cursor_issuer_id is None and state.cycle_count > 0
    if wrapped:
        state.cycle_started_at = now

    query = select(Issuer).where(Issuer.cik.is_not(None)).order_by(Issuer.id)
    if state.cursor_issuer_id is not None:
        query = query.where(Issuer.id > state.cursor_issuer_id)
    issuer_rows = (await db.execute(query.limit(max_issuers + 1))).scalars().all()
    if not issuer_rows and state.cursor_issuer_id is not None:
        wrapped = True
        state.cursor_issuer_id = None
        state.cycle_started_at = now
        issuer_rows = (
            await db.execute(
                select(Issuer)
                .where(Issuer.cik.is_not(None))
                .order_by(Issuer.id)
                .limit(max_issuers + 1)
            )
        ).scalars().all()

    truncated = len(issuer_rows) > max_issuers
    issuer_rows = issuer_rows[:max_issuers]
    if not issuer_rows:
        state.status = "complete"
        state.last_scanned_at = now
        state.last_batch_count = 0
        state.last_event_count = 0
        state.last_failure_count = 0
        state.last_error = None
        await db.commit()
        return {
            "status": "complete",
            "scan_key": _SCAN_KEY,
            "issuers_considered": 0,
            "events": 0,
            "failures": 0,
            "cursor_issuer_id": None,
            "cycle_complete": True,
            "wrapped": wrapped,
        }

    result = await refresh_edgar_ipo_pipeline(
        db,
        [str(issuer.cik) for issuer in issuer_rows if issuer.cik],
        start=start,
        end=end,
        max_ciks=max_issuers,
        max_events_per_issuer=max_events_per_issuer,
        commit=False,
    )
    cycle_complete = not truncated
    state.cursor_issuer_id = None if cycle_complete else issuer_rows[-1].id
    state.cycle_count += 1 if cycle_complete else 0
    state.scanned_count += len(issuer_rows)
    state.last_batch_count = len(issuer_rows)
    state.last_event_count = int(result.get("events", 0))
    state.last_failure_count = int(result.get("failures", 0))
    state.last_scanned_at = now
    state.status = "complete" if cycle_complete else "partial"
    state.last_error = (
        "one or more issuer pipeline reads failed" if state.last_failure_count else None
    )
    state.provenance = {
        "algorithm": "edgar_ipo_pipeline_issuer_scan_v1",
        "issuer_table_scope": "cik_not_null",
        "last_batch_issuer_ids": [issuer.id for issuer in issuer_rows],
        "last_batch_ciks": [str(issuer.cik) for issuer in issuer_rows],
        "window": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "wrapped": wrapped,
        "bounded": True,
    }
    await db.commit()
    return {
        **result,
        "scan_key": _SCAN_KEY,
        "issuers_considered": len(issuer_rows),
        "cursor_issuer_id": state.cursor_issuer_id,
        "cycle_complete": cycle_complete,
        "wrapped": wrapped,
    }
