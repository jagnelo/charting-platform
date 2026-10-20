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
from collections.abc import Awaitable, Callable, Iterable, Sequence
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


async def _rotate_market_event_provider_names(
    db: AsyncSession,
    names: Sequence[str],
    *,
    max_providers: int,
    start: date | None,
    end: date | None,
) -> tuple[list[str], ProviderPaginationState | None, int | None]:
    """Select a bounded provider slice without permanently starving providers.

    ``max_providers`` is a per-invocation work budget, not an allow-list. The
    selected slice advances only when the caller commits the complete refresh,
    so a process failure retries the same slice while provider failures still
    allow later providers to receive their next turn.
    """

    normalized = [str(name).strip().lower() for name in names if str(name).strip()]
    if not normalized or max_providers >= len(normalized):
        return normalized, None, None
    bounded = max(0, int(max_providers))
    if bounded == 0:
        return [], None, None

    identity = "|".join(
        [
            "v1",
            *normalized,
        ]
    )
    state_key = (
        "market-events-provider-rotation:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    )
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
            provider="internal",
            capability=ProviderCapability.MARKET_EVENTS.value,
            operation="provider_rotation",
            page_number=0,
            cursor="0",
            page_size=bounded,
            status="pending",
            metadata_payload={
                "providers": normalized,
                "window": {
                    "start": start.isoformat() if start is not None else None,
                    "end": end.isoformat() if end is not None else None,
                },
            },
        )
        db.add(state)
        await db.flush()

    metadata = state.metadata_payload if isinstance(state.metadata_payload, dict) else {}
    state.metadata_payload = {
        **metadata,
        "providers": normalized,
        "window": {
            "start": start.isoformat() if start is not None else None,
            "end": end.isoformat() if end is not None else None,
        },
    }
    metadata = state.metadata_payload
    last_selected = str(metadata.get("last_selected") or "").strip().lower()
    if last_selected in normalized:
        start_index = (normalized.index(last_selected) + 1) % len(normalized)
    else:
        try:
            start_index = int(state.cursor or 0) % len(normalized)
        except (TypeError, ValueError):
            state.status = "failed"
            state.last_error = "invalid persisted market-event provider rotation cursor"
            raise ValueError(state.last_error)

    selected = [
        normalized[(start_index + offset) % len(normalized)]
        for offset in range(min(bounded, len(normalized)))
    ]
    next_index = (start_index + len(selected)) % len(normalized)
    state.page_size = bounded
    state.status = "pending"
    return selected, state, next_index


def _commit_market_event_provider_rotation(
    state: ProviderPaginationState | None,
    *,
    selected: Sequence[str],
    next_index: int | None,
) -> None:
    if state is None or next_index is None or not selected:
        return
    state.cursor = str(next_index)
    state.page_number = int(state.page_number or 0) + 1
    state.pages_fetched = int(state.pages_fetched or 0) + 1
    state.last_page_count = len(selected)
    state.last_success_at = datetime.now(UTC)
    state.last_failure_at = None
    state.last_error = None
    state.status = "partial"
    state.metadata_payload = {
        **(state.metadata_payload or {}),
        "providers": list(selected),
        "last_selected": selected[-1],
        "selected_count": len(selected),
    }


