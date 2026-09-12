"""Durable, bounded SEC EDGAR issuer-universe pipeline scanning."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import Issuer, MarketEventScanState
from app.models.provider_runtime import ProviderCapability
from app.providers.errors import bounded_redact_provider_message
from app.services.market_events import refresh_edgar_ipo_pipeline
from app.services.provider_runtime import execute_provider_call

_SCAN_KEY = "edgar:ipo_pipeline:issuer_universe"
_DIRECTORY_SCAN_KEY = "edgar:ipo_pipeline:sec_directory"
_PROVIDER = "edgar"
_OPERATION = "fetch_ipo_pipeline_events"
_DIRECTORY_OPERATION = "discover_issuer_ciks_page"
_ISSUER_MATERIALIZATION_MODES = frozenset({"disabled", "create_missing"})


def _validate_limit(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 500:
        raise ValueError(f"{name} must be between 1 and 500")


def _validate_issuer_materialization_mode(value: str) -> str:
    """Validate the explicit SEC directory issuer-materialization policy."""

    mode = str(value or "").strip().lower()
    if mode not in _ISSUER_MATERIALIZATION_MODES:
        allowed = ", ".join(sorted(_ISSUER_MATERIALIZATION_MODES))
        raise ValueError(f"issuer_materialization_mode must be one of: {allowed}")
    return mode


async def _materialize_directory_issuers(
    db: AsyncSession,
    rows: list[dict[str, Any]],
    *,
    mode: str,
    observed_at: datetime,
) -> tuple[int, int]:
    """Create missing issuer rows only when the operator selected that policy.

    The SEC directory provides issuer-level CIK/name evidence, not a complete
    security master. This policy therefore creates *only* missing ``Issuer``
    rows, never instruments/listings, never changes existing legal names, and
    never deactivates anything. ``disabled`` performs no database writes.
    """

    if mode == "disabled" or not rows:
        return 0, 0

    names_by_cik: dict[str, str] = {}
    tickers_by_cik: dict[str, list[str]] = {}
    for row in rows:
        cik = str(row.get("cik") or "").strip()
        name = str(row.get("name") or "").strip()
        if not name or len(name) > 300:
            raise ValueError(
                "SEC issuer directory materialization requires a non-empty name "
                "of at most 300 characters"
            )
        names_by_cik[cik] = name
        raw_tickers = row.get("tickers")
        if raw_tickers is not None and (
            not isinstance(raw_tickers, list)
            or any(not isinstance(ticker, str) or not ticker.strip() for ticker in raw_tickers)
        ):
            raise ValueError("SEC issuer directory materialization returned invalid tickers")
        tickers_by_cik[cik] = sorted(
            {str(ticker).strip().upper() for ticker in raw_tickers or []}
        )

    ciks = list(names_by_cik)
    existing_rows = (
        (await db.execute(select(Issuer).where(Issuer.cik.in_(ciks)))).scalars().all()
    )
    existing_by_cik = {str(issuer.cik): issuer for issuer in existing_rows if issuer.cik}
    domain_rows = (
        (
            await db.execute(
                select(Issuer).where(Issuer.domain_key.in_([f"cik:{cik}" for cik in ciks]))
            )
        )
        .scalars()
        .all()
    )
    domain_owners = {issuer.domain_key: issuer for issuer in domain_rows}

    missing = 0
    for cik, name in names_by_cik.items():
        if cik in existing_by_cik:
            continue
        domain_key = f"cik:{cik}"
        owner = domain_owners.get(domain_key)
        if owner is not None and owner.cik != cik:
            raise ValueError(
                f"SEC issuer directory CIK {cik} conflicts with existing issuer domain key"
            )
        db.add(
            Issuer(
                domain_key=domain_key,
                legal_name=name,
                cik=cik,
                country_code="US",
                provenance={
                    "source": _PROVIDER,
                    "directory": "company_tickers.json",
                    "observed_at": observed_at.isoformat(),
                    "tickers": tickers_by_cik.get(cik, []),
                    "materialization_policy": mode,
                },
            )
        )
        missing += 1
    if missing:
        await db.flush()
    return missing, len(existing_by_cik)


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
            (
                await db.execute(
                    select(Issuer)
                    .where(Issuer.cik.is_not(None))
                    .order_by(Issuer.id)
                    .limit(max_issuers + 1)
                )
            )
            .scalars()
            .all()
        )

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


async def refresh_edgar_ipo_pipeline_for_sec_directory(
    db: AsyncSession,
    *,
    start: date | None = None,
    end: date | None = None,
    max_issuers: int = 50,
    max_events_per_issuer: int = 100,
    max_submissions_requests: int = 0,
    issuer_materialization_mode: str = "disabled",
) -> dict[str, Any]:
    """Scan the complete SEC issuer directory in durable bounded pages.

    EDGAR has no global IPO-calendar endpoint, but its official ticker
    directory is a complete issuer catalogue.  This workflow pages that
    catalogue by unique CIK and then reuses the existing per-CIK submissions
    parser.  The offset is kept in the scan-state provenance JSON so the
    existing issuer foreign key remains dedicated to the legacy canonical-
    issuer scan.  A cycle is still only a statement that every directory CIK
    was attempted; it is not a claim that filing dates equal listing dates.
    """

    _validate_limit(max_issuers, "max_issuers")
    _validate_limit(max_events_per_issuer, "max_events_per_issuer")
    issuer_materialization_mode = _validate_issuer_materialization_mode(
        issuer_materialization_mode
    )
    if (
        not isinstance(max_submissions_requests, int)
        or isinstance(max_submissions_requests, bool)
        or not 1 <= max_submissions_requests <= 500
    ):
        raise ValueError("max_submissions_requests must be between 1 and 500")
    if max_issuers > max_submissions_requests:
        raise ValueError("max_issuers cannot exceed max_submissions_requests")
    if start is not None and end is not None and end < start:
        raise ValueError("end must be on or after start")

    state = (
        await db.execute(
            select(MarketEventScanState)
            .where(MarketEventScanState.scan_key == _DIRECTORY_SCAN_KEY)
            .with_for_update()
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if state is None:
        state = MarketEventScanState(
            scan_key=_DIRECTORY_SCAN_KEY,
            provider=_PROVIDER,
            operation=_DIRECTORY_OPERATION,
            cycle_started_at=now,
            status="running",
            provenance={
                "algorithm": "edgar_ipo_pipeline_sec_directory_v1",
                "directory_offset": 0,
                "submissions_request_bound": max_submissions_requests,
                "issuer_materialization_mode": issuer_materialization_mode,
            },
        )
        db.add(state)
        await db.flush()

    provenance = state.provenance if isinstance(state.provenance, dict) else {}
    raw_offset = provenance.get("directory_offset", 0)
    if isinstance(raw_offset, bool) or not isinstance(raw_offset, int) or raw_offset < 0:
        raise ValueError("SEC directory scan state contains an invalid directory offset")
    offset = raw_offset
    wrapped = offset == 0 and state.cycle_count > 0
    state.status = "running"
    state.last_error = None
    materialized_issuers = 0
    existing_issuers = 0

    try:
        execution = await execute_provider_call(
            db,
            ProviderCapability.MARKET_EVENTS,
            _DIRECTORY_OPERATION,
            provider_name=_PROVIDER,
            invoke=lambda provider, _provider_symbol: provider.discover_issuer_ciks_page(
                offset, limit=max_issuers
            ),
            response_items=lambda result: len(result.get("issuers") or [])
            if isinstance(result, dict)
            else None,
            treat_empty_as_failure=False,
        )
        page = execution.result
        if not isinstance(page, dict):
            raise ValueError("SEC issuer directory returned a malformed page")
        total = page.get("total")
        page_offset = page.get("offset")
        rows = page.get("issuers")
        if (
            isinstance(total, bool)
            or not isinstance(total, int)
            or total < 0
            or page_offset != offset
            or not isinstance(rows, list)
            or len(rows) > max_issuers
        ):
            raise ValueError("SEC issuer directory returned invalid pagination metadata")
        ciks: list[str] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("SEC issuer directory returned a malformed issuer row")
            cik = str(row.get("cik") or "").strip()
            if len(cik) != 10 or not cik.isdigit() or int(cik) <= 0 or cik in seen:
                raise ValueError("SEC issuer directory returned an invalid or duplicate CIK")
            seen.add(cik)
            ciks.append(cik)
        if offset > total or (offset < total and not rows):
            raise ValueError("SEC issuer directory returned a non-progressing page")
        materialized_issuers, existing_issuers = await _materialize_directory_issuers(
            db,
            rows,
            mode=issuer_materialization_mode,
            observed_at=now,
        )
    except Exception as exc:  # noqa: BLE001 - persist bounded scan failure.
        state.status = "failed"
        state.last_scanned_at = now
        state.last_batch_count = 0
        state.last_event_count = 0
        state.last_failure_count = 1
        state.last_error = bounded_redact_provider_message(exc, max_length=500)
        state.provenance = {
            **provenance,
            "algorithm": "edgar_ipo_pipeline_sec_directory_v1",
            "directory_offset": offset,
            "bounded": True,
            "submissions_request_bound": max_submissions_requests,
            "issuer_materialization_mode": issuer_materialization_mode,
        }
        await db.commit()
        return {
            "status": "failed",
            "scan_key": _DIRECTORY_SCAN_KEY,
            "issuers_considered": 0,
            "events": 0,
            "failures": 1,
            "directory_offset": offset,
            "submissions_request_bound": max_submissions_requests,
            "issuer_materialization_mode": issuer_materialization_mode,
            "issuers_materialized": 0,
            "existing_issuers": 0,
            "cycle_complete": False,
            "wrapped": wrapped,
        }

    if not ciks:
        # A zero-row page at the exact catalogue end is the only successful
        # terminal condition; reset the cursor for the next full cycle.
        cycle_complete = offset >= total
        if not cycle_complete:
            raise ValueError("SEC issuer directory returned an empty non-terminal page")
        state.provenance = {
            **provenance,
            "algorithm": "edgar_ipo_pipeline_sec_directory_v1",
            "directory_offset": 0,
            "directory_total": total,
            "last_batch_ciks": [],
            "bounded": True,
            "cycle_complete": True,
            "submissions_request_bound": max_submissions_requests,
            "issuer_materialization_mode": issuer_materialization_mode,
            "issuers_materialized": 0,
            "existing_issuers": 0,
        }
        state.cursor_issuer_id = None
        state.cycle_count += 1
        state.last_scanned_at = now
        state.last_batch_count = 0
        state.last_event_count = 0
        state.last_failure_count = 0
        state.status = "complete"
        await db.commit()
        return {
            "status": "complete",
            "scan_key": _DIRECTORY_SCAN_KEY,
            "issuers_considered": 0,
            "events": 0,
            "failures": 0,
            "directory_offset": 0,
            "submissions_request_bound": max_submissions_requests,
            "issuer_materialization_mode": issuer_materialization_mode,
            "issuers_materialized": 0,
            "existing_issuers": 0,
            "cycle_complete": True,
            "wrapped": wrapped,
        }

    result = await refresh_edgar_ipo_pipeline(
        db,
        ciks,
        start=start,
        end=end,
        max_ciks=max_issuers,
        max_events_per_issuer=max_events_per_issuer,
        commit=False,
    )
    next_offset = offset + len(ciks)
    cycle_complete = next_offset >= total
    state.provenance = {
        **provenance,
        "algorithm": "edgar_ipo_pipeline_sec_directory_v1",
        "directory_offset": 0 if cycle_complete else next_offset,
        "directory_total": total,
        "last_batch_ciks": ciks,
        "window": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "bounded": True,
        "cycle_complete": cycle_complete,
        "submissions_request_bound": max_submissions_requests,
        "issuer_materialization_mode": issuer_materialization_mode,
        "issuers_materialized": materialized_issuers,
        "existing_issuers": existing_issuers,
    }
    state.cursor_issuer_id = None
    state.cycle_count += 1 if cycle_complete else 0
    state.scanned_count += len(ciks)
    state.last_batch_count = len(ciks)
    state.last_event_count = int(result.get("events", 0))
    state.last_failure_count = int(result.get("failures", 0))
    state.last_scanned_at = now
    state.status = "complete" if cycle_complete else "partial"
    state.last_error = (
        "one or more SEC issuer pipeline reads failed" if state.last_failure_count else None
    )
    await db.commit()
    return {
        **result,
        "scan_key": _DIRECTORY_SCAN_KEY,
        "issuers_considered": len(ciks),
        "directory_offset": 0 if cycle_complete else next_offset,
        "submissions_request_bound": max_submissions_requests,
        "issuer_materialization_mode": issuer_materialization_mode,
        "issuers_materialized": materialized_issuers,
        "existing_issuers": existing_issuers,
        "cycle_complete": cycle_complete,
        "wrapped": wrapped,
    }
