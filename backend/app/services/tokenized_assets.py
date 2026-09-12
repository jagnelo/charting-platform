"""Persistence and refresh helpers for tokenized-security observations."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier, InstrumentIdentifierType
from app.models.provider_observation import LatestPriceSnapshot
from app.models.provider_runtime import ProviderCapability
from app.models.tokenized_asset import TokenizedAssetDetail
from app.providers.base import TokenizedAssetRecord
from app.providers.errors import bounded_redact_provider_message
from app.services.instrument_mastering import ensure_instrument_type, register_provider_symbol
from app.services.market_data_identity import normalize_identifier_value
from app.services.market_data_persistence import persist_market_event
from app.services.provider_runtime import execute_provider_call, resolve_provider_chain


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
    underlying, underlying_link_status = await _underlying_instrument(
        db,
        symbol=record.underlying_symbol,
        figi=underlying_figi,
        composite_figi=underlying_composite_figi,
        isin=underlying_isin,
        cusip=underlying_cusip,
    )
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
    }
    detail.description = record.raw_payload.get("description") if record.raw_payload else None

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
            payload=source_payload or record.raw_payload,
        )
        db.add(snapshot)
    await db.flush()
    return instrument


async def refresh_tokenized_assets(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
    max_pages: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    """Refresh bounded tokenized metadata through the provider runtime."""

    chain = await resolve_provider_chain(db, ProviderCapability.TOKENIZED_ASSETS)
    if provider_name:
        chain = [item for item in chain if item.provider_name == provider_name]
    if not chain:
        return {"status": "no_qualified_provider", "providers": [], "assets": 0}

    refreshed: list[dict[str, Any]] = []
    for resolved in chain:
        count = 0
        for page in range(max(1, max_pages)):
            execution = await execute_provider_call(
                db,
                ProviderCapability.TOKENIZED_ASSETS,
                f"discover_tokenized_assets:{page}",
                provider_name=resolved.provider_name,
                invoke=lambda provider, _symbol, page=page: provider.discover_tokenized_assets(
                    page=page, page_size=page_size
                ),
                response_items=len,
                treat_empty_as_failure=False,
            )
            rows = execution.result or []
            for row in rows:
                await upsert_tokenized_asset(db, row)
                count += 1
            if len(rows) < page_size:
                break
        refreshed.append({"provider": resolved.provider_name, "assets": count})
    await db.commit()
    return {"status": "refreshed", "providers": refreshed, "assets": sum(item["assets"] for item in refreshed)}


async def refresh_tokenized_events(
    db: AsyncSession,
    *,
    provider_name: str | None = None,
    max_providers: int = 2,
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
    bounded_page_size = max(1, min(int(page_size), 100))
    # Corporate actions have their own capability contract. This prevents a
    # provider that only advertises catalogue/quote support from being selected
    # merely because it is present in the broader tokenized-asset chain.
    catalog_chain = await resolve_provider_chain(db, ProviderCapability.TOKENIZED_ASSETS)
    chain = await resolve_provider_chain(db, ProviderCapability.TOKENIZED_CORPORATE_ACTIONS)
    if provider_name:
        chain = [item for item in chain if item.provider_name == provider_name]

    supported = [
        item
        for item in chain
        if callable(getattr(item.provider, "fetch_tokenized_corporate_actions", None))
    ][:bounded_providers]
    unsupported = [
        item.provider_name
        for item in catalog_chain
        if not callable(getattr(item.provider, "fetch_tokenized_corporate_actions", None))
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
        for phase in phases:
            try:
                execution = await execute_provider_call(
                    db,
                    ProviderCapability.TOKENIZED_CORPORATE_ACTIONS,
                    "fetch_tokenized_corporate_actions",
                    provider_name=resolved.provider_name,
                    response_items=len,
                    treat_empty_as_failure=False,
                    invoke=lambda provider, _symbol, phase=phase: (
                        provider.fetch_tokenized_corporate_actions(
                            upcoming=phase == "upcoming",
                            page=1,
                            page_size=bounded_page_size,
                        )
                        if resolved.provider_name == "xstocks"
                        else provider.fetch_tokenized_corporate_actions()
                    ),
                )
                rows = execution.result or []
                if not isinstance(rows, list):
                    raise TypeError("tokenized corporate-action provider returned a non-list")
                for row in rows:
                    if not isinstance(row, dict):
                        continue
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
            except Exception as exc:  # noqa: BLE001 - retain per-provider evidence.
                failures.append(
                    {
                        "provider": resolved.provider_name,
                        "phase": phase,
                        "error": bounded_redact_provider_message(exc, max_length=500),
                    }
                )
        provider_results.append(
            {
                "provider": resolved.provider_name,
                "events": provider_count,
                "linked": provider_linked,
                "unlinked": provider_unlinked,
            }
        )
        total_events += provider_count
        total_linked += provider_linked
        total_unlinked += provider_unlinked

    await db.commit()
    status = "refreshed" if total_events else ("failed" if failures else "no_events")
    return {
        "status": status,
        "providers": provider_results,
        "unsupported": unsupported,
        "events": total_events,
        "linked": total_linked,
        "unlinked": total_unlinked,
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
    query = (
        select(TokenizedAssetDetail, Instrument)
        .join(Instrument, Instrument.id == TokenizedAssetDetail.instrument_id)
        .where(Instrument.is_active.is_(True))
        .order_by(TokenizedAssetDetail.updated_at.asc(), TokenizedAssetDetail.id.asc())
        .limit(limit)
    )
    if provider_name:
        query = query.where(TokenizedAssetDetail.provider_name == provider_name)

    rows = (await db.execute(query)).all()
    refreshed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for detail, instrument in rows:
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

    await db.commit()
    return {
        "status": "refreshed" if refreshed else ("failed" if failures else "no_assets"),
        "requested": len(rows),
        "refreshed": len(refreshed),
        "failed": len(failures),
        "quotes": refreshed,
        "failures": failures,
    }
