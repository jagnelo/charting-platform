from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import AssetClass, InstrumentType
from app.models.etf_holdings import ETFProfile
from app.models.instrument import Instrument


async def seed_e2e_instruments(db: AsyncSession) -> None:
    """Seed deterministic workstation symbols for browser tests without provider I/O.

    These are canonical reference identities only: no bars, holdings, or provider
    entitlements are fabricated. Data-dependent tools therefore render explicit
    unavailable/coverage states instead of generating instrument-not-found errors.
    """

    asset_class = await _get_or_create_asset_class(db)
    instrument_type = await _get_or_create_instrument_type(db, asset_class.id)
    names = {
        "AAPL": "Apple Inc.",
        "SPY": "S&P 500 proxy ETF",
        "RSP": "S&P 500 equal-weight ETF",
        "QQQ": "Nasdaq-100 proxy ETF",
        "DIA": "Dow 30 proxy ETF",
        "IWM": "Russell 2000 proxy ETF",
        "XLK": "Technology Select Sector SPDR",
        "XLY": "Consumer Discretionary Select Sector SPDR",
        "XLC": "Communication Services Select Sector SPDR",
        "XLF": "Financial Select Sector SPDR",
        "XLV": "Health Care Select Sector SPDR",
        "XLI": "Industrial Select Sector SPDR",
        "XLP": "Consumer Staples Select Sector SPDR",
        "XLE": "Energy Select Sector SPDR",
        "XLU": "Utilities Select Sector SPDR",
        "XLRE": "Real Estate Select Sector SPDR",
        "XLB": "Materials Select Sector SPDR",
    }
    symbols = tuple(names)
    existing = {
        instrument.symbol.upper(): instrument
        for instrument in (await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))).scalars()
    }
    for symbol, name in names.items():
        if symbol not in existing:
            instrument = Instrument(
                symbol=symbol,
                name=name,
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
                field_provenance={"seed": "e2e", "identity_only": True},
            )
            db.add(instrument)
            existing[symbol] = instrument
    await db.flush()

    for symbol in symbols[1:]:
        profile = await db.scalar(select(ETFProfile).where(ETFProfile.instrument_id == existing[symbol].id))
        if profile is None:
            db.add(ETFProfile(
                instrument_id=existing[symbol].id,
                issuer="reference-only",
                fund_family="E2E reference identity",
                adapter_status="unresolved",
                extra_data={"seed": "e2e", "identity_only": True},
            ))


async def _get_or_create_asset_class(db: AsyncSession) -> AssetClass:
    existing = await db.scalar(select(AssetClass).where(AssetClass.name == "Equity"))
    if existing is not None:
        return existing
    asset_class = AssetClass(name="Equity", description="Equity instruments")
    db.add(asset_class)
    await db.flush()
    return asset_class


async def _get_or_create_instrument_type(
    db: AsyncSession, asset_class_id: int
) -> InstrumentType:
    existing = await db.scalar(
        select(InstrumentType).where(
            InstrumentType.name == "Stock",
            InstrumentType.asset_class_id == asset_class_id,
        )
    )
    if existing is not None:
        return existing
    instrument_type = InstrumentType(name="Stock", asset_class_id=asset_class_id)
    db.add(instrument_type)
    await db.flush()
    return instrument_type
