"""Provider-routed persistence for market-wide normalized events.

Market-wide event feeds (IPO calendars, earnings calendars, and exchange
holiday feeds) are intentionally separate from instrument-level event history.
This module fans out only to providers that advertise ``market_events``,
persists each provider observation idempotently, and links an event to a
canonical instrument or issuer only when an exact provider-symbol or CIK
match exists.  Ambiguous ticker-only matches remain unlinked for later
reconciliation instead of being merged silently.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.market_data_foundation import Issuer, ProviderPaginationState
from app.models.provider_runtime import ProviderCapability
from app.providers import get_provider, list_provider_capabilities, supported_provider_names
from app.providers.base import MarketEventRecord
from app.providers.errors import bounded_redact_provider_message
from app.services.market_data_persistence import persist_market_event
from app.services.market_event_reconciliation import reconcile_market_events
from app.services.provider_runtime import execute_provider_call

_SYMBOL_FIELDS = (
    "symbol",
    "ticker",
    "provider_symbol",
    "underlying_symbol",
)
_CIK_FIELDS = ("cik", "sec_cik", "issuer_cik")


def _first_text(payload: dict[str, Any], fields: Iterable[str]) -> str | None:
    for field in fields:
        value = payload.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _normalize_cik(value: Any) -> str | None:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if not digits or len(digits) > 10:
        return None
    return digits.zfill(10)


def market_event_provider_names(
    provider_names: Sequence[str] | None = None,
) -> list[str]:
    """Return a deterministic, de-duplicated market-event provider list."""

    candidates = provider_names if provider_names is not None else supported_provider_names()
    result: list[str] = []
    seen: set[str] = set()
    for raw_name in candidates:
        name = str(raw_name or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            capabilities = list_provider_capabilities(name)
        except KeyError:
            continue
        # Filing-driven subfeeds (currently EDGAR's IPO pipeline) share the
        # persisted market-events policy but require an explicit issuer/CIK
        # batch. They are dispatched by their dedicated service, not by this
        # calendar-wide fan-out.
        provider = get_provider(name)
        if "market_events" in capabilities and callable(
            getattr(provider, "fetch_market_events", None)
        ):
            result.append(name)
    return result


def _market_event_operations(
    provider_name: str,
    *,
    start: date | None,
    end: date | None,
) -> list[tuple[str, Any]]:
    """Return explicitly metered market-event operations for one provider.

    Most adapters expose the protocol's ``fetch_market_events`` operation.
    Some providers publish additional market-wide feeds without changing that
    protocol; those methods are added only when the concrete adapter exposes
    them, keeping each upstream request independently visible to the runtime.
    """

    provider = get_provider(provider_name)
    operations: list[tuple[str, Any]] = [
        (
            "fetch_market_events",
            lambda resolved, _provider_symbol: resolved.fetch_market_events(
                start=start,
                end=end,
            ),
        )
    ]
    if callable(getattr(provider, "fetch_earnings_calendar", None)):
        operations.append(
            (
                "fetch_earnings_calendar",
                lambda resolved, _provider_symbol: resolved.fetch_earnings_calendar(
                    horizon="3month",
                    start=start,
                    end=end,
                ),
            )
        )
    return operations


async def _fetch_cursor_paginated_market_events(
    db: AsyncSession,
    *,
    provider_name: str,
    start: date | None,
    end: date | None,
) -> tuple[str, list[MarketEventRecord], list[dict[str, str]], int]:
    """Read every provider cursor page while accounting each request.

    Massive exposes the IPO calendar through a cursor-paginated endpoint.  A
    one-page compatibility method is useful to callers, but persistence must
    not silently discard the continuation.  Each page is routed through the
    normal quota/health runtime, so a quota failure after page N leaves pages
    1..N available for persistence and the failure is retained for the next
    scheduled run.
    """

    provider = get_provider(provider_name)
    page_method = getattr(provider, "fetch_market_events_page", None)
    if not callable(page_method):
        raise TypeError("provider does not expose cursor-paginated market events")

    state_key = "market-events:" + ":".join(
        (value.isoformat() if value is not None else "*") for value in (start, end)
    ) + f":{provider_name.strip().lower()}"
    state = (
        await db.execute(
            select(ProviderPaginationState)
            .where(ProviderPaginationState.state_key == state_key)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if state is None:
        state = ProviderPaginationState(
            state_key=state_key,
            provider=provider_name.strip().lower(),
            capability=ProviderCapability.MARKET_EVENTS.value,
            operation="fetch_market_events",
            page_number=0,
            cursor=None,
            page_size=0,
            status="pending",
            pages_fetched=0,
            last_page_count=0,
            cursor_history=[],
            metadata_payload={
                "window": {
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                }
            },
        )
        db.add(state)
        await db.flush()
    elif state.status == "complete":
        # A completed daily window is eligible for a fresh snapshot; a
        # partial/failed window retains its opaque continuation for retry.
        state.page_number = 0
        state.cursor = None
        state.status = "pending"
        state.pages_fetched = 0
        state.last_page_count = 0
        state.last_error = None
        state.cursor_history = []

    cursor: str | None = state.cursor
    seen_cursors: set[str] = set(str(item) for item in (state.cursor_history or []))
    records: list[MarketEventRecord] = []
    failures: list[dict[str, str]] = []
    page_count = 0
    while True:
        page_cursor = cursor
        try:
            execution = await execute_provider_call(
                db,
                ProviderCapability.MARKET_EVENTS,
                "fetch_market_events",
                provider_name=provider_name,
                invoke=lambda resolved, _provider_symbol, page_cursor=page_cursor: resolved.fetch_market_events_page(
                    start=start,
                    end=end,
                    cursor=page_cursor,
                ),
                response_items=lambda result: (
                    len(result.get("events", []))
                    if isinstance(result, dict)
                    else len(result)
                    if isinstance(result, list)
                    else None
                ),
                treat_empty_as_failure=False,
            )
        except Exception as exc:  # noqa: BLE001 - retain partial pages.
            state.status = "failed"
            state.last_failure_at = datetime.now(UTC)
            state.last_error = bounded_redact_provider_message(exc, max_length=500)
            failures.append(
                {
                    "operation": "fetch_market_events",
                    "error_type": exc.__class__.__name__,
                    "error": bounded_redact_provider_message(exc, max_length=500),
                    "page_cursor": page_cursor or "<initial>",
                }
            )
            break

        page_count += 1
        state.pages_fetched = int(state.pages_fetched or 0) + 1
        state.page_number = int(state.page_number or 0) + 1
        state.last_page_count = 0
        state.last_success_at = datetime.now(UTC)
        state.last_failure_at = None
        state.last_error = None
        page = execution.result
        if isinstance(page, list):
            # Preserve compatibility with fixture doubles and providers whose
            # page method is represented as a normalized list.
            page_events = page
            next_cursor = None
            next_url = None
            complete = True
        elif isinstance(page, dict):
            page_events = page.get("events")
            next_url = page.get("next_url")
            next_cursor = page.get("next_cursor")
            complete = page.get("complete") is True or not next_url
        else:
            failures.append(
                {
                    "operation": "fetch_market_events",
                    "error_type": "TypeError",
                    "error": "provider returned malformed market-event page",
                    "page_cursor": page_cursor or "<initial>",
                }
            )
            break

        if not isinstance(page_events, list) or any(
            not isinstance(record, MarketEventRecord) for record in page_events
        ):
            state.status = "failed"
            state.last_failure_at = datetime.now(UTC)
            state.last_error = "provider returned malformed market-event records"
            failures.append(
                {
                    "operation": "fetch_market_events",
                    "error_type": "TypeError",
                    "error": "provider returned malformed market-event records",
                    "page_cursor": page_cursor or "<initial>",
                }
            )
            break
        records.extend(page_events)
        state.last_page_count = len(page_events)
        if complete:
            state.cursor = None
            state.status = "complete"
            state.cursor_history = []
            break
        if not isinstance(next_url, str) or not next_url:
            state.status = "failed"
            state.last_failure_at = datetime.now(UTC)
            state.last_error = "provider returned an incomplete page without next_url"
            failures.append(
                {
                    "operation": "fetch_market_events",
                    "error_type": "ValueError",
                    "error": "provider returned an incomplete page without next_url",
                    "page_cursor": page_cursor or "<initial>",
                }
            )
            break
        if not isinstance(next_cursor, str) or not next_cursor.strip():
            state.status = "failed"
            state.last_failure_at = datetime.now(UTC)
            state.last_error = "provider returned next_url without a validated next_cursor"
            failures.append(
                {
                    "operation": "fetch_market_events",
                    "error_type": "ValueError",
                    "error": "provider returned next_url without a validated next_cursor",
                    "page_cursor": page_cursor or "<initial>",
                }
            )
            break
        next_cursor = next_cursor.strip()
        cursor_digest = hashlib.sha256(next_cursor.encode("utf-8")).hexdigest()
        if cursor_digest in seen_cursors or next_cursor == page_cursor:
            state.status = "failed"
            state.last_failure_at = datetime.now(UTC)
            state.last_error = "provider repeated a market-event cursor"
            failures.append(
                {
                    "operation": "fetch_market_events",
                    "error_type": "ValueError",
                    "error": "provider repeated a market-event cursor",
                    "page_cursor": next_cursor,
                }
            )
            break
        seen_cursors.add(cursor_digest)
        state.cursor_history = sorted(seen_cursors)
        cursor = next_cursor
        state.cursor = next_cursor
        state.status = "partial"

    return execution.provider_name if "execution" in locals() else provider_name, records, failures, page_count


async def _resolve_event_targets(
    db: AsyncSession,
    *,
    provider_name: str,
    payload: dict[str, Any],
) -> tuple[int | None, int | None]:
    """Resolve exact provider-symbol and issuer-CIK links, conservatively."""

    source_id = (
        await db.execute(select(DataSource.id).where(DataSource.name == provider_name))
    ).scalar_one_or_none()
    instrument_id: int | None = None
    if source_id is not None:
        symbol = _first_text(payload, _SYMBOL_FIELDS)
        if symbol:
            rows = (
                await db.execute(
                    select(InstrumentProviderSymbol.instrument_id).where(
                        InstrumentProviderSymbol.data_source_id == source_id,
                        func.upper(InstrumentProviderSymbol.provider_symbol)
                        == symbol.upper(),
                        InstrumentProviderSymbol.is_active.is_(True),
                    )
                )
            ).all()
            candidates = sorted({int(row[0]) for row in rows if row[0] is not None})
            # A provider symbol may legitimately exist on more than one venue.
            # Do not choose one without an exact exchange-qualified binding.
            if len(candidates) == 1:
                instrument_id = candidates[0]

    cik = _normalize_cik(_first_text(payload, _CIK_FIELDS))
    issuer_id: int | None = None
    if cik is not None:
        issuer_rows = (
            await db.execute(select(Issuer.id).where(Issuer.cik == cik))
        ).all()
        issuer_candidates = sorted({int(row[0]) for row in issuer_rows if row[0] is not None})
        if len(issuer_candidates) == 1:
            issuer_id = issuer_candidates[0]
    return instrument_id, issuer_id


async def refresh_market_events(
    db: AsyncSession,
    *,
    start: date | None = None,
    end: date | None = None,
    provider_names: Sequence[str] | None = None,
    max_providers: int | None = None,
) -> dict[str, Any]:
    """Fetch and persist one bounded market-event window per provider.

    Provider calls are routed through the durable capability/quota runtime. A
    provider failure is retained in the returned per-provider result while
    other eligible providers continue; one provider's failure never erases
    successful observations from another source.
    """

    names = market_event_provider_names(provider_names)
    if max_providers is not None:
        names = names[: max(0, int(max_providers))]

    provider_results: list[dict[str, Any]] = []
    total_events = 0
    total_persisted = 0
    total_linked = 0
    total_unlinked = 0

    failures = 0
    for requested_name in names:
        provider_events = 0
        provider_persisted = 0
        provider_linked = 0
        provider_unlinked = 0
        fetched_at = datetime.now(UTC)
        operation_failures: list[dict[str, Any]] = []
        resolved_provider_name = requested_name
        try:
            operations = _market_event_operations(
                requested_name,
                start=start,
                end=end,
            )
        except Exception as exc:  # noqa: BLE001 - retain per-provider outcome.
            operations = []
            failures += 1
            operation_failures.append(
                {
                    "operation": "provider_resolution",
                    "error_type": exc.__class__.__name__,
                    "error": bounded_redact_provider_message(exc, max_length=500),
                }
            )

        for operation, invoke in operations:
            if operation == "fetch_market_events" and callable(
                getattr(get_provider(requested_name), "fetch_market_events_page", None)
            ):
                (
                    resolved_provider_name,
                    records,
                    page_failures,
                    _page_count,
                ) = await _fetch_cursor_paginated_market_events(
                    db,
                    provider_name=requested_name,
                    start=start,
                    end=end,
                )
                if page_failures:
                    failures += len(page_failures)
                    operation_failures.extend(page_failures)
            else:
                try:
                    execution = await execute_provider_call(
                        db,
                        ProviderCapability.MARKET_EVENTS,
                        operation,
                        provider_name=requested_name,
                        invoke=invoke,
                        response_items=lambda result: len(result)
                        if isinstance(result, list)
                        else None,
                        treat_empty_as_failure=False,
                    )
                    resolved_provider_name = execution.provider_name
                    records = execution.result
                    if not isinstance(records, list) or any(
                        not isinstance(record, MarketEventRecord) for record in records
                    ):
                        raise TypeError("market-event provider returned malformed records")
                except Exception as exc:  # noqa: BLE001 - retain per-operation outcome.
                    failures += 1
                    operation_failures.append(
                        {
                            "operation": operation,
                            "error_type": exc.__class__.__name__,
                            "error": bounded_redact_provider_message(exc, max_length=500),
                        }
                    )
                    continue

            for record in records:
                payload = dict(record.raw_payload or {})
                instrument_id, issuer_id = await _resolve_event_targets(
                    db,
                    provider_name=resolved_provider_name,
                    payload=payload,
                )
                await persist_market_event(
                    db,
                    event_key=record.event_key,
                    event_type=record.event_type,
                    source=resolved_provider_name,
                    instrument_id=instrument_id,
                    issuer_id=issuer_id,
                    event_time=record.event_time,
                    effective_date=record.effective_date,
                    source_version=record.source_version,
                    payload=payload,
                    is_provisional=record.is_provisional,
                )
                provider_events += 1
                provider_persisted += 1
                if instrument_id is None and issuer_id is None:
                    provider_unlinked += 1
                else:
                    provider_linked += 1

        provider_results.append(
            {
                "provider": resolved_provider_name,
                "status": (
                    "refreshed"
                    if provider_events
                    else "failed"
                    if operation_failures
                    else "no_events"
                ),
                "events": provider_events,
                "persisted": provider_persisted,
                "linked": provider_linked,
                "unlinked": provider_unlinked,
                "fetched_at": fetched_at,
                "failures": operation_failures,
            }
        )
        total_events += provider_events
        total_persisted += provider_persisted
        total_linked += provider_linked
        total_unlinked += provider_unlinked

    reconciliation = await reconcile_market_events(db, start=start, end=end)
    await db.commit()
    return {
        "status": "refreshed" if total_events else ("failed" if failures else "no_events"),
        "window": {
            "start": start,
            "end": end,
        },
        "providers": provider_results,
        "provider_count": len(provider_results),
        "events": total_events,
        "persisted": total_persisted,
        "linked": total_linked,
        "unlinked": total_unlinked,
        "failures": failures,
        "reconciliation": reconciliation,
    }


async def refresh_edgar_ipo_pipeline(
    db: AsyncSession,
    ciks: Sequence[str],
    *,
    start: date | None = None,
    end: date | None = None,
    max_ciks: int = 50,
    max_events_per_issuer: int = 100,
    commit: bool = True,
) -> dict[str, Any]:
    """Persist EDGAR filing candidates for an explicit CIK batch.

    EDGAR does not publish a global IPO calendar.  Requiring callers to supply
    the candidate CIKs makes the request budget and watchlist scope explicit;
    this function never enumerates the SEC issuer universe implicitly. The
    per-issuer argument remains for compatibility, but every matching filing
    in each SEC submissions response is persisted rather than discarded at a
    local result cap.
    """

    if not isinstance(max_ciks, int) or isinstance(max_ciks, bool) or not 1 <= max_ciks <= 500:
        raise ValueError("max_ciks must be between 1 and 500")
    if (
        not isinstance(max_events_per_issuer, int)
        or isinstance(max_events_per_issuer, bool)
        or not 1 <= max_events_per_issuer <= 500
    ):
        raise ValueError("max_events_per_issuer must be between 1 and 500")
    if start is not None and end is not None and end < start:
        raise ValueError("end must be on or after start")

    normalized_ciks: list[str] = []
    seen: set[str] = set()
    invalid = 0
    for raw_cik in ciks:
        digits = "".join(character for character in str(raw_cik or "") if character.isdigit())
        if not digits or len(digits) > 10:
            invalid += 1
            continue
        cik = digits.zfill(10)
        if cik in seen:
            continue
        seen.add(cik)
        normalized_ciks.append(cik)
        if len(normalized_ciks) >= max_ciks:
            break

    provider_name = "edgar"
    provider = get_provider(provider_name)
    if not callable(getattr(provider, "fetch_ipo_pipeline_events", None)):
        return {
            "status": "unsupported",
            "provider": provider_name,
            "requested_ciks": len(normalized_ciks),
            "invalid_ciks": invalid,
            "events": 0,
            "persisted": 0,
            "linked": 0,
            "unlinked": 0,
            "failures": 1,
            "issuers": [],
        }

    issuer_results: list[dict[str, Any]] = []
    total_events = 0
    total_persisted = 0
    total_linked = 0
    total_unlinked = 0
    failures = invalid
    for cik in normalized_ciks:
        events = 0
        linked = 0
        unlinked = 0
        error: dict[str, str] | None = None
        try:
            execution = await execute_provider_call(
                db,
                ProviderCapability.MARKET_EVENTS,
                "fetch_ipo_pipeline_events",
                provider_name=provider_name,
                usage_identity=f"cik:{cik}",
                invoke=lambda resolved, _provider_symbol, candidate=cik: resolved.fetch_ipo_pipeline_events(
                    candidate,
                    start=start,
                    end=end,
                    max_events=max_events_per_issuer,
                ),
                response_items=lambda result: len(result) if isinstance(result, list) else None,
                treat_empty_as_failure=False,
            )
            records = execution.result
            if not isinstance(records, list) or any(
                not isinstance(record, MarketEventRecord) for record in records
            ):
                raise TypeError("EDGAR IPO pipeline returned malformed records")
            for record in records:
                payload = dict(record.raw_payload or {})
                instrument_id, issuer_id = await _resolve_event_targets(
                    db,
                    provider_name=execution.provider_name,
                    payload=payload,
                )
                await persist_market_event(
                    db,
                    event_key=record.event_key,
                    event_type=record.event_type,
                    source=execution.provider_name,
                    instrument_id=instrument_id,
                    issuer_id=issuer_id,
                    event_time=record.event_time,
                    effective_date=record.effective_date,
                    source_version=record.source_version,
                    payload=payload,
                    is_provisional=record.is_provisional,
                )
                events += 1
                if instrument_id is None and issuer_id is None:
                    unlinked += 1
                else:
                    linked += 1
        except Exception as exc:  # noqa: BLE001 - retain per-issuer outcome.
            failures += 1
            error = {
                "error_type": exc.__class__.__name__,
                "error": bounded_redact_provider_message(exc, max_length=500),
            }
        issuer_results.append(
            {
                "cik": cik,
                "status": "failed" if error else "refreshed",
                "events": events,
                "linked": linked,
                "unlinked": unlinked,
                "error": error,
            }
        )
        total_events += events
        total_persisted += events
        total_linked += linked
        total_unlinked += unlinked

    reconciliation = await reconcile_market_events(db, start=start, end=end)
    if commit:
        await db.commit()
    return {
        "status": "refreshed" if total_events else ("failed" if failures else "no_events"),
        "provider": provider_name,
        "requested_ciks": len(normalized_ciks),
        "invalid_ciks": invalid,
        "events": total_events,
        "persisted": total_persisted,
        "linked": total_linked,
        "unlinked": total_unlinked,
        "failures": failures,
        "issuers": issuer_results,
        "reconciliation": reconciliation,
    }
