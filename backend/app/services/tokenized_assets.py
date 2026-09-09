"""Persistence and refresh helpers for tokenized-security observations."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.provider_observation import LatestPriceSnapshot
from app.models.provider_runtime import ProviderCapability
from app.models.tokenized_asset import TokenizedAssetDetail
from app.providers.base import TokenizedAssetRecord
from app.services.instrument_mastering import ensure_instrument_type, register_provider_symbol
from app.services.provider_runtime import execute_provider_call, resolve_provider_chain


def tokenized_domain_key(provider: str, asset_id: str) -> str:
    digest = hashlib.sha256(asset_id.encode("utf-8")).hexdigest()[:48]
    return f"tokenized:{provider}:{digest}"


async def _underlying_instrument(
    db: AsyncSession, symbol: str | None
) -> Instrument | None:
    if not symbol:
        return None
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
    return rows[0] if len(rows) == 1 else None


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

    underlying = await _underlying_instrument(db, record.underlying_symbol)
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
    detail.underlying_isin = record.underlying_isin
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
        "underlying_link_status": "linked" if underlying else "unresolved_or_ambiguous",
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
                    "error": str(exc)[:500],
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
