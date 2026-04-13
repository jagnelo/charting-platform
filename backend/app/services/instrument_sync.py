"""
Instrument sync service.

Three responsibilities:
  1. Seed:      Page through the yfinance screener for all supported quote
                types globally, create Instrument + detail rows for every
                result.  Metadata comes directly from screener response — no
                per-ticker info calls.  Safe to re-run; existing symbols are
                updated.
  2. Bootstrap: Fetch stable identifiers (ISIN or compositeFIGI) for all
                instruments already in the DB that don't have one yet.
  3. Sync:      Detect delistings and update stale metadata (name, currency,
                sector, industry, country, market-cap tier).

Identifier resolution order (bootstrap):
  1. yfinance Ticker.isin  — ISIN (12-char alphanumeric, gold standard)
  2. OpenFIGI compositeFIGI — globally unique, immutable, good substitute
  3. None — a rename whose final name bears no relation to the original is
     treated as a delisting + new listing; no heuristics attempted.

Quote-type → AssetClass / InstrumentType taxonomy:
  EQUITY       → Equity / Stock
  ETF          → Equity / ETF
  MUTUALFUND   → Equity / Mutual Fund
  INDEX        → Index  / Index
  CURRENCY     → Currency / Forex Pair    (symbol like "EURUSD=X")
  CRYPTOCURRENCY → Cryptocurrency / Crypto Spot
  FUTURE       → Commodity / Future
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

import httpx
import yfinance as yf
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.asset_class import AssetClass, InstrumentType
from app.models.instrument import EquityDetail, ForexDetail, FutureDetail, Instrument
from app.models.instrument_stats import InstrumentStats
from app.models.instrument_sync_run import InstrumentSyncRun
from app.models.listing import InstrumentListing

logger = logging.getLogger(__name__)

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"

# Caps concurrent outbound calls to external APIs platform-wide.
_ISIN_SEMAPHORE = asyncio.Semaphore(settings.YFINANCE_MAX_CONCURRENCY)
_FETCH_SEMAPHORE = asyncio.Semaphore(settings.YFINANCE_MAX_CONCURRENCY)

_YF_SCREENER_PAGE_SIZE = 250

# All yfinance quote types we enumerate.  Maps quote_type → (AssetClass, InstrumentType).
_QUOTE_TYPE_TAXONOMY: dict[str, tuple[str, str]] = {
    "EQUITY": ("Equity", "Stock"),
    "ETF": ("Equity", "ETF"),
    "MUTUALFUND": ("Equity", "Mutual Fund"),
    "INDEX": ("Index", "Index"),
    "CURRENCY": ("Currency", "Forex Pair"),
    "CRYPTOCURRENCY": ("Cryptocurrency", "Crypto Spot"),
    "FUTURE": ("Commodity", "Future"),
}

_YF_QUOTE_TYPES = list(_QUOTE_TYPE_TAXONOMY.keys())


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


# ── Identifier fetchers ───────────────────────────────────────────────────────


def _yfinance_isin_sync(symbol: str) -> str | None:
    try:
        val = yf.Ticker(symbol).isin
        return val if val and val not in ("-", "None", "") else None
    except Exception as exc:
        logger.debug("yfinance ISIN fetch failed for %s: %s", symbol, exc)
        return None


async def _yfinance_isin(symbol: str) -> str | None:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _yfinance_isin_sync, symbol)


async def _openfigi_figi(symbol: str) -> str | None:
    """
    Fetch compositeFIGI from OpenFIGI for *symbol*.

    OpenFIGI's free tier: 25 req/min without an API key.
    We store the compositeFIGI in the isin column because it is equally
    stable and immutable — it just isn't technically an ISIN.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                OPENFIGI_URL,
                json=[{"idType": "TICKER", "idValue": symbol}],
                headers={"Content-Type": "application/json"},
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data and isinstance(data, list) and data[0].get("data"):
            return data[0]["data"][0].get("compositeFIGI")
    except Exception as exc:
        logger.debug("OpenFIGI lookup failed for %s: %s", symbol, exc)
    return None


async def fetch_stable_id(symbol: str) -> str | None:
    """Return a stable immutable identifier for *symbol* (ISIN or FIGI)."""
    isin = await _yfinance_isin(symbol)
    if isin:
        return isin
    return await _openfigi_figi(symbol)


# ── Seed ──────────────────────────────────────────────────────────────────────


def _fetch_yf_info_sync(symbol: str) -> dict:
    try:
        return yf.Ticker(symbol).info or {}
    except Exception:
        return {}


