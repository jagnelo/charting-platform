"""Durable, quota-metered ingestion for paginated short-interest observations."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.market_data_foundation import ProviderPaginationState
from app.models.provider_runtime import ProviderCapability
from app.providers import get_provider, provider_symbol_for_instrument
from app.providers.base import ShortInterestRecord
from app.providers.errors import bounded_redact_provider_message
from app.services.market_data_persistence import persist_short_interest
from app.services.provider_runtime import execute_provider_call


def _short_interest_state_key(
    *,
    provider_name: str,
    instrument_id: int,
    provider_symbol: str,
    start: date | None,
    end: date | None,
) -> str:
    symbol_fingerprint = hashlib.sha256(provider_symbol.encode("utf-8")).hexdigest()[:16]
    return "short-interest:" + ":".join(
        (
            provider_name,
            str(instrument_id),
            symbol_fingerprint,
            start.isoformat() if start else "*",
            end.isoformat() if end else "*",
        )
    )


async def refresh_short_interest_for_instrument(
    db: AsyncSession,
    instrument_id: int,
    *,
    provider_name: str = "finra",
    start: date | None = None,
    end: date | None = None,
    max_pages: int = 1,
    retry_blocked: bool = False,
) -> dict[str, Any]:
    """Fetch, persist, and resume every page for one canonical instrument.

    ``max_pages`` is a per-invocation fairness bound only. The next page and
    its request window are committed with that page's normalized and raw-row
    observations, so a later invocation resumes without losing or repeatedly
    refetching completed pages. No page-count bound is treated as result-set
    completion.
    """

    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    if start is not None and end is not None and start > end:
        raise ValueError("short-interest start date must not be after end date")

    normalized_provider = str(provider_name or "").strip().lower()
    if not normalized_provider:
        raise ValueError("provider_name is required")
    instrument = (
        await db.execute(
            select(Instrument)
            .where(Instrument.id == instrument_id)
            .options(
                selectinload(Instrument.provider_symbols).joinedload(
                    InstrumentProviderSymbol.data_source
                )
            )
        )
    ).scalar_one_or_none()
    if instrument is None:
        return {"status": "missing_instrument", "instrument_id": instrument_id}
    if not instrument.is_active:
        return {"status": "inactive_instrument", "instrument_id": instrument_id}
    if not str(instrument.domain_key or "").strip():
        return {
            "status": "identity_unresolved",
            "instrument_id": instrument_id,
            "reason": "short-interest persistence requires a canonical instrument domain key",
        }

    provider_symbol = provider_symbol_for_instrument(instrument, normalized_provider).strip()
    if not provider_symbol:
        return {
            "status": "provider_symbol_unresolved",
            "instrument_id": instrument_id,
            "provider": normalized_provider,
        }
    provider = get_provider(normalized_provider)
    page_method = getattr(provider, "fetch_short_interest_page", None)
    if not callable(page_method):
        return {
            "status": "provider_pagination_unsupported",
            "instrument_id": instrument_id,
            "provider": normalized_provider,
        }

    state_key = _short_interest_state_key(
        provider_name=normalized_provider,
        instrument_id=instrument_id,
        provider_symbol=provider_symbol,
        start=start,
        end=end,
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
            provider=normalized_provider,
            capability=ProviderCapability.SHORT_INTEREST.value,
            operation="fetch_short_interest",
            page_number=0,
            cursor=None,
            page_size=1_000,
            status="pending",
            pages_fetched=0,
            last_page_count=0,
            cursor_history=[],
            metadata_payload={
                "instrument_id": instrument_id,
                "domain_key": instrument.domain_key,
                "provider_symbol": provider_symbol,
                "window": {
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                },
            },
        )
        db.add(state)
        await db.flush()
    elif state.status == "complete":
        return {
            "status": "already_complete",
            "instrument_id": instrument_id,
            "provider": normalized_provider,
            "pages_fetched": int(state.pages_fetched or 0),
            "records_fetched": int(state.metadata_payload.get("records_fetched", 0) or 0),
            "state_key": state_key,
        }
    elif (
        state.status == "failed"
        and isinstance(state.metadata_payload, dict)
        and state.metadata_payload.get("last_page_blocked_error")
        and not retry_blocked
    ):
        return {
            "status": "failed",
            "instrument_id": instrument_id,
            "provider": normalized_provider,
            "pages_fetched": int(state.pages_fetched or 0),
            "records_fetched": int(state.metadata_payload.get("records_fetched", 0) or 0),
            "failures": [
                {
                    "operation": "fetch_short_interest",
                    "error_type": "ProviderResponseError",
                    "error": str(state.metadata_payload["last_page_blocked_error"])[:500],
                }
            ],
            "state_key": state_key,
        }

    cursor = state.cursor
    cursor_history = list(state.cursor_history) if isinstance(state.cursor_history, list) else []
    seen_cursor_digests = {
        str(value) for value in cursor_history if isinstance(value, str) and value
    }
    pages_fetched = 0
    records_fetched = 0
    records_persisted = 0
    failures: list[dict[str, str]] = []
    state.status = "pending"
    state.last_error = None

    while pages_fetched < max_pages:
        request_cursor = cursor
        try:
            execution = await execute_provider_call(
                db,
                ProviderCapability.SHORT_INTEREST,
                "fetch_short_interest",
                instrument_id=instrument.id,
                provider_name=normalized_provider,
                provider_symbol=provider_symbol,
                usage_identity=provider_symbol,
                invoke=lambda resolved, resolved_symbol, request_cursor=request_cursor: (
                    resolved.fetch_short_interest_page(
                        resolved_symbol or provider_symbol,
                        start=start,
                        end=end,
                        cursor=request_cursor,
                    )
                ),
                response_items=lambda page: (
                    len(page.get("records", [])) if isinstance(page, dict) else None
                ),
                treat_empty_as_failure=False,
            )
            page = execution.result
            if not isinstance(page, dict):
                raise TypeError("provider returned a malformed short-interest page")
            records = page.get("records")
            complete = page.get("complete")
            next_cursor = page.get("next_cursor")
            blocked_error = page.get("blocked_error")
            if (
                not isinstance(records, list)
                or any(not isinstance(record, ShortInterestRecord) for record in records)
                or not isinstance(complete, bool)
                or (complete and next_cursor is not None)
                or (not complete and not blocked_error and not isinstance(next_cursor, str))
                or (blocked_error and (not isinstance(next_cursor, str) or not next_cursor.strip()))
                or (isinstance(next_cursor, str) and not next_cursor.strip())
            ):
                raise TypeError("provider returned malformed short-interest pagination metadata")

            # Persist each complete provider page before its cursor advances.
            # Replays can create another immutable observation, but can never
            # lose the page or make the continuation skip it.
            inserted = await persist_short_interest(
                db,
                instrument.id,
                records,
                source=execution.provider_name,
            )
            pages_fetched += 1
            records_fetched += len(records)
            records_persisted += inserted
            state.page_number = int(state.page_number or 0) + 1
            state.pages_fetched = int(state.pages_fetched or 0) + 1
            state.last_page_count = len(records)
            state.last_success_at = datetime.now(UTC)
            state.last_failure_at = None
            state.last_error = None
            metadata = state.metadata_payload if isinstance(state.metadata_payload, dict) else {}
            state.metadata_payload = {
                **metadata,
                "records_fetched": int(metadata.get("records_fetched", 0) or 0) + len(records),
                "last_page_observed_at": datetime.now(UTC).isoformat(),
                "last_page_blocked_error": blocked_error,
            }
            if blocked_error:
                state.status = "failed"
                state.cursor = (
                    next_cursor.strip() if isinstance(next_cursor, str) else request_cursor
                )
                state.last_failure_at = datetime.now(UTC)
                state.last_error = str(blocked_error)[:500]
                failures.append(
                    {
                        "operation": "fetch_short_interest",
                        "error_type": "ProviderResponseError",
                        "error": str(blocked_error)[:500],
                    }
                )
                await db.commit()
                break

            if complete:
                state.cursor_history = []
            else:
                assert isinstance(next_cursor, str)
                next_cursor = next_cursor.strip()
                cursor_digest = hashlib.sha256(next_cursor.encode("utf-8")).hexdigest()
                if next_cursor == request_cursor or cursor_digest in seen_cursor_digests:
                    error = "provider repeated a short-interest pagination cursor"
                    state.status = "failed"
                    state.cursor = request_cursor or next_cursor
                    state.last_failure_at = datetime.now(UTC)
                    state.last_error = error
                    metadata = (
                        state.metadata_payload if isinstance(state.metadata_payload, dict) else {}
                    )
                    state.metadata_payload = {
                        **metadata,
                        "last_page_blocked_error": error,
                    }
                    failures.append(
                        {
                            "operation": "fetch_short_interest",
                            "error_type": "ProviderPaginationBlocked",
                            "error": error,
                        }
                    )
                    await db.commit()
                    break
                seen_cursor_digests.add(cursor_digest)
                cursor_history.append(cursor_digest)
                state.cursor_history = cursor_history
                cursor = next_cursor
                state.cursor = cursor
            if complete:
                state.status = "complete"
                state.cursor = None
            else:
                state.status = "pending"
            await db.commit()
            if complete:
                break
        except Exception as exc:  # noqa: BLE001 - persist continuation after partial progress.
            state.status = "failed"
            state.last_failure_at = datetime.now(UTC)
            state.last_error = bounded_redact_provider_message(exc, max_length=500)
            failures.append(
                {
                    "operation": "fetch_short_interest",
                    "error_type": exc.__class__.__name__,
                    "error": bounded_redact_provider_message(exc, max_length=500),
                }
            )
            await db.commit()
            break

    return {
        "status": state.status,
        "instrument_id": instrument.id,
        "domain_key": instrument.domain_key,
        "provider": normalized_provider,
        "provider_symbol": provider_symbol,
        "pages_fetched": pages_fetched,
        "total_pages_fetched": int(state.pages_fetched or 0),
        "records_fetched": records_fetched,
        "records_persisted": records_persisted,
        "next_page_pending": state.status == "pending" and bool(state.cursor),
        "failures": failures,
        "state_key": state_key,
    }
