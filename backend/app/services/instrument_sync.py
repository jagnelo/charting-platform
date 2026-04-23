"""
Instrument sync service.

Three responsibilities:
  1. Seed:      Page through the configured discovery provider's universe and
                create/update Instrument rows.
  2. Bootstrap: Fetch stable identifiers for instruments that still lack one.
  3. Sync:      Refresh metadata for active instruments through the configured
                metadata provider.
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.asset_class import AssetClass, InstrumentType
from app.models.instrument import EquityDetail, ForexDetail, FutureDetail, Instrument
from app.models.instrument_stats import InstrumentStats
from app.models.instrument_sync_run import InstrumentSyncRun
from app.models.listing import InstrumentListing
from app.models.provider_runtime import ProviderCapability
from app.providers import provider_symbol_for_instrument
from app.services.instrument_mastering import (
    ensure_external_identifier,
    ensure_internal_identifier,
    ingest_provider_profile,
    register_provider_symbol,
)
from app.services.provider_runtime import execute_provider_call, resolve_provider_chain

logger = logging.getLogger(__name__)

# Caps concurrent outbound calls to external APIs platform-wide.
_IDENTIFIER_SEMAPHORE = asyncio.Semaphore(settings.PROVIDER_MAX_CONCURRENCY)
_METADATA_SEMAPHORE = asyncio.Semaphore(settings.PROVIDER_MAX_CONCURRENCY)

# External quote-type → internal taxonomy normalization.
_QUOTE_TYPE_TAXONOMY: dict[str, tuple[str, str]] = {
    "EQUITY": ("Equity", "Stock"),
    "ETF": ("Equity", "ETF"),
    "MUTUALFUND": ("Equity", "Mutual Fund"),
    "INDEX": ("Index", "Index"),
    "CURRENCY": ("Currency", "Forex Pair"),
    "CRYPTOCURRENCY": ("Cryptocurrency", "Crypto Spot"),
    "FUTURE": ("Commodity", "Future"),
}


# ── Helpers ────────────────────────────────────────────────────────────────────


def _cap_tier(cap: float | None) -> str | None:
    if not cap:
        return None
    if cap >= 200_000_000_000:
        return "mega"
    if cap >= 10_000_000_000:
        return "large"
    if cap >= 2_000_000_000:
        return "mid"
    if cap >= 300_000_000:
        return "small"
    if cap >= 50_000_000:
        return "micro"
    return "nano"


async def _ensure_instrument_type(db: AsyncSession, asset_class_name: str, type_name: str) -> int:
    """Get-or-create AssetClass + InstrumentType; return InstrumentType.id."""
    ac = (
        await db.execute(select(AssetClass).where(AssetClass.name == asset_class_name))
    ).scalar_one_or_none()
    if not ac:
        ac = AssetClass(name=asset_class_name, description=asset_class_name)
        db.add(ac)
        await db.flush()

    it = (
        await db.execute(
            select(InstrumentType).where(
                InstrumentType.asset_class_id == ac.id,
                InstrumentType.name == type_name,
            )
        )
    ).scalar_one_or_none()
    if not it:
        it = InstrumentType(asset_class_id=ac.id, name=type_name, description=type_name)
        db.add(it)
        await db.flush()

    return it.id


# ── Seed ──────────────────────────────────────────────────────────────────────


def _screener_page_sync(provider, quote_type: str, offset: int) -> dict:
    return provider.discover_universe_page(quote_type, offset)


def _parse_forex_pair(symbol: str) -> tuple[str, str] | None:
    """
    Attempt to extract base/quote currencies from a provider symbol.

    Common formats include "EURUSD=X" and "EUR/USD".
    Returns (base, quote) or None if the symbol cannot be parsed.
    """
    s = symbol.upper().replace("=X", "").replace("/", "")
    if len(s) == 6:
        return s[:3], s[3:]
    return None


def _first_present(payload: dict, *keys: str):
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


async def _upsert_listing(
    db: AsyncSession,
    instrument: Instrument,
    symbol: str,
    currency: str | None,
) -> None:
    listing = (
        await db.execute(
            select(InstrumentListing).where(
                InstrumentListing.instrument_id == instrument.id,
                InstrumentListing.ticker == symbol,
            )
        )
    ).scalar_one_or_none()

    if listing is None:
        db.add(
            InstrumentListing(
                instrument_id=instrument.id,
                ticker=symbol,
                currency=currency,
                is_primary=True,
                is_active=True,
            )
        )
        return

    listing.currency = currency or listing.currency
    listing.is_active = True


async def _upsert_stats(
    db: AsyncSession,
    instrument: Instrument,
    q: dict,
    *,
    source_provider: str,
) -> None:
    stats_values = {
        "week52_high": q.get("fiftyTwoWeekHigh"),
        "week52_low": q.get("fiftyTwoWeekLow"),
        "avg_volume_30d": _first_present(
            q,
            "averageDailyVolume3Month",
            "averageDailyVolume10Day",
            "averageVolume",
            "regularMarketVolume",
        ),
        "pe_ratio": _first_present(q, "trailingPE", "forwardPE"),
        "market_cap": q.get("marketCap"),
        "beta": q.get("beta"),
        "dividend_yield": q.get("dividendYield"),
    }
    if not any(value is not None for value in stats_values.values()):
        return

    stats = (
        await db.execute(
            select(InstrumentStats).where(InstrumentStats.instrument_id == instrument.id)
        )
    ).scalar_one_or_none()
    if stats is None:
        stats = InstrumentStats(instrument_id=instrument.id)
        db.add(stats)

    provenance = dict(stats.field_provenance or {})
    for attr, value in stats_values.items():
        if value is not None:
            setattr(stats, attr, value)
            provenance[attr] = {
                "source": source_provider,
                "fetched_at": datetime.now(UTC).isoformat(),
                "provider_symbol": instrument.symbol,
            }
    stats.field_provenance = provenance or None
    stats.computed_at = datetime.now(UTC)


async def _provider_chain_label(db: AsyncSession, capability: ProviderCapability) -> str:
    chain = await resolve_provider_chain(db, capability)
    return ",".join(item.provider_name for item in chain) if chain else "none"


async def seed_universe(db: AsyncSession) -> dict:
    """
    Idempotent bootstrap of the full global instrument universe via the
    configured discovery provider.

    For every supported discovery type the provider is paged in batches
    of 250. Each page response contains all the metadata needed (name, sector,
    industry, country, exchange, currency, marketCap) so no per-instrument info
    call is required — the whole universe is seeded quickly and covers global
    markets (US, EU, Asia, etc.).

    Detail/listing/stat rows created per quote type:
      EQUITY / ETF / MUTUALFUND / INDEX → EquityDetail (sector, industry, …)
      CURRENCY                          → ForexDetail  (base/quote currencies)
      FUTURE                            → FutureDetail with best-effort fields
      all quote types                   → InstrumentListing + InstrumentStats when available

    Existing symbols have their metadata updated; new symbols get a new
    Instrument row.  Commits every page.
    """
    # Pre-resolve all InstrumentType IDs so we don't hit the DB per quote
    type_id_map: dict[str, int] = {}
    for qt, (asset_class, itype) in _QUOTE_TYPE_TAXONOMY.items():
        type_id_map[qt] = await _ensure_instrument_type(db, asset_class, itype)
    await db.commit()

    # Determine which quote types use EquityDetail
    _EQUITY_DETAIL_TYPES = {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}

    # Pre-load symbol → Instrument for cheap existence checks (exclude synthetics)
    existing: dict[str, Instrument] = {
        row.symbol: row
        for row in (await db.execute(select(Instrument).where(Instrument.is_synthetic.is_(False))))
        .scalars()
        .all()
    }

    created = 0
    updated = 0
    loop = asyncio.get_event_loop()
    discovery_chain = await resolve_provider_chain(db, ProviderCapability.UNIVERSE_DISCOVERY)
    if not discovery_chain:
        raise RuntimeError("No enabled universe discovery providers are available")
    discovery = discovery_chain[0]
    discovery_provider = discovery.provider
    discovery_provider_name = discovery.provider_name

    for quote_type in discovery_provider.supported_discovery_types():
        type_id = type_id_map[quote_type]
        offset = 0
        total = None

        logger.info("seed_universe: scanning %s…", quote_type)

        while True:
            page = await loop.run_in_executor(
                None,
                _screener_page_sync,
                discovery_provider,
                quote_type,
                offset,
            )
            quotes = page.get("quotes") or []

            if total is None:
                total = page.get("total", 0)
                logger.info("seed_universe: %s  total=%d", quote_type, total)

            if not quotes:
                break

            for q in quotes:
                symbol = (q.get("symbol") or "").strip()
                if not symbol:
                    continue

                name = q.get("longName") or q.get("shortName") or q.get("displayName") or symbol
                currency = q.get("currency")
                exchange = q.get("exchange") or q.get("fullExchangeName")
                fetched_at = datetime.now(UTC)

                inst = existing.get(symbol)
                if inst is None:
                    inst = Instrument(
                        symbol=symbol,
                        name=name,
                        instrument_type_id=type_id,
                        currency=currency,
                        is_active=True,
                    )
                    db.add(inst)
                    await db.flush()
                    existing[symbol] = inst
                    created += 1
                else:
                    if name:
                        inst.name = name
                    if currency:
                        inst.currency = currency
                    inst.instrument_type_id = type_id
                    inst.is_active = True

                provenance = dict(inst.field_provenance or {})
                provenance["symbol"] = {
                    "source": discovery_provider_name,
                    "fetched_at": fetched_at.isoformat(),
                    "provider_symbol": symbol,
                }
                if name:
                    provenance["name"] = {
                        "source": discovery_provider_name,
                        "fetched_at": fetched_at.isoformat(),
                        "provider_symbol": symbol,
                    }
                if currency:
                    provenance["currency"] = {
                        "source": discovery_provider_name,
                        "fetched_at": fetched_at.isoformat(),
                        "provider_symbol": symbol,
                    }
                inst.field_provenance = provenance

                await _upsert_listing(db, inst, symbol, currency)
                await register_provider_symbol(
                    db,
                    inst,
                    discovery_provider_name,
                    symbol,
                    provider_exchange_code=exchange,
                    provider_instrument_type=quote_type,
                    currency=currency,
                    is_primary=True,
                )
                await _upsert_stats(db, inst, q, source_provider=discovery_provider_name)
                await ensure_internal_identifier(db, inst)

                # ── Detail rows ──────────────────────────────────────────────
                if quote_type in _EQUITY_DETAIL_TYPES:
                    ed = (
                        await db.execute(
                            select(EquityDetail).where(EquityDetail.instrument_id == inst.id)
                        )
                    ).scalar_one_or_none()
                    if ed is None:
                        ed = EquityDetail(instrument_id=inst.id)
                        db.add(ed)

                    ed.sector = q.get("sector") or q.get("sectorDisplay") or ed.sector
                    ed.industry = q.get("industry") or q.get("industryDisplay") or ed.industry
                    ed.country = q.get("country") or ed.country
                    ed.exchange_mic = exchange or ed.exchange_mic
                    ed.market_cap_tier = _cap_tier(q.get("marketCap")) or ed.market_cap_tier
                    field_provenance = dict(ed.field_provenance or {})
                    for field_name, value in [
                        ("sector", q.get("sector") or q.get("sectorDisplay")),
                        ("industry", q.get("industry") or q.get("industryDisplay")),
                        ("country", q.get("country")),
                        ("exchange_mic", exchange),
                        ("market_cap_tier", _cap_tier(q.get("marketCap"))),
                    ]:
                        if value is not None:
                            field_provenance[field_name] = {
                                "source": discovery_provider_name,
                                "fetched_at": fetched_at.isoformat(),
                                "provider_symbol": symbol,
                            }
                    ed.field_provenance = field_provenance or None

                elif quote_type == "CURRENCY":
                    pair = _parse_forex_pair(symbol)
                    if pair:
                        fd = (
                            await db.execute(
                                select(ForexDetail).where(ForexDetail.instrument_id == inst.id)
                            )
                        ).scalar_one_or_none()
                        if fd is None:
                            fd = ForexDetail(
                                instrument_id=inst.id,
                                base_currency=pair[0],
                                quote_currency=pair[1],
                            )
                            db.add(fd)
                        field_provenance = dict(fd.field_provenance or {})
                        field_provenance["base_currency"] = {
                            "source": discovery_provider_name,
                            "fetched_at": fetched_at.isoformat(),
                            "provider_symbol": symbol,
                        }
                        field_provenance["quote_currency"] = {
                            "source": discovery_provider_name,
                            "fetched_at": fetched_at.isoformat(),
                            "provider_symbol": symbol,
                        }
                        fd.field_provenance = field_provenance

                elif quote_type == "FUTURE":
                    fut = (
                        await db.execute(
                            select(FutureDetail).where(FutureDetail.instrument_id == inst.id)
                        )
                    ).scalar_one_or_none()
                    if fut is None:
                        fut = FutureDetail(instrument_id=inst.id)
                        db.add(fut)

                    fut.underlying_name = name or fut.underlying_name
                    fut.is_continuous = symbol.endswith("=F") or fut.is_continuous
                    field_provenance = dict(fut.field_provenance or {})
                    if name:
                        field_provenance["underlying_name"] = {
                            "source": discovery_provider_name,
                            "fetched_at": fetched_at.isoformat(),
                            "provider_symbol": symbol,
                        }
                    if symbol.endswith("=F"):
                        field_provenance["is_continuous"] = {
                            "source": discovery_provider_name,
                            "fetched_at": fetched_at.isoformat(),
                            "provider_symbol": symbol,
                        }
                    fut.field_provenance = field_provenance or None

                # CRYPTOCURRENCY: no dedicated detail table yet; keep Instrument,
                # listing, stats, currency, and OHLCV source identity.

                updated += 1

            await db.commit()
            logger.info(
                "seed_universe: %s  offset=%d/%d  created=%d  updated=%d",
                quote_type,
                offset + len(quotes),
                total,
                created,
                updated,
            )

            offset += len(quotes)
            if not quotes or offset >= (total or 0):
                break

            await asyncio.sleep(settings.INSTRUMENT_DISCOVERY_PAGE_DELAY_SECONDS)

    logger.info("seed_universe complete: created=%d  updated=%d", created, updated)
    return {"created": created, "updated": updated, "total": created + updated}


# ── Bootstrap ─────────────────────────────────────────────────────────────────


async def bootstrap_isins(db: AsyncSession, limit: int | None = None) -> dict:
    """
    Populate the primary stable identifier for every active instrument that doesn't have one.

    Rate-limited via _IDENTIFIER_SEMAPHORE + a small sleep between calls.
    Safe to run multiple times — already-populated rows are skipped.
    """
    stmt = select(Instrument).where(
        (Instrument.primary_identifier_value.is_(None))
        | (Instrument.primary_identifier_type == "internal"),
        Instrument.is_active.is_(True),
        Instrument.is_synthetic.is_(False),
    )
    stmt = stmt.order_by(func.random())
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    instruments = list(result.scalars().all())

    logger.info("Bootstrap: fetching stable IDs for %d instruments", len(instruments))
    updated = 0
    skipped = 0

    for inst in instruments:
        async with _IDENTIFIER_SEMAPHORE:
            before_identifier = inst.primary_identifier_value
            before_type = inst.primary_identifier_type
            changed = await ensure_external_identifier(db, inst)
            await asyncio.sleep(settings.INSTRUMENT_IDENTIFIER_DELAY_SECONDS)

        if not changed and inst.primary_identifier_value == before_identifier and inst.primary_identifier_type == before_type:
            skipped += 1
            continue

        await ensure_internal_identifier(db, inst)
        updated += 1

        if (updated + skipped) % 50 == 0:
            await db.commit()
            logger.info("Bootstrap progress: %d updated, %d skipped", updated, skipped)

    await db.commit()
    logger.info(
        "Bootstrap complete: %d updated, %d skipped / %d total",
        updated,
        skipped,
        len(instruments),
    )
    return {"updated": updated, "skipped": skipped, "total": len(instruments)}


# ── Sync ─────────────────────────────────────────────────────────────────────


async def sync_instruments(db: AsyncSession, limit: int | None = None) -> dict:
    """
    Refresh metadata for all active instruments via the configured metadata provider.

    If the metadata provider returns no data, we do not immediately deactivate
    the instrument. Transient provider failures happen, so the sync remains conservative.
    """
    stmt = (
        select(Instrument)
        .options(selectinload(Instrument.provider_symbols))
        .outerjoin(InstrumentStats, InstrumentStats.instrument_id == Instrument.id)
        .where(
            Instrument.is_active.is_(True),
            Instrument.is_synthetic.is_(False),
        )
        .order_by(InstrumentStats.computed_at.nullsfirst(), Instrument.updated_at, Instrument.id)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    instruments = list(result.scalars().all())

    deactivated = 0
    updated = 0

    for inst in instruments:
        async with _METADATA_SEMAPHORE:
            try:
                execution = await execute_provider_call(
                    db,
                    ProviderCapability.INSTRUMENT_METADATA,
                    "sync_instrument_profile",
                    instrument_id=inst.id,
                    invoke=lambda provider, _provider_symbol: provider.get_instrument_profile(
                        provider_symbol_for_instrument(inst, provider.name)
                    ),
                    response_items=lambda result: 1 if result is not None else 0,
                    treat_empty_as_failure=True,
                )
                profile = execution.result
            except Exception as exc:
                logger.info("No metadata refresh available for %s: %s", inst.symbol, exc)
                profile = None
            await asyncio.sleep(settings.INSTRUMENT_METADATA_DELAY_SECONDS)

        if profile is None:
            continue
        info = profile.raw_payload or {}

        has_price = (
            profile.extra.get("regular_market_price") is not None
            or profile.extra.get("current_price") is not None
            or profile.extra.get("previous_close") is not None
        )
        if not has_price:
            logger.info("No price data for %s — may be delisted", inst.symbol)
            continue

        changed = False
        new_name = info.get("longName") or info.get("shortName")
        if new_name and new_name != inst.name:
            logger.info("Name update: %s '%s' → '%s'", inst.symbol, inst.name, new_name)
            inst.name = new_name
            changed = True

        if info.get("currency") and info["currency"] != inst.currency:
            inst.currency = info["currency"]
            changed = True

        await db.flush()
        await ingest_provider_profile(db, profile, instrument=inst)
        await ensure_internal_identifier(db, inst)

        quote_type = (info.get("quoteType") or "").upper()
        if quote_type in {"EQUITY", "ETF", "MUTUALFUND", "INDEX", ""}:
            ed = (
                await db.execute(select(EquityDetail).where(EquityDetail.instrument_id == inst.id))
            ).scalar_one_or_none()
            if ed is None:
                ed = EquityDetail(instrument_id=inst.id)
                db.add(ed)

            for attr, key in [
                ("sector", "sector"),
                ("industry", "industry"),
                ("country", "country"),
                ("website", "website"),
            ]:
                val = info.get(key)
                if val and val != getattr(ed, attr):
                    setattr(ed, attr, val)
                    changed = True

            cap_tier = _cap_tier(info.get("marketCap"))
            if cap_tier and cap_tier != ed.market_cap_tier:
                ed.market_cap_tier = cap_tier
                changed = True

            employees = info.get("fullTimeEmployees")
            if employees and employees != ed.employees:
                ed.employees = employees
                changed = True

        elif quote_type == "CURRENCY":
            pair = _parse_forex_pair(inst.symbol)
            if pair:
                fd = (
                    await db.execute(
                        select(ForexDetail).where(ForexDetail.instrument_id == inst.id)
                    )
                ).scalar_one_or_none()
                if fd is None:
                    db.add(
                        ForexDetail(
                            instrument_id=inst.id,
                            base_currency=pair[0],
                            quote_currency=pair[1],
                        )
                    )
                    changed = True

        elif quote_type == "FUTURE":
            fut = (
                await db.execute(select(FutureDetail).where(FutureDetail.instrument_id == inst.id))
            ).scalar_one_or_none()
            if fut is None:
                fut = FutureDetail(instrument_id=inst.id)
                db.add(fut)
                changed = True
            fut.underlying_name = new_name or fut.underlying_name
            fut.is_continuous = inst.symbol.endswith("=F") or fut.is_continuous

        if changed:
            updated += 1

    await db.commit()
    logger.info(
        "Sync complete: %d updated, %d deactivated / %d instruments",
        updated,
        deactivated,
        len(instruments),
    )
    return {"updated": updated, "deactivated": deactivated, "total": len(instruments)}


# ── Run tracking ─────────────────────────────────────────────────────────────


async def run_tracked_sync(
    db: AsyncSession,
    operation: str,
    *,
    limit: int | None = None,
) -> dict:
    """Run an instrument maintenance operation and persist an audit record."""
    run = InstrumentSyncRun(
        operation=operation,
        source=(
            await _provider_chain_label(db, ProviderCapability.UNIVERSE_DISCOVERY)
            if operation == "seed-universe"
            else await _provider_chain_label(db, ProviderCapability.INSTRUMENT_IDENTIFIERS)
            if operation == "bootstrap-ids"
            else await _provider_chain_label(db, ProviderCapability.INSTRUMENT_METADATA)
        ),
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.commit()

    try:
        if operation == "seed-universe":
            result = await seed_universe(db)
        elif operation == "sync-instruments":
            result = await sync_instruments(db, limit=limit)
        elif operation == "bootstrap-ids":
            result = await bootstrap_isins(db, limit=limit)
        else:
            raise ValueError(f"Unknown instrument sync operation: {operation}")

        run.status = "completed"
        run.finished_at = datetime.now(UTC)
        run.created_count = int(result.get("created", 0) or 0)
        run.updated_count = int(result.get("updated", 0) or 0)
        run.skipped_count = int(result.get("skipped", 0) or 0)
        run.total_count = int(result.get("total", 0) or 0)
        run.metrics = result
        await db.commit()
        return {"run_id": run.id, **result}
    except Exception as exc:
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.error = str(exc)
        await db.commit()
        raise