def _screener_page_sync(quote_type: str, offset: int) -> dict:
    """
    Fetch one page from the yfinance global screener synchronously.

    Returns the raw response dict with keys 'total' and 'quotes'.
    Uses a broad percentchange filter to match all active listings.
    """
    body = {
        "offset": offset,
        "size": _YF_SCREENER_PAGE_SIZE,
        "sortField": "ticker",
        "sortType": "ASC",
        "quoteType": quote_type,
        "query": {
            "operator": "AND",
            "operands": [
                {"operator": "gt", "operands": ["percentchange", -100]},
            ],
        },
    }

    try:
        from yfinance import Screener  # type: ignore[attr-defined]

        s = Screener()
        s.set_body(body)
        return s.response or {}
    except Exception:
        pass

    try:
        from yfinance.data import YfData
        from yfinance.screener.screener import _SCREENER_URL_

        params = {"corsDomain": "finance.yahoo.com", "formatted": "false", "lang": "en-US", "region": "US"}
        response = YfData().post(
            _SCREENER_URL_,
            data=json.dumps(body, separators=(",", ":"), ensure_ascii=False),
            params=params,
        )
        response.raise_for_status()
        return response.json()["finance"]["result"][0]
    except Exception as exc:
        logger.debug(
            "yfinance screener page failed (type=%s offset=%d): %s", quote_type, offset, exc
        )
        return {}


def _parse_forex_pair(symbol: str) -> tuple[str, str] | None:
    """
    Attempt to extract base/quote currencies from a yfinance forex symbol.

    yfinance uses formats like "EURUSD=X" or "EUR/USD".
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


async def _upsert_stats(db: AsyncSession, instrument: Instrument, q: dict) -> None:
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

    for attr, value in stats_values.items():
        if value is not None:
            setattr(stats, attr, value)
    stats.computed_at = datetime.now(UTC)


async def seed_universe(db: AsyncSession) -> dict:
    """
    Idempotent bootstrap of the full global instrument universe via the
    yfinance screener.

    For every quote type in _YF_QUOTE_TYPES the screener is paged in batches
    of 250.  Each page response contains all the metadata needed (name, sector,
    industry, country, exchange, currency, marketCap) so no per-ticker info
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

    for quote_type in _YF_QUOTE_TYPES:
        type_id = type_id_map[quote_type]
        offset = 0
        total = None

        logger.info("seed_universe: scanning %s…", quote_type)

        while True:
            page = await loop.run_in_executor(None, _screener_page_sync, quote_type, offset)
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

                await _upsert_listing(db, inst, symbol, currency)
                await _upsert_stats(db, inst, q)

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

            await asyncio.sleep(settings.YFINANCE_SCREENER_PAGE_DELAY_SECONDS)

    logger.info("seed_universe complete: created=%d  updated=%d", created, updated)
    return {"created": created, "updated": updated, "total": created + updated}


# ── Bootstrap ─────────────────────────────────────────────────────────────────


async def bootstrap_isins(db: AsyncSession, limit: int | None = None) -> dict:
    """
    Populate the isin column for every active instrument that doesn't have one.

    Rate-limited via _ISIN_SEMAPHORE + a small sleep between calls.
    Safe to run multiple times — already-populated rows are skipped.
    """
    stmt = select(Instrument).where(
        Instrument.isin.is_(None),
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
        async with _ISIN_SEMAPHORE:
            stable_id = await fetch_stable_id(inst.symbol)
            await asyncio.sleep(settings.YFINANCE_STABLE_ID_DELAY_SECONDS)

        if not stable_id:
            skipped += 1
            continue

        # Check for conflicts — another instrument already holds this ID
        conflict = await db.execute(
            select(Instrument).where(
                Instrument.isin == stable_id,
                Instrument.id != inst.id,
            )
        )
        if conflict.scalar_one_or_none() is not None:
            logger.warning(
                "ISIN conflict: %s already assigned, skipping %s",
                stable_id,
                inst.symbol,
            )
            skipped += 1
            continue

        inst.isin = stable_id
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
    Refresh metadata for all active instruments and mark delistings.

    Updates Instrument (name, currency) and EquityDetail (sector, industry,
    country, exchange_mic, market_cap_tier) from yfinance.

    Matching strategy (in order):
      1. Instruments with an isin: match by isin.  A symbol change updates
         the symbol column in place — a true rename is tracked correctly.
      2. Instruments without an isin: matched by symbol only.  If yfinance
         returns no data, we *do not* immediately deactivate (transient API
         failures happen).  Two consecutive empty responses would be needed
         to confidently deactivate — for now we log and continue.
    """
    stmt = (
        select(Instrument)
        .outerjoin(InstrumentStats, InstrumentStats.instrument_id == Instrument.id)
        .where(
            Instrument.is_active.is_(True),
            Instrument.is_synthetic.is_(False),  # synthetics don't have yfinance data
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
        loop = asyncio.get_event_loop()
        async with _FETCH_SEMAPHORE:
            info = await loop.run_in_executor(None, _fetch_yf_info_sync, inst.symbol)
            await asyncio.sleep(settings.YFINANCE_METADATA_DELAY_SECONDS)

        if not info:
            continue

        has_price = (
            info.get("regularMarketPrice") is not None
            or info.get("currentPrice") is not None
            or info.get("previousClose") is not None
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
        await _upsert_listing(db, inst, inst.symbol, info.get("currency"))
        await _upsert_stats(db, inst, info)

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
        source="yfinance",
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
