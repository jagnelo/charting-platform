"""Persistence and refresh helpers for tokenized-security observations."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.models.market_data_foundation import AdjustmentBasis, Issuer, ProviderPaginationState
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import LatestPriceSnapshot
from app.models.provider_runtime import ProviderCapability
from app.models.tokenized_asset import TokenizedAssetDetail, TokenizedAssetObservation
from app.providers.base import TokenizedAssetRecord
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderResponseError,
    bounded_redact_provider_message,
)
from app.services.instrument_mastering import ensure_instrument_type, register_provider_symbol
from app.services.market_data import _attach_provider_series, persist_price_history_bars
from app.services.market_data_identity import normalize_identifier_value
from app.services.market_data_persistence import persist_market_event
from app.services.provider_runtime import execute_provider_call, resolve_provider_chain

_NON_PERSISTING_TOKENIZED_CANARIES = frozenset({"dinari"})


async def _tokenized_asset_refresh_batch(
    db: AsyncSession,
    *,
    capability: str,
    operation: str,
    provider_name: str | None,
    max_assets: int,
) -> tuple[list[tuple[TokenizedAssetDetail, Instrument]], ProviderPaginationState | None]:
    """Select a durable rotating asset batch for bounded per-asset refreshes.

    A failed asset must not remain permanently at the head of an
    ``updated_at``-ordered query. The cursor is only committed with the
    refresh transaction, so a process failure before commit retries the same
    batch; caught per-asset failures still advance the cursor and are retried
    after the rest of the active universe has had a turn.
    """

    scope = str(provider_name or "*").strip().lower()
    state_key = f"tokenized-refresh:{operation}:{scope}"
    state = (
        await db.execute(
            select(ProviderPaginationState).where(
                ProviderPaginationState.state_key == state_key
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = ProviderPaginationState(
            state_key=state_key,
            provider=scope,
            capability=capability,
            operation=operation,
            page_number=0,
            cursor=None,
            page_size=max_assets,
            status="pending",
            pages_fetched=0,
            last_page_count=0,
            cursor_history=[],
            metadata_payload={"scope": scope},
        )
        db.add(state)
        await db.flush()

    query = (
        select(TokenizedAssetDetail, Instrument)
        .join(Instrument, Instrument.id == TokenizedAssetDetail.instrument_id)
        .where(Instrument.is_active.is_(True))
        .order_by(TokenizedAssetDetail.id.asc())
    )
    if provider_name:
        query = query.where(TokenizedAssetDetail.provider_name == provider_name)
    rows = list((await db.execute(query)).all())
    if not rows:
        return [], state

    cursor_id = 0
    if state.cursor is not None:
        try:
            cursor_id = max(0, int(state.cursor))
        except (TypeError, ValueError):
            state.last_error = "invalid persisted tokenized refresh cursor"
            state.status = "failed"
            cursor_id = 0
    after_cursor = [row for row in rows if int(row[0].id) > cursor_id]
    before_cursor = [row for row in rows if int(row[0].id) <= cursor_id]
    selected = (after_cursor + before_cursor)[:max_assets]
    return selected, state


def _tokenized_catalog_state_key(provider_name: str, page_size: int) -> str:
    """Scope continuation by provider instance and the provider page size."""

    return f"tokenized-assets:{str(provider_name).strip().lower()}:{int(page_size)}"


async def _tokenized_catalog_state(
    db: AsyncSession,
    *,
    provider_name: str,
    page_size: int,
) -> ProviderPaginationState:
    """Load or create durable catalogue continuation state."""

    state_key = _tokenized_catalog_state_key(provider_name, page_size)
    state = (
        await db.execute(
            select(ProviderPaginationState).where(
                ProviderPaginationState.state_key == state_key
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = ProviderPaginationState(
            state_key=state_key,
            provider=str(provider_name).strip().lower(),
            capability=ProviderCapability.TOKENIZED_ASSETS.value,
            operation="discover_tokenized_assets",
            page_number=0,
            cursor=None,
            page_size=page_size,
            status="pending",
            pages_fetched=0,
            last_page_count=0,
            cursor_history=[],
            metadata_payload={},
        )
        db.add(state)
        await db.flush()
    elif state.status == "complete":
        # A completed cycle starts a fresh snapshot on the next scheduled
        # invocation. Partial/failed cycles retain their exact continuation.
        state.page_number = 0
        state.cursor = None
        state.status = "pending"
        state.pages_fetched = 0
        state.last_page_count = 0
        state.last_error = None
        state.cursor_history = []
        state.metadata_payload = {
            **(state.metadata_payload or {}),
            "previous_cycle_completed_at": state.last_success_at.isoformat()
            if state.last_success_at
            else None,
        }
    return state


async def _tokenized_event_state(
    db: AsyncSession,
    *,
    provider_name: str,
    phase: str,
    page_size: int,
) -> ProviderPaginationState:
    """Load or create durable continuation for one corporate-action feed."""

    state_key = (
        f"tokenized-events:{str(provider_name).strip().lower()}"
        f":{str(phase).strip().lower()}:{int(page_size)}"
    )
    state = (
        await db.execute(
            select(ProviderPaginationState).where(
                ProviderPaginationState.state_key == state_key
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = ProviderPaginationState(
            state_key=state_key,
            provider=str(provider_name).strip().lower(),
            capability=ProviderCapability.TOKENIZED_CORPORATE_ACTIONS.value,
            operation="fetch_tokenized_corporate_actions",
            page_number=1,
            cursor=None,
            page_size=page_size,
            status="pending",
            pages_fetched=0,
            last_page_count=0,
            cursor_history=[],
            metadata_payload={"phase": phase},
        )
        db.add(state)
        await db.flush()
    elif state.status == "complete":
        state.page_number = 1
        state.cursor = None
        state.status = "pending"
        state.pages_fetched = 0
        state.last_page_count = 0
        state.last_error = None
        state.cursor_history = []
        state.metadata_payload = {
            **(state.metadata_payload or {}),
            "previous_cycle_completed_at": state.last_success_at.isoformat()
            if state.last_success_at
            else None,
        }
    return state


async def _fair_tokenized_event_provider_order(
    db: AsyncSession,
    providers: list[Any],
) -> list[Any]:
    """Order action-feed providers so a per-job provider cap cannot starve one.

    ``max_providers`` is a per-invocation fairness budget, not a permanent
    allow-list. Providers with an incomplete/failed feed state (or no state
    yet) are preferred first; completed providers are then rotated by their
    oldest successful observation. The provider-chain order remains the final
    deterministic tie-breaker, so normal capability/health ranking still
    influences equal-age choices.
    """

    if len(providers) < 2:
        return providers
    names = [str(item.provider_name).strip().lower() for item in providers]
    rows = (
        await db.execute(
            select(ProviderPaginationState).where(
                ProviderPaginationState.provider.in_(names),
                ProviderPaginationState.capability
                == ProviderCapability.TOKENIZED_CORPORATE_ACTIONS.value,
                ProviderPaginationState.operation == "fetch_tokenized_corporate_actions",
            )
        )
    ).scalars().all()
    by_provider: dict[str, list[ProviderPaginationState]] = {}
    for row in rows:
        by_provider.setdefault(str(row.provider).strip().lower(), []).append(row)

    def fairness_key(indexed: tuple[int, Any]) -> tuple[int, float, int]:
        index, provider = indexed
        provider_name = str(provider.provider_name).strip().lower()
        states = by_provider.get(provider_name, [])
        incomplete = not states or any(state.status != "complete" for state in states)
        successful_times = [
            state.last_success_at.timestamp()
            for state in states
            if state.last_success_at is not None
        ]
        # Missing/incomplete state must be selected before a completed feed;
        # among completed feeds, the oldest successful provider goes first.
        oldest_success = min(successful_times) if successful_times else float("-inf")
        return (0 if incomplete else 1, oldest_success, index)

    return [item for _, item in sorted(enumerate(providers), key=fairness_key)]


def _ensure_provider_data_may_be_persisted(provider_name: str) -> None:
    if str(provider_name or "").strip().lower() in _NON_PERSISTING_TOKENIZED_CANARIES:
        raise ProviderNotConfiguredError(
            "Dinari Sandbox is canary-only; its responses cannot enter application persistence"
        )


def tokenized_domain_key(provider: str, asset_id: str) -> str:
    digest = hashlib.sha256(asset_id.encode("utf-8")).hexdigest()[:48]
    return f"tokenized:{provider}:{digest}"


_TOKENIZED_ASSET_ID_FIELDS = (
    "assetId",
    "asset_id",
    "stockId",
    "stock_id",
    "providerAssetId",
    "provider_asset_id",
    "tokenId",
    "token_id",
    "id",
)
_TOKENIZED_SYMBOL_FIELDS = (
    "tokenSymbol",
    "token_symbol",
    "symbol",
    "ticker",
    "assetSymbol",
    "asset_symbol",
)


def _normalized_optional_identifier(value: Any) -> str | None:
    """Canonicalize provider identifiers while preserving the raw payload."""

    if value is None or isinstance(value, bool):
        return None
    normalized = normalize_identifier_value(str(value))
    return normalized or None


def _normalized_optional_cik(value: Any) -> str | None:
    """Normalize an SEC CIK without treating malformed input as identity."""

    if value is None or isinstance(value, bool):
        return None
    digits = "".join(character for character in str(value) if character.isdigit())
    if not digits or len(digits) > 10:
        return None
    return digits.zfill(10)


async def _existing_issuer_id_for_cik(db: AsyncSession, cik: str | None) -> int | None:
    """Link only to an already materialized, unique issuer row."""

    if not cik:
        return None
    rows = (await db.execute(select(Issuer.id).where(Issuer.cik == cik).limit(2))).scalars().all()
    return int(rows[0]) if len(rows) == 1 else None
_EVENT_ID_FIELDS = (
    "eventId",
    "event_id",
    "corporateActionId",
    "corporate_action_id",
    "actionId",
    "action_id",
    "id",
)
_EVENT_TIME_FIELDS = (
    "eventTime",
    "event_time",
    "announcedAt",
    "announced_at",
    "createdAt",
    "created_at",
)
_ANNOUNCED_AT_FIELDS = ("announcedAt", "announced_at", "announcementDate", "announcement_date")
_EFFECTIVE_DATE_FIELDS = (
    "effectiveDate",
    "effective_date",
    "exDate",
    "ex_date",
    "recordDate",
    "record_date",
    "paymentDate",
    "payment_date",
    "date",
)


def _first_scalar(row: dict[str, Any], fields: tuple[str, ...]) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, "") and not isinstance(value, dict | list):
            return value
    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return date.fromisoformat(candidate[:10])
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or not re.search(r"[T ]", candidate):
        return None
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _tokenized_action_key(provider_name: str, row: dict[str, Any]) -> str:
    """Build a stable, bounded key without treating a ticker as identity."""

    asset_id = _first_scalar(row, _TOKENIZED_ASSET_ID_FIELDS)
    event_id = _first_scalar(row, _EVENT_ID_FIELDS)
    identity = {
        "provider": provider_name,
        "asset_id": str(asset_id) if asset_id is not None else None,
        "event_id": str(event_id) if event_id is not None else None,
        "payload": row if event_id is None else None,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:48]
    return f"tokenized-action:{provider_name}:{digest}"


async def _tokenized_detail_maps(
    db: AsyncSession, provider_name: str
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    rows = (
        await db.execute(
            select(
                TokenizedAssetDetail.provider_asset_id,
                TokenizedAssetDetail.token_symbol,
                TokenizedAssetDetail.instrument_id,
            ).where(TokenizedAssetDetail.provider_name == provider_name)
        )
    ).all()
    by_asset: dict[str, list[int]] = {}
    by_symbol: dict[str, list[int]] = {}
    for provider_asset_id, token_symbol, instrument_id in rows:
        if provider_asset_id:
            by_asset.setdefault(str(provider_asset_id).lower(), []).append(instrument_id)
        if token_symbol:
            by_symbol.setdefault(str(token_symbol).upper(), []).append(instrument_id)
    return by_asset, by_symbol


def _resolve_tokenized_instrument(
    row: dict[str, Any],
    by_asset: dict[str, list[int]],
    by_symbol: dict[str, list[int]],
) -> int | None:
    asset_id = _first_scalar(row, _TOKENIZED_ASSET_ID_FIELDS)
    if asset_id is not None:
        matches = by_asset.get(str(asset_id).lower(), [])
        return matches[0] if len(matches) == 1 else None
    symbol = _first_scalar(row, _TOKENIZED_SYMBOL_FIELDS)
    if symbol is not None:
        matches = by_symbol.get(str(symbol).upper(), [])
        return matches[0] if len(matches) == 1 else None
    return None


def _tokenized_event_payload(
    provider_name: str, row: dict[str, Any], *, phase: str
) -> dict[str, Any]:
    """Retain the provider row while exposing only explicit normalized fields."""

    action_type = _first_scalar(row, ("actionType", "action_type", "type", "kind"))
    asset_id = _first_scalar(row, _TOKENIZED_ASSET_ID_FIELDS)
    symbol = _first_scalar(row, _TOKENIZED_SYMBOL_FIELDS)
    return {
        "provider": provider_name,
        "provider_asset_id": str(asset_id) if asset_id is not None else None,
        "token_symbol": str(symbol) if symbol is not None else None,
        "action_type": str(action_type) if action_type is not None else None,
        "refresh_phase": phase,
        "raw": row,
    }


async def _underlying_instrument(
    db: AsyncSession,
    *,
    symbol: str | None,
    figi: str | None,
    composite_figi: str | None,
    isin: str | None,
    cusip: str | None,
) -> tuple[Instrument | None, str]:
    """Resolve a token's economic underlying with stable-ID-first semantics.

    A provider-supplied ISIN is security-level evidence. If it is present but
    cannot be resolved uniquely, do not weaken it to a ticker-only match: that
    could attach a token to the wrong share class or venue. Ticker matching is
    retained only for records that carry no stable underlying identifier and is
    still accepted only when exactly one active instrument has that symbol.
    """

    stable_identifiers = (
        ("figi", figi, InstrumentIdentifierType.FIGI),
        ("composite_figi", composite_figi, InstrumentIdentifierType.COMPOSITE_FIGI),
        ("isin", isin, InstrumentIdentifierType.ISIN),
        ("cusip", cusip, InstrumentIdentifierType.CUSIP),
    )
    supplied: list[tuple[str, str, InstrumentIdentifierType]] = []
    for label, value, identifier_type in stable_identifiers:
        normalized = _normalized_optional_identifier(value)
        if normalized:
            supplied.append((label, normalized, identifier_type))
    if supplied:
        candidates: dict[int, Instrument] = {}
        matched_labels: list[str] = []
        for label, value, identifier_type in supplied:
            queries = [
                select(Instrument).where(
                    Instrument.is_active.is_(True),
                    Instrument.domain_key == f"{label.replace('_', '-')}:{value}",
                )
            ]
            if identifier_type is InstrumentIdentifierType.ISIN:
                queries.append(
                    select(Instrument).where(
                        Instrument.isin == value,
                        Instrument.is_active.is_(True),
                    )
                )
            queries.append(
                select(Instrument)
                .join(InstrumentIdentifier, InstrumentIdentifier.instrument_id == Instrument.id)
                .where(
                    InstrumentIdentifier.identifier_type == identifier_type,
                    InstrumentIdentifier.identifier_value == value,
                    InstrumentIdentifier.is_active.is_(True),
                    Instrument.is_active.is_(True),
                )
            )
            matched = {
                candidate.id: candidate
                for query in queries
                for candidate in (await db.execute(query)).scalars().all()
            }
            if matched:
                matched_labels.append(label)
                candidates.update(matched)
        if len(candidates) == 1 and matched_labels:
            return next(iter(candidates.values())), f"linked_by_{matched_labels[0]}"
        strongest = supplied[0][0]
        return None, f"unresolved_or_ambiguous_{strongest}"

    if not symbol:
        return None, "unresolved_or_ambiguous"
    rows = (
        await db.execute(
            select(Instrument)
            .where(Instrument.symbol == symbol, Instrument.is_active.is_(True))
            .limit(2)
        )
    ).scalars().all()
    # A ticker alone is not enough to link an underlying when multiple active
    # listings share it.  The token remains valid but its relationship stays
    # unresolved until authoritative identity evidence is available.
    return (rows[0], "linked_by_symbol") if len(rows) == 1 else (None, "unresolved_or_ambiguous")


async def upsert_tokenized_asset(
    db: AsyncSession,
    record: TokenizedAssetRecord,
    *,
    source_payload: dict[str, Any] | None = None,
) -> Instrument:
    _ensure_provider_data_may_be_persisted(record.provider)
    type_id = await ensure_instrument_type(db, "Tokenized Securities", "Tokenized Security")
    domain_key = tokenized_domain_key(record.provider, record.asset_id)
    instrument = (
        await db.execute(select(Instrument).where(Instrument.domain_key == domain_key))
    ).scalar_one_or_none()
    if instrument is None:
        instrument = Instrument(
            instrument_type_id=type_id,
            symbol=record.symbol or record.asset_id,
            name=record.name or record.symbol or record.asset_id,
            currency=record.currency,
            is_active=record.status not in {"inactive", "delisted", "halted"},
            domain_key=domain_key,
            identity_status="verified_provider_asset",
            isin=record.isin,
            primary_identifier_type="isin" if record.isin else "provider_asset_id",
            primary_identifier_value=record.isin or record.asset_id,
            field_provenance={},
        )
        db.add(instrument)
        await db.flush()
    else:
        instrument.name = record.name or instrument.name
        instrument.currency = record.currency or instrument.currency
        instrument.isin = record.isin or instrument.isin
        instrument.is_active = record.status not in {"inactive", "delisted", "halted"}

    underlying_figi = _normalized_optional_identifier(record.underlying_figi)
    underlying_composite_figi = _normalized_optional_identifier(record.underlying_composite_figi)
    underlying_isin = _normalized_optional_identifier(record.underlying_isin)
    underlying_cusip = _normalized_optional_identifier(record.underlying_cusip)
    underlying_cik = _normalized_optional_cik(record.underlying_cik)
    underlying, underlying_link_status = await _underlying_instrument(
        db,
        symbol=record.underlying_symbol,
        figi=underlying_figi,
        composite_figi=underlying_composite_figi,
        isin=underlying_isin,
        cusip=underlying_cusip,
    )
    underlying_issuer_id = await _existing_issuer_id_for_cik(db, underlying_cik)
    detail = (
        await db.execute(
            select(TokenizedAssetDetail).where(TokenizedAssetDetail.instrument_id == instrument.id)
        )
    ).scalar_one_or_none()
    if detail is None:
        detail = TokenizedAssetDetail(
            instrument_id=instrument.id,
            provider_asset_id=record.asset_id,
            provider_name=record.provider,
        )
        db.add(detail)
    detail.underlying_instrument_id = underlying.id if underlying else None
    detail.provider_asset_id = record.asset_id
    detail.provider_name = record.provider
    detail.token_symbol = record.symbol
    detail.isin = record.isin
    detail.underlying_symbol = record.underlying_symbol
    detail.underlying_figi = underlying_figi
    detail.underlying_composite_figi = underlying_composite_figi
    detail.underlying_isin = underlying_isin
    detail.underlying_cusip = underlying_cusip
    detail.underlying_cik = underlying_cik
    detail.underlying_issuer_id = underlying_issuer_id
    detail.backing_type = record.backing_type
    detail.multiplier = record.multiplier
    detail.circulating_supply = record.circulating_supply
    detail.total_supply = record.total_supply
    detail.status = record.status
    detail.deployments = record.collateral.get("deployments") if record.collateral else None
    detail.collateral = record.collateral or None
    detail.corporate_actions = record.corporate_actions or None
    detail.provenance = {
        "provider": record.provider,
        "provider_asset_id": record.asset_id,
        "observed_at": (record.observed_at or datetime.now(UTC)).isoformat(),
        "underlying_link_status": underlying_link_status,
        "underlying_issuer_link_status": (
            "linked_by_cik"
            if underlying_issuer_id is not None
            else "unresolved_or_not_materialized"
            if underlying_cik
            else "not_provided"
        ),
    }
    detail.description = record.raw_payload.get("description") if record.raw_payload else None

    # Keep the provider response immutable even though the detail row above is
    # intentionally a latest-state projection.  Every invocation is retained,
    # including an identical response, because the observation itself is
    # evidence of a quota-consuming fetch and must remain replayable.
    observed_at = record.observed_at or datetime.now(UTC)
    db.add(
        TokenizedAssetObservation(
            instrument_id=instrument.id,
            provider_asset_id=record.asset_id,
            provider_name=record.provider,
            token_symbol=record.symbol,
            observed_at=observed_at,
            fetched_at=datetime.now(UTC),
            payload=(
                source_payload
                if source_payload is not None
                else (record.raw_payload if record.raw_payload is not None else {})
            ),
        )
    )

    await register_provider_symbol(
        db,
        instrument,
        record.provider,
        record.symbol or record.asset_id,
        provider_instrument_type="TOKENIZED_SECURITY",
        currency=record.currency,
        is_primary=True,
        extra_data={
            "provider_asset_id": record.asset_id,
            "contract_address": record.contract_address,
            "network": record.network,
            "chain_id": record.chain_id,
            "underlying_symbol": record.underlying_symbol,
            "tokenized_security": True,
        },
    )

    if record.price is not None:
        from app.providers import ensure_data_source

        source = await ensure_data_source(db, record.provider)
        observed_at = record.observed_at or datetime.now(UTC)
        snapshot = LatestPriceSnapshot(
            instrument_id=instrument.id,
            data_source_id=source.id,
            provider_symbol=record.symbol or record.asset_id,
            observed_at=observed_at,
            fetched_at=datetime.now(UTC),
            price=record.price,
            payload=(
                source_payload
                if source_payload is not None
                else (record.raw_payload if record.raw_payload is not None else {})
            ),
        )
        db.add(snapshot)
    await db.flush()
    return instrument


def _discover_tokenized_catalog_page(
    provider: Any,
    *,
    page: int,
    cursor: str | None,
    page_size: int,
    use_cursor: bool,
    continuation: dict[str, str | None],
) -> list[TokenizedAssetRecord]:
    """Read one catalogue page while exposing opaque continuation metadata."""

    if use_cursor:
        rows, next_cursor = provider.discover_tokenized_page(
            cursor=cursor,
            page_size=page_size,
        )
        continuation["next_cursor"] = next_cursor
        return rows
    return provider.discover_tokenized_assets(page=page, page_size=page_size)


async def refresh_tokenized_assets(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
    max_pages: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    """Refresh bounded tokenized metadata through the provider runtime."""

    bounded_max_pages = max(1, min(int(max_pages), 1000))
    bounded_page_size = max(1, min(int(page_size), 1000))
    chain = await resolve_provider_chain(db, ProviderCapability.TOKENIZED_ASSETS)
    if provider_name:
        chain = [item for item in chain if item.provider_name == provider_name]
    chain = [
        item
        for item in chain
        if item.provider_name.strip().lower() not in _NON_PERSISTING_TOKENIZED_CANARIES
    ]
    if not chain:
        return {"status": "no_qualified_provider", "providers": [], "assets": 0}

    refreshed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    successful_providers = 0
    truncated_any = False
    for resolved in chain:
        provider_name = str(resolved.provider_name).strip()
        state = await _tokenized_catalog_state(
            db,
            provider_name=provider_name,
            page_size=bounded_page_size,
        )
        cursor_history = list(state.cursor_history or [])
        cursor_provider = callable(getattr(resolved.provider, "discover_tokenized_page", None))
        count = 0
        pages_fetched = 0
        truncated = False
        provider_failed = False
        for _budget_page in range(bounded_max_pages):
            pages_fetched += 1
            requested_page = int(state.page_number or 0)
            requested_cursor = state.cursor
            continuation: dict[str, str | None] = {"next_cursor": None}
            try:
                execution = await execute_provider_call(
                    db,
                    ProviderCapability.TOKENIZED_ASSETS,
                    f"discover_tokenized_assets:{requested_page}",
                    provider_name=provider_name,
                    invoke=lambda provider, _symbol: _discover_tokenized_catalog_page(
                        provider,
                        page=requested_page,
                        cursor=requested_cursor,
                        page_size=bounded_page_size,
                        use_cursor=cursor_provider,
                        continuation=continuation,
                    ),
                    response_items=len,
                    treat_empty_as_failure=False,
                )
                rows = execution.result or []
                for row in rows:
                    await upsert_tokenized_asset(db, row)
                    count += 1
            except Exception as exc:  # noqa: BLE001 - retain per-provider evidence.
                provider_failed = True
                state.status = "failed"
                state.last_failure_at = datetime.now(UTC)
                state.last_error = bounded_redact_provider_message(exc, max_length=500)
                truncated = True
                failures.append(
                    {
                        "provider": provider_name,
                        "page": requested_page,
                        "cursor": bool(requested_cursor),
                        "error": state.last_error,
                    }
                )
                # A failed page is not evidence of completion. Continue with
                # the next provider so one outage cannot suppress the rest of
                # the qualified tokenized universe.
                break

            state.pages_fetched = int(state.pages_fetched or 0) + 1
            state.last_page_count = len(rows)
            state.last_success_at = datetime.now(UTC)
            state.last_failure_at = None
            state.last_error = None
            next_cursor = continuation.get("next_cursor") if cursor_provider else None
            if cursor_provider:
                if next_cursor is None:
                    state.page_number = 0
                    state.cursor = None
                    state.status = "complete"
                    state.cursor_history = cursor_history
                    truncated = False
                    break
                cursor_token = str(next_cursor).strip()
                cursor_digest = hashlib.sha256(cursor_token.encode("utf-8")).hexdigest()
                if not cursor_token or cursor_token == requested_cursor or cursor_digest in cursor_history:
                    provider_failed = True
                    state.status = "failed"
                    state.last_failure_at = datetime.now(UTC)
                    state.last_error = "provider returned a repeated tokenized catalogue cursor"
                    failures.append(
                        {
                            "provider": provider_name,
                            "page": requested_page,
                            "cursor": bool(requested_cursor),
                            "error": state.last_error,
                        }
                    )
                    truncated = True
                    break
                cursor_history.append(cursor_digest)
                state.cursor_history = cursor_history
                state.page_number = requested_page + 1
                state.cursor = cursor_token
                state.status = "partial"
                truncated = True
            elif len(rows) < bounded_page_size:
                state.page_number = 0
                state.cursor = None
                state.status = "complete"
                state.cursor_history = []
                truncated = False
                break
            else:
                state.page_number = requested_page + 1
                state.cursor = None
                state.status = "partial"
                truncated = True
        truncated_any = truncated_any or truncated
        if not provider_failed:
            successful_providers += 1
        refreshed.append(
            {
                "provider": provider_name,
                "assets": count,
                "pages_fetched": pages_fetched,
                "truncated": truncated,
                "complete": not truncated,
            }
        )
    await db.commit()
    status = (
        "failed"
        if failures and successful_providers == 0
        else "partial"
        if truncated_any or failures
        else "refreshed"
    )
    return {
        "status": status,
        "providers": refreshed,
        "assets": sum(item["assets"] for item in refreshed),
        "truncated": truncated_any,
        "complete": not truncated_any,
        "failed": len(failures),
        "failures": failures,
    }


async def refresh_tokenized_events(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
    max_providers: int = 2,
    max_pages: int = 1,
    page_size: int = 100,
    include_upcoming: bool = True,
) -> dict[str, Any]:
    """Persist provider corporate actions into the canonical market-event table.

    The provider catalog is intentionally broader than the corporate-action
    surface: xStocks, Robinhood, and Dinari expose public action feeds (Dinari's
    unscoped feed is split-only), while the other exchange adapters only expose
    metadata/quotes. Unsupported adapters are reported and skipped rather than
    invoked through a guessed method.
    Every request goes through the provider runtime so durable quota
    reservations, request telemetry, and circuit state remain authoritative.
    """

    bounded_providers = max(1, min(int(max_providers), 10))
    bounded_max_pages = max(1, min(int(max_pages), 1000))
    bounded_page_size = max(1, min(int(page_size), 100))
    # Corporate actions have their own capability contract. This prevents a
    # provider that only advertises catalogue/quote support from being selected
    # merely because it is present in the broader tokenized-asset chain.
    catalog_chain = await resolve_provider_chain(db, ProviderCapability.TOKENIZED_ASSETS)
    chain = await resolve_provider_chain(db, ProviderCapability.TOKENIZED_CORPORATE_ACTIONS)
    if provider_name:
        chain = [item for item in chain if item.provider_name == provider_name]
    chain = [
        item
        for item in chain
        if item.provider_name.strip().lower() not in _NON_PERSISTING_TOKENIZED_CANARIES
    ]

    supported = [
        item
        for item in chain
        if callable(getattr(item.provider, "fetch_tokenized_corporate_actions", None))
        or callable(getattr(item.provider, "fetch_tokenized_corporate_actions_page", None))
    ]
    # The provider cap is a per-job budget. Rotate from durable per-provider
    # action-feed state before applying it so later eligible providers are
    # eventually queried rather than being excluded forever by chain order.
    supported = (await _fair_tokenized_event_provider_order(db, supported))[:bounded_providers]
    unsupported = [
        item.provider_name
        for item in catalog_chain
        if not (
            callable(getattr(item.provider, "fetch_tokenized_corporate_actions", None))
            or callable(getattr(item.provider, "fetch_tokenized_corporate_actions_page", None))
        )
    ]
    if not supported:
        return {
            "status": "no_corporate_action_provider",
            "providers": [],
            "unsupported": unsupported,
            "events": 0,
            "linked": 0,
            "unlinked": 0,
            "failed": 0,
        }

    provider_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    total_events = 0
    total_linked = 0
    total_unlinked = 0
    truncated_any = False

    for resolved in supported:
        phases = ["history", "upcoming"] if include_upcoming else ["history"]
        if resolved.provider_name != "xstocks":
            # Robinhood's public endpoint combines historical and upcoming
            # actions; Dinari's unscoped feed is a bounded global split read
            # with no upcoming semantic. Both use provider-native defaults.
            phases = ["combined"]
        by_asset, by_symbol = await _tokenized_detail_maps(db, resolved.provider_name)
        provider_count = 0
        provider_linked = 0
        provider_unlinked = 0
        provider_truncated = False
        provider_pages = 0
        cursor_page_provider = callable(
            getattr(resolved.provider, "fetch_tokenized_corporate_actions_page", None)
        )
        for phase in phases:
            state = await _tokenized_event_state(
                db,
                provider_name=resolved.provider_name,
                phase=phase,
                page_size=bounded_page_size,
            )
            cursor_history = list(state.cursor_history or [])
            phase_truncated = False
            try:
                for _ in range(bounded_max_pages):
                    provider_pages += 1
                    requested_page = int(state.page_number or 1)
                    requested_cursor = state.cursor

                    def _invoke(provider, _symbol):
                        if callable(
                            getattr(provider, "fetch_tokenized_corporate_actions_page", None)
                        ):
                            return provider.fetch_tokenized_corporate_actions_page(
                                page=requested_page,
                                page_size=bounded_page_size,
                                cursor=requested_cursor,
                            )
                        if resolved.provider_name == "xstocks":
                            return (
                                provider.fetch_tokenized_corporate_actions(
                                    upcoming=phase == "upcoming",
                                    page=requested_page,
                                    page_size=bounded_page_size,
                                ),
                                None,
                            )
                        # Robinhood's public feed is not paginated and returns
                        # its complete response in one request.
                        return (provider.fetch_tokenized_corporate_actions(), None)

                    execution = await execute_provider_call(
                        db,
                        ProviderCapability.TOKENIZED_CORPORATE_ACTIONS,
                        "fetch_tokenized_corporate_actions",
                        provider_name=resolved.provider_name,
                        response_items=lambda result: len(result[0])
                        if isinstance(result, tuple)
                        else len(result),
                        treat_empty_as_failure=False,
                        invoke=_invoke,
                    )
                    result = execution.result
                    if isinstance(result, tuple) and len(result) == 2:
                        rows, next_cursor = result
                    elif isinstance(result, list):
                        # Compatibility with test doubles and older adapters
                        # that expose a complete non-paginated response.
                        rows, next_cursor = result, None
                    else:
                        raise TypeError(
                            "tokenized corporate-action provider returned an invalid page"
                        )
                    if not isinstance(rows, list) or not isinstance(next_cursor, str | type(None)):
                        raise TypeError("tokenized corporate-action provider returned an invalid page")
                    if any(not isinstance(row, dict) for row in rows):
                        # Never silently drop a provider row. A malformed row
                        # makes the entire page untrusted; leave the durable
                        # cursor/state at the failed page so a later retry can
                        # recover it after the provider fixes its response.
                        raise TypeError(
                            "tokenized corporate-action provider returned a non-object row"
                        )
                    for row in rows:
                        event_payload = _tokenized_event_payload(
                            resolved.provider_name, row, phase=phase
                        )
                        instrument_id = _resolve_tokenized_instrument(row, by_asset, by_symbol)
                        if instrument_id is None:
                            provider_unlinked += 1
                        else:
                            provider_linked += 1
                        await persist_market_event(
                            db,
                            event_key=_tokenized_action_key(resolved.provider_name, row),
                            event_type="tokenized_corporate_action",
                            source=resolved.provider_name,
                            instrument_id=instrument_id,
                            event_time=_parse_datetime(_first_scalar(row, _EVENT_TIME_FIELDS)),
                            effective_date=_parse_date(_first_scalar(row, _EFFECTIVE_DATE_FIELDS)),
                            announced_at=_parse_datetime(
                                _first_scalar(row, _ANNOUNCED_AT_FIELDS)
                            ),
                            payload=event_payload,
                            is_provisional=True,
                        )
                        provider_count += 1

                    state.pages_fetched = int(state.pages_fetched or 0) + 1
                    state.last_page_count = len(rows)
                    state.last_success_at = datetime.now(UTC)
                    state.last_failure_at = None
                    state.last_error = None
                    if next_cursor is not None:
                        cursor_token = next_cursor.strip()
                        cursor_digest = hashlib.sha256(cursor_token.encode("utf-8")).hexdigest()
                        if (
                            not cursor_token
                            or cursor_token == requested_cursor
                            or cursor_digest in cursor_history
                        ):
                            raise ProviderResponseError(
                                resolved.provider_name,
                                "provider returned a repeated tokenized event cursor",
                            )
                        cursor_history.append(cursor_digest)
                        state.cursor_history = cursor_history
                        state.page_number = requested_page + 1
                        state.cursor = cursor_token
                        state.status = "partial"
                        phase_truncated = True
                        continue
                    if not cursor_page_provider and len(rows) >= bounded_page_size:
                        state.page_number = requested_page + 1
                        state.cursor = None
                        state.status = "partial"
                        phase_truncated = True
                        continue
                    state.page_number = 1
                    state.cursor = None
                    state.status = "complete"
                    state.cursor_history = []
                    break
            except Exception as exc:  # noqa: BLE001 - retain per-provider evidence.
                state.status = "failed"
                state.last_failure_at = datetime.now(UTC)
                state.last_error = bounded_redact_provider_message(exc, max_length=500)
                phase_truncated = True
                failures.append(
                    {
                        "provider": resolved.provider_name,
                        "phase": phase,
                        "page": int(state.page_number or 1),
                        "cursor": bool(state.cursor),
                        "error": state.last_error,
                    }
                )
            provider_truncated = provider_truncated or phase_truncated
        provider_results.append(
            {
                "provider": resolved.provider_name,
                "events": provider_count,
                "linked": provider_linked,
                "unlinked": provider_unlinked,
                "pages_fetched": provider_pages,
                "truncated": provider_truncated,
                "complete": not provider_truncated,
            }
        )
        truncated_any = truncated_any or provider_truncated
        total_events += provider_count
        total_linked += provider_linked
        total_unlinked += provider_unlinked

    await db.commit()
    status = (
        "failed"
        if failures and total_events == 0
        else "partial"
        if truncated_any or failures
        else "refreshed"
        if total_events
        else "no_events"
    )
    return {
        "status": status,
        "providers": provider_results,
        "unsupported": unsupported,
        "events": total_events,
        "linked": total_linked,
        "unlinked": total_unlinked,
        "truncated": truncated_any,
        "complete": not truncated_any,
        "failed": len(failures),
        "failures": failures,
    }


async def refresh_tokenized_prices(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
    max_assets: int = 100,
) -> dict[str, Any]:
    """Refresh bounded tokenized quotes through the provider runtime.

    Discovery and quote reads are intentionally separate operations: a public
    catalogue response does not imply a current price, and quote polling must
    consume the provider's own durable quota contract.  The provider asset ID
    is used as the request identity rather than the economic underlying ticker.
    """

    limit = max(1, min(int(max_assets), 1000))
    rows, refresh_state = await _tokenized_asset_refresh_batch(
        db,
        capability=ProviderCapability.TOKENIZED_ASSETS.value,
        operation="get_tokenized_price",
        provider_name=provider_name,
        max_assets=limit,
    )
    refreshed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for detail, instrument in rows:
        if detail.provider_name.strip().lower() in _NON_PERSISTING_TOKENIZED_CANARIES:
            failures.append(
                {
                    "instrument_id": instrument.id,
                    "provider": detail.provider_name,
                    "provider_asset_id": detail.provider_asset_id,
                    "error": "sandbox_canary_data_is_not_persistable",
                }
            )
            continue
        identifier = detail.provider_asset_id or detail.token_symbol
        if not identifier:
            failures.append(
                {
                    "instrument_id": instrument.id,
                    "provider": detail.provider_name,
                    "error": "missing_provider_asset_id",
                }
            )
            continue
        try:
            execution = await execute_provider_call(
                db,
                ProviderCapability.TOKENIZED_ASSETS,
                "get_tokenized_price",
                instrument_id=instrument.id,
                provider_symbol=identifier,
                usage_identity=identifier,
                provider_name=detail.provider_name,
                invoke=lambda provider, _symbol, identifier=identifier: provider.get_tokenized_price(
                    identifier
                ),
                response_items=lambda value: 1 if value is not None else 0,
                treat_empty_as_failure=True,
            )
            record = execution.result
            if not isinstance(record, TokenizedAssetRecord):
                raise TypeError("tokenized provider returned an invalid record")
            await upsert_tokenized_asset(db, record, source_payload=record.raw_payload)
            refreshed.append(
                {
                    "instrument_id": instrument.id,
                    "provider": execution.provider_name,
                    "provider_asset_id": identifier,
                    "observed_at": record.observed_at.isoformat()
                    if record.observed_at
                    else None,
                }
            )
        except Exception as exc:  # noqa: BLE001 - retain per-asset coverage evidence.
            failures.append(
                {
                    "instrument_id": instrument.id,
                    "provider": detail.provider_name,
                    "provider_asset_id": identifier,
                    "error": bounded_redact_provider_message(exc, max_length=500),
                }
            )

    if refresh_state is not None and rows:
        refresh_state.cursor = str(rows[-1][0].id)
        refresh_state.page_number = int(refresh_state.page_number or 0) + 1
        refresh_state.pages_fetched = int(refresh_state.pages_fetched or 0) + 1
        refresh_state.page_size = limit
        refresh_state.last_page_count = len(rows)
        refresh_state.last_success_at = datetime.now(UTC)
        refresh_state.last_failure_at = None
        refresh_state.last_error = None
        refresh_state.status = "partial"
    await db.commit()
    return {
        "status": "refreshed" if refreshed else ("failed" if failures else "no_assets"),
        "requested": len(rows),
        "refreshed": len(refreshed),
        "failed": len(failures),
        "quotes": refreshed,
        "failures": failures,
    }


_TOKENIZED_HISTORY_TIMEFRAMES = {
    "DAY": Timeframe.D1,
    "WEEK": Timeframe.W1,
    "MONTH": Timeframe.MN,
    "YEAR": Timeframe.Y1,
}


def _tokenized_history_bar(
    row: dict[str, Any],
    *,
    instrument_id: int,
    data_source_id: int,
    timeframe: Timeframe,
    provider_name: str,
    provider_asset_id: str,
) -> OHLCVBar:
    """Normalize one aggregate without inventing volume or adjustment."""

    timestamp = row.get("timestamp")
    if not isinstance(timestamp, datetime):
        raise ValueError("tokenized historical row has no normalized timestamp")
    values: dict[str, Decimal] = {}
    for field in ("open", "high", "low", "close"):
        try:
            value = Decimal(str(row.get(field)))
        except (TypeError, ValueError):
            raise ValueError(f"tokenized historical row has invalid {field}") from None
        if not value.is_finite():
            raise ValueError(f"tokenized historical row has invalid {field}")
        values[field] = value
    return OHLCVBar(
        instrument_id=instrument_id,
        data_source_id=data_source_id,
        timeframe=timeframe,
        ts=timestamp,
        session="24_7",
        open=values["open"],
        high=values["high"],
        low=values["low"],
        close=values["close"],
        volume=None,
        vwap=None,
        is_adjusted=False,
        adjustment_basis=AdjustmentBasis.RAW.value,
        adjustment_version="provider-native-tokenized",
        provenance={
            "provider": provider_name,
            "provider_asset_id": provider_asset_id,
            "feed": "tokenized_aggregate_history",
            "session": "24_7",
            "raw_payload": row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else row,
        },
    )


async def refresh_tokenized_historical_prices(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
    max_assets: int = 100,
    timespan: str = "DAY",
) -> dict[str, Any]:
    """Persist bounded tokenized aggregate candles through durable routing."""

    normalized_timespan = str(timespan or "").strip().upper()
    timeframe = _TOKENIZED_HISTORY_TIMEFRAMES.get(normalized_timespan)
    if timeframe is None:
        return {
            "status": "invalid_timespan",
            "timespan": normalized_timespan,
            "requested": 0,
            "refreshed": 0,
            "failed": 0,
            "unsupported": [],
        }
    limit = max(1, min(int(max_assets), 1000))
    rows, refresh_state = await _tokenized_asset_refresh_batch(
        db,
        capability=ProviderCapability.TOKENIZED_HISTORICAL_PRICES.value,
        operation=f"fetch_tokenized_historical_prices:{normalized_timespan}",
        provider_name=provider_name,
        max_assets=limit,
    )
    chain = await resolve_provider_chain(db, ProviderCapability.TOKENIZED_HISTORICAL_PRICES)
    resolved_by_provider = {
        item.provider_name: item
        for item in chain
        if item.provider_name.strip().lower() not in _NON_PERSISTING_TOKENIZED_CANARIES
        if callable(getattr(item.provider, "fetch_tokenized_historical_prices", None))
    }
    refreshed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    unsupported: list[str] = []
    for detail, instrument in rows:
        if detail.provider_name.strip().lower() in _NON_PERSISTING_TOKENIZED_CANARIES:
            unsupported.append(detail.provider_name)
            continue
        resolved = resolved_by_provider.get(detail.provider_name)
        identifier = detail.provider_asset_id or detail.token_symbol
        if resolved is None or not identifier:
            unsupported.append(detail.provider_name)
            continue
        try:
            execution = await execute_provider_call(
                db,
                ProviderCapability.TOKENIZED_HISTORICAL_PRICES,
                "fetch_tokenized_historical_prices",
                instrument_id=instrument.id,
                provider_symbol=identifier,
                usage_identity=identifier,
                provider_name=detail.provider_name,
                invoke=lambda provider, _symbol, identifier=identifier: provider.fetch_tokenized_historical_prices(
                    identifier, timespan=normalized_timespan
                ),
                response_items=len,
                treat_empty_as_failure=False,
            )
            payload_rows = execution.result or []
            if not isinstance(payload_rows, list) or any(
                not isinstance(row, dict) for row in payload_rows
            ):
                raise TypeError("tokenized historical provider returned a non-list")
            bars = [
                _tokenized_history_bar(
                    row,
                    instrument_id=instrument.id,
                    data_source_id=execution.data_source.id,
                    timeframe=timeframe,
                    provider_name=execution.provider_name,
                    provider_asset_id=identifier,
                )
                for row in payload_rows
            ]
            bars = await _attach_provider_series(
                db, instrument, timeframe, False, execution, bars=bars
            )
            await persist_price_history_bars(
                db,
                instrument,
                data_source_id=execution.data_source.id,
                provider_symbol=identifier,
                timeframe=timeframe,
                adjusted=False,
                bars=bars,
            )
            refreshed.append(
                {
                    "instrument_id": instrument.id,
                    "provider": execution.provider_name,
                    "provider_asset_id": identifier,
                    "timespan": normalized_timespan,
                    "bars": len(bars),
                }
            )
        except Exception as exc:  # noqa: BLE001 - retain bounded provider evidence.
            failures.append(
                {
                    "instrument_id": instrument.id,
                    "provider": detail.provider_name,
                    "provider_asset_id": identifier,
                    "timespan": normalized_timespan,
                    "error": bounded_redact_provider_message(exc, max_length=500),
                }
            )
    if refresh_state is not None and rows:
        refresh_state.cursor = str(rows[-1][0].id)
        refresh_state.page_number = int(refresh_state.page_number or 0) + 1
        refresh_state.pages_fetched = int(refresh_state.pages_fetched or 0) + 1
        refresh_state.page_size = limit
        refresh_state.last_page_count = len(rows)
        refresh_state.last_success_at = datetime.now(UTC)
        refresh_state.last_failure_at = None
        refresh_state.last_error = None
        refresh_state.status = "partial"
    await db.commit()
    return {
        "status": "refreshed" if refreshed else ("failed" if failures else "no_assets"),
        "timespan": normalized_timespan,
        "requested": len(rows),
        "refreshed": len(refreshed),
        "failed": len(failures),
        "unsupported": sorted(set(unsupported)),
        "history": refreshed,
        "failures": failures,
    }