async def _fetch_cursor_paginated_market_events(
    db: AsyncSession,
    *,
    provider_name: str,
    start: date | None,
    end: date | None,
    max_pages: int | None,
    force_refresh: bool,
    retry_blocked: bool,
) -> tuple[str, dict[str, int], list[dict[str, str]], int, dict[str, Any]]:
    """Read every provider cursor page while accounting each request.

    Massive exposes URL cursors and FMP exposes numeric page cursors. A
    one-page compatibility method is useful to callers, but persistence must
    not silently discard either continuation form. Each valid page's source
    rows, request accounting, and next cursor are committed together before
    another page is requested. A quota failure after page N therefore leaves
    pages 1..N durably available and the failure is retained for the next run.
    """

    provider = get_provider(provider_name)
    page_method = getattr(provider, "fetch_market_events_page", None)
    if not callable(page_method):
        raise TypeError("provider does not expose cursor-paginated market events")

    state_key = (
        "market-events:"
        + ":".join((value.isoformat() if value is not None else "*") for value in (start, end))
        + f":{provider_name.strip().lower()}"
    )
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
    elif state.status == "complete" and not force_refresh:
        return (
            provider_name,
            {"events": 0, "persisted": 0, "linked": 0, "unlinked": 0},
            [],
            0,
            {
                "status": "complete",
                "pages_fetched": 0,
                "total_pages_fetched": int(state.pages_fetched or 0),
                "continuation_pending": False,
                "skipped_completed_window": True,
            },
        )
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
    elif state.status == "blocked":
        if not retry_blocked:
            return (
                provider_name,
                {"events": 0, "persisted": 0, "linked": 0, "unlinked": 0},
                [
                    {
                        "operation": "fetch_market_events",
                        "error_type": "ProviderPaginationBlocked",
                        "error": str(state.last_error or "provider pagination is blocked"),
                        "page_cursor": state.cursor or "<blocked>",
                    }
                ],
                0,
                {
                    "status": "blocked",
                    "pages_fetched": 0,
                    "total_pages_fetched": int(state.pages_fetched or 0),
                    "continuation_pending": bool(state.cursor),
                    "skipped_completed_window": False,
                },
            )
        # A blocked cursor is durable evidence of what remains, not a terminal
        # discard. An explicit retry lets a later adapter/source improvement
        # resume from that point without resetting the window or losing rows.
        state.status = "pending"

    cursor: str | None = state.cursor
    seen_cursors: set[str] = set(str(item) for item in (state.cursor_history or []))
    counts = {"events": 0, "persisted": 0, "linked": 0, "unlinked": 0}
    failures: list[dict[str, str]] = []
    page_count = 0
    while max_pages is None or page_count < max_pages:
        page_cursor = cursor
        try:
            execution = await execute_provider_call(
                db,
                ProviderCapability.MARKET_EVENTS,
                "fetch_market_events",
                provider_name=provider_name,
                invoke=lambda resolved,
                _provider_symbol,
                page_cursor=page_cursor: resolved.fetch_market_events_page(
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
            blocked_error = None
        elif isinstance(page, dict):
            page_events = page.get("events")
            next_url = page.get("next_url")
            next_cursor = page.get("next_cursor")
            blocked_error = page.get("blocked_error")
            complete = (
                page.get("complete") is True
                if "complete" in page or blocked_error
                else not next_url and not next_cursor
            )
        else:
            state.status = "failed"
            state.last_failure_at = datetime.now(UTC)
            state.last_error = "provider returned malformed market-event page"
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
        page_counts = await _persist_market_event_records(
            db,
            provider_name=execution.provider_name,
            records=page_events,
        )
        for count_name, count in page_counts.items():
            counts[count_name] += count
        state.last_page_count = len(page_events)
        if blocked_error:
            if (
                not isinstance(blocked_error, str)
                or not blocked_error.strip()
                or complete
                or next_url is not None
            ):
                state.status = "failed"
                state.last_failure_at = datetime.now(UTC)
                state.last_error = "provider returned invalid blocked-page metadata"
                failures.append(
                    {
                        "operation": "fetch_market_events",
                        "error_type": "ValueError",
                        "error": state.last_error,
                        "page_cursor": page_cursor or "<initial>",
                    }
                )
                await db.commit()
                break
            state.cursor = next_cursor.strip() if isinstance(next_cursor, str) else page_cursor
            state.status = "blocked"
            state.last_failure_at = datetime.now(UTC)
            state.last_error = str(blocked_error).strip()[:500]
            metadata = state.metadata_payload if isinstance(state.metadata_payload, dict) else {}
            state.metadata_payload = {
                **metadata,
                "blocked_page_number": state.page_number,
                "blocked_page_count": len(page_events),
                "blocked_error": state.last_error,
            }
            failures.append(
                {
                    "operation": "fetch_market_events",
                    "error_type": "ProviderPaginationBlocked",
                    "error": state.last_error,
                    "page_cursor": page_cursor or "<initial>",
                }
            )
            # This page has already been persisted. Do not spend quota
            # repeatedly on an impossible range; a narrower range has its own
            # cursor state and can continue collecting the remaining rows.
            await db.commit()
            break
        if complete:
            if next_url is not None or next_cursor is not None:
                state.status = "failed"
                state.last_failure_at = datetime.now(UTC)
                state.last_error = "provider marked a page complete with continuation"
                failures.append(
                    {
                        "operation": "fetch_market_events",
                        "error_type": "ValueError",
                        "error": "provider marked a page complete with continuation",
                        "page_cursor": page_cursor or "<initial>",
                    }
                )
                await db.commit()
                break
            state.cursor = None
            state.status = "complete"
            state.cursor_history = []
            await db.commit()
            break
        if next_url is not None and (not isinstance(next_url, str) or not next_url.strip()):
            state.status = "failed"
            state.last_failure_at = datetime.now(UTC)
            state.last_error = "provider returned an invalid next_url"
            failures.append(
                {
                    "operation": "fetch_market_events",
                    "error_type": "ValueError",
                    "error": state.last_error,
                    "page_cursor": page_cursor or "<initial>",
                }
            )
            await db.commit()
            break
        if not isinstance(next_cursor, str) or not next_cursor.strip():
            state.status = "failed"
            state.last_failure_at = datetime.now(UTC)
            state.last_error = "provider returned an incomplete page without a validated cursor"
            failures.append(
                {
                    "operation": "fetch_market_events",
                    "error_type": "ValueError",
                    "error": state.last_error,
                    "page_cursor": page_cursor or "<initial>",
                }
            )
            await db.commit()
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
            await db.commit()
            break
        seen_cursors.add(cursor_digest)
        state.cursor_history = sorted(seen_cursors)
        cursor = next_cursor
        state.cursor = next_cursor
        state.status = "partial"
        await db.commit()

    return (
        execution.provider_name if "execution" in locals() else provider_name,
        counts,
        failures,
        page_count,
        {
            "status": state.status,
            "pages_fetched": page_count,
            "total_pages_fetched": int(state.pages_fetched or 0),
            "continuation_pending": bool(state.cursor),
            "skipped_completed_window": False,
        },
    )


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
                        func.upper(InstrumentProviderSymbol.provider_symbol) == symbol.upper(),
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
        issuer_rows = (await db.execute(select(Issuer.id).where(Issuer.cik == cik))).all()
        issuer_candidates = sorted({int(row[0]) for row in issuer_rows if row[0] is not None})
        if len(issuer_candidates) == 1:
            issuer_id = issuer_candidates[0]
    return instrument_id, issuer_id


async def _persist_market_event_records(
    db: AsyncSession,
    *,
    provider_name: str,
    records: Sequence[MarketEventRecord],
) -> dict[str, int]:
    """Persist each provider event with its exact source payload and link state."""

    counts = {"events": 0, "persisted": 0, "linked": 0, "unlinked": 0}
    for record in records:
        payload = dict(record.raw_payload or {})
        instrument_id, issuer_id = await _resolve_event_targets(
            db,
            provider_name=provider_name,
            payload=payload,
        )
        await persist_market_event(
            db,
            event_key=record.event_key,
            event_type=record.event_type,
            source=provider_name,
            instrument_id=instrument_id,
            issuer_id=issuer_id,
            event_time=record.event_time,
            effective_date=record.effective_date,
            source_version=record.source_version,
            payload=payload,
            is_provisional=record.is_provisional,
        )
        counts["events"] += 1
        counts["persisted"] += 1
        counts["linked" if instrument_id is not None or issuer_id is not None else "unlinked"] += 1
    return counts


async def refresh_market_events(
    db: AsyncSession,
    *,
    start: date | None = None,
    end: date | None = None,
    provider_names: Sequence[str] | None = None,
    max_providers: int | None = None,
    max_pages: int | None = None,
    force_refresh: bool = True,
    retry_blocked: bool = False,
) -> dict[str, Any]:
    """Fetch and persist one bounded market-event window per provider.

    Provider calls are routed through the durable capability/quota runtime. A
    provider failure is retained in the returned per-provider result while
    other eligible providers continue; one provider's failure never erases
    successful observations from another source.
    """

    if start is not None and end is not None and start > end:
        raise ValueError("market-event start date must not be after end date")
    if max_pages is not None and (
        isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1
    ):
        raise ValueError("max_pages must be a positive integer or None")

    names = market_event_provider_names(provider_names)
    rotation_state: ProviderPaginationState | None = None
    rotation_next_index: int | None = None
    if max_providers is not None:
        names, rotation_state, rotation_next_index = await _rotate_market_event_provider_names(
            db,
            names,
            max_providers=max(0, int(max_providers)),
            start=start,
            end=end,
        )

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
        pagination_summary: dict[str, Any] | None = None
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
                    page_counts,
                    page_failures,
                    _page_count,
                    pagination_summary,
                ) = await _fetch_cursor_paginated_market_events(
                    db,
                    provider_name=requested_name,
                    start=start,
                    end=end,
                    max_pages=max_pages,
                    force_refresh=force_refresh,
                    retry_blocked=retry_blocked,
                )
                if page_failures:
                    failures += len(page_failures)
                    operation_failures.extend(page_failures)
                provider_events += page_counts["events"]
                provider_persisted += page_counts["persisted"]
                provider_linked += page_counts["linked"]
                provider_unlinked += page_counts["unlinked"]
                # Cursor-paginated rows were persisted atomically with each
                # page's durable continuation inside the page reader.
                continue
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

            persisted_counts = await _persist_market_event_records(
                db,
                provider_name=resolved_provider_name,
                records=records,
            )
            provider_events += persisted_counts["events"]
            provider_persisted += persisted_counts["persisted"]
            provider_linked += persisted_counts["linked"]
            provider_unlinked += persisted_counts["unlinked"]

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
                "pagination": pagination_summary,
            }
        )
        total_events += provider_events
        total_persisted += provider_persisted
        total_linked += provider_linked
        total_unlinked += provider_unlinked

    reconciliation = await reconcile_market_events(db, start=start, end=end)
    _commit_market_event_provider_rotation(
        rotation_state,
        selected=names,
        next_index=rotation_next_index,
    )
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
        "max_pages_per_provider": max_pages,
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
    after_issuer: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
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
                provider_symbol=f"CIK:{cik}",
                usage_identity=f"cik:{cik}",
                invoke=lambda resolved,
                _provider_symbol,
                candidate=cik: resolved.fetch_ipo_pipeline_events(
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
        if after_issuer is not None:
            await after_issuer(issuer_results[-1])

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
