"""US universe reconciliation and conservative listing lifecycle maintenance.

Discovery providers are observations, not authoritative truth.  This service
keeps every page in the existing snapshot tables, records the latest per-symbol
state, and requires repeated complete absences before a listing is marked
inactive.  A transient provider outage therefore cannot delist the universe.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.asset_class import InstrumentType
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.models.instrument_reconciliation import InstrumentReconciliationIssue
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    CalendarExceptionKind,
    ExchangeCalendarException,
    Issuer,
    MarketEvent,
    MarketUniverseLifecycleObservation,
    MarketUniverseReconciliationRun,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_runtime import ProviderCapability
from app.providers import get_discovery_provider
from app.services.exchange_catalog import (
    coerce_listing_lifecycle_at,
    ensure_exchange,
    normalize_exchange_mic,
    upsert_instrument_listing,
)
from app.services.instrument_mastering import ensure_internal_identifier, register_provider_symbol
from app.services.market_data_identity import apply_domain_identity
from app.services.market_data_monitoring import record_coverage_snapshot
from app.services.provider_observations import store_universe_discovery_snapshot
from app.services.provider_runtime import execute_provider_call, resolve_provider_chain

logger = logging.getLogger(__name__)

_MISSING_CONFIRMATIONS = 3
_ACTIVE_STATUSES = {"active", "listed", "tradable", "live"}
_TYPE_MAP: dict[str, tuple[str, str]] = {
    "EQUITY": ("Equity", "Stock"),
    "ETF": ("Equity", "ETF"),
    "ETN": ("Equity", "ETN"),
    "INDEX": ("Index", "Index"),
    "FUTURE": ("Commodity", "Future"),
    "CRYPTOCURRENCY": ("Cryptocurrency", "Crypto Spot"),
}


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current if current.tzinfo is not None else current.replace(tzinfo=UTC)


def _row_symbol(row: dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").strip().upper()


def _normalize_cik(value: Any) -> str:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return digits.zfill(10) if digits else ""


def _row_type(row: dict[str, Any], fallback: str) -> str:
    value = str(row.get("quoteType") or row.get("instrument_type") or fallback).strip().upper()
    return "EQUITY" if value in {"CS", "COMMON_STOCK", "STOCK", "EQUITIES"} else value


def _listing_key(
    symbol: str, exchange_mic: str | None, quote_type: str
) -> tuple[str, str | None, str]:
    return symbol, exchange_mic, quote_type


async def _instrument_type_id(db: AsyncSession, quote_type: str) -> int:
    asset_class, type_name = _TYPE_MAP.get(quote_type, ("Equity", "Stock"))
    from app.models.asset_class import AssetClass

    asset = (
        await db.execute(select(AssetClass).where(AssetClass.name == asset_class))
    ).scalar_one_or_none()
    if asset is None:
        asset = AssetClass(name=asset_class, description=asset_class)
        db.add(asset)
        await db.flush()
    instrument_type = (
        await db.execute(
            select(InstrumentType).where(
                InstrumentType.asset_class_id == asset.id,
                InstrumentType.name == type_name,
            )
        )
    ).scalar_one_or_none()
    if instrument_type is None:
        instrument_type = InstrumentType(
            asset_class_id=asset.id,
            name=type_name,
            description=type_name,
        )
        db.add(instrument_type)
        await db.flush()
    return instrument_type.id


async def _find_instrument(
    db: AsyncSession,
    *,
    symbol: str,
    exchange_id: int | None,
    sec_cik: Any = None,
) -> Instrument | None:
    if sec_cik not in (None, ""):
        cik = _normalize_cik(sec_cik)
        if cik:
            # CIK is an issuer identifier, not a security identifier. Use it
            # to narrow an exact existing listing, but never infer a ticker
            # change or share-class merge from CIK alone.
            by_issuer = (
                (
                    await db.execute(
                        select(Instrument)
                        .join(Issuer, Issuer.id == Instrument.issuer_id)
                        .where(Issuer.cik == cik)
                    )
                )
                .scalars()
                .all()
            )
            if by_issuer:
                issuer_ids = [candidate.id for candidate in by_issuer]
                issuer_symbol_query = (
                    select(Instrument)
                    .join(InstrumentListing, InstrumentListing.instrument_id == Instrument.id)
                    .where(
                        Instrument.id.in_(issuer_ids),
                        InstrumentListing.ticker == symbol,
                    )
                )
                if exchange_id is None:
                    issuer_symbol_query = issuer_symbol_query.where(
                        InstrumentListing.exchange_id.is_(None)
                    )
                else:
                    issuer_symbol_query = issuer_symbol_query.where(
                        InstrumentListing.exchange_id == exchange_id
                    )
                issuer_matches = (await db.execute(issuer_symbol_query)).scalars().unique().all()
                if len(issuer_matches) == 1:
                    return issuer_matches[0]
                # A CIK-only feed cannot distinguish a ticker change from a
                # newly listed share class. Never merge a new symbol into an
                # issuer's existing instrument without a security key.
                return None

            # Older rows may have CIK in the instrument identifier table. It
            # remains a compatibility fallback, but new reconciliation rows
            # never write CIK there because it is issuer-scoped.
            by_legacy_cik = (
                (
                    await db.execute(
                        select(Instrument)
                        .join(
                            InstrumentIdentifier,
                            InstrumentIdentifier.instrument_id == Instrument.id,
                        )
                        .where(
                            InstrumentIdentifier.identifier_type == InstrumentIdentifierType.CIK,
                            InstrumentIdentifier.identifier_value == cik,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if by_legacy_cik:
                legacy_ids = [candidate.id for candidate in by_legacy_cik]
                legacy_symbol_query = (
                    select(Instrument)
                    .join(InstrumentListing, InstrumentListing.instrument_id == Instrument.id)
                    .where(
                        Instrument.id.in_(legacy_ids),
                        InstrumentListing.ticker == symbol,
                    )
                )
                if exchange_id is None:
                    legacy_symbol_query = legacy_symbol_query.where(
                        InstrumentListing.exchange_id.is_(None)
                    )
                else:
                    legacy_symbol_query = legacy_symbol_query.where(
                        InstrumentListing.exchange_id == exchange_id
                    )
                legacy_matches = (await db.execute(legacy_symbol_query)).scalars().unique().all()
                if len(legacy_matches) == 1:
                    return legacy_matches[0]
                return None

            # A provider-supplied issuer key with no canonical issuer row is
            # stronger than a bare ticker; do not merge it into an unrelated
            # symbol match.
            return None
    query = (
        select(Instrument)
        .join(InstrumentListing, InstrumentListing.instrument_id == Instrument.id)
        .where(InstrumentListing.ticker == symbol)
    )
    if exchange_id is None:
        query = query.where(InstrumentListing.exchange_id.is_(None))
    else:
        query = query.where(InstrumentListing.exchange_id == exchange_id)
    candidates = (await db.execute(query)).scalars().unique().all()
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return None
    # An exchange-qualified discovery row must never fall back to a ticker-only
    # match from another venue. That would silently merge two securities that
    # happen to share a symbol. Unqualified legacy rows may still use the
    # compatibility symbol fallback when it is globally unambiguous.
    if exchange_id is not None:
        return None
    by_symbol = (
        (await db.execute(select(Instrument).where(Instrument.symbol == symbol))).scalars().all()
    )
    return by_symbol[0] if len(by_symbol) == 1 else None


async def _quarantine_candidate(
    db: AsyncSession,
    *,
    data_source_id: int,
    provider_name: str,
    symbol: str,
    exchange_mic: str | None,
    payload: dict[str, Any],
    reason: str,
) -> None:
    fingerprint = f"{provider_name}:{symbol}:{exchange_mic}:{reason}"
    existing = (
        await db.execute(
            select(InstrumentReconciliationIssue).where(
                InstrumentReconciliationIssue.data_source_id == data_source_id,
                InstrumentReconciliationIssue.provider_symbol == symbol,
                InstrumentReconciliationIssue.issue_type == "unresolved_universe_identity",
                InstrumentReconciliationIssue.fingerprint == fingerprint,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            InstrumentReconciliationIssue(
                data_source_id=data_source_id,
                provider_symbol=symbol,
                issue_type="unresolved_universe_identity",
                fingerprint=fingerprint,
                status="open",
                candidates=payload.get("identity_ambiguity"),
                payload={"reason": reason, "quote": payload},
                observed_at=_utc(),
            )
        )


async def _upsert_observation(
    db: AsyncSession,
    *,
    data_source_id: int,
    run_id: int,
    symbol: str,
    exchange_mic: str | None,
    quote_type: str,
    instrument_id: int | None,
    listing_id: int | None,
    payload: dict[str, Any],
    present: bool = True,
    observed_at: datetime,
) -> MarketUniverseLifecycleObservation:
    query = select(MarketUniverseLifecycleObservation).where(
        MarketUniverseLifecycleObservation.data_source_id == data_source_id,
        MarketUniverseLifecycleObservation.provider_symbol == symbol,
        MarketUniverseLifecycleObservation.quote_type == quote_type,
    )
    if exchange_mic is None:
        query = query.where(MarketUniverseLifecycleObservation.exchange_mic.is_(None))
    else:
        query = query.where(MarketUniverseLifecycleObservation.exchange_mic == exchange_mic)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        row = MarketUniverseLifecycleObservation(
            data_source_id=data_source_id,
            run_id=run_id,
            instrument_id=instrument_id,
            listing_id=listing_id,
            provider_symbol=symbol,
            exchange_mic=exchange_mic,
            quote_type=quote_type,
            observed_at=observed_at,
            present=present,
            lifecycle_status="active" if present else "missing_pending",
            first_seen_at=observed_at,
            last_seen_at=observed_at if present else None,
            consecutive_seen=1 if present else 0,
            consecutive_missing=0 if present else 1,
            payload=payload,
        )
        db.add(row)
        await db.flush()
        return row
    was_present = bool(row.present)
    row.run_id = run_id
    row.instrument_id = instrument_id or row.instrument_id
    row.listing_id = listing_id or row.listing_id
    row.observed_at = observed_at
    row.present = present
    row.payload = payload
    if present:
        row.last_seen_at = observed_at
        row.consecutive_seen = row.consecutive_seen + 1 if was_present else 1
        row.consecutive_missing = 0
        row.lifecycle_status = "active"
    else:
        row.last_missing_at = observed_at
        row.consecutive_missing = row.consecutive_missing + 1 if not was_present else 1
        row.consecutive_seen = 0
        row.lifecycle_status = (
            "missing" if row.consecutive_missing >= _MISSING_CONFIRMATIONS else "missing_pending"
        )
    await db.flush()
    return row


async def _deactivate_if_unlisted(db: AsyncSession, instrument_id: int) -> bool:
    active_listing = (
        await db.execute(
            select(func.count(InstrumentListing.id)).where(
                InstrumentListing.instrument_id == instrument_id,
                InstrumentListing.is_active.is_(True),
            )
        )
    ).scalar_one()
    if active_listing:
        return False
    instrument = await db.get(Instrument, instrument_id)
    if instrument is None or not instrument.is_active:
        return False
    instrument.is_active = False
    instrument.identity_status = "retired"
    return True


async def _reconcile_rows(
    db: AsyncSession,
    *,
    run: MarketUniverseReconciliationRun,
    provider_name: str,
    rows: list[dict[str, Any]],
    quote_type: str,
    observed_at: datetime,
    missing_confirmations: int = _MISSING_CONFIRMATIONS,
) -> set[tuple[str, str | None, str]]:
    active_keys: set[tuple[str, str | None, str]] = set()
    for quote in rows:
        if not isinstance(quote, dict):
            continue
        symbol = _row_symbol(quote)
        if not symbol:
            continue
        normalized_type = _row_type(quote, quote_type)
        exchange = await ensure_exchange(db, quote.get("exchange"))
        exchange_mic = normalize_exchange_mic(quote.get("exchange"))
        key = _listing_key(symbol, exchange_mic, normalized_type)
        active_keys.add(key)
        if quote.get("identity_ambiguity"):
            await _quarantine_candidate(
                db,
                data_source_id=run.data_source_id,
                provider_name=provider_name,
                symbol=symbol,
                exchange_mic=exchange_mic,
                payload=quote,
                reason="provider returned multiple issuer candidates",
            )
            run.quarantined_count += 1
            continue

        instrument = await _find_instrument(
            db,
            symbol=symbol,
            exchange_id=exchange.id if exchange else None,
            sec_cik=quote.get("sec_cik") or quote.get("cik"),
        )
        created = instrument is None
        if instrument is None:
            instrument = Instrument(
                symbol=symbol,
                name=str(quote.get("longName") or quote.get("name") or symbol),
                instrument_type_id=await _instrument_type_id(db, normalized_type),
                currency=str(quote.get("currency") or "USD")[:3],
                is_active=True,
            )
            db.add(instrument)
            await db.flush()
            cik = _normalize_cik(quote.get("sec_cik") or quote.get("cik"))
            if cik:
                issuer = (
                    await db.execute(select(Issuer).where(Issuer.cik == cik))
                ).scalar_one_or_none()
                if issuer is None:
                    issuer = Issuer(
                        domain_key=f"cik:{cik}",
                        legal_name=str(quote.get("longName") or quote.get("name") or symbol),
                        cik=cik,
                        country_code="US",
                        provenance={
                            "source": provider_name,
                            "observed_at": observed_at.isoformat(),
                        },
                    )
                    db.add(issuer)
                    await db.flush()
                instrument.issuer_id = issuer.id

            # Discovery feeds commonly supply only SEC CIK. Keep the issuer
            # link, but require a security-level identifier (FIGI, ISIN,
            # CUSIP, or SEDOL) before assigning a domain key. This prevents
            # two share classes from being collapsed under one CIK.
            security_identifiers: dict[InstrumentIdentifierType, str] = {}
            for key, identifier_type in (
                ("figi", InstrumentIdentifierType.FIGI),
                ("composite_figi", InstrumentIdentifierType.COMPOSITE_FIGI),
                ("isin", InstrumentIdentifierType.ISIN),
                ("cusip", InstrumentIdentifierType.CUSIP),
                ("sedol", InstrumentIdentifierType.SEDOL),
            ):
                value = str(quote.get(key) or "").strip().upper()
                if value:
                    security_identifiers[identifier_type] = value
            primary_identifier_assigned = False
            for identifier_type, value in list(security_identifiers.items()):
                existing_identifier = (
                    await db.execute(
                        select(InstrumentIdentifier).where(
                            InstrumentIdentifier.identifier_type == identifier_type,
                            InstrumentIdentifier.identifier_value == value,
                        )
                    )
                ).scalar_one_or_none()
                if existing_identifier is None:
                    db.add(
                        InstrumentIdentifier(
                            instrument_id=instrument.id,
                            identifier_type=identifier_type,
                            identifier_value=value,
                            is_primary=not primary_identifier_assigned,
                            effective_at=coerce_listing_lifecycle_at(quote.get("ipo_date")),
                            known_at=observed_at,
                            extra_data={"source": provider_name},
                        )
                    )
                    primary_identifier_assigned = True
                elif existing_identifier.instrument_id != instrument.id:
                    await _quarantine_candidate(
                        db,
                        data_source_id=run.data_source_id,
                        provider_name=provider_name,
                        symbol=symbol,
                        exchange_mic=exchange_mic,
                        payload=quote,
                        reason=(
                            "security identifier is already owned by instrument "
                            f"{existing_identifier.instrument_id}"
                        ),
                    )
                    security_identifiers.pop(identifier_type, None)
            await db.flush()

            # Keep a canonical row for lifecycle bookkeeping, but require
            # identity review when the discovery feed has no security key.
            await apply_domain_identity(
                db,
                instrument,
                identifiers=security_identifiers,
                provider_name=provider_name,
                provider_symbol=symbol,
                exchange_mic=exchange_mic,
                candidate_payload=quote,
            )
            run.new_count += 1
        else:
            run.updated_count += 1
            if quote.get("longName") or quote.get("name"):
                instrument.name = str(quote.get("longName") or quote.get("name"))
            instrument.is_active = True

        listing = await upsert_instrument_listing(
            db,
            instrument,
            symbol,
            exchange_code=quote.get("exchange"),
            currency=quote.get("currency") or "USD",
            is_primary=True,
            reactivate_existing=True,
            effective_at=coerce_listing_lifecycle_at(quote.get("ipo_date")),
            known_at=observed_at,
            delisted_at=coerce_listing_lifecycle_at(quote.get("delisting_date")),
            source=provider_name,
            provenance={"reconciliation_run_id": run.id, "quote_type": normalized_type},
        )
        status = str(quote.get("status") or "active").strip().lower()
        if status not in _ACTIVE_STATUSES or quote.get("delisting_date"):
            listing.is_active = False
            listing.delisted_at = listing.delisted_at or observed_at
            await _deactivate_if_unlisted(db, instrument.id)
        await register_provider_symbol(
            db,
            instrument,
            provider_name,
            symbol,
            provider_exchange_code=quote.get("exchange"),
            provider_instrument_type=normalized_type,
            currency=quote.get("currency") or "USD",
            is_primary=True,
            extra_data={"reconciliation_run_id": run.id, "lifecycle_status": status},
            reactivate_existing=status in _ACTIVE_STATUSES,
            effective_at=coerce_listing_lifecycle_at(quote.get("ipo_date")),
            known_at=observed_at,
            delisted_at=coerce_listing_lifecycle_at(quote.get("delisting_date")),
        )
        await ensure_internal_identifier(db, instrument)
        await _upsert_observation(
            db,
            data_source_id=run.data_source_id,
            run_id=run.id,
            symbol=symbol,
            exchange_mic=exchange_mic,
            quote_type=normalized_type,
            instrument_id=instrument.id,
            listing_id=listing.id,
            payload=quote,
            observed_at=observed_at,
        )
        run.observed_count += 1
        if created:
            event_type = "listing_discovered"
            db.add(
                MarketEvent(
                    instrument_id=instrument.id,
                    event_type=event_type,
                    event_key=f"{provider_name}:{symbol}:{event_type}:{observed_at.date().isoformat()}",
                    event_time=observed_at,
                    effective_date=observed_at.date(),
                    source=provider_name,
                    payload={"exchange_mic": exchange_mic, "quote": quote},
                    is_provisional=True,
                )
            )
    return active_keys


async def _mark_missing(
    db: AsyncSession,
    *,
    run: MarketUniverseReconciliationRun,
    provider_name: str,
    quote_type: str,
    active_keys: set[tuple[str, str | None, str]],
    observed_at: datetime,
    missing_confirmations: int,
) -> None:
    observations = (
        (
            await db.execute(
                select(MarketUniverseLifecycleObservation).where(
                    MarketUniverseLifecycleObservation.data_source_id == run.data_source_id,
                    MarketUniverseLifecycleObservation.quote_type == quote_type,
                )
            )
        )
        .scalars()
        .all()
    )
    for observation in observations:
        key = _listing_key(
            observation.provider_symbol, observation.exchange_mic, observation.quote_type
        )
        if key in active_keys:
            continue
        if (
            observation.lifecycle_status in {"missing", "missing_pending"}
            and not observation.present
        ):
            observation.consecutive_missing += 1
        else:
            observation.consecutive_missing = 1
        observation.present = False
        observation.last_missing_at = observed_at
        observation.observed_at = observed_at
        observation.run_id = run.id
        observation.consecutive_seen = 0
        observation.lifecycle_status = (
            "missing"
            if observation.consecutive_missing >= missing_confirmations
            else "missing_pending"
        )
        run.missing_count += 1
        if observation.consecutive_missing < missing_confirmations:
            continue
        if observation.listing_id is not None:
            listing = await db.get(InstrumentListing, observation.listing_id)
            if listing is not None and listing.is_active:
                listing.is_active = False
                listing.delisted_at = listing.delisted_at or observed_at
                db.add(
                    MarketEvent(
                        instrument_id=observation.instrument_id,
                        event_type="listing_delisted_candidate",
                        event_key=f"{provider_name}:{observation.provider_symbol}:delisted:{observed_at.date().isoformat()}",
                        event_time=observed_at,
                        effective_date=observed_at.date(),
                        source=provider_name,
                        payload={
                            "exchange_mic": observation.exchange_mic,
                            "confirmations": observation.consecutive_missing,
                        },
                        is_provisional=True,
                    )
                )
        if observation.instrument_id is not None and await _deactivate_if_unlisted(
            db, observation.instrument_id
        ):
            run.deactivated_count += 1


async def reconcile_us_universe(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
    quote_types: list[str] | None = None,
    missing_confirmations: int | None = None,
) -> dict[str, Any]:
    """Reconcile one or more complete US discovery feeds conservatively."""
    confirmations = max(
        1,
        int(
            missing_confirmations
            if missing_confirmations is not None
            else settings.MARKET_UNIVERSE_MISSING_CONFIRMATIONS
        ),
    )
    chain = await resolve_provider_chain(db, ProviderCapability.UNIVERSE_DISCOVERY)
    if provider_name:
        chain = [item for item in chain if item.provider_name == provider_name]
    if not chain:
        return {"status": "no_provider", "providers": [], "runs": []}
    results: list[dict[str, Any]] = []
    for resolved in chain:
        provider = get_discovery_provider(resolved.provider_name)
        requested_types = quote_types or provider.supported_discovery_types()
        for quote_type in requested_types:
            observed_at = _utc()
            run = MarketUniverseReconciliationRun(
                data_source_id=resolved.data_source.id,
                quote_type=quote_type,
                observed_at=observed_at,
                status="running",
                provenance={
                    "provider": resolved.provider_name,
                    "complete_absence_confirmation": confirmations,
                },
            )
            db.add(run)
            await db.flush()
            rows: list[dict[str, Any]] = []
            offset = 0
            total: int | None = None
            try:
                while True:
                    execution = await execute_provider_call(
                        db,
                        ProviderCapability.UNIVERSE_DISCOVERY,
                        f"reconcile_universe_page:{quote_type}:{offset}",
                        provider_name=resolved.provider_name,
                        invoke=lambda candidate, _symbol: candidate.discover_universe_page(
                            quote_type, offset
                        ),
                        response_items=lambda page: len(page.get("quotes") or []),
                        # An empty terminal page is valid for cursor-based
                        # feeds after at least one page, but an empty first
                        # page is never accepted as a complete universe.
                        treat_empty_as_failure=not bool(rows),
                    )
                    page = execution.result or {}
                    await store_universe_discovery_snapshot(
                        db,
                        data_source_id=execution.data_source.id,
                        quote_type=quote_type,
                        offset=offset,
                        page=page,
                        observed_at=observed_at,
                        fetched_at=observed_at,
                    )
                    page_rows = [row for row in (page.get("quotes") or []) if isinstance(row, dict)]
                    rows.extend(page_rows)
                    declared_total = page.get("total")
                    if declared_total is not None:
                        page_total = int(declared_total)
                        if page_total < 0:
                            raise ValueError("discovery provider returned a negative total")
                        if total is None:
                            total = page_total
                        elif total != page_total:
                            raise ValueError("discovery provider changed its declared total")
                        if total < offset + len(page_rows):
                            raise ValueError("discovery provider total is smaller than observed rows")
                    next_offset = page.get("next_offset")
                    next_url = bool(page.get("next_url"))
                    if isinstance(next_offset, int) and next_offset > offset:
                        if next_offset > 2_000_000:
                            raise ValueError("discovery provider exceeded safety page limit")
                        offset = next_offset
                        continue
                    if next_url:
                        offset += len(page_rows)
                        if offset > 2_000_000:
                            raise ValueError("discovery provider exceeded safety page limit")
                        continue
                    offset += len(page_rows)
                    if total is not None:
                        if offset >= total:
                            break
                        raise ValueError(
                            "discovery provider omitted pagination before declared total"
                        )
                    if page.get("complete") is True:
                        break
                    if not page_rows:
                        raise ValueError(
                            "discovery provider returned an empty page without completion evidence"
                        )
                    raise ValueError(
                        "discovery provider omitted total and completion evidence"
                    )
                run.expected_count = total if total is not None else len(rows)
                active_keys = await _reconcile_rows(
                    db,
                    run=run,
                    provider_name=resolved.provider_name,
                    rows=rows,
                    quote_type=quote_type,
                    observed_at=observed_at,
                )
                await _mark_missing(
                    db,
                    run=run,
                    provider_name=resolved.provider_name,
                    quote_type=quote_type,
                    active_keys=active_keys,
                    observed_at=observed_at,
                    missing_confirmations=confirmations,
                )
                run.status = "complete"
            except Exception as exc:
                # A failed/empty provider run is never treated as a complete
                # universe.  Its snapshots and error remain inspectable.
                run.status = "failed"
                run.error = str(exc)[:4000]
                logger.warning(
                    "universe reconciliation %s/%s failed: %s",
                    resolved.provider_name,
                    quote_type,
                    exc,
                )
            run.finished_at = _utc()
            await db.commit()
            results.append(
                {
                    "provider": resolved.provider_name,
                    "quote_type": quote_type,
                    "status": run.status,
                    "expected": run.expected_count,
                    "observed": run.observed_count,
                    "new": run.new_count,
                    "missing": run.missing_count,
                    "deactivated": run.deactivated_count,
                    "quarantined": run.quarantined_count,
                }
            )
    statuses = [row["status"] for row in results]
    overall_status = (
        "complete"
        if statuses and all(status == "complete" for status in statuses)
        else "failed"
        if statuses and all(status == "failed" for status in statuses)
        else "partial"
    )
    return {
        "status": overall_status,
        "providers": sorted({row["provider"] for row in results}),
        "runs": results,
    }


def _latest_expected_session(value: date) -> date:
    current = value
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _latest_expected_session_for_exchange(
    value: date,
    exchange_id: int | None,
    closed_dates: set[date],
) -> date:
    current = value
    while current.weekday() >= 5 or (exchange_id is not None and current in closed_dates):
        current -= timedelta(days=1)
    return current


async def record_core_daily_coverage(
    db: AsyncSession,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Record one D1 coverage row per active instrument without fabricating bars."""
    current = _utc(as_of)
    target = _latest_expected_session(current.date())
    latest_rows = (
        await db.execute(
            select(OHLCVBar.instrument_id, func.max(OHLCVBar.ts))
            .join(Instrument, Instrument.id == OHLCVBar.instrument_id)
            .where(
                Instrument.is_active.is_(True),
                Instrument.is_synthetic.is_(False),
                OHLCVBar.timeframe == Timeframe.D1,
                OHLCVBar.is_adjusted.is_(True),
            )
            .group_by(OHLCVBar.instrument_id)
        )
    ).all()
    latest_by_instrument = {
        instrument_id: _utc(ts) if ts else None for instrument_id, ts in latest_rows
    }
    instrument_rows = (
        await db.execute(
            select(Instrument.id, func.min(InstrumentListing.exchange_id))
            .outerjoin(
                InstrumentListing,
                (InstrumentListing.instrument_id == Instrument.id)
                & InstrumentListing.is_primary.is_(True)
                & InstrumentListing.is_active.is_(True),
            )
            .where(Instrument.is_active.is_(True), Instrument.is_synthetic.is_(False))
            .group_by(Instrument.id)
        )
    ).all()
    exchange_ids = {exchange_id for _, exchange_id in instrument_rows if exchange_id is not None}
    closed_by_exchange: dict[int, set[date]] = {}
    if exchange_ids:
        exceptions = (
            (
                await db.execute(
                    select(ExchangeCalendarException).where(
                        ExchangeCalendarException.exchange_id.in_(exchange_ids),
                        ExchangeCalendarException.session_date <= current.date(),
                        ExchangeCalendarException.session_date
                        >= current.date() - timedelta(days=14),
                        ExchangeCalendarException.exception_kind.in_(
                            {CalendarExceptionKind.HOLIDAY, CalendarExceptionKind.CLOSED}
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for exception in exceptions:
            closed_by_exchange.setdefault(exception.exchange_id, set()).add(exception.session_date)
    complete = 0
    for instrument_id, exchange_id in instrument_rows:
        instrument_target = _latest_expected_session_for_exchange(
            current.date(), exchange_id, closed_by_exchange.get(exchange_id, set())
        )
        latest = latest_by_instrument.get(instrument_id)
        observed = int(latest is not None and latest.date() >= instrument_target)
        if observed:
            complete += 1
        await record_coverage_snapshot(
            db,
            instrument_id=instrument_id,
            market_series_id=None,
            timeframe=Timeframe.D1.value,
            expected_bars=1,
            observed_bars=observed,
            expected_start=datetime.combine(instrument_target, datetime.min.time(), tzinfo=UTC),
            expected_end=datetime.combine(
                instrument_target + timedelta(days=1), datetime.min.time(), tzinfo=UTC
            ),
            evaluated_at=current,
            provenance={
                "source": "core_daily_coverage",
                "target_session": instrument_target.isoformat(),
                "exchange_id": exchange_id,
            },
        )
    total = len(instrument_rows)
    return {
        "target_session": target,
        "eligible_instruments": total,
        "complete_instruments": complete,
        "coverage_ratio": complete / total if total else 0.0,
    }
