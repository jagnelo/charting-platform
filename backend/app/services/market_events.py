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

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.market_data_foundation import Issuer
from app.models.provider_runtime import ProviderCapability
from app.providers import list_provider_capabilities, supported_provider_names
from app.providers.base import MarketEventRecord
from app.providers.errors import bounded_redact_provider_message
from app.services.market_data_persistence import persist_market_event
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
        if "market_events" in capabilities:
            result.append(name)
    return result


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

    for requested_name in names:
        try:
            execution = await execute_provider_call(
                db,
                ProviderCapability.MARKET_EVENTS,
                "fetch_market_events",
                provider_name=requested_name,
                invoke=lambda provider, _provider_symbol: provider.fetch_market_events(
                    start=start,
                    end=end,
                ),
                response_items=lambda result: len(result) if isinstance(result, list) else None,
                treat_empty_as_failure=False,
            )
            records = execution.result
            if not isinstance(records, list) or any(
                not isinstance(record, MarketEventRecord) for record in records
            ):
                raise TypeError("market-event provider returned malformed records")
        except Exception as exc:  # noqa: BLE001 - retain per-provider outcome.
            provider_results.append(
                {
                    "provider": requested_name,
                    "status": "failed",
                    "events": 0,
                    "persisted": 0,
                    "linked": 0,
                    "unlinked": 0,
                    "error_type": exc.__class__.__name__,
                    "error": bounded_redact_provider_message(exc, max_length=500),
                }
            )
            continue

        provider_events = 0
        provider_persisted = 0
        provider_linked = 0
        provider_unlinked = 0
        fetched_at = datetime.now(UTC)
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
            provider_events += 1
            provider_persisted += 1
            if instrument_id is None and issuer_id is None:
                provider_unlinked += 1
            else:
                provider_linked += 1

        provider_results.append(
            {
                "provider": execution.provider_name,
                "status": "refreshed",
                "events": provider_events,
                "persisted": provider_persisted,
                "linked": provider_linked,
                "unlinked": provider_unlinked,
                "fetched_at": fetched_at,
            }
        )
        total_events += provider_events
        total_persisted += provider_persisted
        total_linked += provider_linked
        total_unlinked += provider_unlinked

    await db.commit()
    failures = sum(1 for result in provider_results if result["status"] == "failed")
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
    }
