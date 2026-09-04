"""Provider-exchange normalisation and canonical listing persistence helpers.

Provider APIs use a mixture of ISO 10383 MICs, short venue codes, and display
names.  The canonical security master stores the resolved MIC on ``Exchange``
and links each listing to it.  Unknown values are retained on the provider
observation/detail fields but are not guessed into a canonical exchange.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import ExchangeSessionRule


@dataclass(frozen=True)
class ExchangeDefinition:
    mic: str
    name: str
    country_code: str = "US"
    timezone: str = "America/New_York"
    market_open: str = "09:30"
    market_close: str = "16:00"
    currency: str = "USD"


_DEFINITIONS: dict[str, ExchangeDefinition] = {
    "XNAS": ExchangeDefinition(
        "XNAS",
        "Nasdaq",
    ),
    "XNYS": ExchangeDefinition("XNYS", "New York Stock Exchange"),
    "ARCX": ExchangeDefinition("ARCX", "NYSE Arca"),
    "XASE": ExchangeDefinition("XASE", "NYSE American"),
    "BATS": ExchangeDefinition("BATS", "Cboe BZX"),
    "XCBO": ExchangeDefinition("XCBO", "Cboe C2"),
    "IEXG": ExchangeDefinition("IEXG", "Investors Exchange"),
    "OTCM": ExchangeDefinition("OTCM", "OTC Markets"),
    "XCHI": ExchangeDefinition("XCHI", "Chicago Stock Exchange"),
}

_ALIASES: dict[str, str] = {
    "NASDAQ": "XNAS",
    "NASDAQ GLOBAL SELECT MARKET": "XNAS",
    "NASDAQ GLOBAL MARKET": "XNAS",
    "NASDAQ CAPITAL MARKET": "XNAS",
    "NMS": "XNAS",
    "NAS": "XNAS",
    "NYSE": "XNYS",
    "NYQ": "XNYS",
    "NEW YORK STOCK EXCHANGE": "XNYS",
    "NYSE ARCA": "ARCX",
    "ARCA": "ARCX",
    "PCX": "ARCX",
    "NYSE AMERICAN": "XASE",
    "AMEX": "XASE",
    "ASE": "XASE",
    "BATS": "BATS",
    "BZX": "BATS",
    "CBOE BZX": "BATS",
    "IEX": "IEXG",
    "IEXG": "IEXG",
    "OTC": "OTCM",
    "OTCQX": "OTCM",
    "OTCQB": "OTCM",
    "PINK": "OTCM",
    "CHX": "XCHI",
}


def normalize_exchange_mic(value: str | None) -> str | None:
    """Resolve a provider venue label to a known canonical MIC.

    We deliberately return ``None`` for unknown values instead of treating an
    arbitrary provider string as an exchange.  The raw/provider value remains
    available through provider symbols and field provenance.
    """

    text = str(value or "").strip().upper()
    if not text:
        return None
    return text if text in _DEFINITIONS else _ALIASES.get(text)


async def ensure_exchange(db: AsyncSession, value: str | None) -> Exchange | None:
    mic = normalize_exchange_mic(value)
    if mic is None:
        return None
    definition = _DEFINITIONS[mic]
    exchange = (
        await db.execute(select(Exchange).where(Exchange.mic == definition.mic))
    ).scalar_one_or_none()
    if exchange is None:
        exchange = Exchange(
            mic=definition.mic,
            name=definition.name,
            country_code=definition.country_code,
            timezone=definition.timezone,
            market_open=definition.market_open,
            market_close=definition.market_close,
            currency=definition.currency,
        )
        db.add(exchange)
        await db.flush()
    else:
        exchange.name = definition.name
        exchange.country_code = definition.country_code
        exchange.timezone = definition.timezone
        exchange.market_open = definition.market_open
        exchange.market_close = definition.market_close
        exchange.currency = definition.currency
    await ensure_default_session_rules(db, exchange)
    return exchange


async def ensure_default_session_rules(db: AsyncSession, exchange: Exchange) -> None:
    """Seed the versioned weekday regular session for a known US venue.

    Holidays and early closes are separate exception rows and must be supplied
    by a reviewed exchange-calendar source; this helper only establishes the
    baseline rule needed for session-aware coverage calculations.
    """

    valid_from = date(1970, 1, 1)
    existing = (
        await db.execute(
            select(ExchangeSessionRule).where(
                ExchangeSessionRule.exchange_id == exchange.id,
                ExchangeSessionRule.session_code == "regular",
                ExchangeSessionRule.valid_from == valid_from,
            )
        )
    ).scalars().all()
    weekdays = {row.weekday for row in existing}
    for weekday in range(5):
        if weekday in weekdays:
            continue
        db.add(
            ExchangeSessionRule(
                exchange_id=exchange.id,
                session_code="regular",
                weekday=weekday,
                opens_at=time(9, 30),
                closes_at=time(16, 0),
                valid_from=valid_from,
                provenance={"source": "exchange_catalog_default", "review_required": True},
            )
        )
    if len(weekdays) < 5:
        await db.flush()


async def upsert_instrument_listing(
    db: AsyncSession,
    instrument: Instrument,
    ticker: str,
    *,
    exchange_code: str | None = None,
    currency: str | None = None,
    is_primary: bool = False,
    reactivate_existing: bool = True,
    effective_at: datetime | None = None,
    known_at: datetime | None = None,
    delisted_at: datetime | None = None,
    source: str | None = None,
    provenance: dict | None = None,
) -> InstrumentListing:
    """Create/update one canonical listing without merging venue-distinct rows.

    ``reactivate_existing`` is explicit because provider discovery is evidence,
    not canonical listing-lifecycle truth. Discovery callers can preserve an
    inactive listing until a separate reconciliation decision promotes it.
    """

    exchange = await ensure_exchange(db, exchange_code)
    rows = (
        (
            await db.execute(
                select(InstrumentListing).where(
                    InstrumentListing.instrument_id == instrument.id,
                    InstrumentListing.ticker == ticker,
                )
            )
        )
        .scalars()
        .all()
    )
    listing = next(
        (row for row in rows if row.exchange_id == (exchange.id if exchange else None)),
        None,
    )
    # A pre-existing venue-less row can be safely enriched once.  If a distinct
    # venue already exists, create a second listing instead of collapsing it.
    if listing is None and exchange is not None:
        listing = next((row for row in rows if row.exchange_id is None), None)
    if listing is None:
        listing = InstrumentListing(
            instrument_id=instrument.id,
            exchange_id=exchange.id if exchange else None,
            ticker=ticker,
            currency=currency,
            is_primary=is_primary,
            is_active=True,
            effective_at=effective_at,
            known_at=known_at,
            delisted_at=delisted_at,
            last_verified_at=datetime.now(UTC),
            source=source,
            provenance=provenance or {},
        )
        db.add(listing)
    else:
        if exchange is not None:
            listing.exchange_id = exchange.id
        listing.currency = currency or listing.currency
        if reactivate_existing:
            listing.is_active = True
        listing.is_primary = is_primary or listing.is_primary
        if effective_at is not None:
            listing.effective_at = effective_at
        if known_at is not None:
            listing.known_at = known_at
        if delisted_at is not None:
            listing.delisted_at = delisted_at
        listing.last_verified_at = datetime.now(UTC)
        if source:
            listing.source = source
        if provenance:
            listing.provenance = {**(listing.provenance or {}), **provenance}
    return listing


def coerce_listing_lifecycle_at(value: object) -> datetime | None:
    """Normalize provider lifecycle dates to timezone-aware UTC timestamps."""

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
