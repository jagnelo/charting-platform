from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import AssetClass, InstrumentType
from app.models.instrument import Instrument


async def seed_e2e_instruments(db: AsyncSession) -> None:
    """Seed deterministic local instruments for browser tests without provider I/O."""

    asset_class = await _get_or_create_asset_class(db)
    instrument_type = await _get_or_create_instrument_type(db, asset_class.id)
    existing = await db.scalar(select(Instrument).where(Instrument.symbol == "AAPL"))
    if existing is not None:
        return
    db.add(
        Instrument(
            symbol="AAPL",
            name="Apple Inc.",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            field_provenance={"seed": "e2e"},
        )
    )


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
